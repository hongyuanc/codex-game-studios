"""Locked, checksummed recovery transactions for approved operation plans.

Lifecycle-specific callbacks may only mutate digest-approved paths through the
provided :class:`AtomicMutation` object.  The transaction owns locking,
same-filesystem snapshots, durable journal phases, validation, and rollback.
"""

from __future__ import annotations

import dataclasses
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import time
from collections.abc import Callable, Iterable
from typing import Any
import uuid

from models import (
    Action,
    OperationPlan,
    PayloadError,
    canonical_json,
    digest_document,
    normalize_relative_path,
    validate_operation_plan_digest,
)
from safe_fs import (
    AnchoredFilesystem,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    GENERIC_WRITE,
    _NOFOLLOW,
    _parent_fd,
    _windows_descriptor_from_verified,
    _windows_open_verified,
    pin_root,
    read_file_secure,
    SecureEntry,
    secure_root_identity,
)
from studio_manager import ManagerError


LOCK_RELATIVE_PATH = ".codex/codex-game-studios/manager.lock"
RECOVERY_RELATIVE_PATH = ".codex/codex-game-studios/recovery"
JOURNAL_SCHEMA_VERSION = 1
_OPEN_ALWAYS = 4
_CHANGING_ACTIONS = frozenset({"create", "merge", "update", "remove", "state-write"})
_JOURNAL_FIELDS = {
    "schema_version",
    "transaction_id",
    "root_identity",
    "plan_digest",
    "authority_digest",
    "phase",
    "execution_index",
    "active_action",
    "active_quarantined",
    "snapshots",
    "applied_paths",
    "checksum",
}
_SNAPSHOT_FIELDS = {"path", "entry_type", "mode", "sha256", "snapshot_path"}
_AUTHORITY_FIELDS = {
    "schema_version",
    "transaction_id",
    "root_identity",
    "plan_digest",
    "changing_actions",
    "snapshots",
    "quarantine_records",
    "checksum",
}
_PHASES = frozenset(
    {
        "snapshot-created",
        "journal-written",
        "action-started",
        "action-applied",
        "validation-started",
        "state-written",
        "committed",
        "rolled-back",
        "ROLLBACK_FAILED",
    }
)


@dataclasses.dataclass(frozen=True)
class SnapshotRecord:
    """Exact pre-transaction type, mode, and optional file-byte snapshot."""

    path: str
    entry_type: str
    mode: int | None
    sha256: str | None
    snapshot_path: str | None


@dataclasses.dataclass(frozen=True)
class QuarantineRecord:
    """Immutable expected quarantine content for one approved action state."""

    path: str
    action_path: str
    role: str
    entry_type: str
    mode: int
    sha256: str


@dataclasses.dataclass(frozen=True)
class RecoveryAuthority:
    """Immutable canonical recovery authority written before the journal."""

    schema_version: int
    transaction_id: str
    root_identity: str
    plan_digest: str
    changing_actions: tuple[Action, ...]
    snapshots: tuple[SnapshotRecord, ...]
    quarantine_records: tuple[QuarantineRecord, ...]
    checksum: str

    def body(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "transaction_id": self.transaction_id,
            "root_identity": self.root_identity,
            "plan_digest": self.plan_digest,
            "changing_actions": [dataclasses.asdict(action) for action in self.changing_actions],
            "snapshots": [dataclasses.asdict(record) for record in self.snapshots],
            "quarantine_records": [
                dataclasses.asdict(record) for record in self.quarantine_records
            ],
        }

    def checksummed(self) -> "RecoveryAuthority":
        return dataclasses.replace(
            self, checksum=hashlib.sha256(canonical_json(self.body())).hexdigest()
        )

    def encoded(self) -> bytes:
        if self.checksum != self.checksummed().checksum:
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority checksum is stale")
        document = self.body()
        document["checksum"] = self.checksum
        return canonical_json(document)

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        expected_root_identity: str,
        expected_transaction_id: str,
        approved_plan: OperationPlan,
    ) -> "RecoveryAuthority":
        try:
            validate_operation_plan_digest(approved_plan)
        except PayloadError as error:
            raise ManagerError("INVALID_INSTALLATION_STATE", "approved recovery plan is invalid") from error
        state_actions = tuple(
            action for action in approved_plan.actions if action.kind == "state-write"
        )
        expected_actions = tuple(
            action
            for action in approved_plan.actions
            if action.kind in _CHANGING_ACTIONS and action.kind != "state-write"
        ) + state_actions
        authority_path = Path(path)
        try:
            root = authority_path.parents[4]
            relative = authority_path.relative_to(root).as_posix()
            raw = read_file_secure(root, relative)
            document = json.loads(raw.decode("utf-8"))
        except (IndexError, OSError, PayloadError, UnicodeError, json.JSONDecodeError) as error:
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority is unreadable") from error
        if not isinstance(document, dict) or set(document) != _AUTHORITY_FIELDS:
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority fields are invalid")
        if document["schema_version"] != JOURNAL_SCHEMA_VERSION:
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority schema is invalid")
        try:
            actions = tuple(Action(**item) for item in document["changing_actions"])
            snapshots = tuple(SnapshotRecord(**item) for item in document["snapshots"])
            quarantine = tuple(
                QuarantineRecord(**item) for item in document["quarantine_records"]
            )
        except (TypeError, PayloadError) as error:
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority content is invalid") from error
        authority = cls(
            document["schema_version"],
            document["transaction_id"],
            document["root_identity"],
            document["plan_digest"],
            actions,
            snapshots,
            quarantine,
            document["checksum"],
        )
        if raw != authority.encoded():
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority is noncanonical")
        if (
            authority.transaction_id != authority_path.parent.name
            or authority.transaction_id != expected_transaction_id
            or authority.root_identity != expected_root_identity
            or authority.root_identity != secure_root_identity(root)
            or authority.plan_digest != approved_plan.digest
            or authority.changing_actions != expected_actions
        ):
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery authority does not match approval")
        if len({action.path.casefold() for action in actions}) != len(actions):
            raise ManagerError("INVALID_INSTALLATION_STATE", "authority actions are not canonical")
        if snapshots != tuple(
            sorted(snapshots, key=lambda item: (len(PurePosixPath(item.path).parts), item.path))
        ) or len({item.path.casefold() for item in snapshots}) != len(snapshots):
            raise ManagerError("INVALID_INSTALLATION_STATE", "authority snapshots are not canonical")
        observations = {item.path: item for item in approved_plan.target_observations}
        if {record.path for record in snapshots} != set(observations):
            raise ManagerError("INVALID_INSTALLATION_STATE", "authority snapshots are unauthorized")
        for index, record in enumerate(snapshots):
            digest_valid = isinstance(record.sha256, str) and len(record.sha256) == 64 and all(
                character in "0123456789abcdef" for character in record.sha256
            )
            if record.entry_type == "missing":
                valid = record.mode is None and record.sha256 is None and record.snapshot_path is None
            elif record.entry_type == "directory":
                valid = type(record.mode) is int and digest_valid and record.snapshot_path is None
            elif record.entry_type == "file":
                expected_storage = (
                    f"{RECOVERY_RELATIVE_PATH}/{authority.transaction_id}"
                    f"/snapshots/{index:06d}.bin"
                )
                valid = (
                    type(record.mode) is int
                    and digest_valid
                    and record.snapshot_path == expected_storage
                )
            else:
                valid = False
            if not valid:
                raise ManagerError("INVALID_INSTALLATION_STATE", "authority snapshot is malformed")
            approved = observations[record.path]
            if (
                record.entry_type != approved.entry_type
                or record.mode != approved.mode
                or record.sha256 != approved.digest
            ):
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE",
                    "authority snapshot does not match approved plan observation",
                )
            action = next(item for item in actions if item.path == record.path)
            if action.before_hash != approved.digest and not (
                action.kind in {"create", "state-write"}
                and action.before_hash is None
                and approved.entry_type == "missing"
            ):
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "authority snapshot before-state is invalid"
                )
        if quarantine != tuple(sorted(quarantine, key=lambda item: item.path)) or len(
            {item.path.casefold() for item in quarantine}
        ) != len(quarantine):
            raise ManagerError("INVALID_INSTALLATION_STATE", "authority quarantine is not canonical")
        for item in quarantine:
            try:
                path = normalize_relative_path(item.path)
                action_path = normalize_relative_path(item.action_path)
            except PayloadError as error:
                raise ManagerError("INVALID_INSTALLATION_STATE", "authority quarantine is unsafe") from error
            if (
                path != item.path
                or action_path != item.action_path
                or item.role not in {"approved-before", "rollback-after"}
                or item.entry_type not in {"file", "directory"}
                or type(item.mode) is not int
                or not isinstance(item.sha256, str)
                or len(item.sha256) != 64
                or any(character not in "0123456789abcdef" for character in item.sha256)
            ):
                raise ManagerError("INVALID_INSTALLATION_STATE", "authority quarantine record is malformed")
        if quarantine != _quarantine_authority_records(
            str(PurePosixPath(relative).parent), expected_actions, approved_plan
        ):
            raise ManagerError(
                "INVALID_INSTALLATION_STATE",
                "authority quarantine does not match approved plan states",
            )
        return authority


