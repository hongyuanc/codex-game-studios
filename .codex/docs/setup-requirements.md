# Setup Requirements

Codex Game Studios uses Git, Codex, and Python 3. The runtime has no JavaScript,
shell-script, or external JSON-parser dependency.

## Required tools

| Tool | Purpose | Verification |
| --- | --- | --- |
| Git | Version control and repository discovery | `git --version` |
| Codex | Skills, custom agents, and phase-gated orchestration | `codex --version` |
| Python 3.11+ | 10 hook actions, tests, and repository validation | `python3 --version` |

On Windows, `py -3 --version` may be used instead. Hook registrations in
`.codex/hooks.json` provide Windows commands as well as macOS/Linux commands.

## Runtime layout

- `.codex/config.toml` configures Codex features and agent concurrency.
- `.codex/studio.toml` selects the engine pack, language, review mode, and model policy.
- `.codex/hooks.json` maps Codex events to Python commands.
- `.codex/hooks/hook_runner.py` implements all 10 hook actions.
- `.agents/skills/` contains the 73 discoverable studio skills.
- `.codex/agents/` and `.codex/agent-packs/` contain the 49 TOML profiles.

## Verify the installation

From the repository root:

```text
git --version
codex --version
python3 --version
python3 -m unittest discover -s tests/studio -v
python3 -m tools.codex_studio.validate --root . --phase final
```

If Python is unavailable, Codex can still open the repository, but the hook
runner and validation gates cannot operate. Install Python before relying on
the studio safety contract.

## Trust and review

Review `AGENTS.md`, `.codex/config.toml`, `.codex/studio.toml`,
`.codex/hooks.json`, and `.codex/hooks/hook_runner.py` before trusting a fork.
Hook actions should use repository-relative paths, avoid network access, and
fail open for optional quality checks while blocking clear safety violations.
