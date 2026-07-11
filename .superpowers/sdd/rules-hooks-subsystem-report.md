# Rules and Hooks Subsystem Report

## Result

Implemented the complete Rules and Hooks subsystem as a single reviewed unit.
The runtime now uses nested Codex instructions plus one portable Python hook
runner and native project-local hook configuration. No legacy shell hook remains
below `.codex/hooks/`.

## Test-First Evidence

- Instruction RED: `python3 -m unittest tests.studio.test_instruction_coverage -v`
  failed because all 11 nested instruction boundaries were absent.
- Instruction GREEN: the same command passed 2 tests after the rule-intent
  migration.
- Parser RED: `python3 -m unittest tests.studio.test_hooks -v` failed because
  `.codex/hooks/hook_runner.py` did not exist.
- Parser GREEN: the initial command/path/destructive-operation contract passed
  3 tests.
- Behavior RED: the expanded 17-test suite failed on the intentionally absent
  lifecycle handlers, safe-path filter, portable config, supported output
  encoding, staged checks, and hook validator.
- Behavior GREEN: the expanded suite passed after implementing those contracts.
- Final focused suite: 19 tests passed.
- Final studio suite: 93 tests passed.

## Nested Instruction Coverage

| Legacy responsibility | Codex boundary |
| --- | --- |
| Gameplay code | `src/gameplay/AGENTS.md` |
| Core engine code | `src/core/AGENTS.md` |
| AI code | `src/ai/AGENTS.md` |
| Network code | `src/networking/AGENTS.md` |
| UI code | `src/ui/AGENTS.md` |
| Shader code | `src/shaders/AGENTS.md` |
| Data files | `assets/data/AGENTS.md` |
| Design documents | `design/gdd/AGENTS.md` |
| Narrative | `design/narrative/AGENTS.md` |
| Tests | `tests/AGENTS.md` |
| Prototypes | `prototypes/AGENTS.md` |

Every boundary defines Applies To, Required Practices, Forbidden Practices, and
Verification sections and preserves the material requirements from its matching
legacy rule.

## Event and Action Matrix

| Native event | Matcher | Runner action(s) |
| --- | --- | --- |
| `SessionStart` | `startup|resume|clear|compact` | `session-start`, `detect-gaps` |
| `PreToolUse` | `Bash` | `validate-command` |
| `PostToolUse` | `Edit|Write|apply_patch` | `validate-assets`, `validate-skill-change` |
| `PreCompact` | `auto|manual` | `pre-compact` |
| `PostCompact` | `auto|manual` | `post-compact` |
| `SubagentStart` | all | `subagent-start` |
| `SubagentStop` | all | `subagent-stop` |
| `Stop` | all | `session-stop` |

The configuration has exact 10-action parity with the runner dispatch table.
Each handler has a repository-root POSIX command, a Windows PowerShell override,
and no user-specific path.

## Blocking and Advisory Cases

Exit 2 blocks deterministic destructive Git commands (`reset --hard`, force
push forms, and forced `clean`) and invalid staged JSON data during a commit.
Commit quality findings, protected-branch pushes, post-edit asset findings,
skill-change reminders, gap detection, and lifecycle context remain advisory and
exit 0. Malformed payloads fail open; unknown actions emit supported
`systemMessage` JSON and fail open.

Session orientation is plain text. Other model-visible context is encoded as
JSON with `systemMessage`. File paths extracted from `Edit`, `Write`, and
`apply_patch` are normalized and constrained to the repository before reads or
writes. Session and audit artifacts are limited to
`production/session-state/` and `production/session-logs/`.

## Removed Legacy Scripts

Replaced and removed: `detect-gaps.sh`, `log-agent-stop.sh`, `log-agent.sh`,
`notify.sh`, `post-compact.sh`, `pre-compact.sh`, `session-start.sh`,
`session-stop.sh`, `validate-assets.sh`, `validate-commit.sh`,
`validate-push.sh`, and `validate-skill-change.sh`. Native Codex notifications
supersede the platform-specific notification script.

## Verification Commands

```text
python3 -m unittest tests.studio.test_hooks tests.studio.test_instruction_coverage -v
python3 -m unittest discover -s tests/studio -v
python3 -m json.tool .codex/hooks.json
python3 -m py_compile .codex/hooks/hook_runner.py tools/codex_studio/validate.py
git diff --check
rg -n '/Users/|/home/|Claude Code|\.claude/' .codex/hooks.json .codex/hooks src assets/data design tests/AGENTS.md prototypes/AGENTS.md
find .codex/hooks -maxdepth 1 -type f -name '*.sh' -print
```

Results: all tests and syntax checks passed; `git diff --check` was clean; both
forbidden scans and the legacy-shell listing returned no matches/files.

## Concerns

None blocking. Public hook/setup documentation still describes the legacy shell
inventory and is intentionally outside this subsystem commit; the approved
documentation/cleanup subsystem owns that update.
