from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "docs/WORKFLOW-GUIDE.md",
    *sorted((ROOT / "docs/examples").glob("*.md")),
    *sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.md")),
    ROOT / ".github/PULL_REQUEST_TEMPLATE.md",
    ROOT / ".github/CODEOWNERS",
]
FORBIDDEN = (
    "Claude Code",
    "AskUserQuestion",
    "Task tool",
    "subagent_type",
    ".claude/",
    ".Codex/",
)


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
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in FORBIDDEN:
                if token in text:
                    failures.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], failures)

    def test_public_skill_invocations_use_dollar_syntax(self):
        names = {
            path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        slash = re.compile(r"(?<![A-Za-z0-9_.-])/((?:" + "|".join(sorted(map(re.escape, names))) + r"))\b")
        failures = []
        for path in PUBLIC:
            for match in slash.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                failures.append(f"{path.relative_to(ROOT)}: /{match.group(1)}")
        self.assertEqual([], failures)

    def test_upgrade_guide_is_historical_only(self):
        text = (ROOT / "UPGRADING.md").read_text(encoding="utf-8")
        self.assertIn("source system", text)
        self.assertIn("Codex-only", text)
        self.assertNotIn("runtime compatibility", text.lower())


if __name__ == "__main__":
    unittest.main()
