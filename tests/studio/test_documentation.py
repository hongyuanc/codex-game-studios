from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CODEX_DOCS = ROOT / ".codex/docs"
REQUIRED = {
    "agent-coordination-map.md",
    "agent-roster.md",
    "coding-standards.md",
    "context-management.md",
    "coordination-rules.md",
    "director-gates.md",
    "directory-structure.md",
    "hooks-reference.md",
    "quick-start.md",
    "review-workflow.md",
    "rules-reference.md",
    "setup-requirements.md",
    "skills-reference.md",
    "technical-preferences.md",
    "workflow-catalog.yaml",
}
# enforcement-literal-start
FORBIDDEN_RUNTIME_TEXT = (
    ".claude/",
    "CLAUDE.md",
    "CLAUDE.local.md",
    "Claude",
    "Claude Code",
    "claude-",
    "CLAUDE_CODE",
    "@anthropic-ai",
    "AskUserQuestion",
    "Task tool",
    "Task calls",
    "Task subagent",
    "`Task`",
    "Read tool",
    "Write tool",
    "Edit tool",
    "Glob tool",
    "Grep tool",
    "Opus",
    "Sonnet",
    "Haiku",
    "PreToolUse (Bash)",
    "Write/apply_patch",
)
# enforcement-literal-end


def markdown_headings(path: Path) -> list[str]:
    return [
        line.rstrip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"^#{1,6} ", line)
    ]


