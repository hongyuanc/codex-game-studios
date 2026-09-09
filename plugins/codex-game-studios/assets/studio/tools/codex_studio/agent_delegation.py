"""Fail-closed plugin-local role resolution and delegation route contracts."""

from __future__ import annotations

import argparse
import dataclasses
import json
import ntpath
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import sys
import tomllib
from typing import Collection, Mapping


if __package__ in {None, ""}:
    _BUNDLED_STUDIO_ROOT = Path(__file__).absolute().parents[2]
    sys.path.insert(0, str(_BUNDLED_STUDIO_ROOT))

from tools.codex_studio.engine_pack import SUPPORTED_ENGINES, load_studio_config


ROLE_FIELDS = frozenset(
    {"name", "description", "developer_instructions", "model", "model_reasoning_effort"}
)
ALLOWED_MODELS = frozenset({"gpt-6-astra", "gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"})
ALLOWED_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh"})
CORE_ROLE_NAMES = frozenset(
    """accessibility-specialist ai-programmer analytics-engineer art-director
audio-director community-manager creative-director devops-engineer economy-designer
engine-programmer game-designer gameplay-programmer lead-programmer level-designer
live-ops-designer localization-lead narrative-director network-programmer
performance-analyst producer prototyper qa-lead qa-tester release-manager
security-engineer sound-designer systems-designer technical-artist technical-director
tools-programmer ui-programmer ux-designer world-builder writer""".split()
)
ENGINE_ROLE_NAMES: Mapping[str, frozenset[str]] = {
    "godot": frozenset(
        """godot-csharp-specialist godot-gdextension-specialist
godot-gdscript-specialist godot-shader-specialist godot-specialist""".split()
    ),
    "unity": frozenset(
        """unity-addressables-specialist unity-dots-specialist
unity-shader-specialist unity-specialist unity-ui-specialist""".split()
    ),
    "unreal": frozenset(
        """ue-blueprint-specialist ue-gas-specialist ue-replication-specialist
ue-umg-specialist unreal-specialist""".split()
    ),
}
DELEGATING_SKILL_NAMES = frozenset(
    """architecture-decision architecture-review art-bible asset-spec brainstorm
bug-report bug-triage changelog code-review create-architecture
create-control-manifest create-epics create-stories day-one-patch design-review
design-system dev-story estimate gate-check hotfix launch-checklist localize
map-systems milestone-review onboard patch-notes playtest-report
propagate-design-change prototype qa-plan regression-suite release-checklist
retrospective reverse-document review-all-gdds security-audit skill-improve
skill-test smoke-check soak-test sprint-plan sprint-status story-done
story-readiness team-audio team-combat team-level team-live-ops team-narrative
team-polish team-qa team-release team-ui test-evidence-review test-flakiness
test-helpers test-setup ux-design vertical-slice""".split()
)

