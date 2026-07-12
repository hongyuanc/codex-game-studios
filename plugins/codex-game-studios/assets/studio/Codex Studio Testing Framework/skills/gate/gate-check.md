# Skill Test Spec: $gate-check

## Codex Runtime Contract

- Runtime skill: `.agents/skills/gate-check/SKILL.md`
- Runtime name: `gate-check`
- Runtime trigger description: `Evaluate readiness to advance to a named development phase and issue a PASS, CONCERNS, or FAIL verdict.`
- Native invocation: `$gate-check`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$gate-check` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has ≥2 phase headings (numbered Phase N or ## sections)
- [ ] Contains verdict keywords: PASS, CONCERNS, FAIL
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (Follow-Up Actions section)

---

## Test Cases

### Case 1: Happy Path — All Concept artifacts present, advancing to Systems Design

**Fixture:**
- `design/gdd/game-concept.md` exists, has content including all required sections
- `design/gdd/game-pillars.md` exists (or pillars defined within concept doc)
- No systems index yet (which is correct for this stage)

**Input:** `$gate-check systems-design`

**Expected behavior:**
1. Skill reads `design/gdd/game-concept.md` and verifies it has content
2. Skill checks for game pillars (in concept or separate file)
3. Skill checks quality items (core loop described, target audience identified)
4. Skill outputs structured checklist with all items marked
5. Skill presents PASS/CONCERNS/FAIL verdict
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Skill uses Glob or Read to verify `design/gdd/game-concept.md` exists before marking it checked
- [ ] Output includes a "Required Artifacts" section with check status per item
- [ ] Output includes a "Quality Checks" section with check status per item
- [ ] Output includes a "Verdict" line with one of PASS / CONCERNS / FAIL
- [ ] Skill asks about unverifiable quality items (e.g., "Has this been reviewed?") rather than assuming PASS
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill does NOT write `production/stage.txt` without explicit user confirmation

---

### Case 2: Failure Path — Missing required artifacts for Concept → Systems Design

**Fixture:**
- `design/gdd/game-concept.md` does NOT exist
- No game pillars document exists
- `design/gdd/` directory is empty or absent

**Input:** `$gate-check systems-design`

**Expected behavior:**
1. Skill attempts to read `design/gdd/game-concept.md` — file not found
2. Skill marks required artifact as missing (not present)
3. Skill outputs FAIL verdict
4. Skill lists blocker: "No game concept document found"
5. Skill suggests remediation: run `$brainstorm` to create one

**Assertions:**
- [ ] Verdict is FAIL (not PASS or CONCERNS) when required artifacts are missing
- [ ] Output explicitly names `design/gdd/game-concept.md` as missing
- [ ] Output includes a "Blockers" section with at least 1 item
- [ ] Output recommends `$brainstorm` as the remediation action
- [ ] Skill does NOT write `production/stage.txt` when verdict is FAIL

---

### Case 3: No Argument — Auto-detect current stage

**Fixture:**
- `production/stage.txt` contains `Concept`
- `design/gdd/game-concept.md` exists with content
- No systems index yet

**Input:** `$gate-check` (no argument)

**Expected behavior:**
1. Skill reads `production/stage.txt` to determine current stage
2. Skill determines the next gate is Concept → Systems Design
3. Skill proceeds with the Systems Design gate checks
4. Output clearly states which transition is being validated

**Assertions:**
- [ ] Skill reads `production/stage.txt` (or uses project-stage-detect heuristics) to determine current stage
- [ ] Output header names both current and target phases (e.g., "Gate Check: Concept → Systems Design")
- [ ] Skill does not ask the user which gate to check if current stage is determinable

---

### Case 4: Edge Case — Manual check items flagged correctly

**Fixture:**
- All required artifacts for Concept → Systems Design are present
- No playtest or review record exists (can't auto-verify quality checks)

**Input:** `$gate-check systems-design`

**Expected behavior:**
1. Skill verifies all artifact files exist
2. Skill encounters quality check: "Game concept reviewed (not MAJOR REVISION NEEDED)"
3. Since no review record exists, skill marks item as MANUAL CHECK NEEDED
4. Skill asks the user: "Has the game concept been reviewed for design quality?"
5. Skill waits for user input before finalizing verdict

**Assertions:**
- [ ] Items that cannot be auto-verified are marked `[?] MANUAL CHECK NEEDED` rather than assumed PASS
- [ ] Skill uses a question to the user for at least one unverifiable quality item
- [ ] Skill does not mark unverifiable items as PASS by default

---

---

### Case 5: Director Gate — phase-gated vs full vs solo mode

For phase transitions, mandatory `*-PHASE-GATE` directors run in `full`, `phase-gated`, and `solo`; only optional gates vary by review mode.

**Fixture:**
- `.codex/studio.toml` exists (or equivalent state file)
- All required artifacts for the target gate are present
- `design/gdd/game-concept.md` exists

**Case 5a — full mode:**
- `.codex/studio.toml` contains `full`

**Input:** `$gate-check systems-design` (with full mode active)

**Expected behavior:**
1. Skill reads review mode — determines `full`
2. Skill spawns all 4 PHASE-GATE director prompts in parallel:
   - CD-PHASE-GATE (creative-director)
   - TD-PHASE-GATE (technical-director)
   - PR-PHASE-GATE (producer)
   - AD-PHASE-GATE (art-director)
3. If one director returns CONCERNS → overall gate verdict is at minimum CONCERNS
4. All 4 verdicts are collected before producing final output

**Assertions (5a):**
- [ ] Skill reads review-mode before deciding which directors to spawn
- [ ] All 4 PHASE-GATE director prompts are spawned (not just 1 or 2)
- [ ] Directors are spawned in parallel (simultaneous, not sequential)
- [ ] A CONCERNS verdict from any one director propagates to overall verdict
- [ ] Verdict is NOT auto-PASS if any director returns CONCERNS or REJECT

**Case 5b — phase-gated and solo modes:**
- `.codex/studio.toml` contains `phase-gated` or `solo`

**Input:** `$gate-check systems-design`

**Expected behavior:**
1. Skill reads the review mode.
2. Skill still spawns CD-PHASE-GATE, TD-PHASE-GATE, PR-PHASE-GATE, and AD-PHASE-GATE in parallel because they are mandatory.
3. The parent waits for and synthesizes all four verdicts.
4. Optional inline gates remain skipped according to the selected mode.

**Assertions (5b):**
- [ ] All four mandatory PHASE-GATE directors run in phase-gated and solo modes.
- [ ] Only optional gates vary by review mode.
- [ ] A CONCERNS or REJECT verdict still propagates to the overall result.

**Note on Case 3 correction:**
The Case 3 assertions previously stated "Skill does not ask the user which gate to check
if current stage is determinable." This is correct. However, the skill DOES use
request_user_input to confirm the auto-detected transition before running full checks —
this is a confirmation step, not a gate selection. Assertions for Case 3 should not
treat this confirmation as a failure.

---

## Protocol Compliance

- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Presents the full checklist report before asking for write approval
- [ ] Ends with a "Follow-Up Actions" section listing next steps per verdict
- [ ] Never advances the stage without explicit user confirmation
- [ ] Never auto-creates `production/stage.txt` if it doesn't exist without asking

---

## Coverage Notes

- The Production → Polish and Polish → Release gates are not covered here
  because they require complex multi-artifact setups (sprint plans, playtest
  data, QA sign-off); these are deferred to dedicated follow-up specs.
- The "CONCERNS" verdict path (minor gaps, not blocking) is not explicitly
  tested here; it falls between Case 1 and Case 2 and follows the same pattern.
- The Vertical Slice validation block (Pre-Production → Production gate) is not
  covered because it requires a playable build context that cannot be expressed
  as a document fixture.
