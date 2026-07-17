from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_agent


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / ".codex/docs/plugin-agent-delegation.md"


class AgentValidationTests(unittest.TestCase):
    def test_plugin_agent_delegation_protocol_has_exact_ordered_fallbacks(self):
        # Arrange
        expected_routes = (
            "If the collaboration API exposes the named role, delegate with that role.",
            "Otherwise read `../../../.codex/agents/<role>.toml`",
            "If delegation is unavailable",
        )

        # Act
        text = PROTOCOL.read_text(encoding="utf-8")
        positions = tuple(text.index(route) for route in expected_routes)
        normalized = " ".join(text.split())

        # Assert
        self.assertEqual(tuple(sorted(positions)), positions)
        for token in (
            "../../../.codex/agent-packs/<engine>/<role>.toml",
            "complete role contract",
            "`name`",
            "`description`",
            "`developer_instructions`",
            "`model`",
            "`model_reasoning_effort`",
            "single-agent fallback",
        ):
            with self.subTest(token=token):
                self.assertIn(token, normalized)

    def test_plugin_agent_delegation_protocol_preserves_coordination_ownership(self):
        # Arrange / Act
        text = PROTOCOL.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        coordination = (ROOT / ".codex/docs/coordination-rules.md").read_text(
            encoding="utf-8"
        )

        # Assert
        for token in (
            "direct child",
            "bounded",
            "parent synthesis",
            "Do not copy role TOML",
            "repository-local `.codex/agents/`",
            "repository-local `.codex/agent-packs/`",
        ):
            with self.subTest(token=token):
                self.assertIn(token, normalized)
        self.assertIn("plugin-agent-delegation.md", coordination)

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