DELEGATION_MARKER = "<!-- codex-studio-delegation: governed -->"
DELEGATION_PREFLIGHT = (
    "Resolve every role through `../../../.codex/docs/plugin-agent-delegation.md`;\n"
    "do not require a repository-local `.codex/agents/` or `.codex/agent-packs/` tree."
)
DELEGATION_RESOLVER_INVOCATION = (
    "Before default delegation, run `python3 "
    "../../../tools/codex_studio/agent_delegation.py resolve --project-root "
    "<project-root> --role <role>` and use only its returned role contract."
)
_SAFE_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_POSIX_DIR_FD_SUPPORTED = (
    os.open in getattr(os, "supports_dir_fd", set())
    and os.stat in getattr(os, "supports_dir_fd", set())
    and os.stat in getattr(os, "supports_follow_symlinks", set())
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
_DELEGATION_INSTRUCTIONS = (
    re.compile(r"(?i)\buse\s+codex\s+custom[- ]agents?\b"),
    re.compile(r"(?i)\bdelegat(?:e|es|ed|ing)\b"),
    re.compile(
        r"(?i)(?:\bspawn(?:s|ed|ing)?\b.{0,100}\b(?:agent|specialist|director|role)s?\b|"
        r"\b(?:agent|specialist|director|role)s?\b.{0,100}\bspawn(?:s|ed|ing)?\b)"
    ),
    re.compile(
        r"(?i)\b(?:use|invoke|route|target|issue|start|launch|delegate|spawn)\b.{0,100}"
        r"\bcustom[- ]agents?\b"
    ),
)


@dataclasses.dataclass(frozen=True)
class RoleContract:
    """Strict plugin-local role contract returned by the resolver."""

    name: str
    description: str
    developer_instructions: str
    model: str
    model_reasoning_effort: str
    source_kind: str
    path: Path


@dataclasses.dataclass(frozen=True)
class BoundedTask:
    """Complete direct-child ownership envelope for default delegation."""

    objective: str
    owned_paths: tuple[str, ...]
    inputs: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    required_evidence: tuple[str, ...]
    prohibited_actions: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class RouteDecision:
    """Closed delegation route decision."""

    route: str
    status: str
    evidence_label: str | None


class ModelApprovalRequired(ValueError):
    """Raised when configured model settings require explicit fallback approval."""


def _without_frontmatter(text: str) -> str:
    if text.startswith("---\n") and "\n---\n" in text[4:]:
        return text.split("\n---\n", 1)[1]
    return text


def _without_fenced_blocks(text: str) -> str:
    """Remove Markdown examples without treating a closing fence as a new opener."""

    kept: list[str] = []
    opening_character: str | None = None
    opening_length = 0
    for line in text.splitlines(keepends=True):
        match = _FENCE_LINE.match(line.rstrip("\r\n"))
        if opening_character is None:
            if match:
                opening_character = match.group(1)[0]
                opening_length = len(match.group(1))
            else:
                kept.append(line)
            continue
        if (
            match
            and match.group(1)[0] == opening_character
            and len(match.group(1)) >= opening_length
            and not match.group(2).strip()
        ):
            opening_character = None
            opening_length = 0
    return "".join(kept)


def contains_delegation_instruction(text: str) -> bool:
    """Return whether executable prose contains an actual delegation instruction."""

    scan = _without_frontmatter(text)
    for governed_literal in (
        DELEGATION_MARKER,
        DELEGATION_PREFLIGHT,
        DELEGATION_RESOLVER_INVOCATION,
    ):
        scan = scan.replace(governed_literal, "")
    scan = _without_fenced_blocks(scan)
    scan = _HTML_COMMENT.sub("", scan)
    return any(pattern.search(scan) for pattern in _DELEGATION_INSTRUCTIONS)


def validate_delegation_skill(name: str, text: str) -> tuple[str, ...]:
    """Validate marker, preflight, resolver, and semantic inventory agreement."""

    governed = name in DELEGATING_SKILL_NAMES
    actual_instruction = contains_delegation_instruction(text)
    counts = {
        "delegation marker": text.count(DELEGATION_MARKER),
        "delegation preflight": text.count(DELEGATION_PREFLIGHT),
        "delegation resolver invocation": text.count(DELEGATION_RESOLVER_INVOCATION),
    }
    issues: list[str] = []
    if governed:
        for label, count in counts.items():
            if count != 1:
                issues.append(f"governed skill requires exactly one {label}; found {count}")
        if not actual_instruction:
            issues.append("governed skill has no delegation instruction")
    else:
        for label, count in counts.items():
            if count:
                issues.append(f"ungoverned skill must not contain {label}; found {count}")
        if actual_instruction:
            issues.append("ungoverned delegation instruction")
    return tuple(issues)


def _link_kind(metadata: os.stat_result) -> str | None:
    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    reparse_tag = int(getattr(metadata, "st_reparse_tag", 0) or 0)
    if attributes & reparse_flag or reparse_tag:
        return "reparse point"
    return None


def _safe_metadata(path: Path, label: str, *, missing_ok: bool = False) -> os.stat_result | None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ValueError(f"{label} is missing: {path}") from None
    kind = _link_kind(metadata)
    if kind:
        raise ValueError(f"{label} is an unsafe {kind}: {path}")
    return metadata


def _same_posix_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        stat.S_IFMT(left.st_mode),
    ) == (
        right.st_dev,
        right.st_ino,
        stat.S_IFMT(right.st_mode),
    )


