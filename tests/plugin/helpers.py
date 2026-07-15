"""Deterministic integration fixtures for plugin manager tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
sys.path.insert(0, str(PLUGIN / "scripts"))


def copy_plugin_fixture(source: Path, destination: Path) -> None:
    """Copy a plugin fixture without transient Python bytecode caches."""

    def ignore_transient_caches(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        ignored: set[str] = set()
        for name in names:
            entry = current / name
            entry_mode = entry.lstat().st_mode
            if name == "__pycache__" and stat.S_ISDIR(entry_mode):
                ignored.add(name)
            elif entry.suffix in {".pyc", ".pyo"} and stat.S_ISREG(entry_mode):
                ignored.add(name)
        return ignored

    shutil.copytree(
        source,
        destination,
        symlinks=True,
        ignore=ignore_transient_caches,
    )


def init_git_repo(path: Path) -> None:
    """Initialize ``path`` as an isolated Git work tree."""

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _desired_toml_values(content: bytes) -> dict[str, object]:
    document = tomllib.loads(content.decode("utf-8"))
    return {
        "agents.max_depth": document["agents"]["max_depth"],
        "agents.max_threads": document["agents"]["max_threads"],
        "features.hooks": document["features"]["hooks"],
    }


def write_installed_fixture(path: Path, plugin_root: Path = PLUGIN) -> None:
    """Materialize a valid installed repository and checksummed state."""

    from managed_blocks import merge_block, merge_owned_toml
    from models import InstallationState, ManagedPath, canonical_json
    from payload import load_manifest
    from studio_manager import state_with_checksum, write_state_document

    manifest = load_manifest(plugin_root / "assets/payload-manifest.json")
    studio = plugin_root / "assets/studio"
    managed_paths: list[ManagedPath] = []
    decisions: list[dict[str, object]] = []
    for entry in manifest.entries:
        target = path / entry.path
        if entry.entry_type == "directory":
            target.mkdir(parents=True, exist_ok=True)
            managed_paths.append(
                ManagedPath(entry.path, None, entry.ownership, entry.merge, None)
            )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        desired = (studio / entry.path).read_bytes()
        block_hash = None
        if entry.merge == "managed-block":
            result = merge_block(b"", "codex-game-studios", desired)
            content = result.content
            block_hash = result.block_hash
            decisions.append(
                {"kind": "managed-block", "path": entry.path, "outcome": "merge"}
            )
        elif entry.merge == "toml-keys":
            values = _desired_toml_values(desired)
            result = merge_owned_toml(b"", values, {})
            content = result.content
            decisions.append(
                {
                    "kind": "toml-keys",
                    "path": entry.path,
                    "outcome": "merge",
                    "owned_values": values,
                }
            )
        else:
            content = desired
        target.write_bytes(content)
        os.chmod(target, entry.mode)
        managed_paths.append(
            ManagedPath(
                entry.path,
                hashlib.sha256(content).hexdigest(),
                entry.ownership,
                entry.merge,
                block_hash,
            )
        )

    state = state_with_checksum(
        InstallationState(
            schema_version=1,
            plugin_version=manifest.version,
            payload_digest=manifest.digest,
            transaction_id="00000000-0000-4000-8000-000000000001",
            installed_at="2026-07-12T00:00:00Z",
            managed_paths=tuple(managed_paths),
            decisions=tuple(sorted(decisions, key=lambda item: canonical_json(item))),
            validator_version="1",
            journal_status="committed",
            checksum="",
        )
    )
    state_path = path / ".codex/codex-game-studios/installation.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_bytes(write_state_document(state))


def snapshot_tree(path: Path) -> dict[str, tuple[str, int, str | None]]:
    """Return a deterministic non-Git tree fingerprint without following links."""

    result: dict[str, tuple[str, int, str | None]] = {}
    for candidate in sorted(path.rglob("*")):
        relative = candidate.relative_to(path).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        file_stat = candidate.lstat()
        mode = file_stat.st_mode & 0o777
        if candidate.is_symlink():
            result[relative] = ("link", mode, os.readlink(candidate))
        elif candidate.is_dir():
            result[relative] = ("directory", mode, None)
        elif candidate.is_file():
            result[relative] = (
                "file",
                mode,
                hashlib.sha256(candidate.read_bytes()).hexdigest(),
            )
        else:
            result[relative] = ("special", mode, None)
    return result


def run_manager(
    operation: str,
    root: Path,
    approve_digest: str | None = None,
    plugin_root: Path = PLUGIN,
    approval_context: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the public manager CLI with deterministic JSON output."""

    if plugin_root == PLUGIN:
        with tempfile.TemporaryDirectory(
            dir=Path(tempfile.gettempdir()).resolve()
        ) as temporary:
            fixture = Path(temporary) / "plugin"
            copy_plugin_fixture(PLUGIN, fixture)
            return run_manager(
                operation,
                root,
                approve_digest,
                fixture,
                approval_context,
            )

    command = [
        sys.executable,
        str(plugin_root / "scripts/studio_manager.py"),
        operation,
        "--root",
        str(root),
        "--plugin-root",
        str(plugin_root),
        "--format",
        "json",
    ]
    if approve_digest is not None:
        command.extend(["--approve-digest", approve_digest])
    if approval_context is not None:
        command.extend(["--approval-context", approval_context])
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def approved_install(root: Path, plugin_root: Path = PLUGIN) -> SimpleNamespace:
    """Plan and approve one installation, returning both CLI results."""

    planned = run_manager("install", root, plugin_root=plugin_root)
    document = __import__("json").loads(planned.stdout)
    applied = run_manager(
        "install", root, document["digest"], plugin_root, document["approval_context"]
    )
    return SimpleNamespace(planned=planned, applied=applied)
