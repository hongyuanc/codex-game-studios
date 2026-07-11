from pathlib import Path
import re
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
        self.assertNotIn("AskUserQuestion", text)  # enforcement-literal
        self.assertNotIn(".Codex/", text)  # enforcement-literal

    def test_setup_engine_uses_supported_engines_and_selected_pack_preferences(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Godot", text)
        self.assertIn("Unity", text)
        self.assertIn("Unreal", text)
        self.assertIn("request_user_input", text)
        preferences = (ROOT / ".codex/docs/technical-preferences.md").read_text(encoding="utf-8")
        self.assertIn("Active Engine Pack", preferences)
        self.assertIn("managed by `$setup-engine`", preferences)

    def test_setup_engine_decisions_are_strictly_sequential_and_not_combined(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        expected = [
            "Engine",
            "Exact engine version",
            "Primary language",
            "Target platform",
            "Primary input",
            "Testing framework",
            "Performance budget",
        ]
        decisions = re.findall(r"^\d+\. \*\*(.+?)\*\*", text, flags=re.MULTILINE)
        self.assertEqual(expected, decisions)
        self.assertIn("Ask exactly one unresolved decision, then stop and wait", text)

    def test_setup_engine_uses_same_exact_values_across_dry_run_approval_and_apply(self):
        text = (ROOT / ".agents/skills/setup-engine/SKILL.md").read_text(encoding="utf-8")
        commands = re.findall(r"python3 -m tools\.codex_studio\.engine_pack[^\n]+", text)
        dry = next(command for command in commands if "--dry-run" in command)
        apply = next(command for command in commands if "--apply" in command)
        for token in ("<engine>", "<exact-version>", "<primary-language>"):
            self.assertIn(token, dry)
            self.assertIn(token, apply)
        self.assertLess(text.index("complete activation plan"), text.index("explicit approval"))
        self.assertLess(text.index("explicit approval"), text.index("--apply"))
        self.assertIn("No project write is allowed before this approval", text)
        self.assertIn("Stop all remaining setup writes", text)
        self.assertIn("Never claim setup succeeded", text)
        self.assertIn("complete approved write scope", text)
