# Codex Game Studios -- Game Studio Agent Architecture

Indie game development managed through 49 coordinated Codex subagents.
Each agent owns a specific domain, enforcing separation of concerns and quality.

## Technology Stack

- **Engine**: [CHOOSE: Godot 4 / Unity / Unreal Engine 5]
- **Language**: [CHOOSE: GDScript / C# / C++ / Blueprint]
- **Version Control**: Git with trunk-based development
- **Build System**: [SPECIFY after choosing engine]
- **Asset Pipeline**: [SPECIFY after choosing engine]

> **Note**: Engine-specialist agents exist for Godot, Unity, and Unreal with
> dedicated sub-specialists. Use the set matching your engine.

## Project Structure

Before adding, moving, or deleting project paths, you must read
`.codex/docs/directory-structure.md`. Keep runtime configuration under
`.codex/`, reusable skills under `.agents/skills/`, game work under `src/` and
`assets/`, design under `design/`, and production evidence under `production/`.

## Engine Version Reference

Before engine- or version-specific work, you must read the active engine's
`docs/engine-reference/<engine>/VERSION.md`. Read
`docs/engine-reference/godot/VERSION.md` only when Godot is active; do not infer
an engine from the template placeholder above.

## Technical Preferences

Before changing source, build configuration, tests, or asset-pipeline behavior,
you must read `.codex/docs/technical-preferences.md`. Treat its configured
engine, language, build/test commands, budgets, and active-pack routing as
project requirements.

## Coordination Rules

Before delegating or coordinating cross-domain work, you must read
`.codex/docs/coordination-rules.md`. Respect role ownership, direct-child
delegation, bounded tasks, parent synthesis, and required director gates.

## Collaboration Protocol

Use phase-gated autonomy. The user approves game concepts, material design and
architecture decisions, scope and milestone changes, destructive operations,
and external publication. After the user approves an implementation story or
phase, Codex may edit the agreed files, add tests, diagnose failures, and
iterate within that boundary.

`.codex/studio.toml` is the sole persistent review-mode authority. Its default
`phase-gated` mode uses lean optional-review depth while phase-transition and
other mandatory director gates still run.

Pause for user direction when work discovers material scope expansion, an
unresolved design ambiguity, a conflict with an accepted ADR, or a required
change outside the approved boundary. No commits, pushes, releases, or external
publication without explicit user instruction.

See `docs/COLLABORATIVE-DESIGN-PRINCIPLE.md` for full protocol and examples.

> **First session?** If the project has no engine configured and no game concept,
> invoke `$start` to begin the guided onboarding flow.

## Coding Standards

Before editing game code, tests, data, or technical documentation, you must read
`.codex/docs/coding-standards.md` and the nearest nested `AGENTS.md`. Follow the
engine-specific conventions after `$setup-engine` fills in the project choices.

## Context Management

Before long-running or multi-agent work, and before context compaction, you must
read `.codex/docs/context-management.md`. Keep durable state in project files,
record handoffs explicitly, and reload the current story and governing design
after compaction.
