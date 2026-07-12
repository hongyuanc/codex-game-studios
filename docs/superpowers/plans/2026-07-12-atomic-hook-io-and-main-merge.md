# Atomic Hook I/O and Main Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hook working-tree check-then-open I/O with atomic handle-based access, verify the Codex migration, and fast-forward the verified result into local `main` without losing conflicting untracked files.

**Architecture:** Add a focused safe-I/O module used by the hook runner. POSIX uses descriptor-relative `O_NOFOLLOW` traversal; Windows uses `CreateFileW` handles with reparse and final-path containment checks. After the security change passes all tests and review, archive the original checkout's conflicting untracked Codex files and fast-forward `main`.

**Tech Stack:** Python 3.11 standard library (`os`, `stat`, `ctypes`, `msvcrt`, `contextlib`), `unittest`, Codex hooks JSON, Git worktrees.

## Global Constraints

- Preserve session, compaction, gap-detection, asset-validation, and audit behavior.
- Lexical validation remains an early check; verified handles are the I/O security boundary.
- Unsafe advisory I/O exits `0`, emits a safe warning, and performs no fallback pathname I/O.
- POSIX final reads/appends use descriptor-relative `O_NOFOLLOW` operations.
- Windows final reads/appends use `CreateFileW`, reject reparse points, and verify the resolved handle remains below the repository root.
- No external dependency is added.
- Tests must demonstrate RED before implementation and GREEN afterward.
- Local `main` is fast-forwarded only after complete feature-branch verification.
- Conflicting untracked files in the original checkout are moved to a verified backup under `/private/tmp`; unrelated `docs/superpowers/` remains in place.
- Do not pull, push, publish, or release.

---

### Task 1: Atomic Repository I/O Layer

**Files:**
- Create: `.codex/hooks/safe_io.py`
- Modify: `.codex/hooks/hook_runner.py`
- Modify: `tests/studio/test_hooks.py`

**Interfaces:**
- Consumes: validated repository root plus a repository-relative `str | pathlib.Path`.
- Produces: `atomic_read_text(root, relative, *, errors="strict") -> str`, `atomic_append_text(root, relative, text) -> None`, and `UnsafeAtomicPathError`.
- The hook runner translates `UnsafeAtomicPathError` into its existing `UnsafePathError`/advisory result contract.

- [ ] **Step 1: Add failing POSIX race and normal-I/O tests**

Add a dedicated loader for `.codex/hooks/safe_io.py`, then add tests equivalent to:

```python
SAFE_IO_SPEC = spec_from_file_location("codex_hook_safe_io", ROOT / ".codex/hooks/safe_io.py")
SAFE_IO = module_from_spec(SAFE_IO_SPEC)
sys.modules[SAFE_IO_SPEC.name] = SAFE_IO
SAFE_IO_SPEC.loader.exec_module(SAFE_IO)

def test_atomic_read_rejects_parent_swapped_to_symlink(self):
    temporary, root = self.make_root()
    external = tempfile.TemporaryDirectory()
    self.addCleanup(temporary.cleanup)
    self.addCleanup(external.cleanup)
    state_dir = root / "production/session-state"
    state_dir.mkdir(parents=True)
    (state_dir / "active.md").write_text("safe", encoding="utf-8")

    def swap_parent(parts):
        if parts == ("production", "session-state"):
            (state_dir / "active.md").unlink()
            state_dir.rmdir()
            state_dir.symlink_to(Path(external.name), target_is_directory=True)

    with mock.patch.object(SAFE_IO, "_posix_after_component_open", side_effect=swap_parent):
        with self.assertRaises(SAFE_IO.UnsafeAtomicPathError):
            SAFE_IO.atomic_read_text(root, "production/session-state/active.md")

def test_atomic_append_creates_and_appends_inside_repository(self):
    temporary, root = self.make_root()
    self.addCleanup(temporary.cleanup)
    SAFE_IO.atomic_append_text(root, "production/session-logs/audit.log", "one\n")
    SAFE_IO.atomic_append_text(root, "production/session-logs/audit.log", "two\n")
    self.assertEqual("one\ntwo\n", (root / "production/session-logs/audit.log").read_text())
```

Also cover final-file symlink replacement, append-target replacement, missing read, regular-file verification, and descriptor cleanup after an injected failure.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.studio.test_hooks.HookBehaviorTests.test_atomic_read_rejects_parent_swapped_to_symlink \
  tests.studio.test_hooks.HookBehaviorTests.test_atomic_append_creates_and_appends_inside_repository -v
```

Expected: import/file failure because `.codex/hooks/safe_io.py` and its interfaces do not exist.

- [ ] **Step 3: Implement POSIX descriptor-relative traversal**

Implement these concrete pieces in `safe_io.py`:

```python
class UnsafeAtomicPathError(RuntimeError):
    pass

def _relative_parts(root: pathlib.Path, relative: str | pathlib.Path) -> tuple[pathlib.Path, tuple[str, ...]]:
    # Reject NUL, surrogate code points, absolute paths, empty/dot/dot-dot parts,
    # and resolve the trusted root once. Return (trusted_root, parts).

