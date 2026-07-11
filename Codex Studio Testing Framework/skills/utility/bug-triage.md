# Skill Test Spec: $bug-triage

## Codex Runtime Contract

- Runtime skill: `.agents/skills/bug-triage/SKILL.md`
- Runtime name: `bug-triage`
- Runtime trigger description: `"Use when open game bugs need priority and severity review, sprint assignment, or systemic trend analysis."`
- Native invocation: `$bug-triage`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$bug-triage` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keyword: TRIAGED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., `$bug-report` to create new reports, `$hotfix` for critical bugs)

---

## Director Gate Checks

None. `$bug-triage` is a read-only advisory skill. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — 5 bugs of varying severity, sorted table produced

**Fixture:**
- `production/bugs/` contains 5 bug report files:
  - bug-2026-03-10-audio-crash.md (CRITICAL)
  - bug-2026-03-12-score-overflow.md (HIGH)
  - bug-2026-03-14-ui-overlap.md (MEDIUM)
  - bug-2026-03-15-typo-tutorial.md (LOW)
  - bug-2026-03-16-vfx-flicker.md (HIGH)

**Input:** `$bug-triage`

**Expected behavior:**
1. Skill reads all 5 bug report files
2. Skill extracts severity, title, system, and repro status from each
3. Skill produces a triage table sorted: CRITICAL first, then HIGH, MEDIUM, LOW
4. Within the same severity, bugs are ordered by date (oldest first)
5. Verdict is TRIAGED

**Assertions:**
- [ ] Triage table has exactly 5 rows
- [ ] CRITICAL bug appears before both HIGH bugs
- [ ] HIGH bugs appear before MEDIUM and LOW bugs
- [ ] Verdict is TRIAGED
- [ ] No files are written

---

### Case 2: No Bug Reports Found — Guidance to run $bug-report

**Fixture:**
- `production/bugs/` directory exists but is empty (or does not exist)

**Input:** `$bug-triage`

**Expected behavior:**
1. Skill scans `production/bugs/` and finds no reports
2. Skill outputs: "No open bug reports found in production/bugs/"
3. Skill suggests running `$bug-report` to create a bug report
4. No triage table is produced

**Assertions:**
- [ ] Output explicitly states no bugs were found
- [ ] `$bug-report` is suggested as the next step
- [ ] Skill does not error out — it handles empty directory gracefully
- [ ] Verdict is TRIAGED (with "no bugs found" context)

---

### Case 3: Bug Missing Reproduction Steps — Flagged as NEEDS REPRO INFO

**Fixture:**
- `production/bugs/` contains 3 bug reports; one has an empty "Repro Steps" section

**Input:** `$bug-triage`

**Expected behavior:**
1. Skill reads all 3 reports
2. Skill detects the report with no repro steps
3. That bug appears in the triage table with a `NEEDS REPRO INFO` tag
4. Other bugs are triaged normally
5. Verdict is TRIAGED

**Assertions:**
- [ ] `NEEDS REPRO INFO` tag appears next to the bug missing repro steps
- [ ] The flagged bug is still included in the table (not excluded)
- [ ] Other bugs are unaffected
- [ ] Verdict is TRIAGED

---

### Case 4: Possible Duplicate Bugs — Flagged in triage output

**Fixture:**
- `production/bugs/` contains 2 bug reports with similar titles:
  - bug-2026-03-18-player-fall-through-floor.md
  - bug-2026-03-20-player-clips-through-floor.md
  - Both affect the "Physics" system with identical severity

**Input:** `$bug-triage`

**Expected behavior:**
1. Skill reads both reports and detects similar title + same system + same severity
2. Both bugs are included in the triage table
3. Each is tagged with `POSSIBLE DUPLICATE` and cross-references the other report
4. No bugs are merged or deleted — flagging is advisory
5. Verdict is TRIAGED

**Assertions:**
- [ ] Both bugs appear in the table (not merged)
- [ ] Both are tagged `POSSIBLE DUPLICATE`
- [ ] Each cross-references the other (by filename or title)
- [ ] Verdict is TRIAGED

---

### Case 5: Director Gate Check — No gate; triage is advisory

**Fixture:**
- `production/bugs/` contains any number of reports

**Input:** `$bug-triage`

**Expected behavior:**
1. Skill produces the triage table
2. No director agents are spawned
3. No gate IDs appear in output
4. No write tool is called

**Assertions:**
- [ ] No director gate is invoked
- [ ] No write tool is called
- [ ] No gate skip messages appear
- [ ] Verdict is TRIAGED without any gate check

---

## Protocol Compliance

- [ ] Reads all files in `production/bugs/` before generating the table
- [ ] Sorts by severity (CRITICAL → HIGH → MEDIUM → LOW)
- [ ] Flags bugs missing repro steps
- [ ] Flags possible duplicates by title/system similarity
- [ ] Does not write any files
- [ ] Verdict is TRIAGED in all cases (even empty)

---

## Coverage Notes

- The case where a bug report is malformed (missing severity field entirely)
  is not fixture-tested; skill would flag it as `UNKNOWN SEVERITY` and sort it
  last in the table.
- Status transitions (marking bugs as resolved) are outside this skill's scope —
  bug-triage is read-only.
- The duplicate detection heuristic (title similarity + same system) is
  approximate; exact matching logic is defined in the skill body.
