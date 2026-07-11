# Delivery Skills Subsystem Report

## Scope

Converted exactly these 22 delivery workflows to native Codex skills:

`bug-report`, `bug-triage`, `code-review`, `create-epics`, `create-stories`,
`dev-story`, `estimate`, `milestone-review`, `playtest-report`, `qa-plan`,
`regression-suite`, `retrospective`, `smoke-check`, `soak-test`, `sprint-plan`,
`sprint-status`, `story-done`, `story-readiness`, `test-evidence-review`,
`test-flakiness`, `test-helpers`, and `test-setup`.

No validator change was required.

## RED Evidence

Initial command:

```text
python3 -m unittest tests.studio.test_delivery_skills -v
Ran 10 tests
FAILED (failures=34)
```

The failures covered legacy metadata/model declarations, Claude interaction
primitives, missing implementation preflight behavior, incomplete completion
gates, writable diagnostic workflows, story regeneration, write-boundary gaps,
and non-sequential decisions.

The writing-skills discovery audit then added a trigger-description contract:

```text
python3 -m unittest \
  tests.studio.test_delivery_skills.DeliverySkillTests.test_descriptions_are_trigger_oriented -v
Ran 1 test
FAILED (failures=22)
```

Every legacy description failed because it summarized a workflow rather than
starting with an invocation condition.

## GREEN Evidence

Focused delivery suite:

```text
python3 -m unittest tests.studio.test_delivery_skills -v
Ran 11 tests in 0.015s
OK
```

Complete studio suite:

```text
python3 -m unittest discover -s tests/studio -v
Ran 36 tests in 0.148s
OK
```

Plan-mandated forbidden-pattern search:

```text
forbidden-pattern search: clean (rg returned no matches)
```

The search covered `AskUserQuestion`, `TodoWrite`, `Task tool`,
`subagent_type`, `.Codex/`, `.claude/`, Claude model metadata, and
`allowed-tools:` across all 22 skills.

Additional structural checks:

```text
exact skill inventory: 22/22
native frontmatter: 22/22 use name + trigger description only
legacy and unsupported syntax scan: clean
whitespace check: clean
```

All concrete `.codex/docs/*.md` references resolve.

## Review Remediation RED Evidence

The delivery review identified semantic loopholes not covered by the first
contract suite. Tests were added before remediation for preflight immutability,
strict evidence attribution, complete planning changesets, traceability,
canonical evidence paths, native cross-subsystem handoffs, generated template
syntax, and the in-scope minor findings.

```text
python3 -m unittest tests.studio.test_delivery_skills -v
Ran 19 tests in 0.020s
FAILED (failures=18)
```

The failures reproduced every Critical and Important review finding plus the
requested minor fixes. The existing native metadata and baseline delivery
contracts remained green during RED.

## Review Remediation GREEN Evidence

Focused delivery suite after remediation:

```text
python3 -m unittest tests.studio.test_delivery_skills -v
Ran 19 tests in 0.016s
OK
```

Complete studio suite after remediation:

```text
python3 -m unittest discover -s tests/studio -v
Ran 44 tests in 0.151s
OK
```

The plan-mandated forbidden-pattern search again returned no matches.

## Behavioral Audit

- `$dev-story` renders one complete `## Implementation Preflight`, replaces
  runtime placeholders, obtains one story-boundary approval, and does not ask
  again per listed file.
- Every prerequisite, manifest, and dependency decision before that preflight
  is read-only. `$dev-story` never marks another story Complete and routes that
  transition through `$story-done`.
- `$dev-story` pauses on scope expansion, an unlisted path, design ambiguity,
  missing architectural decisions, or ADR conflict.
- `$story-done` cannot mark Complete with an unverified criterion, failing
  required test, missing required evidence, incomplete sign-off, or unresolved
  coverage gap.
- `$story-done` accepts only the exact required path and evidence type, with
  story/criterion attribution, required schema, freshness, and a passing
  verdict. Mention-only, nearby-file, assumed-performance, and broad smoke-report
  shortcuts are rejected.
- `$code-review`, `$test-evidence-review`, `$story-readiness`, and `$estimate`
  remain read-only; fixes require a separately authorized changeset.
- `$create-stories` preserves older stories and does not regenerate them merely
  to add newer optional metadata.
- Missing registry traceability or an active TR-ID blocks generated stories and
  prevents `$story-readiness` from returning READY.
- Planning/report workflows enumerate complete proposed changesets before
  writing. `$test-setup` and `$test-helpers` use one full-file-list preflight.
- Epic/story indexes, sprint review-mode and QA revisions, and retrospective
  archive/rename operations are included in their respective complete approvals.
- Manual evidence uses the canonical `production/qa/evidence/` root.
- `$regression-suite` shows exact proposed registry entries before approval.
- All 22 skills ask one decision question per turn, use `request_user_input`
  when available, and avoid Claude widget/delegation syntax.
- Existing severity, status, risk, confidence, ownership, PASS/FAIL, readiness,
  and evidence schemas remain in their owning workflows.

## Changed Files

- `.agents/skills/bug-report/SKILL.md`
- `.agents/skills/bug-triage/SKILL.md`
- `.agents/skills/code-review/SKILL.md`
- `.agents/skills/create-epics/SKILL.md`
- `.agents/skills/create-stories/SKILL.md`
- `.agents/skills/dev-story/SKILL.md`
- `.agents/skills/estimate/SKILL.md`
- `.agents/skills/milestone-review/SKILL.md`
- `.agents/skills/playtest-report/SKILL.md`
- `.agents/skills/qa-plan/SKILL.md`
- `.agents/skills/regression-suite/SKILL.md`
- `.agents/skills/retrospective/SKILL.md`
- `.agents/skills/smoke-check/SKILL.md`
- `.agents/skills/soak-test/SKILL.md`
- `.agents/skills/sprint-plan/SKILL.md`
- `.agents/skills/sprint-status/SKILL.md`
- `.agents/skills/story-done/SKILL.md`
- `.agents/skills/story-readiness/SKILL.md`
- `.agents/skills/test-evidence-review/SKILL.md`
- `.agents/skills/test-flakiness/SKILL.md`
- `.agents/skills/test-helpers/SKILL.md`
- `.agents/skills/test-setup/SKILL.md`
- `tests/studio/test_delivery_skills.py`
- `.superpowers/sdd/delivery-subsystem-report.md`

## Self-Review and Concerns

- Scoped review found no unrelated validator, design-skill, documentation,
  operations/team, hook, or engine-pack changes in this subsystem.
- `$setup-engine`, `$team-qa`, `$hotfix`, and `$skill-test` belong to later or
  parallel migration subsystems and were intentionally not modified here. Every
  delivery handoff now validates the target skill's native readiness first. If
  a target is absent or non-native, the workflow reports it as a staged
  dependency and stops or defers safely instead of invoking legacy content.
- Pressure behavior is represented by deterministic contract tests rather than
  live agent samples, matching the approved delivery plan and keeping this
  bounded subsystem reproducible.

Verdict: **READY FOR REVIEW**.
