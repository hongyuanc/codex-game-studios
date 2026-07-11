from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
NAMES = set(
    """adopt architecture-decision architecture-review art-bible asset-audit asset-spec
balance-check brainstorm consistency-check content-audit create-architecture
create-control-manifest design-review design-system gate-check help map-systems
perf-profile project-stage-detect propagate-design-change prototype quick-design
review-all-gdds scope-check start tech-debt ux-design ux-review vertical-slice""".split()
)


class DesignSkillTests(unittest.TestCase):
    def skill_text(self, name):
        return (ROOT / ".agents/skills" / name / "SKILL.md").read_text(encoding="utf-8")

    def skill_section(self, name, start, end):
        text = self.skill_text(name)
        self.assertIn(start, text)
        self.assertIn(end, text)
        return text.split(start, 1)[1].split(end, 1)[0]

    def test_exact_skill_set_exists(self):
        found = {path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")}
        self.assertEqual(NAMES, {name for name in found if name in NAMES})
        self.assertEqual(29, len(NAMES))

    def test_design_skills_are_native(self):
        issues = []
        for name in sorted(NAMES):
            issues.extend(validate_skill(ROOT / ".agents/skills" / name / "SKILL.md"))
        self.assertEqual([], issues)

    def test_architecture_review_approves_every_tracking_write_once(self):
        text = self.skill_text("architecture-review")
        approval = self.skill_section(
            "architecture-review", "### Complete proposed changeset approval", "### RTM Output"
        )
        for path in (
            "design/gdd/systems-index.md",
            "docs/architecture/architecture-review-[date].md",
            "docs/architecture/architecture-traceability.md",
            "docs/architecture/tr-registry.yaml",
            "docs/architecture/requirements-traceability.md",
            "docs/consistency-failures.md",
            "production/session-state/active.md",
        ):
            self.assertIn(path, approval)
        self.assertNotIn("silently append", text)

    def test_review_all_gdds_approves_every_tracking_write_once(self):
        text = self.skill_text("review-all-gdds")
        approval = self.skill_section(
            "review-all-gdds", "### Complete proposed changeset approval", "## Phase 7"
        )
        for path in (
            "design/gdd/gdd-cross-review-[date].md",
            "design/gdd/systems-index.md",
            "production/session-state/active.md",
        ):
            self.assertIn(path, approval)
        self.assertNotIn("silently\nappend", text)

    def test_architecture_decision_changeset_covers_dependent_stories(self):
        text = self.skill_text("architecture-decision")
        approval = self.skill_section(
            "architecture-decision",
            "### Complete proposed changeset approval",
            "## 6. Update Architecture Registry",
        )
        self.assertIn("Dependent story updates", approval)
        self.assertIn("Only update story files listed in the approved changeset", approval)
        self.assertNotIn(
            "Update any stories that were `Status: Blocked` pending this ADR to `Status: Ready`.",
            text,
        )

    def test_quick_design_uses_one_complete_changeset_approval(self):
        text = self.skill_text("quick-design")
        approval = self.skill_section(
            "quick-design", "### Complete changeset approval", "## 5. Handoff"
        )
        self.assertIn("design/quick-specs/[kebab-case-title]-[YYYY-MM-DD].md", approval)
        self.assertIn("design/gdd/[filename].md", approval)
        self.assertNotIn("ask separately after", approval)
        self.assertNotIn("If [A]: ask", approval)

    def test_design_review_tracking_decisions_are_sequential(self):
        text = self.skill_text("design-review")
        self.assertIn("Ask the systems-index decision first and wait for the answer", text)
        self.assertIn("Then ask the review-log decision and wait for the answer", text)
        self.assertNotIn("Select any you'd like me to complete", text)
        self.assertNotIn("tracking records (combined", text)

    def test_ux_design_asks_one_information_decision_per_turn(self):
        text = self.skill_text("ux-design")
        self.assertIn("Ask about one information item per turn", text)
        self.assertNotIn("groups of 3-4", text)

    def test_material_architecture_gates_are_required_in_every_review_mode(self):
        decision = self.skill_text("architecture-decision")
        propagation = self.skill_text("propagate-design-change")
        self.assertIn("TD-ADR is required in full, lean, and solo modes", decision)
        self.assertIn("TD-CHANGE-IMPACT is required in full, lean, and solo modes", propagation)
        self.assertNotIn("TD-ADR skipped", decision)
        self.assertNotIn("TD-CHANGE-IMPACT skipped", propagation)
