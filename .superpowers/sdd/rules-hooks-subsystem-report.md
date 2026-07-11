# Rules and Hooks Subsystem Report

## Result

The runtime uses 11 path-scoped Codex instruction boundaries, a native
project-local hook configuration, and one portable standard-library Python hook
runner. The tracked legacy `.claude/hooks/*.sh` inventory and
`.claude/settings.json` are removed. Unrelated `.claude` migration sources remain
outside this subsystem by design.

## Test-First Evidence

Initial implementation:

- Instruction RED failed on all 11 absent boundaries, then passed 2 tests.
- Native runner RED failed on the absent Python runner, then the initial parser
  contract passed 3 tests.
- Initial behavior/configuration expansion went from 17 expected failures to
  19 focused tests passing and 93 studio tests passing.

Critical/Important review remediation:

- Added regressions before runtime changes for structured shell parsing, Git
  global options and refspecs, inert/dry-run commands, commit inspection
  failures, symlink escape and disclosure, actual legacy inventory removal,
  shader path scope, patch move destinations, validator parity/shape, native
  fixture completeness, and source-aware gap detection.
- RED: the 32-test focused run produced 41 expected assertion failures and five
  expected missing-output errors across those categories.
- GREEN: the hardened focused suite passed 34 tests, and the complete studio
  suite passed 108 tests. Additional red-green cases cover brace/conditional
  command boundaries, quoted text that resembles a heredoc marker, symlinked
  directory enumeration, and traversal that normalizes back inside the root.

## Nested Instruction Coverage

| Legacy responsibility | Codex boundary |
| --- | --- |
| Gameplay code | `src/gameplay/AGENTS.md` |
| Core engine code | `src/core/AGENTS.md` |
| AI code | `src/ai/AGENTS.md` |
| Network code | `src/networking/AGENTS.md` |
| UI code | `src/ui/AGENTS.md` |
| Shader code | `assets/shaders/AGENTS.md` |
| Data files | `assets/data/AGENTS.md` |
| Design documents | `design/gdd/AGENTS.md` |
| Narrative | `design/narrative/AGENTS.md` |
| Tests | `tests/AGENTS.md` |
| Prototypes | `prototypes/AGENTS.md` |

The shader boundary now matches the source rule's actual `assets/shaders/`
scope; the incorrect `src/shaders/AGENTS.md` boundary is removed. Every boundary
retains Applies To, Required Practices, Forbidden Practices, and Verification.

## Event, Action, and Fixture Matrix

| Native event | Matcher | Runner action(s) | Fixture |
| --- | --- | --- | --- |
| `SessionStart` | `startup|resume|clear|compact` | `session-start`, `detect-gaps` | `session-start.json` |
| `PreToolUse` | `Bash` | `validate-command` | `pre-tool-bash.json` |
| `PostToolUse` | `Edit|Write|apply_patch` | `validate-assets`, `validate-skill-change` | `post-tool-patch.json` |
| `PreCompact` | `auto|manual` | `pre-compact` | `pre-compact.json` |
| `PostCompact` | `auto|manual` | `post-compact` | `post-compact.json` |
| `SubagentStart` | all | `subagent-start` | `subagent-start.json` |
| `SubagentStop` | all | `subagent-stop` | `subagent-stop.json` |
| `Stop` | all | `session-stop` | `stop.json` |

The validator enforces exact action inventory and event mapping, ACTIONS ↔
HANDLERS ↔ configuration parity, duplicate/missing/unknown actions, exact
repository-root runner invocation, matching POSIX/Windows actions, handler and
group shape, matcher type/regex/semantics, positive integer timeouts, supported
events/types, portable paths, and Windows overrides. Fixtures now include common
native transcript, model, permission, and event fields plus event-specific tool
response, agent transcript/result, compaction, and stop fields.

## Command Safety

The Bash guard uses `shlex` tokenization plus explicit command boundaries,
quote/comment handling, heredoc-body exclusion, shell control prefixes, line
continuation normalization, and structured Git global-option parsing. It:

- Blocks `reset --hard`, forced `clean`, force-push flags, and leading-`+`
  refspecs with exit 2.
- Recognizes real Git invocations after `-C`, `-c`, `--git-dir`, `--work-tree`,
  other supported global options, quoted tokens, and shell boundaries.
- Does not block inert echo/comment/quoted/heredoc text or dry-run clean/push.
- Runs staged validation for every real `git commit` form.
- Blocks a real commit when Git/index/subprocess/decode inspection cannot
  complete; invalid staged JSON also blocks.
- Warns for protected destinations including simple branches,
  `HEAD:main`, and `refs/heads/*` destination refspecs.

Commit quality findings and protected-branch pushes remain advisory. Asset and
skill findings, gap detection, and lifecycle context remain fail-open.

## Repository I/O Safety

All runner-controlled reads and writes use lexical containment plus component
`lstat` checks. Traversal and symlinked file or directory components are
rejected before access. Unsafe advisory I/O is skipped with a safe warning and
never blocks; tests prove external state files, log directories, asset files,
and enumerated directories are neither disclosed nor modified. Session/audit
writes remain limited to `production/session-state/` and
`production/session-logs/`.

`changed_paths()` recognizes Add, Update, Delete, and `*** Move to:` paths so
post-edit asset and skill checks inspect both sides of moves. Gap detection
counts only actual configured source suffixes, ignores instruction-only
directories, and treats both `src/core/` and `src/engine/` as engine-system
alternatives.

## Removed Legacy Runtime

Removed the 12 tracked scripts formerly under `.claude/hooks/`:
`detect-gaps.sh`, `log-agent-stop.sh`, `log-agent.sh`, `notify.sh`,
`post-compact.sh`, `pre-compact.sh`, `session-start.sh`, `session-stop.sh`,
`validate-assets.sh`, `validate-commit.sh`, `validate-push.sh`, and
`validate-skill-change.sh`. Removed `.claude/settings.json`, which registered
those handlers and legacy permissions/status-line behavior.

## Verification Commands

```text
python3 -m unittest tests.studio.test_hooks tests.studio.test_instruction_coverage -v
python3 -m unittest discover -s tests/studio -v
python3 -m json.tool .codex/hooks.json
python3 -m py_compile .codex/hooks/hook_runner.py tools/codex_studio/validate.py
git diff --check
git diff --cached --check
rg -n '/Users/|/home/|Claude Code|\.claude/' .codex/hooks.json .codex/hooks assets/shaders src tests/AGENTS.md prototypes/AGENTS.md
find .claude/hooks .codex/hooks -maxdepth 1 -type f -name '*.sh' -print
git ls-files .claude/hooks .claude/settings.json
```

Expected final evidence: all focused and studio tests pass; JSON/Python and
whitespace checks pass; runtime forbidden scans return no matches; neither hook
tree contains shell scripts; the tracked legacy hook/settings inventory is
empty.

## Concerns

None blocking. Public hook/setup documentation still describes the legacy shell
inventory and remains intentionally assigned to the approved documentation and
cleanup subsystem.
