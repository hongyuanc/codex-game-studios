"""Contract tests for plugin and repository marketplace manifests."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"


def assert_plugin_native_descriptions(testcase: unittest.TestCase, data: dict) -> None:
    """Assert the public description fields present the plugin-native product."""

    metadata = " ".join(
        (
            data["description"],
            data["interface"]["shortDescription"],
            data["interface"]["longDescription"],
        )
    )
    testcase.assertIn("73", metadata)
    testcase.assertIn("bundled skills", metadata)
    testcase.assertIn("$codex-game-studios:start", metadata)
    testcase.assertIn("bounded", metadata)
    testcase.assertIn("project", metadata)
    descriptions = {
        "description": data["description"],
        "shortDescription": data["interface"]["shortDescription"],
        "longDescription": data["interface"]["longDescription"],
    }
    for field, value in descriptions.items():
        testcase.assertNotRegex(
            value.lower(),
            r"\b(?:manager|manage|install|update|verify|repair|remove)\b",
            msg=f"{field} must not advertise the legacy lifecycle as fresh",
        )


class PluginManifestTests(unittest.TestCase):
    """Verify the public plugin metadata contract."""

    def test_plugin_manifest_exposes_complete_native_skill_catalog(self):
        # Arrange
        manifest = PLUGIN / ".codex-plugin/plugin.json"

        # Act
        data = json.loads(manifest.read_text(encoding="utf-8"))
        bundled = {
            path.parent.name
            for path in (PLUGIN / data["skills"]).resolve().glob("*/SKILL.md")
        }
        canonical = {
            path.parent.name
            for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }

        # Assert
        self.assertEqual("codex-game-studios", data["name"])
        self.assertEqual("2.0.0", data["version"])
        self.assertEqual("./assets/studio/.agents/skills/", data["skills"])
        self.assertEqual(canonical, bundled)
        self.assertEqual(73, len(bundled))
        self.assertFalse((PLUGIN / "skills/codex-game-studios/SKILL.md").exists())
        self.assertNotIn("hooks", data)

    def test_plugin_manifest_publishes_approved_metadata(self):
        # Arrange
        manifest = PLUGIN / ".codex-plugin/plugin.json"
        # Act
        data = json.loads(manifest.read_text(encoding="utf-8"))

        # Assert
        assert_plugin_native_descriptions(self, data)
        self.assertEqual({"name": "hongyuanc"}, data["author"])
        self.assertEqual("https://github.com/hongyuanc/codex-game-studios", data["repository"])
        self.assertEqual("https://github.com/hongyuanc/codex-game-studios", data["homepage"])
        self.assertEqual("MIT", data["license"])
        self.assertEqual(["codex", "game-development", "godot", "unity", "unreal"], data["keywords"])
        self.assertEqual("Codex Game Studios", data["interface"]["displayName"])
        self.assertEqual("hongyuanc", data["interface"]["developerName"])
        self.assertEqual("Developer Tools", data["interface"]["category"])
        self.assertEqual(["Read", "Write"], data["interface"]["capabilities"])
        self.assertEqual(
            "https://github.com/hongyuanc/codex-game-studios",
            data["interface"]["websiteURL"],
        )
        self.assertEqual(
            ["Use $codex-game-studios:start to begin in this game repository."],
            data["interface"]["defaultPrompt"],
        )

    def test_plugin_manifest_rejects_manager_first_description_field_mutant(self):
        # Arrange
        manifest = PLUGIN / ".codex-plugin/plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["interface"]["shortDescription"] = "Manage a complete repository studio."

        # Act / Assert
        with self.assertRaises(AssertionError):
            assert_plugin_native_descriptions(self, data)

    def test_marketplace_points_to_local_plugin(self):
        # Arrange
        marketplace = ROOT / ".agents/plugins/marketplace.json"

        # Act
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        entry = data["plugins"][0]

        # Assert
        self.assertEqual(1, data["schemaVersion"])
        self.assertEqual("codex-game-studios", data["name"])
        self.assertEqual("hongyuanc", data["owner"]["name"])
        self.assertEqual(1, len(data["plugins"]))
        self.assertEqual("codex-game-studios", entry["name"])
        self.assertEqual("./plugins/codex-game-studios", entry["source"])


if __name__ == "__main__":
    unittest.main()
