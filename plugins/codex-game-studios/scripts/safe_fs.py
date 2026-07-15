"""No-follow, descriptor-based filesystem operations for payload integrity.

The public helpers anchor relative paths beneath an opened root, reject links,
reparse points, and special files, and verify that source and destination
identities remain stable across I/O. POSIX uses ``dir_fd`` with ``O_NOFOLLOW``;
Windows pins verified root, ancestor, and target handles for the complete I/O
operation and mutates readonly attributes through the target handle. Windows
mode verification intentionally enforces the writable/read-only bit only;
POSIX enforces the complete permission mode.
"""

from __future__ import annotations

import contextlib
import ctypes
import dataclasses
import errno
import hashlib
import ntpath
import os
import pathlib
import stat
import sys
from typing import Iterator

from models import PayloadError, digest_document, normalize_relative_path


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_READ_FLAGS = os.O_RDONLY | _BINARY | _CLOEXEC
_DIRECTORY_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
_IDENTITY_FIELDS = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_WRITE_ATTRIBUTES = 0x00000100
DELETE_ACCESS = 0x00010000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
CREATE_NEW = 1
OPEN_EXISTING = 3
FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_FILE_BASIC_INFO_CLASS = 0
_FILE_RENAME_INFO_CLASS = 3
_FILE_DISPOSITION_INFO_CLASS = 4
_VOLUME_NAME_DOS = 0
_ERROR_ALREADY_EXISTS = 183
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_MANAGER_LOCK_RELATIVE = ".codex/codex-game-studios/manager.lock"


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [("FileAttributes", ctypes.c_uint32), ("ReparseTag", ctypes.c_uint32)]


class _FileBasicInfo(ctypes.Structure):
    _fields_ = [
        ("CreationTime", ctypes.c_int64),
        ("LastAccessTime", ctypes.c_int64),
        ("LastWriteTime", ctypes.c_int64),
        ("ChangeTime", ctypes.c_int64),
        ("FileAttributes", ctypes.c_uint32),
    ]


class _FileDispositionInfo(ctypes.Structure):
    _fields_ = [("DeleteFile", ctypes.c_ubyte)]


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", ctypes.c_uint32),
        ("CreationTimeLow", ctypes.c_uint32),
        ("CreationTimeHigh", ctypes.c_uint32),
        ("LastAccessTimeLow", ctypes.c_uint32),
        ("LastAccessTimeHigh", ctypes.c_uint32),
        ("LastWriteTimeLow", ctypes.c_uint32),
        ("LastWriteTimeHigh", ctypes.c_uint32),
        ("VolumeSerialNumber", ctypes.c_uint32),
        ("FileSizeHigh", ctypes.c_uint32),
        ("FileSizeLow", ctypes.c_uint32),
        ("NumberOfLinks", ctypes.c_uint32),
        ("FileIndexHigh", ctypes.c_uint32),
        ("FileIndexLow", ctypes.c_uint32),
    ]


