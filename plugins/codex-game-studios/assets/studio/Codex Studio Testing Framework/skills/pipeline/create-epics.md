# Skill Test Spec: $create-epics

## Codex Runtime Contract

- Runtime skill: `.agents/skills/create-epics/SKILL.md`
- Runtime name: `create-epics`
- Runtime trigger description: `"Use when approved GDDs and architecture need translation into bounded, traceable implementation epics."`
- Native invocation: `$create-epics`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$create-epics` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: CREATED, BLOCKED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (`$create-stories`)
- [ ] Documents PR-EPIC gate behavior: runs in full mode; skipped in phase-gated/solo

---

## Director Gate Checks

In `full` mode: PR-EPIC (producer) gate runs after epics are drafted and before
any epic file is written. If PR-EPIC returns CONCERNS, epics are revised before
the parent presents the complete EPIC-file changeset for approval.

In `phase-gated` mode: PR-EPIC is skipped. Output notes: "PR-EPIC skipped — phase-gated mode".

In `solo` mode: PR-EPIC is skipped. Output notes: "PR-EPIC skipped — solo mode".

---

## Test Cases

### Case 1: Happy Path — Two approved GDDs create two EPIC files

**Fixture:**
- `design/gdd/systems-index.md` exists with 2 systems listed
- Both systems have approved GDDs in `design/gdd/`
- `docs/architecture/architecture.md` exists with matching modules
- At least one Accepted ADR exists for each system
- `.codex/studio.toml` contains `phase-gated`

**Input:** `$create-epics`

**Expected behavior:**
1. Skill reads systems index and both GDDs
2. Drafts 2 EPIC definitions (layer, GDD path, ADRs, requirements, engine risk)
3. PR-EPIC gate is skipped (phase-gated mode) — noted in output
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. After approval: writes both EPIC files
6. Creates or updates `production/epics/index.md`

**Assertions:**
- [ ] Epic summary is shown before any write ask
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Each EPIC.md contains: layer, GDD path, governing ADRs, requirements table, Definition of Done
- [ ] PR-EPIC skip is noted in output
- [ ] `production/epics/index.md` is updated after writing
- [ ] Skill writes no EPIC until one complete proposed changeset lists every EPIC path and material edit and is approved

---

### Case 2: Failure Path — No approved GDDs found

**Fixture:**
- `design/gdd/systems-index.md` exists
- No GDDs in `design/gdd/` have approved status (all are Draft or In Progress)

**Input:** `$create-epics`

**Expected behavior:**
1. Skill reads systems index and attempts to find approved GDDs
2. No approved GDDs found
3. Skill outputs: "No approved GDDs to convert. GDDs must be Approved before creating epics."
4. Skill suggests running `$design-system` and completing GDD approval first
5. Skill exits without creating any EPIC files

**Assertions:**
- [ ] Skill stops cleanly with a clear message when no approved GDDs exist
- [ ] No EPIC files are written
- [ ] Skill recommends the correct next action
- [ ] Verdict is BLOCKED

---

### Case 3: Director Gate — Full mode spawns PR-EPIC before writing

**Fixture:**
- 2 approved GDDs exist
- `.codex/studio.toml` contains `full`

**Full mode expected behavior:**
1. Skill drafts both epics
2. PR-EPIC gate spawns and reviews the epic drafts
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
4. Epic files are written after approval

**Assertions (full mode):**
- [ ] PR-EPIC gate appears in output as an active gate
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Epic files are NOT written before PR-EPIC completes

**Fixture (phase-gated mode):**
- Same GDDs
- `.codex/studio.toml` contains `phase-gated`

**Phase-gated mode expected behavior:**
1. Epics are drafted
2. PR-EPIC is skipped — noted in output
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions (phase-gated mode):**
- [ ] "PR-EPIC skipped — phase-gated mode" appears in output
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 4: Edge Case — Epic already exists for a GDD

**Fixture:**
- `production/epics/[layer]/EPIC-[name].md` already exists for one of the approved GDDs
- The other GDD has no existing EPIC file

**Input:** `$create-epics`

**Expected behavior:**
1. Skill detects the existing EPIC file for the first system
2. Skill offers to update rather than overwrite: "EPIC-[name].md already exists. Update it, or skip?"
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Skill detects existing EPIC files before writing
- [ ] User is offered "update" or "skip" options — not auto-overwritten
- [ ] The new system's EPIC is created normally without conflict

---

### Case 5: Director Gate — PR-EPIC returns CONCERNS

**Fixture:**
- 2 approved GDDs exist
- `.codex/studio.toml` contains `full`
- PR-EPIC gate returns CONCERNS (e.g., scope of one epic is too large)

**Input:** `$create-epics`

**Expected behavior:**
1. PR-EPIC gate spawns and returns CONCERNS with specific feedback
2. Skill surfaces the concerns to the user before any write ask
3. User is given options: revise epics, accept concerns and proceed, or stop
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Skill does NOT write epics while CONCERNS are unaddressed

**Assertions:**
- [ ] CONCERNS from PR-EPIC are shown to the user before writing
- [ ] Skill does NOT auto-write epics when CONCERNS are returned
- [ ] User is given a clear choice to revise, proceed, or stop
- [ ] Revised epic drafts are re-shown after revision before final approval

---

## Protocol Compliance

- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] PR-EPIC gate (if active) runs before write asks — not after
- [ ] Skipped gates noted by name and mode in output
- [ ] EPIC.md content sourced only from GDDs, ADRs, and architecture docs — nothing invented
- [ ] Ends with next-step handoff: `$create-stories [epic-slug]` per created epic

---

## Coverage Notes

- Processing of Core, Feature, and Presentation layers follows the same complete-changeset
  pattern as Foundation — layer-specific ordering is not independently tested.
- Engine risk level assignment (LOW/MEDIUM/HIGH) from governing ADRs is
  validated implicitly via Case 1's fixture structure.
- The `layer: [name]` and `[system-name]` argument modes follow the same approval
  pattern as the default (all systems) mode.