def _posix_file_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _is_windows() -> bool:
    return os.name == "nt"


def _windows_api_factory():
    # The validator ships beside this resolver and owns the native, tested
    # handle API used by installed validation. Import lazily to avoid its
    # validator-to-resolver inventory import during module initialization.
    from tools.codex_studio.validate import _NativeWindowsApi

    return _NativeWindowsApi()


def _windows_normal(path: str) -> str:
    if path.startswith("\\\\?\\UNC\\"):
        path = "\\\\" + path[8:]
    elif path.startswith("\\\\?\\"):
        path = path[4:]
    return ntpath.normcase(ntpath.normpath(path))


def _windows_info_signature(metadata: object) -> tuple[object, ...]:
    return (
        metadata.identity,
        metadata.kind,
        metadata.reparse,
        metadata.disk,
        metadata.size,
        metadata.write_time,
    )


@dataclasses.dataclass
class _PosixObservation:
    parts: tuple[str, ...]
    descriptors: tuple[int, ...]
    metadata: tuple[os.stat_result, ...]
    missing: bool


@dataclasses.dataclass
class _WindowsObservation:
    parts: tuple[str, ...]
    handles: tuple[int, ...]
    metadata: tuple[object, ...]
    canonical_paths: tuple[str, ...]
    missing: bool


