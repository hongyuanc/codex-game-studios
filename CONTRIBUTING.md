# Contributing to Codex Game Studios

Codex Game Studios is a Codex-native coordination framework for indie game
development. Contributions are welcome when they fix a defect, fill a real
workflow gap, improve an agent or hook, or correct documentation.

Game-specific GDDs, assets, ADRs, and production records belong in the game
repository built from this template, not in the framework repository.

## Native component contracts

### Skills

- Put each skill at `.agents/skills/<name>/SKILL.md`.
- Frontmatter must provide `name` and `description`. The description is the
  trigger contract: state what user intent should activate the skill and what
  the skill produces.
- Document invocations as `$skill-name`, never as path-like commands.
- Keep phase-gated boundaries explicit. A skill may work autonomously inside an
approved story or phase, but must pause on material design, architecture, or
scope decisions.
- Treat `.codex/studio.toml` as the sole persistent review-mode authority.
  `phase-gated` means lean optional-review depth; mandatory director gates still
  run.

### Custom agents

- Define core profiles in `.codex/agents/*.toml`.
- Define engine specialists in `.codex/agent-packs/<engine>/*.toml`; only the
  pack selected in `.codex/studio.toml` may be active.
- Include a clear `description`, bounded `developer_instructions`, the intended
  Sol/Terra/Luna GPT model, reasoning effort, and sandbox policy.
- Do not cross a profile's documented ownership boundary without delegation.

### Hooks

- Register hook events in `.codex/hooks.json` and implement actions in
  `.codex/hooks/hook_runner.py`.
- Hook logic must be Python 3, path-safe, covered by tests, and portable across
  Windows, macOS, and Linux.
- Quality checks should fail open when optional project data is unavailable.
  Clear safety violations may block with a specific remediation message.
- Never add undisclosed network access, secret collection, or user-specific
  absolute paths.

### Durable guidance and configuration

- Put repository instructions in `AGENTS.md` or an appropriately scoped nested
  `AGENTS.md`.
- Put runtime settings in `.codex/config.toml` and `.codex/studio.toml`.
- Update the matching `.codex/docs/` reference when changing a skill, profile,
  engine pack, hook, or coordination rule.

## Phase-gated collaboration

The user approves concepts, material design and architecture decisions, scope
changes, and the bounded implementation changeset. After that preflight, Codex
may edit the agreed files, add tests, diagnose failures, and iterate without a
separate confirmation for each file.

Pause when work discovers material scope expansion, unresolved ambiguity, an
accepted-ADR conflict, or a necessary file outside the approved boundary.
Commits, pushes, releases, destructive operations, and external publication
always require explicit user authorization.

## Testing changes

Use test-driven development for behavior changes: add a focused failing test,
confirm the expected failure, make the smallest implementation change, then run
the focused and full suites.

```bash
python3 -m unittest discover -s tests/studio -v
python3 -m tools.codex_studio.validate --root . --phase final
```

For a skill, also invoke its `$skill-name` flow with an appropriate fixture. For
a hook, exercise the relevant `hook_runner.py` action with representative Codex
JSON. Summarize the evidence in the pull request.

## Commit and review conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add $retrospective workflow
fix: reject an unsafe Git command in hook runner
docs: update $qa-plan reference
```

Types include `feat`, `fix`, `docs`, `chore`, `refactor`, and `test`. CODEOWNERS
assigns the maintainer to sensitive runtime surfaces; allow time for review.
