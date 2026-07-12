# Atomic Hook I/O and Main Merge Design

## Goal

Remove the hook runner's check-then-open filesystem race without losing session,
gap-detection, asset-validation, or audit behavior. After the fix passes the full
gate, integrate the completed Codex migration into local `main` while preserving
the original checkout's conflicting untracked files in an external backup.

## Current Problem

`_safe_relative_path()` validates every path component with `lstat()`, but
`_safe_read_text()` and `_append()` later reopen the path by name. An entry can
be replaced with a symlink or reparse point between those operations. Existing
checks reject links that already exist, but they do not bind validation and I/O
to the same filesystem object.

## Approaches Considered

1. **Atomic handle traversal (selected).** Open and validate each component,
   then perform I/O through the verified parent handle. This preserves all hook
   behavior and closes the race at the filesystem boundary.
2. **Remove hook filesystem I/O.** Emit advice only and stop reading or writing
   repository files. This removes the race but discards useful lifecycle logs,
   gap detection, session context, and JSON validation.
3. **Cooperative lock plus repeated checks.** This reduces accidental races but
   does not protect against an uncooperative process changing a path between the
   final check and open.

## Selected Architecture

### Shared contract

Keep `_safe_relative_path()` for lexical validation, malformed-input rejection,
and early diagnostics. It is not the security boundary. New handle-based helpers
must:

- start from a verified handle to the repository root;
- traverse only relative components;
- reject symlinks, junctions, reparse points, non-directories, and containment
  changes;
- open the final file through the verified parent handle;
- verify the opened object is a regular file where a file is required;
- preserve the existing advisory fail-open behavior while never performing I/O
  on an unsafe object.

### POSIX implementation

Use descriptor-relative operations:

- open the root directory with `O_DIRECTORY` and `O_NOFOLLOW`;
- open each directory component with `os.open(..., dir_fd=parent_fd,
  O_DIRECTORY | O_NOFOLLOW)`;
- create missing session-log directories with `os.mkdir(..., dir_fd=parent_fd)`,
  then open and verify them through the parent descriptor;
- read files using a final `O_RDONLY | O_NOFOLLOW` descriptor;
- append using `O_APPEND | O_CREAT | O_WRONLY | O_NOFOLLOW` through the verified
  parent descriptor;
- compare `fstat()` identity where creation or replacement races are possible;
- close every descriptor on success and failure.

### Windows implementation

Use a small standard-library `ctypes` adapter around `CreateFileW`:

- open directories with `FILE_FLAG_BACKUP_SEMANTICS` and
  `FILE_FLAG_OPEN_REPARSE_POINT`;
- inspect `FileAttributeTagInfo` and reject any reparse point/name surrogate;
- open the final file handle before reading or appending;
- use `GetFinalPathNameByHandleW` to verify the opened object resolves below the
  already verified repository root;
- convert safe file handles with `msvcrt.open_osfhandle` for Python text I/O;
- close native handles on every error path.

The Windows branch will have mock-based contract tests on the current platform;
native Windows execution remains a separately reported evidence item unless a
Windows runner is available.

### Hook integration

Route runner-controlled reads and appends through the new helpers:

- session-state reads;
- compaction/session/agent audit appends;
- asset JSON reads;
- enumerated repository file reads used by gap detection and staged checks where
  the runner accesses the working tree.

Git-index reads performed through `git show` remain subprocess-bound and are not
part of this pathname race.

## Error Handling

- Unsafe, raced, malformed, unsupported, or unopenable paths produce the
  existing safe advisory warning and exit `0` for advisory hooks.
- No fallback may reopen a rejected path by pathname.
- Descriptor/handle cleanup occurs in `finally` blocks or context managers.
- Unsupported Windows API behavior must skip the I/O safely and report it; it
  must not silently use the old check-then-open path.

## Testing

Test-first coverage will include:

- a POSIX race that replaces a validated file or parent with a symlink before
  the final open;
- a race that creates/replaces an append target;
- existing file and directory symlink cases;
- successful normal reads, appends, and directory creation;
- descriptor cleanup after failures;
- Windows adapter contracts for flags, reparse rejection, final-path
  containment, and handle cleanup;
- proof that no hook-controlled read/append path uses `Path.read_text()` or
  `Path.open()` after validation;
- the full studio suite, final validator, Python/JSON parsing, and whitespace
  checks.

## Local Main Integration

The original `main` checkout contains untracked `.agents/`, `.codex/`, and
`AGENTS.md` files that would block a fast-forward. Before merging:

1. Record the exact untracked inventory and copy the conflicting items to a
   timestamped backup under `/private/tmp`.
2. Verify the backup hashes/counts before moving the conflicting originals out
   of the checkout. Leave unrelated untracked `docs/superpowers/` untouched.
3. Fast-forward local `main` to `codex/codex-native-migration`; do not pull,
   push, or publish.
4. Run the complete test suite and final validator from the merged `main`.
5. Keep the external worktree/feature branch because it is outside the
   repository-owned `.worktrees/` paths; report its location and backup path.

## Success Criteria

- Race regressions fail before the implementation and pass afterward.
- No hook-controlled working-tree read or append uses a check-then-open path.
- All studio tests and final validation pass on the feature branch and merged
  `main`.
- Local `main` points to the verified hook-fix commit.
- Conflicting original untracked files remain recoverable from a verified
  external backup.
- No push, release, or publication occurs.
