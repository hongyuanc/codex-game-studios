from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_agent


ROOT = Path(__file__).resolve().parents[2]


class AgentValidationTests(unittest.TestCase):
    def test_invalid_fixture_reports_required_fields(self):
        issues = validate_agent(ROOT / "tests/studio/fixtures/invalid-agent.toml")
        messages = {issue.message for issue in issues}
        self.assertIn("missing required field: description", messages)
        self.assertIn("missing required field: developer_instructions", messages)

    def test_all_profiles_have_valid_contracts(self):
        profiles = sorted((ROOT / ".codex/agents").glob("*.toml"))
        profiles += sorted((ROOT / ".codex/agent-packs").glob("*/*.toml"))
        self.assertEqual(49, len(profiles))
        issues = [issue for path in profiles for issue in validate_agent(path)]
        self.assertEqual([], issues)

    def test_project_configuration_is_bounded(self):
        import tomllib
        config = tomllib.loads((ROOT / ".codex/config.toml").read_text(encoding="utf-8"))
        self.assertEqual(1, config["agents"]["max_depth"])
        self.assertEqual(6, config["agents"]["max_threads"])

    def test_studio_starts_unconfigured(self):
        import tomllib
        studio = tomllib.loads((ROOT / ".codex/studio.toml").read_text(encoding="utf-8"))
        self.assertEqual("unconfigured", studio["engine"])
        self.assertEqual("none", studio["active_engine_pack"])
        self.assertEqual("phase-gated", studio["review_mode"])
        self.assertEqual("balanced", studio["model_policy"])

    def test_balanced_model_distribution(self):
        import tomllib
        profiles = sorted((ROOT / ".codex/agents").glob("*.toml"))
        profiles += sorted((ROOT / ".codex/agent-packs").glob("*/*.toml"))
        models = [tomllib.loads(path.read_text(encoding="utf-8"))["model"] for path in profiles]
        self.assertEqual(3, models.count("gpt-5.6"))
        self.assertEqual(44, models.count("gpt-5.6-terra"))
        self.assertEqual(2, models.count("gpt-5.6-luna"))

    def test_only_selected_roles_use_sol_and_luna(self):
        import tomllib
        profiles = sorted((ROOT / ".codex/agents").glob("*.toml"))
        profiles += sorted((ROOT / ".codex/agent-packs").glob("*/*.toml"))
        by_model = {}
        for path in profiles:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            by_model.setdefault(data["model"], set()).add(data["name"])
        self.assertEqual({"creative-director", "technical-director", "producer"}, by_model["gpt-5.6"])
        self.assertEqual({"community-manager", "qa-tester"}, by_model["gpt-5.6-luna"])

    def test_unconfigured_template_has_core_and_packed_roster(self):
        import tomllib

        core = sorted((ROOT / ".codex/agents").glob("*.toml"))
        packed = sorted((ROOT / ".codex/agent-packs").glob("*/*.toml"))
        self.assertEqual(34, len(core))
        self.assertEqual(15, len(packed))
        self.assertEqual(
            {"godot": 5, "unity": 5, "unreal": 5},
            {
                engine: len(list((ROOT / ".codex/agent-packs" / engine).glob("*.toml")))
                for engine in ("godot", "unity", "unreal")
            },
        )
        devops = tomllib.loads(
            (ROOT / ".codex/agents/devops-engineer.toml").read_text(encoding="utf-8")
        )
        self.assertEqual("gpt-5.6-terra", devops["model"])
        self.assertEqual("high", devops["model_reasoning_effort"])
