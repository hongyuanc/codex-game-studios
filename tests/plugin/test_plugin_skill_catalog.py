from pathlib import Path
import re
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"


class PluginSkillCatalogTests(unittest.TestCase):
    def test_catalog_has_source_parity_and_valid_skills(self):
        source = ROOT / ".agents/skills"
        bundled = PLUGIN / "assets/studio/.agents/skills"
        names = {path.parent.name for path in source.glob("*/SKILL.md")}
        self.assertEqual(73, len(names))
        for name in sorted(names):
            self.assertEqual(
                (source / name / "SKILL.md").read_bytes(),
                (bundled / name / "SKILL.md").read_bytes(),
            )
            self.assertEqual([], validate_skill(bundled / name / "SKILL.md"))

    def test_skills_do_not_probe_repo_local_skill_installation(self):
        pattern = re.compile(r"\.agents/skills/[a-z0-9-]+/SKILL\.md")
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            self.assertIsNone(pattern.search(path.read_text()), path)

    def test_skills_resolve_static_resources_from_the_plugin_bundle(self):
        resource = re.compile(
            r"(?P<prefix>(?:\.\./)*)"
            r"(?P<path>\.codex/docs/[A-Za-z0-9_./-]+|"
            r"docs/engine-reference/[A-Za-z0-9_./\[\]-]+|"
            r"Codex Studio Testing Framework/[A-Za-z0-9_./*\[\]-]+)"
        )
        for skill in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            for match in resource.finditer(skill.read_text(encoding="utf-8")):
                if match.group("path") == ".codex/docs/technical-preferences.md":
                    expected = ""
                else:
                    expected = "../../../"
                self.assertEqual(expected, match.group("prefix"), (skill, match.group()))


if __name__ == "__main__":
    unittest.main()
