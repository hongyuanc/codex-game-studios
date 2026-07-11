from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib
from typing import Callable, Sequence


SUPPORTED_ENGINES = ("godot", "unity", "unreal")
STUDIO_KEYS = (
    "engine",
    "engine_version",
    "language",
    "review_mode",
    "active_engine_pack",
    "model_policy",
)


@dataclasses.dataclass(frozen=True)
class StudioConfig:
    engine: str
    engine_version: str
    language: str
    review_mode: str
    active_engine_pack: str
    model_policy: str


@dataclasses.dataclass(frozen=True)
class ActivationPlan:
    root: Path
    engine: str
    install: tuple[Path, ...]
    remove: tuple[Path, ...]
    target_config: StudioConfig
    source_hashes: tuple[tuple[str, str], ...]
    state_digest: str
    no_op: bool


@dataclasses.dataclass(frozen=True)
class _Backup:
    directory: Path
    agents_existed: bool
    manifest_existed: bool
    config_existed: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_filename(name: object) -> str:
    if (
        not isinstance(name, str)
        or not name
        or "/" in name
        or "\\" in name
        or Path(name).name != name
        or Path(name).is_absolute()
    ):
        raise ValueError("active-engine manifest contains an unsafe generated filename")
    if Path(name).suffix != ".toml" or name in {".", ".."}:
        raise ValueError("active-engine manifest contains an invalid generated filename")
    return name


def _read_regular_file(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"{label} is missing or not a regular file: {path}")
    return path.read_bytes()


def _control_directory(root: Path) -> Path:
    control = root / ".codex"
    if control.is_symlink():
        raise ValueError("Codex control directory must not be a symlink")
    if not control.is_dir():
        raise ValueError("Codex control directory is missing or not a directory")
    return control


def load_studio_config(root: Path) -> StudioConfig:
    root = Path(root).resolve()
    path = _control_directory(root) / "studio.toml"
    try:
        raw = _read_regular_file(path, "studio config")
        data = tomllib.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as error:
        raise ValueError(f"invalid studio config: {error}") from error
    if set(data) != set(STUDIO_KEYS):
        raise ValueError(f"invalid studio config fields: expected {list(STUDIO_KEYS)}")
    if any(not isinstance(data[key], str) for key in STUDIO_KEYS):
        raise ValueError("invalid studio config: all fields must be strings")
    config = StudioConfig(**{key: data[key] for key in STUDIO_KEYS})
    if config.engine not in (*SUPPORTED_ENGINES, "unconfigured"):
        raise ValueError(f"invalid studio config engine: {config.engine}")
    if config.active_engine_pack not in (*SUPPORTED_ENGINES, "none"):
        raise ValueError(f"invalid studio config active_engine_pack: {config.active_engine_pack}")
    if config.engine == "unconfigured" and config.active_engine_pack != "none":
        raise ValueError("invalid studio config: unconfigured engine requires active_engine_pack = none")
    if config.engine in SUPPORTED_ENGINES and config.active_engine_pack != config.engine:
        raise ValueError("invalid studio config: engine and active_engine_pack differ")
    return config


def _load_manifest(root: Path, config: StudioConfig) -> dict[str, object] | None:
    path = root / ".codex/active-engine.json"
    if not path.exists() and not path.is_symlink():
        if config.engine != "unconfigured" or config.active_engine_pack != "none":
            raise ValueError("active-engine manifest is missing for configured engine")
        return None
    try:
        raw = _read_regular_file(path, "active-engine manifest")
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid active-engine manifest: {error}") from error
    if not isinstance(data, dict) or set(data) != {"engine", "generated"}:
        raise ValueError("invalid active-engine manifest schema")
    engine = data.get("engine")
    generated = data.get("generated")
    if engine not in SUPPORTED_ENGINES or not isinstance(generated, dict):
        raise ValueError("invalid active-engine manifest engine or generated map")
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
    if len(normalized) != 5:
        raise ValueError("invalid active-engine manifest: exactly five generated profiles are required")
    if config.engine != engine or config.active_engine_pack != engine:
        raise ValueError("active-engine manifest and studio config disagree")
    return {"engine": engine, "generated": normalized}


def _validate_packs(root: Path) -> dict[str, tuple[tuple[Path, str], ...]]:
    packs_root = root / ".codex/agent-packs"
    if packs_root.is_symlink() or not packs_root.is_dir():
        raise ValueError("engine pack directory is missing or symlinked")
    entries = sorted(packs_root.iterdir(), key=lambda path: path.name)
    if [entry.name for entry in entries] != list(SUPPORTED_ENGINES):
        raise ValueError("engine packs must contain exactly godot, unity, and unreal")
    result: dict[str, tuple[tuple[Path, str], ...]] = {}
    for directory in entries:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"engine pack must be a regular directory, not a symlink: {directory}")
        children = sorted(directory.iterdir(), key=lambda path: path.name)
        if len(children) != 5:
            raise ValueError(f"engine pack {directory.name} must contain exactly five profiles")
        profiles: list[tuple[Path, str]] = []
        for source in children:
            if source.suffix != ".toml" or Path(source.name).name != source.name:
                raise ValueError(f"engine pack {directory.name} contains an invalid filename: {source.name}")
            raw = _read_regular_file(source, "engine pack profile")
            try:
                profile = tomllib.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
                raise ValueError(f"invalid engine pack profile {source}: {error}") from error
            if profile.get("name") != source.stem:
                raise ValueError(f"engine pack profile name must match filename: {source.name}")
            profiles.append((source, _sha256(raw)))
        result[directory.name] = tuple(profiles)
    return result


