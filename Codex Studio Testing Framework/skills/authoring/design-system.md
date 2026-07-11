# Skill Test Spec: $design-system

## Codex Runtime Contract

- Runtime skill: `.agents/skills/design-system/SKILL.md`
- Runtime name: `design-system`
- Runtime trigger description: `Collaboratively author or resume a game-system GDD one approved section at a time.`
- Native invocation: `$design-system`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$design-system` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: APPROVED, NEEDS REVISION, MAJOR REVISION
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end
- [ ] Documents skeleton-first drafting in memory; no skeleton or content is written before complete-changeset approval
- [ ] Under `review_mode = "phase-gated"`, per-skill CD-GDD-ALIGN is skipped outside a phase gate
- [ ] Documents retrofit mode for existing GDD files

---

## Director Gate Checks

`.codex/studio.toml` is authoritative. With
`review_mode = "phase-gated"`, `$design-system` does not run a per-section
director gate outside a phase transition. Section drafts remain conversational
and in memory. After all approved section drafts are assembled, the parent shows
the complete file changeset and obtains approval before the single write.

---

## Test Cases

### Case 1: Happy Path — New GDD drafted section by section, written once

**Fixture:**
- No existing GDD for the target system in `design/gdd/`
- `.codex/studio.toml` contains `review_mode = "phase-gated"`

**Input:** `$design-system [system-name]`

**Expected behavior:**
1. Skill drafts an in-memory skeleton for `design/gdd/[system-name].md` with all 8 section headers.
2. For each section, discuss with the user, draft content, and obtain conversational approval without writing.
3. Because this is outside a phase gate, no CD-GDD-ALIGN child is invoked.
4. Assemble all approved, non-empty sections into one proposed file.
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Write the approved GDD once.

**Assertions:**
- [ ] The skeleton and section bodies remain in memory until final approval
- [ ] CD-GDD-ALIGN does not run outside a phase gate
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] No section is written until the complete changeset is shown and approved
- [ ] All 8 sections are present in the final GDD file

---

### Case 2: Retrofit Mode — Existing GDD, update specific section

**Fixture:**
- `design/gdd/[system-name].md` already exists with all 8 sections populated

**Input:** `$design-system [system-name]`

**Expected behavior:**
1. Skill detects existing GDD file and reads its current content
2. Skill offers retrofit mode: "GDD already exists. Which section would you like to update?"
3. User selects a specific section (e.g., Formulas)
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Only the selected section is updated — other sections are not modified

**Assertions:**
- [ ] Skill detects and reads existing GDD before offering retrofit mode
- [ ] User is asked which section to update — not asked to rewrite the whole document
- [ ] Only the selected section is rewritten — others remain unchanged
- [ ] CD-GDD-ALIGN still runs on the updated section
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 3: Phase-Gate Boundary — Director feedback blocks the final changeset

**Fixture:**
- New GDD being authored
- `.codex/studio.toml` contains `review_mode = "phase-gated"`
- The workflow is explicitly part of a phase transition and CD-GDD-ALIGN returns MAJOR REVISION on the Player Fantasy section

**Input:** `$design-system [system-name]`

**Expected behavior:**
1. Player Fantasy section is drafted
2. CD-GDD-ALIGN gate runs and returns MAJOR REVISION with specific feedback
3. Skill surfaces the feedback to the user
4. No part of the GDD is written while MAJOR REVISION is unresolved
5. User rewrites the section in collaboration with the skill
6. CD-GDD-ALIGN runs again on the revised section
7. After all feedback is resolved, the parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] No GDD write occurs when CD-GDD-ALIGN returns MAJOR REVISION
- [ ] Gate feedback is shown to the user before requesting revision
- [ ] CD-GDD-ALIGN runs again after the section is revised
- [ ] Skill does NOT auto-proceed to the next section while MAJOR REVISION is unresolved

---

### Case 4: Non-Phase Workflow — Director gate skipped and write remains atomic

**Fixture:**
- New GDD being authored
- `.codex/studio.toml` contains `review_mode = "phase-gated"`

**Input:** `$design-system [system-name]`

**Expected behavior:**
1. An 8-section skeleton and each section body are drafted in memory and shown to the user.
2. CD-GDD-ALIGN is not invoked because this is outside a phase gate.
3. The parent presents the complete proposed GDD changeset and obtains approval before any write.
4. The GDD is written once after approval; no gate review occurs.

**Assertions:**
- [ ] The phase-gated policy is stated without producing repetitive per-section skip messages
- [ ] Section approval does not itself authorize a filesystem write
- [ ] Skill does NOT spawn any CD-GDD-ALIGN gate in a non-phase workflow
- [ ] Full GDD is written only after the complete changeset is shown and approved

---

### Case 5: Director Gate — Empty sections not written to file

**Fixture:**
- GDD authoring in progress
- User and skill discuss one section but do not produce any approved content
  (e.g., discussion ends without a decision, or user says "skip for now")

**Input:** `$design-system [system-name]`

**Expected behavior:**
1. Section discussion produces no approved content
2. Skill does NOT add an empty or placeholder body to the proposed changeset
3. The section header remains in the in-memory skeleton but the body stays empty
4. Skill moves to the next section without writing
5. At the end, incomplete sections are listed and user is reminded to return to them

**Assertions:**
- [ ] Empty or unapproved sections are not included as file content
- [ ] The in-memory skeleton retains the section header
- [ ] Skill tracks and lists incomplete sections at the end of the session
- [ ] Skill does NOT write "TBD" or placeholder content without user approval

---

## Protocol Compliance

- [ ] Skeleton and content are drafted in memory before any filesystem write
- [ ] CD-GDD-ALIGN is limited to an explicit phase transition
- [ ] Outside a phase gate, no director child is spawned
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] MAJOR REVISION from CD-GDD-ALIGN blocks the complete GDD write until resolved
- [ ] Only approved, non-empty sections are written to the file
- [ ] Ends with next-step handoff: `$review-all-gdds` or `$map-systems next`

---

## Coverage Notes

- The 8 required sections are validated against the project's design document
  standards defined in `AGENTS.md` — not re-enumerated here.
- The skill's internal section-ordering logic (which section to author first) is
  not independently tested — the order follows the standard GDD template.
- Pillar alignment checking within CD-GDD-ALIGN is evaluated holistically by
  the gate agent — specific pillar checks are not fixture-tested here.
