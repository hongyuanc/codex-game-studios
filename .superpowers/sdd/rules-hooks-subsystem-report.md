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

Second hardening review:

- RED: 43 hook tests reproduced 33 assertion failures and seven deterministic
  errors across recursive shell execution, dynamic executable expansion,
  continuation and heredoc normalization, `--` option handling, compound result
  aggregation, push option/refspec parsing, parser recursion, Windows reparse
  metadata, exact platform templates, fixture schemas, and malformed paths.
- GREEN: all 43 hook tests pass. Together with instruction coverage, the focused
  Rules/Hooks suite passes 46 tests; the complete studio suite passes 120 tests.

Final destructive-Git parser review:

- RED: eight focused regression methods reproduced 23 failures and one error
  across unique
  long-option abbreviations, Git aliases, wrapper option operands, quote-aware
  variable expansion, recursion fallback, broad protected pushes, and push
  option values.
- GREEN: all 51 hook tests pass. The cases use temporary Git repositories for
  ordinary, shell, commit, dry-run, chained, looping, inline `-c`, and compact
  `-c` aliases, plus forced parser-failure and deep-recursion paths.

Final ambiguous-execution policy review:

- RED: eight focused methods reproduced 57 assertion failures and one
  missing-advisory error across embedded variable quoting, abbreviated dynamic
  subcommands, wrappers, Windows command forms, help/value parsing, unknown
  aliases, matching refspecs, and the raw/depth fallback.
- GREEN: all 53 hook tests pass. Unknown aliases and git-* extensions now block
  consistently across HOME, `cd`, `env`, `sudo`, `-C`, Git-dir/work-tree, and
  recursion contexts; explicit inline `-c alias.name=value` aliases remain
  expandable when their complete value can be inspected.

Finite ambiguous-policy completion review:

- RED: seven focused methods reproduced 39 policy assertion failures and one
  help-path error across Git global options, dynamic commit/push tails,
  deferred inline aliases, dashed executables, PowerShell relative/UNC paths,
  clustered help flags, the built-in allowlist, and raw fallback behavior.
- GREEN: all 58 hook tests pass. The static allowlist includes the reviewed
  plumbing commands, while dashed git-* extensions and every deferred execution
  path remain intentionally ambiguous.

Direct-classification table completion:

- RED: four focused methods reproduced 25 failures across unresolved dynamic
  subcommands, commit help/value disambiguation, global version terminals, and
  Git's current built-in inventory.
- GREEN: all 59 hook tests pass. When supported, the suite asserts that
  `git --list-cmds=builtins` is a subset of the static allowlist.

Commit option-table completion:

- RED: the focused commit-help matrix reproduced 13 value-consumption failures
  covering template, cleanup, unified, inter-hunk-context, and unique long-option
  abbreviations.
- GREEN: all 59 hook tests pass with separate, compact-short, equals, and unique
  abbreviated commit value forms distinguished from actual terminal help.

Optional commit-operand completion:

- RED: the focused matrix reproduced one attached-value failure and one
  ambiguous-abbreviation help error for `-S` and `--un`.
- GREEN: all 59 hook tests pass. Exact `-S` consumes no following token,
  attached `-S<keyid>` remains one value, and `--un` stays ambiguous between
  unified and untracked-files while a unique unified abbreviation still works.

Clustered signing-option completion:

- RED: the focused commit matrix reproduced the `-qS-h` help/value collision.
- GREEN: all 59 hook tests pass. Valid no-value short flags may precede `S` in
  one cluster, while any preceding value-taking option retains ownership of its
  attached suffix.

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
events/types, portable paths, and Windows overrides. POSIX and PowerShell
templates are anchored full-command contracts: alternate interpreters, extra
arguments/commands, and echo-spoof prefixes are rejected. Fixtures now use exact
event-specific field sets: compact events have `turn_id` but no
`permission_mode`; agent start has `turn_id` without a transcript-result field;
agent stop and stop carry their current result/stop fields.

## Command Safety

The Bash guard deliberately does not emulate arbitrary shell, HOME, user, cwd,
or Git-config environments. It uses recursive `shlex` tokenization plus explicit command
boundaries, quote/comment handling, normalized quoted/escaped heredoc
delimiters, shell control prefixes, POSIX and PowerShell continuation
normalization, simple literal assignment expansion, and structured Git
global-option parsing. It:

- Blocks `reset --hard`, forced `clean`, force-push flags, and leading-`+`
  refspecs with exit 2.
- Recognizes real Git invocations after `-C`, `-c`, `--git-dir`, `--work-tree`,
  other supported global options, quoted tokens, and shell boundaries.
- Maintains an explicit built-in allowlist. Direct known built-ins are analyzed
  precisely; every unknown subcommand, possible configured alias, git-* extension,
  `--config-env=alias.*` execution, or unresolved destructive dynamic form blocks
  with instructions to rerun an explicit direct Git built-in command.
- Supports Git's `-P`/`--no-pager` and `--no-lazy-fetch` global flags, plus
  terminal `-v`/`--version`. Unknown global options fail closed when they
  prevent precise direct analysis.
- Applies Git-compatible unique long-option abbreviation matching. Ambiguous
  prefixes remain unrecognized; abbreviations such as `--har`, `--for`,
  `--mir`, `--force-with-l`, `--force-if-i`, and `--dry-r` are classified.
- Expands only self-contained inline `git -c alias.name=value` overrides when
  their complete ordinary or `!` shell value can be inspected. It never reads
  repository or user alias configuration; configured aliases, loops, depth
  failures, and context-dependent execution fail closed as ambiguous.
