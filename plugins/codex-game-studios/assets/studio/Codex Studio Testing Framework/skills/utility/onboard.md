# Skill Test Spec: $onboard

## Codex Runtime Contract

- Runtime skill: `.agents/skills/onboard/SKILL.md`
- Runtime name: `onboard`
- Runtime trigger description: `"Use when a contributor or agent needs a role-specific summary of project state, architecture, conventions, and priorities."`
- Native invocation: `$onboard`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$onboard` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keyword: ONBOARDING COMPLETE
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff suggesting a relevant follow-on skill

---

## Director Gate Checks

None. `$onboard` is a read-only orientation skill. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — Configured project in Production stage with active sprint

**Fixture:**
- `production/stage.txt` contains `Production`
- `.codex/docs/technical-preferences.md` has engine, language, and specialists populated
- `production/sprints/sprint-005.md` exists with stories in progress
- Git log contains 5 recent commits

**Input:** `$onboard`

**Expected behavior:**
1. Skill reads stage.txt, .codex/docs/technical-preferences.md, active sprint, and git log
2. Skill produces an onboarding summary with sections: Project Overview, Tech Stack,
   Current Stage, Active Sprint Summary, Recent Activity
3. Summary is formatted for readability (headers, bullet points)
4. Next-step suggestions are appropriate for Production stage (e.g., `$sprint-status`,
   `$dev-story`)
5. Verdict ONBOARDING COMPLETE is stated

**Assertions:**
- [ ] Output includes current stage name from stage.txt
- [ ] Output includes engine and language from .codex/docs/technical-preferences.md
- [ ] Active sprint stories are summarized (not just the sprint file name)
- [ ] Recent commit context is present
- [ ] Verdict is ONBOARDING COMPLETE
- [ ] No files are written

---

### Case 2: Fresh Project — No engine, no sprint, suggests $start

**Fixture:**
- `.codex/docs/technical-preferences.md` contains only placeholders (`[TO BE CONFIGURED]`)
- No `production/stage.txt`
- No sprint files
- No AGENTS.md overrides beyond defaults

**Input:** `$onboard`

**Expected behavior:**
1. Skill reads all config files and detects unconfigured state
2. Skill produces a minimal summary: "This project has not been configured yet"
3. Output explains the onboarding workflow: `$start` → `$setup-engine` → `$brainstorm`
4. Skill suggests running `$start` as the immediate next step
5. Verdict is ONBOARDING COMPLETE (informational, not a failure)

**Assertions:**
- [ ] Output explicitly mentions the project is not yet configured
- [ ] `$start` is recommended as the next step
- [ ] Skill does NOT error out — it gracefully handles an empty project state
- [ ] Verdict is still ONBOARDING COMPLETE

---

### Case 3: No AGENTS.md Found — Error with remediation

**Fixture:**
- `AGENTS.md` file does not exist (deleted or never created)
- All other files may or may not exist

**Input:** `$onboard`

**Expected behavior:**
1. Skill attempts to read AGENTS.md and fails
2. Skill outputs an error: "AGENTS.md not found — cannot generate onboarding summary"
3. Skill provides remediation: "Run `$start` to initialize the project configuration"
4. No partial summary is generated

**Assertions:**
- [ ] Error message clearly identifies the missing file as AGENTS.md
- [ ] Remediation step (`$start`) is explicitly named
- [ ] Skill does NOT produce a partial output when the root config is missing
- [ ] Verdict is ONBOARDING COMPLETE (with error context, not a crash)

---

### Case 4: Role-Specific Onboarding — User specifies "artist" role

**Fixture:**
- Fully configured project in Production stage
- `art-bible.md` exists in `design/`
- Active sprint has visual story types (animation, VFX)

**Input:** `$onboard artist`

**Expected behavior:**
1. Skill reads all standard files plus any art-relevant docs (art bible, asset specs)
2. Summary is tailored to the artist role: art bible overview, asset pipeline,
   current visual stories in the active sprint
3. Technical architecture details (code structure, ADRs) are de-emphasized
4. Specialist agents for art/audio are highlighted in the summary
5. Verdict is ONBOARDING COMPLETE

**Assertions:**
- [ ] Role argument is acknowledged in the output ("Onboarding for: Artist")
- [ ] Art bible summary is included if the file exists
- [ ] Current visual stories from the active sprint are shown
- [ ] Technical implementation details are not the primary focus
- [ ] Verdict is ONBOARDING COMPLETE

---

### Case 5: Director Gate Check — No gate; onboard is read-only orientation

**Fixture:**
- Any configured project state

**Input:** `$onboard`

**Expected behavior:**
1. Skill completes the full onboarding summary
2. No director agents are spawned at any point
3. No gate IDs appear in the output
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] No director gate is invoked
- [ ] No write tool is called
- [ ] No gate skip messages appear
- [ ] Verdict is ONBOARDING COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Reads all source files before generating output (no hallucinated project state)
- [ ] Adapts output to project stage (Production ≠ Concept)
- [ ] Respects role argument when provided
- [ ] Does not write any files
- [ ] Ends with ONBOARDING COMPLETE verdict in all paths

---

## Coverage Notes

- The case where `.codex/docs/technical-preferences.md` is missing entirely (as opposed to
  having placeholders) is not separately tested; behavior follows the graceful
  error pattern of Case 3.
- Git history reading is assumed available; offline/no-git scenarios are not
  tested here.
- Discipline roles beyond "artist" (e.g., programmer, designer, producer) follow
  the same tailoring pattern as Case 4 and are not separately tested.
