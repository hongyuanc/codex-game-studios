"""Canonical payload models and cross-platform path safety helpers."""

from __future__ import annotations

import dataclasses
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


def canonical_json(value: object) -> bytes:
    """Encode a value as newline-terminated canonical UTF-8 JSON."""

    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


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
        if any(character in '<>:"|?*' for character in part) or part.endswith((" ", ".")):
            raise PayloadError("unsafe payload path for Windows")
        if part.split(".", 1)[0].upper() in windows_reserved:
            raise PayloadError("unsafe payload path for Windows")
    return raw