@dataclasses.dataclass(frozen=True)
class RecoveryJournal:
    """Canonical, checksum-bound durable recovery journal."""

    schema_version: int
    transaction_id: str
    root_identity: str
    plan_digest: str
    authority_digest: str
    phase: str
    execution_index: int
    active_action: str | None
    active_quarantined: bool
    snapshots: tuple[SnapshotRecord, ...]
    applied_paths: tuple[str, ...]
    checksum: str

    def body(self) -> dict[str, object]:
        """Return all checksum-covered journal fields."""

        return {
            "schema_version": self.schema_version,
            "transaction_id": self.transaction_id,
            "root_identity": self.root_identity,
            "plan_digest": self.plan_digest,
            "authority_digest": self.authority_digest,
            "phase": self.phase,
            "execution_index": self.execution_index,
            "active_action": self.active_action,
            "active_quarantined": self.active_quarantined,
            "snapshots": [dataclasses.asdict(item) for item in self.snapshots],
            "applied_paths": list(self.applied_paths),
        }

    def checksummed(self) -> "RecoveryJournal":
        """Return this journal with a SHA-256 checksum over its canonical body."""

        digest = hashlib.sha256(canonical_json(self.body())).hexdigest()
        return dataclasses.replace(self, checksum=digest)

    def encoded(self) -> bytes:
        """Return strict canonical JSON after verifying the current checksum."""

        expected = self.checksummed().checksum
        if self.checksum != expected:
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery journal checksum is stale")
        document = self.body()
        document["checksum"] = self.checksum
        return canonical_json(document)

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        authority: RecoveryAuthority,
        allowed_phases: frozenset[str],
    ) -> "RecoveryJournal":
        """Load a journal only under independent recovery authority."""

        journal_path = Path(path)
        try:
            root = journal_path.parents[4]
            relative = journal_path.relative_to(root).as_posix()
            if not relative.startswith(f"{RECOVERY_RELATIVE_PATH}/"):
                raise ValueError
            raw = read_file_secure(root, relative)
        except (IndexError, OSError, PayloadError, ValueError) as error:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "recovery journal cannot be read safely"
            ) from error
        journal = cls._parse(raw)
        if (
            journal.transaction_id != journal_path.parent.name
            or journal.transaction_id != authority.transaction_id
        ):
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "journal transaction does not match generation"
            )
        if (
            journal.root_identity != secure_root_identity(root)
            or journal.root_identity != authority.root_identity
        ):
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "journal root identity does not match repository"
            )
        if journal.plan_digest != authority.plan_digest:
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal plan digest is unauthorized")
        if journal.authority_digest != authority.checksum:
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal authority digest is invalid")
        if journal.snapshots != authority.snapshots:
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal snapshots are unauthorized")
        if journal.phase not in allowed_phases:
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal phase transition is unauthorized")
        normalized_actions = frozenset(action.path for action in authority.changing_actions)
        if {item.path for item in journal.snapshots} != normalized_actions:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "journal snapshots do not match action authority"
            )
        if any(path not in normalized_actions for path in journal.applied_paths):
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal applied path is unauthorized")
        for record in journal.snapshots:
            if record.snapshot_path is None:
                continue
            try:
                snapshot = read_file_secure(root, record.snapshot_path)
            except PayloadError as error:
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "authorized recovery snapshot is unreadable"
                ) from error
            if hashlib.sha256(snapshot).hexdigest() != record.sha256:
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "authorized recovery snapshot checksum mismatch"
                )
        _validate_journal_phase(authority, journal)
        with pin_root(root) as pinned:
            filesystem = AnchoredFilesystem(pinned)
            _verify_complete_generation(filesystem, authority, relative, journal)
        return journal

    @classmethod
    def _parse(cls, raw: bytes) -> "RecoveryJournal":
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "recovery journal is not UTF-8 JSON"
            ) from error
        if not isinstance(document, dict) or set(document) != _JOURNAL_FIELDS:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "recovery journal fields are missing or extra"
            )
        if document["schema_version"] != JOURNAL_SCHEMA_VERSION or type(
            document["schema_version"]
        ) is not int:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "unsupported recovery journal schema"
            )
        for key in (
            "transaction_id",
            "root_identity",
            "plan_digest",
            "authority_digest",
            "phase",
            "checksum",
        ):
            if not isinstance(document[key], str) or not document[key]:
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "malformed recovery journal metadata"
                )
        identity_parts = document["root_identity"].split(":")
        if (
            len(identity_parts) != 3
            or identity_parts[0] not in {"posix", "windows"}
            or not all(part.isdecimal() for part in identity_parts[1:])
        ):
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "malformed recovery root identity"
            )
        try:
            parsed_id = uuid.UUID(document["transaction_id"])
            if str(parsed_id) != document["transaction_id"]:
                raise ValueError
        except ValueError as error:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "malformed recovery transaction identifier"
            ) from error
        if document["phase"] not in _PHASES:
            raise ManagerError("INVALID_INSTALLATION_STATE", "unknown recovery journal phase")
        for key in ("plan_digest", "authority_digest", "checksum"):
            value = document[key]
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "malformed recovery journal digest"
                )
        raw_snapshots = document["snapshots"]
        if not isinstance(raw_snapshots, list):
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal snapshots must be a list")
        snapshots: list[SnapshotRecord] = []
        for index, item in enumerate(raw_snapshots):
            if not isinstance(item, dict) or set(item) != _SNAPSHOT_FIELDS:
                raise ManagerError("INVALID_INSTALLATION_STATE", "malformed snapshot record")
            try:
                path = normalize_relative_path(item["path"])
            except (PayloadError, TypeError) as error:
                raise ManagerError("INVALID_INSTALLATION_STATE", "unsafe snapshot path") from error
            entry_type = item["entry_type"]
            mode = item["mode"]
            digest = item["sha256"]
            snapshot_path = item["snapshot_path"]
            if entry_type not in {"missing", "file", "directory"}:
                raise ManagerError("INVALID_INSTALLATION_STATE", "malformed snapshot type")
            if entry_type == "missing":
                if any(value is not None for value in (mode, digest, snapshot_path)):
                    raise ManagerError("INVALID_INSTALLATION_STATE", "malformed missing snapshot")
            elif entry_type == "directory":
                if (
                    type(mode) is not int
                    or not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                    or snapshot_path is not None
                ):
                    raise ManagerError("INVALID_INSTALLATION_STATE", "malformed directory snapshot")
            else:
                if type(mode) is not int or not isinstance(digest, str) or not isinstance(snapshot_path, str):
                    raise ManagerError("INVALID_INSTALLATION_STATE", "malformed file snapshot")
                try:
                    normalize_relative_path(snapshot_path)
                except PayloadError as error:
                    raise ManagerError("INVALID_INSTALLATION_STATE", "unsafe snapshot storage path") from error
                expected_snapshot_path = (
                    f"{RECOVERY_RELATIVE_PATH}/{document['transaction_id']}"
                    f"/snapshots/{index:06d}.bin"
                )
                if snapshot_path != expected_snapshot_path:
                    raise ManagerError(
                        "INVALID_INSTALLATION_STATE",
                        "snapshot storage path does not match transaction",
                    )
                if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                    raise ManagerError("INVALID_INSTALLATION_STATE", "malformed snapshot hash")
            snapshots.append(SnapshotRecord(path, entry_type, mode, digest, snapshot_path))
        if snapshots != sorted(snapshots, key=lambda item: (len(PurePosixPath(item.path).parts), item.path)):
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal snapshots are not canonical")
        if len({item.path.casefold() for item in snapshots}) != len(snapshots):
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal snapshot paths collide")
        applied = document["applied_paths"]
        if not isinstance(applied, list):
            raise ManagerError("INVALID_INSTALLATION_STATE", "applied paths must be a list")
        try:
            applied_paths = tuple(normalize_relative_path(item) for item in applied)
        except (PayloadError, TypeError) as error:
            raise ManagerError("INVALID_INSTALLATION_STATE", "unsafe applied path") from error
        if applied_paths != tuple(sorted(set(applied_paths))) or len(
            {path.casefold() for path in applied_paths}
        ) != len(applied_paths):
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "applied paths are not canonical and unique"
            )
        if type(document["execution_index"]) is not int or document[
            "execution_index"
        ] < 0:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "journal execution index is malformed"
            )
        active_action = document["active_action"]
        if active_action is not None:
            try:
                active_action = normalize_relative_path(active_action)
            except (PayloadError, TypeError) as error:
                raise ManagerError("INVALID_INSTALLATION_STATE", "journal active action is unsafe") from error
        if type(document["active_quarantined"]) is not bool:
            raise ManagerError("INVALID_INSTALLATION_STATE", "journal quarantine marker is malformed")
        journal = cls(
            document["schema_version"],
            document["transaction_id"],
            document["root_identity"],
            document["plan_digest"],
            document["authority_digest"],
            document["phase"],
            document["execution_index"],
            active_action,
            document["active_quarantined"],
            tuple(snapshots),
            applied_paths,
            document["checksum"],
        )
        if journal.checksummed().checksum != journal.checksum or raw != journal.encoded():
            raise ManagerError("INVALID_INSTALLATION_STATE", "recovery journal checksum mismatch")
        return journal


