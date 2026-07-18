"""Contract tests for plugin and repository marketplace manifests."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"


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
        metadata = " ".join(
            (
                data["description"],
                data["interface"]["shortDescription"],
                data["interface"]["longDescription"],
            )
        )

        # Assert
        self.assertIn("73", metadata)
        self.assertIn("bundled skills", metadata)
        self.assertIn("$codex-game-studios:start", metadata)
        self.assertIn("bounded", metadata)
        self.assertIn("project", metadata)
        for manager_first in ("install and manage", "install, update", "remove"):
            self.assertNotIn(manager_first, metadata.lower())
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