def _validate_managed_profiles(root: Path, manifest: dict[str, object] | None) -> dict[str, str]:
    if manifest is None:
        return {}
    generated = manifest["generated"]
    assert isinstance(generated, dict)
    agents = root / ".codex/agents"
    if agents.is_symlink() or not agents.is_dir():
        raise ValueError("active agents directory is missing or symlinked")
    result: dict[str, str] = {}
    for name, expected in sorted(generated.items()):
        assert isinstance(name, str) and isinstance(expected, str)
        target = agents / name
        raw = _read_regular_file(target, "generated profile")
        actual = _sha256(raw)
        if actual != expected:
            raise ValueError(f"generated profile was modified: {name}")
        result[name] = expected
    return result


def _tree_digest(path: Path) -> bytes:
    records: list[bytes] = []
    if not path.exists() and not path.is_symlink():
        return b"ABSENT\0"
    if path.is_symlink():
        return b"SYMLINK\0" + os.readlink(path).encode("utf-8", "surrogateescape")
    if not path.is_dir():
        return b"NON_DIRECTORY\0" + path.read_bytes()
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        name = item.relative_to(path).as_posix().encode("utf-8", "surrogateescape")
        if item.is_symlink():
            records.extend((b"L\0", name, b"\0", os.readlink(item).encode("utf-8", "surrogateescape"), b"\0"))
        elif item.is_dir():
            records.extend((b"D\0", name, b"\0"))
        elif item.is_file():
            records.extend((b"F\0", name, b"\0", hashlib.sha256(item.read_bytes()).digest()))
        else:
            records.extend((b"O\0", name, b"\0"))
    return b"".join(records)


def _state_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in (".codex/studio.toml", ".codex/active-engine.json"):
        path = root / relative
        digest.update(relative.encode("utf-8") + b"\0")
        if path.is_symlink():
            digest.update(b"L\0" + os.readlink(path).encode("utf-8", "surrogateescape"))
        elif path.is_file():
            digest.update(b"F\0" + path.read_bytes())
        else:
            digest.update(b"A\0")
    digest.update(b"agents\0" + _tree_digest(root / ".codex/agents"))
    return digest.hexdigest()


def plan_activation(root: Path, engine: str, *, version: str = "", language: str = "") -> ActivationPlan:
    root = Path(root).resolve()
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"unsupported engine: {engine}")
    if not isinstance(version, str) or not isinstance(language, str):
        raise ValueError("engine version and language must be strings")
    config = load_studio_config(root)
    packs = _validate_packs(root)
    manifest = _load_manifest(root, config)
    managed = _validate_managed_profiles(root, manifest)
    selected = packs[engine]
    selected_hashes = tuple((source.name, digest) for source, digest in selected)
    agents = root / ".codex/agents"
    if agents.exists() or agents.is_symlink():
        if agents.is_symlink() or not agents.is_dir():
            raise ValueError("active agents path must be a regular directory, not a symlink")
    for source, _digest in selected:
        target = agents / source.name
        if target.is_symlink():
            raise ValueError(f"target profile must not be a symlink: {source.name}")
        if target.exists() and source.name not in managed:
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
    no_op = same_profiles and target_config == config
    return ActivationPlan(
        root=root,
        engine=engine,
        install=install,
        remove=remove,
        target_config=target_config,
        source_hashes=selected_hashes,
        state_digest=_state_digest(root),
        no_op=no_op,
    )


def _serialize_config(config: StudioConfig) -> bytes:
    values = dataclasses.asdict(config)
    return "".join(f"{key} = {json.dumps(values[key], ensure_ascii=False)}\n" for key in STUDIO_KEYS).encode("utf-8")


def _serialize_manifest(engine: str, generated: dict[str, str]) -> bytes:
    return (json.dumps({"engine": engine, "generated": dict(sorted(generated.items()))}, indent=2) + "\n").encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
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


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _unlink_managed(path: Path) -> None:
    path.unlink()


def _create_backup(root: Path, directory: Path) -> _Backup:
    agents = root / ".codex/agents"
    manifest = root / ".codex/active-engine.json"
    config = root / ".codex/studio.toml"
    agents_existed = agents.exists() or agents.is_symlink()
    manifest_existed = manifest.exists() or manifest.is_symlink()
    config_existed = config.exists() or config.is_symlink()
    if agents_existed:
        if agents.is_symlink() or not agents.is_dir():
            raise ValueError("active agents path cannot be backed up safely")
        shutil.copytree(agents, directory / "agents", symlinks=True)
    if manifest_existed:
        (directory / "active-engine.json").write_bytes(_read_regular_file(manifest, "active-engine manifest"))
    if config_existed:
        (directory / "studio.toml").write_bytes(_read_regular_file(config, "studio config"))
    return _Backup(directory, agents_existed, manifest_existed, config_existed)


