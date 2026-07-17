from pathlib import Path
import tomllib
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / ".agents/skills/start/SKILL.md"


def detect_start_state(root: Path) -> dict[str, object]:
    studio = tomllib.loads((root / ".codex/studio.toml").read_text(encoding="utf-8"))
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
        "source_files": source_files,
        "design_docs": design_docs,
        "prototypes": prototypes,
        "production_files": production_files,
        "fresh": fresh,
    }


class StartSkillTests(unittest.TestCase):
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
        self.assertIn("engine/version/language are `unconfigured`", text)
        self.assertIn('review_mode = "phase-gated"', text)
        self.assertIn('active_engine_pack = "none"', text)
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
