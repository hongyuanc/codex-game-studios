# Skill Test Spec: $map-systems

## Codex Runtime Contract

- Runtime skill: `.agents/skills/map-systems/SKILL.md`
- Runtime name: `map-systems`
- Runtime trigger description: `Decompose an approved game concept into systems, dependencies, priorities, and design order.`
- Native invocation: `$map-systems`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---

## Skill Summary

`$map-systems` decomposes an approved concept, validates dependencies and scope,
then writes the canonical systems index and session-state record through one
approved initial changeset. Full-mode gates are sequential at their runtime
phases: TD-SYSTEM-BOUNDARY after dependency-map approval, PR-SCOPE after priority approval, the initial two-file changeset, then CD-SYSTEMS after the initial index write.

The parent presents one complete proposed changeset containing every target path
and material edit, then obtains approval before any write. Any post-write
creative-director change uses a separate exact revision changeset and approval
before modifying the index.

---

## Static Assertions (Structural)

- [ ] Runtime YAML frontmatter has only `name` and `description`, and both match the contract above.
- [ ] Has at least two phase headings and contains COMPLETE and BLOCKED verdicts.
- [ ] Uses only `design/gdd/systems-index.md` as the systems-index path.
- [ ] Documents TD-SYSTEM-BOUNDARY, PR-SCOPE, and CD-SYSTEMS in their sequential runtime order.
- [ ] Documents full, phase-gated, and solo behavior for all three optional gates.
- [ ] Lists `design/gdd/systems-index.md` and `production/session-state/active.md` in one approved initial changeset.
- [ ] Requires a separate approved revision changeset for post-write CD-SYSTEMS feedback.
- [ ] Ends with a `$design-system` handoff.

---

## Director Gate Checks

Full mode follows this order:

1. TD-SYSTEM-BOUNDARY after dependency-map approval.
2. PR-SCOPE after priority approval.
3. Present and approve the initial two-file changeset; write the index and then session state.
4. CD-SYSTEMS after the initial index write.

Phase-gated mode skips each optional gate with these exact notes:

- `TD-SYSTEM-BOUNDARY skipped — Phase-gated mode.`
- `PR-SCOPE skipped — Phase-gated mode.`
- `CD-SYSTEMS skipped — Phase-gated mode.`

Solo mode skips each optional gate with these exact notes:

- `TD-SYSTEM-BOUNDARY skipped — Solo mode.`
- `PR-SCOPE skipped — Solo mode.`
- `CD-SYSTEMS skipped — Solo mode.`

---

## Test Cases

### Case 1: Happy Path — Full mode uses sequential gates and one initial changeset

**Fixture:**
- `design/gdd/game-concept.md` and `design/gdd/game-pillars.md` exist.
- No `design/gdd/systems-index.md` exists.
- `.codex/studio.toml` contains `review_mode = "full"`.

**Input:** `$map-systems`

**Expected behavior:**
1. Read the concept and pillars, enumerate systems, and obtain dependency-map approval.
2. Run TD-SYSTEM-BOUNDARY and resolve its verdict before priority assignment.
3. Obtain priority approval, run PR-SCOPE, and resolve its verdict.
4. Draft the canonical index and present one complete proposed changeset for `design/gdd/systems-index.md` plus `production/session-state/active.md`.
5. After approval, write the index first and session state second.
6. Run CD-SYSTEMS against the initial written index, then return COMPLETE.

**Assertions:**
- [ ] The three gates run sequentially at their specified phases.
- [ ] No write occurs before the initial two-file changeset is approved.
- [ ] Both listed paths are written exactly as approved.
- [ ] CD-SYSTEMS receives the written index, not an unwritten draft.
- [ ] Verdict is COMPLETE.

---

### Case 2: Blocked Preconditions — Missing concept writes nothing

**Fixture:**
- `design/gdd/game-concept.md` is missing.

**Input:** `$map-systems`

**Expected behavior:**
1. Report the missing canonical concept path.
2. Recommend `$brainstorm`.
3. Run no director gate and write neither target file.
4. Return BLOCKED.

**Assertions:**
- [ ] The missing path is named.
- [ ] No gate is delegated.
- [ ] Neither the index nor session-state file is created.
- [ ] Verdict is BLOCKED.

---

### Case 3: Post-Write Review — CD-SYSTEMS feedback requires a revision approval

**Fixture:**
- Full mode initial changeset was approved and written.
- CD-SYSTEMS returns CONCERNS requiring a missing system and director note.

**Input:** Continue `$map-systems` after the initial index write.

**Expected behavior:**
1. Present the CD-SYSTEMS verdict without changing the file.
2. Show an exact revision changeset for `design/gdd/systems-index.md`, including every line to add, replace, or remove.
3. Obtain approval before modifying the file.
4. Apply only the approved revision, or leave the index unchanged if declined.

**Assertions:**
- [ ] Feedback is shown before the revision proposal.
- [ ] No silent note or system-list edit occurs.
- [ ] Declining the revision preserves the initial written index byte-for-byte.
- [ ] New scope requires a new proposal.

---

### Case 4: Existing Index — Update path preserves unapproved content

**Fixture:**
- `design/gdd/systems-index.md` exists with N systems.
- `production/session-state/active.md` may exist or be absent.
- `.codex/studio.toml` contains `review_mode = "full"`.

**Input:** `$map-systems`

**Expected behavior:**
1. Read and summarize the existing canonical index before asking whether to update systems or priorities.
2. Run TD-SYSTEM-BOUNDARY after any revised dependency map is approved.
3. Run PR-SCOPE after revised priorities are approved.
4. Present the exact index update and session-state create/update together for approval.
5. Write only approved changes, then run CD-SYSTEMS against the updated index.

**Assertions:**
- [ ] Existing content is not silently overwritten.
- [ ] The current system count is shown.
- [ ] Unlisted sections and paths remain unchanged.
- [ ] Post-write feedback uses the Case 3 revision boundary.

---

### Case 5: Mode Boundary — Phase-gated and solo skip all three optional gates

**Fixture:**
- A valid concept exists.
- Run once with `review_mode = "phase-gated"` and once with `review_mode = "solo"`.

**Input:** `$map-systems`

**Expected behavior:**
1. Complete enumeration, dependency approval, priority approval, and the initial changeset flow.
2. Emit all three exact skip notes for the active mode at the gates' normal phases.
3. Obtain initial two-file approval before writing in either mode.
4. Do not delegate a director or producer child.

**Assertions:**
- [ ] Phase-gated output includes the three Phase-gated notes above.
- [ ] Solo output includes the three Solo notes above.
- [ ] Gate skips do not bypass human write approval.
- [ ] The index and session-state paths remain canonical.

---

## Protocol Compliance

- [ ] Reads the concept before decomposition.
- [ ] Full mode uses TD-SYSTEM-BOUNDARY, then PR-SCOPE, then the approved initial write, then CD-SYSTEMS.
- [ ] Phase-gated and solo skip all three optional gates with exact notes.
- [ ] The initial index and session-state writes share one complete approved changeset.
- [ ] CD-SYSTEMS feedback never modifies the index without a separate approved revision.
- [ ] Ends with `$design-system [next-system]` or `$map-systems next` handoff.

---

## Coverage Notes

- Circular-dependency resolution and priority heuristics are exercised within
  Cases 1 and 4 rather than as separate fixtures.
- The `next` argument is a post-index handoff convenience and does not change
  the three-gate or write-approval contracts.
