"""Canonical payload models and cross-platform path safety helpers."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import unicodedata


class PayloadError(ValueError):
    """Raised when payload data or a payload path violates the contract."""


@dataclasses.dataclass(frozen=True)
class PayloadEntry:
    """One canonical file-system entry in the operational payload."""

    path: str
    entry_type: str
    mode: int
    sha256: str | None
    ownership: str
    merge: str | None
    required: bool


@dataclasses.dataclass(frozen=True)
class PayloadManifest:
    """Canonical, digest-bound description of an operational payload."""

    schema_version: int
    version: str
    entries: tuple[PayloadEntry, ...]
    digest: str


@dataclasses.dataclass(frozen=True)
class ManagedPath:
    """One target path and the exact ownership evidence recorded for it."""

    path: str
    installed_hash: str | None
    ownership: str
    merge: str | None
    block_hash: str | None


@dataclasses.dataclass(frozen=True)
class InstallationState:
    """Checksum-bound installation ownership and provenance state."""

    schema_version: int
    plugin_version: str
    payload_digest: str
    transaction_id: str
    installed_at: str
    managed_paths: tuple[ManagedPath, ...]
    decisions: tuple[dict[str, object], ...]
    validator_version: str
    journal_status: str
    checksum: str


@dataclasses.dataclass(frozen=True)
class Conflict:
    """One stable, content-free reason a planned operation cannot proceed."""

    code: str
    path: str
    detail: str


@dataclasses.dataclass(frozen=True)
class Action:
    """One deterministic lifecycle action classified without applying it."""

    kind: str
    path: str
    before_hash: str | None
    after_hash: str | None
    detail: str


@dataclasses.dataclass(frozen=True)
class TargetObservation:
    """Digest-bound exact pre-transaction state for one changing action path."""

    path: str
    entry_type: str
    mode: int | None
    digest: str | None


@dataclasses.dataclass(frozen=True)
class OperationPlan:
    """A complete ordered plan bound to every relevant observed hash."""

    operation: str
    plugin_version: str
    payload_digest: str
    state_digest: str | None
    actions: tuple[Action, ...]
    conflicts: tuple[Conflict, ...]
    digest: str
    target_hashes: tuple[tuple[str, str | None], ...] = ()
    shared_hashes: tuple[tuple[str, str | None], ...] = ()
    target_observations: tuple[TargetObservation, ...] = ()
    target_results: tuple[TargetObservation, ...] = ()
    approval_context_digest: str | None = None


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _validate_projection_pairs(
    label: str, projection: object
) -> tuple[tuple[str, str | None], ...]:
    if not isinstance(projection, tuple):
        raise PayloadError(f"operation plan {label} projection is malformed")
    validated: list[tuple[str, str | None]] = []
    aliases: set[str] = set()
    for item in projection:
        if not isinstance(item, tuple) or len(item) != 2:
            raise PayloadError(f"operation plan {label} projection is malformed")
        path, digest = item
        try:
            normalized = normalize_relative_path(path)
        except PayloadError as error:
            raise PayloadError(f"operation plan {label} projection path is unsafe") from error
        if normalized != unicodedata.normalize("NFC", normalized):
            raise PayloadError(f"operation plan {label} projection path is noncanonical")
        alias = normalized.casefold()
        if alias in aliases:
            raise PayloadError(f"operation plan {label} projection path aliases collide")
        aliases.add(alias)
        if digest is not None and not _valid_digest(digest):
            raise PayloadError(f"operation plan {label} projection digest is malformed")
        validated.append((normalized, digest))
    result = tuple(validated)
    if result != tuple(sorted(result, key=lambda item: item[0])):
        raise PayloadError(f"operation plan {label} projection is not sorted")
    return result


def _validate_target_observations(
    observations: object,
) -> tuple[TargetObservation, ...]:
    if not isinstance(observations, tuple) or any(
        not isinstance(item, TargetObservation) for item in observations
    ):
        raise PayloadError("operation plan observation projection is malformed")
    aliases: set[str] = set()
    for item in observations:
        try:
            path = normalize_relative_path(item.path)
        except PayloadError as error:
            raise PayloadError("operation plan observation projection path is unsafe") from error
        if path != item.path or path != unicodedata.normalize("NFC", path):
            raise PayloadError("operation plan observation projection path is noncanonical")
        alias = path.casefold()
        if alias in aliases:
            raise PayloadError("operation plan observation projection path aliases collide")
        aliases.add(alias)
        if item.entry_type == "missing":
            valid = item.mode is None and item.digest is None
        elif item.entry_type in {"file", "directory"}:
            valid = type(item.mode) is int and 0 <= item.mode <= 0o7777 and _valid_digest(item.digest)
        else:
            valid = False
        if not valid:
            raise PayloadError("operation plan observation projection state is malformed")
    if observations != tuple(sorted(observations, key=lambda item: item.path)):
        raise PayloadError("operation plan observation projection is not sorted")
    return observations


def validate_operation_plan_projections(plan: OperationPlan) -> None:
    """Validate canonical projections before they can be hashed or compared."""

    _validate_projection_pairs("target", plan.target_hashes)
    _validate_projection_pairs("shared", plan.shared_hashes)
    if plan.approval_context_digest is not None and not _valid_digest(
        plan.approval_context_digest
    ):
        raise PayloadError("operation plan approval context commitment is malformed")
    observations = _validate_target_observations(plan.target_observations)
    results = _validate_target_observations(plan.target_results)
    changing = tuple(
        sorted(
            action.path
            for action in plan.actions
            if action.kind in {"create", "merge", "update", "remove", "state-write"}
        )
    )
    if tuple(item.path for item in observations) != changing:
        raise PayloadError("operation plan observation projection does not match changing actions")
    if tuple(item.path for item in results) != changing:
        raise PayloadError("operation plan result projection does not match changing actions")


def operation_plan_digest(plan: OperationPlan) -> str:
    """Recompute one complete public operation-plan digest."""

    validate_operation_plan_projections(plan)

    body: dict[str, object] = {
        "operation": plan.operation,
        "plugin_version": plan.plugin_version,
        "payload_digest": plan.payload_digest,
        "state_digest": plan.state_digest,
        "target_hashes": list(plan.target_hashes),
        "shared_hashes": list(plan.shared_hashes),
        "target_observations": [dataclasses.asdict(item) for item in plan.target_observations],
        "target_results": [dataclasses.asdict(item) for item in plan.target_results],
        "actions": [dataclasses.asdict(item) for item in plan.actions],
        "conflicts": [dataclasses.asdict(item) for item in plan.conflicts],
        "approval_context_digest": plan.approval_context_digest,
    }
    return digest_document(body)


def plan_with_digest(plan: OperationPlan) -> OperationPlan:
    """Return an operation plan bound to all its public fields."""

    return dataclasses.replace(plan, digest=operation_plan_digest(plan))


def validate_operation_plan_digest(plan: OperationPlan) -> None:
    """Reject an internally inconsistent or noncanonical operation plan."""

    if plan.digest != operation_plan_digest(plan):
        raise PayloadError("operation plan digest is internally inconsistent")


def canonical_json(value: object) -> bytes:
    """Encode a value as newline-terminated canonical UTF-8 JSON."""

    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def digest_document(document: dict[str, object]) -> str:
    """Return the SHA-256 digest of a canonical JSON document."""

    return hashlib.sha256(canonical_json(document)).hexdigest()


def normalize_relative_path(raw: str) -> str:
    """Return a safe canonical POSIX path or raise ``PayloadError``."""

    if not isinstance(raw, str):
        raise PayloadError("unsafe payload path")
    if "\x00" in raw or "\\" in raw or raw.startswith("/"):
        raise PayloadError("unsafe payload path")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in raw):
        raise PayloadError("unsafe payload path contains a name surrogate")
    parts = pathlib.PurePosixPath(raw).parts
    if (
        not parts
        or any(part in {"", ".", ".."} for part in raw.split("/"))
        or any(part in {".", ".."} for part in parts)
    ):
        raise PayloadError("parent traversal or non-normalized payload path")
    normalized = unicodedata.normalize("NFC", raw)
    if normalized != raw or pathlib.PurePosixPath(raw).as_posix() != raw:
        raise PayloadError("non-normalized payload path")
    windows_reserved = {"CON", "PRN", "AUX", "NUL"}
    windows_reserved.update(f"COM{number}" for number in range(1, 10))
    windows_reserved.update(f"LPT{number}" for number in range(1, 10))
    for part in parts:
        if any(unicodedata.category(character) == "Cc" for character in part):
            raise PayloadError("unsafe payload path contains a control character")
        if any(character in '<>:"|?*' for character in part) or part.endswith((" ", ".")):
            raise PayloadError("unsafe payload path for Windows")
        if part.split(".", 1)[0].upper() in windows_reserved:
            raise PayloadError("unsafe payload path for Windows")
    return raw
