from pathlib import Path
import re
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
DELEGATION_PATTERN = re.compile(r"\b(?:delegate|spawn|subagent|custom-agent)\b")
DELEGATION_PREFLIGHT = (
    "Resolve every role through `../../../.codex/docs/plugin-agent-delegation.md`;\n"
    "do not require a repository-local `.codex/agents/` or `.codex/agent-packs/` tree."
)
EXPECTED_DELEGATING_SKILLS = {
    "architecture-decision",
    "architecture-review",
    "art-bible",
    "asset-spec",
    "brainstorm",
    "code-review",
    "create-architecture",
    "create-control-manifest",
    "create-epics",
    "create-stories",
    "day-one-patch",
    "design-review",
    "design-system",
    "dev-story",
    "gate-check",
    "hotfix",
    "localize",
    "map-systems",
    "milestone-review",
    "playtest-report",
    "propagate-design-change",
    "prototype",
    "review-all-gdds",
    "security-audit",
    "sprint-plan",
    "story-done",
    "story-readiness",
    "team-audio",
    "team-combat",
    "team-level",
    "team-live-ops",
    "team-narrative",
    "team-polish",
    "team-qa",
    "team-release",
    "team-ui",
    "ux-design",
    "vertical-slice",
}
NAMES = set(
    """bug-report bug-triage code-review create-epics create-stories dev-story estimate
milestone-review playtest-report qa-plan regression-suite retrospective smoke-check
soak-test sprint-plan sprint-status story-done story-readiness test-evidence-review
test-flakiness test-helpers test-setup""".split()
)


def delegating_skill_paths():
    """Return the exact canonical skills selected by the Task 4 keyword query."""

    paths = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
    return tuple(
        path
        for path in paths
        if DELEGATION_PATTERN.search(path.read_text(encoding="utf-8"))
    )


