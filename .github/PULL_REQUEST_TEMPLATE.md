## Summary

Brief description of what this PR does.

## Type of Change

- [ ] New agent
- [ ] New skill
- [ ] New hook or rule
- [ ] Bug fix
- [ ] Documentation improvement
- [ ] Other:

## Changes

-
-
-

## Checklist

- [ ] I've tested this in a Codex session
- [ ] New agents use valid `.codex/agents/*.toml` profiles and phase-gated instructions
- [ ] New skills use `.agents/skills/<name>/SKILL.md` with `name`, `description`, and an accurate trigger description
- [ ] Reference docs are updated (agent-roster, skills-reference, hooks-reference, rules-reference)
- [ ] Hook changes use `.codex/hooks/hook_runner.py`, have tests, and preserve fail-open quality checks
- [ ] Durable repository guidance is in `AGENTS.md`; runtime settings are in `.codex/studio.toml`
- [ ] No hardcoded paths or platform-specific assumptions
- [ ] Material scope, commits, pushes, releases, and destructive actions remain explicitly gated
