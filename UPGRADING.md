# Upgrading to Codex Game Studios

This guide is a historical migration record for projects created from the
Claude Code Game Studios source system. The current repository is Codex-only
and does not retain operational compatibility with the source runtime.

## Preserve project-owned work

Before migrating, commit or back up game code, assets, GDDs, ADRs, production
records, engine references, and any customized instructions. Do not overwrite
filled-in game documents with template placeholders.

## Map the runtime surfaces

| Source-system responsibility | Codex destination |
| --- | --- |
| Root durable guidance | `AGENTS.md` |
| Directory-scoped guidance | nested `AGENTS.md` files |
| Skills | `.agents/skills/<name>/SKILL.md` |
| Core custom agents | `.codex/agents/*.toml` |
| Engine specialists | `.codex/agent-packs/<engine>/*.toml` |
| Project configuration | `.codex/config.toml` and `.codex/studio.toml` |
| Hooks | `.codex/hooks.json` and `.codex/hooks/` |
| Studio references | `.codex/docs/` |

The migration intentionally changes invocation syntax to `$skill`, model routing
to Sol/Terra/Luna GPT profiles, and approvals to phase-gated autonomy. It also
keeps all engine packs inactive until `$setup-engine` activates exactly one.

## Recommended migration

1. Move durable instructions into `AGENTS.md` and the 11 nested instruction files.
2. Merge project-specific values into `.codex/docs/technical-preferences.md`.
3. Copy only project-owned customizations into the native skills and profiles.
4. Review `.codex/config.toml`, `.codex/studio.toml`, and `.codex/hooks.json`.
5. Run `$adopt` for an existing game, then `$setup-engine` if no pack is active.
6. Run the studio test suite and final repository validator.

```bash
python3 -m unittest discover -s tests/studio -v
python3 -m tools.codex_studio.validate --root . --phase final
```

The coverage evidence at `production/migration/claude-to-codex-coverage.yaml`
records how every source-system runtime artifact was migrated or retired. Keep
that file and the migration plans as audit history; they are not runtime
dependencies.
