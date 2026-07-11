# Skill Test Spec: $skill-improve

## Codex Runtime Contract

- Runtime skill: `.agents/skills/skill-improve/SKILL.md`
- Runtime name: `skill-improve`
- Runtime trigger description: `"Use when a Codex skill has validation failures or warnings that need an approved test-fix-retest cycle."`
- Native invocation: `$skill-improve`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$skill-improve` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: IMPROVED, NO CHANGE, REVERTED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., run `$skill-test spec` to validate behavioral compliance)

---

## Director Gate Checks

None. `$skill-improve` is a meta-utility skill. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — Skill With 2 Static Failures, Both Fixed, IMPROVED

**Fixture:**
- `.agents/skills/some-skill/SKILL.md` has 2 static failures:
  - The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
  - Check 5: no next-step handoff at the end

**Input:** `$skill-improve some-skill`

**Expected behavior:**
1. Skill runs `$skill-test static some-skill` — baseline: 5/7 checks pass
2. Skill diagnoses the 2 failing checks (4 and 5)
3. Skill proposes fixes:
   - The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
   - Add a next-step handoff section at the end
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Fixes applied; `$skill-test static some-skill` re-run — now 7/7 checks pass
6. Verdict is IMPROVED (5→7)

**Assertions:**
- [ ] Baseline score is established before any changes (5/7)
- [ ] Both failing checks are diagnosed and addressed in the proposed fix
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Re-test confirms improvement (7/7)
- [ ] Verdict is IMPROVED with before/after score shown

---

### Case 2: Fix Causes Regression — Score Comparison Shows Regression, REVERTED

**Fixture:**
- `.agents/skills/some-skill/SKILL.md` has 1 static failure (missing handoff)
- Proposed fix inadvertently removes the verdict keywords section
  (introducing a new failure)

**Input:** `$skill-improve some-skill`

**Expected behavior:**
1. Baseline: 6/7 checks pass (1 failure: missing handoff)
2. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
3. Fix is applied; re-test runs
4. Re-test result: 5/7 (fixed the handoff but broke verdict keywords)
5. Skill detects regression: score went DOWN
6. The parent shows regression evidence and obtains explicit revert approval in its own decision turn.
7. User confirms; changes are reverted; verdict is REVERTED

**Assertions:**
- [ ] Re-test score is compared to baseline before finalizing
- [ ] Regression is detected when score decreases
- [ ] User is asked to confirm revert (not automatic)
- [ ] File is reverted on user confirmation
- [ ] Verdict is REVERTED

---

### Case 3: Skill With Category Assignment — Baseline Captures Both Scores

**Fixture:**
- `.agents/skills/gate-check/SKILL.md` is a gate skill with 1 static failure
  and 2 category (G-criteria) failures
- `tests/skills/quality-rubric.md` has Gate Skills section

**Input:** `$skill-improve gate-check`

**Expected behavior:**
1. Skill runs both static and category tests for the baseline:
   - Static: 6/7 checks pass
   - Category: 3/5 G-criteria pass
2. Combined baseline: 9/12
3. Skill diagnoses all 3 failures and proposes fixes
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Fixes applied; both test types re-run
6. Re-test: static 7/7, category 5/5 = 12/12
7. Verdict is IMPROVED (9→12)

**Assertions:**
- [ ] Both static and category scores are captured in the baseline
- [ ] Combined score is used for comparison (not just one type)
- [ ] All 3 failures are addressed in the proposed fix
- [ ] Re-test confirms improvement in both score types
- [ ] Verdict is IMPROVED with combined before/after

---

### Case 4: Skill Already Perfect — No Improvements Needed

**Fixture:**
- `.agents/skills/brainstorm/SKILL.md` has no static failures
- Category score is also 5/5 (if applicable)

**Input:** `$skill-improve brainstorm`

**Expected behavior:**
1. Skill runs `$skill-test static brainstorm` — 7/7 checks pass
2. If category applies: 5/5 criteria pass
3. Skill outputs: "No improvements needed — brainstorm is fully compliant"
4. Skill exits without proposing any changes
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Verdict is NO CHANGE

**Assertions:**
- [ ] Skill exits immediately after confirming 0 failures
- [ ] "No improvements needed" message is shown
- [ ] No changes are proposed
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is NO CHANGE

---

### Case 5: Director Gate Check — No gate; skill-improve is a meta utility

**Fixture:**
- Skill with at least 1 static failure

**Input:** `$skill-improve some-skill`

**Expected behavior:**
1. Skill runs the test-fix-retest loop
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is IMPROVED, NO CHANGE, or REVERTED — no gate verdict

---

## Protocol Compliance

- [ ] Always establishes a baseline score before proposing any changes
- [ ] Shows before/after score comparison in the output
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Detects regressions by comparing re-test score to baseline
- [ ] Asks for user confirmation before reverting (not automatic)
- [ ] Ends with IMPROVED, NO CHANGE, or REVERTED verdict

---

## Coverage Notes

- The improvement loop is designed to run only one fix-retest cycle per
  invocation; running multiple iterations requires re-invoking `$skill-improve`.
- Behavioral compliance (spec-mode test results) is not included in the
  improvement loop — only structural (static) and category scores are automated.
- The case where the skill file cannot be read (permissions error or missing file)
  is not tested; this would result in an error before the baseline is established.
