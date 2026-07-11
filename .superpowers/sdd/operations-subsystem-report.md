# Operations and Team Skills Subsystem Report

## Scope

Converted exactly these 21 skills:

- `.agents/skills/changelog/SKILL.md`
- `.agents/skills/day-one-patch/SKILL.md`
- `.agents/skills/hotfix/SKILL.md`
- `.agents/skills/launch-checklist/SKILL.md`
- `.agents/skills/localize/SKILL.md`
- `.agents/skills/onboard/SKILL.md`
- `.agents/skills/patch-notes/SKILL.md`
- `.agents/skills/release-checklist/SKILL.md`
- `.agents/skills/reverse-document/SKILL.md`
- `.agents/skills/security-audit/SKILL.md`
- `.agents/skills/skill-improve/SKILL.md`
- `.agents/skills/skill-test/SKILL.md`
- `.agents/skills/team-audio/SKILL.md`
- `.agents/skills/team-combat/SKILL.md`
- `.agents/skills/team-level/SKILL.md`
- `.agents/skills/team-live-ops/SKILL.md`
- `.agents/skills/team-narrative/SKILL.md`
- `.agents/skills/team-polish/SKILL.md`
- `.agents/skills/team-qa/SKILL.md`
- `.agents/skills/team-release/SKILL.md`
- `.agents/skills/team-ui/SKILL.md`

Focused contract coverage is in `tests/studio/test_operations_skills.py`.

## TDD Evidence

### RED

- Initial focused run: 12 tests, 85 expected assertion failures. The failures showed non-native frontmatter and interaction/delegation primitives, legacy paths, missing bounded delegation language, missing exact roster sections, and missing authorization boundaries.
- Follow-up staged-dependency test: 13 tests, two expected failures (missing subsystem report and missing native-framework deferral language).
- Pre-report full studio run: 61 tests, one expected failure for this report only; all behavioral assertions passed.

### GREEN

- Focused command: `python3 -m unittest tests.studio.test_operations_skills -v`
- Full command: `python3 -m unittest discover -s tests/studio -v`
- Final results are recorded below after the report itself entered the tested artifact set.

## Exact Team Roster Audit

The focused test parses both each explicit `## Team Roster` section and every configured custom-agent role mentioned anywhere in the skill. Each skill has no extra or missing role.

| Skill | Exact roster |
|---|---|
| team-audio | audio-director, sound-designer, technical-artist, gameplay-programmer |
| team-combat | game-designer, gameplay-programmer, ai-programmer, technical-artist, sound-designer, qa-tester |
| team-level | level-designer, narrative-director, world-builder, art-director, systems-designer, qa-tester |
| team-live-ops | live-ops-designer, economy-designer, analytics-engineer, community-manager, writer, narrative-director |
| team-narrative | narrative-director, writer, world-builder, level-designer |
| team-polish | performance-analyst, technical-artist, sound-designer, qa-tester |
| team-qa | qa-lead, qa-tester |
| team-release | release-manager, qa-lead, devops-engineer, producer |
| team-ui | ux-designer, art-director, ui-programmer, accessibility-specialist, qa-tester |

Every team skill contains the same bounded delegation contract: independent tasks only, exact returned artifact/evidence, no recursive fan-out at `agents.max_depth = 1`, parent synthesis, no child commits/publication/scope expansion, draft/read-only parallel work, and one parent-presented complete changeset approval.

## Authorization Audit

- `hotfix` and `day-one-patch` contain the required exact release-safety rule. Branch changes, commits, pushes, deployments, releases, publication, and destructive work are independently authorized at the step where they occur.
- `team-release` keeps its four-role roster draft-only. The parent presents the exact action, evidence, and rollback immediately before separately authorizing each branch, commit, push, tag, staging deploy, production deploy, release, or publication operation.
- `launch-checklist` and `release-checklist` are read-only evaluators.
- `security-audit` is diagnostic, produces prioritized evidence, and does not remediate. Fixes are a separately authorized changeset.
- Changelog, patch-note, onboarding, reverse-documentation, and localization writes use one complete proposed changeset, not per-file approvals.
- `skill-test` validation is read-only and approval-free. Extended modes defer cleanly until the Codex Studio Testing Framework migration exists and never fall back to a legacy framework.
- `skill-improve` shows an exact edit set, requires approval, preserves the original, and restores it without destructive Git if the retest score regresses.

## Native Dependency and Terminology Audit

- Skill root: `.agents/skills/`
- Agent profiles: `.codex/agents/`
- Review configuration: `.codex/studio.toml`
- Studio references: `.codex/docs/`
- Native validator: `tools/codex_studio/validate.py`
- All literal native document and skill dependencies resolve. The future Codex Studio Testing Framework is guarded as a staged dependency.
- The required forbidden-pattern scan is clean.

## Output-Schema Preservation

Existing checklist fields, report tables, severity/verdict vocabularies, output paths, and next-step contracts remain in their originating skills. The migration changes runtime terminology, delegation ownership, and mutation gates without replacing those domain outputs.

## Self-Review and Concerns

- Scoped inventory: 21/21 skills, one focused test file, and this report only.
- Exact roster audit: 9/9.
- No child agent is authorized to commit, publish, deploy, release, or expand scope.
- `Codex Studio Testing Framework/` is intentionally a guarded staged dependency until the later documentation/cleanup subsystem migrates it; static skill validation already works natively.
- No push, merge, deployment, release, or publication was performed.

## Final Verification

- Focused operations suite: 14 tests passed.
- Complete studio suite: 62 tests passed.
- Forbidden-pattern scan: clean (no matches).
- Literal native dependencies: 21/21 skills resolved; guarded future framework excluded by its explicit staged-dependency gate.
- Exact roster audit: 9/9 rosters, with no extra or missing configured role anywhere in each team skill.
- Whitespace and scoped-diff review: clean across the 23 scoped files before commit.
