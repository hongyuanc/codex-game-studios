"""Read-only, deterministic planning for Codex Game Studios lifecycle operations."""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tomllib
import types
import uuid
from collections.abc import Mapping

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

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


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
    if relative == ".codex" and children == (("codex-game-studios", "directory"),):
        return () if _transaction_control_only(root) else children
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
            actions, conflicts = _customized(path, observed, "managed target differs from recorded ownership hash")
            return [_action("preserve", path, observed.digest, observed.digest, "preserve customized managed target")], conflicts
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
                after = hashlib.sha256(result.content).hexdigest()
            else:
                recorded = _recorded_toml(state, path)
                merge_owned_toml(existing, recorded, recorded)
                after = None
            return [
                _action("backup", path, observed.digest, observed.digest, "snapshot shared ownership before removal"),
                _action("remove", path, observed.digest, after, f"remove owned {record.merge} content"),
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
                _action("preserve", path, observed.digest, observed.digest, "preserve customized shared target")
            ], [Conflict("CUSTOMIZED_MANAGED_FILE", path, str(error))]
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
    conflicts: list[Conflict],
) -> None:
    """Plan conditional rmdir only when every observed child is removable."""

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
            path_actions, path_conflicts = _customized(
                record.path, current, "managed directory has the wrong type"
            )
            actions.extend(path_actions)
            conflicts.extend(path_conflicts)
            continue
        child_paths = {
            f"{record.path}/{name}" for name, _entry_type in current.children
        }
        if child_paths.issubset(removable):
            actions.extend(
                [
                    _action(
                        "backup",
                        record.path,
                        current.digest,
                        current.digest,
                        "record directory inventory before conditional removal",
                    ),
                    _action(
                        "remove",
                        record.path,
                        current.digest,
                        None,
                        "conditionally remove empty managed directory",
                    ),
                ]
            )
            removable.add(record.path)
        else:
            actions.append(
                _action(
                    "preserve",
                    record.path,
                    current.digest,
                    current.digest,
                    "preserve directory containing user or retained children",
                )
            )


def _historical_record_matches_allowlist(
    record: ManagedPath, entry: PayloadEntry
) -> bool:
    """Return whether historical ownership uses the current path semantics."""

    if record.ownership != entry.ownership or record.merge != entry.merge:
        return False
    if entry.entry_type == "directory":
        return record.installed_hash is None
    return record.installed_hash is not None


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
) -> OperationPlan:
    def action_order(item: Action) -> tuple[object, ...]:
        if item.kind in {"backup", "remove"}:
            return (1, -len(PurePosixPath(item.path).parts), item.path, item.kind)
        return (0, item.path, item.kind, item.detail)

    ordered_actions = tuple(sorted(actions, key=action_order))
    ordered_conflicts = tuple(sorted(conflicts, key=lambda item: (item.path, item.code, item.detail)))
    changing_paths = sorted(
        action.path
        for action in ordered_actions
        if action.kind in {"create", "merge", "update", "remove", "state-write"}
    )
    observations = tuple(
        TargetObservation(
            path,
            observed[path].kind,
            observed[path].mode,
            observed[path].digest,
        )
        for path in changing_paths
    )
    action_by_path = {action.path: action for action in ordered_actions}
    results: list[TargetObservation] = []
    for path in changing_paths:
        action = action_by_path[path]
        if action.kind == "remove":
            results.append(TargetObservation(path, "missing", None, None))
            continue
        entry = entries[path]
        digest = (
            digest_document({"entries": []})
            if entry.entry_type == "directory"
            else action.after_hash
        )
        results.append(TargetObservation(path, entry.entry_type, entry.mode, digest))
    return plan_with_digest(OperationPlan(
        operation,
        plugin_version,
        payload_digest,
        state_digest,
        ordered_actions,
        ordered_conflicts,
        "",
        tuple(sorted(target_hashes.items())),
        tuple(sorted(shared_hashes.items())),
        observations,
        tuple(results),
    ))


def _plan_operation_at_root(
    operation: str,
    target_root: Path,
    plugin: Path,
    manifest: PayloadManifest,
) -> OperationPlan:
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
        _schedule_directory_uninstall(
            records, entries, observed, actions, conflicts
        )

    return _make_plan(
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
    )


def plan_operation(operation: str, root: Path | str, plugin_root: Path | str) -> OperationPlan:
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
                        operation, target_root, plugin_pinned.root, manifest
                    )
                    verify_manifest_snapshot(plugin_pinned.root, manifest)
                    plugin_pinned.verify()
            except PayloadError as error:
                raise ManagerError("INVALID_PAYLOAD", str(error)) from error
            pinned.verify()
            return plan
    except PayloadError as error:
        raise ManagerError("UNSAFE_PATH", str(error)) from error


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
            try:
                sys.dont_write_bytecode = True
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
                sys.dont_write_bytecode = previous
    except PayloadError as error:
        raise ManagerError("UNSAFE_PATH", str(error)) from error


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
    }


def main(argv: list[str] | None = None) -> int:
    """Print one canonical JSON operation plan for later approval and application."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--plugin-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--format", choices=("json",), default="json")
    arguments = parser.parse_args(argv)
    try:
        plan = plan_operation(arguments.operation, arguments.root, arguments.plugin_root)
    except ManagerError as error:
        parser.exit(2, f"{error}\n")
    print(canonical_json(_plan_document(plan)).decode("utf-8"), end="")
    return 1 if plan.conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
