"""Build a deterministic, checksummed Codex Game Studios plugin archive."""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
import sys
import zipfile


ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PLUGIN_RELATIVE = PurePosixPath("plugins/codex-game-studios")
CACHE_DIRECTORY_NAME = "__pycache__"
CACHE_FILE_SUFFIXES = {".pyc", ".pyo"}
PACKAGE_OUTPUT_PREFIX = "codex-game-studios-"


@dataclass(frozen=True)
class PackageResult:
    """Paths and digest produced by one plugin packaging run."""

    archive: Path
    checksum: Path
    archive_sha256: str


@dataclass(frozen=True)
class _PluginFile:
    relative: str
    archive_path: PurePosixPath
    source: Path
    mode: int
    observed: object


@dataclass(frozen=True)
class _PluginInventory:
    files: tuple[_PluginFile, ...]
    observations: tuple[tuple[str, object], ...]


def _manager_api(plugin: Path) -> tuple[object, object, object, object, object]:
    scripts = plugin / "scripts"
    names = ("models", "safe_fs", "payload", "legacy_payload")
    saved = {name: sys.modules.get(name) for name in names}
    for name in names:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(scripts))
    try:
        models = importlib.import_module("models")
        safe_fs = importlib.import_module("safe_fs")
        payload = importlib.import_module("payload")
        legacy_payload = importlib.import_module("legacy_payload")
        payload._LEGACY_CAPSULE_VERIFIER = (
            legacy_payload.LegacyPayloadError,
            legacy_payload.verified_legacy_snapshot,
        )
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass
        for name in names:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
    return (
        models.PayloadError,
        payload.build_payload,
        payload.load_verified_manifest,
        safe_fs.AnchoredFilesystem,
        safe_fs.pin_root,
    )


