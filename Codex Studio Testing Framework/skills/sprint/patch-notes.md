# Skill Test Spec: $patch-notes

## Codex Runtime Contract

- Runtime skill: `.agents/skills/patch-notes/SKILL.md`
- Runtime name: `patch-notes`
- Runtime trigger description: `"Use when repository and release history must be translated into player-facing patch notes."`
- Native invocation: `$patch-notes`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$patch-notes` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (e.g., share with community manager)

---

## Director Gate Checks

None. Patch notes generation is a fast compilation task; no gates are invoked.

---

## Test Cases

### Case 1: Happy Path — Changelog filtered to player-facing entries

**Fixture:**
- `docs/CHANGELOG.md` exists with 5 entries:
  - "Add dual-wield melee system" (Features — player-facing)
  - "Fix crash on level transition" (Fixes — player-facing)
  - "Add enemy patrol AI" (Features — player-facing)
  - "Refactor input handler to use event bus" (Fixes — internal only)
  - "Update dependency: Godot 4.6" (internal only)
- Version is `v0.4.0`

**Input:** `$patch-notes v0.4.0`

**Expected behavior:**
1. Skill reads `docs/CHANGELOG.md`
2. Skill filters to 3 player-facing entries; excludes 2 internal entries
3. Skill rewrites entries in plain language (no task IDs, no tech jargon)
4. Skill presents draft to user
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. User approves; file written; verdict COMPLETE

**Assertions:**
- [ ] Only 3 entries appear in the patch notes (2 internal entries excluded)
- [ ] Entries are written in plain language without internal task IDs
- [ ] File path matches `docs/patch-notes-v0.4.0.md`
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE after write

---

### Case 2: No Changelog Found — Directed to run $changelog first

**Fixture:**
- `docs/CHANGELOG.md` does NOT exist

**Input:** `$patch-notes v0.4.0`

**Expected behavior:**
1. Skill attempts to read `docs/CHANGELOG.md` — not found
2. Skill outputs: "No changelog found — run $changelog first to generate one"
3. No patch notes are generated; no file is written

**Assertions:**
- [ ] Skill does not crash when changelog is absent
- [ ] Output explicitly directs user to run `$changelog`
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is BLOCKED (dependency not met)

---

### Case 3: Tone Guidance from Design Folder — Incorporated into output

**Fixture:**
- `docs/CHANGELOG.md` exists with player-facing entries
- `design/community/tone-guide.md` exists with guidance: "upbeat, encouraging tone; avoid passive voice"

**Input:** `$patch-notes v0.4.0`

**Expected behavior:**
1. Skill reads changelog
2. Skill detects tone guide at `design/community/tone-guide.md`
3. Skill applies tone guidance when rewriting entries in plain language
4. Patch notes use upbeat, active-voice phrasing
5. Skill presents draft, asks to write, writes on approval

**Assertions:**
- [ ] Skill checks `design/` for a community or tone guidance file
- [ ] Tone guide content influences phrasing of patch note entries
- [ ] Output reflects active voice and upbeat tone where applicable
- [ ] Skill notes that tone guidance was applied

---

### Case 4: Patch Note Template Exists — Used instead of generated structure

**Fixture:**
- `.codex/docs/templates/patch-notes-template.md` exists with a structured header format
- `docs/CHANGELOG.md` exists with player-facing entries

**Input:** `$patch-notes v0.4.0`

**Expected behavior:**
1. Skill reads changelog and detects template exists
2. Skill populates the template with player-facing entries
3. Template header/footer structure is preserved in the output
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Skill checks for a patch notes template before generating from scratch
- [ ] Template structure is used when found (not overridden by default format)
- [ ] Player-facing entries are inserted into the correct template section
- [ ] Output note confirms template was used

---

### Case 5: Gate Compliance — No gate; community-manager is separate

**Fixture:**
- `docs/CHANGELOG.md` exists with player-facing entries
- `.codex/studio.toml` contains `full`

**Input:** `$patch-notes v0.4.0`

**Expected behavior:**
1. Skill compiles patch notes in full mode
2. No director gate is invoked (community review is a separate, manual step)
3. Skill runs on Luna model — fast compilation
4. Skill notes in output: "Consider sharing draft with community manager before publishing"
5. Skill asks user for approval and writes on confirmation

**Assertions:**
- [ ] No director gate is invoked regardless of review mode
- [ ] Output suggests (but does not require) community manager review
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE

---

## Protocol Compliance

- [ ] Reads `docs/CHANGELOG.md` before generating patch notes
- [ ] Filters entries to player-facing items only
- [ ] Rewrites entries in plain language without internal IDs
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] No director gates are invoked
- [ ] Runs on Luna model tier (fast, low-cost)

---

## Coverage Notes

- The case where all changelog entries are internal (zero player-facing items)
  is not tested; behavior is an empty patch notes draft with a warning.
- Version number parsing from the changelog header is an implementation detail
  not verified here.
- The community manager consultation noted in Case 5 is advisory; a separate
  skill or manual review handles that step.
