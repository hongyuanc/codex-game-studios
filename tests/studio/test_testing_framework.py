from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT / "Codex Studio Testing Framework"
OLD = ROOT / "CCGS Skill Testing Framework"


def catalog_names(text: str, section: str) -> set[str]:
    block = text.split(f"{section}:\n", 1)[1]
    if section == "skills":
        block = block.split("\nagents:\n", 1)[0]
    return set(re.findall(r"^  - name: ([a-z0-9-]+)$", block, re.MULTILINE))


class TestingFrameworkTests(unittest.TestCase):
    def test_catalog_and_native_guidance_exist(self):
        self.assertTrue((NEW / "catalog.yaml").is_file())
        self.assertTrue((NEW / "README.md").is_file())
        self.assertTrue((NEW / "AGENTS.md").is_file())

    def test_migrated_tree_has_source_parity_before_cleanup(self):
        if not OLD.exists() or not any(path.is_file() for path in OLD.rglob("*")):
            self.skipTest("legacy tree already removed after recorded parity gate")
        for directory in ("agents", "skills", "templates"):
            old_files = {
                path.relative_to(OLD / directory)
                for path in (OLD / directory).rglob("*")
                if path.is_file()
            }
            new_files = {
                path.relative_to(NEW / directory)
                for path in (NEW / directory).rglob("*")
                if path.is_file()
            }
            expected_additions = (
                {Path("utility/vertical-slice.md")} if directory == "skills" else set()
            )
            self.assertEqual(old_files | expected_additions, new_files)

    def test_catalog_covers_runtime_inventory_exactly(self):
        text = (NEW / "catalog.yaml").read_text(encoding="utf-8")
        runtime_skills = {
            path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        runtime_agents = set()
        for path in [
            *sorted((ROOT / ".codex/agents").glob("*.toml")),
            *sorted((ROOT / ".codex/agent-packs").glob("*/*.toml")),
        ]:
            match = re.search(r'^name = "([a-z0-9-]+)"$', path.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertIsNotNone(match, path)
            runtime_agents.add(match.group(1))
        self.assertEqual(runtime_skills, catalog_names(text, "skills"))
        self.assertEqual(runtime_agents, catalog_names(text, "agents"))
        self.assertEqual(73, len(runtime_skills))
        self.assertEqual(49, len(runtime_agents))

    def test_framework_is_codex_native(self):
        forbidden = (
            "Claude Code", "AskUserQuestion", "Task tool", "subagent_type",
            "model: opus", "model: sonnet", "model: haiku", ".claude/",
        )
        failures = []
        for path in NEW.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in forbidden:
                    if token in text:
                        failures.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
