from pathlib import Path
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
NAMES = set(
    """bug-report bug-triage code-review create-epics create-stories dev-story estimate
milestone-review playtest-report qa-plan regression-suite retrospective smoke-check
soak-test sprint-plan sprint-status story-done story-readiness test-evidence-review
test-flakiness test-helpers test-setup""".split()
)


class DeliverySkillTests(unittest.TestCase):
    def skill_text(self, name):
        return (ROOT / ".agents/skills" / name / "SKILL.md").read_text(encoding="utf-8")

    def test_exact_delivery_skill_set_exists(self):
        found = {path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")}
        self.assertTrue(NAMES <= found)

    def test_delivery_skills_are_native(self):
        issues = [
            issue
            for name in sorted(NAMES)
            for issue in validate_skill(ROOT / ".agents/skills" / name / "SKILL.md")
        ]
        self.assertEqual([], issues)

    def test_descriptions_are_trigger_oriented(self):
        for name in sorted(NAMES):
            with self.subTest(skill=name):
                frontmatter = self.skill_text(name).split("---", 2)[1]
                description = next(
                    line for line in frontmatter.splitlines() if line.startswith("description:")
                )
                self.assertTrue(description.startswith('description: "Use when'))

    def test_dev_story_contains_single_preflight_gate(self):
        text = self.skill_text("dev-story")
        self.assertIn("## Implementation Preflight", text)
        for field in (
            "- Story: [path]",
            "- Requirements: [TR-IDs]",
            "- Governing ADRs: [paths]",
            "- Intended files: [complete list]",
            "- Required tests: [complete list]",
            "- Acceptance criteria: [checkbox list]",
            "- Risks or open questions: [none, or explicit items]",
        ):
            self.assertIn(field, text)
        self.assertIn("approved story boundary", text)
        self.assertIn("do not ask again for each listed file", text)
        self.assertIn("Pause", text)
        self.assertIn("outside", text)

    def test_story_done_requires_passing_evidence(self):
        text = self.skill_text("story-done")
        self.assertIn(
            "Never mark the story Complete while any acceptance criterion is unverified, "
            "any required test is failing, or required test evidence is missing.",
            text,
        )

    def test_diagnostic_workflows_are_read_only_without_fix_approval(self):
        for name in ("code-review", "test-evidence-review", "story-readiness", "estimate"):
            with self.subTest(skill=name):
                text = self.skill_text(name).lower()
                self.assertIn("read-only", text)
                self.assertIn("separately", text)
                self.assertIn("authoriz", text)

    def test_existing_stories_are_not_regenerated_for_optional_metadata(self):
        text = self.skill_text("create-stories")
        self.assertIn("Do not regenerate existing stories", text)
        self.assertIn("newer optional metadata", text)

    def test_traceability_contracts_remain_explicit(self):
        for name in ("create-epics", "create-stories", "story-readiness"):
            with self.subTest(skill=name):
                text = self.skill_text(name)
                for token in ("TR-ID", "ADR", "control manifest", "acceptance", "test evidence"):
                    self.assertIn(token.lower(), text.lower())

    def test_test_infrastructure_uses_one_complete_preflight(self):
        for name in ("test-helpers", "test-setup"):
            with self.subTest(skill=name):
                text = self.skill_text(name)
                self.assertIn("## Changeset Preflight", text)
                self.assertIn("every new or modified file", text)
                self.assertIn("do not ask again for each listed file", text)

    def test_regression_registry_requires_proposed_entries(self):
        text = self.skill_text("regression-suite")
        self.assertIn("proposed entries", text)
        self.assertIn("approval", text.lower())

    def test_interaction_contract_is_one_decision_per_turn(self):
        for name in sorted(NAMES):
            with self.subTest(skill=name):
                self.assertIn("one decision question per turn", self.skill_text(name).lower())


if __name__ == "__main__":
    unittest.main()
