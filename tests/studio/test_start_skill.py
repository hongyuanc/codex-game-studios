from pathlib import Path
import tempfile
import unittest

from tools.codex_studio.engine_pack import load_studio_config
from tools.codex_studio.start_initialization import (
    contract,
    contract_fingerprint,
    contract_summary,
    detect_project_state,
    validate_contract,
    validate_documentation,
    validate_session,
)
from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / ".agents/skills/start/SKILL.md"
def valid_initialization_session(initialization_contract: dict[str, object]) -> dict[str, object]:
    action = {
        "path": ".codex/studio.toml",
        "kind": "create",
        "material_change": "write the complete default authority",
        "form": "atomic",
        "expanded_paths": [".codex/studio.toml"],
    }
    return {
        "authority_state": "missing",
        "events": [
            {"type": "detect"},
            {"type": "select-next-step"},
            {
                "type": "initialization-changeset",
                "authority_toml": initialization_contract["default_authority_toml"],
                "actions": [action],
            },
            {"type": "approval"},
            {
                "type": "write",
                "path": action["path"],
                "kind": action["kind"],
                "material_change": action["material_change"],
            },
        ],
    }


class StartSkillTests(unittest.TestCase):
    def test_start_initialization_rejects_reviewed_bypass_sessions(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        bypasses = {
            "unlisted post-approval write": {
                **valid,
                "events": [
                    *valid["events"],
                    {
                        "type": "write",
                        "path": "production/stage.txt",
                        "kind": "create",
                        "material_change": "write an unlisted stage",
                    },
                ],
            },
            "exact forbidden directory": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": ".agents/skills",
                                "kind": "directory-create",
                                "material_change": "create a forbidden directory",
                                "form": "atomic",
                                "expanded_paths": [".agents/skills"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "repository escape": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "../outside.txt",
                                "kind": "create",
                                "material_change": "escape the project",
                                "form": "atomic",
                                "expanded_paths": ["../outside.txt"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "absolute target": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "/tmp/outside.txt",
                                "kind": "create",
                                "material_change": "escape with an absolute path",
                                "form": "atomic",
                                "expanded_paths": ["/tmp/outside.txt"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "path alias": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "./.codex/studio.toml",
                                "kind": "create",
                                "material_change": "use a path alias",
                                "form": "atomic",
                                "expanded_paths": ["./.codex/studio.toml"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "speculative directory": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production",
                                "kind": "directory-create",
                                "material_change": "create an empty directory",
                                "form": "atomic",
                                "expanded_paths": ["production"],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "hidden bulk action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": ".codex/studio.toml",
                                "kind": "create",
                                "material_change": "write the selected authority artifacts",
                                "form": "atomic",
                                "expanded_paths": [
                                    ".codex/studio.toml",
                                    "production/stage.txt",
                                ],
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "initialized repository write": {
                "authority_state": "initialized",
                "events": [{"type": "write", "path": "production/stage.txt"}],
            },
        }

        # Act / Assert
        for name, session in bypasses.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_session(session)

    def test_start_initialization_contract_loads_complete_default_authority(self):
        # Arrange
        initialization_contract = contract()

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            control = project / ".codex"
            control.mkdir(parents=True)

            # Act
            (control / "studio.toml").write_text(
                initialization_contract["default_authority_toml"], encoding="utf-8"
            )
            config = load_studio_config(project)

            # Assert
            self.assertEqual("unconfigured", config.engine)
            self.assertEqual("", config.engine_version)
            self.assertEqual("", config.language)
            self.assertEqual("phase-gated", config.review_mode)
            self.assertEqual("none", config.active_engine_pack)
            self.assertEqual("balanced", config.model_policy)

    def test_start_initialization_contract_executes_missing_authority_read_only_until_approval(self):
        # Arrange
        initialization_contract = contract()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            for path in (
                ".codex",
                "src",
                "design/gdd",
                "prototypes",
                "production/sprints",
                "production/milestones",
            ):
                (project / path).mkdir(parents=True, exist_ok=True)
            before = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            # Act
            state = detect_project_state(project)
            validate_session(valid_initialization_session(initialization_contract))
            after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            # Assert
            self.assertEqual("missing", state["authority_state"])
            self.assertTrue(state["fresh"])
            self.assertEqual(before, after)

    def test_start_initialization_contract_rejects_invalid_sessions(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        eleven_actions = [
            {
                "path": f"production/path-{index}.txt",
                "kind": "create",
                "material_change": "create one explicit file",
            }
            for index in range(11)
        ]
        cases = {
            "pre-approval write": {
                **valid,
                "events": [
                    {"type": "detect"},
                    {"type": "write", "path": ".codex/studio.toml"},
                    *valid["events"][1:],
                ],
            },
            "zero changesets": {
                **valid,
                "events": [{"type": "detect"}, {"type": "approval"}],
            },
            "multiple changesets": {
                **valid,
                "events": [
                    *valid["events"][:3],
                    valid["events"][2],
                    *valid["events"][3:],
                ],
            },
            "eleven paths": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": eleven_actions,
                    },
                    *valid["events"][3:],
                ],
            },
            "glob action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/*.txt",
                                "kind": "create",
                                "material_change": "bulk glob",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "recursive action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/recurse",
                                "kind": "recursive",
                                "material_change": "recursive mutation",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "tree action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/tree",
                                "kind": "tree-copy",
                                "material_change": "copy a tree",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "bulk action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "production/bulk",
                                "kind": "bulk",
                                "material_change": "bulk mutation",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "global target": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": ".agents/skills/start/SKILL.md",
                                "kind": "create",
                                "material_change": "install a global skill",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "unselected engine reference": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "actions": [
                            {
                                "path": "docs/engine-reference/unreal/VERSION.md",
                                "kind": "create",
                                "material_change": "initialize an unselected reference",
                            }
                        ],
                    },
                    *valid["events"][3:],
                ],
            },
            "incomplete authority": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "authority_toml": 'engine = "unconfigured"\n',
                    },
                    *valid["events"][3:],
                ],
            },
            "invalid authority": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {
                        **valid["events"][2],
                        "authority_toml": (
                            'engine = "unconfigured"\n'
                            'engine_version = ""\n'
                            'language = ""\n'
                            'review_mode = "phase-gated"\n'
                            'active_engine_pack = "none"\n'
                            'model_policy = ""\n'
                        ),
                    },
                    *valid["events"][3:],
                ],
            },
        }

        # Act / Assert
        for name, session in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_session(session)

    def test_start_initialization_contract_preserves_initialized_repositories(self):
        # Arrange
        initialization_contract = contract()

        # Act / Assert
        validate_session(
            {
                "authority_state": "initialized",
                "events": [{"type": "detect"}],
            }
        )
        with self.assertRaises(ValueError):
            validate_session(
                {
                    "authority_state": "initialized",
                    "events": valid_initialization_session(initialization_contract)["events"],
                }
            )

    def test_start_initialization_reconciles_missing_duplicate_and_reordered_actions(self):
        # Arrange
        initialization_contract = contract()
        valid = valid_initialization_session(initialization_contract)
        action = valid["events"][2]["actions"][0]
        stage_action = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
        }
        stage_write = {
            "type": "write",
            "path": stage_action["path"],
            "kind": stage_action["kind"],
            "material_change": stage_action["material_change"],
        }
        cases = {
            "missing action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": []},
                    *valid["events"][3:],
                ],
            },
            "duplicated action": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [action, action]},
                    *valid["events"][3:],
                ],
            },
            "reordered writes": {
                **valid,
                "events": [
                    *valid["events"][:2],
                    {**valid["events"][2], "actions": [action, stage_action]},
                    *valid["events"][3:4],
                    stage_write,
                    valid["events"][4],
                ],
            },
        }

        # Act / Assert
        for name, session in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_session(session)

    def test_start_initialization_contract_binds_production_docs_and_rejects_mutation(self):
        # Arrange
        framework = ROOT / "Codex Studio Testing Framework/skills/utility/start.md"
        runtime_text = START.read_text(encoding="utf-8")
        framework_text = framework.read_text(encoding="utf-8")
        mutated_contract = contract()
        mutated_contract["first_run"]["max_path_mutations"] = 11

        # Act / Assert
        validate_contract(contract())
        validate_documentation(runtime_text, framework_text)
        self.assertIn(contract_fingerprint(), runtime_text)
        self.assertIn(contract_summary(), framework_text)
        with self.assertRaises(ValueError):
            validate_contract(mutated_contract)
        with self.assertRaises(ValueError):
            validate_documentation(
                runtime_text.replace("at most 10 path mutations", "at most 11 path mutations"),
                framework_text,
            )

    def test_start_initialized_repository_requires_separate_approved_write(self):
        # Arrange
        action = {
            "path": "production/stage.txt",
            "kind": "create",
            "material_change": "write the selected initial stage",
            "form": "atomic",
            "expanded_paths": ["production/stage.txt"],
        }
        session = {
            "authority_state": "initialized",
            "events": [
                {"type": "detect"},
                {"type": "stage-proposal", "action": action},
                {"type": "stage-approval"},
                {
                    "type": "write",
                    "path": action["path"],
                    "kind": action["kind"],
                    "material_change": action["material_change"],
                },
            ],
        }

        # Act / Assert
        validate_session(session)

    def test_clean_template_heuristic_ignores_instruction_only_files(self):
        state = detect_project_state(ROOT)
        self.assertEqual("unconfigured", state["engine"])
        self.assertEqual([], state["source_files"])
        self.assertEqual([], state["design_docs"])
        self.assertEqual([], state["prototypes"])
        self.assertEqual([], state["production_files"])
        self.assertTrue(state["fresh"])
        text = START.read_text(encoding="utf-8")
        self.assertIn("exclude every nested `AGENTS.md`", text)
        self.assertIn("instruction-only files such as `.gitkeep`", text)

    def test_start_supports_plugin_native_uninitialized_repository(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("$codex-game-studios:start", text)
        self.assertIn("Initialization changeset", text)
        self.assertIn("at most 10 path mutations", text)
        self.assertIn("No writes precede approval", text)
        self.assertIn("Forbidden roots and every descendant", text)
        self.assertIn("tools.codex_studio.start_initialization", text)
        self.assertIn('engine = "unconfigured"', text)
        self.assertIn('engine_version = ""', text)
        self.assertIn('language = ""', text)
        self.assertIn('review_mode = "phase-gated"', text)
        self.assertIn('active_engine_pack = "none"', text)
        self.assertIn('model_policy = "balanced"', text)
        self.assertIn("continue read-only project detection", text)
        self.assertIn(
            "Initialization changeset replaces the separate persistent", text
        )
        self.assertNotIn("do not continue to onboarding", text)

    def test_start_is_native_and_detects_unconfigured_fresh_projects(self):
        text = START.read_text(encoding="utf-8")
        self.assertEqual([], validate_skill(START))
        self.assertIn(".codex/studio.toml", text)
        self.assertIn('engine = "unconfigured"', text)
        self.assertIn("No concept, source, prototype, design, or production artifacts", text)
        self.assertIn("route to `$brainstorm`", text)

    def test_start_questions_fit_native_schema(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("Ask one decision per turn", text)
        self.assertIn("2-3 mutually exclusive options", text)
        self.assertIn("New or exploratory", text)
        self.assertIn("Defined or existing", text)
        self.assertNotIn("these exact options", text)
        self.assertNotIn("- `D) Existing work`", text)

    def test_start_uses_actual_project_state_and_orders_persistent_decisions(self):
        text = START.read_text(encoding="utf-8")
        ordered_contract = (
            "Read `.codex/studio.toml`",
            "Check for `design/gdd/game-concept.md`",
            "repository file search for source files in `src/`",
            "Check for subdirectories in `prototypes/`",
            "Check for files in `production/sprints/` or `production/milestones/`",
            "## Phase 2: Confirm the Detected Starting Point",
            "## Phase 3: Confirm the Workflow Path",
            "## Phase 4: Propose the Initial Stage Artifact",
            "## Phase 5: Select Review Depth",
            "## Phase 6: Approve the Studio Configuration Changeset",
            "## Phase 7: Confirm Before Proceeding",
        )
        positions = [text.index(marker) for marker in ordered_contract]
        self.assertEqual(sorted(positions), positions)
        self.assertIn("show the concrete evidence you found", text)
        self.assertIn("production/stage.txt", text)
        self.assertIn('review_mode = "phase-gated"', text)
        self.assertIn("exact `.codex/studio.toml` diff", text)
        self.assertIn("explicit approval", text)

    def test_start_never_creates_a_competing_review_mode_authority(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("`.codex/studio.toml` is the sole persistent review-mode authority", text)
        self.assertIn("Never create a separate review-mode file", text)
        self.assertNotIn("production/review-mode.txt", text)
        self.assertNotIn("production/session-state/review-mode.txt", text)

    def test_all_runtime_skills_use_only_studio_toml_for_persistent_review_mode(self):
        failures = []
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            for legacy in (
                "production/review-mode.txt",
                "production/session-state/review-mode.txt",
            ):
                if legacy in text:
                    failures.append(f"{path.relative_to(ROOT)}: {legacy}")
        self.assertEqual([], failures)

    def test_phase_gated_mode_keeps_mandatory_director_gates(self):
        gates = (ROOT / ".codex/docs/director-gates.md").read_text(encoding="utf-8")
        self.assertIn("lean optional-review depth", gates)
        self.assertIn("mandatory director gates still run", gates)
        self.assertIn('review_mode = "phase-gated"', gates)

    def test_returning_engine_and_concept_skip_onboarding(self):
        text = START.read_text(encoding="utf-8")
        self.assertIn("engine configured, concept exists", text)
        self.assertIn("Skip onboarding entirely", text)


if __name__ == "__main__":
    unittest.main()
