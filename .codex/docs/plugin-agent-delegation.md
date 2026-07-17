# Plugin Agent Delegation

Use this protocol whenever a skill assigns work to a named studio role. Relative
resource paths resolve from the current skill directory and therefore select the
plugin-local studio bundle when the skill is installed from the plugin.

## Role routing order

Apply these routes in order and stop at the first available route:

1. If the collaboration API exposes the named role, delegate with that role.
2. Otherwise read `../../../.codex/agents/<role>.toml`, pass its complete role
   contract to a default delegated agent, and preserve supported model settings.
   For an engine-pack role, read
   `../../../.codex/agent-packs/<engine>/<role>.toml` instead. The complete role
   contract comprises `name`, `description`, and `developer_instructions`.
   Preserve `model` and `model_reasoning_effort` when the current collaboration
   API exposes and supports those settings. Never silently substitute a model;
   follow the unavailable-model rule in
   `../../../.codex/docs/coordination-rules.md`.
3. If delegation is unavailable, execute the bounded role checklist in the
   current agent and label the evidence `single-agent fallback`. Use the same
   role contract, scope, acceptance criteria, and evidence requirements. Do not
   represent this evidence as an independent review.

Do not skip an available earlier route. A default delegated agent carrying the
complete plugin-local role contract is the only substitute for a native named
role.

## Ownership and synthesis

- Delegate only a concrete, bounded task to a direct child. State its objective,
  owned files or artifact, complete inputs, acceptance criteria, required
  evidence, and prohibited actions.
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
engine-pack TOML only from the plugin-local paths above. Project-owned
`.codex/studio.toml` and `.codex/docs/technical-preferences.md` may select the
engine or routing policy, but they do not supply or override role contracts.
