"""Deterministic integration fixtures for plugin manager tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/codex-game-studios"
sys.path.insert(0, str(PLUGIN / "scripts"))


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
