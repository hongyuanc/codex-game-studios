# Plugin-Native Studio Distribution Design

## Goal

Installing the Codex Game Studios plugin must make the complete studio skill
catalog available immediately. A user should not have to approve a 514-action
repository installation before using the studio.

The primary fresh-project flow is:

```text
Install plugin -> start a new task -> run $codex-game-studios:start
```

Natural-language requests may select the same bundled skill automatically. The
explicit namespaced form is the documented, unambiguous invocation.

## Current Problem

The 1.0.x plugin bundles only one lifecycle skill. That skill drives a retained
manager which copies 513 payload entries into every target repository. The
payload includes 146 entries for the 73 studio skills alone: one directory and
one `SKILL.md` per skill.

This architecture provides strong collision, rollback, repair, and uninstall
guarantees, but it treats globally distributable plugin capabilities as if they
were project data. The result is a large approval plan, slow first use, and a
manager-centric interface.

## Distribution Architecture

### Plugin-bundled skills

All 73 studio skills are bundled under the plugin's declared `skills/`
directory. Codex installs and discovers them together with the plugin. Their
labels use the normal plugin namespace, such as `Codex Game Studios: Start`,
`Codex Game Studios: Brainstorm`, and `Codex Game Studios: Setup Engine`.

The plugin identifier and display name remain `codex-game-studios` and
`Codex Game Studios`. The duplicated `Codex Game Studios: Codex Game Studios`
manager label is removed.

The repository `.agents/skills/` tree remains the canonical authoring source.
The deterministic plugin builder mirrors those skills into the plugin package
and verifies exact inventory and content parity. Fresh project setup never
copies `.agents/skills/` into the target repository.

### Plugin-local shared resources

Static studio resources remain in the plugin package and are read on demand:

- workflow templates and director-gate rules;
- role and agent-pack definitions;
- testing-framework guidance;
- Godot, Unity, and Unreal reference material; and
- validation and setup utilities.

Skills must not require those resources to exist at fixed project paths. The
canonical skill instructions will resolve project-owned state first and then
use their plugin-bundled references. Cross-skill dependencies use skill
discovery and invocation rather than testing for another skill at
`.agents/skills/<name>/SKILL.md`.

### Minimal project initialization

`$codex-game-studios:start` works before project initialization. It detects
project state and offers a small, reviewable initialization changeset only when
persistent project state is needed.

Fresh initialization may create or merge only project-specific authority and
guidance, such as:

- `.codex/studio.toml`;
- `.codex/docs/technical-preferences.md`;
- a bounded managed block in `AGENTS.md` or `.codex/config.toml` when required;
  and
- directories or artifacts selected by the user during the active workflow.

Fresh initialization must contain at most ten mutating actions. It must not
pre-create empty game directories, install all engine references, install the
testing framework, or copy the global skill catalog.

Engine-specific project state is created only after the user selects an engine.
Unselected engine references remain plugin-local.

### Agent coordination

Role definitions and pack metadata remain plugin-local. Team skills load the
required role definition and delegate with explicit role instructions and
model settings. They do not require 49 persistent project-local agent files.

When the current Codex surface does not support delegation, the skill degrades
to the documented single-agent path instead of requiring a repository-wide
agent installation.

## Legacy Compatibility

The 1.0.x manager scripts and payload contract remain available internally for
one major-version migration window. They are not the fresh-project entry point.

When `.codex/codex-game-studios/installation.json` exists, `Start` detects the
legacy installation and offers a digest-bound migration plan. Migration:

1. verifies the recorded 1.0.x installation;
2. removes only unchanged manager-owned copies that are redundant in the
   plugin-native model;
3. preserves customized and project-owned files;
4. retains the minimal project-specific configuration; and
5. records the migrated state before reporting success.

Legacy verify, repair, and uninstall remain reachable through `Start` while the
migration window is supported. A fresh repository never needs the legacy
manager.

## Versioning

The plugin-native model changes skill identifiers and the normal entry flow, so
it is released as version `2.0.0`. Version `1.0.1` remains an unreleased local
fix for the 1.0.x mutable-cache apply failure; its immutable payload snapshot
logic is retained in the legacy migration path.

## Error Handling

- Plugin installation itself performs no target-repository writes.
- Missing or malformed project configuration is reported by `Start` with a
  bounded proposed initialization changeset.
- Missing plugin resources or skill-inventory drift fail plugin validation and
  release packaging.
- Legacy state never triggers automatic mutation; migration requires the exact
  digest-bound approval protocol.
- Any project write reports what changed and preserves the existing recovery
  guarantees appropriate to that bounded operation.

## Testing and Acceptance Criteria

- Installing the plugin exposes exactly the 73 studio workflow skills plus no
  duplicated lifecycle skill.
- A new task can invoke `$codex-game-studios:start` in an unmodified Git game
  repository.
- Plugin installation and skill discovery cause zero writes to that repository.
- Fresh initialization has at most ten mutating actions and never creates
  `.agents/skills/`.
- Every bundled skill passes structural and behavioral validation from its
  installed plugin path.
- Tests reject hardcoded cross-skill dependencies on `.agents/skills/`.
- Godot, Unity, and Unreal setup reads only the selected engine's reference
  material.
- A disposable Embermarch-shaped repository completes Start and engine setup
  while preserving its existing files.
- A representative 1.0.x installation can verify, migrate, repair, and
  uninstall without losing customized or project-owned content.
- Payload freshness, repository validation, compilation, complete plugin tests,
  complete studio tests, and the native Windows lifecycle gate pass before any
  separately authorized publication.

## Scope Boundaries

This redesign does not push, tag, release, publish, modify the real Embermarch
repository, or remove the legacy safety mechanisms before their migration
window ends.
