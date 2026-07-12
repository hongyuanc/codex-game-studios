"""Conservative byte-preserving merges for project-owned shared files."""

from __future__ import annotations

import dataclasses
import hashlib
import re
import tomllib
from collections.abc import Mapping


_MARKER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_OWNED_TYPES: dict[str, type[object]] = {
    "agents.max_depth": int,
    "agents.max_threads": int,
    "features.hooks": bool,
}
_OWNED_ORDER = tuple(_OWNED_TYPES)
_SIMPLE_HEADER = re.compile(r"[ \t]*\[([A-Za-z0-9_-]+)\][ \t]*(?:#.*)?\Z")
_ANY_HEADER = re.compile(r"[ \t]*\[\[?.*\]\]?[ \t]*(?:#.*)?\Z")


class MergeConflict(ValueError):
    """Raised when a shared file cannot be changed without unsafe inference."""


@dataclasses.dataclass(frozen=True)
class BlockResult:
    """Result of adding, updating, or removing one managed block."""

    content: bytes
    block_hash: str
    changed: bool


@dataclasses.dataclass(frozen=True)
class TomlMergeResult:
    """Result of merging the manager-owned TOML values."""

    content: bytes
    owned_values: dict[str, object]
    changed: bool


@dataclasses.dataclass(frozen=True)
class _BlockSpan:
    start: int
    end: int
    content: bytes


def _decode_utf8(content: bytes, *, toml: bool = False) -> str:
    try:
        return content.decode("utf-8", errors="strict")
    except (AttributeError, UnicodeDecodeError) as error:
        message = "unsupported TOML layout" if toml else "shared file must be UTF-8"
        raise MergeConflict(message) from error


def _marker_pair(marker_name: str) -> tuple[str, str]:
    if not isinstance(marker_name, str) or not _MARKER_NAME.fullmatch(marker_name):
        raise MergeConflict("invalid managed marker name")
    return (
        f"<!-- {marker_name}:start -->",
        f"<!-- {marker_name}:end -->",
    )


def _marker_candidate_pattern(marker_name: str) -> re.Pattern[str]:
    """Match opening comment-like manager markers, including truncations."""

    _marker_pair(marker_name)
    return re.compile(
        r"<\s*!?\s*-\s*-\s*"
        + re.escape(marker_name)
        + r"\s*:\s*(?:start|end)\b",
        re.IGNORECASE,
    )


def _line_body(line: str) -> str:
    if line.endswith("\n"):
        line = line[:-1]
        if line.endswith("\r"):
            line = line[:-1]
    return line


def _find_block(content: bytes, marker_name: str, *, required: bool) -> _BlockSpan | None:
    text = _decode_utf8(content)
    start_marker, end_marker = _marker_pair(marker_name)
    candidate_pattern = _marker_candidate_pattern(marker_name)
    lines = text.splitlines(keepends=True)
    if not lines and text:
        lines = [text]

    start_lines = [index for index, line in enumerate(lines) if _line_body(line) == start_marker]
    end_lines = [index for index, line in enumerate(lines) if _line_body(line) == end_marker]
    exact_occurrences = sum(len(candidate_pattern.findall(line)) for line in lines)
    standalone_occurrences = len(start_lines) + len(end_lines)
    malformed = exact_occurrences != standalone_occurrences

    if not start_lines and not end_lines and not malformed:
        if required:
            raise MergeConflict("expected exactly one managed block")
        return None
    if (
        malformed
        or len(start_lines) != 1
        or len(end_lines) != 1
        or start_lines[0] >= end_lines[0]
    ):
        raise MergeConflict("expected exactly one managed block")

    offsets: list[int] = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line.encode("utf-8"))
    start = offsets[start_lines[0]]
    end_index = end_lines[0]
    end = offsets[end_index] + len(lines[end_index].encode("utf-8"))
    return _BlockSpan(start=start, end=end, content=content[start:end])


