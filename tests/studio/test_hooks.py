from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


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

    def test_paths_outside_repository_are_ignored(self):
        event = {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Update File: ../../etc/passwd\n*** End Patch"
            },
        }
        self.assertEqual(set(), HOOKS.repository_paths(event, ROOT))


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
        self.assertEqual(
            {"session-start", "pre-tool-bash", "post-tool-patch", "subagent-start", "pre-compact", "stop"},
            fixture_names,
        )
        for name in fixture_names:
            fixture = json.loads(
                (ROOT / f"tests/studio/fixtures/hooks/{name}.json").read_text(
                    encoding="utf-8"
                )
            )
            with self.subTest(fixture=name):
                self.assertTrue(
                    {"session_id", "cwd", "hook_event_name", "model"}
                    <= set(fixture)
                )

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
                self.assertNotRegex(handler["command"] + handler["commandWindows"], r"/Users/|/home/|[A-Za-z]:\\Users\\")

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
                                            "command": "/Users/person/run.sh",
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


if __name__ == "__main__":
    unittest.main()
