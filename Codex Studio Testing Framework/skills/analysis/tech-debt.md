# Skill Test Spec: $tech-debt

## Codex Runtime Contract

- Runtime skill: `.agents/skills/tech-debt/SKILL.md`
- Runtime name: `tech-debt`
- Runtime trigger description: `Scan, record, prioritize, or report technical debt in the game project.`
- Native invocation: `$tech-debt`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$tech-debt` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: REGISTER UPDATED, NO NEW DEBT FOUND
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (what to do after register is updated)

---

## Director Gate Checks

None. Tech debt tracking is an internal codebase analysis skill; no gates are
invoked.

---

## Test Cases

### Case 1: Happy Path — Inline TODOs plus existing register items merged

**Fixture:**
- `docs/tech-debt-register.md` exists with 2 items (LOW and MEDIUM severity)
- `src/gameplay/combat.gd` has 2 `# TODO` comments and 1 `# FIXME` comment
- `src/ui/hud.gd` has 0 inline debt comments

**Input:** `$tech-debt`

**Expected behavior:**
1. Skill reads `docs/tech-debt-register.md` — finds 2 existing items
2. Skill scans `src/` — finds 3 inline comments (2 TODOs, 1 FIXME)
3. Skill checks whether inline comments already exist in the register (deduplication)
4. Skill presents combined list sorted by severity (FIXME before TODO by default)
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. User approves; register updated; verdict REGISTER UPDATED

**Assertions:**
- [ ] Inline comments are found by scanning `src/` recursively
- [ ] Existing register items are not duplicated
- [ ] Combined list is sorted by severity
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is REGISTER UPDATED

---

### Case 2: Register Doesn't Exist — Offered to create it

**Fixture:**
- `docs/tech-debt-register.md` does NOT exist
- `src/` contains 4 inline TODO/FIXME comments

**Input:** `$tech-debt`

**Expected behavior:**
1. Skill attempts to read `docs/tech-debt-register.md` — not found
2. Skill informs user: "No tech-debt-register.md found"
3. Skill offers to create the register with the inline items it found
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. User approves; register created with 4 items; verdict REGISTER UPDATED

**Assertions:**
- [ ] Skill does not crash when register file is absent
- [ ] User is offered register creation (not silently skipping)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is REGISTER UPDATED after creation

---

### Case 3: Resolved Item Detected — Marked resolved in register

**Fixture:**
- `docs/tech-debt-register.md` has 3 items; one references `src/gameplay/legacy_input.gd`
- `src/gameplay/legacy_input.gd` has been deleted (refactored away)
- The referenced TODO comment no longer exists in source

**Input:** `$tech-debt`

**Expected behavior:**
1. Skill reads register — finds 3 items
2. Skill scans `src/` — does not find the source location referenced by item 2
3. Skill flags item 2 as RESOLVED (source is gone)
4. Skill presents the resolved item to user for confirmation
5. On approval, register is updated with item 2 marked `Status: Resolved`

**Assertions:**
- [ ] Skill checks whether each register item's source reference still exists
- [ ] Missing source locations result in items being flagged as RESOLVED
- [ ] User confirms before resolved items are written
- [ ] RESOLVED items are kept in the register (not deleted) for audit history

---

### Case 4: Edge Case — CRITICAL debt item surfaces prominently

**Fixture:**
- `src/core/network_sync.gd` has a comment: `# FIXME(CRITICAL): race condition in sync buffer — can corrupt save data`
- `docs/tech-debt-register.md` exists with 5 lower-severity items

**Input:** `$tech-debt`

**Expected behavior:**
1. Skill scans source and finds the CRITICAL-tagged FIXME
2. Skill presents the CRITICAL item at the top of the output — before the full table
3. Skill asks user to acknowledge the critical item before proceeding
4. After acknowledgment, skill presents full debt table and asks to write
5. Register is updated with CRITICAL item at top; verdict REGISTER UPDATED

**Assertions:**
- [ ] CRITICAL items appear at the top of the output, not buried in the table
- [ ] Skill surfaces CRITICAL items before asking to write
- [ ] User acknowledgment of the CRITICAL item is requested
- [ ] CRITICAL severity is preserved in the written register entry

---

### Case 5: Gate Compliance — No gate; register updated only with approval

**Fixture:**
- Inline scan finds 2 new TODOs; register has 3 existing items
- `review-mode.txt` contains `full`

**Input:** `$tech-debt`

**Expected behavior:**
1. Skill scans source and reads register; compiles combined debt list
2. No director gate is invoked regardless of review mode
3. Skill presents sorted debt table to user
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. User approves; register updated; verdict REGISTER UPDATED

**Assertions:**
- [ ] No director gate is invoked in any review mode
- [ ] Debt table is presented before any write prompt
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Write only occurs with explicit user approval

---

## Protocol Compliance

- [ ] Reads `docs/tech-debt-register.md` and scans `src/` before compiling
- [ ] Deduplicates inline comments against existing register items
- [ ] Sorts combined list by severity
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] No director gates are invoked
- [ ] Verdict is REGISTER UPDATED or NO NEW DEBT FOUND

---

## Coverage Notes

- The case where `src/` is empty or absent is not tested; behavior follows
  the NO NEW DEBT FOUND path for the inline scan, but register items would
  still be read and presented.
- TODO comments without severity tags are treated as LOW severity by default;
  this classification detail is an implementation concern, not tested here.