class _PinnedBundle:
    """One retained plugin-root authority for inventory checks and role reads."""

    def __init__(self, root: Path):
        self.root = Path(root) if _is_windows() else Path(root).absolute()
        self._root_descriptor: int | None = None
        self._root_metadata: os.stat_result | None = None
        self._posix_observations: list[_PosixObservation] = []
        self._windows_api = None
        self._windows_root_handle: int | None = None
        self._windows_root_metadata = None
        self._windows_root_canonical: str | None = None
        self._windows_root_text: str | None = None
        self._windows_observations: list[_WindowsObservation] = []

    def __enter__(self) -> "_PinnedBundle":
        if _is_windows():
            self._enter_windows()
        else:
            self._enter_posix()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if exc_type is None:
                self.verify()
        finally:
            self._close()

    @staticmethod
    def _parts(relative: Path) -> tuple[str, ...]:
        text = relative.as_posix()
        pure = PurePosixPath(text)
        if pure.is_absolute() or not pure.parts or any(
            part in {"", ".", ".."} for part in pure.parts
        ):
            raise ValueError("role path escapes plugin bundle")
        return pure.parts

    def _enter_posix(self) -> None:
        nofollow = int(getattr(os, "O_NOFOLLOW", 0))
        directory = int(getattr(os, "O_DIRECTORY", 0))
        if (
            not nofollow
            or not directory
            or not _POSIX_DIR_FD_SUPPORTED
        ):
            raise ValueError("platform lacks secure descriptor-relative role resolution")
        expected = _safe_metadata(self.root, "plugin bundle root")
        assert expected is not None
        if not stat.S_ISDIR(expected.st_mode):
            raise ValueError(f"plugin bundle root is not a directory: {self.root}")
        flags = os.O_RDONLY | directory | nofollow | int(getattr(os, "O_CLOEXEC", 0))
        try:
            descriptor = os.open(self.root, flags)
        except OSError as error:
            raise ValueError(f"cannot pin plugin bundle root: {error}") from error
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode) or not _same_posix_identity(expected, opened):
            os.close(descriptor)
            raise ValueError("plugin bundle root identity changed while pinning")
        self._root_descriptor = descriptor
        self._root_metadata = opened

    def _enter_windows(self) -> None:
        api = _windows_api_factory()
        self._windows_api = api
        self._windows_root_text = ntpath.normpath(str(self.root))
        try:
            handle, metadata, canonical = self._open_windows_component(
                self._windows_root_text,
                expected_parent=None,
                directory=True,
            )
        except OSError as error:
            raise ValueError(f"cannot pin plugin bundle root: {error}") from error
        self._windows_root_handle = handle
        self._windows_root_metadata = metadata
        self._windows_root_canonical = canonical

    def _open_windows_component(
        self,
        path: str,
        *,
        expected_parent: str | None,
        directory: bool,
    ) -> tuple[int, object, str]:
        api = self._windows_api
        assert api is not None
        flags = api.FILE_FLAG_OPEN_REPARSE_POINT
        if directory:
            flags |= api.FILE_FLAG_BACKUP_SEMANTICS
        handle = api.open(path, flags=flags, share=api.FILE_SHARE_READ)
        try:
            metadata = api.info(handle)
            if metadata.reparse or not metadata.disk:
                raise ValueError(f"unsafe link, reparse point, or special role path: {path}")
            expected_kind = "directory" if directory else "file"
            if metadata.kind != expected_kind:
                raise ValueError(f"role path component has wrong type: {path}")
            canonical = _windows_normal(api.final_path(handle))
            if expected_parent is not None and _windows_normal(
                str(PureWindowsPath(canonical).parent)
            ) != _windows_normal(expected_parent):
                raise ValueError("plugin bundle ancestor identity changed or escaped")
            return handle, metadata, canonical
        except BaseException:
            api.close(handle)
            raise

    def read_optional(self, relative: Path) -> bytes | None:
        parts = self._parts(relative)
        try:
            if _is_windows():
                return self._read_windows(parts)
            return self._read_posix(parts)
        except ValueError:
            raise
        except OSError as error:
            raise ValueError(f"cannot securely resolve role contract: {error}") from error

    def _read_posix(self, parts: tuple[str, ...]) -> bytes | None:
        assert self._root_descriptor is not None
        nofollow = int(getattr(os, "O_NOFOLLOW", 0))
        directory_flag = int(getattr(os, "O_DIRECTORY", 0))
        base_flags = (
            os.O_RDONLY
            | nofollow
            | int(getattr(os, "O_CLOEXEC", 0))
            | int(getattr(os, "O_NONBLOCK", 0))
            | int(getattr(os, "O_BINARY", 0))
        )
        descriptors = [os.dup(self._root_descriptor)]
        metadata: list[os.stat_result] = []
        try:
            for index, part in enumerate(parts):
                final = index == len(parts) - 1
                parent = descriptors[-1]
                try:
                    before = os.stat(part, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    if final:
                        self._posix_observations.append(
                            _PosixObservation(parts, tuple(descriptors), tuple(metadata), True)
                        )
                        return None
                    raise
                if _link_kind(before):
                    raise ValueError(f"unsafe link or reparse point in role path: {part}")
                expected_directory = not final
                if expected_directory and not stat.S_ISDIR(before.st_mode):
                    raise ValueError(f"role path ancestor is not a directory: {part}")
                if final and not stat.S_ISREG(before.st_mode):
                    raise ValueError(f"role contract is not a regular TOML file: {part}")
                flags = base_flags | (directory_flag if expected_directory else 0)
                child = os.open(part, flags, dir_fd=parent)
                opened = os.fstat(child)
                current = os.stat(part, dir_fd=parent, follow_symlinks=False)
                if (
                    _link_kind(opened)
                    or not _same_posix_identity(before, opened)
                    or not _same_posix_identity(opened, current)
                ):
                    os.close(child)
                    raise ValueError("plugin bundle ancestor or role identity changed while opening")
                descriptors.append(child)
                metadata.append(opened)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptors[-1], 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            if _posix_file_signature(metadata[-1]) != _posix_file_signature(
                os.fstat(descriptors[-1])
            ):
                raise ValueError("role file identity changed during secure read")
            self._posix_observations.append(
                _PosixObservation(parts, tuple(descriptors), tuple(metadata), False)
            )
            return b"".join(chunks)
        except BaseException:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            raise

    def _read_windows(self, parts: tuple[str, ...]) -> bytes | None:
        api = self._windows_api
        assert api is not None
        assert self._windows_root_text is not None
        assert self._windows_root_canonical is not None
        handles: list[int] = []
        metadata: list[object] = []
        canonical_paths: list[str] = []
        parent = self._windows_root_canonical
        try:
            for index, part in enumerate(parts):
                final = index == len(parts) - 1
                path = ntpath.join(self._windows_root_text, *parts[: index + 1])
                try:
                    handle, info, canonical = self._open_windows_component(
                        path,
                        expected_parent=parent,
                        directory=not final,
                    )
                except FileNotFoundError:
                    if final:
                        self._windows_observations.append(
                            _WindowsObservation(
                                parts,
                                tuple(handles),
                                tuple(metadata),
                                tuple(canonical_paths),
                                True,
                            )
                        )
                        return None
                    raise
                handles.append(handle)
                metadata.append(info)
                canonical_paths.append(canonical)
                parent = canonical
            raw = api.read(handles[-1])
            if _windows_info_signature(metadata[-1]) != _windows_info_signature(
                api.info(handles[-1])
            ):
                raise ValueError("role file identity changed during secure read")
            self._windows_observations.append(
                _WindowsObservation(
                    parts,
                    tuple(handles),
                    tuple(metadata),
                    tuple(canonical_paths),
                    False,
                )
            )
            return raw
        except BaseException:
            for handle in reversed(handles):
                api.close(handle)
            raise

    def verify(self) -> None:
        if _is_windows():
            self._verify_windows()
        else:
            self._verify_posix()

    def _verify_posix(self) -> None:
        assert self._root_descriptor is not None
        assert self._root_metadata is not None
        for observation in self._posix_observations:
            for index, expected in enumerate(observation.metadata):
                current = os.stat(
                    observation.parts[index],
                    dir_fd=observation.descriptors[index],
                    follow_symlinks=False,
                )
                if _link_kind(current) or not _same_posix_identity(expected, current):
                    raise ValueError("plugin bundle ancestor or role identity changed after read")
            if observation.missing:
                try:
                    os.stat(
                        observation.parts[-1],
                        dir_fd=observation.descriptors[-1],
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("ambiguous role candidate appeared during resolution")
            elif _posix_file_signature(observation.metadata[-1]) != _posix_file_signature(
                os.fstat(observation.descriptors[-1])
            ):
                raise ValueError("role file identity changed after read")
        current_root = _safe_metadata(self.root, "plugin bundle root")
        assert current_root is not None
        opened_root = os.fstat(self._root_descriptor)
        if (
            not _same_posix_identity(self._root_metadata, opened_root)
            or not _same_posix_identity(opened_root, current_root)
        ):
            raise ValueError("plugin bundle root identity changed during resolution")

    def _verify_windows(self) -> None:
        api = self._windows_api
        assert api is not None
        assert self._windows_root_handle is not None
        assert self._windows_root_metadata is not None
        assert self._windows_root_canonical is not None
        assert self._windows_root_text is not None
        for observation in self._windows_observations:
            parent = self._windows_root_canonical
            for index, part in enumerate(observation.parts):
                final = index == len(observation.parts) - 1
                if final and observation.missing:
                    path = ntpath.join(
                        self._windows_root_text, *observation.parts[: index + 1]
                    )
                    try:
                        fresh, _, _ = self._open_windows_component(
                            path, expected_parent=parent, directory=False
                        )
                    except FileNotFoundError:
                        break
                    else:
                        api.close(fresh)
                        raise ValueError("ambiguous role candidate appeared during resolution")
                path = ntpath.join(
                    self._windows_root_text, *observation.parts[: index + 1]
                )
                fresh, fresh_info, fresh_canonical = self._open_windows_component(
                    path, expected_parent=parent, directory=not final
                )
                try:
                    expected = observation.metadata[index]
                    if (
                        fresh_info.identity != expected.identity
                        or fresh_canonical != observation.canonical_paths[index]
                    ):
                        raise ValueError("plugin bundle ancestor or role identity changed after read")
                    retained = api.info(observation.handles[index])
                    if _windows_info_signature(retained) != _windows_info_signature(expected):
                        raise ValueError("plugin bundle ancestor or role identity changed after read")
                finally:
                    api.close(fresh)
                parent = fresh_canonical
        fresh_root, fresh_info, fresh_canonical = self._open_windows_component(
            self._windows_root_text, expected_parent=None, directory=True
        )
        try:
            retained_root = api.info(self._windows_root_handle)
            if (
                fresh_info.identity != self._windows_root_metadata.identity
                or _windows_info_signature(retained_root)
                != _windows_info_signature(self._windows_root_metadata)
                or fresh_canonical != self._windows_root_canonical
            ):
                raise ValueError("plugin bundle root identity changed during resolution")
        finally:
            api.close(fresh_root)

    def _close(self) -> None:
        if self._windows_api is not None:
            for observation in reversed(self._windows_observations):
                for handle in reversed(observation.handles):
                    self._windows_api.close(handle)
            if self._windows_root_handle is not None:
                self._windows_api.close(self._windows_root_handle)
            return
        for observation in reversed(self._posix_observations):
            for descriptor in reversed(observation.descriptors):
                os.close(descriptor)
        if self._root_descriptor is not None:
            os.close(self._root_descriptor)


def _parse_contract(raw: bytes, path: Path, role: str, source_kind: str) -> RoleContract:
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"invalid role TOML: {error}") from error
    if set(data) != set(ROLE_FIELDS) or any(not isinstance(data.get(key), str) for key in ROLE_FIELDS):
        raise ValueError(f"role contract fields must be exactly {sorted(ROLE_FIELDS)} strings")
    if data["name"] != role:
        raise ValueError("role contract name does not match requested role")
    for field in ("name", "description", "developer_instructions", "model", "model_reasoning_effort"):
        if not data[field] or data[field] != data[field].strip():
            raise ValueError(f"role contract field {field} must be non-empty and trimmed")
    if data["model"] not in ALLOWED_MODELS:
        raise ValueError(f"role contract uses unknown configured model: {data['model']}")
    if data["model_reasoning_effort"] not in ALLOWED_REASONING_EFFORTS:
        raise ValueError(
            "role contract uses unknown configured reasoning effort: "
            f"{data['model_reasoning_effort']}"
        )
    return RoleContract(
        **{field: data[field] for field in ROLE_FIELDS},
        source_kind=source_kind,
        path=path,
    )


def resolve_role(bundle_root: Path, project_root: Path, role: str) -> RoleContract:
    """Resolve one declared role beneath the plugin bundle and selected engine pack."""

    if not isinstance(role, str) or _SAFE_SLUG.fullmatch(role) is None:
        raise ValueError("requested role must be a safe role slug")
    config = load_studio_config(Path(project_root))
    active_pack = config.active_engine_pack
    if active_pack not in (*SUPPORTED_ENGINES, "none"):
        raise ValueError(f"unsupported active engine pack: {active_pack}")

    core_member = role in CORE_ROLE_NAMES
    owning_packs = tuple(
        engine for engine, names in ENGINE_ROLE_NAMES.items() if role in names
    )
    if core_member and owning_packs:
        raise ValueError(f"ambiguous declared role inventory: {role}")
    if not core_member and not owning_packs:
        raise ValueError(f"unknown role: {role}")
    if owning_packs and active_pack not in owning_packs:
        raise ValueError(
            f"role belongs to inactive engine pack: {role}; active={active_pack}"
        )

    core_relative = Path(".codex/agents") / f"{role}.toml"
    active_relative = (
        Path(".codex/agent-packs") / active_pack / f"{role}.toml"
        if active_pack != "none"
        else None
    )
    with _PinnedBundle(bundle_root) as bundle:
        core_raw = bundle.read_optional(core_relative)
        active_raw = (
            bundle.read_optional(active_relative)
            if active_relative is not None
            else None
        )
        if core_raw is not None and active_raw is not None:
            raise ValueError(
                f"ambiguous role contract exists in core and active pack: {role}"
            )
        if core_member:
            relative = core_relative
            source_kind = "core"
            raw = core_raw
        else:
            assert active_relative is not None
            relative = active_relative
            source_kind = active_pack
            raw = active_raw
        if raw is None:
            raise ValueError(f"role contract is missing: {bundle.root / relative}")
        return _parse_contract(raw, bundle.root / relative, role, source_kind)


def decide_route(
    *, native_result: str, default_result: str, model_supported: bool
) -> RouteDecision:
    """Apply the closed native/default/single-agent route state machine."""

    native_states = {"success", "blocked", "absent", "unavailable"}
    default_states = {"success", "blocked", "absent", "unavailable", "not-attempted"}
    if native_result not in native_states or default_result not in default_states:
        raise ValueError("invalid delegation route state")
    if native_result in {"success", "blocked"}:
        if default_result != "not-attempted":
            raise ValueError("impossible route state: default ran after completed native route")
        return RouteDecision(
            "native", "SUCCESS" if native_result == "success" else "BLOCKED", None
        )
    if default_result in {"absent", "unavailable"}:
        return RouteDecision("single-agent", "FALLBACK", "single-agent fallback")
    if default_result in {"success", "blocked"}:
        if not model_supported:
            raise ValueError(
                "impossible route state: default completed with unsupported model"
            )
        return RouteDecision(
            "default", "SUCCESS" if default_result == "success" else "BLOCKED", None
        )
    if not model_supported:
        return RouteDecision("approval-required", "BLOCKED", None)
    raise ValueError("impossible route state: usable default route was not attempted")


def _list_block(values: tuple[str, ...]) -> str:
    return "\n".join(f"- {value}" for value in values) if values else "- none"


def build_default_agent_request(
    contract: RoleContract,
    task: BoundedTask,
    *,
    supported_models: Collection[str],
    supported_reasoning_efforts: Collection[str],
) -> dict[str, str]:
    """Build the exact default-agent parameters and complete bounded prompt."""

    if contract.model not in supported_models:
        raise ModelApprovalRequired(
            f"configured model is unavailable; explicit approval is required: {contract.model}"
        )
    if contract.model_reasoning_effort not in supported_reasoning_efforts:
        raise ModelApprovalRequired(
            "configured reasoning effort is unavailable; explicit approval is required: "
            f"{contract.model_reasoning_effort}"
        )
    if not task.objective.strip() or not task.acceptance_criteria or not task.required_evidence:
        raise ValueError("bounded direct-child task requires objective, acceptance criteria, and evidence")
    message = f"""You are a direct child. Do not delegate again.

Complete role contract
Name: {contract.name}
Description: {contract.description}
Model: {contract.model}
Reasoning effort: {contract.model_reasoning_effort}
Developer instructions:
{contract.developer_instructions}

Bounded direct-child task
Objective: {task.objective}
Owned paths:
{_list_block(task.owned_paths)}
Inputs:
{_list_block(task.inputs)}
Acceptance criteria:
{_list_block(task.acceptance_criteria)}
Required evidence:
{_list_block(task.required_evidence)}
Prohibited actions:
{_list_block(task.prohibited_actions)}

Parent synthesis: return evidence to the parent; do not broaden scope, commit, push, release, or publish.
"""
    return {
        "agent_type": "default",
        "fork_turns": "none",
        "model": contract.model,
        "reasoning_effort": contract.model_reasoning_effort,
        "message": message,
    }


def _contract_json(contract: RoleContract) -> str:
    document = dataclasses.asdict(contract)
    document["path"] = str(contract.path)
    return json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Resolve a role from the installed plugin bundle."""

    parser = argparse.ArgumentParser(description="Resolve a plugin-local studio role")
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--project-root", type=Path, required=True)
    resolve_parser.add_argument("--role", required=True)
    arguments = parser.parse_args(argv)
    try:
        bundle_root = Path(__file__).absolute().parents[2]
        contract = resolve_role(bundle_root, arguments.project_root, arguments.role)
    except (OSError, ValueError) as error:
        print(f"Agent delegation resolver: ERROR ({error})", file=sys.stderr)
        return 2
    sys.stdout.write(_contract_json(contract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
