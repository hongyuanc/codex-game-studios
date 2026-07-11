# Skill Test Spec: $sprint-plan

## Codex Runtime Contract

- Runtime skill: `.agents/skills/sprint-plan/SKILL.md`
- Runtime name: `sprint-plan`
- Runtime trigger description: `"Use when a sprint needs creation, replanning, capacity allocation, milestone alignment, or backlog prioritization."`
- Native invocation: `$sprint-plan`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$sprint-plan` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (what to do after sprint is written)

---

## Director Gate Checks

| Gate ID   | Trigger condition        | Mode guard         |
|-----------|--------------------------|--------------------|
| PR-SPRINT | After sprint draft built | full only (not phase-gated/solo) |

---

## Test Cases

### Case 1: Happy Path — Backlog with stories generates sprint

**Fixture:**
- `production/milestones/milestone-02.md` exists with capacity `10 story points`
- Backlog contains 5 unstarted stories across 2 epics, mixed priorities
- `.codex/studio.toml` contains `full`
- Next sprint number is `003` (sprints 001 and 002 already exist)

**Input:** `$sprint-plan`

**Expected behavior:**
1. Skill reads current milestone to obtain capacity and goals
2. Skill reads all unstarted stories from backlog; sorts by layer + priority
3. Skill drafts sprint-003 with stories fitting within capacity
4. Skill presents draft to user before invoking gate
5. Skill invokes PR-SPRINT gate (full mode); producer approves
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
7. User approves; file is written

**Assertions:**
- [ ] Stories are sorted by implementation layer before priority
- [ ] Sprint draft is shown before any write or gate invocation
- [ ] PR-SPRINT gate is invoked in full mode after draft is ready
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Written file path matches `production/sprints/sprint-003.md`
- [ ] Verdict is COMPLETE after successful write

---

### Case 2: Blocked Path — Backlog is empty

**Fixture:**
- `production/milestones/milestone-02.md` exists
- No unstarted stories exist in any epic backlog

**Input:** `$sprint-plan`

**Expected behavior:**
1. Skill reads backlog — finds no unstarted stories
2. Skill outputs "No unstarted stories in backlog"
3. Skill suggests running `$create-stories` to populate the backlog
4. No gate is invoked; no file is written

**Assertions:**
- [ ] Verdict is BLOCKED
- [ ] Output contains "No unstarted stories" or equivalent message
- [ ] Output recommends `$create-stories`
- [ ] PR-SPRINT gate is NOT invoked
- [ ] No write tool is called

---

### Case 3: Gate returns CONCERNS — Sprint overloaded, revised before write

**Fixture:**
- Backlog has 8 stories totalling 16 points; milestone capacity is 10 points
- `.codex/studio.toml` contains `full`

**Input:** `$sprint-plan`

**Expected behavior:**
1. Skill drafts sprint with all 8 stories (over capacity)
2. PR-SPRINT gate runs; producer returns CONCERNS: sprint is overloaded
3. Skill presents concern to user and asks which stories to defer
4. User selects 3 stories to defer; sprint is revised to 5 stories / 10 points
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] CONCERNS from PR-SPRINT gate surfaces to user before any write
- [ ] Skill allows sprint to be revised after gate feedback
- [ ] Revised sprint (not original) is written to file
- [ ] Verdict is COMPLETE after revision and write

---

### Case 4: Phase-gated Mode — PR-SPRINT gate skipped

**Fixture:**
- Backlog has 4 stories; milestone capacity is 8 points
- `.codex/studio.toml` contains `phase-gated`

**Input:** `$sprint-plan`

**Expected behavior:**
1. Skill reads review mode — determines `phase-gated`
2. Skill drafts sprint and presents it to user
3. PR-SPRINT gate is skipped; output notes "[PR-SPRINT] skipped — Phase-gated mode"
4. Skill asks user for direct approval of the sprint
5. User approves; sprint file is written

**Assertions:**
- [ ] PR-SPRINT gate is NOT invoked in phase-gated mode
- [ ] Skip is explicitly noted in output
- [ ] User approval is still required before write (gate skip ≠ approval skip)
- [ ] Verdict is COMPLETE after write

---

### Case 5: Edge Case — Previous sprint still has open stories

**Fixture:**
- `production/sprints/sprint-002.md` exists with 2 stories still `Status: In Progress`
- Backlog has 5 new unstarted stories
- `.codex/studio.toml` contains `full`

**Input:** `$sprint-plan`

**Expected behavior:**
1. Skill reads sprint-002 and detects 2 open (in-progress) stories
2. Skill flags: "Sprint 002 has 2 open stories — confirm carry-over before planning sprint 003"
3. Skill presents user with choice: carry stories over, defer them, or cancel
4. User confirms carry-over; carried stories are prepended to new sprint with `[CARRY]` tag
5. Sprint draft is built; PR-SPRINT gate runs; sprint is written on approval

**Assertions:**
- [ ] Skill checks the most recent sprint file for open stories
- [ ] User is asked to confirm carry-over before sprint planning continues
- [ ] Carried stories appear in the new sprint draft with a distinguishing label
- [ ] Skill does not silently ignore open stories from the previous sprint

---

## Protocol Compliance

- [ ] Shows draft sprint before invoking PR-SPRINT gate or asking to write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] PR-SPRINT gate only runs in full mode
- [ ] Skip message appears in phase-gated and solo mode output
- [ ] Verdict is clearly stated at the end of the skill output

---

## Coverage Notes

- The case where no milestone file exists is not explicitly tested; behavior
  follows the BLOCKED pattern with a suggestion to run `$gate-check` for
  milestone progression.
- Solo mode behavior is equivalent to phase-gated (gate skipped, user approval
  required) and is not separately tested.
- Parallel story selection algorithms are not tested here; those are unit
  concerns for the sprint-plan subagent.
