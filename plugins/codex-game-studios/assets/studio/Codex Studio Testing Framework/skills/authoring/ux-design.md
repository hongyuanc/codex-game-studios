# Skill Test Spec: $ux-design

## Codex Runtime Contract

- Runtime skill: `.agents/skills/ux-design/SKILL.md`
- Runtime name: `ux-design`
- Runtime trigger description: `Collaboratively author a UX specification, HUD design, player journey, or interaction pattern artifact.`
- Native invocation: `$ux-design`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$ux-design` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

The runtime uses bounded incremental authoring. Draft and present one section, obtain approval, then write that approved section to the already identified artifact path. No write occurs before that section approval, and no per-file reapproval is required inside the approved section. After each section write, update session state; a new path, section, or scope expansion requires fresh approval.

---

## Static Assertions (Structural)

Verified automatically by `$skill-test static` — no fixture needed.

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings
- [ ] Contains verdict keyword: COMPLETE
- [ ] Skeleton creation and each section follow the runtime's bounded approval/write cycle
- [ ] Has a next-step handoff (e.g., `$ux-review` to validate the completed spec)

---

## Director Gate Checks

None. `$ux-design` has no inline director gates. `$ux-review` is the separate
review skill invoked after this skill completes.

---

## Test Cases

### Case 1: Happy Path — New HUD spec, all sections authored and written

**Fixture:**
- No existing HUD UX spec in `design/ux/`
- Engine and rendering preferences configured

**Input:** `$ux-design hud`

**Expected behavior:**
1. Skill identifies `design/ux/hud.md`, presents the skeleton proposal, and writes it only after approval.
2. Skill discusses and presents one section draft at a time: User Flows, Interaction States
   (normal/hover/focus/disabled), Wireframe Description, Accessibility Notes
3. Ask "Approve the [Section Name] section?" after showing that complete draft.
4. Write the approved section without a second per-file prompt, update the runtime-directed session record, and continue.
5. After all sections are written, verdict is COMPLETE
6. Skill suggests running `$ux-review` as the next step

**Assertions:**
- [ ] Skeleton creation is approved before its write
- [ ] Each section is approved before its write and does not receive duplicate per-file approval
- [ ] All required sections are present: User Flows, Interaction States,
     Wireframe Description, Accessibility Notes
- [ ] Handoff to `$ux-review` is at the end
- [ ] Verdict is COMPLETE

---

### Case 2: Existing UX Spec — Retrofit: user picks section to update

**Fixture:**
- `design/ux/hud.md` already exists with all sections populated
- User wants to update only the Accessibility Notes section

**Input:** `$ux-design hud`

**Expected behavior:**
1. Skill reads existing `design/ux/hud.md` and detects all sections are populated
2. Skill reports: "UX spec already exists for HUD — offering to retrofit"
3. Skill lists all sections and asks which to update
4. User selects Accessibility Notes
5. Present the Accessibility Notes draft and obtain approval.
6. Write only that approved section, update session state, and preserve all other sections; verdict is COMPLETE.

**Assertions:**
- [ ] Existing spec is detected and retrofit is offered
- [ ] User selects which section(s) to update
- [ ] Only the selected section is updated — other sections unchanged
- [ ] The approved selected section is written without another per-file approval
- [ ] Verdict is COMPLETE

---

### Case 3: Dependency Gap — Spec references a system with no design doc

**Fixture:**
- User is authoring a UX spec for the inventory screen
- `design/gdd/inventory.md` does not exist

**Input:** `$ux-design inventory-screen`

**Expected behavior:**
1. Skill begins authoring the inventory screen UX spec
2. During the User Flows section, skill attempts to reference inventory system rules
3. Skill detects: "No GDD found for inventory system — UX spec has a DEPENDENCY GAP"
4. The dependency gap is flagged in the spec (noted inline: "DEPENDENCY GAP: inventory GDD")
5. Skill continues authoring with placeholder notes for the missing rules
6. Verdict is COMPLETE with advisory note about the dependency gap

**Assertions:**
- [ ] DEPENDENCY GAP label appears in the spec for the missing system doc
- [ ] Skill does NOT block on the missing GDD — it continues with placeholders
- [ ] Dependency gap is also noted in the skill output (not just in the file)
- [ ] Handoff suggests both `$ux-review` and writing the missing GDD

---

### Case 4: No Argument Provided — Usage error

**Fixture:**
- No argument provided with the skill invocation

**Input:** `$ux-design`

**Expected behavior:**
1. Skill detects no screen name or argument provided
2. Skill outputs a usage error: "Screen name required. Usage: `$ux-design [screen-name]`"
3. Skill provides examples: `$ux-design hud`, `$ux-design main-menu`, `$ux-design inventory`
4. Skill stops without proposing or writing an artifact.

**Assertions:**
- [ ] Usage error is clearly stated
- [ ] Example invocations are provided
- [ ] No file is created
- [ ] Skill does not attempt to proceed without an argument

---

### Case 5: Director Gate Check — No gate; ux-review is the separate review skill

**Fixture:**
- New screen spec with argument provided

**Input:** `$ux-design settings-menu`

**Expected behavior:**
1. Skill authors all sections of the settings menu UX spec
2. No director agents are spawned
3. No gate IDs appear in output during authoring

**Assertions:**
- [ ] No director gate is invoked during ux-design
- [ ] No gate skip messages appear
- [ ] Verdict is COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Skeleton creation is approved before writing empty section headers
- [ ] Discusses and drafts one section at a time
- [ ] Every section draft is shown and approved before its incremental write
- [ ] Session state is updated after each section without redundant per-file approval
- [ ] Detects existing spec and offers retrofit path
- [ ] Ends with handoff to `$ux-review`
- [ ] Verdict is COMPLETE when all sections are written

---

## Coverage Notes

- Interaction state enumeration (normal/hover/focus/disabled/error) is a core
  requirement of each spec; the `$ux-review` skill checks for completeness.
- Wireframe descriptions are text-only (no images); image references may be
  added manually by a designer after the fact.
- Responsive layout concerns (different screen sizes) are noted as optional
  content and not assertion-tested here.
