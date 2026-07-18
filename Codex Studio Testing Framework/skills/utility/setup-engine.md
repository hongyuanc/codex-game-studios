# Skill Test Spec: $setup-engine

## Codex Runtime Contract

- Runtime skill: `.agents/skills/setup-engine/SKILL.md`
- Runtime name: `setup-engine`
- Runtime trigger description: `Use when you need to configure and safely activate one native Codex engine-specialist pack for Godot, Unity, or Unreal.`
- Native invocation: `$setup-engine`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$setup-engine` is tested against the exact runtime discovery contract above. The five
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
- [ ] Has a next-step handoff (e.g., `$brainstorm` or `$start` depending on flow)

---

## Director Gate Checks

None. `$setup-engine` is a technical configuration skill. No director gates apply.

---

## Test Cases

### Case 1: Godot 4 + GDScript — Full engine configuration

**Fixture:**
- `.codex/docs/technical-preferences.md` contains only placeholders
- Engine argument provided: `godot`
- User decisions during workflow: exact version `Godot 4`; primary language `GDScript`.

**Input:** `$setup-engine godot`

**Expected behavior:**
1. Skill skips engine-selection step (argument provided)
2. Skill asks for the exact engine version; user selects Godot 4
3. Skill presents Godot language options; user selects GDScript
4. Skill drafts all engine sections: engine/language/rendering/physics fields,
   naming conventions (snake_case for GDScript), specialist assignments
   (`godot-specialist`, `godot-gdscript-specialist`,
   `godot-shader-specialist`, etc.)
5. Skill populates the routing table: `.gd` → `godot-gdscript-specialist`,
   `.gdshader` → `godot-shader-specialist`, `.tscn` → `godot-specialist`
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
7. File is written after approval; verdict is COMPLETE

**Assertions:**
- [ ] Engine field is set to Godot 4 (not a placeholder)
- [ ] Language field is set to GDScript
- [ ] Naming conventions are GDScript-appropriate (snake_case)
- [ ] Routing table includes `.gd`, `.gdshader`, and `.tscn` entries
- [ ] Specialists are assigned (not placeholders)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Verdict is COMPLETE

---

### Case 2: Unity + C# — Unity-specific configuration

**Fixture:**
- `.codex/docs/technical-preferences.md` contains only placeholders
- Engine argument provided: `unity`
- User decisions during workflow: an exact supported Unity version; primary language `C#`; concrete target platform, primary input, testing framework, and performance budget.

**Input:** `$setup-engine unity`

**Expected behavior:**
1. Skill skips engine-selection step (argument provided)
2. Skill asks for the exact engine version; user selects an exact supported Unity version
3. Skill records and confirms C# as Unity's only supported primary language
4. Skill gathers target platform
5. Skill gathers primary input
6. Skill gathers testing framework
7. Skill gathers performance budget
8. Skill sets engine to Unity and language to C#
9. Naming conventions are C#-appropriate (PascalCase for classes, camelCase for fields)
10. Specialist assignments reference `unity-specialist` and other profiles from
   the exact five-profile Unity pack
11. Routing table: `.cs` → `unity-specialist`, `.asmdef` → `unity-specialist`,
   `.unity` → `unity-specialist` for scene files
12. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Engine field is set to Unity (not Godot or Unreal)
- [ ] Language field is set to C#
- [ ] Naming conventions reflect C# conventions
- [ ] Routing table includes `.cs`, `.asmdef`, and `.unity` entries
- [ ] Verdict is COMPLETE

---

### Case 3: Unreal + Blueprint — Unreal-specific configuration

**Fixture:**
- `.codex/docs/technical-preferences.md` contains only placeholders
- Engine argument provided: `unreal`
- User decisions during workflow: exact version `Unreal Engine 5`; primary language `Blueprint (Visual Scripting)`.

**Input:** `$setup-engine unreal`

**Expected behavior:**
1. Skill skips engine-selection step (argument provided)
2. Skill asks for the exact engine version; user selects Unreal Engine 5
3. Skill presents Unreal language options; user selects Blueprint (Visual Scripting)
4. Skill sets engine to Unreal Engine 5 and primary language to Blueprint (Visual Scripting)
5. Specialist assignments reference `unreal-specialist` and
   `ue-blueprint-specialist`
6. Routing table: `.uasset` → `ue-blueprint-specialist` for Blueprint assets or
   `unreal-specialist` otherwise; `.umap` → `unreal-specialist`
7. Skill asks for the performance budget; user accepts the offered frame/memory defaults or supplies a target
8. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Engine field is set to Unreal Engine 5
- [ ] Language field is Blueprint (Visual Scripting)
- [ ] Routing table includes `.uasset` and `.umap` entries
- [ ] Blueprint specialist is assigned
- [ ] Verdict is COMPLETE

---

### Case 4: Engine Already Configured — Offers to reconfigure specific sections

**Fixture:**
- The six-field studio authority is valid for Godot 4 + GDScript
- `.codex/active-engine.json` validates for that selection, and exactly five Godot profiles exist and match their recorded hashes
- For Godot 4 + GDScript, all technical-preference sections are populated in `.codex/docs/technical-preferences.md`
- No engine argument provided

**Input:** `$setup-engine`

**Expected behavior:**
1. Skill reads studio authority, the active manifest and profiles, and technical preferences, then detects a fully configured Godot 4 + GDScript engine
2. Skill reports: "Engine already configured as Godot 4 + GDScript"
3. Skill presents options: reconfigure all, reconfigure specific section only
   (Engine/Language, Naming Conventions, Specialists, Performance Budgets)
4. User selects "Reconfigure Performance Budgets only"
5. Only the performance budget section is updated; all other fields unchanged
6. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] Skill does NOT overwrite all fields when only a section update was requested
- [ ] User is offered section-specific reconfiguration
- [ ] Only the selected section is modified in the written file
- [ ] Verdict is COMPLETE

---

### Case 5: Director Gate Check — No gate; setup-engine is a utility skill

**Fixture:**
- Fresh project with no engine configured

**Input:** `$setup-engine godot`

**Expected behavior:**
1. Skill completes full engine configuration
2. No director agents are spawned at any point
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is COMPLETE without any gate check

---

## Protocol Compliance

- [ ] Presents draft configuration before asking to write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Respects engine argument when provided (skips selection step)
- [ ] Detects existing config and offers partial reconfigure
- [ ] Routing table is populated for all key file types for the chosen engine
- [ ] Verdict is COMPLETE after file is written

---

## Coverage Notes

- Godot 4 + C# (instead of GDScript) follows the same flow as Case 1 with
  different naming conventions and the godot-csharp-specialist assignment.
  This variant is not separately tested.
- The engine-version-specific guidance (e.g., Godot 4.6 knowledge gap warning
  from VERSION.md) is surfaced by the skill but not assertion-tested here.
- Performance budget values are user-approved: the user may accept offered
  frame/memory defaults or supply a target. Exact values are not assertion-tested.
