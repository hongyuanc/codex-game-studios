# Plugin Agent Delegation

Use this protocol whenever a skill assigns work to a named studio role. The
plugin bundle is the sole source of role contracts; a project selects an active
engine pack but cannot supply or override a role.

## Role resolution

Before the default route, resolve the requested role with:

```text
python3 ../../../tools/codex_studio/agent_delegation.py resolve --project-root <project-root> --role <role>
```

Use only the returned complete role contract: `name`, `description`,
`developer_instructions`, `model`, and `model_reasoning_effort`. The resolver
accepts safe role slugs, checks declared core and selected-pack membership, and
reads a regular plugin-local TOML without following symlinks or reparse points.
Missing, malformed, mismatched, ambiguous, unknown, inactive-pack, or unsafe
contracts are errors. Never interpolate a role into a path or read a
project-local role contract directly.

## Closed routing order

Apply these routes in order:

1. If the collaboration API exposes the named role, delegate with that role.
2. Otherwise run the plugin-local resolver and launch a default delegated agent
   with the returned contract and the bounded direct-child task.
3. If delegation is unavailable, execute the bounded role checklist in the
   current agent and label the evidence `single-agent fallback`.

The operational states are closed:

| Current route | Result | Required action |
| --- | --- | --- |
| Native named role | success | Record a completed route result; must not fall through. |
| Native named role | child returns `BLOCKED` | Record a completed route result as blocked; must not fall through. |
| Native named role | native named role absent | Attempt the default delegated agent route. |
| Native named role | native invocation reports capability unavailable | Attempt the default delegated agent route. |
| Default delegated agent | success | Record a completed route result; must not fall through. |
| Default delegated agent | child returns `BLOCKED` | Record a completed route result as blocked; must not fall through. |
| Default delegated agent | default delegated agent absent | Use the `single-agent fallback`. |
| Default delegated agent | default launch reports capability unavailable | Use the `single-agent fallback`. |

Do not infer any other transition. Do not skip an available earlier route. A
default delegated agent carrying the complete plugin-local role contract is the
only substitute for a native named role.

## Default-agent parameter contract

Map supported settings exactly:

- TOML `model` -> default-agent `model`
- TOML `model_reasoning_effort` -> default-agent `reasoning_effort`
- set `fork_turns = "none"` whenever model or reasoning-effort overrides are
  supplied

The default-agent message must include the complete role contract and the
bounded direct-child task: objective, owned paths, inputs, acceptance criteria,
required evidence, and prohibited actions. It must also prohibit further
delegation, scope expansion, commits, pushes, releases, and publication.

If the configured model is unavailable, or its configured reasoning effort is
unavailable, the route is `approval-required`. Stop with a blocked result and
request explicit approval for any substitution; do not silently change the
model and do not enter the single-agent fallback. Retry the default route only
after approval provides a supported setting.

## Ownership and synthesis

- Delegate only a concrete, bounded task to a direct child.
- A direct child must not delegate again, broaden scope, commit, push, release,
  publish, or modify files outside its ownership.
- The parent retains parent synthesis: collect all child evidence, resolve
  conflicts, verify material claims, and produce the final recommendation or
  artifact.
- Keep independent direct-child tasks parallel only when they do not share
  mutable files. Keep dependent tasks sequential and surface blocked evidence.

## Portable resource boundary

Do not copy role TOML into a project. Do not require a repository-local
`.codex/agents/` or a repository-local `.codex/agent-packs/` tree. Read role and
engine-pack TOML only through the plugin-local resolver. Project-owned
`.codex/studio.toml` and `.codex/docs/technical-preferences.md` may select the
engine or routing policy, but they do not supply or override role contracts.