def rollback_activation(root: Path, backup: _Backup) -> None:
    root = Path(root).resolve()
    agents = root / ".codex/agents"
    manifest = root / ".codex/active-engine.json"
    config = root / ".codex/studio.toml"
    _remove_path(agents)
    if backup.agents_existed:
        shutil.copytree(backup.directory / "agents", agents, symlinks=True)
    for target, existed, stored in (
        (manifest, backup.manifest_existed, backup.directory / "active-engine.json"),
        (config, backup.config_existed, backup.directory / "studio.toml"),
    ):
        _remove_path(target)
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(stored.read_bytes())


def _checkpoint(_phase: str) -> None:
    return None


def validate_activation(root: Path) -> list[str]:
    root = Path(root).resolve()
    try:
        config = load_studio_config(root)
        packs = _validate_packs(root)
        manifest = _load_manifest(root, config)
        managed = _validate_managed_profiles(root, manifest)
        if config.engine == "unconfigured":
            if manifest is not None or managed:
                raise ValueError("unconfigured studio must not have an active engine manifest")
        elif manifest is None or len(managed) != 5:
            raise ValueError("configured studio must have five managed engine profiles")
        elif dict((source.name, digest) for source, digest in packs[config.engine]) != managed:
            raise ValueError("active profiles do not match the immutable source pack")
    except (OSError, ValueError) as error:
        return [str(error)]
    return []


def apply_activation(root: Path, plan: ActivationPlan) -> None:
    root = Path(root).resolve()
    if root != plan.root:
        raise ValueError("activation plan belongs to a different project root")
    _control_directory(root)
    if plan.engine not in SUPPORTED_ENGINES:
        raise ValueError("invalid activation plan engine")
    packs = _validate_packs(root)
    current_source_hashes = tuple((source.name, digest) for source, digest in packs[plan.engine])
    if current_source_hashes != plan.source_hashes:
        raise ValueError("source pack changed after activation planning")
    if _state_digest(root) != plan.state_digest:
        raise ValueError("stale activation plan: project state changed after planning")
    expected_plan = plan_activation(
        root,
        plan.engine,
        version=plan.target_config.engine_version,
        language=plan.target_config.language,
    )
    if plan != expected_plan:
        raise ValueError("invalid activation plan: paths or target configuration were modified")
    if plan.no_op:
        return
    # Re-run all semantic validation before creating a backup or mutating state.
    config = load_studio_config(root)
    manifest = _load_manifest(root, config)
    _validate_managed_profiles(root, manifest)
    agents = root / ".codex/agents"
    with tempfile.TemporaryDirectory(prefix="codex-engine-pack-") as temporary:
        backup = _create_backup(root, Path(temporary))
        try:
            agents.mkdir(parents=True, exist_ok=True)
            for target in plan.remove:
                _unlink_managed(target)
            _checkpoint("remove")
            for source in plan.install:
                shutil.copy2(source, agents / source.name)
            _checkpoint("copy")
            generated = dict(plan.source_hashes)
            _atomic_write(root / ".codex/active-engine.json", _serialize_manifest(plan.engine, generated))
            _checkpoint("manifest-write")
            _atomic_write(root / ".codex/studio.toml", _serialize_config(plan.target_config))
            _checkpoint("config-write")
            issues = validate_activation(root)
            if issues:
                raise ValueError("post-apply validation failed: " + "; ".join(issues))
            _checkpoint("post-validation")
        except BaseException:
            rollback_activation(root, backup)
            raise


def _print_plan(root: Path, plan: ActivationPlan, stream: object = sys.stdout) -> None:
    write: Callable[[str], object] = getattr(stream, "write")
    write(f"ENGINE {plan.engine}\n")
    for source in plan.install:
        write(f"INSTALL {source.relative_to(root).as_posix()} -> .codex/agents/{source.name}\n")
    for target in plan.remove:
        write(f"REMOVE {target.relative_to(root).as_posix()}\n")
    config = plan.target_config
    write(f"CONFIG engine={config.engine} version={config.engine_version} language={config.language}\n")
    if plan.no_op:
        write("NO-OP active pack and configuration already match\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or apply a transactional Codex engine-agent pack activation")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--engine", required=True, choices=SUPPORTED_ENGINES)
    parser.add_argument("--version", default="")
    parser.add_argument("--language", default="")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _parser()
    options = parser.parse_args(arguments)
    root = options.root.resolve()
    try:
        plan = plan_activation(root, options.engine, version=options.version, language=options.language)
        _print_plan(root, plan)
        if options.apply:
            apply_activation(root, plan)
            issues = validate_activation(root)
            if issues:
                raise ValueError("post-apply validation failed: " + "; ".join(issues))
            print(f"Activated {options.engine} with 5 managed profiles")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
