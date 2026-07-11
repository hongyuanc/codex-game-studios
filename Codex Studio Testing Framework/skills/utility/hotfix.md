# Skill Test Spec: $hotfix

## Codex Runtime Contract

- Runtime skill: `.agents/skills/hotfix/SKILL.md`
- Runtime name: `hotfix`
- Runtime trigger description: `"Use when an S1 or S2 production defect requires an emergency fix with an audit trail and rollback plan."`
- Native invocation: `$hotfix`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$hotfix` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: HOTFIX COMPLETE, HOTFIX BLOCKED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., `$bug-report` to document the issue, or version bump)

---

## Director Gate Checks

None. Hotfixes are time-critical. Director review may follow separately as a
post-hoc step. No gate is invoked within this skill.

---

## Test Cases

### Case 1: Happy Path — Critical crash bug fixed, smoke check passes

**Fixture:**
- `main` branch is clean
- Bug is identified in `src/gameplay/arena.gd` (crash on boss arena entry)
- Repro steps are provided by user

**Input:** `$hotfix` (user describes the crash and affected file)

**Expected behavior:**
1. Skill proposes creating a hotfix branch: `hotfix/boss-arena-crash`
2. User confirms; Bash command for branch creation is shown and confirmed
3. Skill identifies the fix location in `arena.gd` and drafts the change
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Skill runs `$smoke-check` — PASS
6. Skill presents the merge command and asks user to confirm merge to `main`
7. User confirms; merge executes; verdict is HOTFIX COMPLETE

**Assertions:**
- [ ] Hotfix branch is created before any code changes
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] `$smoke-check` runs after the fix is applied
- [ ] Merge requires explicit user confirmation (not automatic)
- [ ] Verdict is HOTFIX COMPLETE after successful merge

---

### Case 2: Smoke Check Fails — HOTFIX BLOCKED

**Fixture:**
- Fix has been applied to `src/gameplay/arena.gd`
- `$smoke-check` returns FAIL: "Player health clamping regression detected"

**Input:** `$hotfix`

**Expected behavior:**
1. Skill applies the fix and runs `$smoke-check`
2. Smoke check returns FAIL with specific regression identified
3. Skill reports: "HOTFIX BLOCKED — smoke check failed: [regression detail]"
4. Skill presents options: attempt revised fix, revert changes, or merge with
   known regression (user acknowledges risk)
5. No automatic merge occurs when smoke check fails

**Assertions:**
- [ ] Verdict is HOTFIX BLOCKED
- [ ] Smoke check failure is shown verbatim to user
- [ ] Merge is NOT performed automatically when smoke check fails
- [ ] User is given explicit options for how to proceed

---

### Case 3: Fix to Already-Released Build — Version tag noted, patch bump prompted

**Fixture:**
- Latest git tag is `v1.2.0`
- Hotfix targets a bug in the v1.2.0 release

**Input:** `$hotfix`

**Expected behavior:**
1. Skill detects that the current HEAD is a tagged release (v1.2.0)
2. Skill notes: "Hotfix targeting tagged release v1.2.0"
3. After smoke check passes, skill prompts: "Should version be bumped to v1.2.1?"
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. After version update and merge: verdict is HOTFIX COMPLETE with version noted

**Assertions:**
- [ ] Version tag context is detected and surfaced to user
- [ ] Patch version bump is suggested (not required) after merge
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is HOTFIX COMPLETE

---

### Case 4: No Repro Steps — Skill Asks Before Applying Fix

**Fixture:**
- User invokes `$hotfix` with a vague description: "something is broken on level 3"
- No repro steps provided

**Input:** `$hotfix` (vague description)

**Expected behavior:**
1. Skill detects insufficient information to identify the fix location
2. Skill asks: "Please provide reproduction steps and the affected file or system"
3. Skill does NOT create a branch or modify any file until repro steps are provided
4. After user provides repro steps: normal hotfix flow begins

**Assertions:**
- [ ] No branch is created without repro steps
- [ ] No code changes are made without a clearly identified fix location
- [ ] Repro step request is specific (not a generic "please provide more info")
- [ ] Normal hotfix flow resumes after user provides repro steps

---

### Case 5: Director Gate Check — No gate; hotfixes are time-critical

**Fixture:**
- Critical bug with repro steps identified

**Input:** `$hotfix`

**Expected behavior:**
1. Skill completes the hotfix workflow
2. No director agents are spawned during execution
3. No gate IDs appear in output
4. Post-hoc director review (if needed) is a manual follow-up, not invoked here

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is HOTFIX COMPLETE or HOTFIX BLOCKED — no gate verdict

---

## Protocol Compliance

- [ ] Creates hotfix branch before making any code changes
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Runs `$smoke-check` after applying the fix
- [ ] Requires explicit user confirmation before merging
- [ ] HOTFIX BLOCKED when smoke check fails — no automatic merge
- [ ] Verdict is HOTFIX COMPLETE or HOTFIX BLOCKED

---

## Coverage Notes

- The case where multiple files need to be modified for one fix follows the same
  The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
- The post-hotfix steps (create bug report, update changelog) are suggested in
  the handoff but not tested as part of this skill's execution.
- Conflict resolution during the merge (if main has diverged) is not tested;
  the skill would surface the conflict and ask the user to resolve it manually.
