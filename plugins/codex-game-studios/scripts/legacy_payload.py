"""Authenticated access to immutable public legacy studio payloads."""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import os
from pathlib import Path
import stat
import tempfile
from typing import Iterator
import zipfile

from models import PayloadError, PayloadManifest, normalize_relative_path
from payload import load_manifest, verify_manifest_snapshot
from safe_fs import read_file_secure


ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
SUPPORTED_LEGACY_VERSIONS = frozenset({"1.0.0"})
# The capsule is generated once from this exact public Git commit; runtime
# authentication uses only the committed digests below and never invokes Git.
_LEGACY_SOURCE_COMMITS = {
    "1.0.0": "b854a442399610f61e5d30b7861dfd5633503fcb",
}
_MANIFEST_SHA256 = {
    "1.0.0": "560d7aeedc302adaf3d018ac5ca32be5e975eb67e5816d8faee29d465e7e26bd",
}
_ARCHIVE_SHA256 = {
    "1.0.0": "1114c9fbb458421422c4371e1db4c038994de7c150ae3f75254f81d2437359a5",
}
_PAYLOAD_DIGEST = {
    "1.0.0": "a9b7aebc65767d92bc48f05adf9539b70e9c3f86aaba39b34f86181466351daa",
}


class LegacyPayloadError(PayloadError):
    """Raised when an immutable legacy capsule violates its contract."""


@dataclasses.dataclass(frozen=True)
class LegacyPayload:
    """One authenticated legacy payload capsule."""

    version: str
    archive: Path
    manifest: PayloadManifest


def _authenticated_capsule_bytes(plugin: Path, version: str) -> tuple[LegacyPayload, bytes, bytes]:
    if version not in SUPPORTED_LEGACY_VERSIONS:
        raise LegacyPayloadError("unsupported legacy plugin version")
    base = plugin / "assets/legacy" / version
    try:
        manifest_bytes = read_file_secure(base, "payload-manifest.json")
        archive_bytes = read_file_secure(base, "studio.zip")
    except (OSError, PayloadError) as error:
        raise LegacyPayloadError("legacy payload capsule is missing or unsafe") from error
    if hashlib.sha256(manifest_bytes).hexdigest() != _MANIFEST_SHA256[version]:
        raise LegacyPayloadError("legacy payload manifest authentication failed")
    if hashlib.sha256(archive_bytes).hexdigest() != _ARCHIVE_SHA256[version]:
        raise LegacyPayloadError("legacy payload archive authentication failed")
    try:
        manifest = load_manifest(base / "payload-manifest.json")
    except PayloadError as error:
        raise LegacyPayloadError("legacy payload manifest is invalid") from error
    if manifest.version != version or manifest.digest != _PAYLOAD_DIGEST[version]:
        raise LegacyPayloadError("legacy payload version or digest mismatch")
    return LegacyPayload(version, base / "studio.zip", manifest), manifest_bytes, archive_bytes


def load_legacy_payload(plugin: Path, version: str) -> LegacyPayload:
    """Load one digest-authenticated public legacy payload."""

    legacy, _manifest_bytes, _archive_bytes = _authenticated_capsule_bytes(
        Path(plugin), version
    )
    return legacy


def _expected_member_name(path: str, entry_type: str) -> str:
    return f"assets/studio/{path}" + ("/" if entry_type == "directory" else "")


def _validate_member_metadata(info: zipfile.ZipInfo, entry: object) -> None:
    directory = entry.entry_type == "directory"
    expected_name = _expected_member_name(entry.path, entry.entry_type)
    expected_type = stat.S_IFDIR if directory else stat.S_IFREG
    expected_attributes = (expected_type | entry.mode) << 16
    if directory:
        expected_attributes |= 0x10
    if info.filename != expected_name:
        raise LegacyPayloadError(f"legacy archive has undeclared entry: {info.filename}")
    if info.is_dir() != directory:
        raise LegacyPayloadError(f"legacy archive entry type drift: {info.filename}")
    if stat.S_IFMT(info.external_attr >> 16) != expected_type:
        raise LegacyPayloadError(f"legacy archive link or special entry: {info.filename}")
    if stat.S_IMODE(info.external_attr >> 16) != entry.mode:
        raise LegacyPayloadError(f"legacy archive mode drift: {info.filename}")
    if (
        info.date_time != ARCHIVE_TIMESTAMP
        or info.create_system != 3
        or info.create_version != 20
        or info.extract_version != 20
        or info.reserved != 0
        or info.flag_bits != 0
        or info.volume != 0
        or info.internal_attr != 0
        or info.external_attr != expected_attributes
        or info.compress_type != zipfile.ZIP_DEFLATED
        or info.extra != b""
        or info.comment != b""
    ):
        raise LegacyPayloadError(f"legacy archive metadata drift: {info.filename}")
    if directory and (info.file_size != 0 or info.CRC != 0):
        raise LegacyPayloadError(f"legacy archive directory contains data: {info.filename}")