def _newline_for(content: bytes, fallback: bytes = b"\n") -> bytes:
    first_lf = content.find(b"\n")
    if first_lf >= 0:
        return b"\r\n" if first_lf and content[first_lf - 1] == 13 else b"\n"
    return fallback


def _managed_block(marker_name: str, desired: bytes, newline: bytes) -> bytes:
    desired_text = _decode_utf8(desired)
    start_marker, end_marker = _marker_pair(marker_name)
    if _marker_candidate_pattern(marker_name).search(desired_text):
        raise MergeConflict("expected exactly one managed block")
    if "\r" in desired_text.replace("\r\n", ""):
        raise MergeConflict("managed content must use LF or CRLF newlines")
    normalized = desired_text.replace("\r\n", "\n").rstrip("\n")
    body = normalized.encode("utf-8").replace(b"\n", newline)
    parts = [start_marker.encode("utf-8"), newline]
    if body:
        parts.extend((body, newline))
    parts.extend((end_marker.encode("utf-8"), newline))
    return b"".join(parts)


def _preceding_newline(content: bytes, offset: int) -> bytes:
    if content[:offset].endswith(b"\r\n"):
        return b"\r\n"
    if content[:offset].endswith(b"\n"):
        return b"\n"
    return b""


def merge_block(
    existing: bytes,
    marker_name: str,
    desired: bytes,
    *,
    recorded_hash: str | None = None,
) -> BlockResult:
    """Append or replace one block, preserving recorded separator ownership."""

    _decode_utf8(existing)
    if recorded_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", recorded_hash):
        raise MergeConflict("recorded block hash is invalid")
    span = _find_block(existing, marker_name, required=False)
    if span is not None:
        ownership_prefix = b""
        if recorded_hash is not None:
            block_hash = hashlib.sha256(span.content).hexdigest()
            preceding_newline = _preceding_newline(existing, span.start)
            prefixed_hash = (
                hashlib.sha256(preceding_newline + span.content).hexdigest()
                if preceding_newline
                else None
            )
            if recorded_hash == block_hash:
                ownership_prefix = b""
            elif recorded_hash == prefixed_hash:
                ownership_prefix = preceding_newline
            else:
                raise MergeConflict("managed block differs from recorded block hash")
        newline = _newline_for(span.content, _newline_for(existing))
        block = _managed_block(marker_name, desired, newline)
        content = existing[: span.start] + block + existing[span.end :]
    else:
        if recorded_hash is not None:
            raise MergeConflict("expected exactly one managed block for recorded block hash")
        newline = _newline_for(existing, _newline_for(desired))
        block = _managed_block(marker_name, desired, newline)
        separator = b"" if not existing or existing.endswith(b"\n") else newline
        ownership_prefix = separator
        content = existing + separator + block
    owned_block = ownership_prefix + block
    return BlockResult(
        content=content,
        block_hash=hashlib.sha256(owned_block).hexdigest(),
        changed=content != existing,
    )


