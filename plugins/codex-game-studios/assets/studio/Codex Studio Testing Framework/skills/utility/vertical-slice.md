# Skill Test Spec: $vertical-slice

## Codex Runtime Contract

- Runtime skill: `.agents/skills/vertical-slice/SKILL.md`
- Runtime name: `vertical-slice`
- Runtime trigger description: `Build and evaluate a production-quality vertical slice before advancing from Pre-Production to Production.`
- Native invocation: `$vertical-slice`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

## Skill Summary

`$vertical-slice` validates whether one representative start → challenge →
resolution loop can reach production quality at a credible production velocity.
It requires approved design, architecture, UX, and an active engine pack; bounds
the slice to a 3–5 minute loop; records automated, manual, playtest, and velocity
evidence; and ends in `PROCEED`, `PIVOT`, or `KILL`. It never advances the project
stage implicitly.

## Static Assertions

- [ ] Reads `AGENTS.md`, the concept, systems index, architecture, control
  manifest, and relevant GDDs before planning implementation.
- [ ] Defines a falsifiable player-experience and production-feasibility question.
- [ ] Presents every initial implementation path, test, and risk as one complete
  proposed changeset before editing.
- [ ] Pauses for any material scope expansion or unresolved architecture conflict.
- [ ] Requires a playable loop, test evidence, a playtest debrief, and a velocity log.
- [ ] Uses only direct child custom agents and retains parent synthesis.
- [ ] Emits only `PROCEED`, `PIVOT`, or `KILL` as the final recommendation.

## Test Cases

### Case 1: Happy Path — Representative loop reaches production quality

**Fixture:**
- One engine pack is active and its version reference is available.
- Approved game concept, systems index, GDDs, architecture, control manifest,
  UX specs, and measurable acceptance criteria exist.
- The approved slice is one 4-minute start → challenge → resolution loop.
- Automated tests pass, one unguided playtest completes the loop, and the actual
  build duration stays inside the approved timebox.

**Expected behavior:**
1. Read all upstream artifacts and state the falsifiable validation question.
2. Present the bounded file list, systems, tests, evidence paths, risks, and hard
   time limit as one complete proposed changeset.
3. After approval, implement and verify only that scope.
4. Collect debrief answers one decision at a time and record actual velocity.
5. Produce a report and recommend `PROCEED` without changing the project stage.

**Assertions:**
- [ ] The loop exercises every system required for one complete cycle.
- [ ] Automated and manual/playtest evidence are both cited.
- [ ] The velocity log contains actual elapsed work, not an estimate.
- [ ] `PROCEED` is evidence-backed and no production transition is automatic.

### Case 2: Blocked Preconditions — Upstream artifact or engine pack is missing

**Fixture:**
- No engine pack is active, or the architecture/control manifest/UX spec is
  absent or not approved.

**Expected behavior:**
1. Detect the missing prerequisite during context loading.
2. Return `BLOCKED` with the exact missing path or configuration.
3. Recommend the appropriate setup or design workflow.
4. Do not create a prototype directory, implementation file, report, or session
   checkpoint.

**Assertions:**
- [ ] The blocker names the exact missing prerequisite.
- [ ] No child implementation agent is delegated work.
- [ ] No file is written and no final slice verdict is fabricated.

### Case 3: Scope Boundary — Requested feature exceeds the approved slice

**Fixture:**
- A 3-minute combat loop is approved.
- During implementation, a request adds crafting progression and a second level,
  neither required by the validation question nor listed in the changeset.

**Expected behavior:**
1. Preserve completed in-scope evidence.
2. Identify both additions as material scope expansion.
3. Stop dependent work and present cut, defer, or revise-scope options through
   one structured decision turn.
4. Continue only after a revised complete proposed changeset is approved.

**Assertions:**
- [ ] The new systems are not silently implemented.
- [ ] `request_user_input`, if used, has one question and 2–3 options.
- [ ] Existing approval is not treated as authorization for the expanded scope.
- [ ] Cutting content is preferred to reducing representative quality.

### Case 4: Evidence Failure — Playable loop lacks release-quality proof

**Fixture:**
- The loop launches and can be completed.
- A critical automated test fails and the only playtest was a guided developer
  walkthrough with no recorded observations.

**Expected behavior:**
1. Report the failing test and inadequate playtest evidence.
2. Do not recommend `PROCEED` merely because the build launches.
3. Recommend a bounded fix/retest or `PIVOT`, depending on whether the failure is
   implementation-local or invalidates an architecture/design assumption.
4. Keep unresolved evidence visible in the report.

**Assertions:**
- [ ] Failed automated evidence is blocking, not downgraded to a note.
- [ ] Guided observation is not represented as an unguided playtest.
- [ ] The recommendation is `PIVOT` or remains blocked pending retest, never an
  unsupported `PROCEED`.

### Case 5: Final Gate — Direct-child creative review and explicit disposition

**Fixture:**
- Full review mode is active and the report, validation question, pillars,
  playtest evidence, and velocity log are complete.
- The creative review finds that the mechanic works technically but fails the
  named player-fantasy pillar.

**Expected behavior:**
1. Delegate one bounded `CD-PLAYTEST` review to the `creative-director` profile.
2. Give the child only the relevant report and design context.
3. Receive the child's evidence; do not allow it to delegate further, write,
   commit, publish, or question the user.
4. Have the parent agent synthesize the technical and creative evidence.
5. Recommend `PIVOT`, record what should be preserved and what failed, and wait
   for explicit user direction before any stage or design change.

**Assertions:**
- [ ] The maximum delegation depth is 1.
- [ ] The child result returns to the parent agent for synthesis.
- [ ] The pillar conflict prevents `PROCEED`.
- [ ] The final outcome is exactly `PIVOT`; project stage remains unchanged.

## Protocol Compliance

- [ ] Uses `$vertical-slice` natively.
- [ ] Keeps user decisions sequential and structured choices within schema.
- [ ] Treats implementation and report paths as approved complete changesets.
- [ ] Preserves evidence across a stop, pivot, or child-agent failure.
- [ ] Never commits, publishes, releases, or advances production implicitly.

## Coverage Notes

- Engine-specific execution commands belong to the active engine pack and are
  intentionally not duplicated here.
- External playtester recruitment and distribution remain user-controlled.
