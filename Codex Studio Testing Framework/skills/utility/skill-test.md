# Skill Test Spec: $skill-test

## Codex Runtime Contract

- Runtime skill: `.agents/skills/skill-test/SKILL.md`
- Runtime name: `skill-test`
- Runtime trigger description: `"Use when Codex skill files need structural, behavioral, category, or coverage validation."`
- Native invocation: `$skill-test`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

## Skill Summary

`$skill-test` is read-only while validating. It provides `static`, `spec`,
`category`, and `audit` modes. Runtime validation targets `.agents/skills/`,
`tools/codex_studio/validate.py`, the catalog, behavioral specs, and category
rubrics. After findings are shown, result and catalog writes are optional and
must be one complete approved changeset.

## Static Assertions

- [ ] `static` performs exactly seven checks: native contract, phase structure,
  verdicts, changeset approval, next-step handoff, delegation boundary, and
  invocation contract.
- [ ] `spec` evaluates every assertion in all five cases plus protocol compliance.
- [ ] `category` reads metrics from `quality-rubric.md` rather than hardcoding them.
- [ ] `audit` compares exactly 73 runtime skills and exactly 49 runtime agents,
  including the three engine packs, against the catalog and spec tree.
- [ ] Validation performs no writes.
- [ ] Any saved result and catalog metadata are optionally offered together as
  one complete approved changeset.

## Test Cases

### Case 1: Happy Path — Static validation reports all seven checks

**Fixture:**
- `.agents/skills/brainstorm/SKILL.md` exists with native `name` and
  trigger-oriented `description` frontmatter.
- The body contains multiple phases, verdicts, a complete changeset boundary, a
  handoff, a direct-child delegation boundary, and `$brainstorm` usage.
- `tools/codex_studio/validate.py` reports no issue for the skill.

**Input:** `$skill-test static brainstorm`

**Expected behavior:**
1. Read the runtime skill and invoke the native validator.
2. Evaluate exactly seven documented checks.
3. Return a per-check table and `COMPLIANT`.
4. Write nothing and recommend the next validation action.

**Assertions:**
- [ ] Exactly seven check rows are present.
- [ ] Each row is `PASS` and cites observed evidence where useful.
- [ ] The verdict is `COMPLIANT`.
- [ ] No result or catalog file is written.

### Case 2: Blocked / Failure — Native contract violation is non-compliant

**Fixture:**
- `.agents/skills/example/SKILL.md` has a non-trigger description and directs
  writes without a complete proposed changeset.
- The validator reports both issues.

**Input:** `$skill-test static example`

**Expected behavior:**
1. Run all seven checks even after the first failure.
2. Mark Check 1 and Check 4 `FAIL` with the specific evidence.
3. Preserve passing and warning rows.
4. Return `NON-COMPLIANT` and recommend `$skill-improve example`.

**Assertions:**
- [ ] Both independent failures are reported.
- [ ] The skill is not edited during validation.
- [ ] The output does not claim a passing aggregate verdict.

### Case 3: Mode or Boundary Variant — Behavioral spec is evaluated completely

**Fixture:**
- `.agents/skills/gate-check/SKILL.md` exists.
- The catalog points to a gate-check spec containing five cases and protocol
  assertions.

**Input:** `$skill-test spec gate-check`

**Expected behavior:**
1. Resolve the spec through `catalog.yaml`.
2. Read the entire runtime skill and entire spec.
3. Evaluate each assertion as `PASS`, `PARTIAL`, or `FAIL` with a case verdict.
4. Present the report before offering any persistence.
5. Optionally offer the result file and catalog metadata as one complete approved
   changeset.

**Assertions:**
- [ ] All five cases and protocol compliance are evaluated.
- [ ] A failing assertion includes the exact runtime gap.
- [ ] Declining persistence leaves the filesystem unchanged.
- [ ] Approving persistence authorizes only the listed result and catalog paths.

### Case 4: Edge Case — Audit requires exact runtime inventory parity

**Fixture:**
- Runtime contains exactly 73 skill `SKILL.md` files.
- Runtime contains exactly 49 TOML agent profiles across core and engine packs.
- Catalog omits one engine-pack profile and contains one stale skill name.

**Input:** `$skill-test audit`

**Expected behavior:**
1. Enumerate the runtime rather than trusting catalog totals.
2. Compare runtime, catalog, and spec sets exactly.
3. Report both the missing engine agent and stale skill entry.
4. Return an incomplete/failing coverage verdict without inventing entries.

**Assertions:**
- [ ] Audit checks exactly 73 runtime skills.
- [ ] Audit checks exactly 49 runtime agents, including engine packs.
- [ ] Missing and extra set members are reported separately.
- [ ] Approximate thresholds such as “72+” or “49+” are not accepted.

### Case 5: Delegation or Gate — Category mode remains parent-owned

**Fixture:**
- `gate-check` has a catalog category and the rubric defines G1–G5.
- A direct child custom agent is used to evaluate independent rubric evidence.

**Input:** `$skill-test category gate-check`

**Expected behavior:**
1. Parent reads the category and rubric definitions.
2. Delegate a bounded, read-only evaluation to one direct child if useful.
3. Child returns evidence without further delegation or user interaction.
4. Parent agent synthesizes each metric and the overall verdict.
5. Parent optionally offers a catalog-only metadata update as a complete proposed
   changeset after showing findings.

**Assertions:**
- [ ] Every rubric metric is evaluated from the file.
- [ ] Maximum delegation depth is 1.
- [ ] The parent agent synthesizes and presents the result.
- [ ] Catalog writes remain optional and separately approved.

## Protocol Compliance

- [ ] Static mode runs exactly seven checks.
- [ ] Spec mode evaluates five cases plus protocol assertions.
- [ ] Audit uses exact 73/49 runtime inventory equality.
- [ ] No validation mode writes files as a side effect.
- [ ] Persistence optionally offers one complete approved changeset for result
  and/or catalog paths after findings are presented.
- [ ] Failures recommend `$skill-improve` with the affected name.

## Coverage Notes

- Static validation delegates parsing details to the repository validator; this
  spec tests orchestration and reporting rather than duplicating parser fixtures.
- Saved-result file naming is tested through the approved changeset description,
  not by writing a live result during validation.
