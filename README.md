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

1. Clone this repository and open the clone in the Codex app.
2. Open **Plugins**, select the **Codex Game Studios** repository marketplace,
   and install **Codex Game Studios**.
3. Start a new Codex task in the Git game repository where you want the studio.
   A new task is required so Codex loads the newly installed plugin.
4. Run:

```text
$codex-game-studios install
```

You can close the Codex Game Studios source repository after installing the
plugin. The installed copy is available to other local repositories.

### Codex CLI

First install the [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) if
`codex --version` is not available. Then add this repository's marketplace and
install the plugin from the published `main` branch:

```bash
codex plugin marketplace add hongyuanc/codex-game-studios --ref main
codex plugin add codex-game-studios@codex-game-studios
```

Start a new Codex session in the target Git repository, then run
`$codex-game-studios install`.

The retained manager presents a complete, digest-bound plan and changes the
repository only after you explicitly approve that exact plan. Project
operations use the verified embedded payload and make no network requests.
After installation, invoke `$start`; use `$setup-engine` when you are ready to
choose Godot, Unity, or Unreal. The selected engine itself must be installed
separately to run or export a game.

The same retained manager remains available for repository lifecycle work:

```text
$codex-game-studios update
$codex-game-studios verify
$codex-game-studios repair
$codex-game-studios uninstall
```

`verify` is read-only. Mutating operations retain plan, approval, ownership,
recovery, and validation safeguards. Existing game content and unrelated Codex
configuration stay project-owned.

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

- **Native Codex surfaces:** durable `AGENTS.md` guidance, 73 discoverable
  skills in `.agents/skills/`, TOML agent profiles in `.codex/agents/`, and
  repository-owned Codex configuration.
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

## Use the source checkout directly

1. Clone this repository.
2. Open the project in Codex and trust the repository configuration and hooks after review.
3. Invoke `$start`.
4. Choose Godot, Unity, or Unreal when `$setup-engine` runs.

Review [AGENTS.md](AGENTS.md), [.codex/config.toml](.codex/config.toml), and
[.codex/hooks.json](.codex/hooks.json) before trusting the project. Hooks are
best-effort defense-in-depth guardrails with incomplete interception. Codex
permissions, explicit approvals, and durable instructions remain the
authorization boundary.

## What is included

| Surface | Count | Purpose |
| --- | ---: | --- |
| Custom agents | 49 | 34 core roles plus three inactive five-role engine packs |
| Skills | 73 | Design, architecture, delivery, QA, operations, and release workflows |
| Nested instructions | 11 | Directory-scoped coding and content rules |
| Document templates | 40 | GDD, architecture, UX, production, QA, and release artifacts |

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
AGENTS.md                         durable project instructions
.agents/skills/                   73 Codex skills
.codex/agents/                   34 core profiles, plus 5 managed profiles after engine setup
.codex/agent-packs/              inactive Godot, Unity, and Unreal packs
.codex/hooks.json                reviewed native hook registration
.codex/hooks/                    native Python hook runner and modules
.codex/docs/                     studio references and 40 templates
Codex Studio Testing Framework/  agent and skill behavioral specifications
design/                          game design and narrative
docs/                            architecture and project documentation
production/                      plans, stories, QA, and release evidence
src/                             game source
tests/                           game and studio tests
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
