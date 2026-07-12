# Skill Test Spec: $playtest-report

## Codex Runtime Contract

- Runtime skill: `.agents/skills/playtest-report/SKILL.md`
- Runtime name: `playtest-report`
- Runtime trigger description: `"Use when a playtest session needs a report template or raw notes need structured findings and design-impact analysis."`
- Native invocation: `$playtest-report`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$playtest-report` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (e.g., `$bug-report` for new issues found, `$design-review` for feedback)

---

## Director Gate Checks

None. `$playtest-report` is a documentation utility. The CD-PLAYTEST gate is a
separate invocation and not part of this skill.

---

## Test Cases

### Case 1: Happy Path — User provides playtest notes, structured report produced

**Fixture:**
- User provides typed playtest notes from a single session
- Notes cover: game feel, one bug (framerate drop), and a design concern
  (tutorial too long)
- `production/bugs/` exists but is empty (bug not yet reported)

**Input:** `$playtest-report` (user pastes session notes)

**Expected behavior:**
1. Skill reads the provided notes and structures them into the 4-section template
2. Feel/Accessibility: extracts feel observations
3. Bugs: notes the framerate drop with available repro details
4. Design Feedback: notes the tutorial length concern
5. Next Steps: suggests `$bug-report` for the framerate issue and `$design-review`
   for the tutorial feedback
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
7. Report is written on approval; verdict is COMPLETE

**Assertions:**
- [ ] All 4 sections are present in the report
- [ ] Bug is listed in the Bugs section (not the Design Feedback section)
- [ ] Next Steps are appropriate (bug report for crash, design review for feedback)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE

---

### Case 2: Empty Input — Guided prompting through each section

**Fixture:**
- No notes provided by user at invocation

**Input:** `$playtest-report`

**Expected behavior:**
1. Skill detects empty input
2. Skill prompts through each section:
   a. "Describe the overall feel and any accessibility observations"
   b. "Were any bugs observed? Describe them"
   c. "What design feedback did testers provide?"
3. User answers each prompt
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Report written on approval; verdict is COMPLETE

**Assertions:**
- [ ] At least 3 guiding questions are asked (one per main section)
- [ ] Report is not created until all sections have input (or user explicitly skips one)
- [ ] Verdict is COMPLETE after file is written

---

### Case 3: Multiple Testers — Aggregated feedback with majority/minority notes

**Fixture:**
- User provides notes from 3 testers
- 2/3 testers found the controls "intuitive"
- 1/3 tester found the UI font too small
- All 3 noted the same bug (player stuck on ledge)

**Input:** `$playtest-report` (3-tester session)

**Expected behavior:**
1. Skill identifies 3 distinct tester perspectives in the input
2. Control intuitiveness → noted as "Majority (2/3): controls intuitive"
3. Font size → noted as "Minority (1/3): UI font size concern"
4. Stuck-on-ledge bug → noted as "All testers: player stuck on ledge (confirmed)"
5. Skill generates aggregated report with majority/minority labels
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Majority opinion (2/3) is labeled as majority
- [ ] Minority opinion (1/3) is labeled as minority
- [ ] Unanimously reported bug is noted as confirmed by all testers
- [ ] Verdict is COMPLETE

---

### Case 4: Bug Matches Existing Report — Links to existing file

**Fixture:**
- `production/bugs/bug-2026-03-30-player-stuck-ledge.md` exists
- User's playtest notes describe "player gets stuck on ledges near walls"

**Input:** `$playtest-report`

**Expected behavior:**
1. Skill structures the report and identifies the stuck-on-ledge bug
2. Skill scans `production/bugs/` and finds `bug-2026-03-30-player-stuck-ledge.md`
3. In the Bugs section, the report includes: "See existing report:
   production/bugs/bug-2026-03-30-player-stuck-ledge.md"
4. Skill does NOT suggest creating a new bug report for this issue
5. Report written; verdict is COMPLETE

**Assertions:**
- [ ] Existing bug report is found and linked in the playtest report
- [ ] `$bug-report` is NOT suggested for the already-reported issue
- [ ] Cross-reference to existing file appears in the Bugs section
- [ ] Verdict is COMPLETE

---

### Case 5: Optional Director Gate — CD-PLAYTEST runs only in full

**Fixture:**
- Playtest notes provided
- `.codex/studio.toml` contains `full`

**Input:** `$playtest-report`

**Expected behavior:**
1. Skill generates and writes the playtest report
2. CD-PLAYTEST is optional: run it only in `full`; phase-gated and solo skip it.
3. Pass the structured report, pillars/core fantasy, and tested hypothesis to the creative director.
4. Record the director assessment in the report before saving.

**Assertions:**
- [ ] CD-PLAYTEST runs in full mode.
- [ ] Phase-gated and solo emit the optional-gate skip and proceed to save.
- [ ] The assessment is included before the report's COMPLETE verdict.

---

## Protocol Compliance

- [ ] Structures output into all 4 sections (Feel, Bugs, Design Feedback, Next Steps)
- [ ] Labels majority vs. minority opinions when multiple testers are involved
- [ ] Cross-references existing bug reports when bugs match
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE when report is written

---

## Coverage Notes

- CD-PLAYTEST is an optional inline gate governed by the runtime review-mode
  check; it is not a separate user invocation.
- Video recording or screenshot attachments are not tested; the report is a
  text-only document.
- The case where a tester's identity is unknown (anonymous feedback) follows
  the same aggregation pattern as Case 3 without tester labels.