def remove_block(existing: bytes, marker_name: str, recorded_hash: str) -> BlockResult:
    """Remove a managed block only when its exact bytes retain recorded ownership."""

    if not isinstance(recorded_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", recorded_hash):
        raise MergeConflict("recorded block hash is invalid")
    span = _find_block(existing, marker_name, required=True)
    assert span is not None
    removal_start = span.start
    if hashlib.sha256(span.content).hexdigest() != recorded_hash:
        prefix = _preceding_newline(existing, span.start)
        owned_content = prefix + span.content
        if not prefix or hashlib.sha256(owned_content).hexdigest() != recorded_hash:
            raise MergeConflict("managed block differs from recorded block hash")
        removal_start -= len(prefix)
    content = existing[:removal_start] + existing[span.end :]
    return BlockResult(content=content, block_hash="", changed=True)


def _validate_owned_values(values: Mapping[str, object], *, recorded: bool) -> dict[str, object]:
    if not isinstance(values, Mapping):
        raise MergeConflict("unsupported TOML layout")
    validated: dict[str, object] = {}
    for key, value in values.items():
        expected_type = _OWNED_TYPES.get(key)
        if expected_type is None or type(value) is not expected_type:
            raise MergeConflict("unsupported TOML layout")
        validated[key] = value
    if recorded and not set(validated).issubset(_OWNED_TYPES):
        raise MergeConflict("unsupported TOML layout")
    return validated


def _reject_multiline_toml_strings(text: str) -> None:
    """Fail closed on multiline strings without mistaking quoted/comment text."""

    state = "normal"
    index = 0
    while index < len(text):
        character = text[index]
        if state == "comment":
            if character == "\n":
                state = "normal"
            index += 1
            continue
        if state == "basic":
            if character == "\\":
                index += 2
                continue
            if character == '"':
                state = "normal"
            index += 1
            continue
        if state == "literal":
            if character == "'":
                state = "normal"
            index += 1
            continue
        if character == "#":
            state = "comment"
            index += 1
            continue
        if text.startswith(('"""', "'''"), index):
            raise MergeConflict("unsupported TOML layout")
        if character == '"':
            state = "basic"
        elif character == "'":
            state = "literal"
        index += 1


def _lookup_owned(document: dict[str, object], dotted_key: str) -> tuple[bool, object | None]:
    table_name, key_name = dotted_key.split(".", 1)
    table = document.get(table_name)
    if table is None:
        return False, None
    if not isinstance(table, dict):
        raise MergeConflict("unsupported TOML layout")
    if key_name not in table:
        return False, None
    return True, table[key_name]


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _assignment_pattern(dotted_key: str, *, dotted: bool) -> re.Pattern[str]:
    table_name, key_name = dotted_key.split(".", 1)
    name = rf"{re.escape(table_name)}[ \t]*\.[ \t]*{re.escape(key_name)}" if dotted else re.escape(key_name)
    if _OWNED_TYPES[dotted_key] is bool:
        value = r"true|false"
    else:
        value = r"[+-]?[0-9](?:_?[0-9])*"
    return re.compile(
        rf"(?P<prefix>[ \t]*{name}[ \t]*=[ \t]*)(?P<value>{value})(?P<suffix>[ \t]*(?:#.*)?)\Z"
    )


def _find_assignment(lines: list[str], dotted_key: str) -> tuple[int, re.Match[str]] | None:
    table_name, _ = dotted_key.split(".", 1)
    current_table: str | None = None
    matches: list[tuple[int, re.Match[str]]] = []
    plain_pattern = _assignment_pattern(dotted_key, dotted=False)
    dotted_pattern = _assignment_pattern(dotted_key, dotted=True)
    for index, line in enumerate(lines):
        body, _ending = _split_line_ending(line)
        header = _SIMPLE_HEADER.fullmatch(body)
        if header:
            current_table = header.group(1)
            continue
        if _ANY_HEADER.fullmatch(body):
            current_table = None
            continue
        match = plain_pattern.fullmatch(body) if current_table == table_name else None
        if current_table is None:
            match = match or dotted_pattern.fullmatch(body)
        if match:
            matches.append((index, match))
    if len(matches) > 1:
        raise MergeConflict("unsupported TOML layout")
    return matches[0] if matches else None


def _render_value(value: object) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


def _first_newline(text: str) -> str:
    match = re.search(r"\r\n|\n", text)
    return match.group(0) if match else "\n"


def _insert_assignment(text: str, dotted_key: str, value: object) -> str:
    lines = text.splitlines(keepends=True)
    table_name, key_name = dotted_key.split(".", 1)
    newline = _first_newline(text)
    header_indexes: list[int] = []
    for index, line in enumerate(lines):
        body, _ending = _split_line_ending(line)
        header = _SIMPLE_HEADER.fullmatch(body)
        if header and header.group(1) == table_name:
            header_indexes.append(index)
    if len(header_indexes) > 1:
        raise MergeConflict("unsupported TOML layout")

    assignment = f"{key_name} = {_render_value(value)}{newline}"
    if header_indexes:
        insertion = len(lines)
        for index in range(header_indexes[0] + 1, len(lines)):
            body, _ending = _split_line_ending(lines[index])
            if _ANY_HEADER.fullmatch(body):
                insertion = index
                break
        if insertion and not lines[insertion - 1].endswith("\n"):
            lines[insertion - 1] += newline
        lines.insert(insertion, assignment)
        return "".join(lines)

    try:
        document = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, TypeError) as error:
        raise MergeConflict("unsupported TOML layout") from error
    if table_name in document:
        raise MergeConflict("unsupported TOML layout")
    separator = "" if not text or text.endswith("\n") else newline
    return text + separator + f"[{table_name}]{newline}" + assignment


