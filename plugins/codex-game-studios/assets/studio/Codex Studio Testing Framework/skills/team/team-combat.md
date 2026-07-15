# Skill Test Spec: $team-combat

## Codex Runtime Contract

- Runtime skill: `.agents/skills/team-combat/SKILL.md`
- Runtime name: `team-combat`
- Runtime trigger description: `"Use when a combat feature needs coordinated design, implementation, integration, and QA validation."`
- Native invocation: `$team-combat`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$team-combat` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

Validation is read-only. If the workflow writes, the parent first presents one
complete proposed changeset containing every target path and material edit; any
new path or scope expansion requires fresh approval. If it delegates, direct
children return scoped evidence and the parent synthesizes the result.

---

## Static Assertions (Structural)

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings (Phase 1 through Phase 6 are all present)
- [ ] Contains verdict keywords: COMPLETE, NEEDS WORK, BLOCKED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (references `$code-review`, `$balance-check`, `$team-polish`)
- [ ] Error Recovery Protocol section is present with all four recovery steps
- [ ] Uses `request_user_input` at phase transitions for user approval before proceeding
- [ ] Phase 3 is explicitly marked as parallel (gameplay-programmer, ai-programmer, technical-artist, sound-designer)
- [ ] Phase 2 includes spawning the primary engine specialist (read from `.codex/docs/technical-preferences.md`)
- [ ] Team Composition lists all seven roles (game-designer, gameplay-programmer, ai-programmer, technical-artist, sound-designer, engine specialist, qa-tester)

---

## Test Cases

### Case 1: Happy Path — All agents succeed, full pipeline runs to completion

**Fixture:**
- `design/gdd/game-concept.md` exists and is populated
- Engine is configured in `.codex/docs/technical-preferences.md` (Engine Specialists section filled)
- No existing GDD for the requested combat feature

**Input:** `$team-combat parry and riposte system`

**Expected behavior:**
1. Phase 1 — game-designer spawned; produces `design/gdd/parry-riposte.md` covering all 8 required sections (overview, player fantasy, rules, formulas, edge cases, dependencies, tuning knobs, acceptance criteria); asks user to approve design doc
2. Phase 2 — gameplay-programmer + ai-programmer spawned; produce architecture sketch with class structure, interfaces, and file list; then primary engine specialist is spawned to validate idioms; engine specialist output incorporated; `request_user_input` presented with architecture options before Phase 3 begins
3. Phase 3 — gameplay-programmer, ai-programmer, technical-artist, sound-designer spawned in parallel; all four return outputs before Phase 4 begins
4. Phase 4 — integration wires together all Phase 3 outputs; tuning knobs verified as data-driven; `request_user_input` confirms integration before Phase 5
5. Phase 5 — qa-tester spawned; writes test cases from acceptance criteria; verifies edge cases; performance impact checked against budget
6. Phase 6 — summary report produced: design COMPLETE, all team members COMPLETE, test cases listed, verdict: COMPLETE
7. Next steps listed: `$code-review`, `$balance-check`, `$team-polish`

**Assertions:**
- [ ] `request_user_input` called at each phase gate (at minimum before Phase 3 and before Phase 5)
- [ ] Phase 3 agents launched simultaneously — no sequential dependency between gameplay-programmer, ai-programmer, technical-artist, sound-designer
- [ ] Engine specialist runs in Phase 2 before Phase 3 begins (output incorporated into architecture)
- [ ] All file writes delegated to child custom agents (orchestrator never calls Write/Edit directly)
- [ ] Verdict COMPLETE present in final report
- [ ] Next steps include `$code-review`, `$balance-check`, `$team-polish`
- [ ] Design doc covers all 8 required GDD sections

---

### Case 2: Blocked Agent — One subagent returns BLOCKED mid-pipeline

**Fixture:**
- `design/gdd/parry-riposte.md` exists (Phase 1 already complete)
- ai-programmer agent returns BLOCKED because no AI system architecture ADR exists (ADR status is Proposed)

**Input:** `$team-combat parry and riposte system`

**Expected behavior:**
1. Phase 1 — design doc found; game-designer confirms it is valid; phase approved
2. Phase 2 — gameplay-programmer completes architecture sketch; ai-programmer returns BLOCKED: "ADR for AI behavior system is Proposed — cannot implement until ADR is Accepted"
3. Error Recovery Protocol triggered: "ai-programmer: BLOCKED — AI behavior ADR is Proposed"
4. `request_user_input` presented with options: (a) Skip ai-programmer and note the gap; (b) Retry with narrower scope; (c) Stop here and run `$architecture-decision` first
5. If user chooses (a): Phase 3 proceeds with gameplay-programmer, technical-artist, sound-designer only; ai-programmer gap noted in partial report
6. Final report produced: partial implementation documented, ai-programmer section marked BLOCKED, overall verdict: BLOCKED

**Assertions:**
- [ ] BLOCKED surface message appears before any dependent phase continues
- [ ] `request_user_input` offers at minimum three options: skip / retry / stop
- [ ] Partial report produced — completed agents' work is not discarded
- [ ] Overall verdict is BLOCKED (not COMPLETE) when any agent is unresolved
- [ ] Blocked reason references the ADR and suggests `$architecture-decision`
- [ ] Orchestrator does not silently proceed past the blocked dependency

---

### Case 3: No Argument — Clear usage guidance shown

**Fixture:**
- Any project state

**Input:** `$team-combat` (no argument)

**Expected behavior:**
1. Skill detects no argument provided
2. Outputs usage message explaining the required argument (combat feature description)
3. Provides an example invocation: `$team-combat [combat feature description]`
4. Skill exits without spawning any subagents

**Assertions:**
- [ ] Skill does NOT spawn any subagents when no argument is given
- [ ] Usage message includes the invocation arguments format from frontmatter
- [ ] Error message includes at least one example of a valid invocation
- [ ] No file reads beyond what is needed to detect the missing argument
- [ ] Verdict is NOT shown (pipeline never runs)

---

### Case 4: Parallel Phase Validation — Phase 3 agents run simultaneously

**Fixture:**
- `design/gdd/parry-riposte.md` exists and is complete
- Architecture sketch has been approved
- Engine specialist has validated architecture

**Input:** `$team-combat parry and riposte system` (resuming from Phase 2 complete)

**Expected behavior:**
1. Phase 3 begins after architecture approval
2. All four child-agent delegations — gameplay-programmer, ai-programmer, technical-artist, sound-designer — are issued before any result is awaited
3. Skill waits for all four agents to complete before proceeding to Phase 4
4. If any single agent completes early, skill does not begin Phase 4 until all four have returned

**Assertions:**
- [ ] Four child-agent delegations issued in a single batch (no sequential waiting between them)
- [ ] Phase 4 does not begin until all four Phase 3 agents have returned results
- [ ] Skill does not pass one Phase 3 agent's output as input to another Phase 3 agent (they are independent)
- [ ] All four Phase 3 agent results referenced in the Phase 4 integration step

---

### Case 5: Architecture Phase Engine Routing — Engine specialist receives correct context

**Fixture:**
- `.codex/docs/technical-preferences.md` has Engine Specialists section populated (e.g., Primary: godot-specialist)
- Architecture sketch produced by gameplay-programmer is available
- Engine version pinned in `docs/engine-reference/godot/VERSION.md`

**Input:** `$team-combat parry and riposte system`

**Expected behavior:**
1. Phase 2 — gameplay-programmer produces architecture sketch
2. Skill reads `.codex/docs/technical-preferences.md` Engine Specialists section to identify the primary engine specialist agent type
3. Engine specialist is spawned with: the architecture sketch, the GDD path, the engine version from `VERSION.md`, and explicit instructions to check for deprecated APIs
4. Engine specialist output (idiom notes, deprecated API warnings, native system recommendations) is returned to orchestrator
5. Orchestrator incorporates engine notes into the architecture before presenting Phase 2 results to user
6. `request_user_input` includes engine specialist's notes alongside the architecture sketch

**Assertions:**
- [ ] Engine specialist agent type is read from `.codex/docs/technical-preferences.md` — not hardcoded
- [ ] Engine specialist prompt includes the architecture sketch and GDD path
- [ ] Engine specialist checks for deprecated APIs against the pinned engine version
- [ ] Engine specialist output is incorporated before Phase 3 begins (not skipped or appended separately)
- [ ] If no engine is configured, engine specialist step is skipped and a note is added to the report

---

## Protocol Compliance

- [ ] `request_user_input` used at each phase transition — user approves before pipeline advances
- [ ] Any delegated file write is bounded to a direct child custom agent; the orchestrator remains responsible for synthesis and scope
- [ ] Error Recovery Protocol followed: surface → assess → offer options → partial report
- [ ] Phase 3 agents launched in parallel per skill spec
- [ ] Partial report always produced even when agents are BLOCKED
- [ ] Verdict is one of COMPLETE / NEEDS WORK / BLOCKED
- [ ] Next steps present at end of output: `$code-review`, `$balance-check`, `$team-polish`

---

## Coverage Notes

- The NEEDS WORK verdict path (qa-tester finds failures in Phase 5) is not separately tested
  here; it follows the same error recovery and partial report protocol as Case 2.
- "Retry with narrower scope" error recovery option is listed in assertions but its full
  recursive behavior (splitting via `$create-stories`) is covered by the `$create-stories` spec.
- Phase 4 integration logic (wiring gameplay, AI, VFX, audio) is validated implicitly by
  the Happy Path case; a dedicated integration test would require fixture code files.
- Engine specialist unavailable (no engine configured) is partially covered in Case 5
  assertions — a dedicated fixture for unconfigured engine state would strengthen coverage.
