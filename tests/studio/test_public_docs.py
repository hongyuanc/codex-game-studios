from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "UPGRADING.md",
    ROOT / "docs/COLLABORATIVE-DESIGN-PRINCIPLE.md",
    ROOT / "docs/WORKFLOW-GUIDE.md",
    ROOT / "docs/engine-reference/README.md",
    *sorted((ROOT / "docs/examples").glob("*.md")),
    *sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.md")),
    ROOT / ".github/PULL_REQUEST_TEMPLATE.md",
    ROOT / ".github/CODEOWNERS",
]
# enforcement-literal-start
FORBIDDEN = (
    "Claude Code",
    "AskUserQuestion",
    "Task tool",
    "subagent_type",
    ".claude/",
    ".Codex/",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "claude --version",
    "slash command",
    "slash commands",
    "multi-select",
    "2-4 options",
    "2–4 options",
    "Batch up to 4",
    "session-start.sh",
)
PROVIDER_NAMES = re.compile(
    r"\b(?:Anthropic|Claude(?: Code)?)\b",
    re.IGNORECASE,
)
# enforcement-literal-end


def local_markdown_links(path: Path) -> list[str]:
    links = []
    for target in re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        target = target.strip().split(maxsplit=1)[0].strip("<>")
        if re.match(r"(?:https?://|mailto:|#)", target):
            continue
        links.append(target.split("#", 1)[0])
    return [link for link in links if link]


def markdown_section(text: str, heading: str) -> str:
    """Return one Markdown heading body through the next peer/parent heading."""

    marker = re.search(rf"(?m)^(?P<level>#+) {re.escape(heading)}\s*$", text)
    if marker is None:
        raise AssertionError(f"missing Markdown section: {heading}")
    level = len(marker.group("level"))
    following = re.search(rf"(?m)^#{{1,{level}}} ", text[marker.end() :])
    end = marker.end() + following.start() if following else len(text)
    return text[marker.end() : end]


def assert_fresh_repository_contract(testcase: unittest.TestCase, text: str) -> None:
    """Assert the documented fresh repository mutation boundary."""

    testcase.assertRegex(
        text,
        r"(?is)\b(?:plugin installation|skill discovery)\b"
        r"[^.!?]*\bzero writes\b[^.!?]*\bgame repository\b",
    )
    testcase.assertRegex(
        text,
        r"(?is)\bat most ten (?:mutations|mutating actions)\b",
    )
    testcase.assertRegex(
        text,
        r"(?is)\b(?:never|does not|do not)\b[^.!?]*"
        r"\b(?:creat(?:e|es|ed|ing)|cop(?:y|ies|ied|ying)|"
        r"install(?:s|ed|ing)?)\b[^.!?]*`\.agents/skills/`",
    )


