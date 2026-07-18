"""Contract tests for plugin documentation and licensing."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"


def markdown_section(text: str, heading: str) -> str:
    """Return one Markdown heading body through the next peer/parent heading."""

    marker = re.search(rf"(?m)^(?P<level>#+) {re.escape(heading)}\s*$", text)
    if marker is None:
        raise AssertionError(f"missing Markdown section: {heading}")
    level = len(marker.group("level"))
    following = re.search(rf"(?m)^#{{1,{level}}} ", text[marker.end() :])
    end = marker.end() + following.start() if following else len(text)
    return text[marker.end() : end]


class PluginDocumentationTests(unittest.TestCase):
    """Verify user-facing plugin and skill contracts."""

    def test_plugin_notices_keep_modification_copyright_only_in_attribution(self):
        # Arrange
        license_path = PLUGIN / "LICENSE"
        attribution_path = PLUGIN / "ATTRIBUTION.md"
        readme_path = PLUGIN / "README.md"

        # Act
        license_text = license_path.read_text(encoding="utf-8")
        attribution = attribution_path.read_text(encoding="utf-8")
        readme = readme_path.read_text(encoding="utf-8")
        combined = "\n".join((license_text, attribution, readme))

        # Assert
        self.assertIn("Copyright (c) 2026 Donchitos", combined)
        self.assertIn("https://github.com/Donchitos/Claude-Code-Game-Studios", combined)  # enforcement-literal
        self.assertIn("Copyright (c) 2026 hongyuanc", attribution)
        self.assertNotIn("Copyright (c) 2026 hongyuanc", readme)
        self.assertNotIn("Copyright (c) 2026 hongyuanc", license_text)
        self.assertIn("independent Codex-native adaptation", combined)

    def test_plugin_license_is_exact_copy_of_upstream_mit_text(self):
        # Arrange
        root_license = ROOT / "LICENSE"
        plugin_license = PLUGIN / "LICENSE"

        # Act
        expected = root_license.read_text(encoding="utf-8")
        actual = plugin_license.read_text(encoding="utf-8")

        # Assert
        self.assertEqual(expected, actual)

    def test_attribution_describes_modifications_and_disclaims_endorsement(self):
        # Arrange
        attribution_path = PLUGIN / "ATTRIBUTION.md"

        # Act
        attribution = attribution_path.read_text(encoding="utf-8")

        # Assert
        self.assertIn("Copyright (c) 2026 hongyuanc", attribution)
        self.assertIn("Codex-native", attribution)
        self.assertIn("plugin", attribution)
        self.assertIn("skills", attribution)
        self.assertIn("bundled", attribution)
        self.assertIn("initialization", attribution)
        self.assertIn("migration", attribution)
        self.assertIn("not endorsed by Donchitos, Anthropic, or OpenAI", attribution)  # enforcement-literal

    def test_readme_documents_plugin_native_start_and_separate_legacy_operations(self):
        # Arrange
        readme_path = PLUGIN / "README.md"

        # Act
        readme = readme_path.read_text(encoding="utf-8")
        app = markdown_section(readme, "Codex app")
        cli = markdown_section(readme, "Codex CLI")
        fresh, legacy = readme.split("## Legacy 1.0.0 lifecycle support", maxsplit=1)

        # Assert
        for section in (app, cli):
            self.assertIn("repository marketplace", section)
            self.assertIn("Start a new Codex task", section)
            self.assertIn("in-Codex", section)
            self.assertIn("$codex-game-studios:start", section)
        self.assertIn("Clone", app)
        self.assertIn("open", app.lower())
        self.assertIn("Plugins", app)
        self.assertNotIn("codex plugin", app)
        self.assertIn("codex plugin marketplace add", cli)
        self.assertIn("codex plugin add", cli)
        self.assertIn("all 73 studio skills", fresh.lower())
        self.assertIn("zero writes to the game repository", fresh)
        self.assertIn("small project-specific state", fresh)
        self.assertIn("at most ten", fresh)
        self.assertIn("never", fresh)
        self.assertIn("`.agents/skills/`", fresh)
        self.assertNotIn("$codex-game-studios install", readme)
        self.assertNotIn("$codex-game-studios update", readme)
        for operation in (
            "verify legacy installation",
            "repair legacy installation",
            "migrate to plugin-native",
            "uninstall legacy installation",
        ):
            self.assertNotIn(operation, fresh)
            self.assertIn(operation, legacy)
        self.assertIn("Git repository", readme)

if __name__ == "__main__":
    unittest.main()
