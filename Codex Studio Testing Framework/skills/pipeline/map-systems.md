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

`$map-systems` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: COMPLETE, BLOCKED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (`$design-system`)
- [ ] Documents gate behavior: CD-SYSTEMS + TD-SYSTEM-BOUNDARY in parallel in full mode

---

## Director Gate Checks

In `full` mode: CD-SYSTEMS (creative-director) and TD-SYSTEM-BOUNDARY
(technical-director) spawn in parallel after the systems decomposition is drafted
and before `design/systems-index.md` is written.

In `phase-gated` mode: both gates are skipped. Output notes:
"CD-SYSTEMS skipped — phase-gated mode" and "TD-SYSTEM-BOUNDARY skipped — phase-gated mode".

In `solo` mode: both gates are skipped with equivalent notes.

---

## Test Cases

### Case 1: Happy Path — Game concept exists, 5-8 systems identified

**Fixture:**
- `design/gdd/game-concept.md` exists with Core Mechanics and MVP Definition sections
- `design/gdd/game-pillars.md` exists with ≥1 pillar defined
- No `design/systems-index.md` exists yet
- `.codex/studio.toml` contains `full`

**Input:** `$map-systems`

**Expected behavior:**
1. Skill reads game-concept.md and game-pillars.md
2. Identifies 5-8 systems (explicit + implicit)
3. Maps dependencies between systems and assigns layers
4. CD-SYSTEMS and TD-SYSTEM-BOUNDARY spawn in parallel and return APPROVED
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Writes systems-index.md after approval
7. Updates the explicit skill argument or a user-selected artifact under `production/`

**Assertions:**
- [ ] Between 5 and 8 systems are identified (not fewer, not more without explanation)
- [ ] CD-SYSTEMS and TD-SYSTEM-BOUNDARY spawn in parallel (not sequentially)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] systems-index.md is NOT written without approval
- [ ] Session state is updated after writing
- [ ] Verdict is COMPLETE

---

### Case 2: Failure Path — No game concept found

**Fixture:**
- `design/gdd/game-concept.md` does NOT exist
- `design/gdd/` directory may be empty or absent

**Input:** `$map-systems`

**Expected behavior:**
1. Skill attempts to read `design/gdd/game-concept.md`
2. File not found
3. Skill outputs: "No game concept found. Run `$brainstorm` to create one, then return to `$map-systems`."
4. Skill exits without creating systems-index.md

**Assertions:**
- [ ] Skill outputs a clear error naming the missing file path
- [ ] Skill recommends `$brainstorm` as the next action
- [ ] No systems-index.md is created
- [ ] Verdict is BLOCKED

---

### Case 3: Director Gate — CD-SYSTEMS returns CONCERNS (missing core system)

**Fixture:**
- Game concept exists
- `.codex/studio.toml` contains `full`
- CD-SYSTEMS gate returns CONCERNS: "The [core-system] is implied by the concept but not identified"

**Input:** `$map-systems`

**Expected behavior:**
1. Systems are drafted (5-8 initial systems identified)
2. CD-SYSTEMS gate returns CONCERNS naming the missing core system
3. TD-SYSTEM-BOUNDARY returns APPROVED
4. Skill surfaces CD-SYSTEMS concerns to user
5. User is asked: revise systems list to add the missing system, or proceed as-is
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] CD-SYSTEMS concerns are shown to the user before writing
- [ ] Skill does NOT auto-write systems-index.md while CONCERNS are unresolved
- [ ] User is given the option to revise or proceed
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 4: Edge Case — systems-index.md already exists

**Fixture:**
- `design/gdd/game-concept.md` exists
- `design/systems-index.md` already exists with N systems

**Input:** `$map-systems`

**Expected behavior:**
1. Skill reads the existing systems-index.md and presents its current state
2. Skill asks: "systems-index.md already exists with [N] systems. Update with new systems, or review and revise priorities?"
3. User chooses an action
4. Skill does NOT silently overwrite the existing index

**Assertions:**
- [ ] Skill detects and reads the existing systems-index.md before proceeding
- [ ] User is offered update/review options — not auto-overwritten
- [ ] Existing system count is presented to the user
- [ ] Skill does NOT proceed with a full re-decomposition without user choosing to do so

---

### Case 5: Director Gate — Phase-gated mode and solo mode both skip gates, noted

**Fixture (phase-gated mode):**
- Game concept exists
- `.codex/studio.toml` contains `phase-gated`

**Phase-gated mode expected behavior:**
1. Systems are decomposed and drafted
2. Both CD-SYSTEMS and TD-SYSTEM-BOUNDARY are skipped
3. Output notes: "CD-SYSTEMS skipped — phase-gated mode" and "TD-SYSTEM-BOUNDARY skipped — phase-gated mode"
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions (phase-gated mode):**
- [ ] Both gate skip notes appear in output
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] systems-index.md is written after user approval

**Fixture (solo mode):**
- Same game concept, `.codex/studio.toml` contains `solo`

**Solo mode expected behavior:**
1. Same decomposition workflow
2. Both gates skipped — noted in output with "solo mode"
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions (solo mode):**
- [ ] Both skip notes appear with "solo mode" label
- [ ] Behavior is otherwise identical to phase-gated mode for this skill

---

## Protocol Compliance

- [ ] Reads game-concept.md and game-pillars.md before any decomposition
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] systems-index.md is NOT written without user approval
- [ ] CD-SYSTEMS and TD-SYSTEM-BOUNDARY spawn in parallel in full mode
- [ ] Skipped gates noted by name and mode in phase-gated/solo output
- [ ] Ends with next-step handoff: `$design-system [next-system]`

---

## Coverage Notes

- Circular dependency detection (System A depends on System B which depends on A)
  is part of the dependency mapping phase — not independently fixture-tested here.
- Priority tier assignment (MVP heuristics) is evaluated as part of the Case 1
  collaborative workflow rather than independently.
- The `next` argument mode (handing off the highest-priority undesigned system to
  `$design-system`) is not tested here — it is a post-index-creation convenience.
