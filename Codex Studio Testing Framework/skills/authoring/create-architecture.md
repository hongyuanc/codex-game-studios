# Skill Test Spec: $create-architecture

## Codex Runtime Contract

- Runtime skill: `.agents/skills/create-architecture/SKILL.md`
- Runtime name: `create-architecture`
- Runtime trigger description: `Author the master technical architecture from approved design requirements and engine constraints.`
- Native invocation: `$create-architecture`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$create-architecture` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

The runtime uses bounded incremental authoring. Draft and present one section, obtain approval, then write that approved section to the already identified artifact path. No write occurs before that section approval, and no per-file reapproval is required inside the approved section. Continue sequentially, then read back and finalize the already assembled document as a completeness check. No second whole-document write approval or rewrite occurs. New paths, multi-file changes, or non-section scope expansion require a complete approved changeset.

---

## Static Assertions (Structural)

Verified automatically by `$skill-test static` — no fixture needed.

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings
- [ ] Contains verdict keywords: APPROVED, NEEDS REVISION, MAJOR REVISION NEEDED
- [ ] Draft-before-approval and incremental section writes match the runtime protocol
- [ ] Has a next-step handoff at the end (`$architecture-review` or `$create-control-manifest`)
- [ ] Documents skeleton-first approach
- [ ] Documents gate behavior: TD-ARCHITECTURE is mandatory in every mode; LP-FEASIBILITY is optional in full only
- [ ] Documents retrofit mode for existing architecture documents

---

## Director Gate Checks

TD-ARCHITECTURE is mandatory in `full`, `phase-gated`, and `solo`; it delegates
to `technical-director` after the approved sections have been written and the
assembled document has passed read-back. LP-FEASIBILITY is optional: run it only in `full`; skip it in `phase-gated` and `solo`. In full mode the two independent
reviews may run in parallel.

---

## Test Cases

### Case 1: Happy Path — New architecture doc, skeleton-first, full mode gates approve

**Fixture:**
- No existing `docs/architecture/architecture.md`
- `docs/architecture/` contains Accepted ADRs for reference
- `.codex/studio.toml` contains `full`

**Input:** `$create-architecture`

**Expected behavior:**
1. Skill identifies `docs/architecture/architecture.md` and presents the first architecture section draft.
2. Obtain approval, write that approved section immediately, and continue sequentially.
3. Read back the assembled document for completeness without a second whole-document write or approval.
4. TD-ARCHITECTURE and LP-FEASIBILITY spawn in parallel.
5. Both gates return APPROVED.
6. The later Document Status sign-off update is shown and explicitly approved before that bounded update.

**Assertions:**
- [ ] Each section is shown and approved before its write
- [ ] No per-file reapproval is requested inside an approved section
- [ ] TD-ARCHITECTURE and LP-FEASIBILITY spawn in parallel (not sequentially)
- [ ] Both gates complete before the final completion confirmation
- [ ] Verdict is APPROVED when both gates return APPROVED
- [ ] Next-step handoff to `$architecture-review` or `$create-control-manifest` is present

---

### Case 2: Failure Path — TD-ARCHITECTURE returns MAJOR REVISION

**Fixture:**
- Architecture doc is fully drafted (all sections)
- `.codex/studio.toml` contains `full`
- TD-ARCHITECTURE gate returns MAJOR REVISION: "[specific structural issue]"

**Input:** `$create-architecture`

**Expected behavior:**
1. All sections are drafted and written
2. TD-ARCHITECTURE gate runs and returns MAJOR REVISION with specific feedback
3. Skill surfaces the feedback to the user
4. Architecture is NOT marked as finalized
5. User is asked: revise the flagged sections, or accept the document as a draft

**Assertions:**
- [ ] Architecture is NOT marked finalized when TD-ARCHITECTURE returns MAJOR REVISION
- [ ] Gate feedback is shown to the user with specific issue descriptions
- [ ] User is given the option to revise specific sections
- [ ] Skill does NOT auto-finalize despite MAJOR REVISION feedback

---

### Case 3: Phase-gated Mode — Mandatory TD review runs; optional LP review skips

**Fixture:**
- No existing architecture doc
- `.codex/studio.toml` contains `phase-gated`

**Input:** `$create-architecture`

**Expected behavior:**
1. The current section is drafted and shown inline.
2. Each section is approved and written immediately before moving to the next.
3. Read back the assembled document; do not rewrite it or request a second whole-document write approval.
4. TD-ARCHITECTURE runs because it is mandatory in every review mode.
5. LP-FEASIBILITY is skipped with: "LP-FEASIBILITY skipped — phase-gated mode".
6. The later sign-off status update remains separately displayed and approved.

**Assertions:**
- [ ] TD-ARCHITECTURE delegates to technical-director
- [ ] Only the LP-FEASIBILITY skip note appears
- [ ] No section write occurs before that section's approval
- [ ] No final whole-document rewrite or duplicate write approval occurs
- [ ] Next-step handoff is still present

---

### Case 4: Retrofit Mode — Existing architecture doc, user updates a section

**Fixture:**
- `docs/architecture/architecture.md` already exists with all sections populated

**Input:** `$create-architecture`

**Expected behavior:**
1. Skill detects existing architecture doc and reads its current content
2. Skill offers retrofit mode: "Architecture doc already exists. Which section would you like to update?"
3. User selects a section
4. Present the selected section draft and obtain approval.
5. Write only the approved section — other sections remain unchanged.

**Assertions:**
- [ ] Skill detects and reads the existing architecture doc before offering retrofit
- [ ] User is asked which section to update — not asked to rewrite the whole document
- [ ] Only the selected section is updated
- [ ] Other sections are not modified during a retrofit session

---

### Case 5: Director Gate — Architecture references a Proposed ADR; flagged as risk

**Fixture:**
- Architecture doc is being authored
- One section references or depends on an ADR that has `Status: Proposed`
- `.codex/studio.toml` contains `full`

**Input:** `$create-architecture`

**Expected behavior:**
1. Skill authors all sections
2. During authoring, skill detects a reference to a Proposed ADR
3. Skill flags: "Note: [section] references ADR-NNN which is Proposed — this is a risk until the ADR is accepted"
4. Risk flag is embedded in the relevant section's content
5. TD-ARCHITECTURE and LP-FEASIBILITY still run — they are informed of the Proposed ADR risk

**Assertions:**
- [ ] Proposed ADR reference is detected and flagged during section authoring
- [ ] Risk note is embedded in the architecture document section
- [ ] TD-ARCHITECTURE and LP-FEASIBILITY still spawn (the risk does not block the gates)
- [ ] Risk flag names the specific ADR number and title

---

## Protocol Compliance

- [ ] Sections are drafted, approved, and written sequentially
- [ ] Session state is updated at handoff without redundant approval for the already approved section write
- [ ] TD-ARCHITECTURE is mandatory in full, phase-gated, and solo modes
- [ ] LP-FEASIBILITY runs only in full and is skipped by name in phase-gated/solo output
- [ ] Phase 7 reads back the assembled document without a second whole-document write approval
- [ ] Proposed ADR references flagged as risks in the document
- [ ] Ends with next-step handoff: `$architecture-review` or `$create-control-manifest`

---

## Coverage Notes

- The required section list for architecture documents is defined in the skill
  body and in the `$architecture-review` skill — not re-enumerated here.
- Engine version stamping in the architecture doc (parallel to ADR stamping)
  is part of the authoring workflow — tested implicitly via Case 1.
- The retrofit mode for updating multiple sections in one session follows the
  same per-section approval pattern — not independently tested for multi-section
  retrofits.
