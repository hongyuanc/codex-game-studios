from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "src/gameplay/AGENTS.md",
    "src/core/AGENTS.md",
    "src/ai/AGENTS.md",
    "src/networking/AGENTS.md",
    "src/ui/AGENTS.md",
    "assets/shaders/AGENTS.md",
    "assets/data/AGENTS.md",
    "design/gdd/AGENTS.md",
    "design/narrative/AGENTS.md",
    "tests/AGENTS.md",
    "prototypes/AGENTS.md",
}


class InstructionCoverageTests(unittest.TestCase):
    def test_all_instruction_boundaries_exist(self):
        missing = sorted(path for path in EXPECTED if not (ROOT / path).is_file())
        self.assertEqual([], missing)

    def test_nested_instructions_preserve_material_rule_contracts(self):
        required_phrases = {
            "src/gameplay/AGENTS.md": ("data files", "delta time", "events or signals", "dependency injection"),
            "src/core/AGENTS.md": ("ZERO allocations", "thread-safe", "engine-reference", "graceful degradation"),
            "src/ai/AGENTS.md": ("2ms", "visualization", "telegraph", "network"),
            "src/networking/AGENTS.md": ("authoritative", "versioned", "rollback", "packet sizes"),
            "src/ui/AGENTS.md": ("localization", "gamepad", "colorblind", "game thread"),
            "assets/shaders/AGENTS.md": ("texture samples", "dynamic branching", "fallback", "variant"),
            "assets/data/AGENTS.md": ("valid JSON", "lowercase", "camelCase", "defaults"),
            "design/gdd/AGENTS.md": ("Player Fantasy", "Edge Cases", "Tuning Knobs", "user approval"),
            "design/narrative/AGENTS.md": ("canon level", "voice profile", "localization-ready", "120 characters"),
            "tests/AGENTS.md": ("arrange", "act", "assert", "regression test"),
            "prototypes/AGENTS.md": ("README.md", "hypothesis", "must not be deployed", "rewritten"),
        }
        for relative, phrases in required_phrases.items():
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file(), f"missing nested instructions: {relative}")
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("Claude", text)
                self.assertIn("## Applies To", text)
                self.assertIn("## Required Practices", text)
                self.assertIn("## Forbidden Practices", text)
                self.assertIn("## Verification", text)
                for phrase in phrases:
                    self.assertIn(phrase, text)

    def test_shader_instructions_use_the_actual_asset_boundary(self):
        self.assertTrue((ROOT / "assets/shaders/AGENTS.md").is_file())
        self.assertFalse((ROOT / "src/shaders/AGENTS.md").exists())
        text = (ROOT / "assets/shaders/AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("assets/shaders/", text)


if __name__ == "__main__":
    unittest.main()
