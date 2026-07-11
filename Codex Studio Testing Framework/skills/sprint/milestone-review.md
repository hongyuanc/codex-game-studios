# Skill Test Spec: $milestone-review

## Codex Runtime Contract

- Runtime skill: `.agents/skills/milestone-review/SKILL.md`
- Runtime name: `milestone-review`
- Runtime trigger description: `"Use when a milestone checkpoint needs completeness, quality, risk, schedule, and go/no-go assessment."`
- Native invocation: `$milestone-review`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$milestone-review` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: MILESTONE COMPLETE, MILESTONE INCOMPLETE
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (what to do after review is written)

---

## Director Gate Checks

| Gate ID       | Trigger condition              | Mode guard              |
|---------------|--------------------------------|-------------------------|
| PR-MILESTONE  | After review document compiled | full only (not phase-gated/solo) |

---

## Test Cases

### Case 1: Happy Path — Nearly complete milestone with one deferred story

**Fixture:**
- `production/milestones/milestone-03.md` exists with 8 stories
- 7 stories have `Status: Complete`
- 1 story has `Status: Deferred` (deferred to milestone-04)
- `.codex/studio.toml` contains `full`

**Input:** `$milestone-review milestone-03`

**Expected behavior:**
1. Skill reads `milestone-03.md` and all referenced sprint files
2. Skill compiles: 7 shipped, 1 deferred; velocity; no blockers
3. Skill presents review draft to user
4. PR-MILESTONE gate invoked; producer approves
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. User approves; file is written; verdict MILESTONE COMPLETE

**Assertions:**
- [ ] Deferred story is noted in the review with its target milestone
- [ ] Verdict is MILESTONE COMPLETE despite the one deferred story
- [ ] PR-MILESTONE gate is invoked after draft compilation in full mode
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Review document path matches `production/milestones/review-milestone-03.md`

---

### Case 2: Blocked Milestone — Multiple blocked stories

**Fixture:**
- `production/milestones/milestone-03.md` exists with 5 stories
- 2 stories have `Status: Complete`
- 3 stories have `Status: Blocked` (named blockers listed in each story)
- `.codex/studio.toml` contains `full`

**Input:** `$milestone-review milestone-03`

**Expected behavior:**
1. Skill reads milestone and sprint files
2. Skill finds 3 blocked stories; compiles blocker details
3. Verdict is MILESTONE INCOMPLETE
4. PR-MILESTONE gate runs; producer notes the unresolved blockers
5. Review is written with blocker list on approval

**Assertions:**
- [ ] Verdict is MILESTONE INCOMPLETE when any stories are Blocked
- [ ] Each blocked story's name and blocker reason is listed in the review
- [ ] PR-MILESTONE gate is still invoked in full mode even for INCOMPLETE verdict
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 3: Full Mode — PR-MILESTONE returns CONCERNS

**Fixture:**
- Milestone-03 has 6 complete stories but 2 were not in the original scope (added mid-sprint)
- `.codex/studio.toml` contains `full`

**Input:** `$milestone-review milestone-03`

**Expected behavior:**
1. Skill compiles review; notes 2 out-of-scope stories shipped
2. PR-MILESTONE gate invoked; producer returns CONCERNS about scope drift
3. Skill surfaces the CONCERNS to the user and adds a "scope drift" note to the review
4. User approves revised review; file written as MILESTONE COMPLETE with caveat

**Assertions:**
- [ ] CONCERNS from PR-MILESTONE gate are shown to user before write
- [ ] Scope drift is explicitly noted in the written review document
- [ ] Verdict is MILESTONE COMPLETE (stories shipped) with CONCERNS annotation
- [ ] Skill does not suppress gate feedback

---

### Case 4: Edge Case — No milestone file found for specified milestone

**Fixture:**
- User calls `$milestone-review milestone-07`
- `production/milestones/milestone-07.md` does NOT exist

**Input:** `$milestone-review milestone-07`

**Expected behavior:**
1. Skill attempts to read `production/milestones/milestone-07.md`
2. File not found; skill outputs an error message
3. Skill suggests checking available milestones in `production/milestones/`
4. No gate is invoked; no file is written

**Assertions:**
- [ ] Skill does not crash when milestone file is absent
- [ ] Output names the expected file path in the error message
- [ ] Output suggests checking `production/milestones/` for valid milestone names
- [ ] Verdict is BLOCKED (cannot review a non-existent milestone)

---

### Case 5: Phase-gated/Solo Mode — PR-MILESTONE gate skipped

**Fixture:**
- `production/milestones/milestone-03.md` exists with 5 complete stories
- `.codex/studio.toml` contains `solo`

**Input:** `$milestone-review milestone-03`

**Expected behavior:**
1. Skill reads review mode — determines `solo`
2. Skill compiles review draft
3. PR-MILESTONE gate is skipped; output notes "[PR-MILESTONE] skipped — Solo mode"
4. Skill asks user for direct approval of the review
5. User approves; review file is written; verdict MILESTONE COMPLETE

**Assertions:**
- [ ] PR-MILESTONE gate is NOT invoked in solo (or phase-gated) mode
- [ ] Skip is explicitly noted in skill output
- [ ] User direct approval is still required before write
- [ ] Verdict is MILESTONE COMPLETE after successful write

---

## Protocol Compliance

- [ ] Shows compiled review draft before invoking PR-MILESTONE or asking to write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] PR-MILESTONE gate only runs in full mode
- [ ] Skip message appears in phase-gated and solo output
- [ ] Verdict is MILESTONE COMPLETE or MILESTONE INCOMPLETE, stated clearly

---

## Coverage Notes

- The case where the milestone has zero stories is not tested; it follows the
  MILESTONE INCOMPLETE pattern with a note suggesting the milestone may not
  have been planned.
- Velocity calculation specifics (story points vs. story count) are not
  verified here; they are implementation details of the review compilation phase.