@contextlib.contextmanager
def _posix_parent_fd(root: pathlib.Path, parts: tuple[str, ...], *, create: bool):
    # Open root with O_RDONLY|O_DIRECTORY|O_NOFOLLOW.
    # For every parent component, optionally mkdir through dir_fd, then open it
    # with O_DIRECTORY|O_NOFOLLOW and verify fstat() is a directory.
    # Yield (parent_fd, final_name); close all descriptors in reverse order.

def _posix_read_text(root, parts, *, errors):
    # os.open(final_name, O_RDONLY|O_NOFOLLOW, dir_fd=parent_fd), verify regular
    # with fstat, then os.fdopen(fd, "r", encoding="utf-8", errors=errors).

def _posix_append_text(root, parts, text):
    # os.open(final_name, O_APPEND|O_CREAT|O_WRONLY|O_NOFOLLOW, 0o666,
    # dir_fd=parent_fd), verify regular, then fdopen and write.
```

Expose `_posix_after_component_open(parts)` as a no-op test seam called only
after a component handle is safely open; the implementation must remain safe if
the pathname is swapped after this callback.

- [ ] **Step 4: Run POSIX focused and existing symlink tests**

Run:

```bash
python3 -m unittest \
  tests.studio.test_hooks.HookBehaviorTests.test_atomic_read_rejects_parent_swapped_to_symlink \
  tests.studio.test_hooks.HookBehaviorTests.test_atomic_append_creates_and_appends_inside_repository \
  tests.studio.test_hooks.HookBehaviorTests.test_session_state_symlinks_are_not_read_or_disclosed \
  tests.studio.test_hooks.HookBehaviorTests.test_session_log_symlink_is_not_written_outside_repository -v
```

Expected: all selected tests end with `OK`.

- [ ] **Step 5: Add failing Windows handle-contract tests**

Add mock-based tests that assert:

```python
def test_windows_open_rejects_reparse_and_outside_final_path(self):
    # Force the Windows adapter path.
    # Mock CreateFileW to return handles, FileAttributeTagInfo to report a
    # reparse point, and GetFinalPathNameByHandleW to return an outside path.
    # Each case must raise UnsafeAtomicPathError and close every handle.

def test_windows_open_uses_required_flags(self):
    # Assert directory opens include FILE_FLAG_BACKUP_SEMANTICS and
    # FILE_FLAG_OPEN_REPARSE_POINT; final file opens include
    # FILE_FLAG_OPEN_REPARSE_POINT and the correct read/append disposition.
```

- [ ] **Step 6: Run the Windows contract tests and verify RED**

Run the two new test methods directly.

Expected: FAIL because the Windows adapter/constants are absent.

- [ ] **Step 7: Implement the Windows adapter**

Implement a private `_WindowsApi` with typed `ctypes` bindings for:

```python
CreateFileW
GetFileInformationByHandleEx  # FileAttributeTagInfo
GetFinalPathNameByHandleW
CloseHandle
```

Use these exact protections:

- directory flags: `FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT`;
- final flags: `FILE_FLAG_OPEN_REPARSE_POINT`;
- reject `FILE_ATTRIBUTE_REPARSE_POINT` or nonzero reparse tags;
- verify `GetFinalPathNameByHandleW` is contained by the verified root using
  case-insensitive Windows path comparison;
- transfer the verified final handle to Python with `msvcrt.open_osfhandle` so
  the resulting file object owns and closes it;
- close every directory handle and every final handle not successfully
  transferred to Python in `finally` blocks.

`atomic_read_text()` and `atomic_append_text()` dispatch to the POSIX or Windows
implementation without a pathname-I/O fallback.

- [ ] **Step 8: Integrate the hook runner**

At the top of `hook_runner.py`, insert its directory into `sys.path` and import:

```python
from safe_io import UnsafeAtomicPathError, atomic_append_text, atomic_read_text
```

Replace `_safe_read_text()` and `_append()` internals:

```python
def _safe_read_text(root, relative, *, errors="strict"):
    _safe_relative_path(root, relative)  # lexical diagnostics only
    try:
        return atomic_read_text(root, relative, errors=errors)
    except UnsafeAtomicPathError as error:
        raise UnsafePathError(str(error)) from error

def _append(root, relative, text):
    _safe_relative_path(root, relative)
    try:
        atomic_append_text(root, relative, text)
    except UnsafeAtomicPathError as error:
        raise UnsafePathError(str(error)) from error
