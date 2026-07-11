# Skill Test Spec: $test-evidence-review

## Codex Runtime Contract

- Runtime skill: `.agents/skills/test-evidence-review/SKILL.md`
- Runtime name: `test-evidence-review`
- Runtime trigger description: `"Use when tests or manual evidence need quality, assertion, edge-case, naming, sign-off, or completeness review before QA closure."`
- Native invocation: `$test-evidence-review`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$test-evidence-review` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: PASS, WARNINGS, FAIL
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (what to do after findings are reviewed)

---

## Director Gate Checks

None. Test evidence review is an advisory quality skill; QL-TEST-COVERAGE gate
is a separate skill invocation and is NOT triggered here.

---

## Test Cases

### Case 1: Happy Path — Tests follow all standards

**Fixture:**
- `tests/unit/combat/health_system_take_damage_test.gd` exists with:
  - Naming: `test_health_system_take_damage_reduces_health()` (follows `test_[system]_[scenario]_[expected]`)
  - Arrange/Act/Assert structure present
  - No `sleep()`, `await` with time values, or random seeds
  - No calls to external APIs or file I/O
  - No inline magic numbers (uses constants from `tests/unit/combat/fixtures/`)

**Input:** `$test-evidence-review tests/unit/combat/`

**Expected behavior:**
1. Skill reads test standards from `coding-standards.md`
2. Skill reads the test file; checks all 5 standards
3. All checks pass: naming, structure, determinism, isolation, no hardcoded data
4. Verdict is PASS

**Assertions:**
- [ ] Each of the 5 test standards is checked and reported
- [ ] All checks show PASS when standards are met
- [ ] Verdict is PASS
- [ ] No files are written

---

### Case 2: Fail — Timing dependency detected

**Fixture:**
- `tests/unit/ui/hud_update_test.gd` contains:
  ```gdscript
  await get_tree().create_timer(1.0).timeout
  assert_eq(label.text, "Ready")
  ```
- Real-time wait of 1 second used instead of mock or signal-based assertion

**Input:** `$test-evidence-review tests/unit/ui/hud_update_test.gd`

**Expected behavior:**
1. Skill reads the test file
2. Skill detects real-time wait (`create_timer(1.0)`) — non-deterministic timing dependency
3. Skill flags this as a FAIL-level finding
4. Verdict is FAIL
5. Skill recommends replacing the timer with a signal-based assertion or mock

**Assertions:**
- [ ] Real-time wait usage is detected as a non-deterministic timing dependency
- [ ] Finding is classified as FAIL severity (blocking — violates determinism standard)
- [ ] Verdict is FAIL
- [ ] Remediation suggestion references signal-based or mock-based approach
- [ ] Skill does not edit the test file

---

### Case 3: Fail — Test calls external API directly

**Fixture:**
- `tests/unit/networking/auth_test.gd` contains:
  ```gdscript
  var result = HTTPRequest.new().request("https://api.example.com/auth")
  ```
- Direct HTTP call to external API without a mock

**Input:** `$test-evidence-review tests/unit/networking/auth_test.gd`

**Expected behavior:**
1. Skill reads the test file
2. Skill detects direct external API call (HTTPRequest to live URL)
3. Skill flags this as a FAIL-level finding — violates isolation standard
4. Verdict is FAIL
5. Skill recommends injecting a mock HTTP client

**Assertions:**
- [ ] Direct external API call is detected and flagged
- [ ] Finding is classified as FAIL severity (violates isolation standard)
- [ ] Verdict is FAIL
- [ ] Remediation references dependency injection with a mock HTTP client
- [ ] Skill does not modify the test file

---

### Case 4: Edge Case — No Test Files Found

**Fixture:**
- User calls `$test-evidence-review tests/unit/audio/`
- `tests/unit/audio/` directory does not exist

**Input:** `$test-evidence-review tests/unit/audio/`

**Expected behavior:**
1. Skill attempts to read files in `tests/unit/audio/` — not found
2. Skill outputs: "No test files found at `tests/unit/audio/` — run `$test-setup` to scaffold test directories"
3. No verdict is emitted

**Assertions:**
- [ ] Skill does not crash when path does not exist
- [ ] Output names the attempted path in the message
- [ ] Output recommends `$test-setup` for scaffolding
- [ ] No verdict is emitted when there is nothing to review

---

### Case 5: Gate Compliance — No gate; QL-TEST-COVERAGE is a separate skill

**Fixture:**
- Test file has 1 WARNINGS-level finding (magic number in a non-boundary test)
- `.codex/studio.toml` contains `full`

**Input:** `$test-evidence-review tests/unit/combat/`

**Expected behavior:**
1. Skill reviews tests; finds 1 WARNINGS-level finding
2. No director gate is invoked (QL-TEST-COVERAGE is invoked separately, not here)
3. Verdict is WARNINGS
4. Output notes: "For full test coverage gate, run `$gate-check` which invokes QL-TEST-COVERAGE"
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] No director gate is invoked in any review mode
- [ ] Output distinguishes this skill from the QL-TEST-COVERAGE gate invocation
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is WARNINGS for advisory-level test quality issues

---

## Protocol Compliance

- [ ] Reads `coding-standards.md` test standards before reviewing test files
- [ ] Checks naming, Arrange/Act/Assert structure, determinism, isolation, no hardcoded data
- [ ] Does not edit any test files (read-only skill)
- [ ] No director gates are invoked
- [ ] Verdict is one of: PASS, WARNINGS, FAIL

---

## Coverage Notes

- Batch review of all test files in `tests/` is not explicitly tested; behavior
  is assumed to apply the same checks file by file and aggregate the verdict.
- The QL-TEST-COVERAGE director gate (which checks test coverage percentage) is
  a separate concern and is intentionally NOT invoked by this skill.
