# Skill Test Spec: $regression-suite

## Codex Runtime Contract

- Runtime skill: `.agents/skills/regression-suite/SKILL.md`
- Runtime name: `regression-suite`
- Runtime trigger description: `"Use when bug fixes, critical paths, or release gates need regression coverage mapping and drift detection."`
- Native invocation: `$regression-suite`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$regression-suite` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: FULL COVERAGE, GAPS FOUND, CRITICAL GAPS
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., `$test-setup` if framework missing, `$qa-plan` if plan missing)

---

## Director Gate Checks

None. `$regression-suite` is a QA analysis utility. No director gates apply.

---

## Test Cases

### Case 1: Full Coverage — All ACs in sprint have corresponding tests

**Fixture:**
- `production/sprints/sprint-004.md` lists 3 stories with 2 ACs each (6 total)
- `tests/unit/` and `tests/integration/` contain test files that match all 6 ACs
  (by system name and scenario description)

**Input:** `$regression-suite sprint-004`

**Expected behavior:**
1. Skill reads all 6 ACs from sprint-004 stories
2. Skill scans test files and matches each AC to at least one test assertion
3. All 6 ACs have coverage
4. Skill produces coverage report: "6/6 ACs covered"
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. File is written on approval; verdict is FULL COVERAGE

**Assertions:**
- [ ] All 6 ACs appear in the coverage report
- [ ] Each AC is marked as covered with the matching test file referenced
- [ ] Verdict is FULL COVERAGE
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 2: Gaps Found — 3 ACs have no tests

**Fixture:**
- Sprint has 5 stories with 8 total ACs
- Tests exist for 5 of the 8 ACs; 3 ACs have no corresponding test file or assertion

**Input:** `$regression-suite`

**Expected behavior:**
1. Skill reads all 8 ACs
2. Skill scans tests — 5 matched, 3 unmatched
3. Coverage report lists the 3 untested ACs by story and AC text
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Report is written; verdict is GAPS FOUND

**Assertions:**
- [ ] The 3 untested ACs are listed by name in the report
- [ ] Matched ACs are also shown (not only the gaps)
- [ ] Verdict is GAPS FOUND (not FULL COVERAGE)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 3: Critical AC Untested — CRITICAL GAPS verdict, flagged prominently

**Fixture:**
- Sprint has 4 stories; one story is Priority: Critical with 2 ACs
- One of the critical-priority ACs has no test

**Input:** `$regression-suite`

**Expected behavior:**
1. Skill reads all stories and ACs, noting which stories are critical priority
2. Skill scans tests — the critical AC has no match
3. Report prominently flags: "CRITICAL GAP: [AC text] — no test found (Critical priority story)"
4. Skill recommends blocking story completion until test is added
5. Verdict is CRITICAL GAPS

**Assertions:**
- [ ] Verdict is CRITICAL GAPS (not GAPS FOUND)
- [ ] Critical priority AC is flagged more prominently than normal gaps
- [ ] Recommendation to block story completion is included
- [ ] Non-critical gaps (if any) are also listed

---

### Case 4: Orphan Tests — Test file has no matching AC

**Fixture:**
- `tests/unit/save_system_test.gd` exists with assertions for scenarios
  not present in any current story's AC list
- Current sprint stories do not reference save system

**Input:** `$regression-suite`

**Expected behavior:**
1. Skill scans tests and cross-references ACs
2. `save_system_test.gd` assertions do not match any current AC
3. Test file is flagged as ORPHAN TEST in the coverage report
4. Report notes: "Orphan tests may belong to a past or future sprint, or AC was renamed"
5. Verdict is FULL COVERAGE or GAPS FOUND depending on overall AC coverage
   (orphan tests do not affect verdict, they are advisory)

**Assertions:**
- [ ] Orphan test is flagged in the report
- [ ] Orphan flag includes the filename and suggestion (past sprint / renamed AC)
- [ ] Orphan tests do not cause a GAPS FOUND verdict on their own
- [ ] Overall verdict reflects AC coverage only

---

### Case 5: Director Gate Check — No gate; regression-suite is a QA utility

**Fixture:**
- Sprint with stories and test files

**Input:** `$regression-suite`

**Expected behavior:**
1. Skill produces coverage report and writes it
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is FULL COVERAGE, GAPS FOUND, or CRITICAL GAPS — no gate verdict

---

## Protocol Compliance

- [ ] Reads story ACs from sprint files before scanning tests
- [ ] Matches ACs to tests by system name and scenario (not file name alone)
- [ ] Flags critical-priority untested ACs as CRITICAL GAPS
- [ ] Flags orphan tests (exist in tests/ but no AC matches)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is FULL COVERAGE, GAPS FOUND, or CRITICAL GAPS

---

## Coverage Notes

- The heuristic for matching an AC to a test (by system name + scenario keywords)
  is approximate; exact matching logic is defined in the skill body.
- Integration test coverage is mapped the same way as unit test coverage; no
  distinction in verdicts is made between the two.
- This skill does not run the tests — it maps AC text to test assertions. Test
  execution is handled by the CI pipeline.
