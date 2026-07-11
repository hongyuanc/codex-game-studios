from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = spec_from_file_location("hook_runner", ROOT / ".codex/hooks/hook_runner.py")
HOOKS = module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOKS
SPEC.loader.exec_module(HOOKS)

VALIDATE_SPEC = spec_from_file_location(
    "studio_validate_hooks", ROOT / "tools/codex_studio/validate.py"
)
VALIDATE = module_from_spec(VALIDATE_SPEC)
sys.modules[VALIDATE_SPEC.name] = VALIDATE
VALIDATE_SPEC.loader.exec_module(VALIDATE)

EXPECTED_ACTIONS = {
    "session-start",
    "detect-gaps",
    "validate-command",
    "validate-assets",
    "validate-skill-change",
    "pre-compact",
    "post-compact",
    "subagent-start",
    "subagent-stop",
    "session-stop",
}
EXPECTED_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}
FIXTURE_EVENTS = {
    "session-start": "SessionStart",
    "pre-tool-bash": "PreToolUse",
    "post-tool-patch": "PostToolUse",
    "pre-compact": "PreCompact",
    "post-compact": "PostCompact",
    "subagent-start": "SubagentStart",
    "subagent-stop": "SubagentStop",
    "stop": "Stop",
}
COMMON_FIXTURE_FIELDS = {"session_id", "transcript_path", "cwd", "hook_event_name", "model"}
FIXTURE_FIELDS = {
    "session-start": COMMON_FIXTURE_FIELDS | {"permission_mode", "source"},
    "pre-tool-bash": COMMON_FIXTURE_FIELDS
    | {"turn_id", "permission_mode", "tool_name", "tool_use_id", "tool_input"},
    "post-tool-patch": COMMON_FIXTURE_FIELDS
    | {
        "turn_id",
        "permission_mode",
        "tool_name",
        "tool_use_id",
        "tool_input",
        "tool_response",
    },
    "pre-compact": COMMON_FIXTURE_FIELDS | {"turn_id", "trigger"},
    "post-compact": COMMON_FIXTURE_FIELDS | {"turn_id", "trigger"},
    "subagent-start": COMMON_FIXTURE_FIELDS
    | {"turn_id", "permission_mode", "agent_id", "agent_type"},
    "subagent-stop": COMMON_FIXTURE_FIELDS
    | {
        "turn_id",
        "permission_mode",
        "agent_id",
        "agent_type",
        "agent_transcript_path",
        "last_assistant_message",
        "stop_hook_active",
    },
    "stop": COMMON_FIXTURE_FIELDS
    | {"turn_id", "permission_mode", "last_assistant_message", "stop_hook_active"},
}