class _WindowsApi:
    """Typed Win32 operations used to bind I/O to verified handles."""

    def __init__(self) -> None:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create_file = kernel32.CreateFileW
        self._create_file.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        self._create_file.restype = wintypes.HANDLE
        self._get_file_information_ex = kernel32.GetFileInformationByHandleEx
        self._get_file_information_ex.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        self._get_file_information_ex.restype = wintypes.BOOL
        self._set_file_information = kernel32.SetFileInformationByHandle
        self._set_file_information.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        self._set_file_information.restype = wintypes.BOOL
        self._get_final_path = kernel32.GetFinalPathNameByHandleW
        self._get_final_path.argtypes = [
            wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        ]
        self._get_final_path.restype = wintypes.DWORD
        self._close_handle = kernel32.CloseHandle
        self._close_handle.argtypes = [wintypes.HANDLE]
        self._close_handle.restype = wintypes.BOOL
        self._create_directory = kernel32.CreateDirectoryW
        self._create_directory.argtypes = [wintypes.LPCWSTR, wintypes.LPVOID]
        self._create_directory.restype = wintypes.BOOL
        self._get_file_information_basic = kernel32.GetFileInformationByHandle
        self._get_file_information_basic.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ByHandleFileInformation),
        ]
        self._get_file_information_basic.restype = wintypes.BOOL

    def create_file(self, path: str, access: int, share: int, disposition: int, flags: int) -> int:
        handle = self._create_file(path, access, share, None, disposition, flags, None)
        if handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def attributes(self, handle: int) -> tuple[int, int]:
        information = _FileAttributeTagInfo()
        if not self._get_file_information_ex(
            handle, _FILE_ATTRIBUTE_TAG_INFO_CLASS, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(information.FileAttributes), int(information.ReparseTag)

    def final_path(self, handle: int) -> str:
        buffer = ctypes.create_unicode_buffer(32768)
        length = self._get_final_path(handle, buffer, len(buffer), _VOLUME_NAME_DOS)
        if not length or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value

    def basic_info(self, handle: int) -> _FileBasicInfo:
        information = _FileBasicInfo()
        if not self._get_file_information_ex(
            handle, _FILE_BASIC_INFO_CLASS, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return information

    def set_basic_info(self, handle: int, information: _FileBasicInfo) -> None:
        if not self._set_file_information(
            handle, _FILE_BASIC_INFO_CLASS, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def mark_delete(self, handle: int) -> None:
        """Mark the exact opened file or empty directory for deletion."""

        information = _FileDispositionInfo(1)
        if not self._set_file_information(
            handle,
            _FILE_DISPOSITION_INFO_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def _rename(self, handle: int, destination: str, *, replace: bool) -> None:
        encoded = destination.encode("utf-16-le")
        alignment = ctypes.alignment(ctypes.c_void_p)
        root_offset = (
            ctypes.sizeof(ctypes.c_uint32) + alignment - 1
        ) & ~(alignment - 1)
        name_length_offset = root_offset + ctypes.sizeof(ctypes.c_void_p)
        name_offset = name_length_offset + ctypes.sizeof(ctypes.c_uint32)
        buffer = ctypes.create_string_buffer(
            name_offset + len(encoded) + ctypes.sizeof(ctypes.c_uint16)
        )
        ctypes.c_uint32.from_buffer(buffer, 0).value = int(replace)
        ctypes.c_void_p.from_buffer(buffer, root_offset).value = None
        ctypes.c_uint32.from_buffer(buffer, name_length_offset).value = len(encoded)
        buffer[name_offset : name_offset + len(encoded)] = encoded
        if not self._set_file_information(
            handle,
            _FILE_RENAME_INFO_CLASS,
            ctypes.byref(buffer),
            len(buffer),
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def rename_no_replace(self, handle: int, destination: str) -> None:
        """Rename the exact opened source handle and fail if target exists."""

        self._rename(handle, destination, replace=False)

    def rename_replace(self, handle: int, destination: str) -> None:
        """Atomically replace an internal destination with the exact source handle."""

        self._rename(handle, destination, replace=True)

    def close(self, handle: int) -> None:
        if not self._close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def create_directory(self, path: str) -> None:
        if self._create_directory(path, None):
            return
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)

    def identity(self, handle: int) -> tuple[int, int]:
        """Return volume serial and file index for one retained handle."""

        information = _ByHandleFileInformation()
        if not self._get_file_information_basic(handle, ctypes.byref(information)):
            raise ctypes.WinError(ctypes.get_last_error())
        index = (int(information.FileIndexHigh) << 32) | int(information.FileIndexLow)
        return int(information.VolumeSerialNumber), index


def _windows_normal_path(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))


def _windows_contained(root: str, candidate: str) -> bool:
    try:
        return ntpath.commonpath([_windows_normal_path(root), _windows_normal_path(candidate)]) == _windows_normal_path(root)
    except ValueError:
        return False


def _windows_verify_handle(
    api: object,
    handle: int,
    verified_root: str | None,
    directory: bool | None,
) -> tuple[str, bool]:
    attributes, reparse_tag = api.attributes(handle)
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT or reparse_tag:
        raise PayloadError("link or reparse point is forbidden")
    is_directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
    if directory is not None and is_directory != directory:
        raise PayloadError("payload path has wrong type")
    final_path = api.final_path(handle)
    if verified_root is not None and not _windows_contained(verified_root, final_path):
        raise PayloadError("verified Windows path escapes secure root")
    return final_path, is_directory


@dataclasses.dataclass
class _WindowsOpenedHandles:
    """Verified target and ancestors pinned until context exit."""

    api: object
    final_handle: int
    ancestor_handles: tuple[int, ...]
    final_is_directory: bool
    _detached: bool = False

    def __enter__(self) -> "_WindowsOpenedHandles":
        return self

    def detach_final(self) -> int:
        self._detached = True
        return self.final_handle

    def __exit__(self, exc_type, exc, traceback) -> None:
        if not self._detached:
            self.api.close(self.final_handle)
        for handle in reversed(self.ancestor_handles):
            self.api.close(handle)


def _windows_open_verified(
    root: pathlib.Path,
    relative: str,
    *,
    access: int,
    share: int,
    disposition: int,
    create_parents: bool,
    final_directory: bool | None,
    api: object | None = None,
) -> _WindowsOpenedHandles:
    """Open a Windows file handle while pinning and verifying all ancestors."""

    relative = normalize_relative_path(relative)
    api = _WindowsApi() if api is None else api
    parts = pathlib.PurePosixPath(relative).parts
    root_text = ntpath.normpath(str(root))
    directory_flags = FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT
    directory_handles: list[int] = []
    final_handle: int | None = None
    try:
        verified_root: str | None = None
        for index in range(len(parts)):
            directory_path = ntpath.join(root_text, *parts[:index])
            if index and create_parents:
                try:
                    api.create_directory(directory_path)
                except OSError as error:
                    error_code = getattr(error, "winerror", None)
                    if error_code is None:
                        error_code = error.errno
                    if error_code != _ERROR_ALREADY_EXISTS:
                        raise
            handle = api.create_file(
                directory_path, GENERIC_READ, share, OPEN_EXISTING, directory_flags
            )
            directory_handles.append(handle)
            opened_path, _ = _windows_verify_handle(api, handle, verified_root, True)
            if verified_root is None:
                verified_root = opened_path
        final_path = ntpath.join(root_text, *parts)
        final_flags = FILE_FLAG_OPEN_REPARSE_POINT
        if final_directory is not False:
            final_flags |= FILE_FLAG_BACKUP_SEMANTICS
        final_handle = api.create_file(
            final_path, access, share, disposition, final_flags
        )
        _, final_is_directory = _windows_verify_handle(
            api, final_handle, verified_root, final_directory
        )
    except BaseException:
        if final_handle is not None:
            api.close(final_handle)
        for handle in reversed(directory_handles):
            api.close(handle)
        raise
    assert final_handle is not None
    return _WindowsOpenedHandles(
        api, final_handle, tuple(directory_handles), final_is_directory
    )


def _windows_set_writable(api: object, handle: int, *, writable: bool) -> None:
    """Update only readonly state through the verified target handle."""

    information = api.basic_info(handle)
    currently_writable = not bool(
        information.FileAttributes & FILE_ATTRIBUTE_READONLY
    )
    if currently_writable == writable:
        return
    if writable:
        information.FileAttributes &= ~FILE_ATTRIBUTE_READONLY
        if information.FileAttributes == 0:
            information.FileAttributes = FILE_ATTRIBUTE_NORMAL
    else:
        information.FileAttributes |= FILE_ATTRIBUTE_READONLY
    api.set_basic_info(handle, information)


def _windows_stat_view(api: object, handle: int, *, directory: bool) -> object:
    information = api.basic_info(handle)
    mode = (stat.S_IFDIR if directory else stat.S_IFREG) | stat.S_IREAD
    if not information.FileAttributes & FILE_ATTRIBUTE_READONLY:
        mode |= stat.S_IWRITE
    return type("WindowsHandleStat", (), {"st_mode": mode})()


def _windows_descriptor_from_verified(
    opened: _WindowsOpenedHandles,
    flags: int,
    *,
    msvcrt_module: object | None = None,
) -> int:
    if msvcrt_module is None:
        import msvcrt as msvcrt_module
    handle = opened.detach_final()
    try:
        return msvcrt_module.open_osfhandle(handle, flags)
    except BaseException:
        opened.api.close(handle)
        raise


def is_reparse_point(file_stat: os.stat_result) -> bool:
    """Return whether a stat result identifies a Windows reparse point."""

    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_attribute)


def _kind(file_stat: os.stat_result) -> str:
    if stat.S_ISLNK(file_stat.st_mode) or is_reparse_point(file_stat):
        raise PayloadError("link or reparse point is forbidden")
    if stat.S_ISDIR(file_stat.st_mode):
        return "directory"
    if stat.S_ISREG(file_stat.st_mode):
        return "file"
    raise PayloadError("special payload file is forbidden")


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return all(getattr(left, field) == getattr(right, field) for field in _IDENTITY_FIELDS)


def _is_windows() -> bool:
    return os.name == "nt"


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    if _is_windows():
        return (
            getattr(left, "st_ino", None),
            getattr(left, "st_dev", None),
        ) == (
            getattr(right, "st_ino", None),
            getattr(right, "st_dev", None),
        )
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _validate_root(root: pathlib.Path) -> os.stat_result:
    try:
        root_stat = root.lstat()
    except OSError as error:
        raise PayloadError(f"cannot inspect secure root: {error}") from error
    if _kind(root_stat) != "directory":
        raise PayloadError("secure root must be a directory")
    return root_stat


@dataclasses.dataclass
class PinnedRoot:
    """Repository root identity retained for the full enclosing operation."""

    root: pathlib.Path
    identity: object
    _descriptor: int | None = None
    _windows_api: object | None = None
    _windows_handle: int | None = None

    def verify(self) -> None:
        """Raise when the path no longer names the retained root identity."""

        if self._windows_handle is not None:
            assert self._windows_api is not None
            current_path, _ = _windows_verify_handle(
                self._windows_api, self._windows_handle, None, True
            )
            fresh = self._windows_api.create_file(
                str(self.root),
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
            )
            try:
                fresh_path, _ = _windows_verify_handle(
                    self._windows_api, fresh, None, True
                )
            finally:
                self._windows_api.close(fresh)
            if (
                _windows_normal_path(current_path) != self.identity
                or _windows_normal_path(fresh_path) != self.identity
            ):
                raise PayloadError("secure root changed during operation")
            return
        assert self._descriptor is not None
        opened = os.fstat(self._descriptor)
        current = _validate_root(self.root)
        if not _same_object(opened, current) or not _same_object(opened, self.identity):
            raise PayloadError("secure root changed during operation")


@contextlib.contextmanager
def pin_root(root: pathlib.Path | str) -> Iterator[PinnedRoot]:
    """Retain a no-follow root handle and verify its path identity on success."""

    root_path = pathlib.Path(root)
    if _is_windows():
        api = _WindowsApi()
        handle = api.create_file(
            str(root_path),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT,
        )
        try:
            final_path, _ = _windows_verify_handle(api, handle, None, True)
            pinned = PinnedRoot(
                root_path,
                _windows_normal_path(final_path),
                _windows_api=api,
                _windows_handle=handle,
            )
            yield pinned
            pinned.verify()
        finally:
            api.close(handle)
        return

    expected = _validate_root(root_path)
    try:
        descriptor = os.open(root_path, _DIRECTORY_FLAGS)
    except OSError as error:
        raise PayloadError(
            f"cannot open secure root without following links: {error}"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if _kind(opened) != "directory" or not _same_object(expected, opened):
            raise PayloadError("secure root changed while opening")
        pinned = PinnedRoot(root_path, opened, _descriptor=descriptor)
        yield pinned
        pinned.verify()
    finally:
        os.close(descriptor)


def secure_root_identity(root: pathlib.Path | str | PinnedRoot) -> str:
    """Return a canonical root identity from a retained no-follow handle."""

    if isinstance(root, PinnedRoot):
        pinned = root
        pinned.verify()
        if pinned._windows_handle is not None:
            assert pinned._windows_api is not None
            volume, index = pinned._windows_api.identity(pinned._windows_handle)
            return f"windows:{volume}:{index}"
        assert pinned._descriptor is not None
        opened = os.fstat(pinned._descriptor)
        return f"posix:{opened.st_dev}:{opened.st_ino}"
    with pin_root(root) as pinned:
        return secure_root_identity(pinned)


@dataclasses.dataclass(frozen=True)
class ImmediateEntry:
    """One securely observed immediate directory child."""

    name: str
    entry_type: str
    sha256: str | None


def _hash_descriptor(descriptor: int, before: os.stat_result) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    if not _same_identity(before, os.fstat(descriptor)):
        raise PayloadError("directory child changed during secure read")
    return digest.hexdigest()


def list_immediate_secure(
    root: pathlib.Path,
    relative: str,
    *,
    cooperative_children: frozenset[str] | set[str] = frozenset(),
) -> tuple[ImmediateEntry, ...]:
    """Return sorted immediate children without traversing nested directories."""

    relative = normalize_relative_path(relative)
    cooperative_children = frozenset(cooperative_children)
    if any(
        not name or pathlib.PurePosixPath(name).name != name
        for name in cooperative_children
    ):
        raise PayloadError("cooperative directory child must be one exact name")
    if _is_windows():
        api = _WindowsApi()
        directory = _windows_open_verified(
            root,
            relative,
            access=GENERIC_READ,
            share=FILE_SHARE_READ,
            disposition=OPEN_EXISTING,
            create_parents=False,
            final_directory=True,
            api=api,
        )
        entries: list[ImmediateEntry] = []
        with directory:
            directory_path = ntpath.join(
                str(root), *pathlib.PurePosixPath(relative).parts
            )
            with os.scandir(directory_path) as iterator:
                names = sorted(entry.name for entry in iterator)
            for name in names:
                child_relative = normalize_relative_path(f"{relative}/{name}")
                is_manager_lock = child_relative == _MANAGER_LOCK_RELATIVE
                child_share = FILE_SHARE_READ
                if name in cooperative_children:
                    child_share |= FILE_SHARE_WRITE | FILE_SHARE_DELETE
                elif is_manager_lock:
                    child_share |= FILE_SHARE_WRITE
                child = _windows_open_verified(
                    root,
                    child_relative,
                    access=GENERIC_READ,
                    share=child_share,
                    disposition=OPEN_EXISTING,
                    create_parents=False,
                    final_directory=None,
                    api=api,
                )
                with child as handles:
                    entry_type = (
                        "directory" if handles.final_is_directory else "file"
                    )
                    child_hash = None
                    if entry_type == "file" and not is_manager_lock:
                        descriptor = _windows_descriptor_from_verified(
                            handles, _READ_FLAGS
                        )
                        try:
                            before = os.fstat(descriptor)
                            child_hash = _hash_descriptor(descriptor, before)
                        finally:
                            os.close(descriptor)
                    entries.append(ImmediateEntry(name, entry_type, child_hash))
        return tuple(entries)

    entries = []
    with _open_existing(root, relative, expect="directory") as (
        directory_descriptor,
        directory_stat,
    ):
        try:
            names = sorted(os.listdir(directory_descriptor))
        except OSError as error:
            raise PayloadError(
                f"cannot list secure directory: {relative}: {error}"
            ) from error
        for name in names:
            child_relative = normalize_relative_path(f"{relative}/{name}")
            is_manager_lock = child_relative == _MANAGER_LOCK_RELATIVE
            try:
                descriptor = os.open(
                    name,
                    _READ_FLAGS | _NOFOLLOW | _NONBLOCK,
                    dir_fd=directory_descriptor,
                )
            except OSError as error:
                raise PayloadError(
                    f"link or reparse point or unsafe child is forbidden: {relative}/{name}: {error}"
                ) from error
            try:
                before = os.fstat(descriptor)
                entry_type = _kind(before)
                child_hash = (
                    _hash_descriptor(descriptor, before)
                    if entry_type == "file" and not is_manager_lock
                    else None
                )
                current = os.stat(
                    name, dir_fd=directory_descriptor, follow_symlinks=False
                )
                if not _same_object(before, current):
                    raise PayloadError("directory child changed during observation")
                entries.append(ImmediateEntry(name, entry_type, child_hash))
            finally:
                os.close(descriptor)
    try:
        with _open_existing(root, relative, expect="directory") as (
            _descriptor,
            current_directory,
        ):
            if not _same_object(directory_stat, current_directory):
                raise PayloadError("directory changed during immediate observation")
    except PayloadError as error:
        raise PayloadError("directory changed during immediate observation") from error
    return tuple(entries)


def recovery_tree_digest_secure(root: pathlib.Path, relative: str) -> str:
    """Digest every recovery descendant through no-follow secure reads."""

    inventory: list[dict[str, object]] = []

    def visit(directory: str) -> None:
        for item in list_immediate_secure(root, directory):
            child = f"{directory}/{item.name}"
            inventory.append(
                {
                    "path": child[len(relative) + 1 :],
                    "entry_type": item.entry_type,
                    "sha256": item.sha256,
                }
            )
            if item.entry_type == "directory":
                visit(child)

    visit(relative)
    return digest_document({"entries": inventory})


@contextlib.contextmanager
def _root_fd(root: pathlib.Path) -> Iterator[int | None]:
    expected = _validate_root(root)
    if os.name == "nt":
        raise PayloadError("POSIX descriptor helper is unavailable on Windows")
    try:
        descriptor = os.open(root, _DIRECTORY_FLAGS)
    except OSError as error:
        raise PayloadError(f"cannot open secure root without following links: {error}") from error
    try:
        opened = os.fstat(descriptor)
        if _kind(opened) != "directory" or not _same_object(expected, opened):
            raise PayloadError("secure root changed while opening")
        yield descriptor
        if not _same_object(opened, os.fstat(descriptor)) or not _same_object(
            opened, _validate_root(root)
        ):
            raise PayloadError("secure root changed during operation")
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def _parent_fd(root: pathlib.Path, relative: str, *, create: bool = False) -> Iterator[tuple[int | None, str]]:
    relative = normalize_relative_path(relative)
    parts = pathlib.PurePosixPath(relative).parts
    with _root_fd(root) as root_descriptor:
        descriptors: list[int] = []
        current_descriptor = root_descriptor
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o755, dir_fd=current_descriptor)
                    except FileExistsError:
                        pass
                    except OSError as error:
                        raise PayloadError(f"cannot create secure directory: {relative}: {error}") from error
                try:
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current_descriptor)
                except OSError as error:
                    raise PayloadError(
                        f"link or reparse point or unsafe ancestor is forbidden: {relative}: {error}"
                    ) from error
                if _kind(os.fstat(child)) != "directory":
                    os.close(child)
                    raise PayloadError(f"secure path parent is not a directory: {relative}")
                try:
                    path_stat = os.stat(part, dir_fd=current_descriptor, follow_symlinks=False)
                except OSError as error:
                    os.close(child)
                    raise PayloadError(f"cannot verify secure directory: {relative}: {error}") from error
                if not _same_object(path_stat, os.fstat(child)) or _kind(path_stat) != "directory":
                    os.close(child)
                    raise PayloadError(f"secure directory changed while opening: {relative}")
                descriptors.append(child)
                current_descriptor = child
            yield current_descriptor, parts[-1]
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


@contextlib.contextmanager
def _open_existing(
    root: pathlib.Path, relative: str, *, expect: str = "file"
) -> Iterator[tuple[int, os.stat_result]]:
    relative = normalize_relative_path(relative)
    if os.name == "nt":
        if expect == "directory":
            raise PayloadError("use a verified Windows directory handle")
        opened = _windows_open_verified(
            root,
            relative,
            access=GENERIC_READ,
            share=FILE_SHARE_READ,
            disposition=OPEN_EXISTING,
            create_parents=False,
            final_directory=False,
        )
        with opened:
            descriptor = _windows_descriptor_from_verified(opened, _READ_FLAGS)
            try:
                opened_stat = os.fstat(descriptor)
                if _kind(opened_stat) != expect:
                    raise PayloadError(f"payload path has wrong type: {relative}")
                yield descriptor, opened_stat
            finally:
                os.close(descriptor)
        return
    with _parent_fd(root, relative) as (parent_descriptor, name):
        flags = _READ_FLAGS | _NOFOLLOW
        if expect == "directory":
            flags |= _DIRECTORY
        try:
            descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        except OSError as error:
            raise PayloadError(
                f"link or reparse point or unsafe ancestor is forbidden: {relative}: {error}"
            ) from error
        try:
            opened = os.fstat(descriptor)
            if _kind(opened) != expect:
                raise PayloadError(f"payload path has wrong type: {relative}")
            yield descriptor, opened
        finally:
            os.close(descriptor)


def inspect_secure(root: pathlib.Path, relative: str, *, expect: str | None = None) -> tuple[str, os.stat_result]:
    """Inspect a relative entry through an anchored no-follow descriptor."""

    relative = normalize_relative_path(relative)
    if os.name == "nt":
        try:
            opened = _windows_open_verified(
                root,
                relative,
                access=GENERIC_READ,
                share=FILE_SHARE_READ,
                disposition=OPEN_EXISTING,
                create_parents=False,
                final_directory=None if expect is None else expect == "directory",
            )
        except FileNotFoundError as error:
            raise PayloadError(
                f"cannot inspect payload path: {relative}: {error}"
            ) from error
        with opened as handles:
            entry_kind = "directory" if handles.final_is_directory else "file"
            if expect is not None and entry_kind != expect:
                raise PayloadError(f"payload path has wrong type: {relative}")
            return entry_kind, _windows_stat_view(
                handles.api, handles.final_handle, directory=handles.final_is_directory
            )
    path = root / pathlib.PurePosixPath(relative)
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise PayloadError(f"cannot inspect payload path: {relative}: {error}") from error
    entry_kind = _kind(path_stat)
    if expect is not None and entry_kind != expect:
        raise PayloadError(f"payload path has wrong type: {relative}")
    with _open_existing(root, relative, expect=entry_kind) as (descriptor, opened):
        if not _same_object(path_stat, opened):
            raise PayloadError(f"payload path changed while opening: {relative}")
        return entry_kind, opened


def read_file_secure(root: pathlib.Path, relative: str) -> bytes:
    """Read a regular file from a stable no-follow descriptor."""

    with _open_existing(root, relative) as (descriptor, before):
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if not _same_identity(before, after):
            raise PayloadError(f"payload source changed during secure read: {relative}")
        if os.name != "nt" and not _path_identity(root, relative, before):
            raise PayloadError(f"payload source changed during secure read: {relative}")
    return b"".join(chunks)


def hash_file_secure(root: pathlib.Path, relative: str) -> tuple[str, os.stat_result]:
    """Hash a regular file through a stable no-follow descriptor."""

    digest = hashlib.sha256()
    with _open_existing(root, relative) as (descriptor, before):
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        if not _same_identity(before, after):
            raise PayloadError(f"payload file changed during secure hash: {relative}")
        if os.name != "nt" and not _path_identity(root, relative, before):
            raise PayloadError(f"payload file changed during secure hash: {relative}")
    return digest.hexdigest(), before


def _copy_stream(source_fd: int, destination_fd: int) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(source_fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        view = memoryview(chunk)
        while view:
            written = os.write(destination_fd, view)
            view = view[written:]
    return digest.hexdigest()


def _path_identity(root: pathlib.Path, relative: str, expected: os.stat_result) -> bool:
    try:
        with _open_existing(root, relative) as (_, current):
            return _same_object(expected, current)
    except PayloadError:
        return False


def copy_file_secure(
    source_root: pathlib.Path,
    source_relative: str,
    destination_root: pathlib.Path,
    destination_relative: str,
    mode: int,
) -> str:
    """Copy one file using stable source and exclusive destination descriptors."""

    source_relative = normalize_relative_path(source_relative)
    destination_relative = normalize_relative_path(destination_relative)
    with _open_existing(source_root, source_relative) as (source_fd, source_before):
        if os.name == "nt":
            opened = _windows_open_verified(
                destination_root,
                destination_relative,
                access=GENERIC_READ | GENERIC_WRITE,
                share=0,
                disposition=CREATE_NEW,
                create_parents=True,
                final_directory=False,
            )
            with opened as handles:
                destination_fd = _windows_descriptor_from_verified(
                    handles, os.O_RDWR | _BINARY
                )
                try:
                    destination_before = os.fstat(destination_fd)
                    if _kind(destination_before) != "file":
                        raise PayloadError(f"payload destination is not regular: {destination_relative}")
                    digest = _copy_stream(source_fd, destination_fd)
                    _windows_set_writable(
                        handles.api, handles.final_handle, writable=bool(mode & 0o222)
                    )
                    os.fsync(destination_fd)
                    source_after = os.fstat(source_fd)
                    destination_after = os.fstat(destination_fd)
                    if not _same_identity(source_before, source_after):
                        raise PayloadError(f"source changed during secure copy: {source_relative}")
                    if not _same_object(destination_before, destination_after):
                        raise PayloadError(f"destination changed during secure copy: {destination_relative}")
                finally:
                    os.close(destination_fd)
            return digest
        else:
            with _parent_fd(destination_root, destination_relative, create=True) as (parent_fd, name):
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY | _CLOEXEC | _NOFOLLOW
                try:
                    destination_fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
                except OSError as error:
                    raise PayloadError(
                        f"cannot create exclusive payload destination: {destination_relative}: {error}"
                    ) from error
                destination_before = os.fstat(destination_fd)
                if _kind(destination_before) != "file":
                    raise PayloadError(f"payload destination is not regular: {destination_relative}")
                digest = _copy_stream(source_fd, destination_fd)
                if not hasattr(os, "fchmod"):
                    raise PayloadError("descriptor chmod is unavailable")
                os.fchmod(destination_fd, mode)
                os.fsync(destination_fd)
                source_after = os.fstat(source_fd)
                destination_after = os.fstat(destination_fd)
                if not _same_identity(source_before, source_after):
                    raise PayloadError(f"source changed during secure copy: {source_relative}")
                if not _same_object(destination_before, destination_after):
                    raise PayloadError(f"destination changed during secure copy: {destination_relative}")
        if not _path_identity(source_root, source_relative, source_before) or not _path_identity(
            destination_root, destination_relative, destination_before
        ):
            raise PayloadError("source or destination changed during secure copy")
        return digest


def write_file_secure(root: pathlib.Path, relative: str, data: bytes, mode: int = 0o644) -> None:
    """Create a new file exclusively beneath a secure root."""

    relative = normalize_relative_path(relative)
    if os.name == "nt":
        opened = _windows_open_verified(
            root, relative, access=GENERIC_READ | GENERIC_WRITE,
            share=0, disposition=CREATE_NEW, create_parents=True,
            final_directory=False,
        )
        with opened as handles:
            descriptor = _windows_descriptor_from_verified(
                handles, os.O_RDWR | _BINARY
            )
            try:
                view = memoryview(data)
                while view:
                    written = os.write(descriptor, view)
                    view = view[written:]
                _windows_set_writable(
                    handles.api, handles.final_handle, writable=bool(mode & 0o222)
                )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return
    with _parent_fd(root, relative, create=True) as (parent_fd, name):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY | _CLOEXEC | _NOFOLLOW
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except OSError as error:
            raise PayloadError(f"cannot create secure payload file: {relative}: {error}") from error
        try:
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            if not hasattr(os, "fchmod"):
                raise PayloadError("descriptor chmod is unavailable")
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
            expected = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    if not _path_identity(root, relative, expected):
        raise PayloadError(f"payload destination changed during secure write: {relative}")


def modes_match(
    actual: int | None,
    expected: int | None,
    *,
    is_windows: bool | None = None,
) -> bool:
    """Compare exact POSIX modes or the representable Windows writable bit."""

    if actual is None or expected is None:
        return actual == expected
    windows = os.name == "nt" if is_windows is None else is_windows
    if windows:
        return bool(actual & stat.S_IWRITE) == bool(expected & 0o222)
    return actual == expected


def mode_matches(file_stat: os.stat_result, expected: int, *, is_windows: bool | None = None) -> bool:
    """Check exact POSIX modes or the representable Windows writable bit."""

    return modes_match(
        stat.S_IMODE(file_stat.st_mode), expected, is_windows=is_windows
    )


def set_directory_mode_secure(root: pathlib.Path, relative: str, mode: int) -> None:
    """Set a directory mode through an anchored descriptor and verify it."""

    relative = normalize_relative_path(relative)
    if os.name == "nt":
        opened = _windows_open_verified(
            root, relative,
            access=GENERIC_READ | FILE_WRITE_ATTRIBUTES,
            share=FILE_SHARE_READ,
            disposition=OPEN_EXISTING,
            create_parents=False,
            final_directory=True,
        )
        with opened as handles:
            _windows_set_writable(
                handles.api, handles.final_handle, writable=bool(mode & 0o222)
            )
        return
    with _open_existing(root, relative, expect="directory") as (descriptor, before):
        os.fchmod(descriptor, mode)
        after = os.fstat(descriptor)
        if not _same_object(before, after) or not mode_matches(after, mode):
            raise PayloadError(f"directory changed during secure chmod: {relative}")


def _walk_tree_windows(
    root: pathlib.Path,
    *,
    api: object,
    scandir: object,
) -> dict[str, tuple[str, object]]:
    """Enumerate a Windows tree while directory handles pin every active path."""

    found: dict[str, tuple[str, object]] = {}

    def walk(relative: str | None) -> None:
        if relative is None:
            anchor_root = root.parent
            anchor_relative = normalize_relative_path(root.name)
            current_path = root
        else:
            anchor_root = root
            anchor_relative = relative
            current_path = root / pathlib.PurePosixPath(relative)
        opened = _windows_open_verified(
            anchor_root,
            anchor_relative,
            access=GENERIC_READ,
            share=FILE_SHARE_READ,
            disposition=OPEN_EXISTING,
            create_parents=False,
            final_directory=True,
            api=api,
        )
        with opened:
            with scandir(current_path) as iterator:
                names = sorted(entry.name for entry in iterator)
            for name in names:
                child_relative = name if relative is None else f"{relative}/{name}"
                child = _windows_open_verified(
                    root,
                    child_relative,
                    access=GENERIC_READ,
                    share=FILE_SHARE_READ,
                    disposition=OPEN_EXISTING,
                    create_parents=False,
                    final_directory=None,
                    api=api,
                )
                with child as handles:
                    entry_type = "directory" if handles.final_is_directory else "file"
                    found[child_relative] = (
                        entry_type,
                        _windows_stat_view(
                            handles.api,
                            handles.final_handle,
                            directory=handles.final_is_directory,
                        ),
                    )
                    if handles.final_is_directory:
                        walk(child_relative)

    walk(None)
    return found


def walk_tree_secure(root: pathlib.Path) -> dict[str, tuple[str, object]]:
    """Return a no-follow recursive inventory with directories pinned while listed."""

    if os.name == "nt":
        return _walk_tree_windows(root, api=_WindowsApi(), scandir=os.scandir)
    _validate_root(root)
    found: dict[str, tuple[str, object]] = {}
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        directory_path = pathlib.Path(directory)
        for name in sorted(directory_names + file_names):
            path = directory_path / name
            relative = path.relative_to(root).as_posix()
            found[relative] = inspect_secure(root, relative)
    return found


@dataclasses.dataclass(frozen=True)
class SecureEntry:
    """One handle-observed entry used by the recovery transaction boundary."""

    entry_type: str
    digest: str | None
    mode: int | None
    identity: tuple[int, int] | str | None


def _rename_no_replace_posix(
    source_parent_fd: int,
    source_name: str,
    destination_parent_fd: int,
    destination_name: str,
) -> None:
    """Atomically rename without replacement using the native POSIX extension."""

    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform.startswith("linux"):
        operation = getattr(libc, "renameat2", None)
        flag = 0x1  # RENAME_NOREPLACE
    elif sys.platform == "darwin":
        operation = getattr(libc, "renameatx_np", None)
        flag = 0x4  # RENAME_EXCL from <sys/stdio.h>
    else:
        operation = None
        flag = 0
    if operation is None:
        raise PayloadError("UNSUPPORTED_ENVIRONMENT: native no-replace rename unavailable")
    operation.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    operation.restype = ctypes.c_int
    if operation(
        source_parent_fd,
        source,
        destination_parent_fd,
        destination,
        flag,
    ) != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise FileExistsError(error, os.strerror(error), destination_name)
        raise OSError(error, os.strerror(error), destination_name)


class AnchoredFilesystem:
    """Mutation boundary rooted in one retained :class:`PinnedRoot` handle."""

    def __init__(self, pinned: PinnedRoot, boundary: object | None = None):
        self.pinned = pinned
        self.root = pinned.root
        self._boundary = boundary if boundary is not None else lambda: pinned.verify()
        self._quarantine_relative: str | None = None
        self._quarantine_counts: dict[str, int] = {}

    def set_quarantine(self, relative: str) -> None:
        """Bind destructive target moves to one exclusive recovery directory."""

        self._quarantine_relative = normalize_relative_path(relative)

    def _quarantine_name(self, relative: str, role: str) -> str:
        if self._quarantine_relative is None:
            raise PayloadError("recovery quarantine is not configured")
        index = self._quarantine_counts.get(relative, 0)
        self._quarantine_counts[relative] = index + 1
        path_digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
        return f"{role}-{path_digest}-{index:04d}"

    def verify_boundary(self) -> None:
        """Reverify the retained root plus the caller's lock identity guard."""

        self.pinned.verify()
        self._boundary()

    @contextlib.contextmanager
    def _posix_parent(
        self, relative: str, *, missing_ok: bool = False
    ) -> Iterator[tuple[int, str] | None]:
        relative = normalize_relative_path(relative)
        if self.pinned._descriptor is None:
            raise PayloadError("POSIX anchored filesystem requires retained root descriptor")
        root_fd = os.dup(self.pinned._descriptor)
        descriptors = [root_fd]
        current = root_fd
        try:
            parts = pathlib.PurePosixPath(relative).parts
            for part in parts[:-1]:
                try:
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
                except FileNotFoundError:
                    if missing_ok:
                        yield None
                        return
                    raise PayloadError(f"secure path parent is missing: {relative}")
                except OSError as error:
                    raise PayloadError(
                        f"cannot open anchored path parent: {relative}: {error}"
                    ) from error
                opened = os.fstat(child)
                current_stat = os.stat(part, dir_fd=current, follow_symlinks=False)
                if _kind(opened) != "directory" or not _same_object(opened, current_stat):
                    os.close(child)
                    raise PayloadError(f"anchored path parent changed: {relative}")
                descriptors.append(child)
                current = child
            yield current, parts[-1]
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _posix_observe(self, relative: str) -> SecureEntry:
        with self._posix_parent(relative, missing_ok=True) as parent:
            if parent is None:
                return SecureEntry("missing", None, None, None)
            parent_fd, name = parent
            try:
                descriptor = os.open(
                    name,
                    _READ_FLAGS | _NOFOLLOW | _NONBLOCK,
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                return SecureEntry("missing", None, None, None)
            except OSError as error:
                raise PayloadError(f"cannot open anchored target: {relative}: {error}") from error
            try:
                opened = os.fstat(descriptor)
                entry_type = _kind(opened)
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if not _same_object(opened, current):
                    raise PayloadError(f"anchored target changed while opening: {relative}")
                digest: str | None
                if entry_type == "file":
                    digest = _hash_descriptor(descriptor, opened)
                else:
                    entries: list[dict[str, object]] = []
                    for child_name in sorted(os.listdir(descriptor)):
                        child_fd = os.open(
                            child_name,
                            _READ_FLAGS | _NOFOLLOW | _NONBLOCK,
                            dir_fd=descriptor,
                        )
                        try:
                            child_stat = os.fstat(child_fd)
                            child_type = _kind(child_stat)
                            child_hash = (
                                _hash_descriptor(child_fd, child_stat)
                                if child_type == "file"
                                else None
                            )
                            current_child = os.stat(
                                child_name,
                                dir_fd=descriptor,
                                follow_symlinks=False,
                            )
                            if not _same_object(child_stat, current_child):
                                raise PayloadError(
                                    "directory child changed during anchored observation"
                                )
                            entries.append(
                                {
                                    "name": child_name,
                                    "entry_type": child_type,
                                    "sha256": child_hash,
                                }
                            )
                        finally:
                            os.close(child_fd)
                    digest = digest_document({"entries": entries})
                return SecureEntry(
                    entry_type,
                    digest,
                    stat.S_IMODE(opened.st_mode),
                    (opened.st_dev, opened.st_ino),
                )
            finally:
                os.close(descriptor)

    def observe(
        self,
        relative: str,
        *,
        cooperative_children: frozenset[str] | set[str] = frozenset(),
    ) -> SecureEntry:
        """Observe one path through the retained root without following links."""

        self.verify_boundary()
        relative = normalize_relative_path(relative)
        if os.name != "nt":
            return self._posix_observe(relative)
        try:
            entry_type, file_stat = inspect_secure(self.root, relative)
        except PayloadError as error:
            if "cannot inspect payload path" in str(error):
                return SecureEntry("missing", None, None, None)
            raise
        digest = None
        if entry_type == "file":
            digest = hashlib.sha256(read_file_secure(self.root, relative)).hexdigest()
        else:
            entries = [
                dataclasses.asdict(item)
                for item in list_immediate_secure(
                    self.root,
                    relative,
                    cooperative_children=cooperative_children,
                )
            ]
            digest = digest_document({"entries": entries})
        opened = _windows_open_verified(
            self.root,
            relative,
            access=GENERIC_READ,
            share=FILE_SHARE_READ | FILE_SHARE_WRITE,
            disposition=OPEN_EXISTING,
            create_parents=False,
            final_directory=entry_type == "directory",
        )
        with opened as handles:
            volume, index = handles.api.identity(handles.final_handle)
            identity = f"windows:{volume}:{index}"
        return SecureEntry(entry_type, digest, stat.S_IMODE(file_stat.st_mode), identity)

    def list_immediate(self, relative: str) -> tuple[ImmediateEntry, ...]:
        """List a directory through the retained root handle without recursion."""

        self.verify_boundary()
        if os.name == "nt":
            return list_immediate_secure(self.root, relative)
        with self._posix_parent(relative) as parent:
            assert parent is not None
            parent_fd, name = parent
            directory_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            try:
                entries: list[ImmediateEntry] = []
                for child_name in sorted(os.listdir(directory_fd)):
                    child_fd = os.open(
                        child_name,
                        _READ_FLAGS | _NOFOLLOW | _NONBLOCK,
                        dir_fd=directory_fd,
                    )
                    try:
                        child_stat = os.fstat(child_fd)
                        child_type = _kind(child_stat)
                        child_hash = (
                            _hash_descriptor(child_fd, child_stat)
                            if child_type == "file"
                            else None
                        )
                        current_child = os.stat(
                            child_name,
                            dir_fd=directory_fd,
                            follow_symlinks=False,
                        )
                        if not _same_object(child_stat, current_child):
                            raise PayloadError(
                                "directory child changed during anchored listing"
                            )
                        entries.append(ImmediateEntry(child_name, child_type, child_hash))
                    finally:
                        os.close(child_fd)
                return tuple(entries)
            finally:
                os.close(directory_fd)

    def same_filesystem(self, relative: str) -> bool:
        """Compare an observed entry's native volume/device with the pinned root."""

        observed = self.observe(relative)
        if observed.identity is None:
            return False
        root_identity = secure_root_identity(self.pinned)
        if os.name == "nt":
            return str(observed.identity).split(":", 2)[1] == root_identity.split(":", 2)[1]
        assert isinstance(observed.identity, tuple)
        return observed.identity[0] == int(root_identity.split(":", 2)[1])

    def recovery_tree_digest(self, relative: str) -> str:
        """Digest a recovery tree while retaining the transaction root anchor."""

        inventory: list[dict[str, object]] = []

        def visit(directory: str) -> None:
            for item in self.list_immediate(directory):
                child = f"{directory}/{item.name}"
                inventory.append(
                    {
                        "path": child[len(relative) + 1 :],
                        "entry_type": item.entry_type,
                        "sha256": item.sha256,
                    }
                )
                if item.entry_type == "directory":
                    visit(child)

        visit(relative)
        return digest_document({"entries": inventory})

    def tree_digest(self, relative: str) -> str:
        """Recursively digest an ordinary tree without following links."""

        digest, _identities = self.tree_digest_and_identities(relative)
        return digest

    def tree_digest_and_identities(
        self,
        relative: str,
        expected: SecureEntry | None = None,
    ) -> tuple[str, tuple[tuple[str, object], ...]]:
        """Digest a tree and retain ephemeral identities for stale-plan checks."""

        inventory: list[dict[str, object]] = []
        identities: list[tuple[str, object]] = []

        def visit(path: str, parent_observed: SecureEntry | None = None) -> None:
            before = self.observe(path)
            if before.entry_type != "directory":
                raise PayloadError("recursive digest target is not a directory")
            continuity = expected if path == relative else parent_observed
            if continuity is not None and not self.matches(before, continuity):
                raise PayloadError("recursive digest child identity changed")
            identities.append((path[len(relative) :], before.identity))
            for item in self.list_immediate(path):
                child = f"{path}/{item.name}"
                observed = self.observe(child)
                if observed.entry_type != item.entry_type:
                    raise PayloadError("recursive digest child type changed")
                identities.append((child[len(relative) :], observed.identity))
                inventory.append(
                    {
                        "path": child[len(relative) + 1 :],
                        "entry_type": observed.entry_type,
                        "mode": observed.mode,
                        "sha256": observed.digest if observed.entry_type == "file" else None,
                    }
                )
                if observed.entry_type == "directory":
                    identities.pop()
                    visit(child, observed)
            after = self.observe(path)
            if not self.matches(after, before):
                raise PayloadError("directory changed during recursive digest")

        visit(relative)
        return digest_document({"entries": inventory}), tuple(identities)

    @staticmethod
    def matches(observed: SecureEntry, expected: SecureEntry) -> bool:
        """Compare exact logical state and retained identity when present."""

        return (
            observed.entry_type == expected.entry_type
            and observed.digest == expected.digest
            and modes_match(observed.mode, expected.mode)
            and (expected.identity is None or observed.identity == expected.identity)
        )

    def read_file(self, relative: str, expected: SecureEntry | None = None) -> bytes:
        """Read a file and reject any identity or content change."""

        before = self.observe(relative)
        if before.entry_type != "file" or (expected is not None and not self.matches(before, expected)):
            raise PayloadError("anchored file differs from expected state")
        if os.name == "nt":
            content = read_file_secure(self.root, relative)
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                descriptor = os.open(name, _READ_FLAGS | _NOFOLLOW, dir_fd=parent_fd)
                try:
                    chunks = []
                    while True:
                        chunk = os.read(descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                finally:
                    os.close(descriptor)
                content = b"".join(chunks)
        after = self.observe(relative)
        if not self.matches(after, before):
            raise PayloadError("anchored file changed during read")
        return content

    def read_file_verified(
        self, relative: str, *, expected_digest: str, expected_mode: int
    ) -> bytes:
        """Read and verify bytes/type/mode/hash through one retained handle."""

        relative = normalize_relative_path(relative)
        self.verify_boundary()
        if os.name == "nt":
            opened = _windows_open_verified(
                self.root,
                relative,
                access=GENERIC_READ,
                share=FILE_SHARE_READ,
                disposition=OPEN_EXISTING,
                create_parents=False,
                final_directory=False,
            )
            with opened as handles:
                descriptor = _windows_descriptor_from_verified(opened, os.O_RDONLY | _BINARY)
                try:
                    native_handle = __import__("msvcrt").get_osfhandle(descriptor)
                    before_identity = handles.api.identity(native_handle)
                    before_info = handles.api.basic_info(native_handle)
                    chunks: list[bytes] = []
                    while True:
                        chunk = os.read(descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    after_identity = handles.api.identity(native_handle)
                    after_info = handles.api.basic_info(native_handle)
                finally:
                    os.close(descriptor)
                mode = stat.S_IREAD
                if not after_info.FileAttributes & FILE_ATTRIBUTE_READONLY:
                    mode |= stat.S_IWRITE
                if before_identity != after_identity or before_info.FileAttributes != after_info.FileAttributes:
                    raise PayloadError("verified file identity changed during read")
                content = b"".join(chunks)
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                descriptor = os.open(name, _READ_FLAGS | _NOFOLLOW, dir_fd=parent_fd)
                try:
                    before = os.fstat(descriptor)
                    if _kind(before) != "file":
                        raise PayloadError("verified snapshot is not a regular file")
                    chunks = []
                    while True:
                        chunk = os.read(descriptor, 1024 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    after = os.fstat(descriptor)
                    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if not _same_object(before, after) or not _same_object(after, current):
                        raise PayloadError("verified file identity changed during read")
                    mode = stat.S_IMODE(after.st_mode)
                    content = b"".join(chunks)
                finally:
                    os.close(descriptor)
        if (
            not modes_match(mode, expected_mode)
            or hashlib.sha256(content).hexdigest() != expected_digest
        ):
            raise PayloadError("verified file bytes or mode do not match authority")
        return content

    def create_directory_exclusive(
        self,
        relative: str,
        mode: int = 0o700,
        on_destructive: object | None = None,
    ) -> SecureEntry:
        """Create a new directory exclusively and immediately verify its identity."""

        self.verify_boundary()
        if self.observe(relative).entry_type != "missing":
            raise PayloadError("exclusive directory destination already exists")
        mark_destructive = on_destructive if on_destructive is not None else lambda: None
        if os.name == "nt":
            parts = pathlib.PurePosixPath(relative).parts
            parent_relative = "/".join(parts[:-1])
            parent_root = self.root if parent_relative else self.root.parent
            opened_relative = parent_relative if parent_relative else normalize_relative_path(self.root.name)
            parent = _windows_open_verified(
                parent_root,
                opened_relative,
                access=GENERIC_READ,
                share=FILE_SHARE_READ | FILE_SHARE_WRITE,
                disposition=OPEN_EXISTING,
                create_parents=False,
                final_directory=True,
            )
            with parent as handles:
                mark_destructive()
                handles.api.create_directory(str(self.root / pathlib.PurePosixPath(relative)))
                created = _windows_open_verified(
                    self.root,
                    relative,
                    access=GENERIC_READ | FILE_WRITE_ATTRIBUTES,
                    share=FILE_SHARE_READ | FILE_SHARE_WRITE,
                    disposition=OPEN_EXISTING,
                    create_parents=False,
                    final_directory=True,
                    api=handles.api,
                )
                with created as created_handles:
                    _windows_set_writable(
                        handles.api,
                        created_handles.final_handle,
                        writable=bool(mode & 0o222),
                    )
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                mark_destructive()
                os.mkdir(name, mode=mode, dir_fd=parent_fd)
                created_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
                try:
                    os.fchmod(created_fd, mode)
                finally:
                    os.close(created_fd)
                os.fsync(parent_fd)
        created_state = self.observe(relative)
        if created_state.entry_type != "directory":
            raise PayloadError("exclusive directory creation verification failed")
        return created_state

    def atomic_replace(
        self,
        relative: str,
        data: bytes,
        mode: int,
        expected: SecureEntry,
        token: str,
        on_destructive: object | None = None,
        on_quarantined: object | None = None,
    ) -> SecureEntry:
        """Replace one exact expected file through anchored temporary storage."""

        self.verify_boundary()
        mark_destructive = on_destructive if on_destructive is not None else lambda: None
        mark_quarantined = on_quarantined if on_quarantined is not None else lambda: None
        current = self.observe(relative)
        if not self.matches(current, expected):
            raise PayloadError("atomic replacement pre-state changed")
        parts = pathlib.PurePosixPath(relative).parts
        temporary_name = f".{parts[-1]}.{token}.tmp"
        temporary_relative = "/".join((*parts[:-1], temporary_name))
        temp_identity: tuple[int, int] | str | None = None
        if os.name == "nt":
            opened = _windows_open_verified(
                self.root,
                temporary_relative,
                access=GENERIC_READ | GENERIC_WRITE | DELETE_ACCESS,
                share=FILE_SHARE_READ | FILE_SHARE_WRITE,
                disposition=CREATE_NEW,
                create_parents=False,
                final_directory=False,
            )
            with opened as handles:
                descriptor = _windows_descriptor_from_verified(opened, os.O_RDWR | _BINARY)
                renamed = False
                native_handle: int | None = None
                try:
                    view = memoryview(data)
                    while view:
                        count = os.write(descriptor, view)
                        if count <= 0:
                            raise PayloadError("atomic replacement short write made no progress")
                        view = view[count:]
                    os.fsync(descriptor)
                    native_handle = __import__("msvcrt").get_osfhandle(descriptor)
                    _windows_set_writable(
                        handles.api, native_handle, writable=bool(mode & 0o222)
                    )
                    self.verify_boundary()
                    if not self.matches(self.observe(relative), expected):
                        raise PayloadError("atomic replacement target raced")
                    if expected.entry_type != "missing":
                        target = _windows_open_verified(
                            self.root,
                            relative,
                            access=GENERIC_READ | DELETE_ACCESS | FILE_WRITE_ATTRIBUTES,
                            share=FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                            disposition=OPEN_EXISTING,
                            create_parents=False,
                            final_directory=False,
                            api=handles.api,
                        )
                        with target as target_handles:
                            volume, index = handles.api.identity(
                                target_handles.final_handle
                            )
                            if expected.identity != f"windows:{volume}:{index}":
                                raise PayloadError(
                                    "atomic replacement target identity raced"
                                )
                            _windows_set_writable(
                                handles.api, target_handles.final_handle, writable=True
                            )
                            mark_destructive()
                            quarantine_name = self._quarantine_name(relative, "before")
                            assert self._quarantine_relative is not None
                            handles.api.rename_no_replace(
                                target_handles.final_handle,
                                str(
                                    self.root
                                    / pathlib.PurePosixPath(self._quarantine_relative)
                                    / quarantine_name
                                ),
                            )
                        mark_quarantined()
                    else:
                        mark_destructive()
                    handles.api.rename_no_replace(
                        native_handle, str(self.root / pathlib.PurePosixPath(relative))
                    )
                    renamed = True
                finally:
                    if not renamed and native_handle is not None:
                        handles.api.mark_delete(native_handle)
                    os.close(descriptor)
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC
                temp_fd = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
                try:
                    temp_stat = os.fstat(temp_fd)
                    temp_identity = (temp_stat.st_dev, temp_stat.st_ino)
                    view = memoryview(data)
                    while view:
                        count = os.write(temp_fd, view)
                        if count <= 0:
                            raise PayloadError("atomic replacement short write made no progress")
                        view = view[count:]
                    os.fchmod(temp_fd, mode)
                    os.fsync(temp_fd)
                    self.verify_boundary()
                    if not self.matches(self.observe(relative), expected):
                        raise PayloadError("atomic replacement target raced")
                    mark_destructive()
                    if expected.entry_type != "missing":
                        target_fd = os.open(
                            name,
                            _READ_FLAGS | _NOFOLLOW | _NONBLOCK,
                            dir_fd=parent_fd,
                        )
                        try:
                            target_stat = os.fstat(target_fd)
                            if expected.identity != (target_stat.st_dev, target_stat.st_ino):
                                raise PayloadError("atomic replacement target identity raced")
                            quarantine_name = self._quarantine_name(relative, "before")
                            assert self._quarantine_relative is not None
                            with self._posix_parent(
                                f"{self._quarantine_relative}/{quarantine_name}"
                            ) as quarantine_parent:
                                assert quarantine_parent is not None
                                quarantine_fd, _ = quarantine_parent
                                _rename_no_replace_posix(
                                    parent_fd,
                                    name,
                                    quarantine_fd,
                                    quarantine_name,
                                )
                                moved = os.stat(
                                    quarantine_name,
                                    dir_fd=quarantine_fd,
                                    follow_symlinks=False,
                                )
                                if (moved.st_dev, moved.st_ino) != (
                                    target_stat.st_dev,
                                    target_stat.st_ino,
                                ):
                                    try:
                                        _rename_no_replace_posix(
                                            quarantine_fd,
                                            quarantine_name,
                                            parent_fd,
                                            name,
                                        )
                                    finally:
                                        raise PayloadError(
                                            "atomic replacement source identity raced"
                                        )
                                mark_quarantined()
                        finally:
                            os.close(target_fd)
                    _rename_no_replace_posix(
                        parent_fd,
                        temporary_name,
                        parent_fd,
                        name,
                    )
                    os.fsync(parent_fd)
                    temp_identity = None
                finally:
                    os.close(temp_fd)
                    if temp_identity is not None:
                        try:
                            leftover = os.stat(
                                temporary_name, dir_fd=parent_fd, follow_symlinks=False
                            )
                            if (leftover.st_dev, leftover.st_ino) == temp_identity:
                                os.unlink(temporary_name, dir_fd=parent_fd)
                        except FileNotFoundError:
                            pass
        result = self.observe(relative)
        expected_digest = hashlib.sha256(data).hexdigest()
        if result.entry_type != "file" or result.digest != expected_digest:
            raise PayloadError("atomic replacement result verification failed")
        return result

    def atomic_replace_internal(
        self,
        relative: str,
        data: bytes,
        mode: int,
        token: str,
        *,
        failpoint: object | None = None,
    ) -> SecureEntry:
        """Atomically overwrite one current-generation journal without quarantine."""

        relative = normalize_relative_path(relative)
        parts = pathlib.PurePosixPath(relative).parts
        if (
            len(parts) != 5
            or parts[:3] != (".codex", "codex-game-studios", "recovery")
            or parts[-1] != "journal.json"
        ):
            raise PayloadError("internal replacement path is outside a recovery generation")
        self.verify_boundary()
        expected = self.observe(relative)
        if expected.entry_type not in {"missing", "file"}:
            raise PayloadError("internal journal target is not a regular file")
        trigger = failpoint if failpoint is not None else lambda _phase: None
        temporary_name = f".journal.{token}.tmp"
        temporary_relative = "/".join((*parts[:-1], temporary_name))
        if os.name == "nt":
            opened = _windows_open_verified(
                self.root,
                temporary_relative,
                access=GENERIC_READ | GENERIC_WRITE | DELETE_ACCESS,
                share=FILE_SHARE_READ | FILE_SHARE_WRITE,
                disposition=CREATE_NEW,
                create_parents=False,
                final_directory=False,
            )
            with opened as handles:
                descriptor = _windows_descriptor_from_verified(opened, os.O_RDWR | _BINARY)
                renamed = False
                native_handle: int | None = None
                try:
                    view = memoryview(data)
                    while view:
                        written = os.write(descriptor, view)
                        if written <= 0:
                            raise PayloadError("internal journal short write made no progress")
                        view = view[written:]
                    os.fsync(descriptor)
                    native_handle = __import__("msvcrt").get_osfhandle(descriptor)
                    _windows_set_writable(handles.api, native_handle, writable=bool(mode & 0o222))
                    if not self.matches(self.observe(relative), expected):
                        raise PayloadError("internal journal target raced")
                    trigger("before-rename")
                    trigger("at-rename")
                    handles.api.rename_replace(
                        native_handle, str(self.root / pathlib.PurePosixPath(relative))
                    )
                    renamed = True
                    trigger("after-rename")
                finally:
                    if not renamed and native_handle is not None:
                        handles.api.mark_delete(native_handle)
                    os.close(descriptor)
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                temp_fd = os.open(
                    temporary_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
                    0o600,
                    dir_fd=parent_fd,
                )
                temp_identity = None
                try:
                    temp_stat = os.fstat(temp_fd)
                    temp_identity = (temp_stat.st_dev, temp_stat.st_ino)
                    view = memoryview(data)
                    while view:
                        written = os.write(temp_fd, view)
                        if written <= 0:
                            raise PayloadError("internal journal short write made no progress")
                        view = view[written:]
                    os.fchmod(temp_fd, mode)
                    os.fsync(temp_fd)
                    if not self.matches(self.observe(relative), expected):
                        raise PayloadError("internal journal target raced")
                    trigger("before-rename")
                    trigger("at-rename")
                    os.rename(temporary_name, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
                    temp_identity = None
                    os.fsync(parent_fd)
                    trigger("after-rename")
                finally:
                    os.close(temp_fd)
                    if temp_identity is not None:
                        try:
                            leftover = os.stat(temporary_name, dir_fd=parent_fd, follow_symlinks=False)
                            if (leftover.st_dev, leftover.st_ino) == temp_identity:
                                os.unlink(temporary_name, dir_fd=parent_fd)
                        except FileNotFoundError:
                            pass
        result = self.observe(relative)
        if result.entry_type != "file" or result.digest != hashlib.sha256(data).hexdigest():
            raise PayloadError("internal journal replacement verification failed")
        return result

    def remove(
        self,
        relative: str,
        expected: SecureEntry,
        on_destructive: object | None = None,
        on_quarantined: object | None = None,
    ) -> None:
        """Remove exactly the securely observed file or empty directory."""

        self.verify_boundary()
        if not self.matches(self.observe(relative), expected):
            raise PayloadError("remove pre-state changed")
        mark_destructive = on_destructive if on_destructive is not None else lambda: None
        mark_quarantined = on_quarantined if on_quarantined is not None else lambda: None
        if os.name == "nt":
            opened = _windows_open_verified(
                self.root,
                relative,
                access=GENERIC_READ | DELETE_ACCESS | FILE_WRITE_ATTRIBUTES,
                share=FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                disposition=OPEN_EXISTING,
                create_parents=False,
                final_directory=expected.entry_type == "directory",
            )
            with opened as handles:
                volume, index = handles.api.identity(handles.final_handle)
                if expected.identity != f"windows:{volume}:{index}":
                    raise PayloadError("remove target identity raced")
                if expected.entry_type == "file":
                    _windows_set_writable(handles.api, handles.final_handle, writable=True)
                mark_destructive()
                quarantine_name = self._quarantine_name(relative, "removed")
                assert self._quarantine_relative is not None
                handles.api.rename_no_replace(
                    handles.final_handle,
                    str(
                        self.root
                        / pathlib.PurePosixPath(self._quarantine_relative)
                        / quarantine_name
                    ),
                )
                mark_quarantined()
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                flags = _READ_FLAGS | _NOFOLLOW | _NONBLOCK
                if expected.entry_type == "directory":
                    flags |= _DIRECTORY
                target_fd = os.open(name, flags, dir_fd=parent_fd)
                try:
                    current = os.fstat(target_fd)
                    if expected.identity != (current.st_dev, current.st_ino):
                        raise PayloadError("remove target identity raced")
                    quarantine_name = self._quarantine_name(relative, "removed")
                    assert self._quarantine_relative is not None
                    with self._posix_parent(
                        f"{self._quarantine_relative}/{quarantine_name}"
                    ) as quarantine_parent:
                        assert quarantine_parent is not None
                        quarantine_fd, _ = quarantine_parent
                        mark_destructive()
                        _rename_no_replace_posix(
                            parent_fd, name, quarantine_fd, quarantine_name
                        )
                        moved = os.stat(
                            quarantine_name,
                            dir_fd=quarantine_fd,
                            follow_symlinks=False,
                        )
                        if (moved.st_dev, moved.st_ino) != (
                            current.st_dev,
                            current.st_ino,
                        ):
                            try:
                                _rename_no_replace_posix(
                                    quarantine_fd,
                                    quarantine_name,
                                    parent_fd,
                                    name,
                                )
                            finally:
                                raise PayloadError("remove source identity raced")
                        mark_quarantined()
                finally:
                    os.close(target_fd)
                os.fsync(parent_fd)
        if self.observe(relative).entry_type != "missing":
            raise PayloadError("remove result verification failed")

    def remove_internal_exact(
        self, relative: str, expected: SecureEntry, generation: str
    ) -> None:
        """Delete one proven pre-journal artifact without target quarantine semantics."""

        relative = normalize_relative_path(relative)
        generation = normalize_relative_path(generation)
        recovery = ".codex/codex-game-studios/recovery"
        if not (
            relative == generation
            or relative.startswith(f"{generation}/")
            or relative == recovery
        ):
            raise PayloadError("internal cleanup escaped the current recovery generation")
        self.verify_boundary()
        current = self.observe(relative)
        if not self.matches(current, expected) or current.entry_type not in {"file", "directory"}:
            raise PayloadError("internal cleanup identity changed")
        if os.name == "nt":
            opened = _windows_open_verified(
                self.root,
                relative,
                access=GENERIC_READ | DELETE_ACCESS | FILE_WRITE_ATTRIBUTES,
                share=FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                disposition=OPEN_EXISTING,
                create_parents=False,
                final_directory=current.entry_type == "directory",
            )
            with opened as handles:
                volume, index = handles.api.identity(handles.final_handle)
                if current.identity != f"windows:{volume}:{index}":
                    raise PayloadError("internal cleanup handle identity changed")
                if current.entry_type == "file":
                    _windows_set_writable(handles.api, handles.final_handle, writable=True)
                handles.api.mark_delete(handles.final_handle)
        else:
            with self._posix_parent(relative) as parent:
                assert parent is not None
                parent_fd, name = parent
                flags = _READ_FLAGS | _NOFOLLOW | _NONBLOCK
                if current.entry_type == "directory":
                    flags |= _DIRECTORY
                descriptor = os.open(name, flags, dir_fd=parent_fd)
                try:
                    opened = os.fstat(descriptor)
                    if current.identity != (opened.st_dev, opened.st_ino):
                        raise PayloadError("internal cleanup descriptor identity changed")
                    if current.entry_type == "directory":
                        os.rmdir(name, dir_fd=parent_fd)
                    else:
                        os.unlink(name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                finally:
                    os.close(descriptor)
        if self.observe(relative).entry_type != "missing":
            raise PayloadError("internal cleanup result verification failed")
