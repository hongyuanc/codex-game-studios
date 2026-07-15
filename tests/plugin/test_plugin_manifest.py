"""Contract tests for plugin and repository marketplace manifests."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"


class PluginManifestTests(unittest.TestCase):
    """Verify the public plugin metadata contract."""

    def test_plugin_manifest_exposes_only_native_manager_skill(self):
        # Arrange
        manifest = PLUGIN / ".codex-plugin/plugin.json"

        # Act
        data = json.loads(manifest.read_text(encoding="utf-8"))

        # Assert
        self.assertEqual("codex-game-studios", data["name"])
        self.assertEqual("1.0.0", data["version"])
        self.assertEqual("./skills/", data["skills"])
        self.assertNotIn("hooks", data)

    def test_plugin_manifest_publishes_approved_metadata(self):
        # Arrange
        manifest = PLUGIN / ".codex-plugin/plugin.json"
        expected_interface = {
            "displayName": "Codex Game Studios",
            "shortDescription": "Install a complete Codex-native game studio.",
            "longDescription": (
                "Safely install, update, verify, repair, and remove a coordinated "
                "Codex game-development studio in Git repositories."
            ),
            "developerName": "hongyuanc",
            "category": "Developer Tools",
            "capabilities": ["Read", "Write"],
            "websiteURL": "https://github.com/hongyuanc/codex-game-studios",
            "defaultPrompt": [
                "Use $codex-game-studios install to add the studio to this game repository."
            ],
        }

        # Act
        data = json.loads(manifest.read_text(encoding="utf-8"))

        # Assert
        self.assertEqual(
            "Install and manage a complete Codex-native game-development studio in a repository.",
            data["description"],
        )
        self.assertEqual({"name": "hongyuanc"}, data["author"])
        self.assertEqual("https://github.com/hongyuanc/codex-game-studios", data["repository"])
        self.assertEqual("https://github.com/hongyuanc/codex-game-studios", data["homepage"])
        self.assertEqual("MIT", data["license"])
        self.assertEqual(["codex", "game-development", "godot", "unity", "unreal"], data["keywords"])
        self.assertEqual(expected_interface, data["interface"])

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
