# Codex Game Studios

Build an indie game with a coordinated Codex studio: **49 agents**, **73 skills**,
one user-controlled production workflow.

Codex Game Studios turns a repository into a structured game-development team.
Directors protect product and technical direction, department leads coordinate
work, and specialists implement and verify the game. Godot 4, Unity, and Unreal
Engine 5 are supported through mutually exclusive engine packs.

## Getting started

1. Clone or use this repository as a template.
2. Open the project in Codex and trust the repository configuration and hooks after review.
3. Invoke `$start`.
4. Choose Godot, Unity, or Unreal when `$setup-engine` runs.

Review [AGENTS.md](AGENTS.md), [.codex/config.toml](.codex/config.toml), and
[.codex/hooks.json](.codex/hooks.json) before trusting the project. Hooks run
repository-relative Python commands and are part of the security boundary.

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

Skills use `$name` invocation syntax. Common entry points include `$brainstorm`,
`$map-systems`, `$design-system`, `$prototype`, `$create-architecture`,
`$create-epics`, `$create-stories`, `$dev-story`, `$story-done`, `$qa-plan`, and
`$gate-check`. `$help` reads project state and recommends the next workflow.

## Repository layout

```text
AGENTS.md                         durable project instructions
.agents/skills/                   73 Codex skills
.codex/agents/                   34 active core agent profiles
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

The final gate checks exact agent, skill, engine-pack, instruction, document,
hook, and reference inventories. See [.codex/docs/quick-start.md](.codex/docs/quick-start.md)
for the guided flow and [docs/WORKFLOW-GUIDE.md](docs/WORKFLOW-GUIDE.md) for the
full lifecycle.

## Contributing and security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing skills, agents, hooks,
or engine packs. Report security issues using [SECURITY.md](SECURITY.md). If you
are migrating a project created from the source template, follow
[UPGRADING.md](UPGRADING.md).

## License

MIT. See [LICENSE](LICENSE).
