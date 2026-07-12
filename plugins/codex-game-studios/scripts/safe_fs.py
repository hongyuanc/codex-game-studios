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
import hashlib
import ntpath
import os
import pathlib
import stat
from typing import Iterator

from models import PayloadError, normalize_relative_path


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_READ_FLAGS = os.O_RDONLY | _BINARY | _CLOEXEC
_DIRECTORY_FLAGS = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
_IDENTITY_FIELDS = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_WRITE_ATTRIBUTES = 0x00000100
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
_VOLUME_NAME_DOS = 0
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


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
        self._get_file_information = kernel32.GetFileInformationByHandleEx
        self._get_file_information.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ]
        self._get_file_information.restype = wintypes.BOOL
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

    def create_file(self, path: str, access: int, share: int, disposition: int, flags: int) -> int:
        handle = self._create_file(path, access, share, None, disposition, flags, None)
        if handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def attributes(self, handle: int) -> tuple[int, int]:
        information = _FileAttributeTagInfo()
        if not self._get_file_information(
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
        if not self._get_file_information(
            handle, _FILE_BASIC_INFO_CLASS, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return information

    def set_basic_info(self, handle: int, information: _FileBasicInfo) -> None:
        if not self._set_file_information(
            handle, _FILE_BASIC_INFO_CLASS, ctypes.byref(information), ctypes.sizeof(information)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self, handle: int) -> None:
        if not self._close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def create_directory(self, path: str) -> None:
        if self._create_directory(path, None):
            return
        error = ctypes.get_last_error()
        if error != 183:
            raise ctypes.WinError(error)


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
                api.create_directory(directory_path)
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


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    if os.name == "nt":
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
        opened = _windows_open_verified(
            root, relative, access=GENERIC_READ, share=FILE_SHARE_READ,
            disposition=OPEN_EXISTING, create_parents=False,
            final_directory=None if expect is None else expect == "directory",
        )
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


def mode_matches(file_stat: os.stat_result, expected: int, *, is_windows: bool | None = None) -> bool:
    """Check exact POSIX modes or the representable Windows writable bit."""

    windows = os.name == "nt" if is_windows is None else is_windows
    if windows:
        expected_writable = bool(expected & 0o222)
        actual_writable = bool(file_stat.st_mode & stat.S_IWRITE)
        return expected_writable == actual_writable
    return stat.S_IMODE(file_stat.st_mode) == expected


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