def readme_upstream_attribution(text: str) -> tuple[str, str]:
    start = "<!-- upstream-" + "attribution-start -->"
    end = "<!-- upstream-" + "attribution-end -->"
    for line in text.splitlines():
        if (start in line or end in line) and line not in {start, end}:
            raise AssertionError(
                "README upstream attribution markers must be exact standalone lines"
            )
    lines = text.splitlines()
    start_lines = [index for index, line in enumerate(lines) if line == start]
    end_lines = [index for index, line in enumerate(lines) if line == end]
    if (
        len(start_lines) != 1
        or len(end_lines) != 1
        or start_lines[0] >= end_lines[0]
    ):
        raise AssertionError(
            "README must contain exactly one balanced upstream attribution block"
        )
    pattern = re.compile(
        rf"^{re.escape(start)}$\n(.*?)\n^{re.escape(end)}$",
        re.DOTALL | re.MULTILINE,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise AssertionError(
            "README must contain exactly one balanced upstream attribution block"
        )
    attribution = matches[0]
    protected_spans = [
        match.span()
        for token in FORBIDDEN
        if PROVIDER_NAMES.fullmatch(token) is None
        for match in re.finditer(re.escape(token), attribution)
    ]

    def redact_provider_name(match: re.Match[str]) -> str:
        if any(
            match.start() < protected_end and match.end() > protected_start
            for protected_start, protected_end in protected_spans
        ):
            return match.group(0)
        return ""

    runtime_text = pattern.sub(
        lambda match: (
            f"{start}\n{PROVIDER_NAMES.sub(redact_provider_name, match.group(1))}\n{end}"
        ),
        text,
    )
    return attribution, runtime_text


class PublicDocumentationTests(unittest.TestCase):
    def test_security_policy_uses_this_repository_private_advisory_route(self):
        # Arrange / Act
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

        # Assert
        self.assertIn(
            "https://github.com/hongyuanc/codex-game-studios/security/advisories/new",
            text,
        )
        self.assertNotIn(
            "https://github.com/Donchitos/Codex-Code-Game-Studios/security/advisories/new",
            text,
        )

    def test_readme_uses_plugin_native_start_flow(self):
        # Arrange / Act
        text = (ROOT / "README.md").read_text(encoding="utf-8")

        # Assert
        self.assertIn("### Codex app", text)
        self.assertIn("### Codex CLI", text)
        self.assertIn("Install Codex Game Studios from the repository marketplace", text)
        app = markdown_section(text, "Codex app")
        cli = markdown_section(text, "Codex CLI")
        fresh, legacy = text.split("## Legacy 1.0.0 lifecycle support", maxsplit=1)

        self.assertIn("Clone", app)
        self.assertIn("open", app.lower())
        self.assertIn("Plugins", app)
        self.assertIn("repository marketplace", app)
        self.assertIn("Start a new Codex task", app)
        self.assertIn("in-Codex", app)
        self.assertIn("$codex-game-studios:start", app)
        self.assertNotIn("codex plugin", app)
        self.assertIn("codex plugin marketplace add", cli)
        self.assertIn("codex plugin add", cli)
        self.assertIn("Start a new Codex task", cli)
        self.assertIn("in-Codex", cli)
        self.assertIn("$codex-game-studios:start", cli)
        self.assertIn("all 73 studio skills", fresh.lower())
        self.assertIn("$codex-game-studios:setup-engine", fresh)
        self.assertIn("$codex-game-studios:<skill>", fresh)
        self.assertNotIn("Use `$setup-engine`", fresh)
        assert_fresh_repository_contract(self, fresh)
        for operation in (
            "verify legacy installation",
            "repair legacy installation",
            "migrate to plugin-native",
            "uninstall legacy installation",
        ):
            self.assertNotIn(operation, fresh)
            self.assertIn(operation, legacy)
        self.assertNotIn("$codex-game-studios install", text)
        self.assertNotIn("$codex-game-studios update", text)
        self.assertIn(
            "codex plugin marketplace add hongyuanc/codex-game-studios --ref main",
            text,
        )
        self.assertIn(
            "codex plugin add codex-game-studios@codex-game-studios",
            text,
        )
        self.assertIn(
            "not yet listed in the public Codex Plugins Directory",
            text,
        )
        self.assertNotIn(
            "Install **Codex Game Studios** once from the public Codex Plugins Directory",
            text,
        )
        self.assertNotIn("v1.0.0-rc.1", text)
        self.assertNotIn("codex plugin install", text)

    def test_readmes_document_plugin_native_and_legacy_contracts(self):
        # Arrange / Act
        root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        plugin_readme = (
            ROOT / "plugins/codex-game-studios/README.md"
        ).read_text(encoding="utf-8")
        # Assert
        for text in (root_readme, plugin_readme):
            with self.subTest(document=text[:40]):
                fresh, legacy = text.split(
                    "## Legacy 1.0.0 lifecycle support", maxsplit=1
                )
                for required in (
                    "$codex-game-studios:start",
                    "$codex-game-studios:setup-engine",
                    "$codex-game-studios:<skill>",
                    "all 73 studio skills",
                    "small project-specific state",
                    "Godot",
                    "Unity",
                    "Unreal",
                    "installed separately",
                ):
                    self.assertIn(required, fresh)
                assert_fresh_repository_contract(self, fresh)
                for required in (
                    "digest-bound",
                    "verify legacy installation",
                    "repair legacy installation",
                    "migrate to plugin-native",
                    "uninstall legacy installation",
                ):
                    self.assertIn(required, legacy)

        self.assertIn("source checkout", root_readme.lower())
        self.assertIn("`$<skill>`", root_readme)
        for command in (
            "setup-engine",
            "brainstorm",
            "map-systems",
            "design-system",
            "prototype",
            "create-architecture",
            "create-epics",
            "create-stories",
            "dev-story",
            "story-done",
            "qa-plan",
            "gate-check",
            "help",
        ):
            with self.subTest(command=command):
                self.assertIn(f"$codex-game-studios:{command}", root_readme)
                self.assertNotIn(f"${command}", root_readme)

    def test_fresh_repository_contract_rejects_unbound_invalid_mutants(self):
        # Arrange
        invalid_mutants = {
            "cap_only": (
                "Plugin installation and skill discovery make zero writes to the "
                "game repository. Start asks at most ten questions. It never creates "
                "`.agents/skills/`."
            ),
            "path_only": (
                "Plugin installation and skill discovery make zero writes to the "
                "game repository. Start uses at most ten mutations. It may create "
                "`.agents/skills/`, but never overwrites existing files."
            ),
            "zero_only": (
                "Plugin installation writes project files. The help screen makes zero "
                "writes to the game repository. Start uses at most ten mutations. "
                "It never creates `.agents/skills/`."
            ),
        }

        # Act / Assert
        for name, mutant in invalid_mutants.items():
            with self.subTest(mutant=name), self.assertRaises(AssertionError):
                assert_fresh_repository_contract(self, mutant)

    def test_root_entry_links_and_native_instruction_contract_resolve(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        local_links = [
            target
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
            if not re.match(r"(?:https?://|mailto:|#)", target)
        ]
        missing = [target for target in local_links if not (ROOT / target).exists()]
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotRegex(agents, r"(?m)^@")
        required_reads = (
            ".codex/docs/directory-structure.md",
            ".codex/docs/technical-preferences.md",
            ".codex/docs/coordination-rules.md",
            ".codex/docs/coding-standards.md",
            ".codex/docs/context-management.md",
        )
        self.assertIn("must read", agents.lower())
        for target in required_reads:
            self.assertIn(f"`{target}`", agents)
            if not (ROOT / target).exists():
                missing.append(target)
        self.assertEqual([], missing)

    def test_hook_docs_describe_best_effort_defense_in_depth(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        hooks = (ROOT / ".codex/docs/hooks-reference.md").read_text(
            encoding="utf-8"
        )
        combined = readme + hooks
        self.assertIn("defense-in-depth", combined)
        self.assertIn("best-effort", combined)
        self.assertIn("permissions", combined)
        self.assertIn("durable instructions", combined)
        self.assertNotIn("part of the security boundary", combined)
        self.assertIn("tests.studio.test_hooks", hooks)
        self.assertNotIn("tests.studio.test_hook_runner", hooks)

    def test_all_public_markdown_links_resolve_recursively(self):
        missing = []
        for path in PUBLIC:
            if path.suffix != ".md":
                continue
            for target in local_markdown_links(path):
                destination = (path.parent / target).resolve()
                if not destination.exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual([], missing)

    def test_readme_has_plugin_native_entry_path(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Codex Game Studios", text)
        self.assertIn("49 agents", text)
        self.assertIn("73 skills", text)
        app = markdown_section(text, "Codex app")
        self.assertIn("repository marketplace", app)
        self.assertIn("start a new codex task", app.lower())
        self.assertIn("$codex-game-studios:start", text)
        self.assertNotIn("Use the source checkout directly", text)
        for required in ("3 Sol", "44 Terra", "2 Luna", "phase-gated", "engine pack"):
            self.assertIn(required, text)

    def test_security_reports_target_this_repository(self):
        text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

        self.assertIn(
            "https://github.com/hongyuanc/codex-game-studios/security/advisories/new",
            text,
        )
        self.assertNotIn("Donchitos/Codex-Code-Game-Studios", text)

    def test_superpowers_plans_do_not_ship_machine_specific_paths(self):
        internal_plans = ROOT / "docs/superpowers"
        # enforcement-literal-start
        machine_paths = re.compile(
            r"(?:/Users/|/home/|/private/tmp/|[A-Za-z]:[\\/]Users[\\/])"
        )
        # enforcement-literal-end
        unsafe_files = (
            [
                path.relative_to(ROOT)
                for path in internal_plans.rglob("*")
                if path.is_file()
                and machine_paths.search(path.read_text(encoding="utf-8"))
            ]
            if internal_plans.exists()
            else []
        )
        self.assertEqual([], unsafe_files)

    def test_readme_credits_upstream_and_defines_native_delta(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        attribution, runtime_text = readme_upstream_attribution(readme)
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")

        self.assertIn(  # enforcement-literal
            "[Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios)",  # enforcement-literal
            attribution,
        )
        self.assertIn(
            "[Donchitos](https://github.com/Donchitos)",
            attribution,
        )
        self.assertIn("independent Codex-native adaptation", attribution)
        self.assertIn("not an official port", attribution)
        self.assertIn("MIT", attribution)
        self.assertIn("Copyright (c) 2026 Donchitos", license_text)
        self.assertNotIn("Claude Code", runtime_text)  # enforcement-literal
        self.assertIn(
            "Codex Game Studios is distributed under the [MIT License](LICENSE). The\n"
            "original `Copyright (c) 2026 Donchitos` and MIT permission notice are retained\n"
            "for the upstream work, and this Codex-native adaptation is distributed under\n"
            "the same license.",
            readme,
        )
        for claim in (
            "Not a thin rename",
            "plugin-bundled skills",
            "repository-owned configuration",
            "Sol, Terra, and Luna",
            "10 Python-based Codex hook actions",
            "Transactional engine packs",
            "state-aware repository validator",
        ):
            self.assertIn(claim, readme)

    # enforcement-literal-start
    def test_readme_attribution_runtime_view_exempts_only_provider_names(self):
        readme = (
            "Codex\n"
            "<!-- upstream-attribution-start -->\n"
            "Claude Code and Anthropic\n"
            ".claude/ AskUserQuestion /start /Users/example/project\n"
            "<!-- upstream-attribution-end -->\n"
        )

        attribution, runtime_text = readme_upstream_attribution(readme)

        self.assertIn("Claude Code and Anthropic", attribution)
        self.assertNotIn("Claude Code", runtime_text)
        self.assertNotIn("Anthropic", runtime_text)
        for token in (".claude/", "AskUserQuestion", "/start", "/Users/example/project"):
            self.assertIn(token, runtime_text)

    def test_readme_attribution_runtime_view_keeps_provider_names_outside_block(self):
        readme = (
            "Claude Code before\n"
            "<!-- upstream-attribution-start -->\n"
            "Claude Code and Anthropic\n"
            "<!-- upstream-attribution-end -->\n"
            "Anthropic after\n"
        )

        _, runtime_text = readme_upstream_attribution(readme)

        self.assertIn("Claude Code before", runtime_text)
        self.assertIn("Anthropic after", runtime_text)

    def test_readme_provider_policy_is_case_insensitive_and_block_scoped(self):
        inside = (
            "Codex\n"
            "<!-- upstream-attribution-start -->\n"
            "Claude, claude code, and aNtHrOpIc\n"
            "<!-- upstream-attribution-end -->\n"
        )
        _, inside_runtime_text = readme_upstream_attribution(inside)
        self.assertIsNone(PROVIDER_NAMES.search(inside_runtime_text))

        outside_readmes = {
            "lowercase_product_before": (
                "claude code before\n"
                "<!-- upstream-attribution-start -->\n"
                "Anthropic\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "mixed_case_provider_after": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
                "aNtHrOpIc after\n"
            ),
            "standalone_product_before": (
                "Claude before\n"
                "<!-- upstream-attribution-start -->\n"
                "Anthropic\n"
                "<!-- upstream-attribution-end -->\n"
            ),
        }
        for case, readme in outside_readmes.items():
            with self.subTest(case=case):
                _, runtime_text = readme_upstream_attribution(readme)
                self.assertIsNotNone(PROVIDER_NAMES.search(runtime_text))

    def test_readme_attribution_markers_must_be_exact_standalone_lines(self):
        invalid_readmes = {
            "prefixed_start": (
                "prefix <!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "suffixed_start": (
                "<!-- upstream-attribution-start --> suffix\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "prefixed_end": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "prefix <!-- upstream-attribution-end -->\n"
            ),
            "suffixed_end": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end --> suffix\n"
            ),
            "inline": (
                "<!-- upstream-attribution-start --> Claude Code "
                "<!-- upstream-attribution-end -->\n"
            ),
        }
        for case, readme in invalid_readmes.items():
            with self.subTest(case=case):
                with self.assertRaisesRegex(
                    AssertionError,
                    "exact standalone lines",
                ):
                    readme_upstream_attribution(readme)

    def test_readme_attribution_requires_one_balanced_ordered_block(self):
        invalid_readmes = {
            "nested_start": (
                "<!-- upstream-attribution-start -->\n"
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "extra_close": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "start_only": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
            ),
            "end_only": (
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "duplicate_blocks": (
                "<!-- upstream-attribution-start -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-end -->\n"
                "<!-- upstream-attribution-start -->\n"
                "Anthropic\n"
                "<!-- upstream-attribution-end -->\n"
            ),
            "reversed": (
                "<!-- upstream-attribution-end -->\n"
                "Claude Code\n"
                "<!-- upstream-attribution-start -->\n"
            ),
        }
        for case, readme in invalid_readmes.items():
            with self.subTest(case=case):
                with self.assertRaisesRegex(
                    AssertionError,
                    "exactly one balanced upstream attribution block",
                ):
                    readme_upstream_attribution(readme)
    # enforcement-literal-end

    def test_runtime_public_surface_is_codex_only(self):
        failures = []
        for path in PUBLIC:
            text = path.read_text(encoding="utf-8")
            if path == ROOT / "README.md":
                _, provider_scan_text = readme_upstream_attribution(text)
                provider_match = PROVIDER_NAMES.search(provider_scan_text)
                if provider_match is not None:
                    failures.append(
                        f"{path.relative_to(ROOT)}: {provider_match.group(0)}"
                    )
            for token in FORBIDDEN:
                if token == "Claude Code" and path == ROOT / "README.md":  # enforcement-literal
                    continue
                if token in text:
                    failures.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], failures)

    def test_public_runtime_contract_is_native_and_phase_gated(self):
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        principle = (ROOT / "docs/COLLABORATIVE-DESIGN-PRINCIPLE.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for token in ("name", "description", "trigger", ".codex/agents/*.toml", "hook_runner.py"):
            self.assertIn(token, contributing)
        self.assertIn("phase-gated", contributing)
        self.assertIn("hook_runner.py", security)
        self.assertIn("OpenAI", security)
        self.assertIn("$start", agents)
        self.assertNotIn("/start", agents)  # enforcement-literal
        self.assertNotIn("Claude", gitignore)  # enforcement-literal

        for token in (
            "phase-gated", "request_user_input", "one decision at a time",
            "1-3 questions", "2-3 mutually exclusive options", ".codex/agents/*.toml",
        ):
            self.assertIn(token, principle)
        self.assertNotIn("before every file", principle.lower())
        self.assertNotIn("May I write this to", principle)

    def test_workflow_guide_has_exact_native_inventory(self):
        text = (ROOT / "docs/WORKFLOW-GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("73 skills", text)
        self.assertIn("10 Python hook actions", text)
        self.assertIn(".codex/hooks/hook_runner.py", text)
        self.assertNotIn("12 automated hooks", text)
        self.assertNotIn("/clear", text)
        self.assertNotIn("controls the status line", text)

    def test_public_runtime_path_and_workflow_references_are_real(self):
        engine_reference = (ROOT / "docs/engine-reference/README.md").read_text(encoding="utf-8")
        gate_example = (ROOT / "docs/examples/session-gate-check-phase-transition.md").read_text(encoding="utf-8")
        tr_registry = (ROOT / "docs/architecture/tr-registry.yaml").read_text(encoding="utf-8")
        architecture_registry = (ROOT / "docs/registry/architecture.yaml").read_text(encoding="utf-8")

        self.assertIn("$setup-engine", engine_reference)
        self.assertNotIn("$refresh-docs", engine_reference)
        self.assertNotIn("status line", gate_example.lower())
        for broken in (
            "design$gdd$",
            "docs$architecture$",
            "docs$registry$",
        ):
            self.assertNotIn(broken, tr_registry + architecture_registry)
        self.assertIn("$architecture-review", architecture_registry)

    def test_public_docs_do_not_define_a_competing_review_mode_file(self):
        failures = []
        for path in PUBLIC:
            text = path.read_text(encoding="utf-8")
            for legacy in (
                "production/review-mode.txt",
                "production/session-state/review-mode.txt",
            ):
                if legacy in text:
                    failures.append(f"{path.relative_to(ROOT)}: {legacy}")
        self.assertEqual([], failures)

    def test_public_templates_use_native_component_contracts(self):
        files = [
            ROOT / ".github/ISSUE_TEMPLATE/bug_report.md",
            ROOT / ".github/ISSUE_TEMPLATE/feature_request.md",
            ROOT / ".github/PULL_REQUEST_TEMPLATE.md",
            ROOT / ".github/CODEOWNERS",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        self.assertIn("$<skill>", combined)
        self.assertIn(".codex/agents/", combined)
        self.assertIn(".codex/hooks/hook_runner.py", combined)
        self.assertIn("AGENTS.md", combined)
        self.assertNotIn("slash command", combined.lower())

    def test_upgrade_guide_preserves_a_complete_migration_method(self):
        text = (ROOT / "UPGRADING.md").read_text(encoding="utf-8")
        for heading in (
            "## Choose a migration strategy", "## Preserve project-owned work",
            "## Merge without losing customizations", "## Breaking changes",
            "## Verification checklist", "## Rollback",
        ):
            self.assertIn(heading, text)
        self.assertIn("source system", text)
        self.assertIn("Codex-only", text)
        self.assertIn("production/migration/claude-to-codex-coverage.yaml", text)  # enforcement-literal

    def test_public_skill_invocations_use_dollar_syntax(self):
        names = {
            path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        slash = re.compile(r"(?<![A-Za-z0-9_.-])/((?:" + "|".join(sorted(map(re.escape, names))) + r"))\b")
        failures = []
        for path in PUBLIC:
            for match in slash.finditer(path.read_text(encoding="utf-8")):
                failures.append(f"{path.relative_to(ROOT)}: /{match.group(1)}")
        self.assertEqual([], failures)

    def test_upgrade_guide_is_historical_only(self):
        text = (ROOT / "UPGRADING.md").read_text(encoding="utf-8")
        self.assertIn("source system", text)
        self.assertIn("Codex-only", text)
        self.assertNotIn("runtime compatibility", text.lower())


if __name__ == "__main__":
    unittest.main()
