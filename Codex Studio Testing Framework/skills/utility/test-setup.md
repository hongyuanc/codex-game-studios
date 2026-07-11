# Skill Test Spec: $test-setup

## Codex Runtime Contract

- Runtime skill: `.agents/skills/test-setup/SKILL.md`
- Runtime name: `test-setup`
- Runtime trigger description: `"Use when a configured game engine lacks test directories, runner configuration, smoke seeds, or continuous-integration test wiring."`
- Native invocation: `$test-setup`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$test-setup` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (e.g., `$test-helpers` to generate helper utilities)

---

## Director Gate Checks

None. `$test-setup` is a scaffolding utility. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — Godot project, scaffolds GdUnit4 test structure

**Fixture:**
- `technical-preferences.md` has engine set to Godot 4, language GDScript
- `tests/` directory does not exist yet

**Input:** `$test-setup`

**Expected behavior:**
1. Skill reads engine from `technical-preferences.md` → Godot 4 + GDScript
2. Skill drafts the test directory structure: tests/unit/, tests/integration/,
   tests/performance/, tests/playtest/, and a GdUnit4 runner config file
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
4. Directories and GdUnit4 runner script created on approval
5. Skill confirms the runner script matches the CI command in coding-standards.md:
   `godot --headless --script tests/gdunit4_runner.gd`
6. Verdict is COMPLETE

**Assertions:**
- [ ] All 4 subdirectories (unit/, integration/, performance/, playtest/) are created
- [ ] GdUnit4 runner config is generated
- [ ] Runner script path matches coding-standards.md CI command
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE

---

### Case 2: Unity Project — Scaffolds Unity Test Runner with asmdef

**Fixture:**
- `technical-preferences.md` has engine set to Unity, language C#
- `tests/` directory does not exist

**Input:** `$test-setup`

**Expected behavior:**
1. Skill reads engine → Unity + C#
2. Skill creates `Tests/` directory with Unity conventions (capitalized)
3. Skill generates `Tests/Tests.asmdef` and `Tests/Editor/EditorTests.asmdef`
4. EditMode and PlayMode test runner modes are configured
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Verdict is COMPLETE

**Assertions:**
- [ ] Unity-specific `Tests/` structure is created (not the Godot structure)
- [ ] `.asmdef` files are generated
- [ ] EditMode and PlayMode runner config is present
- [ ] Verdict is COMPLETE

---

### Case 3: Test Framework Already Exists — Verifies config, not re-initialized

**Fixture:**
- `tests/unit/`, `tests/integration/` exist
- GdUnit4 runner script exists (Godot project)

**Input:** `$test-setup`

**Expected behavior:**
1. Skill detects existing tests/ structure
2. Skill reports: "Test framework already exists — verifying configuration"
3. Skill checks: runner script path, directory completeness, CI command alignment
4. If all checks pass: reports "Configuration verified — no changes needed"
5. If checks fail (e.g., missing tests/performance/): reports specific gap and
   The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Skill does NOT reinitialize when framework exists
- [ ] Verification checks are performed on existing structure
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE whether everything was OK or gaps were fixed

---

### Case 4: No Engine Configured — Redirects to $setup-engine

**Fixture:**
- `technical-preferences.md` contains only placeholders (engine not set)

**Input:** `$test-setup`

**Expected behavior:**
1. Skill reads `technical-preferences.md` and finds engine placeholder
2. Skill reports: "Engine not configured — cannot scaffold engine-specific test framework"
3. Skill suggests running `$setup-engine` first
4. No directories or files are created

**Assertions:**
- [ ] Error message explicitly states engine is not configured
- [ ] `$setup-engine` is suggested as the next step
- [ ] No write tool is called
- [ ] Verdict is not COMPLETE (blocked state)

---

### Case 5: Director Gate Check — No gate; test-setup is a scaffolding utility

**Fixture:**
- Engine configured, tests/ does not exist

**Input:** `$test-setup`

**Expected behavior:**
1. Skill scaffolds and writes all test framework files
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Reads engine from `technical-preferences.md` before generating any scaffold
- [ ] Generates engine-appropriate test runner config (not generic)
- [ ] Creates all 4 subdirectories from coding-standards.md
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Detects existing framework and offers verification (not reinitialization)
- [ ] Verdict is COMPLETE when scaffold is in place

---

## Coverage Notes

- Unreal Engine test scaffolding (headless runner with `-nullrhi`) follows the
  same pattern as Cases 1 and 2 and is not separately fixture-tested.
- CI integration file generation (e.g., `.github/workflows/test.yml`) is
  referenced but not assertion-tested here — it may be a separate skill concern.
- The case where tests/ exists but is from a different engine (e.g., Unity tests
  in a now-Godot project) is not tested; the skill would detect the mismatch
  and offer to reconcile.
