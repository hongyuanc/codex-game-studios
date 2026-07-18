# Agent Coordination Rules

1. **Vertical Delegation**: Leadership agents delegate to department leads, who
   delegate to specialists. Never skip a tier for complex decisions.
2. **Horizontal Consultation**: Agents at the same tier may consult each other
   but must not make binding decisions outside their domain.
3. **Conflict Resolution**: When two agents disagree, escalate to the shared
   parent. If no shared parent, escalate to `creative-director` for design
   conflicts or `technical-director` for technical conflicts.
4. **Change Propagation**: When a design change affects multiple domains, the
   `producer` agent coordinates the propagation.
5. **No Unilateral Cross-Domain Changes**: An agent must never modify files
   outside its designated directories without explicit delegation.

## Model Tier Assignment

Agent profiles declare their model and reasoning level in TOML. Skills remain
portable workflow instructions and do not select models in frontmatter.

| Tier | Model | When to use |
|------|-------|-------------|
| **Sol** | `gpt-5.6` | Creative direction, technical direction, production arbitration, and high-stakes cross-system decisions |
| **Terra** | `gpt-5.6-terra` | Design, implementation, review, engine specialization, and most production work |
| **Luna** | `gpt-5.6-luna` | Bounded routine QA and community operations with low or medium reasoning |

Sol is reserved for `creative-director`, `technical-director`, and `producer`.
Luna is reserved for `qa-tester` and `community-manager`. All other profiles use
Terra. If a configured model is unavailable, report it and ask before selecting a
supported fallback; never silently change the tier.

## Phase-Gated Autonomy

The user approves concepts, material design and architecture decisions, scope and
milestone changes, destructive actions, and external publication. Before an
implementation story begins, present its acceptance criteria and intended
changeset. Once that boundary is approved, Codex may use `apply_patch`, add tests,
diagnose failures, and iterate within it without asking before every file edit.

Pause when the work discovers material scope expansion, an unresolved design
ambiguity, an accepted-ADR conflict, or a required file outside the approved
changeset. Commits, pushes, releases, and destructive actions remain separately
gated.

## Codex Delegation

Ordinary skills remain single-agent unless delegation materially helps. Team and
cross-domain skills resolve every role through
`../../../.codex/docs/plugin-agent-delegation.md`. This shared protocol selects a
native named role, a default delegated agent carrying the complete plugin-local
role contract, or a labeled single-agent fallback in that order. It does not
depend on repository-local agent or agent-pack trees. The parent owns synthesis,
conflict resolution, and the final recommendation.

- Delegate only concrete, bounded subtasks with complete context.
- Run independent subtasks in parallel when they do not share mutable files.
- Keep dependent work sequential.
- Subagents return evidence and must not broaden scope, commit, push, or publish.
- `agents.max_depth = 1` prevents recursive delegation.

## Parallel Task Protocol

When an orchestration skill spawns multiple independent agents:

1. Dispatch all independent custom agents before waiting for any result
2. Collect all results before proceeding to dependent phases
3. If any agent is BLOCKED, surface it immediately — do not silently skip
4. Always produce a partial report if some agents complete and others block
