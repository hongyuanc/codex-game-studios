"""Read-only, deterministic planning for Codex Game Studios lifecycle operations."""

from __future__ import annotations

import argparse
import base64
import binascii
import dataclasses
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import types
import uuid
from collections.abc import Callable, Mapping, Sequence

from managed_blocks import MergeConflict, merge_block, merge_owned_toml, remove_block
from models import (
    Action,
    Conflict,
    InstallationState,
    ManagedPath,
    OperationPlan,
    PayloadEntry,
    PayloadError,
    PayloadManifest,
    TargetObservation,
    canonical_json,
    digest_document,
    normalize_relative_path,
    plan_with_digest,
)
from payload import load_verified_manifest, verify_manifest_snapshot
from safe_fs import (
    inspect_secure,
    is_reparse_point,
    list_immediate_secure,
    modes_match,
    pin_root,
    read_file_secure,
    recovery_tree_digest_secure,
)


STATE_SCHEMA_VERSION = 1
STATE_RELATIVE_PATH = ".codex/codex-game-studios/installation.json"
OPERATIONS = frozenset({"install", "update", "verify", "repair", "uninstall"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_STATE_KEYS = {
    "schema_version",
    "plugin_version",
    "payload_digest",
    "transaction_id",
    "installed_at",
    "managed_paths",
    "decisions",
    "validator_version",
    "journal_status",
    "checksum",
}
_MANAGED_PATH_KEYS = {"path", "installed_hash", "ownership", "merge", "block_hash"}
_TOML_KEYS = ("agents.max_depth", "agents.max_threads", "features.hooks")
_DECISION_OUTCOMES = {"adopt", "merge"}
_COLLISION_REASONS = {
    "unmanaged-collision",
    "customized-managed-file",
    "historical-remnant",
}
_TRANSACTION_CONTROL_DIRECTORY = ".codex/codex-game-studios"
_TRANSACTION_INTERNAL_CHILD_TYPES = {
    "manager.lock": "file",
}


class ManagerError(ValueError):
    """Raised when planning cannot safely establish its read-only inputs."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        wrote: bool = False,
        recovery: dict[str, str] | None = None,
    ):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.wrote = wrote
        self.recovery = recovery


_EXPECTED_MANAGER_FAILURES = (
    PayloadError,
    MergeConflict,
    UnicodeError,
    tomllib.TOMLDecodeError,
    OSError,
)
_PUBLIC_MANAGER_FAILURES = (ManagerError, *_EXPECTED_MANAGER_FAILURES)


def _manager_error_from_expected(
    error: BaseException,
    *,
    payload_code: str = "INVALID_PAYLOAD",
) -> ManagerError:
    """Translate expected internal failures to stable content-free categories."""

    wrote = bool(getattr(error, "wrote", False))
    if isinstance(error, PayloadError):
        detail = (
            "installation state validation failed"
            if payload_code == "INVALID_INSTALLATION_STATE"
            else "embedded payload validation failed"
        )
        return ManagerError(payload_code, detail, wrote=wrote)
    if isinstance(error, (MergeConflict, UnicodeError, tomllib.TOMLDecodeError)):
        return ManagerError(
            "CUSTOMIZED_MANAGED_FILE", "shared managed content cannot be changed safely",
            wrote=wrote,
        )
    return ManagerError("UNSAFE_PATH", "filesystem operation failed safely", wrote=wrote)


@dataclasses.dataclass(frozen=True)
class ApprovalContext:
    """Opaque public approval metadata that binds runtime state identity."""

    operation: str
    transaction_id: str
    installed_at: str


_APPROVAL_CONTEXT_KEYS = {"schema_version", "operation", "transaction_id", "installed_at"}
_SHELL_SAFE_CONTEXT = re.compile(r"[A-Za-z0-9_-]+\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def new_approval_context(operation: str) -> ApprovalContext:
    """Return fresh path-free metadata for one mutation plan."""

    return ApprovalContext(
        operation,
        str(uuid.uuid4()),
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


def encode_approval_context(context: ApprovalContext) -> str:
    """Encode canonical approval metadata as an unpadded shell-safe token."""

    raw = canonical_json({
        "schema_version": 1,
        "operation": context.operation,
        "transaction_id": context.transaction_id,
        "installed_at": context.installed_at,
    })
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def approval_context_digest(context: ApprovalContext) -> str:
    """Return the exact immutable commitment for one canonical context token."""

    return hashlib.sha256(encode_approval_context(context).encode("ascii")).hexdigest()


def decode_approval_context(token: str, operation: str) -> ApprovalContext:
    """Decode and strictly validate one canonical shell-safe approval token."""

    try:
        if (
            not isinstance(token, str)
            or len(token) > 512
            or not _SHELL_SAFE_CONTEXT.fullmatch(token)
        ):
            raise ValueError
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        document = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or set(document) != _APPROVAL_CONTEXT_KEYS
            or document.get("schema_version") != 1
            or document.get("operation") != operation
            or encode_approval_context(ApprovalContext(
                document["operation"], document["transaction_id"], document["installed_at"]
            )) != token
        ):
            raise ValueError
        parsed_uuid = uuid.UUID(document["transaction_id"])
        if str(parsed_uuid) != document["transaction_id"] or parsed_uuid.version != 4:
            raise ValueError
        installed_at = document["installed_at"]
        if not isinstance(installed_at, str) or not _RFC3339_UTC.fullmatch(installed_at):
            raise ValueError
        datetime.strptime(installed_at, "%Y-%m-%dT%H:%M:%SZ")
    except (
        binascii.Error, KeyError, TypeError, ValueError, UnicodeError,
        json.JSONDecodeError,
    ) as error:
        raise ManagerError("STALE_PLAN", "approval context is malformed or mismatched") from error
    return ApprovalContext(operation, str(parsed_uuid), installed_at)


@dataclasses.dataclass(frozen=True)
class _Observed:
    kind: str
    digest: str | None
    content: bytes | None
    children: tuple[tuple[str, str], ...] = ()
    mode: int | None = None


def _managed_path_document(item: ManagedPath) -> dict[str, object]:
    return {
        "path": item.path,
        "installed_hash": item.installed_hash,
        "ownership": item.ownership,
        "merge": item.merge,
        "block_hash": item.block_hash,
    }


def _state_body(state: InstallationState) -> dict[str, object]:
    return {
        "schema_version": state.schema_version,
        "plugin_version": state.plugin_version,
        "payload_digest": state.payload_digest,
        "transaction_id": state.transaction_id,
        "installed_at": state.installed_at,
        "managed_paths": [_managed_path_document(item) for item in state.managed_paths],
        "decisions": list(state.decisions),
        "validator_version": state.validator_version,
        "journal_status": state.journal_status,
    }


def state_with_checksum(state: InstallationState) -> InstallationState:
    """Return ``state`` with its checksum recomputed from all other fields."""

    return dataclasses.replace(state, checksum=digest_document(_state_body(state)))


def write_state_document(state: InstallationState) -> bytes:
    """Serialize a fully checksummed installation state as canonical JSON."""

    expected = digest_document(_state_body(state))
    if state.checksum != expected:
        raise ManagerError("INVALID_INSTALLATION_STATE", "state checksum is not current")
    document = _state_body(state)
    document["checksum"] = state.checksum
    return canonical_json(document)


def _valid_hash(value: object, *, optional: bool = False) -> bool:
    return (optional and value is None) or (
        isinstance(value, str) and _HASH.fullmatch(value) is not None
    )


def _validate_json_value(value: object) -> bool:
    if value is None or type(value) in {str, int, bool}:
        return True
    if isinstance(value, list):
        return all(_validate_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _validate_json_value(item)
            for key, item in value.items()
        )
    return False


def _parse_decisions(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ManagerError("INVALID_INSTALLATION_STATE", "decisions must be a list")
    decisions: list[dict[str, object]] = []
    for decision in value:
        if not isinstance(decision, dict) or not _validate_json_value(decision):
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed decision")
        kind = decision.get("kind")
        path = decision.get("path")
        if not isinstance(kind, str) or not kind or not isinstance(path, str):
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed decision")
        try:
            normalize_relative_path(path)
        except PayloadError as error:
            raise ManagerError("INVALID_INSTALLATION_STATE", "unsafe decision path") from error
        if kind == "toml-keys":
            if set(decision) != {"kind", "path", "outcome", "owned_values"}:
                raise ManagerError("INVALID_INSTALLATION_STATE", "malformed TOML decision")
            if decision["outcome"] not in _DECISION_OUTCOMES:
                raise ManagerError("INVALID_INSTALLATION_STATE", "malformed TOML decision")
            owned = decision["owned_values"]
            if not isinstance(owned, dict) or set(owned) != set(_TOML_KEYS):
                raise ManagerError("INVALID_INSTALLATION_STATE", "malformed TOML decision")
            for key, item in owned.items():
                expected = bool if key == "features.hooks" else int
                if type(item) is not expected:
                    raise ManagerError("INVALID_INSTALLATION_STATE", "malformed TOML decision")
        elif kind == "managed-block":
            if set(decision) != {"kind", "path", "outcome"} or decision[
                "outcome"
            ] not in _DECISION_OUTCOMES:
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "malformed managed-block decision"
                )
        elif kind == "preserved-collision":
            if set(decision) != {"kind", "path", "reason", "target_hash"}:
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "malformed collision decision"
                )
            if decision["reason"] not in _COLLISION_REASONS or not _valid_hash(
                decision["target_hash"], optional=True
            ):
                raise ManagerError(
                    "INVALID_INSTALLATION_STATE", "malformed collision decision"
                )
        else:
            raise ManagerError("INVALID_INSTALLATION_STATE", "unknown decision kind")
        decisions.append(dict(decision))
    if decisions != sorted(decisions, key=lambda item: canonical_json(item)):
        raise ManagerError("INVALID_INSTALLATION_STATE", "decisions are not sorted")
    decision_documents = [canonical_json(item) for item in decisions]
    if len(decision_documents) != len(set(decision_documents)):
        raise ManagerError("INVALID_INSTALLATION_STATE", "decisions are duplicated")
    decision_paths = [item["path"].casefold() for item in decisions]
    if len(decision_paths) != len(set(decision_paths)):
        raise ManagerError("INVALID_INSTALLATION_STATE", "decision paths collide")
    return tuple(decisions)


def _parse_state(raw: bytes) -> InstallationState:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ManagerError("INVALID_INSTALLATION_STATE", "state is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != _STATE_KEYS:
        raise ManagerError("INVALID_INSTALLATION_STATE", "state fields are missing or extra")
    if type(document["schema_version"]) is not int:
        raise ManagerError("INVALID_INSTALLATION_STATE", "malformed schema version")
    if document["schema_version"] != STATE_SCHEMA_VERSION:
        raise ManagerError("INVALID_INSTALLATION_STATE", "unsupported schema version")
    for key in ("plugin_version", "transaction_id", "installed_at", "validator_version"):
        if not isinstance(document[key], str) or not document[key]:
            raise ManagerError("INVALID_INSTALLATION_STATE", f"malformed {key}")
    if document["journal_status"] not in {"committed", "clean"}:
        raise ManagerError("INVALID_INSTALLATION_STATE", "malformed journal status")
    if not _valid_hash(document["payload_digest"]) or not _valid_hash(document["checksum"]):
        raise ManagerError("INVALID_INSTALLATION_STATE", "malformed checksum or payload digest")
    try:
        transaction_id = uuid.UUID(document["transaction_id"])
        if str(transaction_id) != document["transaction_id"]:
            raise ValueError
        timestamp = document["installed_at"].replace("Z", "+00:00")
        if datetime.fromisoformat(timestamp).tzinfo is None:
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise ManagerError("INVALID_INSTALLATION_STATE", "malformed transaction metadata") from error

    raw_paths = document["managed_paths"]
    if not isinstance(raw_paths, list):
        raise ManagerError("INVALID_INSTALLATION_STATE", "managed_paths must be a list")
    managed_paths: list[ManagedPath] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, dict) or set(raw_path) != _MANAGED_PATH_KEYS:
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed managed path")
        try:
            path = normalize_relative_path(raw_path["path"])
        except PayloadError as error:
            raise ManagerError("INVALID_INSTALLATION_STATE", "unsafe managed path") from error
        ownership = raw_path["ownership"]
        merge = raw_path["merge"]
        if ownership not in {"dedicated", "shared"}:
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed ownership")
        if ownership == "dedicated" and merge is not None:
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed dedicated ownership")
        if ownership == "shared" and merge not in {"managed-block", "toml-keys"}:
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed shared ownership")
        if not _valid_hash(raw_path["installed_hash"], optional=True):
            raise ManagerError("INVALID_INSTALLATION_STATE", "malformed installed hash")
        if ownership == "shared" and raw_path["installed_hash"] is None:
            raise ManagerError("INVALID_INSTALLATION_STATE", "shared installed hash is missing")
        if merge == "managed-block":
            if not _valid_hash(raw_path["block_hash"]):
                raise ManagerError("INVALID_INSTALLATION_STATE", "malformed block hash")
        elif raw_path["block_hash"] is not None:
            raise ManagerError("INVALID_INSTALLATION_STATE", "unexpected block hash")
        managed_paths.append(
            ManagedPath(
                path,
                raw_path["installed_hash"],
                ownership,
                merge,
                raw_path["block_hash"],
            )
        )
    canonical_paths = [item.path.casefold() for item in managed_paths]
    if managed_paths != sorted(managed_paths, key=lambda item: item.path) or len(
        set(canonical_paths)
    ) != len(managed_paths):
        raise ManagerError("INVALID_INSTALLATION_STATE", "managed paths are unsorted or duplicated")
    decisions = _parse_decisions(document["decisions"])
    toml_paths = {item.path for item in managed_paths if item.merge == "toml-keys"}
    toml_decision_paths = {
        item["path"] for item in decisions if item.get("kind") == "toml-keys"
    }
    if toml_paths != toml_decision_paths:
        raise ManagerError("INVALID_INSTALLATION_STATE", "TOML ownership decisions do not match managed paths")
    shared_paths = {
        item.path: item.merge for item in managed_paths if item.ownership == "shared"
    }
    shared_decisions = {
        item["path"]: item["kind"]
        for item in decisions
        if item["kind"] in {"managed-block", "toml-keys"}
    }
    if shared_paths != shared_decisions:
        raise ManagerError(
            "INVALID_INSTALLATION_STATE",
            "shared ownership decisions do not match managed paths",
        )
    body = dict(document)
    checksum = body.pop("checksum")
    if digest_document(body) != checksum:
        raise ManagerError("INVALID_INSTALLATION_STATE", "state checksum mismatch")
    state = InstallationState(
        document["schema_version"],
        document["plugin_version"],
        document["payload_digest"],
        document["transaction_id"],
        document["installed_at"],
        tuple(managed_paths),
        decisions,
        document["validator_version"],
        document["journal_status"],
        checksum,
    )
    if raw != write_state_document(state):
        raise ManagerError("INVALID_INSTALLATION_STATE", "state is not canonical JSON")
    return state


def load_installation_state(path: Path | str) -> InstallationState:
    """Read and strictly validate one installation state document."""

    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise ManagerError("INVALID_INSTALLATION_STATE", "state cannot be read") from error
    return _parse_state(raw)


def _resolve_git_root(root: Path | str) -> Path:
    requested = Path(root)
    try:
        requested_stat = requested.lstat()
        if stat.S_ISLNK(requested_stat.st_mode) or is_reparse_point(requested_stat):
            raise ManagerError("UNSAFE_PATH", "requested root cannot be a link")
        if not stat.S_ISDIR(requested_stat.st_mode):
            raise ManagerError("UNSUPPORTED_ENVIRONMENT", "requested root is not a directory")
        resolved = requested.resolve(strict=True)
        completed = subprocess.run(
            ["git", "-C", os.fspath(requested), "rev-parse", "--show-toplevel"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except ManagerError:
        raise
    except OSError as error:
        raise ManagerError("UNSUPPORTED_ENVIRONMENT", "cannot inspect Git repository") from error
    if completed.returncode != 0:
        raise ManagerError("UNSUPPORTED_ENVIRONMENT", "requested root is not a Git repository")
    try:
        discovered = Path(completed.stdout.strip()).resolve(strict=True)
    except OSError as error:
        raise ManagerError("UNSAFE_PATH", "discovered Git root is unavailable") from error
    if discovered != resolved:
        raise ManagerError("UNSAFE_PATH", "requested root does not exactly match Git root")
    return resolved


def _transaction_control_only(root: Path) -> bool:
    """Return whether the manager directory contains transaction internals only.

    This is a narrow logical projection used solely so the first authorized
    lock/recovery mutation cannot invalidate an otherwise unchanged approved
    plan. Wrongly typed or unknown siblings remain ordinary digest-bound data.
    """

    try:
        entries = list_immediate_secure(root, _TRANSACTION_CONTROL_DIRECTORY)
    except PayloadError as error:
        raise ManagerError("UNSAFE_PATH", str(error)) from error
    return all(
        _TRANSACTION_INTERNAL_CHILD_TYPES.get(item.name) == item.entry_type
        for item in entries
    )


def _project_transaction_control_children(
    root: Path,
    relative: str,
    children: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Remove only exact, correctly typed transaction-internal observations."""

    if relative == _TRANSACTION_CONTROL_DIRECTORY:
        return tuple(
            item
            for item in children
            if _TRANSACTION_INTERNAL_CHILD_TYPES.get(item[0]) != item[1]
        )
    if relative == ".codex" and ("codex-game-studios", "directory") in children:
        if _transaction_control_only(root):
            return tuple(
                item for item in children
                if item != ("codex-game-studios", "directory")
            )
    return children


def _observe(root: Path, relative: str) -> _Observed:
    relative = normalize_relative_path(relative)
    current = root
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            file_stat = current.lstat()
        except FileNotFoundError:
            return _Observed("missing", None, None)
        except OSError as error:
            raise ManagerError("UNSAFE_PATH", f"cannot inspect target path: {relative}") from error
        if stat.S_ISLNK(file_stat.st_mode) or is_reparse_point(file_stat):
            raise ManagerError("UNSAFE_PATH", f"target path is a link or reparse point: {relative}")
        if index < len(parts) - 1 and not stat.S_ISDIR(file_stat.st_mode):
            return _Observed("blocked", None, None)
    if stat.S_ISDIR(file_stat.st_mode):
        inspect_secure(root, relative, expect="directory")
        try:
            entries = list_immediate_secure(root, relative)
        except PayloadError as error:
            raise ManagerError("UNSAFE_PATH", str(error)) from error
        children = tuple((item.name, item.entry_type) for item in entries)
        projected = _project_transaction_control_children(root, relative, children)
        if not projected and relative in {".codex", _TRANSACTION_CONTROL_DIRECTORY}:
            return _Observed("missing", None, None)
        immediate = [
            dataclasses.asdict(item)
            for item in entries
            if (item.name, item.entry_type) in projected
        ]
        if relative == _TRANSACTION_CONTROL_DIRECTORY:
            for item in immediate:
                if item["name"] == "recovery" and item["entry_type"] == "directory":
                    item["sha256"] = recovery_tree_digest_secure(
                        root, f"{_TRANSACTION_CONTROL_DIRECTORY}/recovery"
                    )
        return _Observed(
            "directory",
            digest_document({"entries": immediate}),
            None,
            projected,
            stat.S_IMODE(file_stat.st_mode),
        )
    if not stat.S_ISREG(file_stat.st_mode):
        raise ManagerError("UNSAFE_PATH", f"target path is a special file: {relative}")
    content = read_file_secure(root, relative)
    return _Observed(
        "file",
        hashlib.sha256(content).hexdigest(),
        content,
        mode=stat.S_IMODE(file_stat.st_mode),
    )


def _load_optional_state(root: Path) -> InstallationState | None:
    observed = _observe(root, STATE_RELATIVE_PATH)
    if observed.kind == "missing":
        return None
    if observed.kind != "file" or observed.content is None:
        raise ManagerError("INVALID_INSTALLATION_STATE", "state path is not a regular file")
    return _parse_state(observed.content)


def _validate_state_manifest_parity(
    state: InstallationState, manifest: PayloadManifest
) -> None:
    """Reject forged ownership claims when state names the embedded payload."""

    if state.payload_digest != manifest.digest:
        return
    if state.plugin_version != manifest.version:
        raise ManagerError(
            "INVALID_INSTALLATION_STATE",
            "plugin version does not match the recorded payload digest",
        )
    records = {item.path: item for item in state.managed_paths}
    entries = {item.path: item for item in manifest.entries}
    if set(records) != set(entries):
        raise ManagerError(
            "INVALID_INSTALLATION_STATE",
            "managed paths do not match the recorded payload manifest",
        )
    for path, entry in entries.items():
        record = records[path]
        if record.ownership != entry.ownership or record.merge != entry.merge:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE",
                "managed ownership does not match the recorded payload manifest",
            )
        if entry.entry_type == "directory" and record.installed_hash is not None:
            raise ManagerError(
                "INVALID_INSTALLATION_STATE", "managed directory has a file hash"
            )
        if (
            entry.entry_type == "file"
            and entry.ownership == "dedicated"
            and record.installed_hash != entry.sha256
        ):
            raise ManagerError(
                "INVALID_INSTALLATION_STATE",
                "dedicated ownership hash does not match the recorded payload",
            )


def _desired_toml(content: bytes) -> dict[str, object]:
    try:
        document = tomllib.loads(content.decode("utf-8"))
        values = {
            "agents.max_depth": document["agents"]["max_depth"],
            "agents.max_threads": document["agents"]["max_threads"],
            "features.hooks": document["features"]["hooks"],
        }
    except (UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as error:
        raise ManagerError("INVALID_PAYLOAD", "shared TOML payload is malformed") from error
    if type(values["agents.max_depth"]) is not int or type(values["agents.max_threads"]) is not int or type(values["features.hooks"]) is not bool:
        raise ManagerError("INVALID_PAYLOAD", "shared TOML payload has invalid owned values")
    return values


def _recorded_toml(state: InstallationState, path: str) -> dict[str, object]:
    matches = [
        item for item in state.decisions
        if item.get("kind") == "toml-keys" and item.get("path") == path
    ]
    if len(matches) != 1:
        raise ManagerError("INVALID_INSTALLATION_STATE", "TOML ownership decision is missing")
    return dict(matches[0]["owned_values"])


def _remove_owned_toml(content: bytes, recorded: Mapping[str, object]) -> bytes:
    """Remove only exact recorded studio assignments from simple TOML layouts."""

    try:
        text = content.decode("utf-8")
        document = tomllib.loads(text)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise MergeConflict("managed TOML is malformed") from error
    for dotted, value in recorded.items():
        table, key = dotted.split(".", 1)
        if not isinstance(document.get(table), dict) or document[table].get(key) != value:
            raise MergeConflict("managed TOML value differs from recorded ownership")
    lines = text.splitlines(keepends=True)
    current: str | None = None
    output: list[str] = []
    for line in lines:
        header = re.fullmatch(r"\s*\[([A-Za-z0-9_-]+)\]\s*", line.rstrip("\r\n"))
        if header:
            current = header.group(1)
            output.append(line)
            continue
        removed = False
        for dotted in recorded:
            table, key = dotted.split(".", 1)
            if current == table and re.match(rf"\s*{re.escape(key)}\s*=", line):
                removed = True
            elif current is None and re.match(
                rf"\s*{re.escape(table)}\s*\.\s*{re.escape(key)}\s*=", line
            ):
                removed = True
        if not removed:
            output.append(line)
    return "".join(output).encode("utf-8")


def _action(kind: str, path: str, before: str | None, after: str | None, detail: str) -> Action:
    return Action(kind, path, before, after, detail)


def _conflict(code: str, path: str, detail: str) -> tuple[Action, Conflict]:
    return (
        _action("conflict", path, None, None, detail),
        Conflict(code, path, detail),
    )


def _classify_fresh(entry: PayloadEntry, observed: _Observed, desired: bytes | None) -> tuple[list[Action], list[Conflict]]:
    if entry.entry_type == "directory":
        if observed.kind == "missing":
            return [_action("create", entry.path, None, None, "create payload directory")], []
        if observed.kind == "directory":
            return [_action("adopt", entry.path, observed.digest, observed.digest, "adopt existing directory")], []
        action, conflict = _conflict("UNMANAGED_COLLISION", entry.path, "unowned target has the wrong type")
        return [action], [conflict]
    if entry.ownership == "dedicated":
        if observed.kind == "missing":
            return [_action("create", entry.path, None, entry.sha256, "create dedicated payload file")], []
        if observed.kind == "file" and observed.digest == entry.sha256:
            return [_action("adopt", entry.path, observed.digest, entry.sha256, "adopt byte-identical payload file")], []
        action, conflict = _conflict("UNMANAGED_COLLISION", entry.path, "unowned target differs from payload")
        return [action], [conflict]
    if observed.kind not in {"missing", "file"}:
        action, conflict = _conflict("UNMANAGED_COLLISION", entry.path, "shared target has the wrong type")
        return [action], [conflict]
    existing = observed.content or b""
    try:
        if entry.merge == "managed-block":
            result = merge_block(existing, "codex-game-studios", desired or b"")
        else:
            result = merge_owned_toml(existing, _desired_toml(desired or b""), {})
    except MergeConflict as error:
        action, conflict = _conflict("UNMANAGED_COLLISION", entry.path, str(error))
        return [action], [conflict]
    after = hashlib.sha256(result.content).hexdigest()
    kind = (
        "adopt"
        if observed.kind == "file" and not result.changed
        else "create" if observed.kind == "missing" else "merge"
    )
    return [_action(kind, entry.path, observed.digest, after, f"{entry.merge} shared ownership")], []


def _customized(path: str, observed: _Observed, detail: str) -> tuple[list[Action], list[Conflict]]:
    action = _action("conflict", path, observed.digest, None, detail)
    return [action], [Conflict("CUSTOMIZED_MANAGED_FILE", path, detail)]


def _classify_dedicated(
    operation: str,
    entry: PayloadEntry | None,
    record: ManagedPath,
    observed: _Observed,
) -> tuple[list[Action], list[Conflict]]:
    path = record.path
    if operation == "uninstall":
        if observed.kind == "missing":
            return [_action("preserve", path, None, None, "managed path is already absent")], []
        if record.installed_hash is None:
            if observed.kind != "directory":
                return _customized(path, observed, "managed directory has the wrong type")
            return [], []
        expected_kind = "directory" if record.installed_hash is None else "file"
        owned = observed.kind == expected_kind and (
            expected_kind == "directory" or observed.digest == record.installed_hash
        )
        if not owned:
            return [_action(
                "preserve", path, observed.digest, observed.digest,
                "preserve customized managed target",
            )], []
        return [
            _action("backup", path, observed.digest, observed.digest, "snapshot owned target before removal"),
            _action("remove", path, observed.digest, None, "remove hash-owned managed target"),
        ], []
    if entry is None:
        if operation == "update":
            return _classify_dedicated("uninstall", None, record, observed)
        return [_action("preserve", path, observed.digest, observed.digest, "path is absent from embedded payload")], []
    if observed.kind == "missing":
        if operation == "repair":
            after = None if entry.entry_type == "directory" else entry.sha256
            return [_action("create", path, None, after, "restore missing managed target")], []
        return _customized(path, observed, "managed target is missing")
    if entry.entry_type == "directory":
        if observed.kind != "directory":
            return _customized(path, observed, "managed directory has the wrong type")
        return [_action("preserve", path, observed.digest, observed.digest, "managed directory remains owned")], []
    if observed.kind != "file" or observed.digest != record.installed_hash:
        return _customized(path, observed, "managed target differs from recorded ownership hash")
    if operation in {"verify", "repair"} or observed.digest == entry.sha256:
        return [_action("preserve", path, observed.digest, observed.digest, "managed file remains owned")], []
    return [_action("update", path, observed.digest, entry.sha256, "replace clean managed file with payload version")], []


def _classify_shared(
    operation: str,
    entry: PayloadEntry | None,
    record: ManagedPath,
    observed: _Observed,
    desired: bytes | None,
    state: InstallationState,
) -> tuple[list[Action], list[Conflict]]:
    path = record.path
    if entry is None:
        return [
            _action(
                "preserve",
                path,
                observed.digest,
                observed.digest,
                "preserve shared path absent from current manifest",
            )
        ], [
            Conflict(
                "STALE_MANUAL_REMNANT",
                path,
                "shared removal requires a current manifest entry",
            )
        ]
    if observed.kind == "missing":
        if operation == "repair" and entry is not None:
            actions, conflicts = _classify_fresh(entry, observed, desired)
            if conflicts:
                return actions, conflicts
            first = actions[0]
            return [_action("create", path, None, first.after_hash, "restore missing shared target")], []
        if operation == "uninstall":
            return [_action("preserve", path, None, None, "shared target is already absent")], []
        return _customized(path, observed, "managed shared target is missing")
    if observed.kind != "file" or observed.content is None:
        return _customized(path, observed, "managed shared target has the wrong type")
    existing = observed.content
    try:
        if operation == "uninstall":
            if record.merge == "managed-block":
                result = remove_block(existing, "codex-game-studios", record.block_hash or "")
                content = result.content
            else:
                recorded = _recorded_toml(state, path)
                content = _remove_owned_toml(existing, recorded)
            after = hashlib.sha256(content).hexdigest() if content else None
            return [
                _action("backup", path, observed.digest, observed.digest, "snapshot shared ownership before removal"),
                _action(
                    "merge" if content else "remove",
                    path,
                    observed.digest,
                    after,
                    f"remove owned {record.merge} content",
                ),
            ], []
        if record.merge == "managed-block":
            result = merge_block(
                existing,
                "codex-game-studios",
                desired or b"",
                recorded_hash=record.block_hash,
            )
        else:
            result = merge_owned_toml(
                existing,
                _desired_toml(desired or b""),
                _recorded_toml(state, path),
            )
    except MergeConflict as error:
        if operation == "uninstall":
            return [
                _action(
                    "preserve", path, observed.digest, observed.digest,
                    f"preserve customized shared target: {error}",
                )
            ], []
        return _customized(path, observed, str(error))
    after = hashlib.sha256(result.content).hexdigest()
    if operation == "verify":
        return [_action("preserve", path, observed.digest, observed.digest, "managed shared ownership remains valid")], []
    if operation == "repair":
        if result.changed:
            return _customized(path, observed, "managed shared content is stale or corrupted")
        return [_action("preserve", path, observed.digest, observed.digest, "managed shared ownership remains valid")], []
    kind = "merge" if result.changed else "preserve"
    return [_action(kind, path, observed.digest, after, f"{record.merge} shared ownership")], []


def _schedule_directory_uninstall(
    records: Mapping[str, ManagedPath],
    entries: Mapping[str, PayloadEntry],
    observed: Mapping[str, _Observed],
    actions: list[Action],
) -> None:
    """Remove empty owned directories deepest-first and preserve nonempty ones."""

    removable = {item.path for item in actions if item.kind == "remove"}
    directories = [
        record
        for path, record in records.items()
        if record.installed_hash is None and path in entries
    ]
    for record in sorted(
        directories, key=lambda item: (-len(PurePosixPath(item.path).parts), item.path)
    ):
        current = observed[record.path]
        if current.kind == "missing":
            actions.append(
                _action(
                    "preserve",
                    record.path,
                    None,
                    None,
                    "managed directory is already absent",
                )
            )
            continue
        if current.kind != "directory":
            actions.append(_action(
                "preserve", record.path, current.digest, current.digest,
                "preserve customized managed directory with wrong type",
            ))
            continue
        children = {f"{record.path}/{name}" for name, _kind in current.children}
        may_remove = (
            record.path not in {".codex", _TRANSACTION_CONTROL_DIRECTORY}
            and children.issubset(removable)
        )
        if may_remove:
            actions.extend([
                _action(
                    "backup", record.path, current.digest, current.digest,
                    "record directory inventory before conditional removal",
                ),
                _action(
                    "remove", record.path, current.digest, None,
                    "conditionally remove empty managed directory",
                ),
            ])
            removable.add(record.path)
        else:
            actions.append(_action(
                "preserve", record.path, current.digest, current.digest,
                "preserve directory containing unrelated or retained content",
            ))


def _historical_record_matches_allowlist(
    record: ManagedPath, entry: PayloadEntry
) -> bool:
    """Return whether historical ownership uses the current path semantics."""

    if record.ownership != entry.ownership or record.merge != entry.merge:
        return False
    if entry.entry_type == "directory":
        return record.installed_hash is None
    return record.installed_hash is not None


def _retain_legal_for_customized_remnants(actions: list[Action]) -> None:
    """Retain installed MIT notices whenever customized framework bytes remain."""

    legal_root = f"{_TRANSACTION_CONTROL_DIRECTORY}/legal"
    has_remnant = any(
        action.kind == "preserve"
        and "customized" in action.detail
        for action in actions
    )
    if not has_remnant:
        return
    rewritten: list[Action] = []
    for action in actions:
        if action.path == legal_root or action.path.startswith(f"{legal_root}/"):
            if action.kind == "backup":
                continue
            if action.kind == "remove":
                rewritten.append(_action(
                    "preserve", action.path, action.before_hash, action.before_hash,
                    "retain legal notice for customized MIT-covered remnants",
                ))
                continue
        rewritten.append(action)
    actions[:] = rewritten


def _action_document(action: Action) -> dict[str, object]:
    return dataclasses.asdict(action)


def _conflict_document(conflict: Conflict) -> dict[str, object]:
    return dataclasses.asdict(conflict)


def _make_plan(
    operation: str,
    plugin_version: str,
    payload_digest: str,
    state_digest: str | None,
    actions: list[Action],
    conflicts: list[Conflict],
    target_hashes: Mapping[str, str | None],
    shared_hashes: Mapping[str, str | None],
    observed: Mapping[str, _Observed],
    entries: Mapping[str, PayloadEntry],
    context_digest: str | None = None,
) -> OperationPlan:
    def action_order(item: Action) -> tuple[object, ...]:
        if item.kind == "state-write":
            return (2, item.path, item.kind, item.detail)
        if item.kind in {"backup", "remove"}:
            return (1, -len(PurePosixPath(item.path).parts), item.path, item.kind)
        return (0, item.path, item.kind, item.detail)

    ordered_actions = tuple(sorted(actions, key=action_order))
    ordered_conflicts = tuple(sorted(conflicts, key=lambda item: (item.path, item.code, item.detail)))
    changing_kinds = {"create", "merge", "update", "remove", "state-write"}
    changing_actions = [
        action for action in ordered_actions if action.kind in changing_kinds
    ]
    changing_paths = sorted(action.path for action in changing_actions)
    if len(changing_paths) != len(set(changing_paths)):
        raise ManagerError("UNSAFE_PATH", "operation plan has duplicate changing paths")
    observations = tuple(
        TargetObservation(
            path,
            observed[path].kind,
            observed[path].mode,
            observed[path].digest,
        )
        for path in changing_paths
    )
    action_by_path = {action.path: action for action in changing_actions}
    results: list[TargetObservation] = []
    for path in changing_paths:
        action = action_by_path[path]
        if action.kind == "remove" or (
            action.kind == "state-write" and action.after_hash is None
        ):
            results.append(TargetObservation(path, "missing", None, None))
            continue
        if action.kind == "state-write":
            results.append(TargetObservation(path, "file", 0o600, action.after_hash))
            continue
        entry = entries[path]
        digest = (
            digest_document({"entries": []})
            if entry.entry_type == "directory"
            else action.after_hash
        )
        results.append(TargetObservation(path, entry.entry_type, entry.mode, digest))
    return plan_with_digest(OperationPlan(
        operation=operation,
        plugin_version=plugin_version,
        payload_digest=payload_digest,
        state_digest=state_digest,
        actions=ordered_actions,
        conflicts=ordered_conflicts,
        digest="",
        target_hashes=tuple(sorted(target_hashes.items())),
        shared_hashes=tuple(sorted(shared_hashes.items())),
        target_observations=observations,
        target_results=tuple(results),
        approval_context_digest=context_digest,
    ))


def _prospective_state(
    plan: OperationPlan,
    manifest: PayloadManifest,
    entries: Mapping[str, PayloadEntry],
    state: InstallationState | None,
    plugin: Path,
    approval_context: ApprovalContext | None = None,
) -> InstallationState:
    """Build deterministic ownership state for the plan's approved results."""

    results = {item.path: item for item in plan.target_results}
    actions = {item.path: item for item in plan.actions}
    existing = {item.path: item for item in state.managed_paths} if state else {}
    managed: list[ManagedPath] = []
    decisions: list[dict[str, object]] = []
    for path, entry in sorted(entries.items()):
        result = results.get(path)
        digest = (
            result.digest
            if result is not None and result.entry_type == "file"
            else existing.get(path).installed_hash if path in existing else entry.sha256
        )
        block_hash = None
        if entry.merge == "managed-block":
            desired = read_file_secure(plugin / "assets/studio", path)
            block_hash = merge_block(b"", "codex-game-studios", desired).block_hash
            decisions.append({"kind": "managed-block", "path": path, "outcome": "merge"})
        elif entry.merge == "toml-keys":
            desired = read_file_secure(plugin / "assets/studio", path)
            decisions.append({
                "kind": "toml-keys", "path": path, "outcome": "merge",
                "owned_values": _desired_toml(desired),
            })
        managed.append(ManagedPath(path, digest if entry.entry_type == "file" else None,
                                   entry.ownership, entry.merge, block_hash))
    if approval_context is None:
        seed = digest_document({
            "operation": plan.operation,
            "payload": manifest.digest,
            "targets": list(plan.target_hashes),
        })
        transaction_id = str(uuid.UUID(seed[:32], version=4))
        installed_at = state.installed_at if state is not None else "2026-07-12T00:00:00Z"
    else:
        transaction_id = approval_context.transaction_id
        installed_at = approval_context.installed_at
    return state_with_checksum(InstallationState(
        STATE_SCHEMA_VERSION,
        manifest.version,
        manifest.digest,
        transaction_id,
        installed_at,
        tuple(managed),
        tuple(sorted(decisions, key=canonical_json)),
        "1",
        "committed",
        "",
    ))


def _plan_operation_at_root(
    operation: str,
    target_root: Path,
    plugin: Path,
    manifest: PayloadManifest,
    approval_context: ApprovalContext | None = None,
) -> OperationPlan:
    context_digest = (
        approval_context_digest(approval_context)
        if approval_context is not None else None
    )
    state = _load_optional_state(target_root)
    if state is not None:
        _validate_state_manifest_parity(state, manifest)
    records = {item.path: item for item in state.managed_paths} if state else {}
    entries = {item.path: item for item in manifest.entries}
    paths = sorted(set(entries) | set(records))
    observed = {path: _observe(target_root, path) for path in paths}
    target_hashes = {path: item.digest for path, item in observed.items()}
    shared_hashes = {
        path: observed[path].digest
        for path, entry in entries.items()
        if entry.ownership == "shared"
    }
    actions: list[Action] = []
    conflicts: list[Conflict] = []
    valid_engine_activation = False

    studio_path = ".codex/studio.toml"
    studio_record = records.get(studio_path)
    studio_observed = observed.get(studio_path)
    if (
        state is not None
        and operation in {"update", "verify", "repair"}
        and studio_record is not None
        and studio_record.installed_hash is not None
        and studio_observed is not None
        and studio_observed.kind == "file"
        and studio_observed.digest != studio_record.installed_hash
    ):
        valid_engine_activation = not validate_installed_read_only(
            target_root, plugin
        )

    if state is None and operation != "install":
        conflicts.append(Conflict("NOT_INSTALLED", STATE_RELATIVE_PATH, "installation state is absent"))
        return _make_plan(
            operation, manifest.version, manifest.digest, None, actions, conflicts,
            target_hashes, shared_hashes, observed, entries,
        )
    if state is not None and operation == "install":
        conflicts.append(Conflict("ALREADY_INSTALLED", STATE_RELATIVE_PATH, "valid installation state already exists"))
        return _make_plan(
            operation, manifest.version, manifest.digest, state.checksum, actions, conflicts,
            target_hashes, shared_hashes, observed, entries,
        )
    if operation == "repair" and state is not None and (
        state.plugin_version != manifest.version or state.payload_digest != manifest.digest
    ):
        conflicts.append(
            Conflict(
                "REPAIR_PAYLOAD_MISMATCH",
                STATE_RELATIVE_PATH,
                "repair requires the exact recorded plugin payload",
            )
        )
        return _make_plan(
            operation, manifest.version, manifest.digest, state.checksum, actions, conflicts,
            target_hashes, shared_hashes, observed, entries,
        )
    if operation == "verify" and state is not None and (
        state.plugin_version != manifest.version or state.payload_digest != manifest.digest
    ):
        conflicts.append(
            Conflict(
                "STALE_INSTALLATION",
                STATE_RELATIVE_PATH,
                "recorded installation payload differs from the embedded plugin payload",
            )
        )

    for path in paths:
        entry = entries.get(path)
        record = records.get(path)
        historical_state_only = (
            state is not None
            and state.payload_digest != manifest.digest
            and record is not None
            and entry is None
        )
        historical_mixed = (
            state is not None
            and state.payload_digest != manifest.digest
            and record is not None
            and entry is not None
            and not _historical_record_matches_allowlist(record, entry)
        )
        if historical_state_only or historical_mixed:
            detail = (
                "historical state path is absent from the current operational allowlist"
                if historical_state_only
                else "historical ownership semantics differ from the current operational allowlist"
            )
            actions.append(
                _action(
                    "preserve",
                    path,
                    observed[path].digest,
                    observed[path].digest,
                    "preserve historical manual remnant",
                )
            )
            conflicts.append(
                Conflict(
                    "STALE_MANUAL_REMNANT",
                    path,
                    detail,
                )
            )
            continue
        desired = None
        if entry is not None and entry.entry_type == "file":
            try:
                desired = read_file_secure(plugin / "assets/studio", path)
            except PayloadError as error:
                raise ManagerError("INVALID_PAYLOAD", str(error)) from error
            if hashlib.sha256(desired).hexdigest() != entry.sha256:
                raise ManagerError(
                    "INVALID_PAYLOAD", f"payload source hash changed: {path}"
                )
        if state is None:
            assert entry is not None
            path_actions, path_conflicts = _classify_fresh(entry, observed[path], desired)
        elif record is None:
            assert entry is not None
            if operation == "uninstall":
                continue
            if operation == "verify":
                path_actions = [
                    _action(
                        "diagnostic",
                        path,
                        observed[path].digest,
                        entry.sha256,
                        "current payload path is absent from historical ownership state",
                    )
                ]
                path_conflicts = [
                    Conflict(
                        "STALE_INSTALLATION",
                        path,
                        "current payload path is absent from historical ownership state",
                    )
                ]
            else:
                path_actions, path_conflicts = _classify_fresh(
                    entry, observed[path], desired
                )
        elif path == studio_path and valid_engine_activation:
            path_actions = [_action(
                "preserve",
                path,
                observed[path].digest,
                observed[path].digest,
                "validated engine-pack activation remains configured",
            )]
            path_conflicts = []
        elif record.ownership == "shared":
            path_actions, path_conflicts = _classify_shared(
                operation, entry, record, observed[path], desired, state
            )
        else:
            path_actions, path_conflicts = _classify_dedicated(
                operation, entry, record, observed[path]
            )
        actions.extend(path_actions)
        conflicts.extend(path_conflicts)

    if operation == "uninstall" and state is not None:
        _retain_legal_for_customized_remnants(actions)
        _schedule_directory_uninstall(
            records, entries, observed, actions
        )

    base_plan = _make_plan(
        operation,
        manifest.version,
        manifest.digest,
        state.checksum if state else None,
        actions,
        conflicts,
        target_hashes,
        shared_hashes,
        observed,
        entries,
        context_digest,
    )
    if operation == "verify" or base_plan.conflicts:
        return base_plan
    state_observation = _observe(target_root, STATE_RELATIVE_PATH)
    observed[STATE_RELATIVE_PATH] = state_observation
    if operation == "uninstall":
        state_action = _action(
            "state-write", STATE_RELATIVE_PATH, state_observation.digest, None,
            "remove installation state after uninstall validation",
        )
    else:
        prospective = _prospective_state(
            base_plan, manifest, entries, state, plugin, approval_context
        )
        state_bytes = write_state_document(prospective)
        state_action = _action(
            "state-write", STATE_RELATIVE_PATH, state_observation.digest,
            hashlib.sha256(state_bytes).hexdigest(),
            "persist validated installation ownership state",
        )
    return _make_plan(
        operation, manifest.version, manifest.digest,
        state.checksum if state else None,
        [*actions, state_action], conflicts, target_hashes, shared_hashes,
        observed, entries,
        context_digest,
    )


def plan_operation(
    operation: str,
    root: Path | str,
    plugin_root: Path | str,
    approval_context: ApprovalContext | None = None,
) -> OperationPlan:
    """Return a complete deterministic lifecycle plan without writing the target."""

    if operation not in OPERATIONS:
        raise ManagerError("UNSUPPORTED_ENVIRONMENT", "unknown manager operation")
    plugin = Path(plugin_root)
    try:
        with pin_root(root) as pinned:
            target_root = _resolve_git_root(pinned.root)
            try:
                with pin_root(plugin) as plugin_pinned:
                    manifest = load_verified_manifest(plugin_pinned.root)
                    plan = _plan_operation_at_root(
                        operation, target_root, plugin_pinned.root, manifest,
                        approval_context,
                    )
                    verify_manifest_snapshot(plugin_pinned.root, manifest)
                    plugin_pinned.verify()
            except PayloadError as error:
                raise ManagerError("INVALID_PAYLOAD", str(error)) from error
            pinned.verify()
            return plan
    except PayloadError as error:
        raise ManagerError("UNSAFE_PATH", str(error)) from error
    except _EXPECTED_MANAGER_FAILURES as error:
        raise _manager_error_from_expected(error) from error


def validate_installed_read_only(root: Path | str, plugin_root: Path | str) -> list[object]:
    """Run the embedded installed validator without writing bytecode to the target."""

    try:
        for requested in (Path(root).absolute(), Path(plugin_root).absolute()):
            current = Path(requested.anchor)
            for part in requested.parts[1:]:
                current /= part
                metadata = current.lstat()
                if stat.S_ISLNK(metadata.st_mode) or is_reparse_point(metadata):
                    raise ManagerError("UNSAFE_PATH", f"root ancestor is a link or reparse point: {current}")
        with pin_root(root) as target_pin, pin_root(plugin_root) as plugin_pin:
            manifest = load_verified_manifest(plugin_pin.root)
            entry = next((item for item in manifest.entries if item.path == "tools/codex_studio/validate.py"), None)
            if entry is None or entry.sha256 is None:
                raise ManagerError("INVALID_PAYLOAD", "installed validator is absent from payload")
            source = read_file_secure(plugin_pin.root / "assets/studio", entry.path)
            if hashlib.sha256(source).hexdigest() != entry.sha256:
                raise ManagerError("INVALID_PAYLOAD", "installed validator hash mismatch")
            module_name = "_codex_studio_installed_validator"
            module = types.ModuleType(module_name)
            module.__file__ = str(plugin_pin.root / "assets/studio" / entry.path)
            previous = sys.dont_write_bytecode
            import_root = str(plugin_pin.root / "assets/studio")
            try:
                sys.dont_write_bytecode = True
                sys.path.insert(0, import_root)
                sys.modules[module_name] = module
                exec(compile(source, module.__file__, "exec"), module.__dict__)
                validator = module.__dict__["_validate_installed_repository_secure"]
                result, state_raw = validator(target_pin.root)
                if state_raw is None:
                    raise ManagerError("INVALID_INSTALLATION_STATE", "installation state could not be read securely")
                state = _parse_state(state_raw)
                if state.payload_digest != manifest.digest or state.plugin_version != manifest.version:
                    raise ManagerError(
                        "INVALID_INSTALLATION_STATE",
                        "installed payload provenance does not match the current embedded payload",
                    )
                _validate_state_manifest_parity(state, manifest)
                target_pin.verify()
                plugin_pin.verify()
                return result
            finally:
                sys.modules.pop(module_name, None)
                if sys.path and sys.path[0] == import_root:
                    sys.path.pop(0)
                sys.dont_write_bytecode = previous
    except PayloadError:
        raise


def _plan_document(plan: OperationPlan) -> dict[str, object]:
    return {
        "operation": plan.operation,
        "plugin_version": plan.plugin_version,
        "payload_digest": plan.payload_digest,
        "state_digest": plan.state_digest,
        "actions": [_action_document(item) for item in plan.actions],
        "conflicts": [_conflict_document(item) for item in plan.conflicts],
        "target_hashes": dict(plan.target_hashes),
        "shared_hashes": dict(plan.shared_hashes),
        "target_observations": [dataclasses.asdict(item) for item in plan.target_observations],
        "target_results": [dataclasses.asdict(item) for item in plan.target_results],
        "digest": plan.digest,
        "approval_context_digest": plan.approval_context_digest,
    }


def _result_document(
    plan: OperationPlan,
    *,
    status: str,
    wrote: bool,
    recovery: str | dict[str, str] | None = None,
    next_action: str,
    approval_context: str | None = None,
    findings: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "operation": plan.operation,
        "digest": plan.digest,
        "actions": [_action_document(item) for item in plan.actions],
        "conflicts": [_conflict_document(item) for item in plan.conflicts],
        "wrote": wrote,
        "recovery": recovery,
        "next_action": next_action,
        "approval_context": approval_context,
        "findings": findings or [],
    }


def _error_document(operation: str, code: str, *, next_action: str) -> dict[str, object]:
    return {
        "status": code,
        "operation": operation,
        "digest": None,
        "actions": [],
        "conflicts": [],
        "wrote": False,
        "recovery": None,
        "next_action": next_action,
        "approval_context": None,
        "findings": [],
    }


def _finding_documents(findings: list[object]) -> list[dict[str, str]]:
    """Return ordered content-free public findings with relative canonical paths."""

    result: list[dict[str, str]] = []
    for finding in findings:
        raw_path = getattr(finding, "path", ".")
        try:
            path = "." if raw_path == "." else normalize_relative_path(raw_path)
        except (PayloadError, TypeError):
            path = "."
        result.append({"path": path})
    return sorted(result, key=lambda item: item["path"])


def _stable_conflict_code(plan: OperationPlan) -> str:
    code = plan.conflicts[0].code
    if code in {"UNMANAGED_COLLISION", "CUSTOMIZED_MANAGED_FILE"}:
        return code
    return "INVALID_INSTALLATION_STATE"


def _action_content(
    action: Action,
    root: Path,
    plugin: Path,
    state: InstallationState | None,
) -> tuple[bytes, int] | None:
    manifest = load_verified_manifest(plugin)
    entry = next((item for item in manifest.entries if item.path == action.path), None)
    if entry is None or entry.entry_type == "directory":
        return None
    desired = read_file_secure(plugin / "assets/studio", action.path)
    if entry.ownership == "dedicated":
        return desired, entry.mode
    existing = b"" if not (root / action.path).exists() else read_file_secure(root, action.path)
    if action.detail.startswith("remove owned"):
        assert state is not None
        if entry.merge == "managed-block":
            content = remove_block(
                existing, "codex-game-studios",
                next(item.block_hash for item in state.managed_paths if item.path == action.path) or "",
            ).content
        else:
            content = _remove_owned_toml(existing, _recorded_toml(state, action.path))
    elif entry.merge == "managed-block":
        recorded = next((item.block_hash for item in state.managed_paths if item.path == action.path), None) if state else None
        content = merge_block(existing, "codex-game-studios", desired, recorded_hash=recorded).content
    else:
        recorded_values = _recorded_toml(state, action.path) if state else {}
        content = merge_owned_toml(existing, _desired_toml(desired), recorded_values).content
    return content, entry.mode


def _apply_lifecycle_action(
    action: Action,
    mutation: object,
    root: Path,
    plugin: Path,
    state: InstallationState | None,
) -> None:
    if action.kind in {"backup", "adopt", "preserve", "diagnostic"}:
        return
    if action.kind == "remove":
        target = root / action.path
        if target.is_dir():
            mutation.remove_empty_directory(action.path)
        else:
            mutation.remove_file(action.path)
        return
    if action.kind == "create" and action.after_hash is None:
        entry = next(item for item in load_verified_manifest(plugin).entries if item.path == action.path)
        mutation.make_directory(action.path, entry.mode)
        return
    rendered = _action_content(action, root, plugin, state)
    if rendered is None:
        raise ManagerError("INVALID_PAYLOAD", "approved file action has no payload content")
    content, mode = rendered
    mutation.replace_file(action.path, content, mode)


def _prospective_state_bytes(
    plan: OperationPlan,
    plugin: Path,
    state: InstallationState | None,
    approval_context: ApprovalContext | None = None,
) -> bytes:
    manifest = load_verified_manifest(plugin)
    entries = {item.path: item for item in manifest.entries}
    return write_state_document(_prospective_state(
        plan, manifest, entries, state, plugin, approval_context
    ))


def _validate_uninstall_read_only(
    root: Path,
    plan: OperationPlan,
    state: InstallationState,
) -> list[str]:
    """Validate the exact approved uninstall result before removing ownership state."""

    findings: list[str] = []
    result_by_path = {item.path: item for item in plan.target_results}
    action_by_path = {
        item.path: item for item in plan.actions
        if item.kind in {"create", "merge", "update", "remove"}
    }
    preserved = {
        item.path: item for item in plan.actions if item.kind == "preserve"
    }
    records = {item.path: item for item in state.managed_paths}
    legal_root = f"{_TRANSACTION_CONTROL_DIRECTORY}/legal"
    customized = {
        path for path, action in preserved.items()
        if "customized" in action.detail
    }
    try:
        current_state = _load_optional_state(root)
        if current_state != state:
            findings.append("installation state changed before uninstall validation")
        for path, record in sorted(records.items()):
            observed = _observe(root, path)
            action = action_by_path.get(path)
            if action is not None:
                expected = result_by_path[path]
                if (
                    observed.kind != expected.entry_type
                    or not modes_match(observed.mode, expected.mode)
                    or observed.digest != expected.digest
                ):
                    findings.append(f"approved uninstall result mismatch: {path}")
                continue
            preserve = preserved.get(path)
            if preserve is None:
                findings.append(f"managed path lacks uninstall disposition: {path}")
                continue
            if record.installed_hash is not None:
                if observed.kind == "missing" or observed.digest != preserve.after_hash:
                    findings.append(f"preserved remnant changed: {path}")
            elif preserve.before_hash is None:
                if observed.kind != "missing":
                    findings.append(f"previously absent managed directory appeared: {path}")
            elif observed.kind != "directory":
                findings.append(f"preserved managed directory differs: {path}")
        legal_files = {
            path for path in records
            if path.startswith(f"{legal_root}/") and records[path].installed_hash is not None
        }
        if customized:
            for path in sorted(legal_files):
                observed = _observe(root, path)
                expected_digest = (
                    preserved[path].after_hash
                    if path in customized
                    else records[path].installed_hash
                )
                if observed.kind != "file" or observed.digest != expected_digest:
                    findings.append(f"required retained legal notice differs: {path}")
        else:
            for path in sorted(legal_files):
                if _observe(root, path).kind != "missing":
                    findings.append(f"clean uninstall retained legal notice: {path}")
    except ManagerError as error:
        findings.append(f"uninstall validation could not inspect safely: {error.code}")
    return findings


def _prospective_shadow_ignore(
    root: Path,
) -> Callable[[str, Sequence[str]], tuple[str, ...]]:
    """Exclude only the exact live transaction lock from a validation shadow."""

    control = root / PurePosixPath(_TRANSACTION_CONTROL_DIRECTORY)
    try:
        entries = list_immediate_secure(root, _TRANSACTION_CONTROL_DIRECTORY)
    except PayloadError as error:
        raise ManagerError("UNSAFE_PATH", str(error)) from error
    regular_lock = any(
        item.name == "manager.lock"
        and item.entry_type == _TRANSACTION_INTERNAL_CHILD_TYPES["manager.lock"]
        for item in entries
    )

    def ignore(directory: str, names: Sequence[str]) -> tuple[str, ...]:
        if Path(directory) != control or not regular_lock:
            return ()
        return ("manager.lock",) if "manager.lock" in names else ()

    return ignore


def _validate_prospective(
    root: Path,
    plugin: Path,
    plan: OperationPlan,
    state: InstallationState | None,
    approval_context: ApprovalContext | None = None,
) -> list[object]:
    if plan.operation == "uninstall":
        if state is None:
            return ["installation state is absent during uninstall validation"]
        return _validate_uninstall_read_only(root, plan, state)
    temporary_parent = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(dir=temporary_parent) as temporary:
        shadow = Path(temporary) / "repository"
        shutil.copytree(
            root,
            shadow,
            symlinks=True,
            ignore=_prospective_shadow_ignore(root),
        )
        state_path = shadow / STATE_RELATIVE_PATH
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(_prospective_state_bytes(
            plan, plugin, state, approval_context
        ))
        return validate_installed_read_only(shadow, plugin)


def apply_operation(
    plan: OperationPlan,
    root: Path,
    plugin: Path,
    *,
    approval_context: ApprovalContext | None = None,
) -> object:
    """Apply one approved mutating lifecycle plan through the transaction API."""

    if approval_context is None or plan.approval_context_digest != approval_context_digest(
        approval_context
    ):
        raise ManagerError("STALE_PLAN", "approval context does not match approved plan")
    sys.modules.setdefault("studio_manager", sys.modules[__name__])
    from transaction import apply_transaction

    state = _load_optional_state(root)
    state_bytes = None if plan.operation == "uninstall" else _prospective_state_bytes(
        plan, plugin, state, approval_context
    )

    def persist(action: Action, mutation: object) -> None:
        if plan.operation == "uninstall":
            mutation.remove_state_file(action.path)
        else:
            assert state_bytes is not None
            mutation.replace_file(action.path, state_bytes, 0o600)

    def apply_action(action: Action, mutation: object) -> None:
        try:
            _apply_lifecycle_action(action, mutation, root, plugin, state)
        except _EXPECTED_MANAGER_FAILURES as error:
            raise _manager_error_from_expected(error) from error

    def validate(current: Path) -> list[object]:
        try:
            return _validate_prospective(
                current, plugin, plan, state, approval_context
            )
        except _EXPECTED_MANAGER_FAILURES as error:
            raise _manager_error_from_expected(error) from error

    try:
        return apply_transaction(
            plan,
            root,
            lambda: plan_operation(plan.operation, root, plugin, approval_context),
            apply_action,
            validate,
            persist_state=persist,
            transaction_id=(approval_context.transaction_id if approval_context else None),
        )
    except _EXPECTED_MANAGER_FAILURES as error:
        raise _manager_error_from_expected(error) from error


def main(argv: list[str] | None = None) -> int:
    """Plan or apply one lifecycle operation and emit canonical redacted JSON."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--plugin-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--format", choices=("json",), default="json")
    parser.add_argument("--approve-digest")
    parser.add_argument("--approval-context")
    arguments = parser.parse_args(argv)
    context: ApprovalContext | None = None
    plan: OperationPlan | None = None
    boundary = "planning"
    try:
        if arguments.operation != "verify":
            if arguments.approve_digest is None:
                if arguments.approval_context is not None:
                    raise ManagerError("STALE_PLAN", "approval context requires an approved digest")
                context = new_approval_context(arguments.operation)
            else:
                if arguments.approval_context is None:
                    raise ManagerError("STALE_PLAN", "approved apply requires approval context")
                context = decode_approval_context(
                    arguments.approval_context, arguments.operation
                )
        elif arguments.approve_digest is not None or arguments.approval_context is not None:
            raise ManagerError("STALE_PLAN", "verify does not accept approval metadata")
        plan = plan_operation(
            arguments.operation, arguments.root, arguments.plugin_root, context
        )
        if arguments.operation == "verify":
            boundary = "installed-validation"
            findings = validate_installed_read_only(arguments.root, arguments.plugin_root)
            status = "success" if not findings else "VALIDATION_FAILED"
            print(canonical_json(_result_document(
                plan, status=status, wrote=False,
                next_action="none" if not findings else "repair or reconcile reported findings",
                findings=_finding_documents(findings),
            )).decode("utf-8"), end="")
            return 0 if not findings else 1
        if plan.conflicts:
            print(canonical_json(_result_document(
                plan, status=_stable_conflict_code(plan), wrote=False,
                next_action="resolve conflicts and run a new read-only plan",
            )).decode("utf-8"), end="")
            return 1
        if arguments.approve_digest is None:
            print(canonical_json(_result_document(
                plan, status="awaiting-approval", wrote=False,
                next_action="approve this exact digest to apply",
                approval_context=encode_approval_context(context),
            )).decode("utf-8"), end="")
            return 2
        if arguments.approve_digest != plan.digest:
            print(canonical_json(_result_document(
                plan, status="STALE_PLAN", wrote=False,
                next_action="run a new read-only plan",
            )).decode("utf-8"), end="")
            return 1
        boundary = "approved-apply"
        result = apply_operation(
            plan, arguments.root, arguments.plugin_root,
            approval_context=context,
        )
        print(canonical_json(_result_document(
            plan, status="success", wrote=True, recovery=result.status,
            next_action="$start" if plan.operation == "install" else "none",
        )).decode("utf-8"), end="")
        return 0
    except _PUBLIC_MANAGER_FAILURES as caught:
        if isinstance(caught, ManagerError):
            error = caught
        else:
            error = _manager_error_from_expected(
                caught,
                payload_code=(
                    "INVALID_INSTALLATION_STATE"
                    if boundary == "installed-validation"
                    else "INVALID_PAYLOAD"
                ),
            )
        if boundary == "approved-apply" and plan is not None:
            document = _result_document(
                plan, status=error.code, wrote=error.wrote,
                recovery=error.recovery if error.code == "ROLLBACK_FAILED" else None,
                next_action=(
                    "follow recovery instructions"
                    if error.code == "ROLLBACK_FAILED"
                    else "run a new read-only plan"
                ),
            )
        else:
            document = _error_document(
                arguments.operation,
                error.code,
                next_action=(
                    "inspect installation state"
                    if boundary == "installed-validation"
                    else "run a new read-only plan"
                ),
            )
        print(canonical_json(document).decode("utf-8"), end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