def _validated_members(
    archive_bytes: bytes, manifest: PayloadManifest
) -> tuple[tuple[object, bytes], ...]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            if archive.comment:
                raise LegacyPayloadError("legacy archive comment is forbidden")
            infos = archive.infolist()
            normalized: set[str] = set()
            for info in infos:
                raw = info.filename
                if not raw.startswith("assets/studio/"):
                    raise LegacyPayloadError(f"legacy archive has unsafe entry: {raw}")
                relative = raw[len("assets/studio/") :]
                candidate = relative[:-1] if relative.endswith("/") else relative
                try:
                    normalized_name = normalize_relative_path(candidate)
                except PayloadError as error:
                    raise LegacyPayloadError(f"legacy archive has unsafe entry: {raw}") from error
                if normalized_name in normalized:
                    raise LegacyPayloadError(
                        f"legacy archive has duplicate normalized entry: {raw}"
                    )
                normalized.add(normalized_name)
            if len(infos) != len(manifest.entries):
                raise LegacyPayloadError("legacy archive inventory differs from manifest")
            materialized: list[tuple[object, bytes]] = []
            for info, entry in zip(infos, manifest.entries, strict=True):
                _validate_member_metadata(info, entry)
                try:
                    contents = archive.read(info)
                except (OSError, RuntimeError, zipfile.BadZipFile) as error:
                    raise LegacyPayloadError(
                        f"legacy archive member cannot be authenticated: {info.filename}"
                    ) from error
                if entry.entry_type == "file":
                    digest = hashlib.sha256(contents).hexdigest()
                    if digest != entry.sha256:
                        raise LegacyPayloadError(
                            f"legacy archive hash drift: {info.filename}"
                        )
                elif contents:
                    raise LegacyPayloadError(
                        f"legacy archive directory contains data: {info.filename}"
                    )
                materialized.append((entry, contents))
    except LegacyPayloadError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise LegacyPayloadError("legacy payload archive is invalid") from error
    return tuple(materialized)


def _materialize_snapshot(
    root: Path,
    manifest: PayloadManifest,
    manifest_bytes: bytes,
    members: tuple[tuple[object, bytes], ...],
) -> None:
    assets = root / "assets"
    studio = assets / "studio"
    studio.mkdir(parents=True, mode=0o700)
    for entry, contents in members:
        destination = studio / entry.path
        if entry.entry_type == "directory":
            destination.mkdir(mode=0o700)
        else:
            destination.write_bytes(contents)
            os.chmod(destination, entry.mode)
    for entry, _contents in reversed(members):
        if entry.entry_type == "directory":
            os.chmod(studio / entry.path, entry.mode)
    (assets / "payload-manifest.json").write_bytes(manifest_bytes)
    os.chmod(assets / "payload-manifest.json", 0o644)
    verify_manifest_snapshot(root, manifest)


@contextlib.contextmanager
def verified_legacy_snapshot(
    plugin: Path, version: str
) -> Iterator[tuple[Path, PayloadManifest]]:
    """Yield a private temporary snapshot of one exact legacy payload."""

    legacy, manifest_bytes, archive_bytes = _authenticated_capsule_bytes(
        Path(plugin), version
    )
    members = _validated_members(archive_bytes, legacy.manifest)
    with tempfile.TemporaryDirectory(prefix=".codex-game-studios-legacy-") as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        _materialize_snapshot(root, legacy.manifest, manifest_bytes, members)
        yield root, legacy.manifest
