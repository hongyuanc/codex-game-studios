# Skill Test Spec: $dev-story

## Codex Runtime Contract

- Runtime skill: `.agents/skills/dev-story/SKILL.md`
- Runtime name: `dev-story`
- Runtime trigger description: `"Use when an implementation-ready story has been approved for bounded source, test, and evidence work."`
- Native invocation: `$dev-story`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$dev-story` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: COMPLETE, BLOCKED, IN PROGRESS, NEEDS CHANGES
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (`$story-done`)
- [ ] Documents LP-CODE-REVIEW gate: active in full mode, skipped in lean/solo
- [ ] Notes that implementation is delegated to specialist agents (not done directly)

---

## Director Gate Checks

In `full` mode: LP-CODE-REVIEW gate runs after implementation is complete and all
criteria are verified, before marking the story Complete.

In `lean` mode: LP-CODE-REVIEW is skipped. Output notes:
"LP-CODE-REVIEW skipped — lean mode". Story is marked Complete after user confirms.

In `solo` mode: LP-CODE-REVIEW is skipped with equivalent notes.

---

## Test Cases

### Case 1: Happy Path — Story implemented and marked Complete (full mode)

**Fixture:**
- A story file exists at `production/epics/[layer]/story-[name].md` with:
  - `Status: Ready`
  - A TR-ID referencing a registered requirement
  - At least 2 Given-When-Then acceptance criteria
  - A test evidence path
- Referenced ADR has `Status: Accepted`
- `docs/architecture/control-manifest.md` exists
- `.codex/docs/technical-preferences.md` has engine and language configured
- `production/session-state/review-mode.txt` contains `full`

**Input:** `$dev-story production/epics/[layer]/story-[name].md`

**Expected behavior:**
1. Skill reads the story file and all referenced context
2. Skill verifies the ADR is Accepted (no block)
3. Skill routes implementation to the correct specialist agent
4. All acceptance criteria are verified as met
5. LP-CODE-REVIEW gate spawns and returns APPROVED
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
7. Story status is updated to Complete

**Assertions:**
- [ ] Skill reads story before spawning any agent
- [ ] ADR status is checked before implementation begins
- [ ] Implementation is delegated to a specialist agent (not done inline)
- [ ] All acceptance criteria are confirmed before LP-CODE-REVIEW
- [ ] LP-CODE-REVIEW appears in output as a completed gate
- [ ] Story status is updated to Complete only after gate approval and user consent
- [ ] Test file is written as part of implementation (not deferred)

---

### Case 2: Failure Path — Referenced ADR is Proposed

**Fixture:**
- A story file exists with `Status: Ready`
- The story's TR-ID points to a requirement covered by an ADR with `Status: Proposed`

**Input:** `$dev-story production/epics/[layer]/story-[name].md`

**Expected behavior:**
1. Skill reads the story file
2. Skill resolves the TR-ID and reads the governing ADR
3. ADR status is Proposed — skill outputs a BLOCKED message
4. Skill names the specific ADR blocking the story
5. Skill recommends running `$architecture-decision` to advance the ADR
6. Implementation does NOT begin

**Assertions:**
- [ ] Skill does NOT begin implementation with a Proposed ADR
- [ ] BLOCKED message names the specific ADR number and title
- [ ] Skill recommends `$architecture-decision` as the next action
- [ ] Story status remains unchanged (not set to In Progress or Complete)

---

### Case 3: Ambiguous Acceptance Criteria — Skill asks for clarification

**Fixture:**
- A story file exists with `Status: Ready`
- Referenced ADR is Accepted
- One acceptance criterion is ambiguous (not Given-When-Then; uses subjective language like "feels responsive")

**Input:** `$dev-story production/epics/[layer]/story-[name].md`

**Expected behavior:**
1. Skill reads the story and identifies the ambiguous criterion
2. Before routing to the specialist, skill asks the user to clarify the criterion
3. User provides a concrete, testable restatement
4. Skill proceeds with implementation using the clarified criterion
5. Skill does NOT guess at the intended behavior

**Assertions:**
- [ ] Skill surfaces the ambiguous criterion before implementation starts
- [ ] Skill asks for user clarification (not auto-interpretation)
- [ ] Implementation begins only after clarification is provided
- [ ] Clarified criterion is used in the test (not the original vague version)

---

### Case 4: Edge Case — No argument; reads from session state

**Fixture:**
- No argument is provided
- `production/session-state/active.md` references an active story file
- That story file exists with `Status: In Progress`

**Input:** `$dev-story` (no argument)

**Expected behavior:**
1. Skill detects no argument is provided
2. Skill reads `production/session-state/active.md`
3. Skill finds the active story reference
4. Skill confirms with user: "Continuing work on [story title] — is that correct?"
5. After confirmation, skill proceeds with that story

**Assertions:**
- [ ] Skill reads session state when no argument is provided
- [ ] Skill confirms the active story with the user before proceeding
- [ ] Skill does NOT silently assume the active story without confirmation
- [ ] If session state has no active story, skill asks which story to implement

---

### Case 5: Director Gate — LP-CODE-REVIEW returns NEEDS CHANGES; lean mode skips gate

**Fixture (full mode):**
- Story is implemented and all criteria appear met
- `production/session-state/review-mode.txt` contains `full`
- LP-CODE-REVIEW gate returns NEEDS CHANGES with specific feedback

**Full mode expected behavior:**
1. LP-CODE-REVIEW gate spawns after implementation
2. Gate returns NEEDS CHANGES with 2 specific issues
3. Story status remains In Progress — NOT marked Complete
4. User is shown the gate feedback and asked how to proceed

**Assertions (full mode):**
- [ ] Story is NOT marked Complete when LP-CODE-REVIEW returns NEEDS CHANGES
- [ ] Gate feedback is shown to the user verbatim
- [ ] Story status stays In Progress until issues are resolved and gate passes

**Fixture (lean mode):**
- Same story, `production/session-state/review-mode.txt` contains `lean`

**Lean mode expected behavior:**
1. Implementation completes
2. LP-CODE-REVIEW gate is skipped — noted in output
3. User is asked to confirm all criteria are met
4. Story is marked Complete after user confirmation

**Assertions (lean mode):**
- [ ] "LP-CODE-REVIEW skipped — lean mode" appears in output
- [ ] Story is marked Complete after user confirms criteria (no gate required)
- [ ] Skill does NOT block on a gate that is skipped

---

## Protocol Compliance

- [ ] Does NOT write source code directly — delegates to specialist agents
- [ ] Reads all context (story, TR-ID, ADR, manifest, engine prefs) before implementation
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skipped gates noted by name and mode in output
- [ ] Updates `production/session-state/active.md` after story completion
- [ ] Ends with next-step handoff: `$story-done`

---

## Coverage Notes

- Engine routing logic (Godot vs Unity vs Unreal) is not tested per engine —
  the routing pattern is consistent; engine selection is a config fact.
- Visual/Feel and UI story types (no automated test required) have different
  evidence requirements and are not covered in these cases.
- Integration story type follows the same pattern as Logic but with a different
  evidence path — not independently fixture-tested.