- Rejects inline alias values containing deferred POSIX, command-substitution,
  backtick, PowerShell, or percent-environment expansion before interpretation.
- Recursively inspects literal backticks, `$()` substitutions, `bash -c`,
  `sh -c`, `zsh -c`, and `eval`. Unquoted literal variables undergo shell word
  splitting while quoted expansions remain one executable token. Embedded
  double-quoted expansions are resolved or marked dynamic; single-quoted and
  escaped dollar literals remain inert.
- Parses `env`, `sudo`, `command`, `builtin`, and `exec` wrappers with explicit
  option-value tables, including split execution through `env -S` and the
  `exec -a` display-name operand; `command -v`, `-V`, and `--version` are
  inspection-only.
- Parses `time`, `nice`, and `timeout` wrapper operands, recognizes Windows
  basenames with either slash style—including relative and UNC `git.exe`
  paths—and PowerShell's call operator, and removes PowerShell `--%` before
  native Git argument analysis. `builtin git ...` is correctly treated as
  non-executing.
- Recognizes `git` and `git.exe` case-insensitively. Every unresolved dynamic
  Git subcommand fails closed regardless of its arguments. Executable basenames
  matching `git-*` or `git-*.exe` are deliberately ambiguous extensions.
- Does not block inert echo/comment/quoted/heredoc text or dry-run clean/push.
- Treats dry-run/force flags as options only before `--`, skipping option values.
- Treats reset/clean `-h` and `--help` as terminal, and consumes reset
  `--pathspec-from-file` operands so option-looking values do not false-block.
  Short option clusters containing `h` are terminal before `--` for direct
  known subcommands, including commit and push.
- Commit help detection first consumes message, file, reuse/reedit, fixup,
  squash, author, date, template, trailer, and pathspec-file operands, including
  cleanup, unified, and inter-hunk-context operands. Separate, compact, equals,
  and unique abbreviated forms are canonicalized so option-looking values still
  trigger staged validation rather than being mistaken for terminal help.
- Optional commit operands are modeled separately: `-S[<keyid>]` only consumes
  an attached suffix, and `--untracked-files[=<mode>]` participates in the long
  abbreviation namespace without consuming a separate help token.
- Clustered signing syntax recognizes `S` after valid no-value flags: `-qS-h`
  treats `-h` as the key ID, whereas terminal `-qS -h` leaves help visible.
- On parser recursion/failure, performs a separately bounded structured
  classification before falling back to conservative blocking, so reset,
  clean, force/mirror push, and aliases fail closed while valid dry-runs remain
  non-blocking.
- Runs staged validation for every real `git commit` form.
- Blocks a real commit when Git/index/subprocess/decode inspection cannot
  complete, including parser recursion and deterministic type/value failures;
  invalid staged JSON also blocks.
- Warns for protected destinations including simple branches,
  `HEAD:main`, `:`, `+:`, wildcard/matching destinations, and `--all`, `--branches`, or
  dry-run `--mirror`; a tags-only push does not imply the current branch.
- Skips operands for `--recurse-submodules`, `--receive-pack`, `--push-option`,
  and `-o` when determining modes, remotes, and refspec destinations.
- Evaluates every invocation in compound commands: any block wins, while commit
  context and every protected-push advisory are combined when non-blocking.

Commit quality findings and protected-branch pushes remain advisory. Asset and
skill findings, gap detection, and lifecycle context remain fail-open.

## Repository I/O Safety

All runner-controlled reads and writes now use verified OS handles from open
through read or append. On POSIX, the root is opened with
`O_DIRECTORY | O_NOFOLLOW`, every descendant parent is opened relative to the
previous descriptor and checked against its parent entry, and the final
`O_NOFOLLOW | O_NONBLOCK` descriptor must identify a regular file before it is
made blocking and used.
Native POSIX race tests replace an opened parent or the final path with a
symlink and prove that reads and appends reject the swap without disclosing or
modifying the external target. FIFO and descriptor-cleanup cases are also
covered natively.

On Windows, the implementation opens and retains the root and each ancestor
without delete sharing, uses `FILE_FLAG_OPEN_REPARSE_POINT`, rejects reparse
metadata, verifies each handle's final path remains under the verified root,
and transfers only a verified regular-file handle to the read/append stream.
If stream construction fails after `open_osfhandle` transfers ownership, the
new descriptor is closed for both read and append paths without attempting a
second close through the Win32 handle API.
The Windows evidence in this report is mock-based contract coverage for flags,
containment, reparse rejection, component validation, and handle cleanup; this
verification did not execute the implementation natively on Windows.

Traversal, NUL, surrogate, non-text, and malformed path values fail open
without I/O. Unsafe advisory I/O is skipped with a safe warning and never
blocks; tests prove external state files, log directories, asset files, and
enumerated directories are neither disclosed nor modified. Session/audit
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
python3 -m unittest tests.studio.test_hooks tests.studio.test_instruction_coverage -q
python3 -m unittest discover -s tests/studio -q
python3 -m tools.codex_studio.validate --root . --phase final
python3 -m py_compile .codex/hooks/safe_io.py .codex/hooks/hook_runner.py tools/codex_studio/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
git diff --check
```

Final evidence on this POSIX feature-branch run: the focused suite passed 78
tests and the complete studio suite passed 270 tests, both with `OK`; the
validator printed `Codex Studio validation: PASS`; Python compilation, JSON
parsing, and whitespace checks each exited 0.

## Concerns

None blocking. Native race evidence is present for POSIX. Windows guarantees are
supported by mock-based API-contract tests in this branch, not by a native
Windows execution; native Windows CI remains the outstanding portability check.