def _replace_assignment(text: str, dotted_key: str, value: object) -> str:
    lines = text.splitlines(keepends=True)
    located = _find_assignment(lines, dotted_key)
    if located is None:
        raise MergeConflict("unsupported TOML layout")
    index, match = located
    _body, ending = _split_line_ending(lines[index])
    lines[index] = (
        match.group("prefix")
        + _render_value(value)
        + match.group("suffix")
        + ending
    )
    return "".join(lines)


def merge_owned_toml(
    existing: bytes,
    desired_values: Mapping[str, object],
    recorded_values: Mapping[str, object],
) -> TomlMergeResult:
    """Merge approved owned keys without serializing or reformatting unrelated TOML."""

    text = _decode_utf8(existing, toml=True)
    _reject_multiline_toml_strings(text)
    desired = _validate_owned_values(desired_values, recorded=False)
    recorded = _validate_owned_values(recorded_values, recorded=True)
    if not set(recorded).issubset(desired):
        raise MergeConflict("unsupported TOML layout")
    try:
        document = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, TypeError) as error:
        raise MergeConflict("unsupported TOML layout") from error

    actions: dict[str, str] = {}
    for dotted_key in _OWNED_ORDER:
        if dotted_key not in desired:
            continue
        exists, current = _lookup_owned(document, dotted_key)
        if exists and type(current) is not _OWNED_TYPES[dotted_key]:
            raise MergeConflict("unsupported TOML layout")
        located = _find_assignment(text.splitlines(keepends=True), dotted_key)
        if exists and located is None:
            raise MergeConflict("unsupported TOML layout")
        if dotted_key in recorded:
            if not exists or current != recorded[dotted_key]:
                raise MergeConflict(f"conflicting owned key: {dotted_key}")
            actions[dotted_key] = "keep" if current == desired[dotted_key] else "replace"
        elif exists:
            if current != desired[dotted_key]:
                raise MergeConflict(f"conflicting owned key: {dotted_key}")
            actions[dotted_key] = "keep"
        else:
            actions[dotted_key] = "insert"

    merged = text
    for dotted_key in _OWNED_ORDER:
        action = actions.get(dotted_key)
        if action == "replace":
            merged = _replace_assignment(merged, dotted_key, desired[dotted_key])
        elif action == "insert":
            merged = _insert_assignment(merged, dotted_key, desired[dotted_key])

    content = merged.encode("utf-8")
    try:
        merged_document = tomllib.loads(merged)
    except (tomllib.TOMLDecodeError, TypeError) as error:
        raise MergeConflict("unsupported TOML layout") from error
    for dotted_key, expected in desired.items():
        exists, actual = _lookup_owned(merged_document, dotted_key)
        if (
            not exists
            or type(actual) is not _OWNED_TYPES[dotted_key]
            or actual != expected
        ):
            raise MergeConflict("unsupported TOML layout")
    return TomlMergeResult(
        content=content,
        owned_values=dict(desired),
        changed=content != existing,
    )
