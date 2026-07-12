# Codex Studio Testing Framework Instructions

This directory is the behavioral QA layer for Codex Game Studios. Runtime files
outside this directory are authoritative; specs must describe and test them, not
invent a parallel agent or skill format.

## Required inventory

- Exactly 73 skills at `.agents/skills/<name>/SKILL.md`.
- Exactly 49 TOML custom-agent profiles across `.codex/agents/` and
  `.codex/agent-packs/{godot,unity,unreal}/`.
- One catalog entry and one five-case spec for every runtime item.

## Agent spec rules

Each agent spec identifies the actual `.toml` path and verifies the exact keys
`name`, `description`, `model`, `model_reasoning_effort`, and
`developer_instructions`. It records the runtime route exactly:

- Sol (`gpt-5.6`)
- Terra (`gpt-5.6-terra`)
- Luna (`gpt-5.6-luna`)

Do not infer a route from organizational tier. Read it from the profile.

## Skill spec rules

Each skill spec identifies `.agents/skills/<name>/SKILL.md`, copies its exact
`name` and trigger `description`, and uses native `$name` invocation. YAML
frontmatter requires only `name` and `description`; execution arguments and
permissions are runtime/workflow concerns.

Every spec retains five cases: happy path, blocked/failure path, mode or boundary
variant, edge case, and delegation/gate behavior. Preserve useful domain fixtures
and assertions during migrations.

## Interaction and delegation

For structured decisions, `request_user_input` accepts 1–3 questions and each
question accepts 2–3 options. Ask one decision per turn. Multiple independent
decisions are sequential turns, not one oversized prompt.

Custom-agent work is a bounded direct-child delegation. The maximum delegation
depth is 1. Child agents return scoped evidence and never own user interaction,
commits, publication, or scope expansion. The parent agent synthesizes the final
answer and applies the approved changeset boundary.

## Validation and writes

Validation is read-only. Optional test results and catalog metadata may be
offered as one complete proposed changeset after findings are shown. List every
path and material edit, obtain approval for the whole set, and request fresh
approval for any expansion.

Use `catalog.yaml` for spec paths, `quality-rubric.md` for category criteria, and
the templates in `templates/` for new specs.
