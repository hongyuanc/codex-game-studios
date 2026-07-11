# Skill Test Spec: $create-control-manifest

## Codex Runtime Contract

- Runtime skill: `.agents/skills/create-control-manifest/SKILL.md`
- Runtime name: `create-control-manifest`
- Runtime trigger description: `Generate the programmer control manifest from accepted ADRs, technical preferences, and engine rules.`
- Native invocation: `$create-control-manifest`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$create-control-manifest` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff at the end (`$create-epics` or `$create-stories`)
- [ ] Documents that only Accepted ADRs are included (not Proposed)

---

## Director Gate Checks

No director gates — this skill spawns no director gate agents. The control
manifest is a mechanical extraction from Accepted ADRs; no creative or technical
review gate is needed.

---

## Test Cases

### Case 1: Happy Path — 4 Accepted ADRs create a correct manifest

**Fixture:**
- `docs/architecture/` contains 4 ADR files, all with `Status: Accepted`
- Each ADR has a "Required Patterns" and/or "Forbidden Patterns" section
- No existing `docs/architecture/control-manifest.md`

**Input:** `$create-control-manifest`

**Expected behavior:**
1. Skill reads all ADR files in `docs/architecture/`
2. Extracts Required Patterns, Forbidden Patterns, and key constraints from each
3. Drafts the manifest with correct section structure
4. Shows the draft manifest to the user
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Writes the manifest after approval

**Assertions:**
- [ ] All 4 Accepted ADRs are represented in the manifest
- [ ] Manifest includes distinct sections for Required Patterns and Forbidden Patterns
- [ ] Manifest includes the source ADR number for each constraint
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill does NOT write without approval
- [ ] Verdict is CREATED after writing

---

### Case 2: Failure Path — No ADRs found

**Fixture:**
- `docs/architecture/` directory exists but contains no ADR files

**Input:** `$create-control-manifest`

**Expected behavior:**
1. Skill reads `docs/architecture/` and finds no ADR files
2. Skill outputs: "No ADRs found. Run `$architecture-decision` to create ADRs before generating the control manifest."
3. Skill exits without creating any file
4. Verdict is BLOCKED

**Assertions:**
- [ ] Skill outputs a clear error when no ADRs are found
- [ ] No control manifest file is written
- [ ] Skill recommends `$architecture-decision` as the next action
- [ ] Verdict is BLOCKED (not an error crash)

---

### Case 3: Mixed ADR Statuses — Only Accepted ADRs included

**Fixture:**
- `docs/architecture/` contains 3 Accepted ADRs and 2 Proposed ADRs

**Input:** `$create-control-manifest`

**Expected behavior:**
1. Skill reads all ADR files and filters by Status: Accepted
2. Manifest is drafted from the 3 Accepted ADRs only
3. Output notes: "2 Proposed ADRs were excluded: [adr-NNN-name, adr-NNN-name]"
4. User sees which ADRs were excluded before approving the write
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Only the 3 Accepted ADRs appear in the manifest content
- [ ] Excluded Proposed ADRs are listed by name in the output
- [ ] User sees the exclusion list before approving the write
- [ ] Skill does NOT silently omit Proposed ADRs without noting them

---

### Case 4: Edge Case — Manifest already exists

**Fixture:**
- `docs/architecture/control-manifest.md` already exists (version 1, dated last week)
- `docs/architecture/` contains Accepted ADRs (some new since last manifest)

**Input:** `$create-control-manifest`

**Expected behavior:**
1. Skill detects existing manifest and reads its version number / date
2. Skill offers to regenerate: "control-manifest.md already exists (v1, [date]). Regenerate with current ADRs?"
3. If user confirms: skill drafts updated manifest, increments version number
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Writes updated manifest after approval

**Assertions:**
- [ ] Skill reads and reports the existing manifest version before offering to regenerate
- [ ] User is offered a regenerate/skip choice — not auto-overwritten
- [ ] Updated manifest has an incremented version number
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 5: Optional Director Gate — TD-MANIFEST runs only in full

**Fixture:**
- 4 Accepted ADRs exist
- `.codex/studio.toml` exists with `full`

**Input:** `$create-control-manifest`

**Expected behavior:**
1. Skill reads ADRs and drafts manifest
2. Read and resolve `review_mode` from `.codex/studio.toml` before deciding whether to delegate.
3. TD-MANIFEST is optional: run it only in `full`; skip it in `phase-gated` and `solo`.
4. In this `full` fixture, delegate to the technical director and apply its verdict before writing.
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] The canonical review mode is resolved before the gate decision.
- [ ] Full mode runs TD-MANIFEST; phase-gated and solo skip it with an optional-gate note.
- [ ] TD-MANIFEST feedback is resolved before the approved manifest write.

---

## Protocol Compliance

- [ ] Reads all ADR files before drafting manifest
- [ ] Only Accepted ADRs included — Proposed ones noted as excluded
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] TD-MANIFEST mode behavior matches the runtime skill exactly.
- [ ] Ends with next-step handoff: `$create-epics` or `$create-stories`

---

## Coverage Notes

- The exact section structure of the generated manifest (constraint tables, pattern
  lists) is defined by the skill body and not re-enumerated in test assertions.
- The `version` field incrementing logic (v1 → v2) is tested via Case 4 but exact
  version numbering format is not fixture-locked.
- ADR parsing (extracting Required/Forbidden Patterns) depends on consistent ADR
  structure — tested implicitly via Case 1's fixture.
