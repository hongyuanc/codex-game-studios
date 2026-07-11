# Codex Migration Baseline

Captured on 2026-07-11 before the Codex-only migration changed any migration input.

## Artifact inventory

| Inventory | Count |
| --- | ---: |
| `.claude/agents/**/*.md` | 49 |
| `.claude/skills/**/SKILL.md` | 73 |
| `.codex/agents/**/*.toml` | 49 |
| `.agents/skills/**/SKILL.md` | 73 |

## Git status

The exact output of `git status --short` was:

```text
?? .agents/
?? .codex/
?? AGENTS.md
?? docs/superpowers/
```

## Known user changes

The untracked `.agents/`, `.codex/`, `AGENTS.md`, and `docs/superpowers/` paths are the existing Codex draft. They predate this baseline and must be preserved as migration inputs rather than treated as changes introduced by the migration implementation.

## Authoritative migration inputs

- The approved migration design at `docs/superpowers/specs/2026-07-11-codex-game-studios-migration-design.md` defines the target architecture and validation criteria.
- `CLAUDE.md` and `.claude/` define the authoritative source behavior, including the 49-agent roster and 73-skill workflow catalog.
- The existing `.agents/`, `.codex/`, and `AGENTS.md` draft provides partially converted content to retain where it agrees with the approved design and authoritative source behavior.

Claude artifacts remain authoritative migration inputs until Plan 7 passes final validation.