class DeliverySkillTests(unittest.TestCase):
    def skill_text(self, name):
        return (ROOT / ".agents/skills" / name / "SKILL.md").read_text(encoding="utf-8")

    def test_exact_delivery_skill_set_exists(self):
        found = {path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")}
        self.assertTrue(NAMES <= found)
        self.assertEqual(22, len(NAMES))
        report = (ROOT / ".superpowers/sdd/delivery-subsystem-report.md").read_text(
            encoding="utf-8"
        )
        packaged = set(re.findall(r"\.agents/skills/([^/]+)/SKILL\.md", report))
        self.assertEqual(NAMES, packaged)

    def test_delegation_discovery_has_no_false_omissions(self):
        # Arrange / Act
        discovered = {path.parent.name for path in delegating_skill_paths()}

        # Assert
        self.assertEqual(EXPECTED_DELEGATING_SKILLS, discovered)

    def test_delegating_skills_use_plugin_portable_role_protocol(self):
        # Arrange / Act / Assert
        for path in delegating_skill_paths():
            with self.subTest(skill=path.parent.name):
                self.assertEqual(
                    1,
                    path.read_text(encoding="utf-8").count(DELEGATION_PREFLIGHT),
                    path,
                )

    def test_review_mode_uses_only_canonical_studio_config(self):
        for name in sorted(NAMES):
            with self.subTest(skill=name):
                self.assertNotIn("production/review-mode.txt", self.skill_text(name))
        for name in (
            "create-epics",
            "create-stories",
            "milestone-review",
            "playtest-report",
            "sprint-plan",
            "story-done",
            "story-readiness",
        ):
            with self.subTest(gated_skill=name):
                text = self.skill_text(name)
                self.assertIn(".codex/studio.toml", text)
                self.assertIn('review_mode = "phase-gated"', text)

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

    def test_dev_story_is_read_only_until_preflight_approval(self):
        text = self.skill_text("dev-story")
        before_gate = text.split("### Implementation Preflight", 1)[0]
        for forbidden in (
            "set the story status",
            "edit the story file",
            "May I update [dependency path] Status to Complete?",
            "mark it Complete and continue",
        ):
            self.assertNotIn(forbidden, before_gate)
        self.assertIn("read-only resolution decisions", before_gate)
        self.assertIn("Never mark another story Complete", text)
        self.assertIn("route completion through `$story-done`", text)

    def test_story_done_requires_passing_evidence(self):
        text = self.skill_text("story-done")
        self.assertIn(
            "Never mark the story Complete while any acceptance criterion is unverified, "
            "any required test is failing, or required test evidence is missing.",
            text,
        )

    def test_story_done_requires_exact_attributable_fresh_evidence(self):
        text = self.skill_text("story-done")
        for token in (
            "exact required evidence path",
            "story ID",
            "criterion IDs",
            "required schema",
            "freshness",
            "passing verdict",
        ):
            self.assertIn(token, text)
        for shortcut in (
            "accept as assumed",
            "search `tests/unit/[system]/` broadly",
            "search `tests/integration/[system]/` broadly",
            "check for any `production/qa/smoke-*.md` file",
            "ADVISORY untested criteria",
        ):
            self.assertNotIn(shortcut, text)

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

    def test_complete_planning_changesets_cover_every_output(self):
        stories = self.skill_text("create-stories")
        stories_approval = stories.split("Show the complete proposed changeset", 1)[1].split(
            "## 6. Write Story Files", 1
        )[0]
        for token in (
            "every story path",
            "production/epics/[epic-slug]/EPIC.md",
            "production/epics/index.md",
        ):
            self.assertIn(token, stories_approval)

        sprint = self.skill_text("sprint-plan")
        self.assertIn("## Complete Proposed Changeset Approval", sprint)
        sprint_before_approval = sprint.split("## Complete Proposed Changeset Approval", 1)[0]
        self.assertNotIn("write `production/review-mode.txt`", sprint_before_approval)
        sprint_approval = sprint.split("## Complete Proposed Changeset Approval", 1)[1]
        for token in (
            "production/sprints/sprint-[N].md",
            "production/sprint-status.yaml",
            "production/qa/qa-plan-sprint-[N]-[date].md",
            "QA-gate revisions",
            "revised complete changeset",
        ):
            self.assertIn(token, sprint_approval)

        retro = self.skill_text("retrospective")
        self.assertIn("## Complete Proposed Changeset Approval", retro)
        retro_approval = retro.split("## Complete Proposed Changeset Approval", 1)[1]
        self.assertIn("archive or rename", retro_approval)
        self.assertIn("new retrospective report", retro_approval)

    def test_in_memory_sprint_draft_flows_directly_to_qa_plan(self):
        qa = self.skill_text("qa-plan")
        for token in (
            "sprint-draft",
            "in-memory sprint draft",
            "never select the most recent persisted sprint",
        ):
            self.assertIn(token, qa)

        sprint = self.skill_text("sprint-plan")
        self.assertIn("$qa-plan sprint-draft", sprint)
        self.assertIn("pass the current in-memory sprint draft", sprint)
        self.assertIn("combined complete changeset", sprint)
        self.assertNotIn("then re-run `$sprint-plan`", sprint)

    def test_missing_traceability_blocks_story_generation_and_readiness(self):
        generation = self.skill_text("create-stories")
        self.assertNotIn("TR-[system]-???", generation)
        self.assertIn("Missing registry or TR-ID", generation)
        self.assertIn("Status: Blocked", generation)

        readiness = self.skill_text("story-readiness")
        self.assertNotIn(
            "Auto-pass if the story has no TR-ID reference OR if the registry does not exist",
            readiness,
        )
        self.assertIn("Missing TR registry", readiness)
        self.assertIn("Missing or unregistered TR-ID", readiness)
        self.assertIn("cannot receive READY", readiness)

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

    def test_manual_evidence_uses_one_canonical_root(self):
        for name in ("create-stories", "story-done", "test-setup", "smoke-check"):
            with self.subTest(skill=name):
                text = self.skill_text(name)
                self.assertIn("production/qa/evidence/", text)
                self.assertNotIn("tests/evidence/", text)

    def test_config_data_evidence_has_exact_producer_consumer_contract(self):
        stories = self.skill_text("create-stories")
        exact_path = "production/qa/evidence/[story-id]-smoke-evidence.md"
        self.assertIn(exact_path, stories)
        self.assertNotIn("Config/Data: smoke check pass (`production/qa/smoke-*.md`)", stories)

        smoke = self.skill_text("smoke-check")
        self.assertIn(exact_path, smoke)
        for token in (
            "Story ID",
            "Criterion IDs",
            "Build/engine",
            "Timestamp",
            "Observed result",
            "Verdict: PASS / FAIL",
            "every per-story Config/Data evidence path",
        ):
            self.assertIn(token, smoke)

        done = self.skill_text("story-done")
        self.assertIn(exact_path, done)
        self.assertNotIn("production/qa/smoke-*.md", done)

    def test_legacy_criterion_ids_use_preverification_backfill(self):
        text = self.skill_text("story-done")
        self.assertIn("## Pre-Verification Criterion-ID Backfill", text)
        backfill = text.split("## Pre-Verification Criterion-ID Backfill", 1)[1].split(
            "## Phase 3: Verify Acceptance Criteria", 1
        )[0]
        for token in (
            "separately authorized complete changeset",
            "stable criterion IDs",
            "exact evidence references",
            "restart verification",
        ):
            self.assertIn(token, backfill)
        self.assertIn("No evidence verification may begin", backfill)

    def test_cross_subsystem_handoffs_require_native_readiness(self):
        dependencies = {
            "setup-engine": ("test-setup", "test-helpers", "smoke-check"),
            "team-qa": (
                "bug-triage",
                "dev-story",
                "sprint-plan",
                "story-done",
                "test-evidence-review",
            ),
            "hotfix": ("bug-report",),
            "skill-test": ("test-helpers",),
        }
        for dependency, invokers in dependencies.items():
            for invoker in invokers:
                with self.subTest(dependency=dependency, invoker=invoker):
                    text = self.skill_text(invoker)
                    self.assertIn(f"Native readiness gate for `${dependency}`", text)
                    self.assertIn("Staged dependency", text)
                    self.assertIn("do not invoke", text)

    def test_generated_templates_use_valid_engine_syntax(self):
        setup = self.skill_text("test-setup")
        self.assertIn('res://addons/gdunit4/GdUnitRunner.gd', setup)
        self.assertNotIn("res:/$addons", setup)

        helpers = self.skill_text("test-helpers")
        self.assertIn("</summary>", helpers)
        self.assertNotIn("<$summary>", helpers)

    def test_review_and_soak_wording_has_no_known_contradictions(self):
        review = self.skill_text("code-review")
        self.assertNotIn("fix the implementation to comply", review)

        story_done = self.skill_text("story-done")
        self.assertNotIn("ADVISORY untested criteria", story_done)

        soak = self.skill_text("soak-test")
        self.assertIn("Δ/hr", soak)
        self.assertNotIn("Δ$hr", soak)

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
