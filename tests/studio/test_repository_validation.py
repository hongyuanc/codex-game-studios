from pathlib import Path
import tempfile
import unittest

from tools.codex_studio.validate import (
    validate_repository,
    validate_repository_counts,
    validate_runtime_references,
    validate_skill,
)


ROOT = Path(__file__).resolve().parents[2]


class RepositoryValidationTests(unittest.TestCase):
    def test_skill_rejects_legacy_agent_and_turn_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(
                "---\nname: bad\ndescription: bad\nagent: old\nmaxTurns: 4\n---\n",
                encoding="utf-8",
            )
            messages = {issue.message for issue in validate_skill(path)}
        self.assertIn("contains Claude agent metadata", messages)
        self.assertIn("contains Claude turn-limit metadata", messages)

    def test_repository_counts_are_exact(self):
        self.assertEqual([], validate_repository_counts(ROOT))

    def test_pre_cleanup_gate_accepts_covered_legacy_sources(self):
        legacy = [path for path in (ROOT / ".claude").rglob("*") if path.is_file()]
        legacy += list(ROOT.rglob("CLAUDE.md"))
        if not legacy:
            self.skipTest("pre-cleanup evidence was recorded before legacy deletion")
        self.assertEqual([], validate_runtime_references(ROOT, "pre-cleanup"))
        self.assertEqual([], validate_repository(ROOT, "pre-cleanup"))

    def test_final_gate_rejects_any_remaining_legacy_sources(self):
        issues = validate_runtime_references(ROOT, "final")
        legacy = [path for path in (ROOT / ".claude").rglob("*") if path.is_file()]
        legacy += list(ROOT.rglob("CLAUDE.md"))
        if legacy:
            self.assertTrue(any("legacy source remains" in issue.message for issue in issues))
        else:
            self.assertEqual([], issues)

    def test_unknown_phase_is_rejected(self):
        issues = validate_repository(ROOT, "surprise")
        self.assertTrue(any("unsupported validation phase" in issue.message for issue in issues))


if __name__ == "__main__":
    unittest.main()
