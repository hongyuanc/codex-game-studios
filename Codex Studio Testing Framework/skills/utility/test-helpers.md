# Skill Test Spec: $test-helpers

## Codex Runtime Contract

- Runtime skill: `.agents/skills/test-helpers/SKILL.md`
- Runtime name: `test-helpers`
- Runtime trigger description: `"Use when repeated test setup, assertions, factories, or engine-specific fixtures are creating boilerplate across test files."`
- Native invocation: `$test-helpers`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$test-helpers` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (e.g., write a test using the generated helper)

---

## Director Gate Checks

None. `$test-helpers` is a scaffolding utility. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — Player factory helper generated for Godot/GDScript

**Fixture:**
- `technical-preferences.md` has engine Godot 4, language GDScript
- `tests/` directory exists (test-setup has been run)
- `design/gdd/player.md` exists with defined player properties
- No existing helpers in `tests/helpers/`

**Input:** `$test-helpers player-factory`

**Expected behavior:**
1. Skill reads engine (Godot 4 / GDScript) and player GDD for property context
2. Skill generates a deterministic `PlayerFactory` helper in GDScript:
   - `create_player(health: int = 100, speed: float = 200.0)` function
   - Returns a player node pre-configured to a known state
   - Uses dependency injection (no singletons)
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
4. File is written on approval; verdict is COMPLETE

**Assertions:**
- [ ] Generated helper is in GDScript (not C# or Blueprint)
- [ ] Factory function parameters use defaults matching GDD values
- [ ] Helper uses dependency injection (no Autoload/singleton references)
- [ ] Filename follows snake_case convention for GDScript
- [ ] Verdict is COMPLETE

---

### Case 2: No Test Setup Exists — Redirects to $test-setup

**Fixture:**
- `tests/` directory does not exist

**Input:** `$test-helpers player-factory`

**Expected behavior:**
1. Skill checks for `tests/` directory — not found
2. Skill reports: "Test directory not found — test framework must be set up first"
3. Skill suggests running `$test-setup` before generating helpers
4. No helper file is created

**Assertions:**
- [ ] Error message identifies the missing tests/ directory
- [ ] `$test-setup` is suggested as the prerequisite step
- [ ] No write tool is called
- [ ] Verdict is not COMPLETE (blocked state)

---

### Case 3: Helper Already Exists — Offers to extend rather than replace

**Fixture:**
- `tests/helpers/player_factory.gd` already exists with a `create_player()` function
- User requests a new `create_enemy()` function be added to the factory

**Input:** `$test-helpers enemy-factory`

**Expected behavior:**
1. Skill finds an existing `player_factory.gd` and checks if it's the right file
   to extend (or if a separate `enemy_factory.gd` should be created)
2. Skill presents options: add `create_enemy()` to existing factory or create
   `tests/helpers/enemy_factory.gd`
3. User selects extend; skill drafts the `create_enemy()` function
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. Function is added on approval; verdict is COMPLETE

**Assertions:**
- [ ] Existing helper is detected and surfaced
- [ ] User is given extend vs. new file choice
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Existing `create_player()` is preserved in the extended file
- [ ] Verdict is COMPLETE

---

### Case 4: System Has No GDD — Notes missing design context in helper

**Fixture:**
- `technical-preferences.md` has Godot 4 / GDScript
- `tests/` exists
- User requests a helper for the "inventory system" but no `design/gdd/inventory.md` exists

**Input:** `$test-helpers inventory-factory`

**Expected behavior:**
1. Skill looks for `design/gdd/inventory.md` — not found
2. Skill notes: "No GDD found for inventory — generating helper with placeholder defaults"
3. Skill generates an `inventory_factory.gd` with generic placeholder values
   (item_count = 0, max_capacity = 20) and a comment: "# TODO: align defaults
   with inventory GDD when written"
4. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
5. File is written; verdict is COMPLETE with advisory note

**Assertions:**
- [ ] Skill proceeds without GDD (does not block)
- [ ] Generated helper has placeholder defaults with TODO comment
- [ ] Missing GDD is noted in the output (advisory warning)
- [ ] Verdict is COMPLETE

---

### Case 5: Director Gate Check — No gate; test-helpers is a scaffolding utility

**Fixture:**
- Engine configured, tests/ exists

**Input:** `$test-helpers player-factory`

**Expected behavior:**
1. Skill generates and writes the helper file
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Reads engine before generating any helper (helpers are engine-specific)
- [ ] Reads GDD for default values when available
- [ ] Notes missing GDD context rather than blocking
- [ ] Detects existing helper files and offers extend rather than replace
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE when helper is written

---

## Coverage Notes

- Mock/stub helper generation (for dependencies like save systems or audio buses)
  follows the same pattern as factory helpers and is not separately tested.
- Unity C# helper generation (using NSubstitute or custom mocks) follows the
  same logic as Case 1 with language-appropriate output.
- The case where the requested helper type is not recognized is not tested;
  the skill would ask the user to clarify the helper type.