class HookParserTests(unittest.TestCase):
    def fixture(self, name):
        return json.loads(
            (ROOT / f"tests/studio/fixtures/hooks/{name}.json").read_text(
                encoding="utf-8"
            )
        )

    def test_bash_command_is_read_from_codex_payload(self):
        self.assertEqual("git status", HOOKS.tool_command(self.fixture("pre-tool-bash")))

    def test_apply_patch_paths_are_extracted(self):
        self.assertEqual(
            {"assets/data/items.json"},
            HOOKS.changed_paths(self.fixture("post-tool-patch")),
        )

    def test_apply_patch_move_destination_is_extracted(self):
        event = {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: assets/data/old_items.json\n"
                    "*** Move to: assets/data/new_items.json\n"
                    "@@\n{}\n"
                    "*** End Patch"
                )
            },
        }
        self.assertEqual(
            {"assets/data/old_items.json", "assets/data/new_items.json"},
            HOOKS.changed_paths(event),
        )

    def test_edit_and_write_file_paths_are_extracted(self):
        for tool_name in ("Edit", "Write"):
            event = {
                "tool_name": tool_name,
                "tool_input": {"file_path": r"assets\data\items.json"},
            }
            with self.subTest(tool_name=tool_name):
                self.assertEqual({"assets/data/items.json"}, HOOKS.changed_paths(event))

    def test_destructive_git_command_is_blocked(self):
        event = self.fixture("pre-tool-bash")
        event["tool_input"]["command"] = "git reset --hard"
        result = HOOKS.handle("validate-command", event, ROOT)
        self.assertEqual(2, result.exit_code)
        self.assertIn("blocked", result.stderr.lower())

    def test_force_push_and_destructive_clean_forms_are_blocked(self):
        for command in (
            "git push --force-with-lease origin feature",
            "git push -f origin feature",
            "git clean -fd",
            "git clean -xdf",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(2, result.exit_code)

    def test_structured_shell_parser_blocks_only_executed_destructive_git(self):
        destructive = (
            "git -C . reset --hard",
            "git -c core.filemode=false clean --force -d",
            "git --git-dir=.git clean -df",
            "git --work-tree . push origin +feature:main",
            "git --no-pager push --force-if-includes origin feature",
            '"git" "reset" "--hard"',
            "echo ready && git " "\\\n" "              -C . reset --hard",
            "{ git reset --hard; }",
            "if true; then git push -f origin feature; fi",
            "echo '<<EOF'\ngit reset --hard",
        )
        for command in destructive:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(2, result.exit_code)

    def test_structured_shell_parser_does_not_block_inert_or_dry_run_text(self):
        inert = (
            "echo git reset --hard",
            "printf '%s' 'git clean -fd'",
            "# git push --force origin main",
            "cat <<'EOF'\ngit reset --hard\nEOF",
            'echo "git push -f origin main"',
            "git clean -fdn",
            "git clean --force --dry-run -d",
            "git push --dry-run --force origin main",
            "git push -n origin +feature:main",
        )
        for command in inert:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(0, result.exit_code)

    def test_recursive_literal_execution_and_variable_expansions_are_blocked(self):
        destructive = (
            "echo `git reset --hard`",
            "echo $(git clean -fd)",
            "bash -c 'git push -f origin feature'",
            'sh -c "git reset --hard"',
            "eval 'git clean -fd'",
            'g=git; "$g" reset --hard',
            "g=Git.ExE; $g push origin +feature:main",
            "GIT.EXE reset --hard",
            "git.exe `printf reset` --hard",
            "git.exe `\n reset --hard",
        )
        for command in destructive:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(2, result.exit_code)

    def test_recursive_parser_preserves_inert_quoted_and_heredoc_text(self):
        inert = (
            "echo '$(git reset --hard)'",
            "printf '%s' '`git clean -fd`'",
            "bash -c 'echo git reset --hard'",
            "eval 'echo git clean -fd'",
            'g=echo; "$g" git reset --hard',
            "echo \"$(printf 'git reset --hard')\"",
            "cat <<'EOF'\ngit reset --hard\nEOF\necho done",
            'cat <<E"OF"\ngit clean -fd\nEOF\necho done',
            '"${tool}" status',
            'g=$(unknown); "$g" --version',
        )
        for command in inert:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(0, result.exit_code)

    def test_escaped_heredoc_delimiter_does_not_hide_following_command(self):
        command = "cat <<\\EOF\ngit reset --hard\nEOF\ngit clean -fd"
        result = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": command}},
            ROOT,
        )
        self.assertEqual(2, result.exit_code)

    def test_ambiguous_dynamic_destructive_git_intent_fails_closed(self):
        for command in (
            'g=$(unknown); "$g" reset --hard',
            '"${tool}" push --force origin feature',
            '"${tool}" push --dry-run --force origin feature',
            "git $(unknown) --hard",
            'g=gi; "${g}t" reset --har',
            '"${tool}.exe" reset --har',
            'git "${mode}" --har',
            'git "${mode}" --for -d',
            'git "${mode}" --mir origin',
            'git "${mode}" --help --har',
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(2, result.exit_code)

        for command in (
            "'$tool' reset --hard",
            r"\$tool reset --hard",
            "echo '$tool reset --hard'",
            r'echo "\$tool reset --hard"',
        ):
            with self.subTest(inert=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

    def test_dry_run_flags_after_double_dash_do_not_disable_blocking(self):
        for command in (
            "git clean -f -- -n",
            "git push -f -- -n",
            "git push --force origin -- -n",
            "git push --push-option -n --force origin feature",
            "git clean --exclude -n -f",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(2, result.exit_code)

    def test_git_unique_long_option_abbreviations_follow_git_rules(self):
        destructive = (
            "git reset --har",
            "git clean --for -d",
            "git push --mir origin",
            "git push --force-with-l origin feature",
            "git push --force-if-i origin feature",
        )
        for command in destructive:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)

        safe = (
            "git clean --dry-r --for -d",
            "git push --dry-r --force-with-l origin feature",
            "git push --fo origin feature",
        )
        for command in safe:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

        after_separator = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git clean --for -- --dry-r"}},
            ROOT,
        )
        self.assertEqual(2, after_separator.exit_code)

    def test_global_options_preserve_analysis_and_unknown_options_fail_closed(self):
        for command in (
            "git -P reset --hard",
            "git --no-lazy-fetch clean -fd",
            "git -P push -f origin feature",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)

        for command in (
            "git --mystery reset --hard",
            "git -Z clean -fd",
            "git --mystery commit -m test",
            "git --mystery push origin main",
        ):
            with self.subTest(unknown=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)
                self.assertIn("explicit direct Git", result.stderr)

        for command in (
            "git -P status",
            "git --no-lazy-fetch status",
            "git -v reset --hard",
            "git --version clean -fd",
        ):
            with self.subTest(safe=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

        blocked = HOOKS.HookResult(2, stderr="global commit sentinel\n")
        with mock.patch.object(HOOKS, "_validate_commit", return_value=blocked) as validator:
            commit = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": "git -P commit -m test"}},
                ROOT,
            )
        self.assertEqual(2, commit.exit_code)
        validator.assert_called_once_with(ROOT)

    def test_dynamic_commit_push_and_git_extensions_are_ambiguous(self):
        ambiguous = (
            '"${tool}" commit -m test',
            '"${tool}" push origin main',
            'git "${mode}" commit -m test',
            'git "${mode}" push origin main',
            'git "$(printf commit)" -m x',
            'mode=$(printf commit); git "${mode}" -m x',
            'git "$(printf push)" origin main',
            "git-reset --hard",
            "/usr/local/bin/git-clean -fd",
            r"C:\Git\bin\git-push.exe -f origin feature",
            "git-status",
        )
        for command in ambiguous:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)
                self.assertIn("explicit direct Git", result.stderr)

        for command in (
            '"${tool}" status',
            "echo git-reset --hard",
            "printf '%s' 'git-clean -fd'",
            'echo "& .\\git.exe reset --hard"',
            r'echo "\\server\share\git.exe clean -fd"',
        ):
            with self.subTest(inert=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

    def test_powershell_relative_and_unc_git_paths_are_analyzed(self):
        for command in (
            r"& .\git.exe reset --hard",
            r"& \\server\share\git.exe clean -fd",
            r"& .\git.exe push -f origin feature",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)

    def test_wrapper_option_values_and_command_inspection_are_parsed(self):
        destructive = (
            "sudo -u user git reset --hard",
            "sudo --user user git clean -fd",
            "env -u GIT_CONFIG git push -f origin feature",
            "env --unset=GIT_CONFIG git reset --hard",
            "env -S 'git reset --hard'",
            "env -S'git clean -fd'",
            "env --split-string='sudo -u user git clean -fd'",
            "exec -a codex-git git push -f origin feature",
            "time -p git reset --hard",
            "/usr/bin/time -f format git clean -fd",
            "nice -n 5 git push -f origin feature",
            "timeout -k 1s 5s git reset --hard",
            '"C:\\Program Files\\Git\\cmd\\git.exe" reset --hard',
            r"C:\Git\bin\git.exe reset --hard",
            '& "C:\\Program Files\\Git\\cmd\\git.exe" clean -fd',
            "git --% reset --hard",
            "git reset --% --hard",
            "command -- git clean -fd",
            "command -p git reset --hard",
            "builtin command git clean -fd",
            "builtin exec git reset --hard",
            "builtin eval 'git clean -fd'",
        )
        for command in destructive:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)

        for command in (
            "command -v git reset --hard",
            "command -V git clean -fd",
            "command --version git push -f origin feature",
            "command -p -v git reset --hard",
            "command -pv git clean -fd",
            "command -pV git push -f origin feature",
            "builtin git reset --hard",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

    def test_reset_and_clean_help_and_option_values_are_terminal_or_consumed(self):
        for command in (
            "git reset -h --hard",
            "git reset --help --hard",
            "git clean -h -fd",
            "git clean --help --force",
            "git reset --pathspec-from-file --hard",
            "git reset --pathspec-from-file=--hard",
            "git reset -hf --hard",
            "git reset -qh --hard",
            "git clean -hf -d",
            "git clean -qfh -d",
            "git push -hf origin main",
            "git push -qfh origin main",
            "git push --help origin main",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

        destructive = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git reset --pathspec-from-file paths --hard"}},
            ROOT,
        )
        self.assertEqual(2, destructive.exit_code)

        after_separator = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git clean -f -- -h"}},
            ROOT,
        )
        self.assertEqual(2, after_separator.exit_code)

        with mock.patch.object(HOOKS, "_validate_commit") as validator:
            commit_help = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": "git commit -qh"}},
                ROOT,
            )
        self.assertEqual(0, commit_help.exit_code)
        validator.assert_not_called()

    def test_commit_help_is_terminal_only_after_option_values_are_consumed(self):
        value_forms = (
            "git commit -m -h",
            "git commit -m --help",
            "git commit -m-h",
            "git commit --message=--help",
            "git commit -F -h",
            "git commit -F-h",
            "git commit -C -h",
            "git commit -CHEAD",
            "git commit -c -h",
            "git commit --reuse-message=--help",
            "git commit --reedit-message=--help",
            "git commit --fixup --help",
            "git commit --squash --help",
            "git commit --author --help",
            "git commit --date --help",
            "git commit --template --help",
            "git commit -t -h",
            "git commit -t-h",
            "git commit --template -h",
            "git commit --template=--help",
            "git commit --templ --help",
            "git commit --cleanup -h",
            "git commit --clean --help",
            "git commit -U -h",
            "git commit -U-h",
            "git commit --unified --help",
            "git commit --unif -h",
            "git commit -S-h",
            "git commit -qS-h",
            "git commit -mS-h",
            "git commit --untracked-files=--help",
            "git commit --inter-hunk-context -h",
            "git commit --inter-h --help",
            "git commit --mess --help",
            "git commit --auth --help",
            "git commit --trailer --help",
            "git commit --pathspec-from-file --help",
        )
        sentinel = HOOKS.HookResult(2, stderr="commit option sentinel\n")
        for command in value_forms:
            with self.subTest(command=command):
                with mock.patch.object(
                    HOOKS, "_validate_commit", return_value=sentinel
                ) as validator:
                    result = HOOKS.handle(
                        "validate-command", {"tool_input": {"command": command}}, ROOT
                    )
                self.assertEqual(2, result.exit_code)
                validator.assert_called_once_with(ROOT)

        for command in (
            "git commit -h",
            "git commit --help",
            "git commit -qh",
            "git commit -S -h",
            "git commit -qS -h",
            "git commit --un -h",
            "git commit --untracked-files -h",
        ):
            with self.subTest(terminal=command):
                with mock.patch.object(HOOKS, "_validate_commit") as validator:
                    result = HOOKS.handle(
                        "validate-command", {"tool_input": {"command": command}}, ROOT
                    )
                self.assertEqual(0, result.exit_code)
                validator.assert_not_called()

    def test_known_builtin_allowlist_includes_reviewed_plumbing_commands(self):
        for command in (
            "git pack-refs --all",
            "git multi-pack-index write",
            "git checkout-index --all",
            "git send-pack origin refs/heads/feature",
            "git scalar list",
            "git backfill --help",
            "git hook list",
            "git replay --help",
            "git receive-pack --help",
            "git update-server-info",
            "git upload-pack --help",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

        inventory = subprocess.run(
            ["git", "--list-cmds=builtins"],
            text=True,
            capture_output=True,
            check=False,
        )
        if inventory.returncode == 0:
            self.assertEqual(
                set(),
                set(inventory.stdout.split()) - HOOKS.KNOWN_GIT_SUBCOMMANDS,
            )

    def test_variable_expansion_respects_shell_word_splitting_and_quotes(self):
        destructive = (
            "cmd='git reset'; $cmd --hard",
            "cmd='git clean -fd'; $cmd",
            "cmd='git push --force'; $cmd origin feature",
        )
        for command in destructive:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(2, result.exit_code)

        for command in (
            "cmd='git reset'; \"$cmd\" --hard",
            "cmd='git clean -fd'; \"$cmd\"",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)

    def test_deep_parser_fallback_classifies_destructive_and_dry_run_intent(self):
        commands = {
            "git reset --har": 2,
            "git clean --for -d": 2,
            "git push --mir origin": 2,
            "git clean --dry-r --for -d": 0,
            "git reset --help --har": 0,
            "git mystery": 2,
            'git "${mode}" --har': 2,
            "git commit -qh": 0,
            "git --mystery push origin main": 2,
            "git-reset --hard": 2,
            '"${tool}" commit -m test': 2,
        }
        for inner, expected in commands.items():
            nested = inner
            for _ in range(HOOKS.MAX_SHELL_RECURSION + 2):
                nested = f"$({nested})"
            with self.subTest(inner=inner):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": nested}}, ROOT
                )
                self.assertEqual(expected, result.exit_code)

        with mock.patch.object(
            HOOKS, "git_invocations", side_effect=RecursionError("forced parser failure")
        ):
            for command, expected in commands.items():
                with self.subTest(forced=command):
                    result = HOOKS.handle(
                        "validate-command", {"tool_input": {"command": command}}, ROOT
                    )
                    self.assertEqual(expected, result.exit_code)

            for command in (
                "echo 'git reset --har'",
                "# git mystery",
                "cat <<'EOF'\ngit clean --for -d\nEOF",
                'echo "git reset --hard"',
            ):
                with self.subTest(conservative_inert=command):
                    result = HOOKS.handle(
                        "validate-command", {"tool_input": {"command": command}}, ROOT
                    )
                    self.assertEqual(0, result.exit_code)

        with mock.patch.object(
            HOOKS, "git_invocations", side_effect=RecursionError("primary failure")
        ), mock.patch.object(
            HOOKS, "_recursive_invocations", side_effect=RecursionError("fallback failure")
        ):
            for command, expected in commands.items():
                with self.subTest(conservative=command):
                    result = HOOKS.handle(
                        "validate-command", {"tool_input": {"command": command}}, ROOT
                    )
                    self.assertEqual(expected, result.exit_code)
            for command in (
                "echo 'git reset --har'",
                "# git mystery",
                "cat <<'EOF'\ngit clean --for -d\nEOF",
                'echo "git reset --hard"',
            ):
                with self.subTest(raw_inert=command):
                    result = HOOKS.handle(
                        "validate-command", {"tool_input": {"command": command}}, ROOT
                    )
                    self.assertEqual(0, result.exit_code)

    def test_raw_fallback_honors_help_and_blocks_extensions_and_dynamic_tails(self):
        expected = {
            "git commit -qh": "safe",
            "git reset -hf --hard": "safe",
            "git clean --dry-run --force": "safe",
            "git --mystery push origin main": "ambiguous",
            "git-reset --hard": "ambiguous",
            '"${tool}" commit -m test': "ambiguous",
            '"${tool}" push origin main': "ambiguous",
            "echo 'git-reset --hard'": "none",
            "# git --mystery push origin main": "none",
        }
        for command, classification in expected.items():
            with self.subTest(command=command):
                self.assertEqual(
                    classification,
                    HOOKS._raw_git_classification(command),
                )

    def test_all_real_commit_forms_invoke_staged_validation(self):
        commands = (
            "git commit -m test",
            "git -C . commit -m test",
            "git -c user.name=Codex commit -m test",
            "git --git-dir=.git --work-tree=. commit -m test",
            "git --no-pager " "\\\n" "              commit -m test",
        )
        blocked = HOOKS.HookResult(2, stderr="sentinel\n")
        for command in commands:
            with self.subTest(command=command):
                with mock.patch.object(HOOKS, "_validate_commit", return_value=blocked) as validator:
                    result = HOOKS.handle(
                        "validate-command",
                        {"tool_input": {"command": command}},
                        ROOT,
                    )
                self.assertEqual(2, result.exit_code)
                validator.assert_called_once_with(ROOT)

    def test_protected_push_refspec_destinations_are_recognized(self):
        for command in (
            "git push origin HEAD:main",
            "git push origin HEAD:refs/heads/main",
            "git push origin feature:refs/heads/master",
            "git -C . push origin refs/heads/feature:refs/heads/develop",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(0, result.exit_code)
                self.assertIn("protected branch", json.loads(result.stdout)["systemMessage"])

    def test_paths_outside_repository_are_ignored(self):
        event = {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: ../../etc/passwd\n*** End Patch"
            },
        }
        self.assertEqual(set(), HOOKS.repository_paths(event, ROOT))

    def test_repository_paths_reject_traversal_even_when_it_normalizes_inside(self):
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": "assets/staging/../data/items.json"},
        }
        self.assertEqual(set(), HOOKS.repository_paths(event, ROOT))

    def test_malformed_and_nul_paths_fail_open_without_crashing(self):
        for value in (
            "assets/data/bad\x00name.json",
            "\x00",
            "assets/\udcff.json",
            123,
            ["assets/data/items.json"],
            {"path": "assets/data/items.json"},
        ):
            event = {"tool_name": "Write", "tool_input": {"file_path": value}}
            with self.subTest(value=repr(value)):
                self.assertEqual(set(), HOOKS.repository_paths(event, ROOT))
                result = HOOKS.handle("validate-assets", event, ROOT)
                self.assertEqual(0, result.exit_code)
                self.assertIn("unsafe", result.stdout.lower())

    def test_windows_reparse_and_name_surrogate_metadata_is_rejected(self):
        ordinary = SimpleNamespace(st_mode=stat.S_IFREG, st_file_attributes=0, st_reparse_tag=0)
        reparse_attribute = SimpleNamespace(
            st_mode=stat.S_IFREG,
            st_file_attributes=0x400,
            st_reparse_tag=0,
        )
        junction_tag = SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_file_attributes=0,
            st_reparse_tag=0xA0000003,
        )
        self.assertFalse(HOOKS._is_link_or_reparse(ordinary))
        self.assertTrue(HOOKS._is_link_or_reparse(reparse_attribute))
        self.assertTrue(HOOKS._is_link_or_reparse(junction_tag))
        self.assertFalse(HOOKS._is_link_or_reparse((ROOT / "AGENTS.md").lstat()))


