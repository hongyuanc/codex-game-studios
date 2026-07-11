# Upgrading to Codex Game Studios

This is the migration guide for projects created with the pre-Codex source system.
Source-system names and paths below are historical evidence only. The current
repository is Codex-only and has no operational bridge to the source system.

## Choose a migration strategy

Choose the smallest strategy that preserves your project-owned work:

1. **Fresh template plus content copy** — safest for lightly customized games.
   Create a new Codex Game Studios project, then copy game code, assets, design,
   architecture, and production artifacts into it.
2. **In-place overlay** — best when Git history and directory layout must stay
   intact. Apply the native runtime files on a migration branch and reconcile
   conflicts deliberately.
3. **Manual component migration** — best for heavily customized studio forks.
   Port instructions, skills, profiles, hooks, and references one category at a
   time using the mapping below.

Do not combine strategies mid-migration without first recording which runtime
surface owns each behavior.

## Preserve project-owned work

Before migrating, create a branch and a recoverable backup. Preserve:

- game source, assets, tests, plugins, build scripts, and engine metadata;
- completed GDDs, ADRs, UX specs, level documents, and art/audio bibles;
- production plans, bugs, playtest evidence, release records, and analytics;
- project-specific instruction changes, custom skills, profiles, and hooks;
- engine reference updates newer than the template defaults.

Never replace a filled-in game artifact with an empty template. Record hashes or
use `git diff --no-index` when a customized file has no clear native equivalent.

## Map the runtime surfaces

| Historical source responsibility | Native Codex destination |
| --- | --- |
| Root durable guidance | `AGENTS.md` |
| Directory-scoped guidance | nested `AGENTS.md` files |
| Skills | `.agents/skills/<name>/SKILL.md` |
| Core custom agents | `.codex/agents/*.toml` |
| Engine specialists | `.codex/agent-packs/<engine>/*.toml` |
| Project configuration | `.codex/config.toml` and `.codex/studio.toml` |
| Hook registration | `.codex/hooks.json` |
| Hook implementation | `.codex/hooks/hook_runner.py` |
| Studio references | `.codex/docs/` |

<!-- historical-source-start -->
The historical inventory is retained at
`production/migration/claude-to-codex-coverage.yaml`. It is audit evidence, not
an operational dependency.
<!-- historical-source-end -->

## Merge without losing customizations

For each mapped surface:

1. Compare the old customization with the native file and identify its intent.
2. Keep project facts and policies; discard provider-specific syntax.
3. Merge durable instructions into the nearest `AGENTS.md` scope.
4. Merge engine, language, pack, and review-mode values into
   `.codex/studio.toml`; do not copy configuration keys blindly.
5. Re-express skill invocations as `$skill-name` and ensure each skill's
   `description` accurately declares its trigger.
6. Convert custom agents to TOML profiles with OpenAI GPT model routing.
7. Port hook behavior into a named Python action and add focused tests before
   enabling it in `.codex/hooks.json`.
8. Keep only one engine pack active. Preserve unselected packs as inactive
   templates rather than merging all specialists into the active roster.

When both versions changed the same workflow, prefer the native safety and
phase-gating contract, then reapply the project's domain-specific behavior.

## Breaking changes

- Skills are invoked as `$skill-name` and discovered under `.agents/skills/`.
- Custom agents are TOML profiles under `.codex/agents/`; engine profiles live
  in `.codex/agent-packs/`.
- Sol, Terra, and Luna route exclusively to OpenAI GPT models.
- Hooks are registered in `.codex/hooks.json` and dispatched through one Python
  runner with 10 actions.
- Approval is phase-gated. An approved story changeset can be implemented and
  tested without per-file prompts, while material decisions and scope expansion
  return to the user.
- Commits, pushes, releases, destructive operations, and publication remain
  explicitly gated.
- `$setup-engine` activates exactly one Godot, Unity, or Unreal pack.

## Recommended in-place sequence

1. Create and switch to a migration branch.
2. Preserve the project-owned files listed above.
3. Install the native `AGENTS.md`, `.agents/`, and `.codex/` surfaces.
4. Merge project values into `.codex/docs/technical-preferences.md` and
   `.codex/studio.toml`.
5. Reapply custom skills, profiles, and hook actions using the native contracts.
6. Run `$adopt` to audit existing artifacts.
7. Run `$setup-engine` if `active_engine_pack` is still `none`.
8. Review the migration diff before deleting any historical runtime files.

## Verification checklist

- [ ] Project code, assets, design, architecture, and production artifacts match the backup.
- [ ] `AGENTS.md` imports resolve and no operational instruction points at retired paths.
- [ ] Exactly 73 native skills are discoverable and use `$skill-name` syntax.
- [ ] Exactly 49 profiles exist across core agents and engine packs.
- [ ] `.codex/studio.toml` selects zero or one engine pack, never several.
- [ ] All 10 hook actions run through `.codex/hooks/hook_runner.py`.
- [ ] Public Markdown links resolve.
- [ ] The focused and full studio suites pass.
- [ ] The final validator passes.

```bash
python3 -m unittest discover -s tests/studio -v
python3 -m tools.codex_studio.validate --root . --phase final
```

## Rollback

If verification fails, stop before merging. Save the migration diff and test
output, return to the pre-migration branch or backup, and retry with the manual
component strategy. Do not use a destructive reset when it would discard
uncommitted game work. The historical coverage manifest and migration plans may
remain for audit; they do not need to be loaded by Codex at runtime.
