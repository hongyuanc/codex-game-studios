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

Validation is read-only. If the workflow writes, the parent first presents one
complete proposed changeset containing every target path and material edit; any
new path or scope expansion requires fresh approval. If it delegates, direct
children return scoped evidence and the parent synthesizes the result.

---

## Static Assertions (Structural)

Verified automatically by `$skill-test static` — no fixture needed.

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings
- [ ] Contains verdict keywords: APPROVED, NEEDS REVISION, MAJOR REVISION NEEDED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (`$architecture-review` or `$create-control-manifest`)
- [ ] Documents skeleton-first approach
- [ ] Documents gate behavior: TD-ARCHITECTURE + LP-FEASIBILITY in full mode; skipped in lean/solo
- [ ] Documents retrofit mode for existing architecture documents

---

## Director Gate Checks

In `full` mode: TD-ARCHITECTURE (technical-director) and LP-FEASIBILITY
(lead-programmer) spawn in parallel after all sections are drafted and before
any final approval write.

In `lean` mode: both gates are skipped. Output notes:
"TD-ARCHITECTURE skipped — lean mode" and "LP-FEASIBILITY skipped — lean mode".

In `solo` mode: both gates are skipped with equivalent notes.

---

## Test Cases

### Case 1: Happy Path — New architecture doc, skeleton-first, full mode gates approve

**Fixture:**
- No existing `docs/architecture/architecture.md`
- `docs/architecture/` contains Accepted ADRs for reference
- `production/session-state/review-mode.txt` contains `full`

**Input:** `$create-architecture`

**Expected behavior:**
1. Skill creates skeleton `docs/architecture/architecture.md` with all required section headers
2. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
3. After all sections are drafted: TD-ARCHITECTURE and LP-FEASIBILITY spawn in parallel
4. Both gates return APPROVED
5. The parent asks one explicit completion decision in its own turn.
6. Session state updated

**Assertions:**
- [ ] Skeleton file is created with all section headers before any content is written
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] TD-ARCHITECTURE and LP-FEASIBILITY spawn in parallel (not sequentially)
- [ ] Both gates complete before the final completion confirmation
- [ ] Verdict is APPROVED when both gates return APPROVED
- [ ] Next-step handoff to `$architecture-review` or `$create-control-manifest` is present

---

### Case 2: Failure Path — TD-ARCHITECTURE returns MAJOR REVISION

**Fixture:**
- Architecture doc is fully drafted (all sections)
- `production/session-state/review-mode.txt` contains `full`
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

### Case 3: Lean Mode — Both gates skipped; architecture written with user approval only

**Fixture:**
- No existing architecture doc
- `production/session-state/review-mode.txt` contains `lean`

**Input:** `$create-architecture`

**Expected behavior:**
1. Skeleton file is created
2. All sections are authored and written per-section with user approval
3. After completion: TD-ARCHITECTURE and LP-FEASIBILITY are skipped
4. Output notes: "TD-ARCHITECTURE skipped — lean mode" and "LP-FEASIBILITY skipped — lean mode"
5. Architecture is considered complete based on user approval alone

**Assertions:**
- [ ] Both gate skip notes appear in output
- [ ] Architecture document is written with only user approval in lean mode
- [ ] Skill does NOT block completion because gates were skipped
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
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Only the selected section is updated — other sections unchanged

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
- `production/session-state/review-mode.txt` contains `full`

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

- [ ] Skeleton file created with all section headers before any content is written
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] TD-ARCHITECTURE and LP-FEASIBILITY spawn in parallel in full mode
- [ ] Skipped gates noted by name and mode in lean/solo output
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
