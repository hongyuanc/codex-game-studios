# Skill Test Spec: $[skill-name]

## Codex Runtime Contract

- Runtime skill: `.agents/skills/[skill-name]/SKILL.md`
- Runtime name: `[exact name value]`
- Runtime trigger description: `[exact description value]`
- Native invocation: `$[skill-name]`
- Discovery contract: YAML frontmatter requires `name` and `description`.
- Structured decisions: `request_user_input` uses 1–3 questions with 2–3 options
  each; ask one decision per turn.
- Custom-agent delegation: direct child only; maximum delegation depth is 1.
  The child returns scoped evidence and the parent agent synthesizes the result.

## Skill Summary

[Inputs, outputs, boundary, and verdicts.]

## Static Assertions

- [ ] Runtime path, `name`, and trigger `description` are exact.
- [ ] Invocation uses `$skill-name` and missing arguments have defined behavior.
- [ ] The workflow has at least two phases and explicit verdicts.
- [ ] Writes occur only within one complete approved changeset.
- [ ] Delegation is direct-child only with parent synthesis.

## Test Cases

### Case 1: Happy Path — [brief name]

**Fixture:** [valid project state]
**Expected behavior:** [ordered behavior]
**Assertions:**
- [ ] [happy-path outcome]
- [ ] [evidence produced]

### Case 2: Blocked / Failure — [brief name]

**Fixture:** [missing or invalid prerequisite]
**Expected behavior:** [BLOCKED/FAIL and stop]
**Assertions:**
- [ ] Reports the exact blocker.
- [ ] Makes no unauthorized writes or downstream delegations.

### Case 3: Mode or Boundary Variant — [brief name]

**Fixture:** [review mode, engine pack, or scope boundary]
**Expected behavior:** [variant behavior]
**Assertions:**
- [ ] Applies the correct mode or boundary.
- [ ] Preserves the approved changeset.

### Case 4: Edge Case — [brief name]

**Fixture:** [unusual but valid state]
**Expected behavior:** [safe deterministic handling]
**Assertions:**
- [ ] Does not silently overwrite, guess, or expand scope.

### Case 5: Delegation or Gate — [brief name]

**Fixture:** [agent/gate context]
**Expected behavior:** [direct-child delegation and verdict handling]
**Assertions:**
- [ ] Maximum delegation depth is 1.
- [ ] Child returns scoped evidence and the parent agent synthesizes the result.
- [ ] Blocking verdicts prevent advancement.

## Protocol Compliance

- [ ] Uses native `$skill-name` invocation.
- [ ] Structured choices satisfy the 1–3 question and 2–3 option schema.
- [ ] Asks one decision per turn.
- [ ] Optional writes are one complete approved changeset.

## Coverage Notes

[Known gaps or live-test requirements.]
