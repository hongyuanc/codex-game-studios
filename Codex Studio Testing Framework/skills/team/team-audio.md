# Skill Test Spec: $team-audio

## Codex Runtime Contract

- Runtime skill: `.agents/skills/team-audio/SKILL.md`
- Runtime name: `team-audio`
- Runtime trigger description: `"Use when an audio feature needs coordinated direction, sound design, technical integration, and gameplay hooks."`
- Native invocation: `$team-audio`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$team-audio` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

Validation is read-only. If the workflow writes, the parent first presents one
complete proposed changeset containing every target path and material edit; any
new path or scope expansion requires fresh approval. If it delegates, direct
children return scoped evidence and the parent synthesizes the result.

---

## Static Assertions (Structural)

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 step/phase headings
- [ ] Contains verdict keywords: COMPLETE, BLOCKED
- [ ] Contains "File Write Protocol" section
- [ ] File writes are delegated to child custom agents — orchestrator does not write files directly
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (references `$dev-story`, `$asset-audit`)
- [ ] Error Recovery Protocol section is present
- [ ] `request_user_input` is used at step transitions before proceeding
- [ ] Step 2 explicitly spawns sound-designer and accessibility-specialist in parallel
- [ ] Step 3 explicitly spawns technical-artist and engine specialist in parallel (when engine is configured)
- [ ] Skill reads `design/gdd/sound-bible.md` during context gathering if it exists
- [ ] Output document is saved to `design/gdd/audio-[feature].md`

---

## Test Cases

### Case 1: Happy Path — All steps complete, audio design document saved

**Fixture:**
- GDD for the target feature exists at `design/gdd/combat.md`
- Sound bible exists at `design/gdd/sound-bible.md`
- Existing audio assets are listed in `assets/audio/`
- Engine is configured in `.codex/docs/technical-preferences.md`
- No accessibility gaps exist in the planned audio event list

**Input:** `$team-audio combat`

**Expected behavior:**
1. Context gathering: orchestrator reads `design/gdd/combat.md`, `design/gdd/sound-bible.md`, and `assets/audio/` asset list before spawning any agent
2. Step 1: audio-director is spawned; defines sonic identity, emotional tone, adaptive music direction, mix targets, and adaptive audio rules for combat
3. `request_user_input` presents audio direction; user approves before Step 2 begins
4. Step 2: sound-designer and accessibility-specialist are spawned in parallel; sound-designer produces SFX specifications, audio event list with trigger conditions, and mixing groups; accessibility-specialist identifies critical gameplay audio events and specifies visual fallback and subtitle requirements
5. `request_user_input` presents SFX spec and accessibility requirements; user approves before Step 3 begins
6. Step 3: technical-artist and primary engine specialist are spawned in parallel; technical-artist designs bus structure, middleware integration, memory budgets, and streaming strategy; engine specialist validates that the integration approach is idiomatic for the configured engine
7. `request_user_input` presents technical plan; user approves before Step 4 begins
8. Step 4: gameplay-programmer is spawned; wires up audio events to gameplay triggers, implements adaptive music, sets up occlusion zones, writes unit tests for audio event triggers
9. Orchestrator compiles all outputs into a single audio design document
10. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
11. Summary output lists: audio event count, estimated asset count, implementation tasks, and any open questions
12. Verdict: COMPLETE

**Assertions:**
- [ ] Sound bible is read during context gathering (before Step 1) when it exists
- [ ] audio-director is spawned before sound-designer or accessibility-specialist
- [ ] `request_user_input` appears after Step 1 output and before Step 2 launch
- [ ] sound-designer and accessibility-specialist child-agent delegations are issued simultaneously in Step 2
- [ ] technical-artist and engine specialist child-agent delegations are issued simultaneously in Step 3
- [ ] gameplay-programmer is not launched until Step 3 `request_user_input` is approved
- [ ] Audio design document is written to `design/gdd/audio-combat.md` (not another path)
- [ ] Summary includes audio event count and estimated asset count
- [ ] No files are written by the orchestrator directly
- [ ] Verdict is COMPLETE after document delivery

---

### Case 2: Accessibility Gap — Critical gameplay audio event has no visual fallback

**Fixture:**
- GDD for the target feature exists
- Step 1 and Step 2 are in progress
- sound-designer's audio event list includes "EnemyNearbyAlert" — a spatial audio cue that warns the player an enemy is approaching from off-screen
- accessibility-specialist reviews the event list and finds "EnemyNearbyAlert" has no visual fallback (no on-screen indicator, no subtitle, no controller rumble specified)

**Input:** `$team-audio stealth` (Step 2 scenario)

**Expected behavior:**
1. Steps 1–2 proceed; accessibility-specialist and sound-designer are spawned in parallel
2. accessibility-specialist returns its review with a BLOCKING concern: "`EnemyNearbyAlert` is a critical gameplay audio event (warns player of off-screen threat) with no visual fallback — hearing-impaired players cannot detect this threat. This is a BLOCKING accessibility gap."
3. Orchestrator surfaces the concern immediately in conversation before presenting `request_user_input`
4. `request_user_input` presents the accessibility concern as a BLOCKING issue with options:
   - Add a visual indicator for EnemyNearbyAlert (e.g., directional arrow on HUD) and continue
   - Add controller haptic feedback as the fallback and continue
   - Stop here and resolve all accessibility gaps before proceeding to Step 3
5. Step 3 (technical-artist + engine specialist) is not launched until the user resolves or explicitly accepts the gap
6. The accessibility gap is included in the final audio design document under "Open Accessibility Issues" if unresolved

**Assertions:**
- [ ] Accessibility gap is labeled BLOCKING (not advisory) in the report
- [ ] The specific event name ("EnemyNearbyAlert") and the nature of the gap are stated
- [ ] `request_user_input` surfaces the gap before Step 3 is launched
- [ ] At least one resolution option is offered (add visual fallback, add haptic fallback)
- [ ] Step 3 is not launched while the gap is unresolved without explicit user authorization
- [ ] If the gap is carried forward unresolved, it is documented in the audio design doc as an open issue

---

### Case 3: No Argument — Usage guidance or design doc inference

**Fixture:**
- Any project state

**Input:** `$team-audio` (no argument)

**Expected behavior:**
1. Skill detects no argument is provided
2. Outputs usage guidance: e.g., "Usage: `$team-audio [feature or area]` — specify the feature or area to design audio for (e.g., `combat`, `main menu`, `forest biome`, `boss encounter`)"
3. Skill exits without spawning any agents

**Assertions:**
- [ ] Skill does NOT spawn any agents when no argument is provided
- [ ] Usage message includes the correct invocation format with argument examples
- [ ] Skill does NOT attempt to infer a feature from existing design docs without user direction
- [ ] No `request_user_input` is used — output is direct guidance

---

### Case 4: Missing Sound Bible — Skill notes the gap and proceeds without it

**Fixture:**
- GDD for the target feature exists at `design/gdd/main-menu.md`
- `design/gdd/sound-bible.md` does NOT exist
- Engine is configured; other context files are present

**Input:** `$team-audio main menu`

**Expected behavior:**
1. Context gathering: orchestrator reads `design/gdd/main-menu.md` and checks for `design/gdd/sound-bible.md`
2. Sound bible is not found; orchestrator notes the gap in conversation: "Note: `design/gdd/sound-bible.md` not found — audio direction will proceed without a project-wide sonic identity reference. Consider creating a sound bible if this is an ongoing project."
3. Pipeline proceeds normally through all four steps without the sound bible as input
4. audio-director in Step 1 is informed that no sound bible exists and must establish sonic identity from the feature GDD alone
5. The missing sound bible is mentioned in the final summary as a recommended next step

**Assertions:**
- [ ] Orchestrator checks for the sound bible during context gathering (before Step 1)
- [ ] Missing sound bible is noted explicitly in conversation — not silently ignored
- [ ] Pipeline does NOT halt due to the missing sound bible
- [ ] audio-director is notified that no sound bible exists in its prompt context
- [ ] Summary or Next Steps section recommends creating a sound bible
- [ ] Verdict is still COMPLETE if all other steps succeed

---

### Case 5: Engine Not Configured — Engine specialist step skipped gracefully

**Fixture:**
- Engine is NOT configured in `.codex/docs/technical-preferences.md` (shows `[TO BE CONFIGURED]`)
- GDD for the target feature exists
- Sound bible may or may not exist

**Input:** `$team-audio boss encounter`

**Expected behavior:**
1. Context gathering: orchestrator reads `.codex/docs/technical-preferences.md` and detects no engine is configured
2. Steps 1–2 proceed normally (audio-director, sound-designer, accessibility-specialist)
3. Step 3: technical-artist is spawned normally; engine specialist spawn is SKIPPED
4. Orchestrator notes in conversation: "Engine specialist not spawned — no engine configured in technical-preferences.md. Engine integration validation will be deferred until an engine is selected."
5. Step 4: gameplay-programmer proceeds with a note that engine-specific audio integration patterns could not be validated
6. The engine specialist gap is included in the audio design document under "Deferred Validation"
7. Verdict: COMPLETE (skip is graceful, not a blocker)

**Assertions:**
- [ ] Engine specialist is NOT spawned when no engine is configured
- [ ] Skill does NOT error out due to the missing engine configuration
- [ ] The skip is explicitly noted in conversation — not silently omitted
- [ ] technical-artist is still spawned in Step 3 (skip applies only to the engine specialist)
- [ ] gameplay-programmer proceeds in Step 4 with the deferred validation noted
- [ ] Deferred engine validation is recorded in the audio design document
- [ ] Verdict is COMPLETE (engine not configured is a known graceful case)

---

## Protocol Compliance

- [ ] Context gathering (GDDs, sound bible, asset list) runs before any agent is spawned
- [ ] `request_user_input` is used after every step output before the next step launches
- [ ] Parallel spawning: Step 2 (sound-designer + accessibility-specialist) and Step 3 (technical-artist + engine specialist) issue all child-agent delegations before waiting for results
- [ ] No files are written by the orchestrator directly — all writes are delegated to child custom agents
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] BLOCKED status from any agent is surfaced immediately — not silently skipped
- [ ] A partial report is always produced when some agents complete and others block
- [ ] Audio design document path follows the pattern `design/gdd/audio-[feature].md`
- [ ] Verdict is exactly COMPLETE or BLOCKED — no other verdict values used
- [ ] Next Steps handoff references `$dev-story` and `$asset-audit`

---

## Coverage Notes

- The "Retry with narrower scope" and "Skip this agent" resolution paths from the Error
  Recovery Protocol are not separately tested — they follow the same `request_user_input`
  + partial-report pattern validated in Cases 2 and 5.
- Step 4 (gameplay-programmer) happy-path behavior is validated implicitly by Case 1.
  Failure modes for this step follow the standard Error Recovery Protocol.
- The accessibility-specialist's subtitle and caption requirements (beyond visual fallbacks)
  are validated implicitly by Case 1. Case 2 focuses on the more severe case where a
  critical gameplay event has no fallback at all.
- Engine specialist validation logic (idiomatic integration, version-specific changes) is
  tested only for the configured and unconfigured states. The specific content of the
  engine specialist's output is out of scope for this behavioral spec.
