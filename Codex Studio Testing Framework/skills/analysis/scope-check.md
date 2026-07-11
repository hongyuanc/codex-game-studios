# Skill Test Spec: $scope-check

## Codex Runtime Contract

- Runtime skill: `.agents/skills/scope-check/SKILL.md`
- Runtime name: `scope-check`
- Runtime trigger description: `Compare a feature or sprint with its approved scope and report scope creep and recommended cuts.`
- Native invocation: `$scope-check`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$scope-check` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: ON SCOPE, CONCERNS, SCOPE CREEP DETECTED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (what to do based on verdict)

---

## Director Gate Checks

None. Scope check is a read-only advisory skill; no gates are invoked.

---

## Test Cases

### Case 1: Happy Path — Sprint stories align with milestone goals

**Fixture:**
- `production/milestones/milestone-03.md` lists 3 goals: combat system, enemy AI, level loading
- `production/sprints/sprint-006.md` contains 5 stories, all tagged to one of the 3 goals
- `production/session-state/active.md` references milestone-03 as the active milestone

**Input:** `$scope-check`

**Expected behavior:**
1. Skill reads active milestone goals from milestone-03
2. Skill reads sprint-006 stories and checks each against milestone goals
3. All 5 stories map to one of the 3 goals
4. Skill outputs a mapping table: story → milestone goal
5. Verdict is ON SCOPE

**Assertions:**
- [ ] Each story is mapped to a milestone goal in the output
- [ ] Verdict is ON SCOPE when all stories map to milestone goals
- [ ] No files are written
- [ ] Skill does not modify sprint or milestone files

---

### Case 2: Scope Creep Detected — Stories introducing systems not in milestone

**Fixture:**
- `production/milestones/milestone-03.md` goals: combat, enemy AI, level loading
- `production/sprints/sprint-006.md` contains 5 stories:
  - 3 stories map to milestone goals
  - 2 stories reference "online leaderboard" and "achievement system" (not in milestone-03)

**Input:** `$scope-check`

**Expected behavior:**
1. Skill reads milestone goals and sprint stories
2. Skill identifies 2 stories with no matching milestone goal
3. Skill names the out-of-scope stories: "Online Leaderboard Feature", "Achievement System Setup"
4. Verdict is SCOPE CREEP DETECTED

**Assertions:**
- [ ] Out-of-scope stories are named explicitly in the output
- [ ] Verdict is SCOPE CREEP DETECTED when any story has no milestone goal match
- [ ] Skill does not automatically remove the stories — findings are advisory
- [ ] Output recommends deferring the out-of-scope stories to a later milestone

---

### Case 3: No Milestone Defined — CONCERNS; scope cannot be validated

**Fixture:**
- `production/session-state/active.md` has no milestone reference
- `production/milestones/` directory exists but is empty
- `production/sprints/sprint-006.md` has 4 stories

**Input:** `$scope-check`

**Expected behavior:**
1. Skill reads active.md — finds no milestone reference
2. Skill checks `production/milestones/` — no milestone files found
3. Skill outputs: "No active milestone defined — scope cannot be validated"
4. Verdict is CONCERNS

**Assertions:**
- [ ] Skill does not error when no milestone is defined
- [ ] Output explicitly states that scope validation requires a milestone reference
- [ ] Verdict is CONCERNS (not ON SCOPE or SCOPE CREEP DETECTED without data)
- [ ] Output suggests running `$milestone-review` or creating a milestone

---

### Case 4: Single Story Check — Evaluated against its parent epic

**Fixture:**
- User targets a single story: `production/epics/combat/story-parry-timing.md`
- Story references parent epic: `epic-combat.md`
- `production/epics/combat/epic-combat.md` has scope: "melee combat mechanics"
- Story title: "Implement parry timing window" — matches epic scope

**Input:** `$scope-check production/epics/combat/story-parry-timing.md`

**Expected behavior:**
1. Skill reads the specified story file
2. Skill reads the parent epic to get scope definition
3. Skill evaluates story against epic scope — "parry timing" matches "melee combat"
4. Verdict is ON SCOPE

**Assertions:**
- [ ] Single-file argument is accepted (story path, not sprint)
- [ ] Skill reads the parent epic referenced in the story file
- [ ] Story is evaluated against epic scope (not milestone scope) in single-story mode
- [ ] Verdict is ON SCOPE when story matches epic scope

---

### Case 5: Gate Compliance — No gate; PR may be consulted separately

**Fixture:**
- Sprint has 2 SCOPE CREEP stories and 3 ON SCOPE stories
- `review-mode.txt` contains `full`

**Input:** `$scope-check`

**Expected behavior:**
1. Skill reads milestone and sprint; identifies 2 scope creep items
2. No director gate is invoked regardless of review mode
3. Skill presents findings with SCOPE CREEP DETECTED verdict
4. Output notes: "Consider raising scope concerns with the Producer before sprint begins"
5. Skill ends without writing any files

**Assertions:**
- [ ] No director gate is invoked in any review mode
- [ ] Producer consultation is suggested (not mandated)
- [ ] No files are written
- [ ] Verdict is SCOPE CREEP DETECTED

---

## Protocol Compliance

- [ ] Reads milestone goals and sprint/story files before analysis
- [ ] Maps each story to a milestone goal (or flags as unmapped)
- [ ] Does not write any files
- [ ] No director gates are invoked
- [ ] Runs on Luna model tier (fast, low-cost)
- [ ] Verdict is one of: ON SCOPE, CONCERNS, SCOPE CREEP DETECTED

---

## Coverage Notes

- The case where the sprint file itself does not exist is not tested; the
  skill would output a CONCERNS verdict with a message about missing sprint data.
- Partial scope overlap (story touches a milestone goal but also introduces
  new scope) is not explicitly tested; implementation may classify this as
  CONCERNS rather than SCOPE CREEP DETECTED.
