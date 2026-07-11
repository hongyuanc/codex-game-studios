# Skill Test Spec: $help

## Codex Runtime Contract

- Runtime skill: `.agents/skills/help/SKILL.md`
- Runtime name: `help`
- Runtime trigger description: `Orient the user from current repository state and recommend the next applicable Codex Game Studios workflow.`
- Native invocation: `$help`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$help` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keyword: HELP COMPLETE
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (suggests 2-3 relevant skills based on state)

---

## Director Gate Checks

None. `$help` is a read-only navigation skill. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — Production stage with active sprint

**Fixture:**
- `production/stage.txt` contains `Production`
- `production/sprints/sprint-004.md` exists with in-progress stories
- `production/session-state/active.md` has a recent checkpoint

**Input:** `$help`

**Expected behavior:**
1. Skill reads stage.txt and active sprint
2. Skill identifies current sprint number and in-progress story count
3. Skill outputs: current stage, sprint summary, and 3 suggested next skills
   (e.g., `$sprint-status`, `$dev-story`, `$story-done`)
4. Suggestions are ranked by relevance to current sprint state
5. Verdict is HELP COMPLETE

**Assertions:**
- [ ] Current stage is shown (Production)
- [ ] Active sprint number and story count are mentioned
- [ ] Exactly 2-3 next-skill suggestions are given (not a list of all skills)
- [ ] Suggestions are appropriate for Production stage
- [ ] Verdict is HELP COMPLETE
- [ ] No files are written

---

### Case 2: Concept Stage — Shows concept-to-systems-design workflow path

**Fixture:**
- `production/stage.txt` contains `Concept`
- No sprint files, no GDD files
- `technical-preferences.md` is configured (engine selected)

**Input:** `$help`

**Expected behavior:**
1. Skill reads stage.txt — detects Concept stage
2. Skill outputs the Concept-stage workflow: brainstorm → map-systems → design-system
3. Suggested skills are: `$brainstorm`, `$map-systems` (if concept exists)
4. Current progress is noted: "Engine configured, concept not yet created"

**Assertions:**
- [ ] Stage is identified as Concept
- [ ] Workflow path shows the expected sequence for this stage
- [ ] Suggestions do not include Production-stage skills (e.g., `$dev-story`)
- [ ] Verdict is HELP COMPLETE

---

### Case 3: No stage.txt — Shows full workflow overview

**Fixture:**
- No `production/stage.txt`
- No sprint files
- `technical-preferences.md` has placeholders

**Input:** `$help`

**Expected behavior:**
1. Skill cannot determine stage from stage.txt
2. Skill runs project-stage-detect logic to infer stage from artifacts
3. If stage cannot be inferred: outputs the full workflow overview from
   Concept through Release as a reference map
4. Primary suggestion is `$start` to begin configuration

**Assertions:**
- [ ] Skill does not crash when stage.txt is absent
- [ ] Full workflow overview is shown when stage cannot be determined
- [ ] `$start` or `$project-stage-detect` is a top suggestion
- [ ] Verdict is HELP COMPLETE

---

### Case 4: Context Query — User asks for help with testing

**Fixture:**
- `production/stage.txt` contains `Production`
- Active sprint has a story with `Status: In Review`

**Input:** `$help testing`

**Expected behavior:**
1. Skill reads context query: "testing"
2. Skill surfaces skills relevant to testing: `$qa-plan`, `$smoke-check`,
   `$regression-suite`, `$test-setup`, `$test-evidence-review`
3. Output is focused on testing workflow, not general sprint navigation
4. Currently in-review story is highlighted as a testing candidate

**Assertions:**
- [ ] Context query is acknowledged in output ("Help topic: testing")
- [ ] At least 3 testing-relevant skills are listed
- [ ] General sprint skills (e.g., `$sprint-plan`) are not the primary suggestions
- [ ] Verdict is HELP COMPLETE

---

### Case 5: Director Gate Check — No gate; help is read-only navigation

**Fixture:**
- Any project state

**Input:** `$help`

**Expected behavior:**
1. Skill produces workflow guidance summary
2. No director agents are spawned
3. No gate IDs appear in output
4. No write tool is called

**Assertions:**
- [ ] No director gate is invoked
- [ ] No write tool is called
- [ ] No gate skip messages appear
- [ ] Verdict is HELP COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Reads stage, sprint, and session state before generating suggestions
- [ ] Suggestions are specific to the current project state (not generic)
- [ ] Context query (if provided) narrows the suggestion set
- [ ] Does not write any files
- [ ] Verdict is HELP COMPLETE in all cases

---

## Coverage Notes

- The case where the active sprint is complete (all stories Done) is not
  separately tested; the skill would suggest `$sprint-plan` for the next sprint.
- The `$help` skill does not validate whether suggested skills are available —
  it assumes standard skill catalog availability.
- Stage detection fallback (when stage.txt is absent) delegates to the same
  logic as `$project-stage-detect` and is not re-tested here in detail.
