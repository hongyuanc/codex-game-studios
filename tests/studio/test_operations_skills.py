from pathlib import Path
import re
import tempfile
import unittest

from tools.codex_studio.validate import validate_skill


ROOT = Path(__file__).resolve().parents[2]
NAMES = set(
    """changelog day-one-patch hotfix launch-checklist localize onboard patch-notes
    release-checklist reverse-document security-audit skill-improve skill-test
    team-audio team-combat team-level team-live-ops team-narrative team-polish
    team-qa team-release team-ui""".split()
)
TEAM_ROSTERS = {
    "team-audio": {
        "audio-director",
        "sound-designer",
        "technical-artist",
        "gameplay-programmer",
    },
    "team-combat": {
        "game-designer",
        "gameplay-programmer",
        "ai-programmer",
        "technical-artist",
        "sound-designer",
        "qa-tester",
    },
    "team-level": {
        "level-designer",
        "narrative-director",
        "world-builder",
        "art-director",
        "systems-designer",
        "qa-tester",
    },
    "team-live-ops": {
        "live-ops-designer",
        "economy-designer",
        "analytics-engineer",
        "community-manager",
        "writer",
        "narrative-director",
    },
    "team-narrative": {
        "narrative-director",
        "writer",
        "world-builder",
        "level-designer",
    },
    "team-polish": {
        "performance-analyst",
        "technical-artist",
        "sound-designer",
        "qa-tester",
    },
    "team-qa": {"qa-lead", "qa-tester"},
    "team-release": {"release-manager", "qa-lead", "devops-engineer", "producer"},
    "team-ui": {
        "ux-designer",
        "art-director",
        "ui-programmer",
        "accessibility-specialist",
        "qa-tester",
    },
}


