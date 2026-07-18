# Codex Game Studios

Build an indie game with a coordinated Codex studio: **49 agents**, **73 skills**,
one user-controlled production workflow.

Codex Game Studios turns a repository into a structured game-development team.
Directors protect product and technical direction, department leads coordinate
work, and specialists implement and verify the game. Godot 4, Unity, and Unreal
Engine 5 are supported through mutually exclusive engine packs.

## Install the plugin

Codex Game Studios is currently distributed through this repository's plugin
marketplace. It is not yet listed in the public Codex Plugins Directory.

### Codex app

1. Clone this repository and open the source repository in the Codex app.
2. Open **Plugins**, select the **Codex Game Studios** repository marketplace,
   and install **Codex Game Studios**.
3. Open the game repository. Start a new Codex task so Codex loads the plugin.
4. Run this in-Codex skill invocation (not a shell command):

```text
$codex-game-studios:start
```

You can close the source repository after the plugin is installed.

### Codex CLI

Install Codex Game Studios from the repository marketplace by adding it and the
plugin from the published `main` branch:

```bash
codex plugin marketplace add hongyuanc/codex-game-studios --ref main
codex plugin add codex-game-studios@codex-game-studios
```

Start a new Codex task in the game repository after installation. Then use this
in-Codex skill invocation, not a shell command:

```text
$codex-game-studios:start
```

The plugin makes all 73 studio skills immediately available when it is installed.
Plugin installation and skill discovery make zero writes to the game repository.
Start first detects the project read-only, then asks for approval only when it
needs a small project-specific state changeset (at most ten mutations). It
never installs a project-local skill catalog or creates `.agents/skills/`.
Codex permissions, explicit approvals, and durable project instructions remain
the authorization boundary.
Use `$setup-engine` after Start when you are ready to choose Godot, Unity, or
Unreal. The selected engine itself must be installed separately to run or export
a game.

## Legacy 1.0.0 lifecycle support

Fresh repositories do not use the 1.0.0 manager. If Start finds the authenticated
schema-1 installation record at `.codex/codex-game-studios/installation.json`, it
offers four legacy choices: verify legacy installation, repair legacy installation,
migrate to plugin-native, or uninstall legacy installation.
Migration, repair, and uninstall present a complete digest-bound plan and wait
for you to explicitly approve it; verification is read-only. This compatibility help is
available only through Start during the migration window.


<!-- upstream-attribution-start -->
## Origins and attribution

Codex Game Studios is an **independent Codex-native adaptation** of
[Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios),
created by [Donchitos](https://github.com/Donchitos).

The original project established the studio concept, specialized-agent
hierarchy, game-development workflows, engine specialists, document templates,
and testing-framework foundation that made this edition possible. We are
grateful to Donchitos and the upstream contributors for publishing that work
under the MIT License.

This repository retains the original copyright and MIT permission notice in
[LICENSE](LICENSE). It is not an official port or endorsement by Donchitos,
Anthropic, or OpenAI. For the original implementation, documentation, and
community, visit the
[upstream repository](https://github.com/Donchitos/Claude-Code-Game-Studios).
<!-- upstream-attribution-end -->

## What this Codex edition adds

> **Not a thin rename.** This edition rebuilds the studio as a native Codex
> system instead of stopping at renamed agent definitions.

- **Native Codex surfaces:** 73 plugin-bundled skills, durable project guidance,
  and small repository-owned configuration created only when needed.
- **GPT studio routing:** the 49 roles are organized as Sol, Terra, and Luna
  profiles with explicit model, reasoning, sandbox, and delegation policies.
- **Native workflow semantics:** all workflows use `$skill-name` invocation,
  phase-gated collaboration, and explicit approval boundaries.
- **Hardened lifecycle hooks:** 10 Python-based Codex hook actions provide
  session continuity, gap detection, asset/skill validation, command guardrails,
  and atomic repository I/O without the former shell runtime.
- **Transactional engine packs:** Godot, Unity, and Unreal activation installs
  exactly five managed specialists with collision checks, recorded hashes,
  rollback, recovery, and post-apply validation.
- **Codex-specific verification:** the behavioral testing framework and
  state-aware repository validator check agents, skills, hooks, instructions,
  engine state, documentation, and migration invariants.
- **Lean cross-platform runtime:** studio automation requires Git, Codex, and
  Python 3.11+, with no Node.js, shell-script, or `jq` runtime dependency.
- **Migration path:** `UPGRADING.md` and the retained coverage evidence support
  projects moving from the upstream template without an operational
  compatibility bridge.

## What is included

| Surface | Count | Purpose |
| --- | ---: | --- |
| Studio roles | 49 | Plugin-local coordination roles and three inactive engine packs |
| Skills | 73 | Immediately available design, architecture, delivery, QA, operations, and release workflows |
| Plugin resources | — | Templates, guidance, and selected-engine references read on demand |

The balanced model policy routes 3 Sol roles (`gpt-5.6`), 44 Terra roles
(`gpt-5.6-terra`), and 2 Luna roles (`gpt-5.6-luna`). Only the selected
engine pack is activated; the other two stay in `.codex/agent-packs/`.

## How collaboration works

The default is **phase-gated autonomy**. You approve game concepts, material
design and architecture decisions, scope changes, destructive actions, commits,
and publication. Once you approve an implementation story or phase, Codex may
edit the agreed files, add tests, diagnose failures, and iterate inside that
boundary without asking before every file.

The persistent setting lives only in `.codex/studio.toml`. Its default
`phase-gated` mode uses lean optional-review depth: optional per-skill director
consultations may be skipped, but phase-transition and other mandatory director
gates still run.

Skills use `$name` invocation syntax. Common entry points include `$brainstorm`,
`$map-systems`, `$design-system`, `$prototype`, `$create-architecture`,
`$create-epics`, `$create-stories`, `$dev-story`, `$story-done`, `$qa-plan`, and
`$gate-check`. `$help` reads project state and recommends the next workflow.

## Repository layout

```text
plugins/codex-game-studios/      installable plugin package
plugins/.../assets/studio/       bundled skills and shared studio resources
docs/                            repository documentation and release design
tests/                           plugin and studio contract tests
```

## Validate the studio

The validator uses only Python's standard library:

```bash
python3 -m unittest discover -s tests/studio -v
python3 -m tools.codex_studio.validate --root . --phase final
```

The final gate checks exact state-aware agent, skill, engine-pack, instruction,
document, hook, and reference inventories. See [.codex/docs/quick-start.md](.codex/docs/quick-start.md)
for the guided flow and [docs/WORKFLOW-GUIDE.md](docs/WORKFLOW-GUIDE.md) for the
full lifecycle.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing skills, agents, hooks,
or engine packs. Report security issues using [SECURITY.md](SECURITY.md). If you
are migrating a project created from the source template, follow
[UPGRADING.md](UPGRADING.md).

## License

Codex Game Studios is distributed under the [MIT License](LICENSE). The
original `Copyright (c) 2026 Donchitos` and MIT permission notice are retained
for the upstream work, and this Codex-native adaptation is distributed under
the same license.
