# Skill Test Spec: $launch-checklist

## Codex Runtime Contract

- Runtime skill: `.agents/skills/launch-checklist/SKILL.md`
- Runtime name: `launch-checklist`
- Runtime trigger description: `"Use when launch readiness needs a read-only cross-department go or no-go evaluation."`
- Native invocation: `$launch-checklist`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$launch-checklist` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: LAUNCH READY, LAUNCH BLOCKED, CONCERNS
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., `$team-release` or `$day-one-patch`)

---

## Director Gate Checks

None. `$launch-checklist` is a readiness audit utility. The full release pipeline
is managed by `$team-release`.

---

## Test Cases

### Case 1: Happy Path — All Checklist Items Verified, LAUNCH READY

**Fixture:**
- Legal docs present: EULA, privacy policy in `production/legal/`
- Platform certification: marked as submitted and approved in production notes
- Store page assets: screenshots, description, metadata all present in `production/store/`
- Build: version tag `v1.0.0` exists, reproducible build confirmed
- Crash reporting: configured in `technical-preferences.md`

**Input:** `$launch-checklist`

**Expected behavior:**
1. Skill checks all checklist categories
2. All items pass their verification checks
3. Skill produces checklist report with all items marked PASS
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Report written on approval; verdict is LAUNCH READY

**Assertions:**
- [ ] All checklist categories are checked (legal, platform, store, build, analytics, UX)
- [ ] All items appear in the report with PASS markers
- [ ] Verdict is LAUNCH READY
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 2: Platform Certification Not Submitted — LAUNCH BLOCKED

**Fixture:**
- All other checklist items pass
- Platform certification section: "not submitted" (no submission record found)

**Input:** `$launch-checklist`

**Expected behavior:**
1. Skill checks all items
2. Platform certification check fails: no submission record
3. Skill reports: "LAUNCH BLOCKED — Platform certification not submitted"
4. Specific platform(s) missing certification are named
5. Verdict is LAUNCH BLOCKED

**Assertions:**
- [ ] Verdict is LAUNCH BLOCKED (not CONCERNS)
- [ ] Platform certification is identified as the blocking item
- [ ] Missing platform names are specified
- [ ] All other passing items are still shown in the report

---

### Case 3: Manual Check Required — CONCERNS Verdict

**Fixture:**
- All critical checklist items pass
- First-run experience item: "MANUAL CHECK NEEDED — human must play the first 5
  minutes and verify tutorial completion flow"
- Store screenshots item: "MANUAL CHECK NEEDED — art team must verify screenshot
  quality matches current build"

**Input:** `$launch-checklist`

**Expected behavior:**
1. Skill checks all items
2. 2 items are flagged as requiring human verification
3. Skill reports: "CONCERNS — 2 items require manual verification before launch"
4. Both items are listed with instructions for what to manually verify
5. Verdict is CONCERNS (not LAUNCH BLOCKED, since these are advisory)

**Assertions:**
- [ ] Verdict is CONCERNS (not LAUNCH READY or LAUNCH BLOCKED)
- [ ] Both manual check items are listed with verification instructions
- [ ] Skill does not auto-block on MANUAL CHECK items

---

### Case 4: Previous Checklist Exists — Delta Comparison

**Fixture:**
- `production/launch/launch-checklist-2026-03-25.md` exists with previous results:
  - 2 items were BLOCKED (platform cert, crash reporting)
  - 1 item had a MANUAL CHECK
- New checklist: platform cert is now PASS, crash reporting is now PASS,
  manual check still open; 1 new item flagged (EULA last updated date)

**Input:** `$launch-checklist`

**Expected behavior:**
1. Skill finds the previous checklist and loads it for comparison
2. Skill produces the new checklist and compares:
   - Newly resolved: "Platform cert — was BLOCKED, now PASS"
   - Newly resolved: "Crash reporting — was BLOCKED, now PASS"
   - Still open: manual check (unchanged)
   - New issue: EULA last updated date (not in previous checklist)
3. Delta is shown prominently in the report
4. Verdict is CONCERNS (manual check + new EULA question)

**Assertions:**
- [ ] Delta section shows newly resolved items
- [ ] Delta section shows new issues (not present in previous checklist)
- [ ] Still-open items from the previous checklist are noted as persistent
- [ ] Verdict reflects the current state (not the previous state)

---

### Case 5: Director Gate Check — No gate; launch-checklist is an audit utility

**Fixture:**
- All checklist dependencies present

**Input:** `$launch-checklist`

**Expected behavior:**
1. Skill runs the full checklist and writes the report
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is LAUNCH READY, LAUNCH BLOCKED, or CONCERNS — no gate verdict

---

## Protocol Compliance

- [ ] Checks all required categories (legal, platform, store, build, analytics, UX)
- [ ] LAUNCH BLOCKED for hard failures (uncompleted certifications, missing legal docs)
- [ ] CONCERNS for advisory items requiring manual verification
- [ ] Compares against previous checklist when one exists
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is LAUNCH READY, LAUNCH BLOCKED, or CONCERNS

---

## Coverage Notes

- Region-specific compliance (GDPR data handling, COPPA for under-13 audiences)
  is checked but the specific requirements are not enumerated in test assertions.
- The store page completeness check (screenshots, description) relies on the
  presence of files in `production/store/`; it cannot verify visual quality.
- Build reproducibility check validates the presence of a version tag and build
  configuration but does not execute the build process.
