# Skill Test Spec: $test-flakiness

## Codex Runtime Contract

- Runtime skill: `.agents/skills/test-flakiness/SKILL.md`
- Runtime name: `test-flakiness`
- Runtime trigger description: `"Use when CI history or repeated runs show intermittent, non-deterministic, timing-sensitive, or suspected flaky tests."`
- Native invocation: `$test-flakiness`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$test-flakiness` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: NO FLAKINESS, SUSPECT TESTS FOUND, CONFIRMED FLAKY
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (what to do after flakiness findings)

---

## Director Gate Checks

None. Flakiness detection is an advisory quality skill for the QA lead; no gates
are invoked.

---

## Test Cases

### Case 1: Happy Path — Clean test history, no flakiness

**Fixture:**
- `production/qa/test-history/` contains logs for 10 test runs
- All tests pass consistently across all 10 runs (100% pass rate per test)
- No test has a failure pattern

**Input:** `$test-flakiness`

**Expected behavior:**
1. Skill reads test history logs from `production/qa/test-history/`
2. Skill computes per-test pass rate across 10 runs
3. All tests pass all 10 runs — no inconsistency detected
4. Verdict is NO FLAKINESS

**Assertions:**
- [ ] Skill reads test history logs when available
- [ ] Per-test pass rate is computed across all available runs
- [ ] Verdict is NO FLAKINESS when all tests pass consistently
- [ ] No files are written

---

### Case 2: Suspect Tests Found — Test fails intermittently in history

**Fixture:**
- `production/qa/test-history/` contains logs for 10 test runs
- `test_combat_damage_applies_crit_multiplier` passes 7 times, fails 3 times
- Failure messages differ (sometimes timeout, sometimes wrong value)

**Input:** `$test-flakiness`

**Expected behavior:**
1. Skill reads test history logs — computes pass rates
2. `test_combat_damage_applies_crit_multiplier` has 70% pass rate (threshold: 95%)
3. Skill flags it as SUSPECT with pass rate (7/10) and failure pattern noted
4. Verdict is SUSPECT TESTS FOUND
5. Skill recommends investigating the test for timing or state dependencies

**Assertions:**
- [ ] Tests below the pass-rate threshold are flagged by name
- [ ] Pass rate (fraction and percentage) is shown for each suspect test
- [ ] Failure pattern (e.g., inconsistent error messages) is noted if detectable
- [ ] Verdict is SUSPECT TESTS FOUND
- [ ] Skill recommends investigation steps

---

### Case 3: Source Pattern — Random number used without seed

**Fixture:**
- No test history logs exist
- `tests/unit/loot/loot_drop_test.gd` contains:
  ```gdscript
  var roll = randf()  # unseeded random — non-deterministic
  assert_gt(roll, 0.5, "Loot should drop above 50%")
  ```

**Input:** `$test-flakiness`

**Expected behavior:**
1. Skill finds no test history logs
2. Skill falls back to source code analysis
3. Skill detects `randf()` call without a preceding `seed()` call
4. Skill flags the test as FLAKINESS RISK (source pattern, not confirmed)
5. Verdict is SUSPECT TESTS FOUND (pattern detected, not confirmed by history)
6. Skill recommends seeding random before the call or mocking the random function

**Assertions:**
- [ ] Source code analysis is used as fallback when no history logs exist
- [ ] Unseeded random number usage is detected as a flakiness risk
- [ ] Verdict is SUSPECT TESTS FOUND (not CONFIRMED FLAKY — no history to confirm)
- [ ] Remediation recommends seeding or mocking

---

### Case 4: No Test History — Source-only analysis with common patterns

**Fixture:**
- `production/qa/test-history/` does not exist
- `tests/` contains 15 test files
- Scan finds 2 tests using `OS.get_ticks_msec()` for timing assertions
- No other flakiness patterns found

**Input:** `$test-flakiness`

**Expected behavior:**
1. Skill checks for test history — not found
2. Skill notes: "No test history available — analyzing source code for flakiness patterns only"
3. Skill scans all test files for known patterns: unseeded random, real-time waits, system clock usage
4. Finds 2 tests using `OS.get_ticks_msec()` — flags as FLAKINESS RISK
5. Verdict is SUSPECT TESTS FOUND

**Assertions:**
- [ ] Skill notes clearly that source-only analysis is being performed (no history)
- [ ] Common flakiness patterns are scanned: random, time-based assertions, external I/O
- [ ] `OS.get_ticks_msec()` usage for assertions is flagged as a flakiness risk
- [ ] Verdict is SUSPECT TESTS FOUND when source patterns are found

---

### Case 5: Gate Compliance — No gate; flakiness report is advisory

**Fixture:**
- Test history shows 1 CONFIRMED FLAKY test (fails 6 out of 10 runs)
- `.codex/studio.toml` contains `full`

**Input:** `$test-flakiness`

**Expected behavior:**
1. Skill analyzes test history; identifies 1 confirmed flaky test
2. No director gate is invoked regardless of review mode
3. Verdict is CONFIRMED FLAKY
4. Skill presents findings and offers optional written report
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] No director gate is invoked in any review mode
- [ ] CONFIRMED FLAKY verdict requires history-based evidence (not just source patterns)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Flakiness report is advisory for qa-lead; skill does not auto-disable tests

---

## Protocol Compliance

- [ ] Reads test history logs when available; falls back to source analysis when not
- [ ] Notes clearly which analysis mode is being used (history vs. source-only)
- [ ] Flakiness threshold (e.g., 95% pass rate) is used for SUSPECT classification
- [ ] CONFIRMED FLAKY requires history evidence; SUSPECT covers source patterns only
- [ ] Does not disable or modify any test files
- [ ] No director gates are invoked
- [ ] Verdict is one of: NO FLAKINESS, SUSPECT TESTS FOUND, CONFIRMED FLAKY

---

## Coverage Notes

- The pass-rate threshold for SUSPECT classification (95% suggested above) is an
  implementation detail; the tests verify that intermittent failures are flagged,
  not the exact threshold value.
- Tests that fail due to environment issues (missing assets, wrong platform) are
  not flakiness — the skill distinguishes environment failures from non-determinism
  in the test itself; this distinction is not explicitly tested here.
