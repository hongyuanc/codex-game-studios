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
# enforcement-literal-end


def local_markdown_links(path: Path) -> list[str]:
    links = []
    for target in re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        target = target.strip().split(maxsplit=1)[0].strip("<>")
        if re.match(r"(?:https?://|mailto:|#)", target):
            continue
        links.append(target.split("#", 1)[0])
    return [link for link in links if link]


class PublicDocumentationTests(unittest.TestCase):
    def test_root_entry_links_and_instruction_imports_resolve(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        local_links = [
            target
            for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
            if not re.match(r"(?:https?://|mailto:|#)", target)
        ]
        missing = [target for target in local_links if not (ROOT / target).exists()]
        imports = re.findall(r"^@([^\s]+)$", (ROOT / "AGENTS.md").read_text(encoding="utf-8"), re.MULTILINE)
        missing.extend(target for target in imports if not (ROOT / target).exists())
        self.assertEqual([], missing)

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

    def test_readme_has_exact_codex_entry_path(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Codex Game Studios", text)
        self.assertIn("49 agents", text)
        self.assertIn("73 skills", text)
        expected = (
            "1. Clone or use this repository as a template.\n"
            "2. Open the project in Codex and trust the repository configuration and hooks after review.\n"
            "3. Invoke `$start`.\n"
            "4. Choose Godot, Unity, or Unreal when `$setup-engine` runs."
        )
        self.assertIn(expected, text)
        for required in ("3 Sol", "44 Terra", "2 Luna", "phase-gated", "engine pack"):
            self.assertIn(required, text)

    def test_runtime_public_surface_is_codex_only(self):
        failures = []
        for path in PUBLIC:
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN:
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
