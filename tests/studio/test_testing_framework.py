from pathlib import Path
import json
import re
import tomllib
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

    def test_migrated_tree_has_durable_source_parity(self):
        evidence = json.loads(
            (ROOT / "production/migration/testing-framework-parity.json").read_text(encoding="utf-8")
        )
        sources = {entry["source"] for entry in evidence["entries"]}
        for directory in ("agents", "skills", "templates"):
            old_files = {
                Path(source).relative_to(directory)
                for source in sources
                if source.startswith(f"{directory}/")
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
            "Task call", "Task invocation", "model: opus", "model: sonnet",
            "model: haiku", "claude-opus", "claude-sonnet", "claude-haiku",
            "Opus model", "Sonnet model", "Haiku model", "Opus", "Sonnet",
            "Haiku", "CLAUDE.md", "parallel Task protocol", ".claude/",
            "allowed-tools", "argument-hint", "user-invocable",
            "May I apply the proposed changeset", "May I ",
        )
        failures = []
        for path in NEW.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    if token in text:
                        failures.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual([], failures)

    def test_all_agent_specs_match_their_runtime_toml_contract(self):
        runtime = {}
        for path in [
            *sorted((ROOT / ".codex/agents").glob("*.toml")),
            *sorted((ROOT / ".codex/agent-packs").glob("*/*.toml")),
        ]:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            runtime[data["name"]] = (path.relative_to(ROOT), data)

        specs = {path.stem: path for path in (NEW / "agents").rglob("*.md")}
        self.assertEqual(set(runtime), set(specs))
        self.assertEqual(49, len(specs))

        labels = {
            "gpt-5.6": "Sol",
            "gpt-5.6-terra": "Terra",
            "gpt-5.6-luna": "Luna",
        }
        required_keys = {
            "name", "description", "model", "model_reasoning_effort",
            "developer_instructions",
        }
        for name, spec_path in specs.items():
            runtime_path, data = runtime[name]
            text = spec_path.read_text(encoding="utf-8")
            self.assertEqual(required_keys, set(data), runtime_path)
            self.assertIn(f"Runtime profile: `{runtime_path}`", text, spec_path)
            self.assertIn(
                "Required TOML keys: `name`, `description`, `model`, "
                "`model_reasoning_effort`, `developer_instructions`",
                text,
                spec_path,
            )
            self.assertIn(
                f"Model route: **{labels[data['model']]}** (`{data['model']}`)",
                text,
                spec_path,
            )
            self.assertNotRegex(text, r"\.codex/(?:agents|agent-packs)/[^`\s]+\.md")
            self.assertNotRegex(text, r"(?i)Verified.*frontmatter|runtime capabilities.*list")

    def test_all_skill_specs_match_runtime_discovery_and_interaction_contracts(self):
        runtime = {
            path.parent.name: path
            for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
        }
        specs = {path.stem: path for path in (NEW / "skills").rglob("*.md")}
        self.assertEqual(set(runtime), set(specs))
        self.assertEqual(73, len(specs))

        for name, spec_path in specs.items():
            skill_text = runtime[name].read_text(encoding="utf-8")
            frontmatter = skill_text.split("---", 2)[1]
            runtime_name = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
            description = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
            self.assertIsNotNone(runtime_name, runtime[name])
            self.assertIsNotNone(description, runtime[name])

            text = spec_path.read_text(encoding="utf-8")
            self.assertIn(f"# Skill Test Spec: ${name}", text, spec_path)
            self.assertIn(f"Runtime skill: `.agents/skills/{name}/SKILL.md`", text, spec_path)
            self.assertIn(f"Runtime name: `{runtime_name.group(1).strip()}`", text, spec_path)
            self.assertIn(
                f"Runtime trigger description: `{description.group(1).strip()}`",
                text,
                spec_path,
            )
            self.assertIn(f"Native invocation: `${name}`", text, spec_path)
            self.assertIn("1–3 questions", text, spec_path)
            self.assertIn("2–3 options", text, spec_path)
            self.assertIn("one decision per turn", text, spec_path)
            self.assertIn("maximum delegation depth is 1", text, spec_path)
            self.assertIn("parent agent synthesizes", text, spec_path)
            self.assertNotIn("Has required frontmatter fields", text, spec_path)
            for case in range(1, 6):
                self.assertRegex(text, rf"(?m)^### Case {case}:", spec_path)

    def test_framework_core_documents_define_codex_native_protocol(self):
        combined = "\n".join(
            (NEW / name).read_text(encoding="utf-8")
            for name in ("README.md", "AGENTS.md", "quality-rubric.md")
        )
        self.assertIn("Sol (`gpt-5.6`)", combined)
        self.assertIn("Terra (`gpt-5.6-terra`)", combined)
        self.assertIn("Luna (`gpt-5.6-luna`)", combined)
        self.assertIn("maximum delegation depth is 1", combined)
        self.assertIn("parent agent synthesizes", combined)
        self.assertIn("1–3 questions", combined)
        self.assertIn("2–3 options", combined)

    def test_vertical_slice_and_skill_test_have_complete_native_cases(self):
        vertical = (NEW / "skills/utility/vertical-slice.md").read_text(encoding="utf-8")
        self.assertIn("### Case 1: Happy Path", vertical)
        self.assertIn("### Case 2: Blocked Preconditions", vertical)
        self.assertIn("### Case 3: Scope Boundary", vertical)
        self.assertIn("### Case 4: Evidence Failure", vertical)
        self.assertIn("### Case 5: Final Gate", vertical)
        self.assertIn("PROCEED", vertical)
        self.assertIn("PIVOT", vertical)
        self.assertIn("KILL", vertical)

        skill_test = (NEW / "skills/utility/skill-test.md").read_text(encoding="utf-8")
        self.assertIn("exactly 73 runtime skills", skill_test)
        self.assertIn("exactly 49 runtime agents", skill_test)
        self.assertIn("optionally offers one complete approved changeset", skill_test)


if __name__ == "__main__":
    unittest.main()
