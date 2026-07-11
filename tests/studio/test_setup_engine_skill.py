from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]


class SetupEngineSkillTests(unittest.TestCase):
    def test_setup_engine_is_native_transactional_and_approval_gated(self):
        path = ROOT / ".agents/skills/setup-engine/SKILL.md"
        self.assertEqual([], validate_skill(path))
        text = path.read_text(encoding="utf-8")
        for required in (
            "--dry-run",
            "complete activation plan",
            "explicit approval",
            "--apply",
            "rollback evidence",
            "post-apply validation",
            "one decision per turn",
            "five active profiles",
        ):
            self.assertIn(required, text)
        self.assertNotIn("AskUserQuestion", text)
        self.assertNotIn(".Codex/", text)

    def test_setup_engine_uses_supported_engines_and_selected_pack_preferences(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Godot", text)
        self.assertIn("Unity", text)
        self.assertIn("Unreal", text)
        self.assertIn("request_user_input", text)
        preferences = (ROOT / ".codex/docs/technical-preferences.md").read_text(encoding="utf-8")
        self.assertIn("Active Engine Pack", preferences)
        self.assertIn("managed by `$setup-engine`", preferences)
