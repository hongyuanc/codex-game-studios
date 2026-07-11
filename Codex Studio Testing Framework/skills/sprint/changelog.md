# Skill Test Spec: $changelog

## Codex Runtime Contract

- Runtime skill: `.agents/skills/changelog/SKILL.md`
- Runtime name: `changelog`
- Runtime trigger description: `"Use when an internal or player-facing changelog must be drafted from repository and production history."`
- Native invocation: `$changelog`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$changelog` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keyword: COMPLETE
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., run $patch-notes for player-facing version)

---

## Director Gate Checks

None. Changelog generation is a fast compilation task; no gates are invoked.

---

## Test Cases

### Case 1: Happy Path — Multiple sprints since last release tag

**Fixture:**
- Git history has a tag `v0.3.0` three sprints ago
- Since that tag: 12 commits across sprints 006, 007, 008
- Sprint story files reference task IDs matching commit messages
- `docs/CHANGELOG.md` does not yet exist

**Input:** `$changelog`

**Expected behavior:**
1. Skill reads git log since `v0.3.0` tag
2. Skill reads sprint stories to cross-reference task IDs
3. Skill compiles entries into Features, Fixes, and Known Issues sections
4. Skill presents draft to user
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. User approves; file written; verdict COMPLETE

**Assertions:**
- [ ] Changelog covers commits since the most recent git tag
- [ ] Entries are organized into Features / Fixes / Known Issues sections
- [ ] Sprint story references are used to enrich commit descriptions
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE after write

---

### Case 2: No Git Tags Found — All commits used, version baseline noted

**Fixture:**
- Git repository has commits but no tags exist
- 20 commits in history across 3 sprints

**Input:** `$changelog`

**Expected behavior:**
1. Skill checks for git tags — finds none
2. Skill uses all commits in history as the baseline
3. Skill notes in the output: "No version tag found — using full commit history; version baseline is unset"
4. Skill still compiles organized changelog from available commits
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Skill does not error when no git tags exist
- [ ] Output explicitly notes that no version baseline was found
- [ ] Full commit history is used as the source
- [ ] Changelog is still organized into sections despite missing tag

---

### Case 3: Commit Messages Without Task IDs — Grouped by date with note

**Fixture:**
- Git log since last tag has 8 commits
- 5 commits have no task ID in the message (e.g., "fix typo", "tweak values")
- 3 commits reference task IDs matching sprint stories

**Input:** `$changelog`

**Expected behavior:**
1. Skill reads commits and sprint stories
2. 3 commits are matched to sprint stories and placed in appropriate sections
3. 5 untagged commits are grouped by date under a "Misc" or "Other Changes" section
4. Output notes: "5 commits without task IDs — grouped by date"
5. Skill writes changelog on approval

**Assertions:**
- [ ] Commits with task IDs are placed in appropriate sections (Features or Fixes)
- [ ] Commits without task IDs are grouped separately with a note
- [ ] Output flags the number of commits missing task references
- [ ] No commits are silently dropped from the changelog

---

### Case 4: Existing CHANGELOG.md — New section prepended, old entries preserved

**Fixture:**
- `docs/CHANGELOG.md` already exists with sections for `v0.2.0` and `v0.3.0`
- New commits exist since `v0.3.0` tag

**Input:** `$changelog`

**Expected behavior:**
1. Skill detects that `docs/CHANGELOG.md` already exists
2. Skill compiles new entries for the period since `v0.3.0`
3. Skill presents draft with new section prepended above existing content
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. User approves; new content is prepended, old entries intact; verdict COMPLETE

**Assertions:**
- [ ] Skill reads existing changelog before writing to detect prior content
- [ ] New section is prepended (not appended or overwriting) existing entries
- [ ] Old changelog entries for v0.2.0 and v0.3.0 are preserved in the written file
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write

---

### Case 5: Gate Compliance — No gate; read-then-write with approval

**Fixture:**
- Git history has commits since last tag
- `review-mode.txt` contains `full`

**Input:** `$changelog`

**Expected behavior:**
1. Skill compiles changelog in full mode
2. No director gate is invoked (changelog generation is compilation, not a delivery gate)
3. Skill runs on Luna model — fast compilation
4. Skill asks user for approval and writes file on confirmation

**Assertions:**
- [ ] No director gate is invoked regardless of review mode
- [ ] Output does not reference any gate result
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE

---

## Protocol Compliance

- [ ] Reads git log and sprint story files before compiling
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] No director gates are invoked
- [ ] Verdict is always COMPLETE
- [ ] Runs on Luna model tier (fast, low-cost)

---

## Coverage Notes

- The case where git is not initialized in the repository is not tested;
  behavior would depend on git command failure handling.
- Merge commits vs. squash commits are not explicitly differentiated in
  these tests; implementation detail of the git log parsing phase.
- The `$patch-notes` skill should be run after `$changelog` for player-facing
  output; that handoff is verified in the patch-notes spec.