def _legacy_api(plugin: Path) -> tuple[type[Exception], object]:
    """Load the plugin-local legacy capsule verifier without module leakage."""

    scripts = plugin / "scripts"
    names = ("models", "safe_fs", "payload", "legacy_payload")
    saved = {name: sys.modules.get(name) for name in names}
    for name in names:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(scripts))
    try:
        importlib.import_module("models")
        importlib.import_module("safe_fs")
        importlib.import_module("payload")
        legacy_payload = importlib.import_module("legacy_payload")
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass
        for name in names:
            sys.modules.pop(name, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
    return legacy_payload.LegacyPayloadError, legacy_payload.verified_legacy_snapshot


def _plugin_files(filesystem: object) -> _PluginInventory:
    files: list[_PluginFile] = []
    observations: list[tuple[str, object]] = []
    plugin_relative = PLUGIN_RELATIVE.as_posix()

    def observe(relative: str) -> object:
        try:
            return filesystem.observe(relative)
        except OSError as error:
            raise ValueError(
                f"link, reparse point, or special file is forbidden: {relative}"
            ) from error

    def list_immediate(relative: str) -> tuple[object, ...]:
        try:
            return filesystem.list_immediate(relative)
        except OSError as error:
            raise ValueError(
                f"link, reparse point, or special file is forbidden: {relative}"
            ) from error

    plugins = observe("plugins")
    plugin = observe(plugin_relative)
    if plugins.entry_type != "directory" or plugin.entry_type != "directory":
        raise ValueError("plugin root and its repository ancestor must be directories")
    observations.extend((("plugins", plugins), (plugin_relative, plugin)))

    def visit(directory: str, *, cache: bool) -> None:
        for listed in list_immediate(directory):
            child = f"{directory}/{listed.name}"
            observed = observe(child)
            if observed.entry_type != listed.entry_type:
                raise ValueError(f"plugin path changed during inventory: {child}")
            observations.append((child, observed))
            if observed.entry_type == "directory":
                visit(child, cache=cache or listed.name == CACHE_DIRECTORY_NAME)
                continue
            if observed.entry_type != "file":
                raise ValueError(f"special file is forbidden in plugin package: {child}")
            suffix = Path(listed.name).suffix
            if cache:
                if suffix not in CACHE_FILE_SUFFIXES:
                    raise ValueError(
                        f"unexpected regular file in plugin cache directory: {child}"
                    )
                continue
            if suffix in CACHE_FILE_SUFFIXES:
                raise ValueError(f"cache file outside __pycache__ is forbidden: {child}")
            source = filesystem.root / PurePosixPath(child)
            files.append(
                _PluginFile(
                    child,
                    PurePosixPath(child),
                    source,
                    observed.mode,
                    observed,
                )
            )

    visit(plugin_relative, cache=False)
    files.sort(key=lambda item: item.archive_path.as_posix())
    observations.sort(key=lambda item: item[0])
    return _PluginInventory(tuple(files), tuple(observations))


def _read_plugin_file(filesystem: object, item: _PluginFile) -> bytes:
    try:
        path_stat = item.source.lstat()
    except OSError as error:
        raise ValueError(f"cannot inspect plugin path: {item.relative}") from error
    if stat.S_ISLNK(path_stat.st_mode):
        raise ValueError(f"link is forbidden in plugin package: {item.relative}")
    if not stat.S_ISREG(path_stat.st_mode):
        raise ValueError(f"special file is forbidden in plugin package: {item.relative}")
    try:
        return filesystem.read_file_verified(
            item.relative,
            expected_digest=item.observed.digest,
            expected_mode=item.observed.mode,
        )
    except Exception as error:
        if (
            not isinstance(error, OSError)
            and error.__class__.__name__ != "PayloadError"
        ):
            raise
        raise ValueError(
            f"plugin path changed or became a link during packaging: {item.relative}"
        ) from error


def _declared_version(filesystem: object) -> str:
    manifest_relative = f"{PLUGIN_RELATIVE.as_posix()}/.codex-plugin/plugin.json"
    try:
        observed = filesystem.observe(manifest_relative)
        if (
            observed.entry_type != "file"
            or observed.digest is None
            or observed.mode is None
        ):
            raise ValueError("plugin manifest is not a regular file")
        serialized = filesystem.read_file_verified(
            manifest_relative,
            expected_digest=observed.digest,
            expected_mode=observed.mode,
        )
        manifest = json.loads(serialized.decode("utf-8"))
        version = manifest["version"]
    except (KeyError, json.JSONDecodeError, OSError, UnicodeError) as error:
        raise ValueError("plugin manifest does not provide a valid version") from error
    except Exception as error:
        if error.__class__.__name__ != "PayloadError":
            raise
        raise ValueError(
            "plugin manifest changed or has a link, reparse point, or unsafe path"
        ) from error
    if not isinstance(version, str) or not version:
        raise ValueError("plugin manifest does not provide a valid version")
    return version


def _verified_version(
    root: Path,
    plugin: Path,
    payload_error: type[Exception],
    build_payload: object,
    load_verified_manifest: object,
) -> str:
    try:
        verified = load_verified_manifest(plugin)
        fresh = build_payload(root, plugin, check=True)
    except (OSError, ValueError, payload_error) as error:
        raise ValueError(f"plugin payload is not release-ready: {error}") from error
    if verified.version != fresh.version:
        raise ValueError("plugin and payload versions do not match")
    legacy_error, verified_legacy_snapshot = _legacy_api(plugin)
    try:
        with verified_legacy_snapshot(plugin, "1.0.0"):
            pass
    except (OSError, ValueError, legacy_error) as error:
        raise ValueError(f"legacy payload capsule is not release-ready: {error}") from error
    return verified.version


def _is_package_output_name(name: str) -> bool:
    """Return whether an immediate output name belongs to this packager."""

    def is_final(candidate: str) -> bool:
        if not candidate.startswith(PACKAGE_OUTPUT_PREFIX):
            return False
        for suffix in (".zip.sha256", ".zip"):
            if candidate.endswith(suffix):
                version = candidate[len(PACKAGE_OUTPUT_PREFIX) : -len(suffix)]
                return bool(version)
        return False

    if is_final(name):
        return True
    if not name.startswith(f".{PACKAGE_OUTPUT_PREFIX}") or not name.endswith(
        ".tmp"
    ):
        return False
    temporary_base, separator, token = name[1:-4].rpartition(".")
    return bool(separator and token) and is_final(temporary_base)


def _cleanup_pinned_package_outputs(pinned: object) -> None:
    """Remove plugin artifacts through one already-retained output authority."""

    destination = pinned.root
    for _attempt in range(8):
        if pinned._descriptor is not None:
            descriptor = pinned._descriptor
            names = sorted(os.listdir(descriptor))
            for name in names:
                if not _is_package_output_name(name):
                    continue
                try:
                    current = os.stat(
                        name, dir_fd=descriptor, follow_symlinks=False
                    )
                except FileNotFoundError:
                    continue
                if stat.S_ISDIR(current.st_mode):
                    raise ValueError(
                        f"package output artifact is a directory: {name}"
                    )
                try:
                    os.unlink(name, dir_fd=descriptor)
                except FileNotFoundError:
                    pass
            os.fsync(descriptor)
            remaining = os.listdir(descriptor)
        else:
            pinned.verify()
            names = sorted(os.listdir(destination))
            for name in names:
                if not _is_package_output_name(name):
                    continue
                path = destination / name
                try:
                    before = path.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISDIR(before.st_mode):
                    raise ValueError(
                        f"package output artifact is a directory: {name}"
                    )
                pinned.verify()
                try:
                    current = path.lstat()
                except FileNotFoundError:
                    continue
                if (before.st_dev, before.st_ino) != (
                    current.st_dev,
                    current.st_ino,
                ):
                    continue
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                pinned.verify()
            remaining = os.listdir(destination)
        if not any(_is_package_output_name(name) for name in remaining):
            return
    raise ValueError("package output cleanup did not stabilize")


def _cleanup_package_outputs(destination: Path, pin_root: object) -> None:
    """Unlink only this plugin's final/temp artifacts through a pinned directory."""

    with pin_root(destination) as pinned:
        _cleanup_pinned_package_outputs(pinned)


@contextlib.contextmanager
def _retained_output_authority(
    destination: Path, pin_root: object
) -> object:
    """Clean failures through the retained directory even if its pathname moves."""

    with pin_root(destination) as pinned:
        try:
            yield pinned
        except BaseException:
            _cleanup_pinned_package_outputs(pinned)
            raise


def _new_temporary(
    destination: Path, label: str, filesystem: object
) -> tuple[int, Path]:
    """Create an exclusive temporary through the retained output authority."""

    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_BINARY", 0)
    directory_descriptor = filesystem.pinned._descriptor
    for _attempt in range(128):
        name = f".{label}.{secrets.token_hex(8)}.tmp"
        filesystem.verify_boundary()
        try:
            if directory_descriptor is None:
                descriptor = os.open(destination / name, flags, 0o600)
            else:
                descriptor = os.open(
                    name,
                    flags,
                    0o600,
                    dir_fd=directory_descriptor,
                )
        except FileExistsError:
            continue
        opened = None
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError("package temporary output is not a regular file")
            filesystem.verify_boundary()
            if directory_descriptor is None:
                current = (destination / name).lstat()
            else:
                current = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            if (opened.st_dev, opened.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise ValueError("package temporary output identity raced")
            return descriptor, destination / name
        except BaseException:
            os.close(descriptor)
            try:
                if opened is None:
                    raise FileNotFoundError(name)
                if directory_descriptor is None:
                    current = (destination / name).lstat()
                    if (opened.st_dev, opened.st_ino) == (
                        current.st_dev,
                        current.st_ino,
                    ):
                        (destination / name).unlink()
                else:
                    current = os.stat(
                        name,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                    if (opened.st_dev, opened.st_ino) == (
                        current.st_dev,
                        current.st_ino,
                    ):
                        os.unlink(name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
            raise
    raise FileExistsError("could not allocate an exclusive package temporary")


def _write_archive(
    destination: Path,
    archive_name: str,
    filesystem: object,
    inventory: _PluginInventory,
    output_filesystem: object,
) -> tuple[Path, tuple[int, int], int, str]:
    descriptor, temporary = _new_temporary(
        destination, archive_name, output_filesystem
    )
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(
                stream,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as package:
                for item in inventory.files:
                    contents = _read_plugin_file(filesystem, item)
                    info = zipfile.ZipInfo(
                        item.archive_path.as_posix(), ARCHIVE_TIMESTAMP
                    )
                    info.create_system = 3
                    normalized_mode = 0o755 if item.mode & 0o111 else 0o644
                    info.external_attr = (stat.S_IFREG | normalized_mode) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    package.writestr(
                        info,
                        contents,
                        compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9,
                    )
            stream.flush()
            os.fsync(stream.fileno())
            written = os.fstat(stream.fileno())
            identity = (written.st_dev, written.st_ino)
            mode = stat.S_IMODE(written.st_mode)
            stream.seek(0)
            digest = hashlib.sha256()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return temporary, identity, mode, digest.hexdigest()
    except BaseException:
        # The retained output authority owns temp cleanup; never follow this path.
        raise


def _write_checksum(
    destination: Path,
    checksum_name: str,
    contents: bytes,
    output_filesystem: object,
) -> tuple[Path, tuple[int, int], int]:
    descriptor, temporary = _new_temporary(
        destination, checksum_name, output_filesystem
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
            written = os.fstat(stream.fileno())
            identity = (written.st_dev, written.st_ino)
            mode = stat.S_IMODE(written.st_mode)
        return temporary, identity, mode
    except BaseException:
        # The retained output authority owns temp cleanup; never follow this path.
        raise


def _verify_installed_output(
    final: Path,
    identity: tuple[int, int],
    expected_mode: int,
    expected_digest: str,
    filesystem: object,
) -> bytes:
    """Read and identity-bind one installed output without following links."""

    try:
        contents = filesystem.read_file_verified(
            final.name,
            expected_digest=expected_digest,
            expected_mode=expected_mode,
        )
        installed = final.lstat()
    except Exception as error:
        if (
            not isinstance(error, OSError)
            and error.__class__.__name__ != "PayloadError"
        ):
            raise
        raise ValueError("installed package output changed during finalization") from error
    if (
        not stat.S_ISREG(installed.st_mode)
        or (installed.st_dev, installed.st_ino) != identity
        or hashlib.sha256(contents).hexdigest() != expected_digest
    ):
        raise ValueError("installed package output identity or bytes changed")
    filesystem.verify_boundary()
    return contents


def _replace_temporary(
    temporary: Path,
    final: Path,
    identity: tuple[int, int],
    expected_mode: int,
    expected_digest: str,
    filesystem: object,
) -> bytes:
    """Install and verify exactly the temporary file that was written."""

    current = temporary.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != identity
    ):
        raise ValueError("package temporary output changed before finalization")
    descriptor = filesystem.pinned._descriptor
    if descriptor is None:
        os.replace(temporary, final)
    else:
        os.replace(
            temporary.name,
            final.name,
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
        )
    return _verify_installed_output(
        final,
        identity,
        expected_mode,
        expected_digest,
        filesystem,
    )


def package_plugin(root: Path | str, output: Path | str) -> PackageResult:
    """Verify and package only the plugin tree with reproducible metadata."""

    repository = Path(root).resolve()
    plugin = repository / Path(*PLUGIN_RELATIVE.parts)
    destination = Path(output)
    if not destination.is_absolute():
        destination = repository / destination
    destination = destination.resolve()
    try:
        destination.relative_to(plugin)
    except ValueError:
        pass
    else:
        raise ValueError("package output cannot be inside the plugin tree")

    payload_error, build_payload, load_verified_manifest, filesystem_type, pin_root = (
        _manager_api(plugin)
    )
    archive: Path | None = None
    checksum: Path | None = None
    temporary_archive: Path | None = None
    temporary_checksum: Path | None = None
    destination.mkdir(parents=True, exist_ok=True)
    try:
        _cleanup_package_outputs(destination, pin_root)
        with _retained_output_authority(
            destination, pin_root
        ) as output_pinned, pin_root(repository) as pinned:
            output_filesystem = filesystem_type(output_pinned)
            filesystem = filesystem_type(pinned)
            declared_version = _declared_version(filesystem)
            inventory = _plugin_files(filesystem)
            if not inventory.files:
                raise ValueError("plugin package has no files")

            verified_version = _verified_version(
                repository,
                plugin,
                payload_error,
                build_payload,
                load_verified_manifest,
            )
            if verified_version != declared_version:
                raise ValueError("plugin and payload versions do not match")
            archive = destination / f"codex-game-studios-{verified_version}.zip"
            checksum = destination / f"{archive.name}.sha256"

            (
                temporary_archive,
                archive_identity,
                archive_mode,
                archive_sha256,
            ) = _write_archive(
                destination,
                archive.name,
                filesystem,
                inventory,
                output_filesystem,
            )
            checksum_bytes = (
                f"{archive_sha256}  {archive.name}\n".encode("ascii")
            )
            (
                temporary_checksum,
                checksum_identity,
                checksum_mode,
            ) = _write_checksum(
                destination,
                checksum.name,
                checksum_bytes,
                output_filesystem,
            )
            if _plugin_files(filesystem) != inventory:
                raise ValueError("plugin tree changed during packaging")
            pinned.verify()
            installed_archive = _replace_temporary(
                temporary_archive,
                archive,
                archive_identity,
                archive_mode,
                archive_sha256,
                output_filesystem,
            )
            temporary_archive = None
            installed_checksum = _replace_temporary(
                temporary_checksum,
                checksum,
                checksum_identity,
                checksum_mode,
                hashlib.sha256(checksum_bytes).hexdigest(),
                output_filesystem,
            )
            temporary_checksum = None
            installed_archive = _verify_installed_output(
                archive,
                archive_identity,
                archive_mode,
                archive_sha256,
                output_filesystem,
            )
            installed_checksum = _verify_installed_output(
                checksum,
                checksum_identity,
                checksum_mode,
                hashlib.sha256(checksum_bytes).hexdigest(),
                output_filesystem,
            )
            if (
                hashlib.sha256(installed_archive).hexdigest() != archive_sha256
                or installed_checksum != checksum_bytes
            ):
                raise ValueError("installed package outputs do not match result metadata")
    except BaseException:
        # Do not re-pin a destination pathname that may now name attacker state.
        raise

    assert archive is not None and checksum is not None
    return PackageResult(archive, checksum, archive_sha256)


def main() -> int:
    """Run the release packager CLI."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist"))
    arguments = parser.parse_args()
    try:
        result = package_plugin(arguments.root, arguments.output)
    except (OSError, ValueError) as error:
        print(f"Codex Game Studios package: FAILED ({error})", file=sys.stderr)
        return 1
    print(result.archive)
    print(result.checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
