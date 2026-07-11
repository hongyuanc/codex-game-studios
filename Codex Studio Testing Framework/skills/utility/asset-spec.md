# Skill Test Spec: $asset-spec

## Codex Runtime Contract

- Runtime skill: `.agents/skills/asset-spec/SKILL.md`
- Runtime name: `asset-spec`
- Runtime trigger description: `Generate approved per-asset visual specifications and prompts from the art bible and design documents.`
- Native invocation: `$asset-spec`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$asset-spec` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (e.g., assign to an artist, or `$asset-audit` later)

---

## Director Gate Checks

None. `$asset-spec` is a design documentation utility. Technical artists may
review specs separately but this is not a gate within this skill.

---

## Test Cases

### Case 1: Happy Path — Enemy sprite spec with full GDD and art bible

**Fixture:**
- `design/gdd/enemies.md` exists with enemy variants defined
- `design/art-bible.md` exists with color palette and style notes
- No existing asset spec for "goblin-enemy"

**Input:** `$asset-spec goblin-enemy`

**Expected behavior:**
1. Skill reads enemies GDD and art bible
2. Skill generates a spec for the goblin enemy sprite:
   - Dimensions: inferred from engine defaults or explicitly from GDD
   - Animation states: idle, walk, attack, hurt, death
   - Color palette reference: links to art-bible palette section
   - Style notes: from art bible character design rules
   - Technical constraints: format (PNG), size budget
   - Deliverable checklist
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
4. File written on approval; verdict is COMPLETE

**Assertions:**
- [ ] All 6 spec components are present (dimensions, animations, palette, style, tech, checklist)
- [ ] Color palette reference links to art bible (not duplicated)
- [ ] Animation states are drawn from GDD (not invented)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE

---

### Case 2: No Art Bible Found — Spec with Placeholder Style Notes, Dependency Flagged

**Fixture:**
- `design/gdd/player.md` exists
- `design/art-bible.md` does NOT exist

**Input:** `$asset-spec player-sprite`

**Expected behavior:**
1. Skill reads player GDD but cannot find the art bible
2. Skill generates spec with placeholder style notes: "DEPENDENCY GAP: art bible
   not found — style notes are placeholders"
3. Color palette section uses: "TBD — see art bible when created"
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. File written with placeholders and dependency flag; verdict is COMPLETE with advisory

**Assertions:**
- [ ] DEPENDENCY GAP is flagged for the missing art bible
- [ ] Spec is still generated (not blocked)
- [ ] Style notes contain placeholder markers, not invented styles
- [ ] Verdict is COMPLETE with advisory note

---

### Case 3: Asset Spec Already Exists — Offers to Update

**Fixture:**
- `assets/specs/goblin-enemy-spec.md` already exists
- GDD has been updated since the spec was written (new attack animation added)

**Input:** `$asset-spec goblin-enemy`

**Expected behavior:**
1. Skill detects existing spec file
2. Skill reports: "Asset spec already exists for goblin-enemy — checking for updates"
3. Skill diffs GDD against existing spec and identifies: new "charge-attack" animation
   state added in GDD but not in spec
4. Skill presents the diff: "1 new animation state found — offering to update spec"
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Spec is updated; verdict is COMPLETE

**Assertions:**
- [ ] Existing spec is detected and "update" path is offered
- [ ] Diff between GDD and existing spec is shown
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Existing spec content is preserved; only the diff is applied
- [ ] Verdict is COMPLETE

---

### Case 4: Multiple Assets Requested — May-I-Write Per Asset

**Fixture:**
- GDD and art bible exist
- User requests specs for 3 assets: goblin-enemy, orc-enemy, treasure-chest

**Input:** `$asset-spec goblin-enemy orc-enemy treasure-chest`

**Expected behavior:**
1. Skill generates all 3 specs in sequence
2. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
   `assets/specs/[name]-spec.md`?" individually
3. User can approve all 3 or skip individual assets
4. All approved specs are written; verdict is COMPLETE

**Assertions:**
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] User can decline one asset without blocking the others
- [ ] All 3 spec files are written for approved assets
- [ ] Verdict is COMPLETE when all approved specs are written

---

### Case 5: Director Gate Check — No gate; asset-spec is a design utility

**Fixture:**
- GDD and art bible exist

**Input:** `$asset-spec goblin-enemy`

**Expected behavior:**
1. Skill generates and writes the asset spec
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Reads GDD, art bible, and design system before generating spec
- [ ] Includes all 6 spec components (dimensions, animations, palette, style, tech, checklist)
- [ ] Flags missing dependencies (art bible, GDD) with DEPENDENCY GAP notes
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Handles multiple assets with individual write confirmations
- [ ] Verdict is COMPLETE when all approved specs are written

---

## Coverage Notes

- Audio asset specs (sound effects, music) follow the same structure with
  different fields (duration, sample rate, looping) and are not separately tested.
- UI asset specs (icons, button states) follow the same flow with interaction
  state requirements aligned to the UX spec.
- The case where GDD is also missing (neither GDD nor art bible exists) is not
  separately tested; spec would be generated with both dependency gaps flagged.