```

Remove the obsolete `_safe_mkdir()` pathname creation path if no caller remains.

- [ ] **Step 9: Add a static no-fallback assertion**

Add a test that inspects `hook_runner.py` and asserts the bodies of
`_safe_read_text` and `_append` contain the atomic helper calls and contain none
of `.read_text(`, `.open(`, or `_safe_mkdir(`.

- [ ] **Step 10: Run the complete hook suite**

Run:

```bash
python3 -m unittest tests.studio.test_hooks tests.studio.test_instruction_coverage -v
```

Expected: all hook and instruction tests end with `OK`.

- [ ] **Step 11: Commit the atomic I/O implementation**

```bash
git add .codex/hooks/safe_io.py .codex/hooks/hook_runner.py tests/studio/test_hooks.py
git commit -m "fix: make hook repository I/O atomic"
```

---

### Task 2: Documentation and Feature-Branch Verification

**Files:**
- Modify: `.superpowers/sdd/rules-hooks-subsystem-report.md`
- Modify: `tests/studio/test_hooks.py` only if final evidence requires a test correction

**Interfaces:**
- Consumes: Task 1's atomic helper APIs and passing hook suite.
- Produces: accurate cross-platform guarantees and a fully verified feature branch.

- [ ] **Step 1: Update the hook report**

Replace the TOCTOU concern with the implemented handle guarantees. State that
POSIX behavior has native race tests and Windows behavior has mock-based contract
evidence unless a native Windows run is available. Do not claim native Windows
execution evidence.

- [ ] **Step 2: Run focused and full verification**

Run:

```bash
python3 -m unittest tests.studio.test_hooks tests.studio.test_instruction_coverage -q
python3 -m unittest discover -s tests/studio -q
python3 -m tools.codex_studio.validate --root . --phase final
python3 -m py_compile .codex/hooks/safe_io.py .codex/hooks/hook_runner.py tools/codex_studio/*.py
python3 -m json.tool .codex/hooks.json >/dev/null
git diff --check
```

Expected: both suites end with `OK`; validator prints `Codex Studio validation: PASS`; parsing and whitespace commands exit `0`.

- [ ] **Step 3: Commit the report**

```bash
git add .superpowers/sdd/rules-hooks-subsystem-report.md
git commit -m "docs: record atomic hook I/O evidence"
```

---

### Task 3: Preserve Main Checkout and Fast-Forward

**Files:**
- Move from original checkout into backup: `.agents/`, `.codex/`, `AGENTS.md`
- Leave untouched in original checkout: `docs/superpowers/`
- Merge: `codex/codex-native-migration` into `main`

**Interfaces:**
- Consumes: fully verified feature-branch HEAD from Task 2.
- Produces: local `main` at the same verified commit and `/private/tmp/codex-game-studios-main-untracked-backup-20260712` containing the displaced untracked originals.

- [ ] **Step 1: Verify fast-forward ancestry and feature status**

Run:

```bash
git merge-base --is-ancestor main codex/codex-native-migration
git status --short
```

Expected: ancestry exits `0`; feature status contains only the intentionally untracked historical `docs/superpowers/` files that are not part of the two newly tracked plan/spec paths.

- [ ] **Step 2: Record and move the conflicting untracked main files**

From `/Users/hong/projects/personal/codex-game-studios`:

```bash
backup=/private/tmp/codex-game-studios-main-untracked-backup-20260712
test ! -e "$backup"
mkdir -p "$backup"
{ printf 'AGENTS.md\n'; find .agents .codex -type f -print; } | LC_ALL=C sort > "$backup/inventory.before.txt"
while IFS= read -r file; do shasum -a 256 "$file"; done < "$backup/inventory.before.txt" > "$backup/sha256.before.txt"
mv .agents .codex AGENTS.md "$backup"/
(
  cd "$backup"
  { printf 'AGENTS.md\n'; find .agents .codex -type f -print; } | LC_ALL=C sort > inventory.after.txt
  while IFS= read -r file; do shasum -a 256 "$file"; done < inventory.after.txt > sha256.after.txt
)
cmp "$backup/inventory.before.txt" "$backup/inventory.after.txt"
cmp "$backup/sha256.before.txt" "$backup/sha256.after.txt"
```

If either `cmp` fails, move the three originals back before attempting the
merge.

- [ ] **Step 3: Fast-forward local main**

Run:

```bash
git switch main
git merge --ff-only codex/codex-native-migration
```

Expected: fast-forward succeeds with no merge commit and no pull/network access.

- [ ] **Step 4: Verify merged main**

Run from the merged main checkout:

```bash
python3 -m unittest discover -s tests/studio -q
python3 -m tools.codex_studio.validate --root . --phase final
python3 -m py_compile .codex/hooks/safe_io.py .codex/hooks/hook_runner.py tools/codex_studio/*.py
git diff --check
git status --short
git rev-parse main
git rev-parse codex/codex-native-migration
```

Expected: tests and validator pass; compile/diff checks exit `0`; status contains only the pre-existing untracked `docs/superpowers/` history; both branch hashes are identical.

- [ ] **Step 5: Preserve external worktree and report**

Do not remove `/private/tmp/codex-game-studios-codex-native` or delete its
checked-out feature branch because it is outside repository-owned `.worktrees/`.
Report the merged commit, backup path, test count, validator result, and remaining
manual Windows evidence caveat. Do not push.
