# Codex Studio Testing Framework

Behavioral QA for the 73 Codex Game Studios skills and 49 Codex custom-agent
profiles. This framework tests the studio runtime itself, not games built with it.

The runtime remains authoritative:

- Skills: `.agents/skills/<name>/SKILL.md`
- Core agents: `.codex/agents/<name>.toml`
- Engine agents: `.codex/agent-packs/<engine>/<name>.toml`
- Inventory and spec lookup: `catalog.yaml`

## Native runtime contract

Agent specs verify the five required TOML keys: `name`, `description`, `model`,
`model_reasoning_effort`, and `developer_instructions`. Model aliases are:

- Sol (`gpt-5.6`) for studio-wide synthesis and high-stakes leadership.
- Terra (`gpt-5.6-terra`) for most discipline and implementation work.
- Luna (`gpt-5.6-luna`) for fast, bounded QA or community work.

The matching TOML profile is the source of truth for each spec. Engine profiles
stay in their engine pack; no Markdown agent profile is valid.

Skill specs verify the exact runtime `name` and trigger `description`, native
`$skill-name` invocation, and five behavioral cases. When a structured choice is
useful, `request_user_input` uses 1–3 questions with 2–3 options per question.
The workflow asks one decision per turn and sequences unrelated decisions.

Delegation uses direct child custom agents only; the maximum delegation depth is 1.
Children return scoped findings and evidence; the parent agent synthesizes the
result, owns user interaction, and enforces the approved changeset boundary.

## Layout

```text
Codex Studio Testing Framework/
├── AGENTS.md
├── README.md
├── catalog.yaml
├── quality-rubric.md
├── agents/                  # 49 five-case agent specs
├── skills/                  # 73 five-case skill specs
└── templates/               # native spec templates
```

## Test workflows

Use the native `$skill-test` skill:

```text
$skill-test static <name|all>
$skill-test spec <name>
$skill-test category <name|all>
$skill-test audit
```

- `static` validates runtime skill structure through
  `tools/codex_studio/validate.py` plus the seven documented checks.
- `spec` evaluates all five cases and protocol assertions for one skill.
- `category` evaluates the matching section of `quality-rubric.md`.
- `audit` compares the catalog with exactly 73 runtime skills and 49 runtime
  agents, including all three engine packs.

Validation is read-only. After presenting a report, `$skill-test` may optionally
offer one complete proposed changeset containing a result file and/or the related
catalog metadata update. Nothing is written until that whole changeset is
approved; new paths or scope require fresh approval.

Use `$skill-improve <name>` for the test, diagnose, edit, and retest loop.

## Catalog rules

`catalog.yaml` is the authoritative mapping from runtime names to behavioral
specs. Catalog entries track category, priority, and optional historical result
metadata. A valid audit requires exact set equality with the runtime inventories,
not minimum or approximate counts.

When adding a spec:

1. Copy the relevant native template.
2. Point it at the real runtime TOML or `SKILL.md` file.
3. Preserve five cases and the runtime interaction/delegation contract.
4. Add the exact spec path to `catalog.yaml`.
5. Run `$skill-test spec <name>` and `$skill-test audit`.

This directory is self-contained. Removing it does not remove or disable the
studio's runtime skills, agents, hooks, or engine packs.
