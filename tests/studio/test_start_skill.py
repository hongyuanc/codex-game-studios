from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / ".agents/skills/start/SKILL.md"


class StartSkillTests(unittest.TestCase):
    def test_start_is_native_and_detects_unconfigured_fresh_projects(self):
        text = START.read_text(encoding="utf-8")
        self.assertEqual([], validate_skill(START))
        self.assertIn(".codex/studio.toml", text)
        self.assertIn('engine = "unconfigured"', text)
        self.assertIn("No concept, source, prototype, design, or production artifacts", text)
        self.assertIn("route to `$brainstorm`", text)

    def test_start_questions_fit_native_schema(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("Ask one decision per turn", text)
        self.assertIn("2-3 mutually exclusive options", text)
        self.assertIn("New or exploratory", text)
        self.assertIn("Defined or existing", text)
        self.assertNotIn("these exact options", text)
        self.assertNotIn("- `D) Existing work`", text)


if __name__ == "__main__":
    unittest.main()
