# Skill Test Spec: $art-bible

## Codex Runtime Contract

- Runtime skill: `.agents/skills/art-bible/SKILL.md`
- Runtime name: `art-bible`
- Runtime trigger description: `Author the game's visual identity specification after the game concept is approved and before asset production begins.`
- Native invocation: `$art-bible`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$art-bible` is tested against the exact runtime discovery contract above. The five
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
- [ ] Documents the AD-ART-BIBLE director gate and its mode behavior
- [ ] Has a next-step handoff (e.g., `$asset-spec` or `$design-system`)

---

## Director Gate Checks

| Gate ID      | Trigger condition              | Mode guard            |
|--------------|--------------------------------|-----------------------|
| AD-ART-BIBLE | After draft is complete        | full only (not phase-gated/solo) |

---

## Test Cases

### Case 1: Happy Path — Full mode, art bible drafted, AD-ART-BIBLE approves

**Fixture:**
- No existing `design/art-bible.md`
- `.codex/studio.toml` contains `full`
- `design/gdd/game-concept.md` exists with visual tone described

**Input:** `$art-bible`

**Expected behavior:**
1. Skill drafts an in-memory skeleton for `design/art-bible.md` with all section headers
2. Skill discusses and drafts each section with user collaboration
3. After all sections are drafted, AD-ART-BIBLE gate is invoked (art director review)
4. AD-ART-BIBLE returns APPROVED
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. All sections written after approval; verdict is COMPLETE

**Assertions:**
- [ ] The in-memory skeleton is drafted first (before any section content is written)
- [ ] AD-ART-BIBLE gate is invoked in full mode after draft is complete
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] All sections are present in the final file
- [ ] Verdict is COMPLETE

---

### Case 2: AD-ART-BIBLE Returns CONCERNS — Section revised before writing

**Fixture:**
- Art bible draft complete
- `.codex/studio.toml` contains `full`
- AD-ART-BIBLE gate returns CONCERNS: "Color palette clashes with the dark
  atmospheric tone described in the game concept"

**Input:** `$art-bible`

**Expected behavior:**
1. AD-ART-BIBLE gate returns CONCERNS with specific feedback about palette
2. Skill surfaces feedback to user: "Art director has concerns about the color palette"
3. Skill returns to the Color Palette section for revision
4. User and skill revise the palette to align with game concept tone
5. AD-ART-BIBLE is not re-invoked (user decides to proceed after revision)
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] CONCERNS are shown to user before any section is written
- [ ] Skill returns to the affected section for revision (not all sections)
- [ ] Revised content (not original) is written to file
- [ ] Verdict is COMPLETE after revision and approval

---

### Case 3: Phase-gated Mode — Gate skipped, atomic write still requires approval

**Fixture:**
- No existing art bible
- `.codex/studio.toml` contains `phase-gated`

**Input:** `$art-bible`

**Expected behavior:**
1. Skill reads review mode — determines `phase-gated`
2. Skill drafts all sections with user collaboration
3. AD-ART-BIBLE gate is skipped: output notes "[AD-ART-BIBLE] skipped — phase-gated mode"
4. Skill asks for conversational approval of each section without writing
5. Skill presents the complete art-bible changeset, obtains final approval, and writes once; verdict is COMPLETE

**Assertions:**
- [ ] AD-ART-BIBLE gate is NOT invoked in phase-gated mode
- [ ] Skip is explicitly noted: "[AD-ART-BIBLE] skipped — phase-gated mode"
- [ ] User approval is still required per section (gate skip ≠ approval skip)
- [ ] Verdict is COMPLETE

---

### Case 4: Existing Art Bible — Retrofit Mode

**Fixture:**
- `design/art-bible.md` already exists with all sections populated
- User wants to update the Character Design Rules section

**Input:** `$art-bible`

**Expected behavior:**
1. Skill reads existing art bible and detects all sections populated
2. Skill offers retrofit: "Art bible exists — which section would you like to update?"
3. User selects Character Design Rules
4. Skill drafts updated content; in full mode, AD-ART-BIBLE is invoked for the
   revised section before writing
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Only that section is updated; other sections preserved; verdict is COMPLETE

**Assertions:**
- [ ] Existing art bible is detected and retrofit is offered
- [ ] Only the selected section is updated
- [ ] In full mode: AD-ART-BIBLE gate runs even for single-section retrofit
- [ ] Other sections are preserved
- [ ] Verdict is COMPLETE

---

### Case 5: Solo Mode — AD-ART-BIBLE Skipped, Noted in Output

**Fixture:**
- No existing art bible
- `.codex/studio.toml` contains `solo`

**Input:** `$art-bible`

**Expected behavior:**
1. Skill reads review mode — determines `solo`
2. Art bible is drafted and written only after the complete changeset is shown and approved
3. AD-ART-BIBLE gate is skipped: output notes "[AD-ART-BIBLE] skipped — solo mode"
4. No director agents are spawned
5. Verdict is COMPLETE

**Assertions:**
- [ ] AD-ART-BIBLE gate is NOT invoked in solo mode
- [ ] Skip is explicitly noted with "solo mode" label
- [ ] No director agents of any kind are spawned
- [ ] Verdict is COMPLETE

---

## Protocol Compliance

- [ ] Drafts an in-memory skeleton immediately with all section headers
- [ ] Discusses and drafts one section at a time
- [ ] AD-ART-BIBLE gate runs in full mode after all sections are drafted
- [ ] AD-ART-BIBLE is skipped in phase-gated and solo modes — noted by name
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE when all sections are written

---

## Coverage Notes

- The case where AD-ART-BIBLE returns REJECT (not just CONCERNS) is not
  separately tested; the skill would block writing and ask the user how to
  proceed (revise or override).
- The Typography section is listed as a required art bible section but its
  specific content requirements are not assertion-tested here.
- The art bible feeds into `$asset-spec` — this relationship is noted in the
  handoff but not tested as part of this skill's spec.
