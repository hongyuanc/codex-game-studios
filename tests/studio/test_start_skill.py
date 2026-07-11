from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / ".agents/skills/start/SKILL.md"


class StartSkillTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
