# Skill Test Spec: $start

## Codex Runtime Contract

- Runtime skill: `.agents/skills/start/SKILL.md`
- Runtime name: `start`
- Runtime trigger description: `Use when a first-time user needs project-state detection and guidance to the correct Codex Game Studios workflow.`
- Native invocation: `$start`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$start` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: COMPLETE, BLOCKED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end (routes to `$setup-engine`)

---

## Director Gate Checks

None. `$start` is a utility setup skill. No director agents exist yet at the
point this skill runs.

---

## Test Cases

### Case 1: Happy Path — Fresh repo, no engine, full onboarding flow

**Fixture:**
- Empty repository: no AGENTS.md overrides, no `production/stage.txt`, no
  `technical-preferences.md` content beyond placeholders
- No existing design docs or source code

**Input:** `$start`

**Expected behavior:**
1. Skill detects no existing configuration and begins fresh onboarding
2. Skill asks for project name
3. Skill presents 3 engine options: Godot 4, Unity, Unreal Engine 5
4. User selects an engine
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Skill creates all directories defined in `directory-structure.md`
7. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
8. Skill routes to `$setup-engine [chosen-engine]` to complete technical config

**Assertions:**
- [ ] Project name is captured before any file is written
- [ ] Exactly 3 engine options are presented
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] No file is written without explicit user approval
- [ ] Handoff to `$setup-engine` occurs at the end with the chosen engine argument
- [ ] Verdict is COMPLETE after all files are written and handoff is issued

---

### Case 2: Already Configured — Detects existing config, offers to skip or reconfigure

**Fixture:**
- `technical-preferences.md` has engine already set (not placeholder)
- `production/stage.txt` exists with `Concept`

**Input:** `$start`

**Expected behavior:**
1. Skill reads `technical-preferences.md` and detects configured engine
2. Skill reports: "This project is already configured with [engine]"
3. Skill presents options: skip (exit), reconfigure engine, or reconfigure specific sections
4. If user selects skip: skill exits cleanly with a summary of current config
5. If user selects reconfigure: skill proceeds to the engine-selection step

**Assertions:**
- [ ] Skill does NOT overwrite existing config without user choosing reconfigure
- [ ] Detected engine name is shown to the user in the status message
- [ ] User is offered at least 2 options (skip or reconfigure)
- [ ] Verdict is COMPLETE whether user skips or reconfigures

---

### Case 3: Engine Choice — User picks Godot 4, routes to $setup-engine godot

**Fixture:**
- Fresh repo — no existing configuration

**Input:** `$start`

**Expected behavior:**
1. Skill presents engine options and user selects Godot 4
2. Skill writes initial stubs (directory structure, AGENTS.md) after approval
3. Skill explicitly routes to `$setup-engine godot` as the next step
4. Handoff message clearly names the engine and the next skill invocation

**Assertions:**
- [ ] Handoff command is `$setup-engine godot` (not generic `$setup-engine`)
- [ ] Handoff is issued after all initial stubs are written, not before
- [ ] Engine choice is echoed back to user before writing begins

---

### Case 4: Interrupted Setup — Partial config detected, offers resume or restart

**Fixture:**
- Directory structure exists (was created) but `technical-preferences.md` is
  still all placeholders (engine was never chosen — setup was interrupted)
- No `production/stage.txt`

**Input:** `$start`

**Expected behavior:**
1. Skill detects partial state: directories exist but engine is unconfigured
2. Skill reports: "A partial setup was detected — directories exist but engine is not configured"
3. Skill offers: resume from engine selection, or restart from scratch
4. If resume: skill skips directory creation, proceeds to engine choice
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Partial state is correctly identified (directories present, engine absent)
- [ ] User is offered resume vs. restart choice — not forced into one path
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Restart path asks for permission to overwrite before touching any files

---

### Case 5: Director Gate Check — No gate; start is a utility setup skill

**Fixture:**
- Any fixture

**Input:** `$start`

**Expected behavior:**
1. Skill completes full onboarding flow
2. No director agents are spawned at any point
3. No gate IDs (CD-*, TD-*, AD-*, PR-*) appear in the output

**Assertions:**
- [ ] No director gate is invoked during the skill execution
- [ ] No gate skip messages appear (gates are absent, not suppressed)
- [ ] Skill reaches COMPLETE without any gate verdict

---

## Protocol Compliance

- [ ] Asks for project name before any file is written
- [ ] Presents engine options as a structured choice (not free text)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Ends with a handoff to `$setup-engine` with the engine name as argument
- [ ] Verdict is clearly stated (COMPLETE or BLOCKED) at end of output

---

## Coverage Notes

- The case where the user rejects all engine options and provides a custom
  engine name is not tested — the skill is designed for the three supported
  engines only.
- Git initialization (if any) is not tested here; that is an infrastructure
  concern outside the skill boundary.
- Solo vs. lean mode behavior is not applicable — this skill has no gates and
  mode selection is irrelevant.
