# Skill Test Spec: $release-checklist

## Codex Runtime Contract

- Runtime skill: `.agents/skills/release-checklist/SKILL.md`
- Runtime name: `release-checklist`
- Runtime trigger description: `"Use when build, certification, store, content, and launch readiness need a read-only pre-release evaluation."`
- Native invocation: `$release-checklist`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$release-checklist` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

Validation is read-only. If the workflow writes, the parent first presents one
complete proposed changeset containing every target path and material edit; any
new path or scope expansion requires fresh approval. If it delegates, direct
children return scoped evidence and the parent synthesizes the result.

---

## Static Assertions (Structural)

Verified automatically by `$skill-test static` — no fixture needed.

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings
- [ ] Contains verdict keywords: RELEASE READY, RELEASE BLOCKED, CONCERNS
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., `$launch-checklist` for external or `$gate-check` for phase)

---

## Director Gate Checks

None. `$release-checklist` is an internal audit utility. Formal phase advancement
is managed by `$gate-check`.

---

## Test Cases

### Case 1: Happy Path — All Sprint Stories Complete, QA Passed, RELEASE READY

**Fixture:**
- `production/sprints/sprint-008.md` — all stories are `Status: Done`
- No open bugs with severity HIGH or CRITICAL in `production/bugs/`
- `production/qa/qa-plan-sprint-008.md` has QA sign-off annotation
- Changelog entry for this version exists
- `production/stage.txt` contains `Polish`

**Input:** `$release-checklist`

**Expected behavior:**
1. Skill reads sprint-008: all stories Done
2. Skill reads bugs: no HIGH or CRITICAL open bugs
3. Skill confirms QA plan has sign-off
4. Skill confirms changelog entry exists
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
   `production/releases/release-checklist-2026-04-06.md`?"
6. Report written; verdict is RELEASE READY

**Assertions:**
- [ ] All 4 check categories are evaluated (stories, bugs, QA, changelog)
- [ ] All items appear with PASS markers
- [ ] Verdict is RELEASE READY
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 2: Open HIGH Severity Bugs — RELEASE BLOCKED

**Fixture:**
- All sprint stories are Done
- `production/bugs/` contains 2 open bugs with severity HIGH

**Input:** `$release-checklist`

**Expected behavior:**
1. Skill reads sprint — stories complete
2. Skill reads bugs — 2 HIGH severity bugs open
3. Skill reports: "RELEASE BLOCKED — 2 open HIGH severity bugs must be resolved"
4. Both bug filenames are listed in the report
5. Verdict is RELEASE BLOCKED

**Assertions:**
- [ ] Verdict is RELEASE BLOCKED (not CONCERNS)
- [ ] Both bug filenames are listed explicitly
- [ ] Skill makes clear HIGH severity bugs are blocking (not advisory)

---

### Case 3: Changelog Not Generated — CONCERNS

**Fixture:**
- All stories Done, no HIGH/CRITICAL bugs
- No changelog entry found for the current version/sprint

**Input:** `$release-checklist`

**Expected behavior:**
1. Skill checks all items
2. Changelog check fails: no changelog entry found
3. Skill reports: "CONCERNS — Changelog not generated for this release"
4. Skill suggests running `$changelog` to generate it
5. Verdict is CONCERNS (advisory — not a hard block)

**Assertions:**
- [ ] Verdict is CONCERNS (not RELEASE BLOCKED — changelog is advisory)
- [ ] `$changelog` is suggested as the remediation
- [ ] Other passing checks are shown in the report
- [ ] Missing changelog is described as advisory, not blocking

---

### Case 4: Previous Release Checklist Exists — Delta From Last Release

**Fixture:**
- `production/releases/release-checklist-2026-03-20.md` exists
- Previous: 1 story was incomplete, 1 HIGH bug open
- Current: all stories Done, HIGH bug resolved, but now 1 MEDIUM bug appeared

**Input:** `$release-checklist`

**Expected behavior:**
1. Skill finds the previous checklist and loads it
2. New checklist is generated and compared:
   - Newly resolved: "Story [X] — was open, now Done"
   - Newly resolved: "HIGH bug [filename] — was open, now closed"
   - New item: "1 MEDIUM bug appeared (advisory)"
3. Delta section shows all changes prominently
4. Verdict is CONCERNS (MEDIUM bug is advisory, not blocking)

**Assertions:**
- [ ] Delta section appears in the report with resolved and new items
- [ ] Newly resolved items from the previous checklist are noted
- [ ] New items not present in the previous checklist are highlighted
- [ ] Verdict reflects current state (not previous state)

---

### Case 5: Director Gate Check — No gate; release-checklist is an internal audit

**Fixture:**
- Active sprint with stories and bug reports

**Input:** `$release-checklist`

**Expected behavior:**
1. Skill runs the full checklist and writes the report
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is RELEASE READY, RELEASE BLOCKED, or CONCERNS — no gate verdict

---

## Protocol Compliance

- [ ] Checks sprint story completion status
- [ ] Checks open bug severity (CRITICAL/HIGH = BLOCKED; MEDIUM/LOW = CONCERNS)
- [ ] Checks QA plan sign-off status
- [ ] Checks changelog existence
- [ ] Compares against previous checklist when one exists
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is RELEASE READY, RELEASE BLOCKED, or CONCERNS

---

## Coverage Notes

- Build stability verification (no failed CI runs) is listed as a check category
  but relies on external CI system state; the skill notes this as a MANUAL CHECK
  if CI integration is not configured.
- CRITICAL bugs always result in RELEASE BLOCKED regardless of other items;
  this is equivalent to the HIGH severity case in Case 2.
- Stories with `Status: In Review` (not Done) are treated as incomplete
  and result in RELEASE BLOCKED; this edge case follows the same pattern
  as the HIGH bug case.