class HookBehaviorTests(unittest.TestCase):
    def fixture(self, name):
        return json.loads(
            (ROOT / f"tests/studio/fixtures/hooks/{name}.json").read_text(
                encoding="utf-8"
            )
        )

    def make_root(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return temporary, root

    def test_session_start_and_gap_detection_are_plain_text_and_fail_open(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        event = self.fixture("session-start")
        event["cwd"] = str(root)
        orientation = HOOKS.handle("session-start", event, root)
        gaps = HOOKS.handle("detect-gaps", event, root)
        self.assertEqual(0, orientation.exit_code)
        self.assertIn("Codex Game Studios", orientation.stdout)
        self.assertFalse(orientation.stdout.lstrip().startswith("{"))
        self.assertEqual(0, gaps.exit_code)
        self.assertIn("$start", gaps.stdout)

    def test_invalid_staged_json_blocks_commit(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        path = root / "assets/data/bad_data.json"
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", path.relative_to(root)], check=True)
        result = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git commit -m test"}},
            root,
        )
        self.assertEqual(2, result.exit_code)
        self.assertIn("not valid JSON", result.stderr)

    def test_staged_inspection_failures_block_real_commits(self):
        failures = (
            subprocess.CompletedProcess(["git"], 128, "", "index unavailable"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"),
            OSError("cannot inspect index"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                patcher = (
                    mock.patch.object(HOOKS, "_git", return_value=failure)
                    if isinstance(failure, subprocess.CompletedProcess)
                    else mock.patch.object(HOOKS, "_git", side_effect=failure)
                )
                with patcher:
                    result = HOOKS.handle(
                        "validate-command",
                        {"tool_input": {"command": "git -C . commit -m test"}},
                        ROOT,
                    )
                self.assertEqual(2, result.exit_code)
                self.assertIn("staged", result.stderr.lower())

    def test_configured_aliases_block_while_inline_aliases_are_proven(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        aliases = {
            "nuke": "reset --hard",
            "scrub": "clean -fd",
            "ship": "push --force origin feature",
            "ci": "commit",
            "boom": "!git reset --hard",
            "shellpreview": "!git clean -fdn",
            "preview": "clean -fdn",
            "st": "status",
        }
        for name, value in aliases.items():
            subprocess.run(
                ["git", "-C", str(root), "config", f"alias.{name}", value],
                check=True,
            )

        for command in (
            "git nuke",
            "git scrub",
            "git ship",
            "git boom",
            "git preview",
            "git shellpreview",
            "git st",
            "git ci -m test",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(2, result.exit_code)
                self.assertIn("explicit direct Git", result.stderr)

        inline = (
            "git -c 'alias.nuke=reset --hard' nuke",
            "git '-calias.scrub=clean -fd' scrub",
            "git -c 'alias.boom=!git push --mirror origin' boom",
        )
        for command in inline:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(2, result.exit_code)

        deferred = (
            "git -c 'alias.x=!$SHELL -c git reset --hard' x",
            "git -c 'alias.x=!$(echo git) reset --hard' x",
            "git -c 'alias.x=!`echo git` clean -fd' x",
            "git -c 'alias.x=!%COMSPEC% /c git reset --hard' x",
            "git -c 'alias.x=!$env:COMSPEC /c git reset --hard' x",
            "git -c 'alias.x=reset $MODE' x --hard",
        )
        for command in deferred:
            with self.subTest(deferred=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(2, result.exit_code)
                self.assertIn("explicit direct Git", result.stderr)

        for command in (
            "git -c alias.st=status st",
            "git -c 'alias.preview=clean -fdn' preview",
            "git -C . -c alias.st=status st",
        ):
            with self.subTest(inline_safe=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(0, result.exit_code)

        blocked = HOOKS.HookResult(2, stderr="inline commit sentinel\n")
        with mock.patch.object(HOOKS, "_validate_commit", return_value=blocked) as validator:
            inline_commit = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": "git -c alias.ci=commit ci -m test"}},
                root,
            )
        self.assertEqual(2, inline_commit.exit_code)
        validator.assert_called_once_with(root)

        with mock.patch.object(
            HOOKS, "git_invocations", side_effect=RecursionError("forced parser failure")
        ):
            destructive_alias = HOOKS.handle(
                "validate-command", {"tool_input": {"command": "git nuke"}}, root
            )
            destructive_shell_alias = HOOKS.handle(
                "validate-command", {"tool_input": {"command": "git boom"}}, root
            )
            dry_alias = HOOKS.handle(
                "validate-command", {"tool_input": {"command": "git preview"}}, root
            )
            dry_shell_alias = HOOKS.handle(
                "validate-command", {"tool_input": {"command": "git shellpreview"}}, root
            )
        self.assertEqual(2, destructive_alias.exit_code)
        self.assertEqual(2, destructive_shell_alias.exit_code)
        self.assertEqual(2, dry_alias.exit_code)
        self.assertEqual(2, dry_shell_alias.exit_code)

    def test_git_alias_loops_depth_and_config_failures_do_not_bypass_or_crash(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        subprocess.run(["git", "-C", str(root), "config", "alias.a", "b"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "alias.b", "a"], check=True)
        loop = HOOKS.handle(
            "validate-command", {"tool_input": {"command": "git a"}}, root
        )
        self.assertEqual(2, loop.exit_code)
        self.assertIn("explicit direct Git", loop.stderr)

        chain_length = HOOKS.MAX_ALIAS_RECURSION + 2
        for index in range(chain_length):
            target = f"a{index + 1}" if index + 1 < chain_length else "reset --hard"
            subprocess.run(
                ["git", "-C", str(root), "config", f"alias.a{index}", target],
                check=True,
            )
        deep = HOOKS.handle(
            "validate-command", {"tool_input": {"command": "git a0"}}, root
        )
        self.assertEqual(2, deep.exit_code)

        failure = subprocess.CompletedProcess(["git"], 128, "", "config unavailable")
        with mock.patch.object(HOOKS, "_git", return_value=failure):
            unreadable = HOOKS.handle(
                "validate-command", {"tool_input": {"command": "git unknown"}}, root
            )
        self.assertEqual(2, unreadable.exit_code)
        self.assertIn("explicit direct Git", unreadable.stderr)

    def test_repository_context_aliases_are_ambiguous_and_blocked(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        other = root / "other"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        subprocess.run(
            ["git", "-C", str(other), "config", "alias.nuke", "reset --hard"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(other), "config", "alias.scrub", "clean -fd"],
            check=True,
        )

        for command in (
            "git -C other nuke",
            "git --git-dir=other/.git --work-tree=other nuke",
            "git --git-dir other/.git --work-tree other scrub",
        ):
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(2, result.exit_code)

        invalid_compact = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git -Cother scrub"}},
            root,
        )
        self.assertEqual(2, invalid_compact.exit_code)
        self.assertIn("explicit direct Git", invalid_compact.stderr)

    def test_unknown_git_execution_blocks_across_environment_and_contexts(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        other = root / "other"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        ambiguous = (
            "git mystery",
            "git Status",
            "git ReSeT --hard",
            "HOME=/tmp git mystery",
            "env HOME=/tmp git mystery",
            "sudo -u user git mystery",
            "cd other && git mystery",
            "git -C other mystery",
            "git --git-dir=other/.git --work-tree=other mystery",
            "git --config-env=alias.mystery=ALIAS_VALUE mystery",
        )
        for command in ambiguous:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(2, result.exit_code)
                self.assertIn("explicit direct Git", result.stderr)

        known = (
            "git status",
            "git rev-parse --show-toplevel",
            "git maintenance run",
            "git -C other status",
            "env HOME=/tmp git status",
            "sudo -u user git status",
        )
        for command in known:
            with self.subTest(known=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, root
                )
                self.assertEqual(0, result.exit_code)

        inline_loop = HOOKS.handle(
            "validate-command",
            {
                "tool_input": {
                    "command": "git -c alias.a=b -c alias.b=a a"
                }
            },
            root,
        )
        self.assertEqual(2, inline_loop.exit_code)
        self.assertIn("explicit direct Git", inline_loop.stderr)

    def test_recursion_and_parser_failures_block_recognized_commits(self):
        for failure in (
            RecursionError("nested command limit"),
            ValueError("malformed shell"),
            TypeError("invalid parser token"),
        ):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch.object(HOOKS, "git_invocations", side_effect=failure):
                    result = HOOKS.handle(
                        "validate-command",
                        {"tool_input": {"command": "git.exe -C . commit -m test"}},
                        ROOT,
                    )
                self.assertEqual(2, result.exit_code)
                self.assertIn("parser", result.stderr.lower())

        with mock.patch.object(HOOKS, "_staged_paths", side_effect=RecursionError("loop")):
            staged = HOOKS._validate_commit(ROOT)
        self.assertEqual(2, staged.exit_code)
        self.assertIn("staged", staged.stderr.lower())

        with mock.patch.object(HOOKS, "git_invocations", side_effect=ValueError("malformed")):
            dynamic = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": '"${tool}" reset --hard "unterminated'}},
                ROOT,
            )
        self.assertEqual(2, dynamic.exit_code)
        self.assertIn("explicit direct Git", dynamic.stderr)

    def test_commit_quality_findings_warn_without_blocking(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        gameplay = root / "src/gameplay/combat.py"
        gameplay.parent.mkdir(parents=True)
        gameplay.write_text("damage = 25\n# TODO fix later\n", encoding="utf-8")
        gdd = root / "design/gdd/combat.md"
        gdd.parent.mkdir(parents=True)
        gdd.write_text("# Combat\n\n## Overview\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "add", str(gameplay.relative_to(root)), str(gdd.relative_to(root))],
            check=True,
        )
        result = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git commit -m test"}},
            root,
        )
        self.assertEqual(0, result.exit_code)
        payload = json.loads(result.stdout)
        self.assertIn("hardcoded gameplay", payload["systemMessage"])
        self.assertIn("missing required section", payload["systemMessage"])
        self.assertIn("TODO/FIXME/HACK", payload["systemMessage"])

    def test_protected_branch_push_warns_without_blocking(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        result = HOOKS.handle(
            "validate-command",
            {"tool_input": {"command": "git push origin main"}},
            root,
        )
        self.assertEqual(0, result.exit_code)
        self.assertIn("protected branch", json.loads(result.stdout)["systemMessage"])

    def test_protected_push_parser_skips_options_values_and_remote(self):
        safe = (
            "git push main feature",
            "git push --receive-pack main origin feature",
            "git push --push-option main origin feature",
            "git push --push-option=main origin feature",
            "git push --push-option +not-a-refspec origin feature",
            "git push -o main origin feature",
            "git push --repo main feature",
            "git push -- main feature",
        )
        for command in safe:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(0, result.exit_code)
                self.assertEqual("", result.stdout)

        protected = (
            "git push --receive-pack helper origin HEAD:main",
            "git push -- origin HEAD:refs/heads/main",
            "git push -o ci.skip origin feature:refs/heads/master",
        )
        for command in protected:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command",
                    {"tool_input": {"command": command}},
                    ROOT,
                )
                self.assertEqual(0, result.exit_code)
                self.assertIn("protected branch", json.loads(result.stdout)["systemMessage"])

    def test_broad_push_modes_cover_protected_branches_and_tags_do_not(self):
        broad = (
            "git push --all origin",
            "git push --branches origin",
            "git push --dry-run --mirror origin",
            "git push --dry-run origin '+:'",
            "git push origin 'refs/heads/*:refs/heads/*'",
            "git push origin ':'",
            "git push origin 'feature:refs/heads/*'",
        )
        for command in broad:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)
                self.assertIn("protected branch", json.loads(result.stdout)["systemMessage"])

        option_values = (
            "git push --recurse-submodules main origin feature",
            "git push --recurse-submodules=main origin feature",
            "git push --receive-pack main origin feature",
            "git push --receive-pack=main origin feature",
            "git push --push-option main origin feature",
            "git push --push-option=main origin feature",
            "git push -o main origin feature",
            "git push -omain origin feature",
            "git push origin 'refs/tags/*:refs/tags/*'",
            "git push origin 'refs/heads/release/*:refs/heads/release/*'",
        )
        for command in option_values:
            with self.subTest(command=command):
                result = HOOKS.handle(
                    "validate-command", {"tool_input": {"command": command}}, ROOT
                )
                self.assertEqual(0, result.exit_code)
                self.assertEqual("", result.stdout)

        branch = subprocess.CompletedProcess(["git"], 0, "main\n", "")
        with mock.patch.object(HOOKS, "_git", return_value=branch):
            tags = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": "git push --tags origin"}},
                ROOT,
            )
        self.assertEqual(0, tags.exit_code)
        self.assertEqual("", tags.stdout)

        with mock.patch.object(HOOKS, "_git", return_value=branch):
            option_tag = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": "git push -o --tags origin"}},
                ROOT,
            )
        self.assertIn("protected branch", json.loads(option_tag.stdout)["systemMessage"])

        feature = subprocess.CompletedProcess(["git"], 0, "feature\n", "")
        with mock.patch.object(HOOKS, "_git", return_value=feature):
            for value in ("--all", "--mirror"):
                with self.subTest(option_value=value):
                    result = HOOKS.handle(
                        "validate-command",
                        {"tool_input": {"command": f"git push -o {value} origin"}},
                        ROOT,
                    )
                    self.assertEqual("", result.stdout)

    def test_compound_commands_combine_commit_and_all_push_advisories(self):
        commit_warning = HOOKS._system_message("commit advisory")
        with mock.patch.object(HOOKS, "_validate_commit", return_value=commit_warning):
            result = HOOKS.handle(
                "validate-command",
                {
                    "tool_input": {
                        "command": (
                            "git commit -m test; "
                            "git push origin HEAD:main; "
                            "git push origin HEAD:master"
                        )
                    }
                },
                ROOT,
            )
        self.assertEqual(0, result.exit_code)
        message = json.loads(result.stdout)["systemMessage"]
        self.assertIn("commit advisory", message)
        self.assertIn("'main'", message)
        self.assertIn("'master'", message)

    def test_any_compound_block_wins_over_advisories(self):
        with mock.patch.object(HOOKS, "_validate_commit", return_value=HOOKS._system_message("commit advisory")):
            result = HOOKS.handle(
                "validate-command",
                {"tool_input": {"command": "git commit -m test; git push -f origin feature"}},
                ROOT,
            )
        self.assertEqual(2, result.exit_code)
        self.assertIn("blocked", result.stderr.lower())

    def test_asset_and_skill_checks_are_advisory_json(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        asset = root / "assets/data/Bad-Data.json"
        asset.parent.mkdir(parents=True)
        asset.write_text("{broken", encoding="utf-8")
        asset_event = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(asset)},
        }
        asset_result = HOOKS.handle("validate-assets", asset_event, root)
        self.assertEqual(0, asset_result.exit_code)
        self.assertIn("not valid JSON", json.loads(asset_result.stdout)["systemMessage"])

        skill_event = {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: .agents/skills/example/SKILL.md\n*** End Patch"
            },
        }
        skill_result = HOOKS.handle("validate-skill-change", skill_event, root)
        self.assertEqual(0, skill_result.exit_code)
        self.assertIn("$skill-test static example", json.loads(skill_result.stdout)["systemMessage"])

    def test_compaction_and_audit_writes_stay_in_production_paths(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        state = root / "production/session-state/active.md"
        state.parent.mkdir(parents=True)
        state.write_text("# Active\ncurrent task\n", encoding="utf-8")

        pre = HOOKS.handle("pre-compact", self.fixture("pre-compact"), root)
        self.assertEqual(0, pre.exit_code)
        self.assertIn("current task", json.loads(pre.stdout)["systemMessage"])
        self.assertTrue((root / "production/session-logs/compaction-log.txt").is_file())

        post = HOOKS.handle("post-compact", {"hook_event_name": "PostCompact"}, root)
        self.assertEqual(0, post.exit_code)
        self.assertIn("active.md", json.loads(post.stdout)["systemMessage"])

        agent = self.fixture("subagent-start")
        HOOKS.handle("subagent-start", agent, root)
        HOOKS.handle("subagent-stop", {**agent, "hook_event_name": "SubagentStop"}, root)
        audit = (root / "production/session-logs/agent-audit.log").read_text(encoding="utf-8")
        self.assertIn("Agent invoked: gameplay-programmer", audit)
        self.assertIn("Agent completed: gameplay-programmer", audit)

        stopped = HOOKS.handle("session-stop", self.fixture("stop"), root)
        self.assertEqual(0, stopped.exit_code)
        session_log = (root / "production/session-logs/session-log.md").read_text(encoding="utf-8")
        self.assertIn("Archived Session State", session_log)

    def test_session_state_symlinks_are_not_read_or_disclosed(self):
        temporary, root = self.make_root()
        external = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(external.cleanup)
        secret = Path(external.name) / "secret.md"
        secret.write_text("EXTERNAL-SECRET-CONTEXT", encoding="utf-8")
        state = root / "production/session-state/active.md"
        state.parent.mkdir(parents=True)
        state.symlink_to(secret)

        for action, event in (
            ("session-start", self.fixture("session-start")),
            ("pre-compact", self.fixture("pre-compact")),
            ("post-compact", self.fixture("post-compact")),
            ("session-stop", self.fixture("stop")),
        ):
            with self.subTest(action=action):
                result = HOOKS.handle(action, event, root)
                self.assertEqual(0, result.exit_code)
                self.assertNotIn("EXTERNAL-SECRET-CONTEXT", result.stdout)
                self.assertIn("unsafe", result.stdout.lower())

    def test_session_log_symlink_is_not_written_outside_repository(self):
        temporary, root = self.make_root()
        external = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(external.cleanup)
        production = root / "production"
        production.mkdir()
        (production / "session-logs").symlink_to(Path(external.name), target_is_directory=True)

        result = HOOKS.handle("subagent-start", self.fixture("subagent-start"), root)
        self.assertEqual(0, result.exit_code)
        self.assertIn("unsafe", result.stdout.lower())
        self.assertFalse((Path(external.name) / "agent-audit.log").exists())

    def test_asset_symlink_is_not_read_outside_repository(self):
        temporary, root = self.make_root()
        external = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(external.cleanup)
        outside = Path(external.name) / "outside.json"
        outside.write_text("{broken", encoding="utf-8")
        asset = root / "assets/data/items.json"
        asset.parent.mkdir(parents=True)
        asset.symlink_to(outside)
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(asset)},
        }

        result = HOOKS.handle("validate-assets", event, root)
        self.assertEqual(0, result.exit_code)
        message = json.loads(result.stdout)["systemMessage"]
        self.assertIn("unsafe", message.lower())
        self.assertNotIn("not valid JSON", message)

    def test_gap_detection_requires_actual_source_files_and_supports_engine_path(self):
        temporary, root = self.make_root()
        self.addCleanup(temporary.cleanup)
        core = root / "src/core"
        core.mkdir(parents=True)
        (core / "AGENTS.md").write_text("instructions", encoding="utf-8")

        instructions_only = HOOKS.handle("detect-gaps", self.fixture("session-start"), root)
        self.assertIn("NEW PROJECT", instructions_only.stdout)
        self.assertNotIn("core systems exist", instructions_only.stdout)

        engine = root / "src/engine"
        engine.mkdir()
        (engine / "runtime.py").write_text("pass\n", encoding="utf-8")
        actual_engine = HOOKS.handle("detect-gaps", self.fixture("session-start"), root)
        self.assertNotIn("NEW PROJECT", actual_engine.stdout)
        self.assertIn("core systems exist", actual_engine.stdout)

    def test_gap_detection_does_not_enumerate_symlinked_external_directories(self):
        temporary, root = self.make_root()
        external = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(external.cleanup)
        (Path(external.name) / "EXTERNAL-SECRET-PROTOTYPE").mkdir()
        (root / "prototypes").symlink_to(Path(external.name), target_is_directory=True)

        result = HOOKS.handle("detect-gaps", self.fixture("session-start"), root)
        self.assertEqual(0, result.exit_code)
        self.assertNotIn("EXTERNAL-SECRET-PROTOTYPE", result.stdout)
        self.assertIn("unsafe", result.stdout.lower())

    def test_unknown_action_and_malformed_input_fail_open_with_supported_output(self):
        runner = ROOT / ".codex/hooks/hook_runner.py"
        malformed = subprocess.run(
            [sys.executable, str(runner), "detect-gaps"],
            input="not-json",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, malformed.returncode)
        self.assertEqual("", malformed.stdout)

        unknown = subprocess.run(
            [sys.executable, str(runner), "unknown-action"],
            input=json.dumps(self.fixture("session-start")),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, unknown.returncode)
        self.assertIn("systemMessage", json.loads(unknown.stdout))


class HookConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / ".codex/hooks.json"
        self.config = json.loads(self.path.read_text(encoding="utf-8"))

    def handlers(self):
        for event, groups in self.config["hooks"].items():
            for group in groups:
                for handler in group["hooks"]:
                    yield event, group, handler

    def test_event_action_and_fixture_coverage(self):
        self.assertEqual(EXPECTED_EVENTS, set(self.config["hooks"]))
        actions = {
            handler["command"].rsplit(" ", 1)[-1]
            for _event, _group, handler in self.handlers()
        }
        self.assertEqual(EXPECTED_ACTIONS, actions)
        self.assertEqual(EXPECTED_ACTIONS, HOOKS.ACTIONS)
        self.assertEqual(EXPECTED_ACTIONS, set(HOOKS.HANDLERS))
        self.assertEqual(10, sum(1 for _ in self.handlers()))
        fixture_names = {path.stem for path in (ROOT / "tests/studio/fixtures/hooks").glob("*.json")}
        self.assertEqual(set(FIXTURE_EVENTS), fixture_names)
        fixture_events = set()
        for name in fixture_names:
            fixture = json.loads(
                (ROOT / f"tests/studio/fixtures/hooks/{name}.json").read_text(
                    encoding="utf-8"
                )
            )
            with self.subTest(fixture=name):
                self.assertEqual(FIXTURE_FIELDS[name], set(fixture))
                self.assertEqual(FIXTURE_EVENTS[name], fixture["hook_event_name"])
                fixture_events.add(fixture["hook_event_name"])
        self.assertEqual(EXPECTED_EVENTS, fixture_events)

    def test_tool_matchers_include_all_codex_aliases(self):
        self.assertEqual("Bash", self.config["hooks"]["PreToolUse"][0]["matcher"])
        post_matchers = {group["matcher"] for group in self.config["hooks"]["PostToolUse"]}
        self.assertEqual({"Edit|Write|apply_patch"}, post_matchers)

    def test_commands_are_portable_and_have_windows_overrides(self):
        for _event, _group, handler in self.handlers():
            with self.subTest(command=handler.get("command")):
                self.assertEqual("command", handler["type"])
                self.assertIn('"$(git rev-parse --show-toplevel)/.codex/hooks/hook_runner.py"', handler["command"])
                self.assertIn("commandWindows", handler)
                self.assertIn("git rev-parse --show-toplevel", handler["commandWindows"])
                self.assertIn(".codex/hooks/hook_runner.py", handler["commandWindows"])
                action = handler["command"].rsplit(" ", 1)[-1]
                self.assertIn(action, handler["commandWindows"])
                self.assertNotRegex(handler["command"] + handler["commandWindows"], r"/Users/|/home/|[A-Za-z]:\\Users\\")  # enforcement-literal

    def test_validator_accepts_native_config_and_rejects_invalid_contracts(self):
        self.assertTrue(hasattr(VALIDATE, "validate_hooks"))
        self.assertEqual([], VALIDATE.validate_hooks(self.path))
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "hooks.json"
            invalid.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "matcher": "Bash",
                                    "hooks": [
                                        {
                                            "type": "prompt",
                                            "command": "/Users/person/run.sh",  # enforcement-literal
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            messages = "\n".join(issue.message for issue in VALIDATE.validate_hooks(invalid))
            self.assertIn("unsupported handler type", messages)
            self.assertIn("absolute user path", messages)
            self.assertIn("missing Windows command override", messages)
            self.assertIn("hook_runner.py", messages)

    def test_validator_rejects_action_parity_matcher_timeout_and_shape_errors(self):
        cases = {}

        missing_action = json.loads(json.dumps(self.config))
        missing_action["hooks"]["SessionStart"][0]["hooks"].pop()
        cases["missing required hook actions"] = missing_action

        duplicate_action = json.loads(json.dumps(self.config))
        duplicate_action["hooks"]["SessionStart"][0]["hooks"].append(
            json.loads(json.dumps(duplicate_action["hooks"]["SessionStart"][0]["hooks"][0]))
        )
        cases["duplicate hook action"] = duplicate_action

        wrong_event = json.loads(json.dumps(self.config))
        wrong_event["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = wrong_event["hooks"]["PreToolUse"][0]["hooks"][0]["command"].replace("validate-command", "session-stop")
        wrong_event["hooks"]["PreToolUse"][0]["hooks"][0]["commandWindows"] = wrong_event["hooks"]["PreToolUse"][0]["hooks"][0]["commandWindows"].replace("validate-command", "session-stop")
        cases["event action mapping"] = wrong_event

        mismatched_platform = json.loads(json.dumps(self.config))
        mismatched_platform["hooks"]["Stop"][0]["hooks"][0]["commandWindows"] = mismatched_platform["hooks"]["Stop"][0]["hooks"][0]["commandWindows"].replace("session-stop", "pre-compact")
        cases["POSIX and Windows actions differ"] = mismatched_platform

        bad_matcher = json.loads(json.dumps(self.config))
        bad_matcher["hooks"]["PostToolUse"][0]["matcher"] = "["
        cases["invalid matcher regex"] = bad_matcher

        wrong_matcher = json.loads(json.dumps(self.config))
        wrong_matcher["hooks"]["PreToolUse"][0]["matcher"] = "exec_command"
        cases["expected matcher"] = wrong_matcher

        bad_timeout = json.loads(json.dumps(self.config))
        bad_timeout["hooks"]["Stop"][0]["hooks"][0]["timeout"] = "10"
        cases["timeout must be a positive integer"] = bad_timeout

        bad_shape = json.loads(json.dumps(self.config))
        bad_shape["hooks"]["Stop"][0]["hooks"][0]["extra"] = True
        cases["unsupported handler fields"] = bad_shape

        bad_invocation = json.loads(json.dumps(self.config))
        bad_invocation["hooks"]["Stop"][0]["hooks"][0]["command"] += " extra"
        cases["invalid runner invocation"] = bad_invocation

        nonportable_invocation = json.loads(json.dumps(self.config))
        nonportable_invocation["hooks"]["Stop"][0]["hooks"][0]["command"] = (
            "python3 /tmp/.codex/hooks/hook_runner.py session-stop"  # enforcement-literal
        )
        cases["repository-root runner invocation"] = nonportable_invocation

        with tempfile.TemporaryDirectory() as directory:
            for expected, config in cases.items():
                with self.subTest(expected=expected):
                    path = Path(directory) / f"{len(expected)}.json"
                    path.write_text(json.dumps(config), encoding="utf-8")
                    messages = "\n".join(issue.message for issue in VALIDATE.validate_hooks(path))
                    self.assertIn(expected, messages)

    def test_validator_requires_exact_anchored_platform_templates(self):
        mutations = (
            ("command", lambda value: value.replace("python3 ", "/usr/bin/python3 ", 1)),
            ("command", lambda value: "echo " + value),
            ("command", lambda value: value + "; echo spoof"),
            ("commandWindows", lambda value: value.replace("powershell ", "pwsh ", 1)),
            ("commandWindows", lambda value: "echo spoof; " + value),
            ("commandWindows", lambda value: value[:-1] + "; Write-Host spoof\""),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (field, mutate) in enumerate(mutations):
                with self.subTest(field=field, index=index):
                    config = json.loads(json.dumps(self.config))
                    handler = config["hooks"]["Stop"][0]["hooks"][0]
                    handler[field] = mutate(handler[field])
                    path = Path(directory) / f"template-{index}.json"
                    path.write_text(json.dumps(config), encoding="utf-8")
                    messages = "\n".join(issue.message for issue in VALIDATE.validate_hooks(path))
                    self.assertIn("invalid", messages.lower())
                    self.assertIn("runner invocation", messages)

    def test_tracked_legacy_hook_and_settings_inventory_is_removed(self):
        self.assertFalse((ROOT / ".claude/settings.json").exists())  # enforcement-literal
        legacy_hooks = sorted((ROOT / ".claude/hooks").glob("*.sh"))  # enforcement-literal
        self.assertEqual([], legacy_hooks)


if __name__ == "__main__":
    unittest.main()
