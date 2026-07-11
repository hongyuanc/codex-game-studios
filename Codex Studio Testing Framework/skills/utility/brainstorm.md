# Skill Test Spec: $brainstorm

## Codex Runtime Contract

- Runtime skill: `.agents/skills/brainstorm/SKILL.md`
- Runtime name: `brainstorm`
- Runtime trigger description: `Guide game concept ideation from an initial premise to an approved game concept document.`
- Native invocation: `$brainstorm`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$brainstorm` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: APPROVED, REJECTED, CONCERNS
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (`$map-systems`)
- [ ] Documents 4 director gates in full mode: CD-PILLARS, AD-CONCEPT-VISUAL, TD-FEASIBILITY, PR-SCOPE
- [ ] Documents that all 4 gates are skipped in phase-gated and solo modes

---

## Director Gate Checks

In `full` mode: CD-PILLARS, AD-CONCEPT-VISUAL, TD-FEASIBILITY, and PR-SCOPE
spawn in parallel after the concept draft is approved by the user.

In `phase-gated` mode: all 4 inline gates are skipped (brainstorm has no PHASE-GATEs,
so phase-gated mode skips everything). Output notes all 4 as: "[GATE-ID] skipped — phase-gated mode".

In `solo` mode: all 4 gates are skipped. Output notes all 4 as: "[GATE-ID] skipped — solo mode".

---

## Test Cases

### Case 1: Happy Path — Full mode, 3 concepts, user picks one, all 4 directors approve

**Fixture:**
- No existing `design/gdd/game-concept.md`
- `.codex/studio.toml` contains `full`

**Input:** `$brainstorm`

**Expected behavior:**
1. Skill asks the user questions about genre, scope, and target feeling
2. Skill presents 3 concept options with pros/cons each
3. User selects one concept
4. Skill elaborates the chosen concept into a structured draft
5. All 4 director gates spawn in parallel: CD-PILLARS, AD-CONCEPT-VISUAL, TD-FEASIBILITY, PR-SCOPE
6. All 4 return APPROVED
7. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
8. Concept written after approval

**Assertions:**
- [ ] Exactly 3 concept options are presented (not 1, not 5+)
- [ ] All 4 director gates spawn in parallel (not sequentially)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Concept file is NOT written without user approval
- [ ] Next-step handoff to `$map-systems` is present

---

### Case 2: Failure Path — CD-PILLARS returns REJECT

**Fixture:**
- Concept draft is complete
- `.codex/studio.toml` contains `full`
- CD-PILLARS gate returns REJECT: "The concept has no identifiable creative pillar"

**Input:** `$brainstorm`

**Expected behavior:**
1. CD-PILLARS gate returns REJECT with specific feedback
2. Skill surfaces the rejection to the user
3. Concept is NOT written to file
4. User is asked: rethink the concept direction, or override the rejection
5. If rethinking: skill returns to the concept options phase

**Assertions:**
- [ ] Concept is NOT written when CD-PILLARS returns REJECT
- [ ] Rejection feedback is shown to the user verbatim
- [ ] User is given the option to rethink or override
- [ ] Skill returns to concept ideation phase if user chooses to rethink

---

### Case 3: Phase-gated Mode — All 4 gates skipped; concept written after user confirms

**Fixture:**
- No existing game concept
- `.codex/studio.toml` contains `phase-gated`

**Input:** `$brainstorm`

**Expected behavior:**
1. Concept options are presented and user selects one
2. Concept is elaborated into a structured draft
3. All 4 director gates are skipped — each noted: "[GATE-ID] skipped — phase-gated mode"
4. Skill asks user to confirm the concept is ready to write
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Concept written after approval

**Assertions:**
- [ ] All 4 gate skip notes appear: "CD-PILLARS skipped — phase-gated mode", "AD-CONCEPT-VISUAL skipped — phase-gated mode", "TD-FEASIBILITY skipped — phase-gated mode", "PR-SCOPE skipped — phase-gated mode"
- [ ] Concept is written after user confirmation only (no director approval needed in phase-gated)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 4: Solo Mode — All gates skipped; concept written with only user approval

**Fixture:**
- No existing game concept
- `.codex/studio.toml` contains `solo`

**Input:** `$brainstorm`

**Expected behavior:**
1. Concept options are presented and user selects one
2. Concept draft is shown to user
3. All 4 director gates are skipped — each noted with "solo mode"
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Concept written after user approval

**Assertions:**
- [ ] All 4 skip notes appear with "solo mode" label
- [ ] No director agents are spawned
- [ ] Concept is written with only user approval
- [ ] Behavior is otherwise equivalent to phase-gated mode for this skill

---

### Case 5: Director Gate — PR-SCOPE returns CONCERNS (scope too large)

**Fixture:**
- Concept draft is complete
- `.codex/studio.toml` contains `full`
- PR-SCOPE gate returns CONCERNS: "The concept scope would require 18+ months for a solo developer"

**Input:** `$brainstorm`

**Expected behavior:**
1. PR-SCOPE gate returns CONCERNS with specific scope feedback
2. Skill surfaces the scope concerns to the user
3. Scope concerns are documented in the concept draft before writing
4. User is asked: reduce scope, accept concerns and document them, or rethink
5. If concerns are accepted: concept is written with a "Scope Risk" note embedded

**Assertions:**
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill does NOT write concept without surfacing scope concerns
- [ ] If user accepts: scope concerns are documented in the concept file
- [ ] Skill does NOT auto-reject a concept due to PR-SCOPE CONCERNS (user decides)

---

## Protocol Compliance

- [ ] Presents 2-4 concept options with pros/cons before user commits
- [ ] User confirms concept direction before director gates are invoked
- [ ] All 4 director gates spawn in parallel in full mode
- [ ] All 4 gates skipped in phase-gated AND solo mode — each noted by name
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Ends with next-step handoff: `$map-systems`

---

## Coverage Notes

- AD-CONCEPT-VISUAL gate (art director feasibility) is grouped with the other
  3 gates in the parallel spawn — not independently fixture-tested.
- The iterative concept refinement loop (user rejects all options, skill
  generates new ones) is not fixture-tested — it follows the same pattern as
  the option selection phase.
- The game-concept.md document structure (required sections) is defined in the
  skill body and not re-enumerated in test assertions.
