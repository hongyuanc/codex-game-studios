# Skill Test Spec: $[skill-name]

## Skill summary

[Describe the skill's trigger, workflow, primary artifact, verdict format, and
pipeline stage.]

## Static assertions

Verified automatically by `$skill-test static`:

- [ ] Frontmatter has `name` and an accurate trigger `description`.
- [ ] The skill has at least two meaningful phase headings.
- [ ] Expected verdict keywords are present.
- [ ] Write-capable work documents a phase-gated preflight.
- [ ] The last phase provides an appropriate `$skill-name` handoff.

## Case 1: Happy path

**Fixture:** [List existing artifacts and relevant project state.]

**Input:** `$[skill-name] [arguments]`

**Expected behavior:**

1. Reads the required evidence before deciding.
2. Evaluates the stated acceptance criteria.
3. Produces the documented artifact or verdict.

**Assertions:**

- [ ] Reads [specific file] before producing output.
- [ ] Includes [expected verdict].
- [ ] Grounds findings in fixture evidence.
- [ ] If writes are required, presents one complete bounded changeset for approval.
- [ ] After approval, iterates inside that boundary without repetitive edit prompts.

## Case 2: Failure path

**Fixture:** [Describe the missing, invalid, or conflicting state.]

**Input:** `$[skill-name] [arguments]`

**Expected behavior:**

1. Detects the specific gap.
2. Returns `FAIL` or `BLOCKED` rather than inventing evidence.
3. Names the smallest remediation or next skill.

**Assertions:**

- [ ] Does not return a passing verdict for incomplete evidence.
- [ ] Names the missing or conflicting artifact.
- [ ] Does not expand scope to manufacture prerequisites.

## Case 3: Boundary change

**Fixture:** [Describe a valid approved phase with a newly discovered ambiguity,
ADR conflict, out-of-scope file, or scope expansion.]

**Input:** `$[skill-name] [arguments]`

**Assertions:**

- [ ] Pauses work and explains the evidence.
- [ ] Presents one decision at a time with 2-3 mutually exclusive options.
- [ ] Does not treat prior phase approval as authority for the expanded boundary.
- [ ] Keeps commits, pushes, releases, destructive operations, and publication gated.

## Protocol compliance

- [ ] Uses phase-gated autonomy.
- [ ] Separates material decisions from routine in-boundary execution.
- [ ] Uses `request_user_input` only for constrained choices: 1-3 questions per
  call and 2-3 mutually exclusive options per question.
- [ ] Uses one decision at a time unless questions are genuinely independent.
- [ ] Returns test, review, or inspection evidence.

## Coverage notes

[Document intentionally uncovered modes and why, including external services,
engine installations, or scenarios reserved for manual validation.]