class DocumentationTests(unittest.TestCase):
    def test_required_codex_docs_exist(self):
        missing = sorted(name for name in REQUIRED if not (CODEX_DOCS / name).is_file())
        self.assertEqual([], missing)

    def test_template_tree_has_source_parity(self):
        destination = {
            path.relative_to(CODEX_DOCS / "templates").as_posix()
            for path in (CODEX_DOCS / "templates").rglob("*")
            if path.is_file()
        }
        manifest = (ROOT / "production/migration/claude-to-codex-coverage.yaml").read_text(encoding="utf-8")  # enforcement-literal
        covered = set(re.findall(r"^    destination: \.codex/docs/templates/(.+)$", manifest, re.MULTILINE))
        self.assertEqual(covered, destination)
        self.assertEqual(40, len(destination))

    def test_template_headings_are_preserved(self):
        for destination in sorted((CODEX_DOCS / "templates").rglob("*.md")):
            with self.subTest(path=destination.relative_to(ROOT)):
                self.assertTrue(markdown_headings(destination))
                self.assertGreaterEqual(len(destination.read_text(encoding="utf-8")), 200)

    def test_required_docs_are_substantive(self):
        for name in sorted(REQUIRED):
            destination = CODEX_DOCS / name
            with self.subTest(path=name):
                self.assertGreaterEqual(len(destination.read_text(encoding="utf-8")), 200)

    def test_runtime_docs_have_no_claude_dependencies(self):
        for path in CODEX_DOCS.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                for forbidden in FORBIDDEN_RUNTIME_TEXT:
                    self.assertNotIn(forbidden, text)

    def test_runtime_paths_are_lowercase(self):
        for path in CODEX_DOCS.rglob("*"):
            if path.is_file():
                relative = path.relative_to(CODEX_DOCS).as_posix()
                with self.subTest(path=relative):
                    self.assertEqual(relative, relative.lower())

    def test_codex_operating_contract_is_documented(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in CODEX_DOCS.rglob("*")
            if path.is_file()
        )
        self.assertIn("phase-gated", combined)
        self.assertIn("Sol", combined)
        self.assertIn("Terra", combined)
        self.assertIn("Luna", combined)
        self.assertIn("gpt-5.6-terra", combined)
        self.assertIn("gpt-5.6-luna", combined)
        self.assertIn("$setup-engine", combined)
        self.assertIn("apply_patch", combined)
        self.assertIn("exec_command", combined)
        self.assertIn("activates exactly one", combined)
        self.assertIn("without asking before every file edit", combined)

    def test_gate_coverage_table_matches_runtime_and_framework_modes(self):
        table = (CODEX_DOCS / "director-gates.md").read_text(encoding="utf-8")

        def gate_set(stage: str, column: int) -> set[str]:
            row = next(
                line for line in table.splitlines()
                if line.startswith(f"| **{stage}** |")
            )
            cell = row.split("|")[column]
            return {
                re.match(r"[A-Z]+-[A-Z0-9-]+", item.strip()).group(0)
                for item in cell.split(",")
            }

        self.assertEqual(
            {"TD-SYSTEM-BOUNDARY", "CD-SYSTEMS", "PR-SCOPE"},
            gate_set("Systems Design", 2),
        )
        self.assertEqual(
            {"CD-GDD-ALIGN", "ND-CONSISTENCY", "AD-VISUAL"},
            gate_set("Systems Design", 3),
        )
        self.assertEqual(
            {"TD-ARCHITECTURE", "TD-ADR"},
            gate_set("Technical Setup", 2),
        )
        self.assertEqual(
            {"LP-FEASIBILITY", "AD-ART-BIBLE", "TD-ENGINE-RISK"},
            gate_set("Technical Setup", 3),
        )

        runtime = {
            name: (ROOT / f".agents/skills/{name}/SKILL.md").read_text(encoding="utf-8")
            for name in ("design-system", "create-architecture", "art-bible", "architecture-decision")
        }
        framework = {
            name: (ROOT / f"Codex Studio Testing Framework/skills/authoring/{name}.md").read_text(encoding="utf-8")
            for name in ("design-system", "create-architecture", "art-bible")
        }
        self.assertIn("CD-GDD-ALIGN is optional and runs only in full mode", runtime["design-system"])
        self.assertIn("CD-GDD-ALIGN is optional: run it only in `full`", framework["design-system"])
        self.assertIn("TD-ARCHITECTURE is mandatory in full, lean, and solo modes", runtime["create-architecture"])
        self.assertIn("TD-ARCHITECTURE is mandatory in `full`, `phase-gated`, and `solo`", framework["create-architecture"])
        self.assertIn("LP-FEASIBILITY is optional and runs only in full mode", runtime["create-architecture"])
        self.assertIn("LP-FEASIBILITY is optional: run it only in `full`", framework["create-architecture"])
        self.assertIn("AD-ART-BIBLE is optional and runs only in full mode", runtime["art-bible"])
        self.assertIn("AD-ART-BIBLE delegates to `art-director` and is optional", framework["art-bible"])
        self.assertIn("TD-ADR is required in full, lean, and solo modes", runtime["architecture-decision"])

    def test_skill_references_use_codex_invocation_syntax(self):
        names = {
            path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        slash_skill = re.compile(
            r"(?<![A-Za-z0-9_.-])/("
            + "|".join(map(re.escape, sorted(names)))
            + r")\b"
        )
        issues = []
        for path in CODEX_DOCS.rglob("*"):
            if path.is_file():
                for match in slash_skill.finditer(path.read_text(encoding="utf-8")):
                    issues.append(f"{path.relative_to(ROOT)}: /{match.group(1)}")
        self.assertEqual([], issues)

    def test_codex_doc_references_resolve(self):
        reference = re.compile(r"`(\.codex/docs/[a-z0-9_./-]+)`")
        missing = []
        for path in CODEX_DOCS.rglob("*"):
            if not path.is_file():
                continue
            for relative in reference.findall(path.read_text(encoding="utf-8")):
                if not (ROOT / relative).exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {relative}")
        self.assertEqual([], missing)

    def test_interactive_question_contract_is_current(self):
        protocols = (
            CODEX_DOCS / "templates/collaborative-protocols/design-agent-protocol.md",
            CODEX_DOCS / "templates/collaborative-protocols/leadership-agent-protocol.md",
        )
        for path in protocols:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("up to 4", text)
                self.assertNotIn("2-4 options", text)
                self.assertNotIn("2–4 options", text)
                self.assertNotIn("markdown previews", text)
                self.assertIn("1-3 questions", text)
                self.assertIn("2-3 mutually exclusive options", text)
                self.assertIn("one question at a time", text)
                self.assertIn("genuinely independent", text)

    def test_public_facing_codex_docs_use_python_hook_runtime(self):
        setup = (CODEX_DOCS / "setup-requirements.md").read_text(encoding="utf-8")
        hooks = (CODEX_DOCS / "hooks-reference.md").read_text(encoding="utf-8")
        self.assertIn("Python 3", setup)
        self.assertIn("10 hook actions", setup)
        self.assertNotIn("jq", setup.lower())
        self.assertNotIn("Bash", setup)
        self.assertIn("hook_runner.py", hooks)
        self.assertNotIn(".sh", hooks)

    def test_context_and_skill_test_templates_use_phase_gates(self):
        context = (CODEX_DOCS / "context-management.md").read_text(encoding="utf-8")
        spec = (CODEX_DOCS / "templates/skill-test-spec.md").read_text(encoding="utf-8")
        self.assertNotIn("/clear", context)
        self.assertIn("phase-gated", spec)
        self.assertNotIn("May I write", spec)
        self.assertNotIn("/[skill-name]", spec)
        self.assertIn("$[skill-name]", spec)
        self.assertNotIn("status line script", context.lower())
        self.assertNotIn("status line displays", context.lower())

    def test_runtime_docs_have_one_persistent_review_mode_authority(self):
        failures = []
        for path in CODEX_DOCS.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for legacy in (
                "production/review-mode.txt",
                "production/session-state/review-mode.txt",
            ):
                if legacy in text:
                    failures.append(f"{path.relative_to(ROOT)}: {legacy}")
        self.assertEqual([], failures)

    def test_implementation_protocol_uses_current_question_limits(self):
        path = CODEX_DOCS / "templates/collaborative-protocols/implementation-agent-protocol.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("one decision at a time", text)
        self.assertIn("1-3 questions", text)
        self.assertIn("2-3 mutually exclusive options", text)
        for forbidden in ("up to 4", "Batch up to 4", "four questions", "multi-select"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
