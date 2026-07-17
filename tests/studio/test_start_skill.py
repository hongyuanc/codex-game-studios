from pathlib import Path
import json
import re
import tempfile
import tomllib
import unittest

from tools.codex_studio.engine_pack import load_studio_config
from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / ".agents/skills/start/SKILL.md"
CONTRACT_PATTERN = re.compile(
    r"<!-- start-initialization-contract:start\n(?P<contract>.*?)\n"
    r"start-initialization-contract:end -->",
    re.DOTALL,
)


def load_initialization_contract(text: str) -> dict[str, object]:
    match = CONTRACT_PATTERN.search(text)
    if match is None:
        raise AssertionError("Start initialization contract is missing")
    return json.loads(match.group("contract"))


class InitializationContractHarness:
    """Fail-closed test executor for Start's declared first-run contract."""

    def __init__(self, contract: dict[str, object]):
        self.contract = contract
        self.first_run = contract["first_run"]

    def validate_session(self, session: dict[str, object]) -> None:
        events = session["events"]
        authority_state = session["authority_state"]
        changesets = [event for event in events if event["type"] == "changeset"]

        if authority_state == "initialized":
            if changesets:
                raise ValueError("initialized repositories must not receive initialization changesets")
            return
        if authority_state != "missing":
            raise ValueError("authority state is invalid")
        if self.first_run["action_unit"] != "filesystem path":
            raise ValueError("initialization action unit must be one filesystem path")
        if not self.first_run["replan_above_max_path_mutations"]:
            raise ValueError("initialization cap must require replanning")
        if len(changesets) != self.first_run["initialization_changesets"]:
            raise ValueError("missing authority requires exactly one initialization changeset")

        approval_indexes = [
            index for index, event in enumerate(events) if event["type"] == "approval"
        ]
        if len(approval_indexes) != 1:
            raise ValueError("initialization changeset requires exactly one approval")
        approval_index = approval_indexes[0]
        for index, event in enumerate(events):
            if event["type"] == "write" and index < approval_index:
                raise ValueError("initialization writes require prior approval")

        changeset = changesets[0]
        if not any(event["type"] == "select-next-step" for event in events):
            raise ValueError("initialization changeset requires a selected next step")
        if changeset["authority_toml"] != self.contract["default_authority_toml"]:
            raise ValueError("initialization authority differs from the complete default")
        actions = changeset["actions"]
        if not actions or len(actions) > self.first_run["max_path_mutations"]:
            raise ValueError("initialization changeset path-mutation cap is violated")
        for action in actions:
            self._validate_action(action)

    def _validate_action(self, action: dict[str, object]) -> None:
        path = action["path"]
        if not isinstance(path, str) or not path or any(token in path for token in "*?[]{}"):
            raise ValueError("initialization action path must be exact")
        if action["kind"] not in self.first_run["counted_path_mutations"]:
            raise ValueError("initialization action kind is not atomic")
        if not action["material_change"]:
            raise ValueError("initialization action must describe its material change")
        if any(
            path.startswith(target)
            for target in self.first_run["forbidden_target_prefixes"]
        ):
            raise ValueError("initialization action targets a forbidden resource")


def valid_initialization_session(contract: dict[str, object]) -> dict[str, object]:
    return {
        "authority_state": "missing",
        "events": [
            {"type": "detect"},
            {"type": "select-next-step"},
            {
                "type": "changeset",
                "authority_toml": contract["default_authority_toml"],
                "actions": [
                    {
                        "path": ".codex/studio.toml",
                        "kind": "create",
                        "material_change": "write the complete default authority",
                    }
                ],
            },
            {"type": "approval"},
            {"type": "write", "path": ".codex/studio.toml"},
        ],
    }


def detect_start_state(root: Path) -> dict[str, object]:
    studio_path = root / ".codex/studio.toml"
    authority_state = "initialized" if studio_path.is_file() else "missing"
    studio = (
        tomllib.loads(studio_path.read_text(encoding="utf-8"))
        if authority_state == "initialized"
        else {"engine": "unconfigured"}
    )
    instruction_only = {"AGENTS.md", ".gitkeep"}
    source_suffixes = {".gd", ".cs", ".cpp", ".h", ".rs", ".py", ".js", ".ts"}
    source_files = [
        path for path in (root / "src").rglob("*")
        if path.is_file() and path.name not in instruction_only and path.suffix in source_suffixes
    ]
    design_docs = [
        path for path in (root / "design/gdd").rglob("*.md")
        if path.name not in instruction_only
    ]
    prototypes = [path for path in (root / "prototypes").iterdir() if path.is_dir()]
    production_files = [
        path
        for directory in (root / "production/sprints", root / "production/milestones")
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.is_file() and path.name not in instruction_only
    ]
    concept = root / "design/gdd/game-concept.md"
    fresh = (
        studio["engine"] == "unconfigured"
        and not concept.is_file()
        and not source_files
        and not design_docs
        and not prototypes
        and not production_files
    )
    return {
        "engine": studio["engine"],
        "authority_state": authority_state,
        "source_files": source_files,
        "design_docs": design_docs,
        "prototypes": prototypes,
        "production_files": production_files,
        "fresh": fresh,
    }


class StartSkillTests(unittest.TestCase):
    def test_start_initialization_contract_loads_complete_default_authority(self):
        # Arrange
        contract = load_initialization_contract(START.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            control = project / ".codex"
            control.mkdir(parents=True)

            # Act
            (control / "studio.toml").write_text(
                contract["default_authority_toml"], encoding="utf-8"
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
        contract = load_initialization_contract(START.read_text(encoding="utf-8"))
        harness = InitializationContractHarness(contract)
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
            state = detect_start_state(project)
            harness.validate_session(valid_initialization_session(contract))
            after = sorted(path.relative_to(project).as_posix() for path in project.rglob("*"))

            # Assert
            self.assertEqual("missing", state["authority_state"])
            self.assertTrue(state["fresh"])
            self.assertEqual(before, after)

    def test_start_initialization_contract_rejects_invalid_sessions(self):
        # Arrange
        contract = load_initialization_contract(START.read_text(encoding="utf-8"))
        harness = InitializationContractHarness(contract)
        valid = valid_initialization_session(contract)
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
                    harness.validate_session(session)

    def test_start_initialization_contract_preserves_initialized_repositories(self):
        # Arrange
        contract = load_initialization_contract(START.read_text(encoding="utf-8"))
        harness = InitializationContractHarness(contract)

        # Act / Assert
        harness.validate_session(
            {
                "authority_state": "initialized",
                "events": [{"type": "detect"}, {"type": "phase-4-6-proposals"}],
            }
        )
        with self.assertRaises(ValueError):
            harness.validate_session(
                {
                    "authority_state": "initialized",
                    "events": valid_initialization_session(contract)["events"],
                }
            )

    def test_clean_template_heuristic_ignores_instruction_only_files(self):
        state = detect_start_state(ROOT)
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
        self.assertIn("at most 10 mutating actions", text)
        self.assertIn("zero writes before explicit approval", text)
        self.assertIn("must not create `.agents/skills/`", text)
        self.assertIn("must not initialize global or plugin resources", text)
        self.assertIn('engine = "unconfigured"', text)
        self.assertIn('engine_version = ""', text)
        self.assertIn('language = ""', text)
        self.assertIn('review_mode = "phase-gated"', text)
        self.assertIn('active_engine_pack = "none"', text)
        self.assertIn('model_policy = "balanced"', text)
        self.assertIn("continue read-only project detection", text)
        self.assertIn(
            "replaces the separate persistent proposals in Phases 4-6", text
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