@dataclasses.dataclass(frozen=True)
class TransactionResult:
    """Successful transaction identity and committed action count."""

    transaction_id: str
    status: str
    actions_applied: int


class RepositoryLock:
    """Bounded cooperative repository lock using native operating-system locks."""

    def __init__(self, root: Path | str, timeout: float = 5.0):
        if timeout < 0:
            raise ValueError("lock timeout cannot be negative")
        self.root = Path(root)
        self.timeout = timeout
        self._descriptor: int | None = None
        self._pin_context: Any = None
        self._pinned: Any = None
        self._lock_parent_fd: int | None = None
        self._lock_name: str | None = None
        self._lock_identity: tuple[int, int] | None = None
        self._windows_lock_identity: tuple[int, int] | None = None
        self._root_locked = False

    @property
    def pinned(self):
        """Return the retained repository root after successful acquisition."""

        if self._pinned is None:
            raise RuntimeError("repository lock is not held")
        return self._pinned

    def verify(self) -> None:
        """Verify root, locked inode, and lock dirent identities remain exact."""

        if self._descriptor is None:
            raise ManagerError("LOCKED", "repository manager lock is not held")
        self.pinned.verify()
        opened = os.fstat(self._descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if self._lock_identity is not None and identity != self._lock_identity:
            raise ManagerError("LOCKED", "repository manager lock identity changed")
        if os.name == "nt":
            current = _windows_open_verified(
                self.root,
                LOCK_RELATIVE_PATH,
                access=GENERIC_READ,
                share=FILE_SHARE_READ | FILE_SHARE_WRITE,
                disposition=3,
                create_parents=False,
                final_directory=False,
            )
            with current as handles:
                current_identity = handles.api.identity(handles.final_handle)
            if current_identity != self._windows_lock_identity:
                raise ManagerError("LOCKED", "repository manager lock path was replaced")
            return
        assert self._lock_parent_fd is not None and self._lock_name is not None
        try:
            current = os.stat(
                self._lock_name,
                dir_fd=self._lock_parent_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            raise ManagerError("LOCKED", "repository manager lock path disappeared") from error
        if (current.st_dev, current.st_ino) != identity:
            raise ManagerError("LOCKED", "repository manager lock path was replaced")

    def __enter__(self) -> "RepositoryLock":
        self._pin_context = pin_root(self.root)
        try:
            self._pinned = self._pin_context.__enter__()
            self._acquire_root_lock()
            self._descriptor = self._open_lock()
            self._acquire()
            return self
        except BaseException:
            self._close_descriptor()
            self._release_root_lock()
            if self._pin_context is not None:
                self._pin_context.__exit__(*sys_exc_info())
            self._pin_context = None
            self._pinned = None
            raise

    def _acquire_root_lock(self) -> None:
        if os.name == "nt":
            return
        import fcntl

        assert self.pinned._descriptor is not None
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(
                    self.pinned._descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB
                )
                self._root_locked = True
                return
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN} or time.monotonic() >= deadline:
                    raise ManagerError("LOCKED", "repository root manager lock is held") from error
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def _release_root_lock(self) -> None:
        if not self._root_locked:
            return
        import fcntl

        assert self.pinned._descriptor is not None
        fcntl.flock(self.pinned._descriptor, fcntl.LOCK_UN)
        self._root_locked = False

    def _open_lock(self) -> int:
        descriptor: int | None = None
        try:
            if os.name == "nt":
                opened = _windows_open_verified(
                    self.root,
                    LOCK_RELATIVE_PATH,
                    access=GENERIC_READ | GENERIC_WRITE,
                    share=FILE_SHARE_READ | FILE_SHARE_WRITE,
                    disposition=_OPEN_ALWAYS,
                    create_parents=True,
                    final_directory=False,
                )
                with opened as handles:
                    self._windows_lock_identity = handles.api.identity(handles.final_handle)
                    descriptor = _windows_descriptor_from_verified(
                        handles, os.O_RDWR | getattr(os, "O_BINARY", 0)
                    )
            else:
                with _parent_fd(self.root, LOCK_RELATIVE_PATH, create=True) as (
                    parent_fd,
                    name,
                ):
                    flags = (
                        os.O_RDWR
                        | os.O_CREAT
                        | getattr(os, "O_CLOEXEC", 0)
                        | _NOFOLLOW
                    )
                    descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
                    self._lock_parent_fd = os.dup(parent_fd)
                    self._lock_name = name
                    opened = os.fstat(descriptor)
                    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if not stat.S_ISREG(opened.st_mode) or (
                        opened.st_dev,
                        opened.st_ino,
                    ) != (current.st_dev, current.st_ino):
                        raise ManagerError(
                            "UNSAFE_PATH", "manager lock is not a stable regular file"
                        )
                    _fsync_parent(parent_fd)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            opened = os.fstat(descriptor)
            self._lock_identity = (opened.st_dev, opened.st_ino)
            return descriptor
        except BaseException:
            if descriptor is not None:
                os.close(descriptor)
            raise

    def _acquire(self) -> None:
        assert self._descriptor is not None
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(self._descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(self._descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError as error:
                retryable = error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
                if not retryable or time.monotonic() >= deadline:
                    raise ManagerError("LOCKED", "repository manager lock is held") from error
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def _release(self) -> None:
        if self._descriptor is None:
            return
        if os.name == "nt":
            import msvcrt

            os.lseek(self._descriptor, 0, os.SEEK_SET)
            msvcrt.locking(self._descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._descriptor, fcntl.LOCK_UN)

    def _close_descriptor(self) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None
        if self._lock_parent_fd is not None:
            os.close(self._lock_parent_fd)
            self._lock_parent_fd = None
        self._lock_name = None
        self._lock_identity = None
        self._windows_lock_identity = None

    def __exit__(self, exc_type, exc, traceback) -> None:
        release_error: BaseException | None = None
        try:
            self.verify()
            self._release()
        except BaseException as error:
            release_error = error
        finally:
            self._close_descriptor()
            self._release_root_lock()
            if self._pin_context is not None:
                try:
                    self._pin_context.__exit__(exc_type, exc, traceback)
                finally:
                    self._pin_context = None
                    self._pinned = None
        if release_error is not None and exc is None:
            raise release_error


def sys_exc_info() -> tuple[type[BaseException] | None, BaseException | None, Any]:
    """Import-free indirection used while unwinding a failed lock enter."""

    import sys

    return sys.exc_info()


class AtomicMutation:
    """Single-action capability revoked immediately after its callback returns."""

    def __init__(
        self,
        filesystem: AnchoredFilesystem,
        action: Action,
        expected: object,
        expected_result: object,
        transaction_id: str,
        on_quarantined: Callable[[], None] | None = None,
    ):
        self._filesystem = filesystem
        self._action = action
        self._expected = expected
        self._expected_result = expected_result
        self._transaction_id = transaction_id
        self._active = True
        self._on_quarantined = on_quarantined if on_quarantined is not None else lambda: None
        self.did_mutate = False

    def revoke(self) -> None:
        """Permanently revoke this per-action capability."""

        self._active = False

    def _require_allowed(self, relative: str, kinds: frozenset[str]) -> str:
        if not self._active:
            raise ManagerError("UNSAFE_PATH", "transaction mutation capability is revoked")
        try:
            relative = normalize_relative_path(relative)
        except PayloadError as error:
            raise ManagerError("UNSAFE_PATH", str(error)) from error
        if relative != self._action.path or self._action.kind not in kinds:
            raise ManagerError("UNSAFE_PATH", "callback attempted an unapproved mutation path")
        return relative

    def _begin_mutation(self) -> None:
        try:
            if not self._filesystem.matches(
                self._filesystem.observe(self._action.path), self._expected
            ):
                raise ManagerError("STALE_PLAN", "action target changed before mutation")
        except PayloadError as error:
            raise ManagerError("STALE_PLAN", str(error)) from error

    def _mark_destructive(self) -> None:
        self.did_mutate = True

    def replace_file(self, relative: str, data: bytes, mode: int = 0o644) -> None:
        """Atomically create or replace one approved regular file."""

        relative = self._require_allowed(
            relative, frozenset({"create", "merge", "update", "state-write"})
        )
        if not isinstance(data, bytes):
            raise TypeError("atomic replacement data must be bytes")
        self._begin_mutation()
        try:
            self._filesystem.atomic_replace(
                relative,
                data,
                mode,
                self._expected,
                self._transaction_id,
                self._mark_destructive,
                self._on_quarantined,
            )
        except PayloadError as error:
            raise ManagerError("STALE_PLAN", str(error)) from error

    def remove_file(self, relative: str) -> None:
        """Remove one approved regular file without following links."""

        relative = self._require_allowed(relative, frozenset({"remove"}))
        self._begin_mutation()
        try:
            self._filesystem.remove(
                relative, self._expected, self._mark_destructive, self._on_quarantined
            )
        except PayloadError as error:
            raise ManagerError("STALE_PLAN", str(error)) from error

    def make_directory(self, relative: str, mode: int = 0o755) -> None:
        """Create one approved directory and apply its logical mode."""

        relative = self._require_allowed(relative, frozenset({"create"}))
        if (
            relative in {".codex", ".codex/codex-game-studios"}
            and self._expected.entry_type == "missing"
            and self._filesystem.observe(relative).entry_type == "directory"
        ):
            return
        self._begin_mutation()
        try:
            self._filesystem.create_directory_exclusive(
                relative, mode, self._mark_destructive
            )
        except PayloadError as error:
            raise ManagerError("STALE_PLAN", str(error)) from error

    def remove_empty_directory(self, relative: str) -> None:
        """Remove one approved directory only when it is empty."""

        relative = self._require_allowed(relative, frozenset({"remove"}))
        expected = self._expected
        if self._action.detail == "conditionally remove empty managed directory":
            expected = self._filesystem.observe(relative)
            if (
                self._expected.entry_type != "directory"
                or expected.entry_type != "directory"
                or self._filesystem.list_immediate(relative)
            ):
                raise ManagerError(
                    "STALE_PLAN", "conditional directory removal target is not empty"
                )
        else:
            self._begin_mutation()
        try:
            self._filesystem.remove(
                relative, expected, self._mark_destructive, self._on_quarantined
            )
        except PayloadError as error:
            raise ManagerError("STALE_PLAN", str(error)) from error

    def remove_state_file(self, relative: str) -> None:
        """Remove one post-validation state file whose approved result is missing."""

        relative = self._require_allowed(relative, frozenset({"state-write"}))
        if (
            self._expected.entry_type != "file"
            or self._expected_result.entry_type != "missing"
        ):
            raise ManagerError(
                "UNSAFE_PATH", "state removal requires approved file-to-missing transition"
            )
        self._begin_mutation()
        try:
            self._filesystem.remove(
                relative, self._expected, self._mark_destructive, self._on_quarantined
            )
        except PayloadError as error:
            raise ManagerError("STALE_PLAN", str(error)) from error


def _fsync_parent(parent_descriptor: int | None) -> None:
    if parent_descriptor is None or os.name == "nt":
        return
    try:
        os.fsync(parent_descriptor)
    except OSError as error:
        if error.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EBADF}:
            raise


def _snapshot_paths(plan: OperationPlan) -> tuple[str, ...]:
    paths: set[str] = set()
    for action in plan.actions:
        if action.kind not in _CHANGING_ACTIONS:
            continue
        normalized = normalize_relative_path(action.path)
        if normalized.startswith(f"{RECOVERY_RELATIVE_PATH}/") or normalized in {
            RECOVERY_RELATIVE_PATH,
            LOCK_RELATIVE_PATH,
        }:
            raise ManagerError("UNSAFE_PATH", "operation plan targets transaction control data")
        paths.add(normalized)
    return tuple(sorted(paths, key=lambda path: (len(PurePosixPath(path).parts), path)))


@dataclasses.dataclass(frozen=True)
class _AcquiredSnapshot:
    record: SnapshotRecord
    state: SecureEntry
    content: bytes | None


def _logical_plan_state(filesystem: AnchoredFilesystem, relative: str) -> SecureEntry:
    """Project only the exact retained lock and its transaction-created ancestors."""

    observed = filesystem.observe(relative)
    control = ".codex/codex-game-studios"
    if relative == control and observed.entry_type == "directory":
        entries = filesystem.list_immediate(relative)
        projected = tuple(
            item
            for item in entries
            if not (item.name == "manager.lock" and item.entry_type == "file")
        )
        if not projected:
            return SecureEntry("missing", None, None, None)
        documents = [dataclasses.asdict(item) for item in projected]
        for item in documents:
            if item["name"] == "recovery" and item["entry_type"] == "directory":
                item["sha256"] = filesystem.recovery_tree_digest(
                    f"{control}/recovery"
                )
        return dataclasses.replace(
            observed, digest=digest_document({"entries": documents})
        )
    if relative == ".codex" and observed.entry_type == "directory":
        entries = filesystem.list_immediate(relative)
        if (
            len(entries) == 1
            and entries[0].name == "codex-game-studios"
            and entries[0].entry_type == "directory"
        ):
            if _logical_plan_state(filesystem, control).entry_type == "missing":
                return SecureEntry("missing", None, None, None)
    return observed


def _action_expected_state(action: Action, observed: SecureEntry) -> SecureEntry:
    if action.kind in {"create", "state-write"} and action.before_hash is None:
        if observed.entry_type != "missing":
            raise ManagerError("STALE_PLAN", "approved create target is no longer absent")
        return observed
    if action.before_hash != observed.digest:
        raise ManagerError("STALE_PLAN", "approved action pre-state digest changed")
    if observed.entry_type == "missing":
        raise ManagerError("STALE_PLAN", "approved action target disappeared")
    return observed


def _acquire_snapshot_set(
    filesystem: AnchoredFilesystem,
    plan: OperationPlan,
) -> tuple[_AcquiredSnapshot, ...]:
    """Read and stabilize all changing paths without creating recovery files."""

    actions = {
        action.path: action
        for action in plan.actions
        if action.kind in _CHANGING_ACTIONS
    }
    if len(actions) != sum(action.kind in _CHANGING_ACTIONS for action in plan.actions):
        raise ManagerError("UNSAFE_PATH", "changing action paths must be unique")
    if len({path.casefold() for path in actions}) != len(actions):
        raise ManagerError("UNSAFE_PATH", "changing action paths have case aliases")
    approved_observations = {item.path: item for item in plan.target_observations}
    acquired: list[_AcquiredSnapshot] = []
    for relative in _snapshot_paths(plan):
        state = _logical_plan_state(filesystem, relative)
        action = actions.get(relative)
        if action is not None:
            _action_expected_state(action, state)
        approved = approved_observations[relative]
        if (
            state.entry_type != approved.entry_type
            or state.mode != approved.mode
            or state.digest != approved.digest
        ):
            raise ManagerError("STALE_PLAN", "snapshot state differs from approved observation")
        content = None
        if state.entry_type == "file":
            content = filesystem.read_file(relative, state)
            if hashlib.sha256(content).hexdigest() != state.digest:
                raise ManagerError("STALE_PLAN", "snapshot bytes changed during acquisition")
        record = SnapshotRecord(
            relative,
            state.entry_type,
            state.mode,
            state.digest if state.entry_type in {"file", "directory"} else None,
            None,
        )
        acquired.append(_AcquiredSnapshot(record, state, content))
    return tuple(acquired)


def _persist_snapshot_set(
    filesystem: AnchoredFilesystem,
    generation: str,
    acquired: tuple[_AcquiredSnapshot, ...],
    transaction_id: str,
) -> tuple[_AcquiredSnapshot, ...]:
    recovery = RECOVERY_RELATIVE_PATH
    recovery_created = False
    generation_created = False
    snapshots_created = False
    quarantine_created = False
    created_files: list[tuple[str, SecureEntry]] = []
    snapshots_directory = f"{generation}/snapshots"
    quarantine_directory = f"{generation}/quarantine"
    persisted: list[_AcquiredSnapshot] = []
    try:
        if filesystem.observe(recovery).entry_type == "missing":
            filesystem.create_directory_exclusive(recovery, 0o700)
            recovery_created = True
        filesystem.create_directory_exclusive(generation, 0o700)
        generation_created = True
        if not filesystem.same_filesystem(generation):
            raise ManagerError(
                "UNSAFE_PATH", "recovery generation is not on repository filesystem"
            )
        filesystem.create_directory_exclusive(snapshots_directory, 0o700)
        snapshots_created = True
        filesystem.create_directory_exclusive(quarantine_directory, 0o700)
        quarantine_created = True
        filesystem.set_quarantine(quarantine_directory)
        for index, item in enumerate(acquired):
            if item.content is None:
                persisted.append(item)
                continue
            snapshot_path = f"{snapshots_directory}/{index:06d}.bin"
            created = filesystem.atomic_replace(
                snapshot_path,
                item.content,
                0o600,
                SecureEntry("missing", None, None, None),
                transaction_id,
            )
            created_files.append((snapshot_path, created))
            persisted.append(
                dataclasses.replace(
                    item,
                    record=dataclasses.replace(item.record, snapshot_path=snapshot_path),
                )
            )
        return tuple(persisted)
    except BaseException as setup_error:
        try:
            expected_snapshot_names = tuple(
                PurePosixPath(path).name for path, _expected in created_files
            )
            if snapshots_created and tuple(
                item.name for item in filesystem.list_immediate(snapshots_directory)
            ) != expected_snapshot_names:
                raise ManagerError("ROLLBACK_FAILED", "snapshot setup contains unknown data")
            if generation_created and tuple(
                item.name for item in filesystem.list_immediate(generation)
            ) != (
                tuple(
                    sorted(
                        name
                        for name, created in (
                            ("snapshots", snapshots_created),
                            ("quarantine", quarantine_created),
                        )
                        if created
                    )
                )
            ):
                raise ManagerError("ROLLBACK_FAILED", "recovery generation contains unknown data")
            if recovery_created and tuple(
                item.name for item in filesystem.list_immediate(recovery)
            ) != (
                (PurePosixPath(generation).name,) if generation_created else ()
            ):
                raise ManagerError("ROLLBACK_FAILED", "recovery root contains unknown data")
            for path, expected in reversed(created_files):
                filesystem.remove_internal_exact(path, expected, generation)
            if quarantine_created:
                filesystem.remove_internal_exact(
                    quarantine_directory,
                    filesystem.observe(quarantine_directory),
                    generation,
                )
            if snapshots_created:
                filesystem.remove_internal_exact(
                    snapshots_directory, filesystem.observe(snapshots_directory), generation
                )
            if generation_created:
                filesystem.remove_internal_exact(
                    generation, filesystem.observe(generation), generation
                )
            if recovery_created:
                filesystem.remove_internal_exact(
                    recovery, filesystem.observe(recovery), generation
                )
        except BaseException as cleanup_error:
            raise ManagerError(
                "ROLLBACK_FAILED",
                "partial recovery setup could not be proven safe to clean",
            ) from cleanup_error
        raise setup_error


def _write_journal_anchored(
    filesystem: AnchoredFilesystem,
    relative: str,
    journal: RecoveryJournal,
) -> RecoveryJournal:
    journal = journal.checksummed()
    filesystem.atomic_replace_internal(
        relative,
        journal.encoded(),
        0o600,
        journal.transaction_id,
    )
    parsed = RecoveryJournal._parse(filesystem.read_file(relative))
    if parsed != journal:
        raise ManagerError("INVALID_INSTALLATION_STATE", "durable journal verification failed")
    return journal


def _quarantine_authority_records(
    generation: str, actions: tuple[Action, ...], plan: OperationPlan
) -> tuple[QuarantineRecord, ...]:
    observations = {item.path: item for item in plan.target_observations}
    results = {item.path: item for item in plan.target_results}
    records: list[QuarantineRecord] = []
    for action in actions:
        path_digest = hashlib.sha256(action.path.encode("utf-8")).hexdigest()[:16]
        before = observations[action.path]
        after = results[action.path]
        if before.entry_type != "missing":
            storage_role = (
                "removed"
                if action.kind == "remove" or after.entry_type == "missing"
                else "before"
            )
            quarantine_digest = before.digest or ""
            if action.detail == "conditionally remove empty managed directory":
                quarantine_digest = hashlib.sha256(b'{"entries":[]}\n').hexdigest()
            records.append(
                QuarantineRecord(
                    f"{generation}/quarantine/{storage_role}-{path_digest}-0000",
                    action.path,
                    "approved-before",
                    before.entry_type,
                    before.mode or 0,
                    quarantine_digest,
                )
            )
        if after.entry_type != "missing":
            if before.entry_type == "missing":
                storage_role, index = "removed", 0
            else:
                storage_role, index = "before", 1
            records.append(
                QuarantineRecord(
                    f"{generation}/quarantine/{storage_role}-{path_digest}-{index:04d}",
                    action.path,
                    "rollback-after",
                    after.entry_type,
                    after.mode or 0,
                    after.digest or "",
                )
            )
    return tuple(sorted(records, key=lambda item: item.path))


def _write_authority_anchored(
    filesystem: AnchoredFilesystem,
    relative: str,
    authority: RecoveryAuthority,
) -> RecoveryAuthority:
    authority = authority.checksummed()
    if filesystem.observe(relative).entry_type != "missing":
        raise ManagerError("UNSAFE_PATH", "recovery authority path is occupied")
    filesystem.atomic_replace(
        relative,
        authority.encoded(),
        0o600,
        SecureEntry("missing", None, None, None),
        authority.transaction_id,
    )
    if filesystem.read_file(relative) != authority.encoded():
        raise ManagerError("INVALID_INSTALLATION_STATE", "durable authority verification failed")
    return authority


def _verify_action_result_anchored(
    filesystem: AnchoredFilesystem, action: Action, approved: object
) -> SecureEntry:
    observed = _logical_plan_state(filesystem, action.path)
    if (
        action.kind == "create"
        and action.path in {".codex", ".codex/codex-game-studios"}
        and approved.entry_type == "directory"
        and filesystem.observe(action.path).entry_type == "directory"
    ):
        return approved
    if (
        observed.entry_type != approved.entry_type
        or observed.mode != approved.mode
        or observed.digest != approved.digest
    ):
        raise ManagerError("VALIDATION_FAILED", "action result differs from approved digest")
    return observed


def _failed_mutation_rollback_guard(
    filesystem: AnchoredFilesystem,
    action: Action,
    original: SecureEntry,
) -> SecureEntry | None:
    """Choose a rollback precondition without authorizing raced-in content."""

    current = filesystem.observe(action.path)
    if filesystem.matches(current, original):
        return None
    if current.entry_type == "missing":
        return current
    if action.after_hash is not None and current.digest == action.after_hash:
        return current
    if action.after_hash is None and action.kind == "create" and current.entry_type == "directory":
        return current
    # Returning the original identity intentionally makes rollback fail closed
    # rather than overwriting an unrecognized concurrent inode.
    return original


def _restore_acquired_snapshot(
    filesystem: AnchoredFilesystem,
    acquired: _AcquiredSnapshot,
    current_expected: SecureEntry,
    transaction_id: str,
) -> None:
    record = acquired.record
    if record.entry_type == "missing":
        if current_expected.entry_type != "missing":
            filesystem.remove(record.path, current_expected)
        return
    if record.entry_type == "file":
        if record.snapshot_path is None:
            raise ManagerError("ROLLBACK_FAILED", "file snapshot storage is missing")
        try:
            content = filesystem.read_file_verified(
                record.snapshot_path,
                expected_digest=record.sha256 or "",
                expected_mode=0o600,
            )
        except PayloadError as error:
            raise ManagerError("ROLLBACK_FAILED", "recovery snapshot changed before restore") from error
        filesystem.atomic_replace(
            record.path,
            content,
            record.mode or 0o600,
            current_expected,
            transaction_id,
        )
        return
    if current_expected.entry_type == "missing":
        filesystem.create_directory_exclusive(record.path, record.mode or 0o755)
    elif current_expected.entry_type != "directory":
        filesystem.remove(record.path, current_expected)
        filesystem.create_directory_exclusive(record.path, record.mode or 0o755)


def _verify_recovery_snapshots(
    filesystem: AnchoredFilesystem,
    acquired: tuple[_AcquiredSnapshot, ...],
) -> None:
    for item in acquired:
        if item.record.snapshot_path is None:
            continue
        stored = filesystem.read_file(item.record.snapshot_path)
        if hashlib.sha256(stored).hexdigest() != item.record.sha256:
            raise ManagerError("ROLLBACK_FAILED", "recovery snapshot checksum mismatch")


def _verify_complete_generation(
    filesystem: AnchoredFilesystem,
    authority: RecoveryAuthority,
    journal_path: str,
    journal: RecoveryJournal,
    *,
    rollback_complete: bool = False,
) -> None:
    """Verify authority, snapshots, and exact generation inventory."""

    generation = str(PurePosixPath(journal_path).parent)
    authority_path = f"{generation}/authority.json"
    if filesystem.read_file(authority_path) != authority.encoded():
        raise ManagerError("ROLLBACK_FAILED", "recovery authority bytes changed")
    snapshot_names = tuple(
        sorted(
            PurePosixPath(record.snapshot_path).name
            for record in authority.snapshots
            if record.snapshot_path is not None
        )
    )
    actual_snapshots = filesystem.list_immediate(f"{generation}/snapshots")
    if tuple(item.name for item in actual_snapshots) != snapshot_names or any(
        item.entry_type != "file" for item in actual_snapshots
    ):
        raise ManagerError("ROLLBACK_FAILED", "snapshot inventory changed")
    for record in authority.snapshots:
        if record.entry_type == "file":
            if record.snapshot_path is None:
                raise ManagerError("ROLLBACK_FAILED", "file snapshot authority is incomplete")
            observed = filesystem.observe(record.snapshot_path)
            if (
                observed.entry_type != "file"
                or observed.digest != record.sha256
                or observed.mode != 0o600
            ):
                raise ManagerError("ROLLBACK_FAILED", "snapshot authority verification failed")
        elif record.snapshot_path is not None:
            raise ManagerError("ROLLBACK_FAILED", "non-file snapshot has storage bytes")
    executed = {
        action.path for action in authority.changing_actions[: journal.execution_index]
    }
    forward_paths = set(executed)
    actual_quarantine = filesystem.list_immediate(f"{generation}/quarantine")
    actual_names = tuple(item.name for item in actual_quarantine)
    active_before = next(
        (
            record
            for record in authority.quarantine_records
            if record.action_path == journal.active_action
            and record.role == "approved-before"
        ),
        None,
    )
    transition_moved = (
        journal.phase == "action-started"
        and not journal.active_quarantined
        and active_before is not None
        and PurePosixPath(active_before.path).name in actual_names
    )
    if journal.active_action is not None and (
        journal.active_quarantined or transition_moved
    ):
        forward_paths.add(journal.active_action)
    expected_quarantine = tuple(
        record
        for record in authority.quarantine_records
        if record.action_path in forward_paths
        and (
            record.role == "approved-before"
            or (
                record.action_path in executed
                and record.role == "rollback-after"
                and (journal.phase == "rolled-back" or rollback_complete)
                and not (
                    record.action_path in {".codex", ".codex/codex-game-studios"}
                    and next(
                        item for item in authority.snapshots
                        if item.path == record.action_path
                    ).entry_type == "missing"
                )
            )
        )
    )
    if actual_names != tuple(
        PurePosixPath(record.path).name for record in expected_quarantine
    ):
        raise ManagerError("ROLLBACK_FAILED", "quarantine inventory does not match journal phase")
    for record in expected_quarantine:
        observed = filesystem.observe(record.path)
        if (
            observed.entry_type != record.entry_type
            or observed.mode != record.mode
            or observed.digest != record.sha256
        ):
            raise ManagerError("ROLLBACK_FAILED", "quarantine content does not match authority")
    if journal.phase == "action-started" and journal.active_action is not None:
        target = filesystem.observe(journal.active_action)
        before = next(item for item in authority.snapshots if item.path == journal.active_action)
        if not journal.active_quarantined:
            if transition_moved:
                if target.entry_type != "missing":
                    raise ManagerError("ROLLBACK_FAILED", "pre-marker quarantine transition is ambiguous")
            elif (
                target.entry_type != before.entry_type
                or target.mode != before.mode
                or target.digest != before.sha256
            ):
                raise ManagerError(
                    "ROLLBACK_FAILED",
                    "pre-marker quarantine target state is unauthorized",
                )
        else:
            after = next(
                (
                    record
                    for record in authority.quarantine_records
                    if record.action_path == journal.active_action
                    and record.role == "rollback-after"
                ),
                None,
            )
            authorized_after = after is not None and (
                target.entry_type == after.entry_type
                and target.mode == after.mode
                and target.digest == after.sha256
            )
            authorized_restored = rollback_complete and (
                target.entry_type == before.entry_type
                and target.mode == before.mode
                and target.digest == before.sha256
            )
            if target.entry_type != "missing" and not authorized_after and not authorized_restored:
                raise ManagerError(
                    "ROLLBACK_FAILED",
                    "post-marker quarantine target state is unauthorized",
                )
    generation_entries = filesystem.list_immediate(generation)
    if tuple(item.name for item in generation_entries) != (
        "authority.json",
        "journal.json",
        "quarantine",
        "snapshots",
    ):
        raise ManagerError("ROLLBACK_FAILED", "recovery generation inventory changed")


@dataclasses.dataclass(frozen=True)
class _ControlScaffold:
    codex: tuple[tuple[str, str, int | None, str | None, object | None], ...]
    control: tuple[tuple[str, str, int | None, str | None, object | None], ...]
    prior_recovery: tuple[tuple[str, str], ...]
    recovery_existed: bool


def _capture_control_scaffold(filesystem: AnchoredFilesystem) -> _ControlScaffold:
    def entries(
        relative: str,
    ) -> tuple[tuple[str, str, int | None, str | None, object | None], ...]:
        if filesystem.observe(relative).entry_type == "missing":
            return ()
        captured = []
        for item in filesystem.list_immediate(relative):
            internal_placeholder = (
                relative == ".codex" and item.name == "codex-game-studios"
            ) or (
                relative == ".codex/codex-game-studios"
                and item.name in {"manager.lock", "recovery"}
            )
            if internal_placeholder:
                captured.append((item.name, item.entry_type, None, None, None))
                continue
            observed = filesystem.observe(f"{relative}/{item.name}")
            digest = observed.digest
            identity: object | None = observed.identity
            if observed.entry_type == "directory":
                digest, identity = filesystem.tree_digest_and_identities(
                    f"{relative}/{item.name}", observed
                )
            captured.append((item.name, item.entry_type, observed.mode, digest, identity))
        return tuple(captured)

    recovery_existed = filesystem.observe(RECOVERY_RELATIVE_PATH).entry_type == "directory"
    prior = ()
    if recovery_existed:
        prior = tuple(
            (item.name, filesystem.recovery_tree_digest(f"{RECOVERY_RELATIVE_PATH}/{item.name}"))
            for item in filesystem.list_immediate(RECOVERY_RELATIVE_PATH)
            if item.entry_type == "directory"
        )
        if len(prior) != len(filesystem.list_immediate(RECOVERY_RELATIVE_PATH)):
            raise ManagerError("STALE_PLAN", "approved recovery inventory has a non-directory")
    return _ControlScaffold(
        entries(".codex"),
        entries(".codex/codex-game-studios"),
        prior,
        recovery_existed,
    )


def _verify_control_scaffold(
    filesystem: AnchoredFilesystem,
    approved: _ControlScaffold,
    generation: str,
) -> None:
    current = _capture_control_scaffold(filesystem)
    if current.codex != approved.codex:
        raise ManagerError("STALE_PLAN", "approved .codex scaffold changed")
    expected_control = approved.control
    if not approved.recovery_existed:
        expected_control = tuple(
            sorted((*expected_control, ("recovery", "directory", None, None, None)))
        )
    if current.control != expected_control:
        raise ManagerError("STALE_PLAN", "approved manager scaffold changed")
    current_name = PurePosixPath(generation).name
    current_prior = tuple(item for item in current.prior_recovery if item[0] != current_name)
    if current_prior != approved.prior_recovery:
        raise ManagerError("STALE_PLAN", "approved prior recovery inventory changed")
    recovery_names = tuple(item.name for item in filesystem.list_immediate(RECOVERY_RELATIVE_PATH))
    if recovery_names != tuple(sorted((*[item[0] for item in approved.prior_recovery], current_name))):
        raise ManagerError("STALE_PLAN", "recovery scaffold has an unknown generation")


def _validate_journal_phase(
    authority: RecoveryAuthority, journal: RecoveryJournal
) -> None:
    """Enforce the exact applied-prefix relationship for every journal phase."""

    ordinary = tuple(
        action for action in authority.changing_actions if action.kind != "state-write"
    )
    state = tuple(
        action for action in authority.changing_actions if action.kind == "state-write"
    )
    executed = authority.changing_actions[: journal.execution_index]
    expected_applied = tuple(sorted(action.path for action in executed))
    if journal.execution_index > len(authority.changing_actions) or journal.applied_paths != expected_applied:
        raise ManagerError("INVALID_INSTALLATION_STATE", "journal execution prefix is invalid")
    if journal.active_action is None and journal.active_quarantined:
        raise ManagerError("INVALID_INSTALLATION_STATE", "journal quarantine marker has no active action")
    if journal.phase in {"snapshot-created", "journal-written"}:
        valid = journal.execution_index == 0 and journal.active_action is None
    elif journal.phase == "action-started":
        valid = (
            journal.execution_index < len(authority.changing_actions)
            and journal.active_action
            == authority.changing_actions[journal.execution_index].path
        )
    elif journal.phase == "action-applied":
        valid = 0 < journal.execution_index <= len(ordinary) and journal.active_action is None
    elif journal.phase == "validation-started":
        valid = journal.execution_index == len(ordinary) and journal.active_action is None
    elif journal.phase == "state-written":
        valid = len(state) == 1 and journal.execution_index == len(authority.changing_actions) and journal.active_action is None
    elif journal.phase == "committed":
        valid = journal.execution_index == len(authority.changing_actions) and journal.active_action is None
    else:
        valid = 0 <= journal.execution_index <= len(authority.changing_actions)
    if not valid:
        raise ManagerError("INVALID_INSTALLATION_STATE", "journal phase history is invalid")


def apply_transaction(
    plan: OperationPlan,
    root: Path | str,
    replan: Callable[[], OperationPlan],
    apply_action: Callable[..., object],
    validate: Callable[[Path], Iterable[object]],
    *,
    persist_state: Callable[[Action, AtomicMutation], object] | None = None,
    failpoint: Callable[[str], None] | None = None,
    lock_timeout: float = 5.0,
    transaction_id: str | None = None,
) -> TransactionResult:
    """Apply one approved plan atomically or restore its exact logical state."""

    try:
        validate_operation_plan_digest(plan)
    except PayloadError as error:
        raise ManagerError("STALE_PLAN", str(error)) from error
    if plan.conflicts:
        conflict = plan.conflicts[0]
        raise ManagerError(conflict.code, "approved plan contains an unresolved conflict")
    if plan.operation == "verify":
        raise ManagerError("UNSUPPORTED_ENVIRONMENT", "verify operations are read-only")
    target_root = Path(root)
    trigger = failpoint if failpoint is not None else lambda _phase: None
    if transaction_id is None:
        transaction_id = str(uuid.uuid4())
    else:
        try:
            parsed_transaction_id = uuid.UUID(transaction_id)
        except (AttributeError, TypeError, ValueError) as error:
            raise ManagerError("STALE_PLAN", "approved transaction identifier is malformed") from error
        if str(parsed_transaction_id) != transaction_id or parsed_transaction_id.version != 4:
            raise ManagerError("STALE_PLAN", "approved transaction identifier is malformed")
    generation = f"{RECOVERY_RELATIVE_PATH}/{transaction_id}"
    journal_path = f"{generation}/journal.json"
    state_actions = tuple(action for action in plan.actions if action.kind == "state-write")
    if len(state_actions) > 1:
        raise ManagerError("UNSAFE_PATH", "operation plan contains multiple state writes")
    if state_actions and persist_state is None:
        raise ManagerError("UNSUPPORTED_ENVIRONMENT", "state-write action requires persistence callback")
    journal: RecoveryJournal | None = None

    with RepositoryLock(target_root, timeout=lock_timeout) as repository_lock:
        filesystem = AnchoredFilesystem(repository_lock.pinned, repository_lock.verify)
        repository_lock.verify()
        replanned = replan()
        if replanned != plan or replanned.digest != plan.digest:
            raise ManagerError("STALE_PLAN", "repository changed after plan approval")
        try:
            acquired = _acquire_snapshot_set(filesystem, plan)
        except PayloadError as error:
            raise ManagerError("UNSAFE_PATH", str(error)) from error
        repository_lock.verify()
        after_snapshots = replan()
        if after_snapshots != plan or after_snapshots.digest != plan.digest:
            raise ManagerError("STALE_PLAN", "repository changed during snapshot acquisition")
        approved_scaffold = _capture_control_scaffold(filesystem)
        if filesystem.observe(generation).entry_type != "missing":
            raise ManagerError(
                "STALE_PLAN", "approved transaction recovery generation already exists"
            )
        persisted = _persist_snapshot_set(filesystem, generation, acquired, transaction_id)
        snapshots = tuple(item.record for item in persisted)
        changing_actions = tuple(
            action
            for action in plan.actions
            if action.kind in _CHANGING_ACTIONS and action.kind != "state-write"
        ) + state_actions
        authority_path = f"{generation}/authority.json"
        authority = _write_authority_anchored(
            filesystem,
            authority_path,
            RecoveryAuthority(
                JOURNAL_SCHEMA_VERSION,
                transaction_id,
                secure_root_identity(repository_lock.pinned),
                plan.digest,
                changing_actions,
                snapshots,
                _quarantine_authority_records(generation, changing_actions, plan),
                "",
            ),
        )
        journal = RecoveryJournal(
            JOURNAL_SCHEMA_VERSION,
            transaction_id,
            secure_root_identity(repository_lock.pinned),
            plan.digest,
            authority.checksum,
            "snapshot-created",
            0,
            None,
            False,
            snapshots,
            (),
            "",
        )
        journal = _write_journal_anchored(filesystem, journal_path, journal)
        expected_by_path = {item.record.path: item.state for item in persisted}
        approved_results = {item.path: item for item in plan.target_results}
        touched: list[tuple[str, SecureEntry]] = []
        try:
            repository_lock.verify()
            trigger("snapshot-created")
            journal = _write_journal_anchored(
                filesystem,
                journal_path,
                dataclasses.replace(journal, phase="journal-written", checksum=""),
            )
            trigger("journal-written")
            _verify_control_scaffold(filesystem, approved_scaffold, generation)
            ordinary_actions = tuple(
                action for action in plan.actions if action.kind != "state-write"
            )
            for action in ordinary_actions:
                repository_lock.verify()
                expected = expected_by_path.get(
                    action.path, _logical_plan_state(filesystem, action.path)
                )
                internal_scaffold_create = (
                    action.kind == "create"
                    and action.path in {".codex", ".codex/codex-game-studios"}
                    and expected.entry_type == "missing"
                    and filesystem.observe(action.path).entry_type == "directory"
                )
                conditional_empty_directory = (
                    action.kind == "remove"
                    and action.detail == "conditionally remove empty managed directory"
                    and expected.entry_type == "directory"
                    and filesystem.observe(action.path).entry_type == "directory"
                    and not filesystem.list_immediate(action.path)
                )
                if action.kind in _CHANGING_ACTIONS and not internal_scaffold_create and not conditional_empty_directory and not filesystem.matches(
                    _logical_plan_state(filesystem, action.path), expected
                ):
                    raise ManagerError("STALE_PLAN", "action target changed before durable start")
                if action.kind in _CHANGING_ACTIONS:
                    journal = _write_journal_anchored(
                        filesystem,
                        journal_path,
                        dataclasses.replace(
                            journal,
                            phase="action-started",
                            active_action=action.path,
                            active_quarantined=False,
                            checksum="",
                        ),
                    )
                def mark_active_quarantined() -> None:
                    nonlocal journal
                    journal = _write_journal_anchored(
                        filesystem,
                        journal_path,
                        dataclasses.replace(
                            journal, active_quarantined=True, checksum=""
                        ),
                    )

                capability = AtomicMutation(
                    filesystem,
                    action,
                    expected,
                    approved_results.get(action.path, expected),
                    transaction_id,
                    mark_active_quarantined,
                )
                try:
                    try:
                        apply_action(action, capability)
                    except BaseException:
                        if capability.did_mutate:
                            guard = _failed_mutation_rollback_guard(
                                filesystem, action, expected
                            )
                            if guard is not None:
                                touched.append((action.path, guard))
                        raise
                finally:
                    capability.revoke()
                if action.kind in _CHANGING_ACTIONS:
                    after = _verify_action_result_anchored(
                        filesystem, action, approved_results[action.path]
                    )
                    if capability.did_mutate:
                        touched.append((action.path, after))
                if action.kind in _CHANGING_ACTIONS:
                    journal = _write_journal_anchored(
                        filesystem,
                        journal_path,
                        dataclasses.replace(
                            journal,
                            phase="action-applied",
                            execution_index=journal.execution_index + 1,
                            active_action=None,
                            active_quarantined=False,
                            applied_paths=tuple(
                                sorted({*journal.applied_paths, action.path})
                            ),
                            checksum="",
                        ),
                    )
                    trigger("action-applied")
            repository_lock.verify()
            _verify_complete_generation(filesystem, authority, journal_path, journal)
            journal = _write_journal_anchored(
                filesystem,
                journal_path,
                dataclasses.replace(journal, phase="validation-started", checksum=""),
            )
            trigger("validation-started")
            try:
                findings = tuple(validate(target_root))
            except ManagerError:
                raise
            except BaseException as error:
                raise ManagerError(
                    "VALIDATION_FAILED", "installed-mode validation could not complete"
                ) from error
            repository_lock.verify()
            if findings:
                raise ManagerError("VALIDATION_FAILED", "installed-mode validation reported findings")
            if state_actions:
                state_action = state_actions[0]
                journal = _write_journal_anchored(
                    filesystem,
                    journal_path,
                    dataclasses.replace(
                        journal,
                        phase="action-started",
                        active_action=state_action.path,
                        active_quarantined=False,
                        checksum="",
                    ),
                )
                expected = expected_by_path[state_action.path]
                def mark_state_quarantined() -> None:
                    nonlocal journal
                    journal = _write_journal_anchored(
                        filesystem,
                        journal_path,
                        dataclasses.replace(
                            journal, active_quarantined=True, checksum=""
                        ),
                    )

                capability = AtomicMutation(
                    filesystem,
                    state_action,
                    expected,
                    approved_results[state_action.path],
                    transaction_id,
                    mark_state_quarantined,
                )
                try:
                    try:
                        assert persist_state is not None
                        persist_state(state_action, capability)
                    except BaseException:
                        if capability.did_mutate:
                            guard = _failed_mutation_rollback_guard(
                                filesystem, state_action, expected
                            )
                            if guard is not None:
                                touched.append((state_action.path, guard))
                        raise
                finally:
                    capability.revoke()
                after = _verify_action_result_anchored(
                    filesystem, state_action, approved_results[state_action.path]
                )
                if capability.did_mutate:
                    touched.append((state_action.path, after))
                journal = _write_journal_anchored(
                    filesystem,
                    journal_path,
                    dataclasses.replace(
                        journal,
                        phase="state-written",
                        execution_index=journal.execution_index + 1,
                        active_action=None,
                        active_quarantined=False,
                        applied_paths=tuple(
                            sorted({*journal.applied_paths, state_action.path})
                        ),
                        checksum="",
                    ),
                )
                trigger("state-written")
            repository_lock.verify()
            _verify_complete_generation(filesystem, authority, journal_path, journal)
            journal = _write_journal_anchored(
                filesystem,
                journal_path,
                dataclasses.replace(journal, phase="committed", checksum=""),
            )
            trigger("journal-committed")
            repository_lock.verify()
            return TransactionResult(transaction_id, "committed", len(plan.actions))
        except BaseException as original_error:
            try:
                _verify_complete_generation(filesystem, authority, journal_path, journal)
                if (
                    journal.phase == "action-started"
                    and journal.active_action is not None
                    and not journal.active_quarantined
                ):
                    active_record = next(
                        (
                            record
                            for record in authority.quarantine_records
                            if record.action_path == journal.active_action
                            and record.role == "approved-before"
                        ),
                        None,
                    )
                    if (
                        active_record is not None
                        and filesystem.observe(active_record.path).entry_type != "missing"
                    ):
                        journal = _write_journal_anchored(
                            filesystem,
                            journal_path,
                            dataclasses.replace(
                                journal, active_quarantined=True, checksum=""
                            ),
                        )
                trigger("before-restore-read")
                acquired_by_path = {item.record.path: item for item in persisted}
                for path, expected_after in reversed(touched):
                    _restore_acquired_snapshot(
                        filesystem,
                        acquired_by_path[path],
                        expected_after,
                        transaction_id,
                    )
                for path, _expected_after in touched:
                    original = acquired_by_path[path].state
                    restored = filesystem.observe(path)
                    logical_original = dataclasses.replace(original, identity=None)
                    if not filesystem.matches(restored, logical_original):
                        raise ManagerError(
                            "ROLLBACK_FAILED", "rollback target verification failed"
                        )
                _verify_recovery_snapshots(filesystem, persisted)
                _verify_complete_generation(
                    filesystem, authority, journal_path, journal, rollback_complete=True
                )
                journal = _write_journal_anchored(
                    filesystem,
                    journal_path,
                    dataclasses.replace(journal, phase="rolled-back", checksum=""),
                )
            except BaseException as rollback_error:
                recovery: dict[str, str] | None = None
                try:
                    _verify_recovery_snapshots(filesystem, persisted)
                    try:
                        _verify_complete_generation(
                            filesystem, authority, journal_path, journal
                        )
                    except ManagerError as integrity_error:
                        if "quarantine" not in integrity_error.detail:
                            raise
                    journal = _write_journal_anchored(
                        filesystem,
                        journal_path,
                        dataclasses.replace(journal, phase="ROLLBACK_FAILED", checksum=""),
                    )
                    journal = RecoveryJournal.load(
                        target_root / journal_path,
                        authority=authority,
                        allowed_phases=frozenset({"ROLLBACK_FAILED"}),
                    )
                    recovery = {
                        "generation": generation,
                        "journal": journal_path,
                        "snapshots": f"{generation}/snapshots",
                        "phase": journal.phase,
                        "status": "retained",
                    }
                except BaseException:
                    pass
                raise ManagerError(
                    "ROLLBACK_FAILED",
                    "automatic rollback failed; preserve recovery generation and stop writes",
                    wrote=True,
                    recovery=recovery,
                ) from rollback_error
            if isinstance(original_error, ManagerError):
                original_error.wrote = bool(touched)
                raise original_error
            try:
                original_error.wrote = bool(touched)
            except (AttributeError, TypeError):
                pass
            raise original_error
