from __future__ import annotations

import contextlib
import ctypes
import ntpath
import os
import pathlib
import stat
from collections.abc import Iterator


GENERIC_READ = 0x80000000
FILE_APPEND_DATA = 0x00000004
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
OPEN_ALWAYS = 4
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_VOLUME_NAME_DOS = 0
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class UnsafeAtomicPathError(RuntimeError):
    """Raised when repository I/O cannot be proven to remain inside the root."""


def _relative_parts(
    root: pathlib.Path,
    relative: str | pathlib.Path,
) -> tuple[pathlib.Path, tuple[str, ...]]:
    try:
        raw = os.fspath(relative)
    except TypeError as error:
        raise UnsafeAtomicPathError("unsafe repository path type") from error
    if not isinstance(raw, str):
        raise UnsafeAtomicPathError("unsafe non-text repository path")
    if "\x00" in raw or any(0xD800 <= ord(character) <= 0xDFFF for character in raw):
        raise UnsafeAtomicPathError("unsafe malformed repository path")
    path = pathlib.Path(raw)
    if path.is_absolute():
        raise UnsafeAtomicPathError(f"unsafe absolute repository path: {raw}")
    separators = {os.sep}
    if os.altsep:
        separators.add(os.altsep)
    lexical_parts = [raw]
    for separator in separators:
        lexical_parts = [
            piece
            for part in lexical_parts
            for piece in part.split(separator)
        ]
    if not raw or any(part in {"", ".", ".."} for part in lexical_parts):
        raise UnsafeAtomicPathError(f"unsafe repository path: {raw!r}")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise UnsafeAtomicPathError(f"unsafe repository path: {raw!r}")
    try:
        trusted_root = pathlib.Path(root).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise UnsafeAtomicPathError("unsafe repository root") from error
    if not trusted_root.is_dir():
        raise UnsafeAtomicPathError("unsafe repository root is not a directory")
    return trusted_root, tuple(parts)


def _posix_after_component_open(parts: tuple[str, ...]) -> None:
    """Test seam invoked after a directory component has been safely opened."""


def _posix_open_flags(*flags: int) -> int:
    combined = 0
    for flag in flags:
        combined |= flag
    combined |= getattr(os, "O_CLOEXEC", 0)
    return combined


def _unsafe_open_error(relative: tuple[str, ...], error: OSError) -> UnsafeAtomicPathError:
    return UnsafeAtomicPathError(
        f"unsafe repository path: {'/'.join(relative)} ({error.strerror or error})"
    )


def _posix_verify_open_component(
    parent_fd: int,
    name: str,
    opened_fd: int,
    relative: tuple[str, ...],
) -> None:
    try:
        path_info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened_info = os.fstat(opened_fd)
    except OSError as error:
        raise _unsafe_open_error(relative, error) from error
    if (
        not stat.S_ISDIR(path_info.st_mode)
        or not stat.S_ISDIR(opened_info.st_mode)
        or (path_info.st_dev, path_info.st_ino)
        != (opened_info.st_dev, opened_info.st_ino)
    ):
        raise UnsafeAtomicPathError(
            f"unsafe replaced repository directory: {'/'.join(relative)}"
        )


def _posix_close_descriptors(descriptors: Iterator[int]) -> BaseException | None:
    first_error: BaseException | None = None
    for descriptor in descriptors:
        try:
            os.close(descriptor)
        except BaseException as error:
            if first_error is None:
                first_error = error
    return first_error