class OperationsSkillTests(unittest.TestCase):
    def skill_text(self, name):
        return (ROOT / ".agents/skills" / name / "SKILL.md").read_text(encoding="utf-8")

    def test_exact_operations_skill_set_is_packaged(self):
        found = {path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")}
        self.assertTrue(NAMES <= found)
        self.assertEqual(21, len(NAMES))
        report_path = ROOT / ".superpowers/sdd/operations-subsystem-report.md"
        self.assertTrue(report_path.is_file(), "operations subsystem report is missing")
        report = report_path.read_text(encoding="utf-8")
        packaged = set(re.findall(r"\.agents/skills/([^/]+)/SKILL\.md", report))
        self.assertEqual(NAMES, packaged)

    def test_operations_skills_are_native(self):
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

    def test_team_rosters_are_exact(self):
        configured_roles = {path.stem for path in (ROOT / ".codex/agents").glob("*.toml")}
        for name, expected in TEAM_ROSTERS.items():
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("## Team Roster", text)
                roster = text.split("## Team Roster", 1)[1].split("## ", 1)[0]
                actual = set(re.findall(r"^- `([^`]+)`", roster, flags=re.MULTILINE))
                self.assertEqual(expected, actual)
                mentioned_roles = {
                    role
                    for role in configured_roles
                    if re.search(rf"(?<![a-z0-9-]){re.escape(role)}(?![a-z0-9-])", text)
                }
                self.assertEqual(expected, mentioned_roles)

    def test_team_skills_define_bounded_parent_synthesis(self):
        for name in sorted(TEAM_ROSTERS):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("## Delegation Plan", text)
                for phrase in (
                    "independent and bounded",
                    "The parent agent synthesizes",
                    "must not spawn additional agents",
                    "No subagent commits, publishes, or expands scope",
                    "read-only or draft-only",
                    "one complete changeset approval",
                ):
                    self.assertIn(phrase, text)

    def test_team_skills_use_canonical_review_mode(self):
        for name in sorted(TEAM_ROSTERS):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn(".codex/studio.toml", text)
                self.assertIn('review_mode = "phase-gated"', text)
                self.assertNotIn("production/review-mode.txt", text)

    def test_team_mutations_follow_parent_changeset_gate(self):
        dangerous_before_gate = {
            "team-audio": ("Implement audio manager", "Write unit tests"),
            "team-combat": ("Implement core combat", "Write test cases", "File bug reports"),
            "team-polish": ("optimized code with before/after metrics", "relevant programmers"),
            "team-ui": ("Implement the UI", "add it to `design/ux/interaction-patterns.md`"),
            "team-qa": ("write a formal bug report", "silently append"),
            "team-release": ("Update milestone tracking", "Generate release report"),
        }
        for name, forbidden in dangerous_before_gate.items():
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("## Parent Changeset Gate", text)
                self.assertIn("## Approved Execution", text)
                gate_at = text.index("## Parent Changeset Gate")
                execute_at = text.index("## Approved Execution")
                self.assertLess(gate_at, execute_at)
                before_gate = text[:gate_at]
                self.assertIn("read-only or draft-only", before_gate)
                for phrase in forbidden:
                    self.assertNotIn(phrase, before_gate)
                gate = text[gate_at:execute_at]
                for phrase in (
                    "exact file paths",
                    "exact diffs",
                    "tests and evidence",
                    "session-state, report, and milestone writes",
                    "The parent synthesizes",
                    "approval",
                ):
                    self.assertIn(phrase, gate)
                execution = text[execute_at:]
                self.assertIn("Only after approval", execution)
                self.assertIn("No subagent commits, publishes, or expands scope", execution)

    def test_operational_delegation_is_bounded(self):
        for name in ("day-one-patch", "hotfix", "localize", "security-audit"):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("## Delegation Contract", text)
                for phrase in (
                    "independent and bounded",
                    "exact artifact or evidence",
                    "must not spawn additional agents",
                    "agents.max_depth = 1",
                    "The parent synthesizes",
                    "No subagent commits, publishes, or expands scope",
                ):
                    self.assertIn(phrase, text)

    def test_task_call_syntax_is_forbidden(self):
        for name in sorted(NAMES):
            with self.subTest(skill=name):
                self.assertIsNone(
                    re.search(r"\bTask calls?\b|\btask-call(?:s|ing)?\b", self.skill_text(name), re.I)
                )

        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "SKILL.md"
            fixture.write_text(
                "---\nname: fixture\ndescription: Use when testing.\n---\n"
                "Issue both Task calls before waiting.\n",
                encoding="utf-8",
            )
            issues = validate_skill(fixture)
        self.assertTrue(any("task-call" in issue.message.lower() for issue in issues))

    def test_canonical_output_paths_and_semantics(self):
        changelog = self.skill_text("changelog")
        self.assertIn("docs/CHANGELOG.md", changelog)
        self.assertIn("append", changelog.lower())
        self.assertIn("newest entries first", changelog)

        self.assertIn(
            "production/hotfixes/hotfix-[date]-[short-name].md",
            self.skill_text("hotfix"),
        )
        self.assertIn(
            "production/onboarding/onboard-[role]-[date].md",
            self.skill_text("onboard"),
        )

        patch_notes = self.skill_text("patch-notes")
        for path in (
            "production/releases/[version]/changelog.md",
            "docs/patch-notes/[version].md",
            "production/releases/[version]/patch-notes.md",
        ):
            self.assertIn(path, patch_notes)
        self.assertIn("Verdict: **SAVED**", patch_notes)
        self.assertIn("Verdict: **DRAFT COMPLETE — NOT SAVED**", patch_notes)

    def test_reverse_document_uses_native_templates_and_sequential_questions(self):
        text = self.skill_text("reverse-document")
        for template in (
            ".codex/docs/templates/design-doc-from-implementation.md",
            ".codex/docs/templates/architecture-doc-from-code.md",
            ".codex/docs/templates/concept-doc-from-prototype.md",
        ):
            self.assertIn(template, text)
            self.assertTrue((ROOT / template).is_file())
        self.assertNotRegex(text, r"(?<!\.codex/docs/)templates/")
        self.assertIn("Ask the first unresolved intent question and wait for the answer", text)
        self.assertIn("Then ask the next unresolved intent question", text)
        self.assertNotIn("Before drafting, could you clarify:", text)
        self.assertNotIn("Would you like me to tackle any of these now?", text)

    def test_skill_test_counts_and_default_mode_are_discovered(self):
        text = self.skill_text("skill-test")
        self.assertIn("No argument → run `audit`", text)
        for hardcoded in ("All 52 Skills", "SKILLS (72 total)", "72/72", "49/49"):
            self.assertNotIn(hardcoded, text)
        self.assertIn("discovered", text)

    def test_diagnostic_completion_distinguishes_saved_from_draft(self):
        security = self.skill_text("security-audit")
        self.assertIn("Verdict: **SAVED**", security)
        self.assertIn("Verdict: **DRAFT COMPLETE — NOT SAVED**", security)

    def test_team_qa_decisions_are_sequential_and_schema_sized(self):
        text = self.skill_text("team-qa")
        self.assertNotIn("batched 3-4", text)
        self.assertNotIn("Batch stories into groups", text)
        for block in re.findall(r"```\nquestion:.*?```", text, flags=re.S):
            options = re.findall(r'^  - "', block, flags=re.MULTILINE)
            self.assertLessEqual(len(options), 3, block)

    def test_release_mutations_require_separate_step_authorization(self):
        exact = (
            "Creating or switching branches, committing, pushing, deploying, releasing, "
            "or publishing requires explicit user authorization at that step."
        )
        for name in ("hotfix", "day-one-patch"):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn(exact, text)
                self.assertIn("approval for one step never authorizes another", text)
                self.assertIn("destructive operation", text)

        release = self.skill_text("team-release")
        self.assertIn("explicit user authorization", release)
        for operation in (
            "branch",
            "commit",
            "push",
            "deployment",
            "release",
            "publication",
            "destructive",
        ):
            self.assertIn(operation, release.lower())
        self.assertIn("approval for one step never authorizes another", release)

    def test_evaluators_and_security_audit_stay_diagnostic(self):
        for name in ("launch-checklist", "release-checklist", "security-audit"):
            text = self.skill_text(name).lower()
            with self.subTest(skill=name):
                self.assertIn("read-only", text)
                self.assertIn("separately authorized", text)
        security = self.skill_text("security-audit")
        self.assertIn("does not remediate", security)
        self.assertIn("prioritized findings", security)
        self.assertIn("evidence", security)

    def test_output_writes_use_complete_changeset_approval(self):
        for name in ("changelog", "patch-notes", "reverse-document", "localize", "onboard"):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("complete proposed changeset", text.lower())
                self.assertIn("before writing", text.lower())

    def test_skill_maintenance_has_native_safety_contracts(self):
        skill_test = self.skill_text("skill-test")
        self.assertIn("Validation is read-only and does not require approval", skill_test)
        self.assertIn(".agents/skills/", skill_test)
        self.assertIn("tools/codex_studio/validate.py", skill_test)

        improve = self.skill_text("skill-improve")
        for phrase in (
            "exact proposed edit set",
            "explicit approval before applying",
            "retest score does not regress",
            "restore the original skill",
        ):
            self.assertIn(phrase, improve)

    def test_skill_test_defers_only_staged_framework_modes(self):
        text = self.skill_text("skill-test")
        self.assertIn("Staged dependency: Codex Studio Testing Framework is not migrated yet", text)
        self.assertIn("Static mode remains available", text)
        self.assertIn("do not fall back to a legacy framework", text)

    def test_skill_maintenance_uses_only_native_paths(self):
        for name in ("skill-test", "skill-improve"):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn(".agents/skills/", text)
                self.assertNotIn(".codex/skills/", text)
                self.assertNotIn("CCGS", text)

    def test_native_agent_and_reference_dependencies_are_used(self):
        self.assertIn(".codex/agents/", self.skill_text("onboard"))
        for name in sorted(TEAM_ROSTERS):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("Codex custom-agent", text)
                self.assertIn(".codex/docs/", text)

    def test_decisions_are_one_question_per_turn(self):
        for name in sorted(NAMES):
            text = self.skill_text(name)
            with self.subTest(skill=name):
                self.assertIn("Ask one decision question per turn", text)
                self.assertIn("wait for the answer", text)


if __name__ == "__main__":
    unittest.main()
