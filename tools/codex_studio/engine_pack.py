"""Serialized, recoverable activation of Codex game-engine agent packs.

The cooperative project lock serializes this tool's writers.  A persistent,
same-filesystem recovery journal makes interrupted transactions recoverable.
It does not make multi-file updates atomically visible to lock-ignorant readers
or provide a filesystem-independent power-loss guarantee.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import threading
import tomllib
from typing import Callable, Iterator, Sequence
import unicodedata
import uuid


try:  # POSIX advisory locking.
    import fcntl  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on Windows.
    fcntl = None

try:  # Windows byte-range locking.
    import msvcrt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on POSIX.
    msvcrt = None


SUPPORTED_ENGINES = ("godot", "unity", "unreal")
ALLOWED_LANGUAGES = {
    "godot": frozenset({"gdscript", "csharp"}),
    "unity": frozenset({"csharp"}),
    "unreal": frozenset({"cpp", "blueprint", "cpp-blueprint"}),
}
VALID_REVIEW_MODES = frozenset({"full", "phase-gated", "solo"})
VALID_MODEL_POLICIES = frozenset({"balanced"})
EXPECTED_PACK_FILENAMES = {
    "godot": frozenset({"godot-csharp-specialist.toml", "godot-gdextension-specialist.toml", "godot-gdscript-specialist.toml", "godot-shader-specialist.toml", "godot-specialist.toml"}),
    "unity": frozenset({"unity-addressables-specialist.toml", "unity-dots-specialist.toml", "unity-shader-specialist.toml", "unity-specialist.toml", "unity-ui-specialist.toml"}),
    "unreal": frozenset({"ue-blueprint-specialist.toml", "ue-gas-specialist.toml", "ue-replication-specialist.toml", "ue-umg-specialist.toml", "unreal-specialist.toml"}),
}
STUDIO_KEYS = (
    "engine",
    "engine_version",
    "language",
    "review_mode",
    "active_engine_pack",
    "model_policy",
)
RECOVERY_NAME = "engine-pack-recovery"
LOCK_NAME = "engine-pack.lock"
JOURNAL_PHASES = frozenset({
    "prepared", "remove", "copy", "manifest-write", "config-write",
    "validated", "committed", "rollback-failed", "rolled-back",
})
JOURNAL_FIELDS = frozenset({
    "version", "phase", "project_root", "agents_existed", "manifest_existed",
    "config_existed", "agents_digest", "manifest_sha256", "config_sha256",
    "target_agents_existed", "target_manifest_existed", "target_config_existed",
    "target_agents_digest", "target_manifest_sha256", "target_config_sha256",
    "checksum",
})
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


@dataclasses.dataclass(frozen=True)
class StudioConfig:
    """Canonical six-field studio configuration."""

    engine: str
    engine_version: str
    language: str
    review_mode: str
    active_engine_pack: str
    model_policy: str


@dataclasses.dataclass(frozen=True)
class ActivationPlan:
    """Immutable plan bound to one project state and source-pack revision."""

    root: Path
    source_root: Path
    source_root_identity: tuple[int, int, int]
    source_pack_identity: tuple[int, int, int]
    engine: str
    install: tuple[Path, ...]
    remove: tuple[Path, ...]
    target_config: StudioConfig
    source_hashes: tuple[tuple[str, str], ...]
    state_digest: str
    no_op: bool


class ActivationRecoveryError(RuntimeError):
    """Raised when both activation and its durable rollback fail."""

    def __init__(self, original: BaseException, rollback: BaseException):
        self.original = original
        self.rollback = rollback
        super().__init__(f"activation failed: {original}; rollback failed: {rollback}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _link_kind(metadata: os.stat_result) -> str | None:
    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    reparse_tag = int(getattr(metadata, "st_reparse_tag", 0) or 0)
    if attributes & reparse_flag:
        if reparse_tag & 0x20000000:
            return "name-surrogate reparse point"
        return "reparse point or junction"
    if reparse_tag:
        return "name-surrogate reparse point" if reparse_tag & 0x20000000 else "reparse point"
    return None


def _checked_lstat(path: Path, label: str, *, missing_ok: bool = False) -> os.stat_result | None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ValueError(f"{label} is missing: {path}") from None
    kind = _link_kind(metadata)
    if kind:
        raise ValueError(f"{label} must not be a symlink, junction, or reparse/name-surrogate point ({kind}): {path}")
    return metadata


def _require_directory(path: Path, label: str) -> os.stat_result:
    metadata = _checked_lstat(path, label)
    assert metadata is not None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} is not a directory: {path}")
    return metadata


def _normalize_root(root: Path) -> Path:
    candidate = Path(root).absolute()
    _require_directory(candidate, "project root")
    return candidate.resolve()


def _normalize_source_root(source_root: Path | None, target_root: Path) -> Path:
    """Pin the immutable pack boundary independently of the mutation target."""

    if source_root is None:
        return target_root
    candidate = Path(source_root).absolute()
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if current == Path("/var"):
            continue  # macOS system alias; final root identity remains pinned.
        _require_directory(current, "engine pack source root ancestor")
    _require_directory(candidate, "engine pack source root")
    normalized = candidate.resolve()
    if normalized == target_root:
        raise ValueError("engine pack source root must differ from project root when explicitly supplied")
    return normalized


def _directory_identity(path: Path, label: str) -> tuple[int, int, int]:
    metadata = _require_directory(path, label)
    return (int(metadata.st_dev), int(metadata.st_ino), int(metadata.st_ctime_ns))


def _executing_bundled_studio_root() -> Path | None:
    """Return the immutable bundle boundary when this is a packaged script."""

    candidate = Path(__file__).resolve().parents[2]
    if candidate.name == "studio" and candidate.parent.name == "assets":
        return candidate
    return None


def _require_trusted_bundle_source(source_root: Path) -> None:
    bundled_root = _executing_bundled_studio_root()
    if bundled_root is not None and source_root != bundled_root:
        raise ValueError("engine pack source root must equal this executing bundled studio root")


def _control_directory(root: Path) -> Path:
    control = root / ".codex"
    _require_directory(control, "Codex control directory")
    return control


def _safe_filename(name: object) -> str:
    if (
        not isinstance(name, str)
        or not name
        or "/" in name
        or "\\" in name
        or Path(name).name != name
        or Path(name).is_absolute()
        or name in {".", ".."}
        or Path(name).suffix != ".toml"
        or re.fullmatch(r"[a-z0-9][a-z0-9-]*\.toml", name) is None
    ):
        raise ValueError("invalid or unsafe profile filename")
    return name


def _secure_read(path: Path, label: str) -> bytes:
    before = _checked_lstat(path, label)
    assert before is not None
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"{label} is not a regular file: {path}")
    flags = (
        os.O_RDONLY
        | int(getattr(os, "O_BINARY", 0))
        | int(getattr(os, "O_NOFOLLOW", 0))
    )
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"{label} became a link or non-regular file: {path}")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"{label} changed while it was opened: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_text(value: str, label: str, *, required: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if required and not value:
        raise ValueError(f"{label} is required")
    if value != value.strip():
        raise ValueError(f"{label} must not contain leading or trailing whitespace")
    if any(
        unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        for character in value
    ):
        raise ValueError(f"{label} must not contain control characters")
    return value


def _validate_target_values(engine: str, version: str, language: str, *, require_complete: bool) -> None:
    _validate_text(version, "engine version", required=require_complete)
    _validate_text(language, "primary language", required=require_complete)
    if language and language not in ALLOWED_LANGUAGES[engine]:
        allowed = ", ".join(sorted(ALLOWED_LANGUAGES[engine]))
        raise ValueError(f"primary language {language!r} is incompatible with {engine}; allowed: {allowed}")


def load_studio_config(root: Path) -> StudioConfig:
    """Load and strictly validate `.codex/studio.toml`."""

    root = _normalize_root(root)
    path = _control_directory(root) / "studio.toml"
    try:
        data = tomllib.loads(_secure_read(path, "studio config").decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as error:
        raise ValueError(f"invalid studio config: {error}") from error
    if set(data) != set(STUDIO_KEYS) or any(not isinstance(data.get(key), str) for key in STUDIO_KEYS):
        raise ValueError(f"invalid studio config fields: expected six string fields {list(STUDIO_KEYS)}")
    config = StudioConfig(**{key: data[key] for key in STUDIO_KEYS})
    if config.engine not in (*SUPPORTED_ENGINES, "unconfigured"):
        raise ValueError(f"invalid studio config engine: {config.engine}")
    if config.active_engine_pack not in (*SUPPORTED_ENGINES, "none"):
        raise ValueError(f"invalid studio config active_engine_pack: {config.active_engine_pack}")
    if config.engine == "unconfigured":
        if config.active_engine_pack != "none" or config.engine_version or config.language:
            raise ValueError("invalid studio config: unconfigured engine requires empty version/language and active_engine_pack = none")
    if config.engine in SUPPORTED_ENGINES and config.active_engine_pack != config.engine:
        raise ValueError("invalid studio config: engine and active_engine_pack differ")
    if config.engine in SUPPORTED_ENGINES:
        _validate_target_values(config.engine, config.engine_version, config.language, require_complete=True)
    _validate_text(config.review_mode, "review mode", required=True)
    _validate_text(config.model_policy, "model policy", required=True)
    if config.review_mode not in VALID_REVIEW_MODES:
        raise ValueError("invalid studio config review mode")
    if config.model_policy not in VALID_MODEL_POLICIES:
        raise ValueError("invalid studio config model policy")
    return config


def _validate_packs(
    root: Path, *, selected: frozenset[str] | None = None, external: bool = False,
) -> dict[str, tuple[tuple[Path, str], ...]]:
    """Validate all local packs or only the immutable packs needed by a plan."""

    selected = frozenset(SUPPORTED_ENGINES) if selected is None else selected
    if not selected or not selected <= set(SUPPORTED_ENGINES):
        raise ValueError("invalid selected engine-pack set")
    packs_root = _control_directory(root) / "agent-packs"
    _require_directory(packs_root, "engine packs directory")
    if external:
        entries = [packs_root / name for name in sorted(selected)]
    else:
        entries = sorted(packs_root.iterdir(), key=lambda path: path.name)
        if [entry.name for entry in entries] != list(SUPPORTED_ENGINES):
            raise ValueError("engine packs must contain exactly godot, unity, and unreal")
    result: dict[str, tuple[tuple[Path, str], ...]] = {}
    for directory in entries:
        _require_directory(directory, f"{directory.name} engine pack")
        if directory.name not in selected:
            continue
        children = sorted(directory.iterdir(), key=lambda path: path.name)
        profiles: list[tuple[Path, str]] = []
        for source in children:
            name = _safe_filename(source.name)
            raw = _secure_read(source, "engine pack source profile")
            try:
                profile = tomllib.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
                raise ValueError(f"invalid engine pack profile {source}: {error}") from error
            if profile.get("name") != Path(name).stem:
                raise ValueError(f"engine pack profile name must match filename: {name}")
            profiles.append((source, _sha256(raw)))
        if len(profiles) != 5:
            raise ValueError(f"engine pack {directory.name} must contain exactly five profiles")
        if external:
            expected = EXPECTED_PACK_FILENAMES[directory.name]
            if {source.name for source, _digest in profiles} != expected:
                raise ValueError(f"engine pack {directory.name} must contain exactly its canonical five profiles")
        result[directory.name] = tuple(profiles)
    return result


def _source_pack_selection(
    source_root: Path, target_root: Path, config: StudioConfig, requested_engine: str | None,
) -> frozenset[str] | None:
    """Keep legacy project-local inventory checks while minimizing bundle reads."""

    if source_root == target_root:
        return None
    engines = {requested_engine} if requested_engine is not None else set()
    if config.engine in SUPPORTED_ENGINES:
        engines.add(config.engine)
    return frozenset(engines)


def _load_manifest(
    root: Path,
    config: StudioConfig,
    packs: dict[str, tuple[tuple[Path, str], ...]],
) -> dict[str, object] | None:
    path = _control_directory(root) / "active-engine.json"
    metadata = _checked_lstat(path, "active-engine manifest", missing_ok=True)
    if metadata is None:
        if config.engine != "unconfigured" or config.active_engine_pack != "none":
            raise ValueError("active-engine manifest is missing for configured engine")
        return None
    try:
        data = json.loads(_secure_read(path, "active-engine manifest").decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid active-engine manifest: {error}") from error
    if not isinstance(data, dict) or set(data) != {"engine", "generated"}:
        raise ValueError("invalid active-engine manifest schema")
    engine = data.get("engine")
    generated = data.get("generated")
    if engine not in SUPPORTED_ENGINES or not isinstance(generated, dict):
        raise ValueError("invalid active-engine manifest engine or generated map")
    if engine not in packs:
        raise ValueError("active-engine manifest is inconsistent with unconfigured studio state")
    normalized: dict[str, str] = {}
    for raw_name, raw_hash in generated.items():
        name = _safe_filename(raw_name)
        if not isinstance(raw_hash, str) or len(raw_hash) != 64:
            raise ValueError(f"invalid active-engine manifest hash for {name}")
        try:
            int(raw_hash, 16)
        except ValueError as error:
            raise ValueError(f"invalid active-engine manifest hash for {name}") from error
        normalized[name] = raw_hash.lower()
    expected = {source.name: digest for source, digest in packs[str(engine)]}
    if normalized != expected:
        raise ValueError("active-engine manifest generated ownership does not exactly match its declared immutable source pack")
    if config.engine != engine or config.active_engine_pack != engine:
        raise ValueError("active-engine manifest and studio config disagree")
    return {"engine": engine, "generated": normalized}


def _agents_directory(root: Path, *, create: bool = False) -> Path:
    agents = _control_directory(root) / "agents"
    metadata = _checked_lstat(agents, "active agents directory", missing_ok=True)
    if metadata is None and create:
        os.mkdir(agents, 0o755)
        metadata = _checked_lstat(agents, "active agents directory")
    if metadata is not None and not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("active agents path is not a directory")
    return agents


def _validate_managed_profiles(root: Path, manifest: dict[str, object] | None) -> dict[str, str]:
    agents = _agents_directory(root)
    if manifest is None:
        return {}
    generated = manifest["generated"]
    assert isinstance(generated, dict)
    if _checked_lstat(agents, "active agents directory", missing_ok=True) is None:
        raise ValueError("active agents directory is missing")
    result: dict[str, str] = {}
    for name, expected in sorted(generated.items()):
        assert isinstance(name, str) and isinstance(expected, str)
        raw = _secure_read(agents / name, "generated profile")
        actual = _sha256(raw)
        if actual != expected:
            raise ValueError(f"generated profile was modified: {name}")
        result[name] = expected
    return result


def _tree_digest(path: Path) -> bytes:
    metadata = _checked_lstat(path, "active agents directory", missing_ok=True)
    if metadata is None:
        return b"ABSENT\0"
    if not stat.S_ISDIR(metadata.st_mode):
        return b"NON_DIRECTORY\0"
    records: list[bytes] = []
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        name = item.relative_to(path).as_posix().encode("utf-8", "surrogateescape")
        item_metadata = os.lstat(item)
        kind = _link_kind(item_metadata)
        if kind:
            records.extend((b"L\0", name, b"\0", os.readlink(item).encode("utf-8", "surrogateescape"), b"\0"))
        elif stat.S_ISDIR(item_metadata.st_mode):
            records.extend((b"D\0", name, b"\0"))
        elif stat.S_ISREG(item_metadata.st_mode):
            records.extend((b"F\0", name, b"\0", hashlib.sha256(_secure_read(item, "agent file")).digest()))
        else:
            records.extend((b"O\0", name, b"\0"))
    return b"".join(records)


def _state_digest(root: Path) -> str:
    digest = hashlib.sha256()
    control = _control_directory(root)
    for name in ("studio.toml", "active-engine.json"):
        path = control / name
        digest.update(name.encode() + b"\0")
        metadata = _checked_lstat(path, name, missing_ok=True)
        digest.update(b"A\0" if metadata is None else b"F\0" + _secure_read(path, name))
    digest.update(b"agents\0" + _tree_digest(control / "agents"))
    return digest.hexdigest()


def _snapshot_live(root: Path) -> dict[str, object]:
    """Capture logical agents/manifest/config presence and content digests."""

    root = _normalize_root(root)
    control = _control_directory(root)
    agents = control / "agents"
    agents_meta = _checked_lstat(agents, "active agents directory", missing_ok=True)
    if agents_meta is not None and not stat.S_ISDIR(agents_meta.st_mode):
        raise ValueError("live agents path is not a directory")
    snapshot: dict[str, object] = {
        "agents_existed": agents_meta is not None,
        "agents_digest": _sha256(_tree_digest(agents)) if agents_meta is not None else None,
    }
    for noun, filename, digest_name in (
        ("manifest", "active-engine.json", "manifest_sha256"),
        ("config", "studio.toml", "config_sha256"),
    ):
        path = control / filename
        metadata = _checked_lstat(path, f"live {noun}", missing_ok=True)
        snapshot[f"{noun}_existed"] = metadata is not None
        snapshot[digest_name] = _sha256(_secure_read(path, f"live {noun}")) if metadata is not None else None
    return snapshot


def _target_fields(snapshot: dict[str, object]) -> dict[str, object]:
    return {f"target_{key}": value for key, value in snapshot.items()}


def _verify_live_snapshot(root: Path, journal: dict[str, object], *, target: bool) -> None:
    actual = _snapshot_live(root)
    prefix = "target_" if target else ""
    expected = {key: journal[f"{prefix}{key}"] for key in actual}
    if actual != expected:
        label = "target" if target else "original"
        raise ValueError(f"live state does not match recorded {label} recovery snapshot")


def _journal_path(recovery: Path) -> Path:
    return recovery / "journal.json"


def _journal_checksum(journal: dict[str, object]) -> str:
    """Return the canonical checksum of all journal fields except checksum."""

    payload = {key: value for key, value in journal.items() if key != "checksum"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _sha256(canonical)


def _validate_backup_pair(
    recovery: Path,
    journal: dict[str, object],
    existed_key: str,
    digest_key: str,
    backup_name: str,
    absent_name: str,
    *,
    directory: bool,
) -> None:
    existed = bool(journal[existed_key])
    backup = recovery / backup_name
    absent = recovery / absent_name
    backup_meta = _checked_lstat(backup, f"recovery {backup_name}", missing_ok=True)
    absent_meta = _checked_lstat(absent, f"recovery {absent_name}", missing_ok=True)
    if existed:
        if backup_meta is None or absent_meta is not None:
            raise ValueError(f"corrupt recovery artifact/flag disagreement for {backup_name}")
        if directory and not stat.S_ISDIR(backup_meta.st_mode):
            raise ValueError(f"corrupt recovery directory artifact for {backup_name}")
        if not directory and not stat.S_ISREG(backup_meta.st_mode):
            raise ValueError(f"corrupt recovery file artifact for {backup_name}")
        actual = _sha256(_tree_digest(backup)) if directory else _sha256(_secure_read(backup, f"recovery {backup_name}"))
        if actual != journal[digest_key]:
            raise ValueError(f"corrupt recovery {backup_name} digest")
    else:
        if backup_meta is not None or absent_meta is None or not stat.S_ISREG(absent_meta.st_mode):
            raise ValueError(f"corrupt recovery absence artifact/flag disagreement for {backup_name}")
        if _secure_read(absent, f"recovery {absent_name}") != b"":
            raise ValueError(f"corrupt recovery absence marker for {backup_name}")


def _read_journal(recovery: Path, root: Path) -> dict[str, object]:
    _require_directory(recovery, "engine-pack recovery directory")
    try:
        data = json.loads(_secure_read(_journal_path(recovery), "engine-pack recovery journal").decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid engine-pack recovery journal: {error}") from error
    if not isinstance(data, dict) or set(data) != JOURNAL_FIELDS:
        raise ValueError("corrupt engine-pack recovery journal schema")
    if data.get("version") != 1 or data.get("project_root") != str(_normalize_root(root)):
        raise ValueError("corrupt engine-pack recovery journal version or project-root binding")
    checksum = data.get("checksum")
    if not isinstance(checksum, str) or re.fullmatch(r"[0-9a-f]{64}", checksum) is None or checksum != _journal_checksum(data):
        raise ValueError("corrupt engine-pack recovery journal checksum")
    if data.get("phase") not in JOURNAL_PHASES:
        raise ValueError("corrupt engine-pack recovery journal phase")
    boolean_keys = {
        "agents_existed", "manifest_existed", "config_existed",
        "target_agents_existed", "target_manifest_existed", "target_config_existed",
    }
    digest_keys = {
        "agents_digest", "manifest_sha256", "config_sha256",
        "target_agents_digest", "target_manifest_sha256", "target_config_sha256",
    }
    if (
        not isinstance(data["phase"], str)
        or any(not isinstance(data[key], bool) for key in boolean_keys)
        or any(data[key] is not None and (not isinstance(data[key], str) or re.fullmatch(r"[0-9a-f]{64}", data[key]) is None) for key in digest_keys)
    ):
        raise ValueError("corrupt engine-pack recovery journal values or digest syntax")
    for prefix in ("", "target_"):
        for noun, digest in (("agents", "agents_digest"), ("manifest", "manifest_sha256"), ("config", "config_sha256")):
            existed_key = f"{prefix}{noun}_existed"
            digest_key = f"{prefix}{digest}"
            if bool(data[existed_key]) != (data[digest_key] is not None):
                raise ValueError(f"corrupt recovery flag/digest disagreement for {existed_key}")
    if data["phase"] in {"validated", "committed"} and not all(
        bool(data[key]) for key in ("target_agents_existed", "target_manifest_existed", "target_config_existed")
    ):
        raise ValueError("corrupt committed recovery target metadata")
    _validate_backup_pair(recovery, data, "agents_existed", "agents_digest", "backup-agents", "agents-absent", directory=True)
    _validate_backup_pair(recovery, data, "manifest_existed", "manifest_sha256", "backup-manifest", "backup-manifest-absent", directory=False)
    _validate_backup_pair(recovery, data, "config_existed", "config_sha256", "backup-config", "backup-config-absent", directory=False)
    return data


def _inspect_auxiliary_paths(root: Path) -> tuple[Path, dict[str, object] | None]:
    control = _control_directory(root)
    lock_path = control / LOCK_NAME
    lock_metadata = _checked_lstat(lock_path, "engine-pack lock", missing_ok=True)
    if lock_metadata is not None and not stat.S_ISREG(lock_metadata.st_mode):
        raise ValueError("engine-pack lock is not a regular file")
    recovery = control / RECOVERY_NAME
    recovery_metadata = _checked_lstat(recovery, "engine-pack recovery directory", missing_ok=True)
    if recovery_metadata is None:
        return recovery, None
    return recovery, _read_journal(recovery, root)


def plan_activation(
    root: Path,
    engine: str,
    *,
    version: str = "",
    language: str = "",
    source_root: Path | None = None,
) -> ActivationPlan:
    """Build a deterministic, read-only activation plan."""

    root = _normalize_root(root)
    source_root = _normalize_source_root(source_root, root)
    _require_trusted_bundle_source(source_root)
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"unsupported engine: {engine}")
    _validate_target_values(engine, version, language, require_complete=False)
    _recovery, journal = _inspect_auxiliary_paths(root)
    if journal is not None and journal["phase"] not in {"committed", "rolled-back"}:
        raise ValueError("incomplete engine-pack recovery journal; run the CLI with --recover before planning")
    config = load_studio_config(root)
    packs = _validate_packs(
        source_root,
        selected=_source_pack_selection(source_root, root, config, engine),
        external=source_root != root,
    )
    manifest = _load_manifest(root, config, packs)
    managed = _validate_managed_profiles(root, manifest)
    selected = packs[engine]
    selected_hashes = tuple((source.name, digest) for source, digest in selected)
    source_root_identity = (
        _directory_identity(source_root, "engine pack source root")
        if source_root != root else (0, 0, 0)
    )
    source_pack_identity = (
        _directory_identity(source_root / ".codex/agent-packs" / engine, "selected engine pack")
        if source_root != root else (0, 0, 0)
    )
    agents = _agents_directory(root)
    for source, _digest in selected:
        target = agents / source.name
        target_metadata = _checked_lstat(target, "target profile", missing_ok=True)
        if target_metadata is not None and source.name not in managed:
            raise ValueError(f"unmanaged profile collision: {source.name}")
    target_config = dataclasses.replace(
        config,
        engine=engine,
        engine_version=version,
        language=language,
        active_engine_pack=engine,
    )
    same_profiles = bool(manifest) and manifest["engine"] == engine and dict(selected_hashes) == managed
    install = () if same_profiles else tuple(source for source, _digest in selected)
    remove = () if same_profiles else tuple(agents / name for name in sorted(managed))
    return ActivationPlan(
        root=root,
        source_root=source_root,
        source_root_identity=source_root_identity,
        source_pack_identity=source_pack_identity,
        engine=engine,
        install=install,
        remove=remove,
        target_config=target_config,
        source_hashes=selected_hashes,
        state_digest=_state_digest(root),
        no_op=same_profiles and target_config == config,
    )


def _serialize_config(config: StudioConfig) -> bytes:
    """Serialize studio configuration deterministically as TOML-safe strings."""

    values = dataclasses.asdict(config)
    return "".join(f"{key} = {json.dumps(values[key], ensure_ascii=False)}\n" for key in STUDIO_KEYS).encode("utf-8")


def _serialize_manifest(engine: str, generated: dict[str, str]) -> bytes:
    return (json.dumps({"engine": engine, "generated": dict(sorted(generated.items()))}, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    parent = path.parent
    _require_directory(parent, f"parent directory for {path.name}")
    existing = _checked_lstat(path, f"atomic-write target {path.name}", missing_ok=True)
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise ValueError(f"atomic-write target is not a regular file: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _write_journal(recovery: Path, journal: dict[str, object], phase: str) -> None:
    journal["phase"] = phase
    journal["checksum"] = _journal_checksum(journal)
    _atomic_write(_journal_path(recovery), (json.dumps(journal, sort_keys=True, indent=2) + "\n").encode())


def _copy_agents(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True)


def _create_recovery(root: Path) -> tuple[Path, dict[str, object]]:
    control = _control_directory(root)
    recovery = control / RECOVERY_NAME
    if _checked_lstat(recovery, "engine-pack recovery directory", missing_ok=True) is not None:
        raise ValueError("engine-pack recovery directory already exists")
    stage = control / f".{RECOVERY_NAME}-stage-{uuid.uuid4().hex}"
    os.mkdir(stage, 0o700)
    journal: dict[str, object] = {
        "version": 1,
        "phase": "prepared",
        "project_root": str(root),
        "agents_existed": False,
        "manifest_existed": False,
        "config_existed": False,
        "agents_digest": None,
        "manifest_sha256": None,
        "config_sha256": None,
        "target_agents_existed": False,
        "target_manifest_existed": False,
        "target_config_existed": False,
        "target_agents_digest": None,
        "target_manifest_sha256": None,
        "target_config_sha256": None,
        "checksum": "",
    }
    try:
        agents = _agents_directory(root)
        agents_metadata = _checked_lstat(agents, "active agents directory", missing_ok=True)
        journal["agents_existed"] = agents_metadata is not None
        if agents_metadata is not None:
            _copy_agents(agents, stage / "backup-agents")
            journal["agents_digest"] = _sha256(_tree_digest(stage / "backup-agents"))
        else:
            (stage / "agents-absent").write_bytes(b"")
        for key, name, backup_name in (
            ("manifest_existed", "active-engine.json", "backup-manifest"),
            ("config_existed", "studio.toml", "backup-config"),
        ):
            path = control / name
            metadata = _checked_lstat(path, name, missing_ok=True)
            journal[key] = metadata is not None
            if metadata is not None:
                original = _secure_read(path, name)
                (stage / backup_name).write_bytes(original)
                journal["manifest_sha256" if key == "manifest_existed" else "config_sha256"] = _sha256(original)
            else:
                (stage / f"{backup_name}-absent").write_bytes(b"")
        journal["checksum"] = _journal_checksum(journal)
        (stage / "journal.json").write_bytes((json.dumps(journal, sort_keys=True, indent=2) + "\n").encode())
        os.replace(stage, recovery)
    except BaseException:
        if stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    return recovery, journal


def _failed_name(recovery: Path, label: str) -> Path:
    return recovery / f"failed-{label}-{uuid.uuid4().hex}"


def _restore_file(control: Path, recovery: Path, target_name: str, backup_name: str, existed: bool) -> None:
    target = control / target_name
    target_metadata = _checked_lstat(target, target_name, missing_ok=True)
    if existed:
        backup = recovery / backup_name
        content = _secure_read(backup, f"recovery {backup_name}")
        _atomic_write(target, content)
    elif target_metadata is not None:
        os.replace(target, _failed_name(recovery, target_name))


def _restore_backup(root: Path, recovery: Path, journal: dict[str, object]) -> None:
    """Restore logical state while retaining the only good backup on failure."""

    control = _control_directory(root)
    if bool(journal["agents_existed"]):
        actual_agents_digest = _sha256(_tree_digest(recovery / "backup-agents"))
        if actual_agents_digest != journal["agents_digest"]:
            raise ValueError("recovery agent-tree backup hash does not match journal")
    for existed_key, backup_name, digest_key in (
        ("manifest_existed", "backup-manifest", "manifest_sha256"),
        ("config_existed", "backup-config", "config_sha256"),
    ):
        if bool(journal[existed_key]):
            if _sha256(_secure_read(recovery / backup_name, f"recovery {backup_name}")) != journal[digest_key]:
                raise ValueError(f"recovery {backup_name} hash does not match journal")
    agents = control / "agents"
    agents_metadata = _checked_lstat(agents, "active agents directory", missing_ok=True)
    if bool(journal["agents_existed"]):
        backup = recovery / "backup-agents"
        _require_directory(backup, "recovery agent backup")
        restore = recovery / f"restore-agents-{uuid.uuid4().hex}"
        _copy_agents(backup, restore)
        if agents_metadata is not None:
            os.replace(agents, _failed_name(recovery, "agents"))
        os.replace(restore, agents)
    elif agents_metadata is not None:
        os.replace(agents, _failed_name(recovery, "agents"))
    _restore_file(control, recovery, "active-engine.json", "backup-manifest", bool(journal["manifest_existed"]))
    _restore_file(control, recovery, "studio.toml", "backup-config", bool(journal["config_existed"]))
    _verify_live_snapshot(root, journal, target=False)
    _write_journal(recovery, journal, "rolled-back")
    _retire_recovery(recovery)


def _retire_recovery(recovery: Path) -> None:
    retired = recovery.parent / f".{RECOVERY_NAME}-retired-{uuid.uuid4().hex}"
    os.replace(recovery, retired)
    try:
        shutil.rmtree(retired)
    except OSError:
        # Logical state and the canonical journal path are already terminal.
        # A later housekeeping pass may remove the uniquely named artifact.
        pass


def _try_os_lock(descriptor: int) -> None:
    if fcntl is not None:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("engine-pack activation is locked by another writer") from error
    elif msvcrt is not None:  # pragma: no cover - Windows only.
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ValueError("engine-pack activation is locked by another writer") from error


def _unlock_os(descriptor: int) -> None:
    if fcntl is not None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    elif msvcrt is not None:  # pragma: no cover - Windows only.
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def _activation_lock(root: Path) -> Iterator[None]:
    control = _control_directory(root)
    lock_path = control / LOCK_NAME
    existing = _checked_lstat(lock_path, "engine-pack lock", missing_ok=True)
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise ValueError("engine-pack lock is not a regular file")
    key = str(root)
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, threading.Lock())
    if not thread_lock.acquire(blocking=False):
        raise ValueError("engine-pack activation is locked by another writer")
    descriptor = -1
    os_locked = False
    try:
        flags = os.O_RDWR | os.O_CREAT | int(getattr(os, "O_NOFOLLOW", 0))
        descriptor = os.open(lock_path, flags, 0o600)
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError("engine-pack lock became a link or non-regular file")
        named = _checked_lstat(lock_path, "engine-pack lock")
        assert named is not None
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("engine-pack lock changed while it was opened")
        _try_os_lock(descriptor)
        os_locked = True
        named_after_lock = _checked_lstat(lock_path, "engine-pack lock")
        assert named_after_lock is not None
        if (named_after_lock.st_dev, named_after_lock.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("engine-pack lock changed while the lock was acquired")
        yield
    finally:
        try:
            if descriptor >= 0:
                try:
                    if os_locked:
                        _unlock_os(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            thread_lock.release()


def _cleanup_terminal_recovery(root: Path, recovery: Path, journal: dict[str, object] | None) -> None:
    if journal is not None and journal["phase"] in {"committed", "rolled-back"}:
        _verify_live_snapshot(root, journal, target=journal["phase"] == "committed")
        _retire_recovery(recovery)


def recover_activation(root: Path) -> None:
    """Deterministically recover an incomplete persistent transaction."""

    root = _normalize_root(root)
    with _activation_lock(root):
        recovery, journal = _inspect_auxiliary_paths(root)
        if journal is None:
            return
        if journal["phase"] in {"committed", "rolled-back"}:
            _cleanup_terminal_recovery(root, recovery, journal)
            return
        _restore_backup(root, recovery, journal)


def rollback_activation(root: Path) -> None:
    """Compatibility entry point for explicitly recovering a failed activation."""

    recover_activation(root)


def _exclusive_profile_write(agents: Path, name: str, content: bytes) -> None:
    _safe_filename(name)
    _require_directory(agents, "active agents directory")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | int(getattr(os, "O_BINARY", 0))
        | int(getattr(os, "O_NOFOLLOW", 0))
    )
    directory_flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0))
    before_parent = _require_directory(agents, "active agents directory")
    directory_descriptor = -1
    descriptor = -1
    try:
        supports_dir_fd = os.open in getattr(os, "supports_dir_fd", set())
        if supports_dir_fd:
            directory_descriptor = os.open(agents, directory_flags)
            try:
                descriptor = os.open(name, flags, 0o644, dir_fd=directory_descriptor)
            except FileExistsError as error:
                raise ValueError(f"concurrent unmanaged profile collision: {name}") from error
        else:  # Safe standard-library fallback for platforms without dir_fd.
            target = agents / name
            if _checked_lstat(target, "target profile", missing_ok=True) is not None:
                raise ValueError(f"concurrent unmanaged profile collision: {name}")
            try:
                descriptor = os.open(target, flags, 0o644)
            except FileExistsError as error:
                raise ValueError(f"concurrent unmanaged profile collision: {name}") from error
            after_parent = _require_directory(agents, "active agents directory")
            if (before_parent.st_dev, before_parent.st_ino) != (after_parent.st_dev, after_parent.st_ino):
                raise ValueError("active agents directory changed during exclusive destination creation")
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"target profile became a link or non-regular file: {name}")
        named_target = _checked_lstat(agents / name, "new target profile")
        assert named_target is not None
        if (named_target.st_dev, named_target.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"target profile changed while it was opened: {name}")
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _unlink_managed(path: Path) -> None:
    metadata = _checked_lstat(path, "managed profile")
    assert metadata is not None
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"managed profile is not a regular file: {path.name}")
    path.unlink()


def _checkpoint(_phase: str) -> None:
    return None


def validate_activation(
    root: Path,
    *,
    source_root: Path | None = None,
    _allow_current_transaction: bool = False,
) -> list[str]:
    """Return validation errors for the installed engine-pack state."""

    try:
        root = _normalize_root(root)
        source_root = _normalize_source_root(source_root, root)
        _require_trusted_bundle_source(source_root)
        recovery, journal = _inspect_auxiliary_paths(root)
        if journal is not None:
            if journal["phase"] in {"committed", "rolled-back"}:
                _verify_live_snapshot(root, journal, target=journal["phase"] == "committed")
            elif not _allow_current_transaction:
                raise ValueError("incomplete engine-pack recovery transaction is pending")
        config = load_studio_config(root)
        packs = (
            {} if source_root != root and config.engine == "unconfigured" else _validate_packs(
                source_root,
                selected=_source_pack_selection(source_root, root, config, None),
                external=source_root != root,
            )
        )
        manifest = _load_manifest(root, config, packs)
        managed = _validate_managed_profiles(root, manifest)
        if config.engine == "unconfigured":
            if manifest is not None or managed:
                raise ValueError("unconfigured studio must not have an active manifest")
        elif manifest is None or len(managed) != 5:
            raise ValueError("configured studio must have five managed profiles")
    except (OSError, ValueError) as error:
        return [str(error)]
    return []


def _assert_plan_current(root: Path, plan: ActivationPlan) -> None:
    if plan.engine not in SUPPORTED_ENGINES:
        raise ValueError("invalid activation plan engine")
    source_root = _normalize_source_root(
        plan.source_root if plan.source_root != root else None, root
    )
    if source_root != plan.source_root:
        raise ValueError("invalid activation plan source root")
    _require_trusted_bundle_source(source_root)
    if source_root != root and _directory_identity(source_root, "engine pack source root") != plan.source_root_identity:
        raise ValueError("source root identity changed after activation planning (concurrent source replacement)")
    if source_root != root and _directory_identity(source_root / ".codex/agent-packs" / plan.engine, "selected engine pack") != plan.source_pack_identity:
        raise ValueError("selected source pack identity changed after activation planning")
    packs = _validate_packs(
        source_root,
        selected=frozenset({plan.engine}) if source_root != root else None,
        external=source_root != root,
    )
    current_hashes = tuple((source.name, digest) for source, digest in packs[plan.engine])
    if current_hashes != plan.source_hashes:
        raise ValueError("source pack changed after activation planning")
    if _state_digest(root) != plan.state_digest:
        raise ValueError("stale activation plan: project state changed after planning")
    expected = plan_activation(
        root,
        plan.engine,
        version=plan.target_config.engine_version,
        language=plan.target_config.language,
        source_root=plan.source_root if plan.source_root != root else None,
    )
    if expected != plan:
        raise ValueError("invalid activation plan: paths or target configuration were modified concurrently")


def apply_activation(root: Path, plan: ActivationPlan) -> None:
    """Apply a plan under an exclusive lock with persistent rollback state."""

    root = _normalize_root(root)
    if root != plan.root:
        raise ValueError("activation plan belongs to a different project root")
    if plan.engine not in SUPPORTED_ENGINES:
        raise ValueError("invalid activation plan engine")
    _validate_target_values(
        plan.engine,
        plan.target_config.engine_version,
        plan.target_config.language,
        require_complete=True,
    )
    _validate_text(plan.target_config.review_mode, "review mode", required=True)
    _validate_text(plan.target_config.model_policy, "model policy", required=True)
    with _activation_lock(root):
        recovery, journal = _inspect_auxiliary_paths(root)
        if journal is not None:
            if journal["phase"] in {"committed", "rolled-back"}:
                _cleanup_terminal_recovery(root, recovery, journal)
            else:
                _restore_backup(root, recovery, journal)
        _assert_plan_current(root, plan)
        if plan.no_op:
            return
        _checkpoint("after-revalidation")
        recovery, journal = _create_recovery(root)
        try:
            agents = _agents_directory(root, create=True)
            for target in plan.remove:
                _unlink_managed(target)
            _write_journal(recovery, journal, "remove")
            _checkpoint("remove")
            expected_hashes = dict(plan.source_hashes)
            for source in plan.install:
                if plan.source_root != root and _directory_identity(plan.source_root / ".codex/agent-packs" / plan.engine, "selected engine pack") != plan.source_pack_identity:
                    raise ValueError("selected source pack identity changed during activation")
                raw = _secure_read(source, "engine pack source profile")
                if _sha256(raw) != expected_hashes[source.name]:
                    raise ValueError("source pack changed during activation")
                _exclusive_profile_write(agents, source.name, raw)
            if plan.source_root != root and _directory_identity(plan.source_root, "engine pack source root") != plan.source_root_identity:
                raise ValueError("source root identity changed during activation")
            _write_journal(recovery, journal, "copy")
            _checkpoint("copy")
            if plan.install or plan.remove:
                _atomic_write(root / ".codex/active-engine.json", _serialize_manifest(plan.engine, expected_hashes))
            _write_journal(recovery, journal, "manifest-write")
            _checkpoint("manifest-write")
            _checkpoint("second-replace")
            _atomic_write(root / ".codex/studio.toml", _serialize_config(plan.target_config))
            _write_journal(recovery, journal, "config-write")
            _checkpoint("config-write")
            issues = validate_activation(
                root,
                source_root=plan.source_root if plan.source_root != root else None,
                _allow_current_transaction=True,
            )
            if issues:
                raise ValueError("post-apply validation failed: " + "; ".join(issues))
            journal.update(_target_fields(_snapshot_live(root)))
            _write_journal(recovery, journal, "validated")
            _checkpoint("post-validation")
            _write_journal(recovery, journal, "committed")
            _cleanup_terminal_recovery(root, recovery, journal)
        except BaseException as original:
            try:
                _restore_backup(root, recovery, journal)
            except BaseException as rollback:
                try:
                    _write_journal(recovery, journal, "rollback-failed")
                except BaseException:
                    pass
                raise ActivationRecoveryError(original, rollback) from original
            raise


def _print_plan(root: Path, plan: ActivationPlan, stream: object = sys.stdout) -> None:
    write: Callable[[str], object] = getattr(stream, "write")
    write(f"ENGINE {plan.engine}\n")
    for source in plan.install:
        if plan.source_root == root:
            label = source.relative_to(root).as_posix()
        else:
            label = f"SOURCE {source.relative_to(plan.source_root).as_posix()}"
        write(f"INSTALL {label} -> .codex/agents/{source.name}\n")
    for target in plan.remove:
        write(f"REMOVE {target.relative_to(root).as_posix()}\n")
    config = plan.target_config
    write(
        "CONFIG "
        f"engine={config.engine} engine_version={config.engine_version} language={config.language} "
        f"active_engine_pack={config.active_engine_pack} review_mode={config.review_mode} "
        f"model_policy={config.model_policy}\n"
    )
    if plan.no_op:
        write("NO-OP active pack and configuration already match\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan, apply, or recover a Codex engine-agent pack transaction")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--engine", choices=SUPPORTED_ENGINES)
    parser.add_argument("--version", default="")
    parser.add_argument("--language", default="")
    parser.add_argument("--source-root", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--recover", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    options = parser.parse_args(arguments)
    root = options.root
    if options.recover:
        if options.engine or options.version or options.language or options.source_root is not None:
            parser.error("--recover does not accept --engine, --version, --language, or --source-root")
        try:
            recover_activation(root)
            print("Engine-pack recovery complete")
            return 0
        except (OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
    if not options.engine:
        parser.error("--engine is required for --dry-run and --apply")
    try:
        _validate_target_values(options.engine, options.version, options.language, require_complete=options.apply)
        plan = plan_activation(
            root, options.engine, version=options.version, language=options.language,
            source_root=options.source_root,
        )
        _print_plan(plan.root, plan)
        if options.apply:
            apply_activation(plan.root, plan)
            issues = validate_activation(
                plan.root,
                source_root=plan.source_root if plan.source_root != plan.root else None,
            )
            if issues:
                raise ValueError("post-apply validation failed: " + "; ".join(issues))
            print(f"Activated {options.engine} with 5 managed profiles")
    except (OSError, ValueError, ActivationRecoveryError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