@contextlib.contextmanager
def _posix_parent_fd(
    root: pathlib.Path,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> Iterator[tuple[int, str]]:
    if not parts:
        raise UnsafeAtomicPathError("unsafe empty repository path")
    descriptors: list[int] = []
    directory_flags = _posix_open_flags(
        os.O_RDONLY,
        os.O_DIRECTORY,
        os.O_NOFOLLOW,
    )
    primary_error: BaseException | None = None
    try:
        try:
            root_fd = os.open(root, directory_flags)
        except OSError as error:
            raise _unsafe_open_error((), error) from error
        descriptors.append(root_fd)
        if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
            raise UnsafeAtomicPathError("unsafe repository root is not a directory")
        _posix_after_component_open(())

        for index, component in enumerate(parts[:-1], start=1):
            parent_fd = descriptors[-1]
            relative = parts[:index]
            if create:
                try:
                    os.mkdir(component, mode=0o777, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                except OSError as error:
                    raise _unsafe_open_error(relative, error) from error
            try:
                component_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=parent_fd,
                )
            except FileNotFoundError:
                raise
            except OSError as error:
                raise _unsafe_open_error(relative, error) from error
            descriptors.append(component_fd)
            if not stat.S_ISDIR(os.fstat(component_fd).st_mode):
                raise UnsafeAtomicPathError(
                    f"unsafe non-directory repository path: {'/'.join(relative)}"
                )
            _posix_after_component_open(relative)
            _posix_verify_open_component(
                parent_fd,
                component,
                component_fd,
                relative,
            )
        yield descriptors[-1], parts[-1]
    except BaseException as error:
        primary_error = error
        raise
    finally:
        cleanup_error = _posix_close_descriptors(reversed(descriptors))
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error


def _posix_read_text(
    root: pathlib.Path,
    parts: tuple[str, ...],
    *,
    errors: str,
) -> str:
    with _posix_parent_fd(root, parts, create=False) as (parent_fd, final_name):
        try:
            descriptor = os.open(
                final_name,
                _posix_open_flags(os.O_RDONLY, os.O_NOFOLLOW, os.O_NONBLOCK),
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            raise
        except OSError as error:
            raise _unsafe_open_error(parts, error) from error
        primary_error: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise UnsafeAtomicPathError(
                    f"unsafe non-regular repository file: {'/'.join(parts)}"
                )
            os.set_blocking(descriptor, True)
            with os.fdopen(
                descriptor,
                "r",
                encoding="utf-8",
                errors=errors,
            ) as stream:
                descriptor = -1
                return stream.read()
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if descriptor >= 0:
                cleanup_error = _posix_close_descriptors(iter((descriptor,)))
                if cleanup_error is not None and primary_error is None:
                    raise cleanup_error


def _posix_append_text(
    root: pathlib.Path,
    parts: tuple[str, ...],
    text: str,
) -> None:
    with _posix_parent_fd(root, parts, create=True) as (parent_fd, final_name):
        try:
            descriptor = os.open(
                final_name,
                _posix_open_flags(
                    os.O_APPEND,
                    os.O_CREAT,
                    os.O_WRONLY,
                    os.O_NOFOLLOW,
                    os.O_NONBLOCK,
                ),
                0o666,
                dir_fd=parent_fd,
            )
        except OSError as error:
            raise _unsafe_open_error(parts, error) from error
        primary_error: BaseException | None = None
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise UnsafeAtomicPathError(
                    f"unsafe non-regular repository file: {'/'.join(parts)}"
                )
            os.set_blocking(descriptor, True)
            with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
                descriptor = -1
                stream.write(text)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if descriptor >= 0:
                cleanup_error = _posix_close_descriptors(iter((descriptor,)))
                if cleanup_error is not None and primary_error is None:
                    raise cleanup_error


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("FileAttributes", ctypes.c_uint32),
        ("ReparseTag", ctypes.c_uint32),
    ]


class _WindowsApi:
    """Typed wrappers for the Win32 handle operations used by repository I/O."""

    def __init__(self) -> None:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create_file = kernel32.CreateFileW
        self._create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self._create_file.restype = wintypes.HANDLE

        self._get_file_information = kernel32.GetFileInformationByHandleEx
        self._get_file_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        self._get_file_information.restype = wintypes.BOOL

        self._get_final_path = kernel32.GetFinalPathNameByHandleW
        self._get_final_path.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self._get_final_path.restype = wintypes.DWORD

        self._close_handle = kernel32.CloseHandle
        self._close_handle.argtypes = [wintypes.HANDLE]
        self._close_handle.restype = wintypes.BOOL

        self._create_directory = kernel32.CreateDirectoryW
        self._create_directory.argtypes = [wintypes.LPCWSTR, wintypes.LPVOID]
        self._create_directory.restype = wintypes.BOOL

    def CreateFileW(
        self,
        path: str,
        desired_access: int,
        share_mode: int,
        security_attributes: object | None,
        creation_disposition: int,
        flags_and_attributes: int,
        template_file: object | None,
    ) -> int:
        handle = self._create_file(
            path,
            desired_access,
            share_mode,
            security_attributes,
            creation_disposition,
            flags_and_attributes,
            template_file,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def FileAttributeTagInfo(self, handle: int) -> tuple[int, int]:
        information = _FileAttributeTagInfo()
        if not self._get_file_information(
            handle,
            _FILE_ATTRIBUTE_TAG_INFO_CLASS,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(information.FileAttributes), int(information.ReparseTag)

    def GetFinalPathNameByHandleW(self, handle: int) -> str:
        capacity = 32768
        buffer = ctypes.create_unicode_buffer(capacity)
        length = self._get_final_path(
            handle,
            buffer,
            capacity,
            _VOLUME_NAME_DOS,
        )
        if not length:
            raise ctypes.WinError(ctypes.get_last_error())
        if length >= capacity:
            raise OSError("verified Windows path exceeds supported length")
        return buffer.value

    def CloseHandle(self, handle: int) -> None:
        if not self._close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def CreateDirectoryW(self, path: str) -> None:
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


def _windows_path_is_contained(root: str, candidate: str) -> bool:
    normalized_root = _windows_normal_path(root)
    normalized_candidate = _windows_normal_path(candidate)
    try:
        return ntpath.commonpath([normalized_root, normalized_candidate]) == normalized_root
    except ValueError:
        return False


def _windows_verify_handle(
    api: object,
    handle: int,
    *,
    verified_root: str | None,
    require_directory: bool,
) -> str:
    attributes, reparse_tag = api.FileAttributeTagInfo(handle)
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT or reparse_tag:
        raise UnsafeAtomicPathError("unsafe Windows reparse repository path")
    is_directory = bool(attributes & FILE_ATTRIBUTE_DIRECTORY)
    if is_directory != require_directory:
        kind = "directory" if require_directory else "regular file"
        raise UnsafeAtomicPathError(f"unsafe Windows repository path is not a {kind}")
    final_path = api.GetFinalPathNameByHandleW(handle)
    if verified_root is not None and not _windows_path_is_contained(
        verified_root,
        final_path,
    ):
        raise UnsafeAtomicPathError("unsafe Windows path outside repository")
    return final_path


def _windows_validate_parts(parts: tuple[str, ...]) -> None:
    if not parts:
        raise UnsafeAtomicPathError("unsafe empty repository path")
    for component in parts:
        if (
            not isinstance(component, str)
            or not component
            or component in {".", ".."}
            or "\x00" in component
            or any(0xD800 <= ord(character) <= 0xDFFF for character in component)
            or "/" in component
            or "\\" in component
            or ntpath.isabs(component)
            or bool(ntpath.splitdrive(component)[0])
        ):
            raise UnsafeAtomicPathError(
                f"unsafe Windows repository component: {component!r}"
            )


def _windows_close_handles(api: object, handles: Iterator[int]) -> BaseException | None:
    first_error: BaseException | None = None
    for handle in handles:
        try:
            api.CloseHandle(handle)
        except BaseException as error:
            if first_error is None:
                first_error = error
    return first_error


def _windows_open_verified(
    root: str | pathlib.Path,
    parts: tuple[str, ...],
    *,
    desired_access: int,
    creation_disposition: int,
    create_parents: bool,
    api: object,
) -> int:
    _windows_validate_parts(parts)
    root_text = ntpath.normpath(str(root))
    # Denying delete sharing keeps every opened ancestor from being renamed or
    # replaced while later components are created and verified.
    share_mode = FILE_SHARE_READ | FILE_SHARE_WRITE
    directory_flags = FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT
    directory_handles: list[int] = []
    final_handle: int | None = None
    try:
        verified_root: str | None = None
        for index in range(len(parts)):
            directory_path = ntpath.join(root_text, *parts[:index])
            if index and create_parents:
                create_directory = getattr(api, "CreateDirectoryW", None)
                if create_directory is not None:
                    create_directory(directory_path)
            try:
                handle = api.CreateFileW(
                    directory_path,
                    0,
                    share_mode,
                    None,
                    OPEN_EXISTING,
                    directory_flags,
                    None,
                )
            except FileNotFoundError:
                raise
            except OSError as error:
                raise UnsafeAtomicPathError(
                    f"unsafe Windows repository directory: {directory_path}"
                ) from error
            directory_handles.append(handle)
            final_path = _windows_verify_handle(
                api,
                handle,
                verified_root=verified_root,
                require_directory=True,
            )
            if verified_root is None:
                verified_root = final_path

        final_pathname = ntpath.join(root_text, *parts)
        try:
            final_handle = api.CreateFileW(
                final_pathname,
                desired_access,
                share_mode,
                None,
                creation_disposition,
                FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        except FileNotFoundError:
            raise
        except OSError as error:
            raise UnsafeAtomicPathError(
                f"unsafe Windows repository file: {final_pathname}"
            ) from error
        _windows_verify_handle(
            api,
            final_handle,
            verified_root=verified_root,
            require_directory=False,
        )
    except BaseException:
        cleanup_handles = iter(
            ([final_handle] if final_handle is not None else [])
            + list(reversed(directory_handles))
        )
        _windows_close_handles(api, cleanup_handles)
        raise

    cleanup_error = _windows_close_handles(api, reversed(directory_handles))
    directory_handles.clear()
    if cleanup_error is not None:
        if final_handle is not None:
            _windows_close_handles(api, iter((final_handle,)))
        raise cleanup_error
    assert final_handle is not None
    return final_handle


def _windows_read_text(
    root: pathlib.Path,
    parts: tuple[str, ...],
    *,
    errors: str,
) -> str:
    import msvcrt

    api = _WindowsApi()
    handle = _windows_open_verified(
        root,
        parts,
        desired_access=GENERIC_READ,
        creation_disposition=OPEN_EXISTING,
        create_parents=False,
        api=api,
    )
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        api.CloseHandle(handle)
        raise
    try:
        stream = os.fdopen(descriptor, "r", encoding="utf-8", errors=errors)
    except BaseException:
        _posix_close_descriptors(iter((descriptor,)))
        raise
    with stream:
        return stream.read()


def _windows_append_text(
    root: pathlib.Path,
    parts: tuple[str, ...],
    text: str,
) -> None:
    import msvcrt

    api = _WindowsApi()
    handle = _windows_open_verified(
        root,
        parts,
        desired_access=FILE_APPEND_DATA,
        creation_disposition=OPEN_ALWAYS,
        create_parents=True,
        api=api,
    )
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_APPEND | os.O_WRONLY)
    except BaseException:
        api.CloseHandle(handle)
        raise
    try:
        stream = os.fdopen(descriptor, "a", encoding="utf-8")
    except BaseException:
        _posix_close_descriptors(iter((descriptor,)))
        raise
    with stream:
        stream.write(text)


def atomic_read_text(
    root: pathlib.Path,
    relative: str | pathlib.Path,
    *,
    errors: str = "strict",
) -> str:
    trusted_root, parts = _relative_parts(root, relative)
    if os.name == "posix":
        return _posix_read_text(trusted_root, parts, errors=errors)
    if os.name == "nt":
        return _windows_read_text(trusted_root, parts, errors=errors)
    raise RuntimeError(f"unsupported atomic repository I/O platform: {os.name}")


def atomic_append_text(
    root: pathlib.Path,
    relative: str | pathlib.Path,
    text: str,
) -> None:
    trusted_root, parts = _relative_parts(root, relative)
    if os.name == "posix":
        _posix_append_text(trusted_root, parts, text)
        return
    if os.name == "nt":
        _windows_append_text(trusted_root, parts, text)
        return
    raise RuntimeError(f"unsupported atomic repository I/O platform: {os.name}")
