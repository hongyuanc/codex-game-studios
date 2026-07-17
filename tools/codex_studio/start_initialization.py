"""Fail-closed preflight and audit for the bounded Start ledger."""

from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tomllib
from typing import Iterator, Mapping, Sequence

if __package__ in {None, ""}:
    _BUNDLED_STUDIO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_BUNDLED_STUDIO_ROOT))

from tools.codex_studio.engine_pack import (
    STUDIO_KEYS,
    SUPPORTED_ENGINES,
    StudioConfig,
    _link_kind,
    _serialize_config,
    _validate_target_values,
    _validate_text,
    load_studio_config,
)


_CONTRACT_JSON = r'''{"authority":{"active_engine_pack":"none","engine":"unconfigured","engine_version":"","language":"","model_policy":"balanced","review_mode":"phase-gated"},"default_authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","execution":{"audit_reads":"link-safe filesystem path types and SHA-256 digests (file mode is not part of this material contract)","cli":"tools/codex_studio/start_initialization.py --preflight|--audit LEDGER --project-root PROJECT","ledger_schema_version":1},"first_run":{"action_unit":"filesystem path","allowed_atomic_kinds":["create","modify","merge","delete","directory-create","managed-block-edit"],"allowed_parent_directories":[".codex","production"],"approved_targets":[".codex/studio.toml","production/stage.txt"],"approval_sequence":["detect","select-next-step","initialization-changeset","approval","write"],"forbidden_action_forms":["glob","recursive","tree-copy","bulk"],"forbidden_roots":[".agents/skills",".codex/agents",".codex/agent-packs","Codex Studio Testing Framework","docs/engine-reference"],"initialization_changesets":1,"max_path_mutations":10,"pre_approval_writes":0,"replan_above_max_path_mutations":true,"speculative_empty_directories":false},"initialized":{"approval_pairs":{"review-mode-proposal":"review-mode-approval","stage-proposal":"stage-approval"},"initialization_changesets":0,"proposal_targets":{"review-mode-proposal":".codex/studio.toml","stage-proposal":"production/stage.txt"},"review_modes":["full","phase-gated","solo"],"separate_proposals":true,"stage_action_kinds":["create","modify","merge"],"zero_unapproved_writes":true},"schema_version":1}'''
START_INITIALIZATION_CONTRACT: dict[str, object] = json.loads(_CONTRACT_JSON)
_FILE_ACTION_KEYS = {"path", "kind", "material_change", "form", "expanded_paths", "sha256"}
_DIRECTORY_ACTION_KEYS = _FILE_ACTION_KEYS | {"required_by"}
_WRITE_KEYS = {"type", "path", "kind", "material_change", "sha256"}


def _schema_file_action(path: str, material_change: str, content: str, *, kind: str = "create") -> dict[str, object]:
    return {"path": path, "kind": kind, "material_change": material_change, "form": "atomic", "expanded_paths": [path], "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _schema_write(action: Mapping[str, object]) -> dict[str, object]:
    return {"type": "write", **{key: action[key] for key in ("path", "kind", "material_change", "sha256")}}


def _schema_directory_action(path: str, required_by: str, material_change: str) -> dict[str, object]:
    return {"path": path, "kind": "directory-create", "material_change": material_change, "form": "atomic", "expanded_paths": [path], "required_by": required_by, "sha256": None}


def _config_mapping(config: StudioConfig) -> dict[str, str]:
    return {key: getattr(config, key) for key in STUDIO_KEYS}


def _config_from_mapping(value: object) -> StudioConfig:
    if not isinstance(value, Mapping) or set(value) != set(STUDIO_KEYS) or any(not isinstance(value.get(key), str) for key in STUDIO_KEYS): raise ValueError("review-mode authority_before must contain the exact six string fields")
    return StudioConfig(**{key: value[key] for key in STUDIO_KEYS})


def _review_mode_post_image(before: StudioConfig, review_mode: str) -> bytes:
    return _serialize_config(dataclasses.replace(before, review_mode=review_mode))


_DEFAULT_CONFIG = _config_from_mapping(START_INITIALIZATION_CONTRACT["authority"])
_DEFAULT_AUTHORITY = START_INITIALIZATION_CONTRACT["default_authority_toml"]
_FULL_REVIEW_AUTHORITY = _review_mode_post_image(_DEFAULT_CONFIG, "full").decode()
_AUTHORITY_PARENT_ACTION = _schema_directory_action(".codex", ".codex/studio.toml", "create the authority parent")
_AUTHORITY_ACTION = _schema_file_action(".codex/studio.toml", "write the complete default authority", START_INITIALIZATION_CONTRACT["default_authority_toml"])
_PRODUCTION_PARENT_ACTION = _schema_directory_action("production", "production/stage.txt", "create the stage parent")
_STAGE_ACTION = _schema_file_action("production/stage.txt", "write the selected initial stage", "Concept\n")
_REVIEW_MODE_ACTION = _schema_file_action(".codex/studio.toml", "update only review_mode to full in the complete authority", _FULL_REVIEW_AUTHORITY, kind="modify")


def _example(initial_directories: Mapping[str, str], initial_files: Mapping[str, str], session: Mapping[str, object], write_contents: Mapping[str, str]) -> dict[str, object]:
    return {"initial_state": {"directories": dict(initial_directories), "files": dict(initial_files)}, "session": copy.deepcopy(session), "write_contents": dict(write_contents)}


def _first_run_example(next_step: str) -> dict[str, object]:
    actions = [copy.deepcopy(_AUTHORITY_PARENT_ACTION), copy.deepcopy(_AUTHORITY_ACTION)]
    write_contents = {".codex/studio.toml": _DEFAULT_AUTHORITY}
    if next_step == "setup-engine":
        actions.extend((copy.deepcopy(_PRODUCTION_PARENT_ACTION), copy.deepcopy(_STAGE_ACTION)))
        write_contents["production/stage.txt"] = "Concept\n"
    session = {"authority_state": "missing", "events": [{"type": "detect"}, {"type": "select-next-step", "next_step": next_step}, {"type": "initialization-changeset", "authority_toml": _DEFAULT_AUTHORITY, "actions": actions}, {"type": "approval"}, *[_schema_write(action) for action in actions]]}
    return _example({".codex": "missing", "production": "missing"}, {}, session, write_contents)


def _initialized_stage_group(actions: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    return [{"type": "stage-proposal", "actions": copy.deepcopy(list(actions))}, {"type": "stage-approval"}, *[_schema_write(action) for action in actions]]


def _initialized_review_group() -> list[dict[str, object]]:
    proposal = {"type": "review-mode-proposal", "review_mode": "full", "authority_before": _config_mapping(_DEFAULT_CONFIG), "actions": [copy.deepcopy(_REVIEW_MODE_ACTION)]}
    return [proposal, {"type": "review-mode-approval"}, _schema_write(_REVIEW_MODE_ACTION)]


def _initialized_example(*, stage: bool, review_mode: bool) -> dict[str, object]:
    events: list[dict[str, object]] = [{"type": "detect"}]
    write_contents: dict[str, str] = {}
    if stage:
        events.extend(_initialized_stage_group((_PRODUCTION_PARENT_ACTION, _STAGE_ACTION)))
        write_contents["production/stage.txt"] = "Concept\n"
    if review_mode:
        events.extend(_initialized_review_group())
        write_contents[".codex/studio.toml"] = _FULL_REVIEW_AUTHORITY
    session = {"authority_state": "initialized", "events": events}
    return _example({".codex": "directory", "production": "missing"}, {".codex/studio.toml": _DEFAULT_AUTHORITY}, session, write_contents)


_LEDGER_SCHEMA = {
    "ledger_schema_version": 1,
    "top_level": {"exact_keys": ["authority_state", "events"], "authority_state": ["missing", "initialized"], "events": "array"},
    "authority": {"default_toml_exact_bytes": START_INITIALIZATION_CONTRACT["default_authority_toml"], "default_toml_sha256": hashlib.sha256(START_INITIALIZATION_CONTRACT["default_authority_toml"].encode()).hexdigest(), "missing_requirement": "exactly one .codex/studio.toml create action and reconciled write with these bytes and digest"},
    "control_events": {"detect": {"exact_keys": ["type"]}, "select-next-step": {"exact_keys": ["type", "next_step"], "next_step": ["brainstorm", "setup-engine", "project-stage-detect"]}, "approval": {"exact_keys": ["type"]}, "stage-approval": {"exact_keys": ["type"]}, "review-mode-approval": {"exact_keys": ["type"]}},
    "events": {"initialization-changeset": {"exact_keys": ["type", "authority_toml", "actions"], "authority_toml": START_INITIALIZATION_CONTRACT["default_authority_toml"]}, "stage-proposal": {"exact_keys": ["type", "actions"]}, "review-mode-proposal": {"exact_keys": ["type", "review_mode", "authority_before", "actions"], "review_mode": ["full", "phase-gated", "solo"], "authority_before_exact_keys": list(STUDIO_KEYS)}},
    "action": {"file_exact_keys": sorted(_FILE_ACTION_KEYS), "directory_exact_keys": sorted(_DIRECTORY_ACTION_KEYS), "path": "normalized repository-relative approved target", "kind": ["create", "modify", "merge", "delete", "directory-create", "managed-block-edit"], "form": "atomic", "expanded_paths": "[path]", "material_change": "non-empty string", "sha256": "64 lowercase hex for file actions; null for delete and directory-create", "required_by": "string (directory-create only)"},
    "write": {"exact_keys": sorted(_WRITE_KEYS), "type": "write", "fields": "repeat approved action path/kind/material_change/sha256 in order"},
    "ordering": {"first_run": {"exact_sequence": ["detect", "select-next-step", "initialization-changeset", "approval", "one write per action in action order"], "initialization_changesets": 1}, "initialized": {"exact_prefix": ["detect"], "repeating_group": ["unique proposal", "matching separate approval", "one write per action in action order"], "initialization_changesets": 0}},
    "initialized_groups": {"stage-proposal": {"approval": "stage-approval", "target": "production/stage.txt", "optional_parent": "production", "action_kind": ["create", "modify", "merge"], "preimage": "create requires missing; modify or merge requires existing regular", "post_image": "successful audit requires regular production/stage.txt whose SHA-256 matches the action and write"}, "review-mode-proposal": {"approval": "review-mode-approval", "target": ".codex/studio.toml", "action_kind": "modify", "optional_parent": None, "post_image": "canonical complete six-field authority_before with only review_mode changed from one closed current value to a different closed target value; action/write SHA-256 matches exact post-image"}, "constraints": "each proposal type and mutation path appears at most once; only a stage proposal may include its observed-missing production parent immediately before the create or merge target"},
    "selection_stage_rule": "a production/stage.txt action exists if and only if select-next-step.next_step is setup-engine; it uses create for missing or modify/merge for existing regular and always leaves a digest-bound regular file; brainstorm and project-stage-detect omit it",
    "write_reconciliation": {"cardinality": "exactly one write per approved action", "order": "same order as actions", "exact_fields": ["path", "kind", "material_change", "sha256"], "unapproved_writes": 0},
    "example_envelope": {"exact_keys": ["initial_state", "session", "write_contents"], "initial_state": {"exact_keys": ["directories", "files"], "directories": {".codex": ["missing", "directory"], "production": ["missing", "directory"]}, "files": "exact repository-relative UTF-8 pre-images"}, "write_contents": "exact UTF-8 post-image for every non-directory, non-delete approved action"},
    "examples": {
        "first_run_brainstorm": _first_run_example("brainstorm"),
        "first_run_project_stage_detect": _first_run_example("project-stage-detect"),
        "first_run_setup_engine": _first_run_example("setup-engine"),
        "initialized_review_mode": _initialized_example(stage=False, review_mode=True),
        "initialized_stage": _initialized_example(stage=True, review_mode=False),
        "initialized_stage_and_review_mode": _initialized_example(stage=True, review_mode=True),
    },
}


def contract() -> dict[str, object]: return copy.deepcopy(START_INITIALIZATION_CONTRACT)
def contract_fingerprint(value: Mapping[str, object] | None = None) -> str: return hashlib.sha256(json.dumps(START_INITIALIZATION_CONTRACT if value is None else value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def ledger_schema() -> dict[str, object]: return copy.deepcopy(_LEDGER_SCHEMA)
def ledger_schema_fingerprint() -> str: return hashlib.sha256(json.dumps(_LEDGER_SCHEMA, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def ledger_schema_document() -> str: return json.dumps(_LEDGER_SCHEMA, sort_keys=True, separators=(",", ":"))


def contract_summary(value: Mapping[str, object] | None = None) -> str:
    source = START_INITIALIZATION_CONTRACT if value is None else value
    first, initialized, authority, execution = (_mapping(source, key) for key in ("first_run", "initialized", "authority", "execution"))
    quoted = lambda values: ", ".join(f"`{item}`" for item in values)
    return "\n".join((
        f"- First run has exactly {first['initialization_changesets']} Initialization changeset and at most {first['max_path_mutations']} unique path mutations; each mutation is one {first['action_unit']}.",
        f"- The only first-run project-owned file targets are {quoted(_strings(first, 'approved_targets'))}; a parent directory is created only when observed missing, before a required create or merge child, never for delete or speculation.",
        f"- Each action and write has an exact closed schema, one normalized target, material change, and SHA-256 digest where content exists; actions use {quoted(_strings(first, 'allowed_atomic_kinds'))} and never {quoted(_strings(first, 'forbidden_action_forms'))} or aliases.",
        f"- Forbidden roots and every descendant are {quoted(_strings(first, 'forbidden_roots'))}; all other paths are outside selected and approved project authority.",
        f"- No writes precede approval ({first['pre_approval_writes']}); writes match approved actions exactly in order, and a plan above the cap replans ({first['replan_above_max_path_mutations']}).",
        "- The six-field default authority is " + "; ".join(f"`{key} = {json.dumps(item)}`" for key, item in authority.items()) + ", and missing authority must create and write its exact bytes.",
        f"- Initialized repositories have {initialized['initialization_changesets']} Initialization changesets and retain unique proposal-specific stage and review-mode approval/write groups; stage uses {quoted(_strings(initialized, 'stage_action_kinds'))}, bound to its observed preimage, and must audit as a regular digest-matching file; review mode is a full-file `modify` from and to one of {quoted(_strings(initialized, 'review_modes'))}, preserving every other authority value.",
        f"- Installed execution uses `{execution['cli']}` and ledger schema version {execution['ledger_schema_version']}. Preflight and audit are link/reparse-safe; {execution['audit_reads']}.",
    ))


def validate_contract(value: Mapping[str, object]) -> None:
    if not isinstance(value, Mapping) or contract_fingerprint(value) != contract_fingerprint(): raise ValueError("Start initialization contract differs from the approved normative source")


def validate_documentation(runtime_text: str, framework_text: str) -> None:
    contract_marker = f"<!-- start-initialization-contract:sha256={contract_fingerprint()} -->"
    summary = f"<!-- start-initialization-summary:start\n{contract_summary()}\nstart-initialization-summary:end -->"
    schema_marker = f"<!-- start-initialization-ledger-schema:sha256={ledger_schema_fingerprint()} -->"
    schema_block = f"<!-- start-initialization-ledger-schema:start\n{ledger_schema_document()}\nstart-initialization-ledger-schema:end -->"
    for label, text in (("runtime", runtime_text), ("framework", framework_text)):
        if text.count(contract_marker) != 1 or text.count(summary) != 1 or text.count(schema_marker) != 1 or text.count(schema_block) != 1: raise ValueError(f"{label} Start contract documentation is missing or stale")


_STANDARD_PATH_ALIASES = {Path("/etc"): Path("/private/etc"), Path("/tmp"): Path("/private/tmp"), Path("/var"): Path("/private/var")}


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _is_standard_path_alias(path: Path) -> bool:
    expected = _STANDARD_PATH_ALIASES.get(path)
    return expected is not None and Path(os.path.realpath(path)) == expected and expected.is_dir()


def _validate_root_ancestry(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try: metadata = os.lstat(current)
        except FileNotFoundError: raise ValueError(f"project root ancestry is missing: {current}") from None
        link_kind = _link_kind(metadata)
        if link_kind and not _is_standard_path_alias(current): raise ValueError(f"project root ancestry contains unsafe {link_kind}: {current}")


def _checked_git_metadata(root: Path) -> None:
    git = root / ".git"
    try: metadata = os.lstat(git)
    except FileNotFoundError: raise ValueError(f"project root is not a Git repository: {root}") from None
    if _link_kind(metadata) or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)): raise ValueError(f"project root has unsafe Git metadata: {root}")


def _assert_root_identity(root: Path, expected: tuple[int, int]) -> None:
    try: metadata = os.lstat(root)
    except FileNotFoundError: raise ValueError(f"project root changed during validation: {root}") from None
    if _link_kind(metadata) or not stat.S_ISDIR(metadata.st_mode) or _identity(metadata) != expected: raise ValueError(f"project root changed during validation: {root}")


@dataclasses.dataclass
class _PinnedRoot:
    path: Path
    identity: tuple[int, int]
    descriptor: int | None


_HAS_DIR_FD = (
    os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.stat in os.supports_follow_symlinks
    and os.scandir in os.supports_fd
)


def _assert_pinned_root(root: _PinnedRoot) -> None:
    try:
        lexical = os.lstat(root.path)
        opened = os.fstat(root.descriptor) if root.descriptor is not None else lexical
    except (FileNotFoundError, OSError):
        raise ValueError(f"project root changed during validation: {root.path}") from None
    if (
        _link_kind(lexical)
        or not stat.S_ISDIR(lexical.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or _identity(lexical) != root.identity
        or _identity(opened) != root.identity
    ):
        raise ValueError(f"project root changed during validation: {root.path}")


@contextlib.contextmanager
def _pinned_root(root: Path | _PinnedRoot) -> Iterator[_PinnedRoot]:
    if isinstance(root, _PinnedRoot):
        _assert_pinned_root(root)
        yield root
        _assert_pinned_root(root)
        return
    safe = _real_root(root)
    metadata = os.lstat(safe)
    descriptor: int | None = None
    if _HAS_DIR_FD:
        flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0))
        descriptor = os.open(safe, flags)
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISDIR(opened.st_mode) or _identity(opened) != _identity(metadata):
            os.close(descriptor)
            raise ValueError(f"project root changed while it was pinned: {safe}")
    pinned = _PinnedRoot(safe, _identity(metadata), descriptor)
    try:
        _assert_pinned_root(pinned)
        yield pinned
        _assert_pinned_root(pinned)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _real_root(root: Path) -> Path:
    candidate = Path(os.path.abspath(os.fspath(root)))
    _validate_root_ancestry(candidate)
    try: candidate_before = os.lstat(candidate)
    except FileNotFoundError: raise ValueError(f"project root is missing: {candidate}") from None
    if _link_kind(candidate_before): raise ValueError(f"project root is an unsafe link or reparse point: {candidate}")
    if not stat.S_ISDIR(candidate_before.st_mode): raise ValueError(f"project root is not a directory: {candidate}")
    _checked_git_metadata(candidate)
    result = subprocess.run(["git", "-C", str(candidate), "rev-parse", "--show-toplevel"], text=True, capture_output=True, check=False)
    if result.returncode != 0 or not result.stdout.strip(): raise ValueError(f"project root is not the Git top-level: {candidate}")
    git_top = Path(result.stdout.strip())
    if not git_top.is_absolute(): raise ValueError(f"Git returned a non-absolute project root: {git_top}")
    canonical = Path(os.path.realpath(git_top))
    _validate_root_ancestry(canonical)
    try:
        candidate_after = os.lstat(candidate)
        canonical_meta = os.lstat(canonical)
    except FileNotFoundError: raise ValueError(f"project root changed during validation: {candidate}") from None
    if _identity(candidate_before) != _identity(candidate_after) or _identity(candidate_after) != _identity(canonical_meta) or _link_kind(canonical_meta) or not stat.S_ISDIR(canonical_meta.st_mode): raise ValueError(f"project root is not the Git top-level: {candidate}")
    _checked_git_metadata(canonical)
    return canonical


def _relative_state_lexical(root: Path, relative: str) -> tuple[str, os.stat_result | None]:
    current = root
    for index, part in enumerate(PurePosixPath(relative).parts):
        current /= part
        try: meta = os.lstat(current)
        except FileNotFoundError:
            parts = PurePosixPath(relative).parts
            if parts[:index + 1] in ((".codex",), ("production",)) and relative in {".codex/studio.toml", "production/stage.txt"}: return "missing", None
            return ("missing", None) if index == len(parts) - 1 else (_raise_unsafe(f"missing parent: {current}"))
        if _link_kind(meta): return _raise_unsafe(f"unsafe link or reparse point: {current}")
        if index < len(PurePosixPath(relative).parts) - 1 and not stat.S_ISDIR(meta.st_mode): return _raise_unsafe(f"non-directory parent: {current}")
    if stat.S_ISDIR(meta.st_mode): return "directory", meta
    if stat.S_ISREG(meta.st_mode): return "regular", meta
    return _raise_unsafe(f"unsafe path type: {current}")


def _missing_relative_state(relative: str, index: int, current: Path) -> tuple[str, None]:
    parts = PurePosixPath(relative).parts
    if parts[:index + 1] in ((".codex",), ("production",)) and relative in {".codex/studio.toml", "production/stage.txt"}:
        return "missing", None
    if index == len(parts) - 1:
        return "missing", None
    raise ValueError(f"missing parent: {current}")


def _relative_state_pinned(root: _PinnedRoot, relative: str) -> tuple[str, os.stat_result | None]:
    _assert_pinned_root(root)
    if root.descriptor is None:
        result = _relative_state_lexical(root.path, relative)
        _assert_pinned_root(root)
        return result
    parts = PurePosixPath(relative).parts
    descriptor = os.dup(root.descriptor)
    try:
        for index, part in enumerate(parts):
            current = root.path.joinpath(*parts[:index + 1])
            try:
                metadata = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                return _missing_relative_state(relative, index, current)
            if _link_kind(metadata):
                raise ValueError(f"unsafe link or reparse point: {current}")
            if index < len(parts) - 1:
                if not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError(f"non-directory parent: {current}")
                child = os.open(
                    part,
                    os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
                    dir_fd=descriptor,
                )
                opened = os.fstat(child)
                if _identity(metadata) != _identity(opened) or not stat.S_ISDIR(opened.st_mode):
                    os.close(child)
                    raise ValueError(f"path changed while it was opened: {current}")
                os.close(descriptor)
                descriptor = child
        if stat.S_ISDIR(metadata.st_mode):
            return "directory", metadata
        if stat.S_ISREG(metadata.st_mode):
            return "regular", metadata
        raise ValueError(f"unsafe path type: {root.path / relative}")
    finally:
        os.close(descriptor)


def _relative_state(root: Path | _PinnedRoot, relative: str) -> tuple[str, os.stat_result | None]:
    if isinstance(root, _PinnedRoot):
        return _relative_state_pinned(root, relative)
    return _relative_state_lexical(root, relative)


def _open_relative_directory(root: _PinnedRoot, relative: str) -> int | None:
    if root.descriptor is None:
        return None
    descriptor = os.dup(root.descriptor)
    for index, part in enumerate(PurePosixPath(relative).parts):
        try:
            before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            os.close(descriptor)
            return None
        current = root.path.joinpath(*PurePosixPath(relative).parts[:index + 1])
        if _link_kind(before) or not stat.S_ISDIR(before.st_mode):
            os.close(descriptor)
            raise ValueError(f"unsafe inventory directory: {current}")
        child = os.open(
            part,
            os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
            dir_fd=descriptor,
        )
        opened = os.fstat(child)
        os.close(descriptor)
        if _identity(before) != _identity(opened) or not stat.S_ISDIR(opened.st_mode):
            os.close(child)
            raise ValueError(f"inventory directory changed while opened: {current}")
        descriptor = child
    return descriptor


def _scan_tree_files(root: _PinnedRoot, relative: str, suffixes: set[str] | None = None) -> list[Path]:
    _assert_pinned_root(root)
    if root.descriptor is None:
        base = root.path / relative
        result = [
            path for path in base.rglob("*")
            if base.is_dir() and path.is_file() and path.name not in {"AGENTS.md", ".gitkeep"}
            and (suffixes is None or path.suffix in suffixes)
        ]
        _assert_pinned_root(root)
        return result
    base_descriptor = _open_relative_directory(root, relative)
    if base_descriptor is None:
        return []
    result: list[Path] = []

    def visit(descriptor: int, prefix: PurePosixPath) -> None:
        with os.scandir(descriptor) as entries:
            for entry in entries:
                metadata = entry.stat(follow_symlinks=False)
                if _link_kind(metadata):
                    continue
                child_relative = prefix / entry.name
                if stat.S_ISDIR(metadata.st_mode):
                    child = os.open(
                        entry.name,
                        os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
                        dir_fd=descriptor,
                    )
                    try:
                        opened = os.fstat(child)
                        if _identity(metadata) != _identity(opened) or not stat.S_ISDIR(opened.st_mode):
                            raise ValueError(f"inventory entry changed while opened: {root.path / child_relative}")
                        visit(child, child_relative)
                    finally:
                        os.close(child)
                elif (
                    stat.S_ISREG(metadata.st_mode)
                    and entry.name not in {"AGENTS.md", ".gitkeep"}
                    and (suffixes is None or PurePosixPath(entry.name).suffix in suffixes)
                ):
                    result.append(root.path / child_relative)

    try:
        visit(base_descriptor, PurePosixPath(relative))
    finally:
        os.close(base_descriptor)
    _assert_pinned_root(root)
    return result


def _scan_directories(root: _PinnedRoot, relative: str) -> list[Path]:
    _assert_pinned_root(root)
    if root.descriptor is None:
        base = root.path / relative
        result = [path for path in base.iterdir() if path.is_dir()] if base.is_dir() else []
        _assert_pinned_root(root)
        return result
    descriptor = _open_relative_directory(root, relative)
    if descriptor is None:
        return []
    try:
        with os.scandir(descriptor) as entries:
            return [
                root.path / relative / entry.name for entry in entries
                if not _link_kind(entry.stat(follow_symlinks=False))
                and stat.S_ISDIR(entry.stat(follow_symlinks=False).st_mode)
            ]
    finally:
        os.close(descriptor)


def _raise_unsafe(message: str): raise ValueError(message)
def observed_directories(root: Path | _PinnedRoot) -> dict[str, str]:
    with _pinned_root(root) as pinned:
        observed = {
            path: _relative_state(pinned, path)[0]
            for path in _strings(_mapping(START_INITIALIZATION_CONTRACT, "first_run"), "allowed_parent_directories")
        }
        _assert_pinned_root(pinned)
        return observed


def validate_session(session: Mapping[str, object], *, directories: Mapping[str, object] | None = None, audit: bool = False) -> None:
    validate_contract(START_INITIALIZATION_CONTRACT)
    if not isinstance(session, Mapping) or set(session) != {"authority_state", "events"} or session.get("authority_state") not in {"missing", "initialized"} or not isinstance(session.get("events"), list): raise ValueError("invalid Start session schema")
    observed = _directory_observation(directories)
    (_validate_first_run if session["authority_state"] == "missing" else _validate_initialized)(session["events"], observed, audit=audit)


def preflight_session(session: Mapping[str, object], root: Path) -> dict[str, object]:
    if not isinstance(session, Mapping): raise ValueError("Start ledger must be a JSON object")
    with _pinned_root(root) as pinned:
        detected = detect_project_state(pinned)
        if detected["authority_state"] == "repair-block": raise ValueError("invalid studio authority blocks Start initialization")
        if session.get("authority_state") != detected["authority_state"]: raise ValueError("Start ledger authority state differs from the observed project")
        validate_session(session, directories=observed_directories(pinned))
        _verify_stage_preflight(session, pinned)
        if session["authority_state"] == "initialized":
            _verify_review_mode_preflight(session, _load_studio_config_pinned(pinned))
        _assert_pinned_root(pinned)
        return {"contract_sha256": contract_fingerprint(), "ledger_schema_version": 1, "mode": "preflight", "status": "ok"}


def audit_session(session: Mapping[str, object], root: Path) -> dict[str, object]:
    if not isinstance(session, Mapping): raise ValueError("Start ledger must be a JSON object")
    with _pinned_root(root) as pinned:
        validate_session(session, directories=observed_directories(pinned), audit=True)
        for write in _writes_from_session(session):
            _assert_pinned_root(pinned)
            state, meta = _relative_state(pinned, write["path"])
            if write["kind"] == "delete":
                if state != "missing": raise ValueError(f"audit deleted path still exists: {write['path']}")
            elif write["kind"] == "directory-create":
                if state != "directory": raise ValueError(f"audit missing created directory: {write['path']}")
            elif state != "regular" or _secure_digest(pinned, write["path"], meta) != write["sha256"]:
                raise ValueError(f"audit digest mismatch: {write['path']}")
            _assert_pinned_root(pinned)
        if session["authority_state"] == "initialized":
            _verify_review_mode_audit(session, _load_studio_config_pinned(pinned))
        _assert_pinned_root(pinned)
        return {"contract_sha256": contract_fingerprint(), "ledger_schema_version": 1, "mode": "audit", "status": "ok"}


def _secure_digest(root: _PinnedRoot, relative: str, before: os.stat_result | None) -> str:
    assert before is not None
    _assert_pinned_root(root)
    parent, name = _open_file_parent(root, relative)
    descriptor = os.open(
        name,
        os.O_RDONLY | int(getattr(os, "O_BINARY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
        dir_fd=parent,
    ) if parent is not None else os.open(
        root.path / relative,
        os.O_RDONLY | int(getattr(os, "O_BINARY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
    )
    try:
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino): raise ValueError(f"audit target changed while opened: {relative}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024): digest.update(chunk)
    finally:
        os.close(descriptor)
        if parent is not None:
            os.close(parent)
    state, after = _relative_state(root, relative)
    if state != "regular" or after is None or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino): raise ValueError(f"audit target changed after read: {relative}")
    return digest.hexdigest()


def _open_file_parent(root: _PinnedRoot, relative: str) -> tuple[int | None, str]:
    parts = PurePosixPath(relative).parts
    if root.descriptor is None:
        return None, parts[-1]
    descriptor = os.dup(root.descriptor)
    for index, part in enumerate(parts[:-1]):
        before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
        current = root.path.joinpath(*parts[:index + 1])
        if _link_kind(before) or not stat.S_ISDIR(before.st_mode):
            os.close(descriptor)
            raise ValueError(f"unsafe file parent: {current}")
        child = os.open(
            part,
            os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
            dir_fd=descriptor,
        )
        opened = os.fstat(child)
        os.close(descriptor)
        if _identity(before) != _identity(opened) or not stat.S_ISDIR(opened.st_mode):
            os.close(child)
            raise ValueError(f"file parent changed while opened: {current}")
        descriptor = child
    return descriptor, parts[-1]


def _secure_bytes(root: _PinnedRoot, relative: str) -> bytes:
    state, before = _relative_state(root, relative)
    if state != "regular" or before is None:
        raise ValueError(f"strict file is not regular: {relative}")
    parent, name = _open_file_parent(root, relative)
    descriptor = os.open(
        name,
        os.O_RDONLY | int(getattr(os, "O_BINARY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
        dir_fd=parent,
    ) if parent is not None else os.open(
        root.path / relative,
        os.O_RDONLY | int(getattr(os, "O_BINARY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
    )
    try:
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode) or _identity(before) != _identity(opened):
            raise ValueError(f"strict file changed while opened: {relative}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
    finally:
        os.close(descriptor)
        if parent is not None:
            os.close(parent)
    state, after = _relative_state(root, relative)
    if state != "regular" or after is None or _identity(before) != _identity(after):
        raise ValueError(f"strict file changed after read: {relative}")
    return b"".join(chunks)


def _load_studio_config_pinned(root: _PinnedRoot) -> StudioConfig:
    try:
        data = tomllib.loads(_secure_bytes(root, ".codex/studio.toml").decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError) as error:
        raise ValueError(f"invalid studio config: {error}") from error
    config = _config_from_mapping(data)
    if config.engine not in (*SUPPORTED_ENGINES, "unconfigured"):
        raise ValueError(f"invalid studio config engine: {config.engine}")
    if config.active_engine_pack not in (*SUPPORTED_ENGINES, "none"):
        raise ValueError(f"invalid studio config active_engine_pack: {config.active_engine_pack}")
    if config.engine == "unconfigured" and config.active_engine_pack != "none":
        raise ValueError("invalid studio config: unconfigured engine requires active_engine_pack = none")
    if config.engine in SUPPORTED_ENGINES and config.active_engine_pack != config.engine:
        raise ValueError("invalid studio config: engine and active_engine_pack differ")
    if config.engine in SUPPORTED_ENGINES:
        _validate_target_values(config.engine, config.engine_version, config.language, require_complete=False)
    allowed = _strings(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "review_modes")
    _validate_text(config.review_mode, "review mode", required=True)
    if config.review_mode not in allowed:
        raise ValueError(f"invalid studio config review_mode: {config.review_mode}")
    _validate_text(config.model_policy, "model policy", required=True)
    return config


def detect_project_state(root: Path | _PinnedRoot) -> dict[str, object]:
    with _pinned_root(root) as pinned:
        state, _ = _relative_state(pinned, ".codex/studio.toml")
        authority_state, engine, error = "missing", "unconfigured", None
        if state == "regular":
            try:
                engine, authority_state = _load_studio_config_pinned(pinned).engine, "initialized"
            except ValueError:
                authority_state, engine, error = "repair-block", None, "invalid-studio-authority"
        elif state != "missing":
            authority_state, engine, error = "repair-block", None, "invalid-studio-authority"
        files = {
            "source_files": _scan_tree_files(pinned, "src", {".gd", ".cs", ".cpp", ".h", ".rs", ".py", ".js", ".ts"}),
            "design_docs": _scan_tree_files(pinned, "design/gdd", {".md"}),
        }
        prototypes = _scan_directories(pinned, "prototypes")
        production = [
            *_scan_tree_files(pinned, "production/sprints"),
            *_scan_tree_files(pinned, "production/milestones"),
        ]
        result = {
            "engine": engine,
            "authority_state": authority_state,
            "authority_error": error,
            **files,
            "prototypes": prototypes,
            "production_files": production,
            "fresh": authority_state != "repair-block" and engine == "unconfigured" and not any(files.values()) and not prototypes and not production,
        }
        _assert_pinned_root(pinned)
        return result


def _validate_first_run(events: Sequence[object], directories: Mapping[str, str], *, audit: bool) -> None:
    typed = _event_mappings(events); prefix = [{"type": "detect"}]
    if typed[:1] != prefix or len(typed) < 4 or set(typed[1]) != {"type", "next_step"} or typed[1].get("type") != "select-next-step" or typed[1].get("next_step") not in {"brainstorm", "setup-engine", "project-stage-detect"} or typed[3] != {"type": "approval"} or any(event.get("type") != "write" for event in typed[4:]): raise ValueError("first-run events violate the approved ordering")
    change = typed[2]
    if set(change) != {"type", "authority_toml", "actions"} or change["type"] != "initialization-changeset" or change["authority_toml"] != START_INITIALIZATION_CONTRACT["default_authority_toml"]: raise ValueError("invalid Initialization changeset schema")
    actions = _action_mappings(change["actions"])
    if not actions or len(actions) > 10: raise ValueError("Initialization changeset path-mutation cap is violated")
    _validate_actions(actions, directories, audit=audit)
    has_stage = any(action["path"] == "production/stage.txt" for action in actions)
    if has_stage != (typed[1]["next_step"] == "setup-engine"): raise ValueError("selected next step does not match stage proposal")
    for action in actions:
        if action["path"] == "production/stage.txt" and action["kind"] not in _stage_action_kinds():
            raise ValueError("stage action must leave a regular digest-bound production/stage.txt")
    digest = hashlib.sha256(START_INITIALIZATION_CONTRACT["default_authority_toml"].encode()).hexdigest()
    if len([a for a in actions if a["path"] == ".codex/studio.toml" and a["kind"] == "create" and a["sha256"] == digest]) != 1: raise ValueError("missing authority requires exact studio.toml action")
    _reconcile_writes(actions, typed[4:])


def _validate_initialized(events: Sequence[object], directories: Mapping[str, str], *, audit: bool) -> None:
    typed = _event_mappings(events)
    if not typed or typed[0] != {"type": "detect"}: raise ValueError("initialized repository protocol begins with detection")
    pairs = _mapping(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "approval_pairs"); targets = _mapping(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "proposal_targets"); seen_types, seen_paths, index = set(), set(), 1
    while index < len(typed):
        proposal = typed[index]; kind = proposal.get("type")
        expected_keys = {"type", "review_mode", "authority_before", "actions"} if kind == "review-mode-proposal" else {"type", "actions"}
        if kind not in pairs or kind in seen_types or set(proposal) != expected_keys or index + 2 >= len(typed) or typed[index + 1] != {"type": pairs[kind]}: raise ValueError("initialized proposal lacks its exact separate approval")
        actions = _action_mappings(proposal["actions"]); _validate_actions(actions, directories, audit=audit); target = targets[kind]
        if [a["path"] for a in actions if a["kind"] != "directory-create"] != [target]: raise ValueError("proposal may mutate only its declared target")
        if kind == "review-mode-proposal":
            if len(actions) != 1 or actions[0]["kind"] != "modify": raise ValueError("review-mode proposal must be one full authority modify without a parent action")
            _review_mode_transition(proposal, actions[0])
        elif (
            actions[-1]["kind"] not in _stage_action_kinds()
            or len(actions) == 2 and not (actions[0]["kind"] == "directory-create" and actions[0]["required_by"] == target and actions[1]["path"] == target)
            or len(actions) not in {1, 2}
        ):
            raise ValueError("stage proposal must leave its sole target regular and digest-bound")
        if seen_paths.intersection(a["path"] for a in actions): raise ValueError("initialized proposal repeats a mutation path")
        writes = typed[index + 2:index + 2 + len(actions)]; _reconcile_writes(actions, writes); seen_types.add(kind); seen_paths.update(a["path"] for a in actions); index += 2 + len(actions)


def _review_mode_transition(proposal: Mapping[str, object], action: Mapping[str, object]) -> tuple[StudioConfig, StudioConfig]:
    before = _config_from_mapping(proposal["authority_before"])
    review_mode = proposal["review_mode"]
    allowed = _strings(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "review_modes")
    if before.review_mode not in allowed:
        raise ValueError("review-mode authority_before must use a current allowed value")
    if not isinstance(review_mode, str) or review_mode not in allowed or review_mode == before.review_mode: raise ValueError("review-mode proposal target must be a different allowed value")
    after = dataclasses.replace(before, review_mode=review_mode)
    expected_digest = hashlib.sha256(_serialize_config(after)).hexdigest()
    if action["path"] != ".codex/studio.toml" or action["kind"] != "modify" or action["sha256"] != expected_digest: raise ValueError("review-mode proposal digest must bind the canonical full authority post-image")
    return before, after


def _review_mode_proposals(session: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [event for event in _event_mappings(session["events"]) if event["type"] == "review-mode-proposal"]


def _verify_review_mode_preflight(session: Mapping[str, object], current: StudioConfig) -> None:
    for proposal in _review_mode_proposals(session):
        before, _ = _review_mode_transition(proposal, _action_mappings(proposal["actions"])[0])
        if before != current: raise ValueError("review-mode proposal authority_before differs from current strict authority")


def _verify_review_mode_audit(session: Mapping[str, object], actual: StudioConfig) -> None:
    proposals = _review_mode_proposals(session)
    if not proposals: return
    for proposal in proposals:
        _, expected = _review_mode_transition(proposal, _action_mappings(proposal["actions"])[0])
        if actual != expected: raise ValueError("review-mode audit changed authority fields beyond the approved review_mode")


def _stage_action_kinds() -> tuple[str, ...]:
    return _strings(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "stage_action_kinds")


def _verify_stage_preflight(session: Mapping[str, object], root: _PinnedRoot) -> None:
    actions = [
        action
        for event in _event_mappings(session["events"])
        if event["type"] in {"initialization-changeset", "stage-proposal"}
        for action in _action_mappings(event["actions"])
        if action["path"] == "production/stage.txt"
    ]
    if not actions:
        return
    if len(actions) != 1:
        raise ValueError("Start ledger must contain at most one stage mutation")
    state, _ = _relative_state(root, "production/stage.txt")
    kind = actions[0]["kind"]
    if kind == "create" and state != "missing":
        raise ValueError("stage create requires a missing production/stage.txt")
    if kind in {"modify", "merge"} and state != "regular":
        raise ValueError("stage modify or merge requires an existing regular production/stage.txt")
    if kind not in _stage_action_kinds():
        raise ValueError("stage action must leave a regular digest-bound production/stage.txt")


def _validate_actions(actions: Sequence[Mapping[str, object]], directories: Mapping[str, str], *, audit: bool) -> None:
    paths = [_validate_atomic_action(action) for action in actions]
    if len(paths) != len(set(paths)): raise ValueError("approved actions must have unique paths")
    for index, action in enumerate(actions):
        if action["kind"] == "directory-create":
            children = [i for i, child in enumerate(actions) if child["path"] == action["required_by"]]
            if len(children) != 1 or children[0] != index + 1 or actions[children[0]]["kind"] not in {"create", "merge"}: raise ValueError("parent directory must immediately precede create or merge child")
            if not audit and directories[action["path"]] != "missing": raise ValueError("parent directory creation requires a truly missing parent")
        elif action["kind"] in {"create", "merge"}:
            parent = PurePosixPath(action["path"]).parent.as_posix()
            if parent in directories and directories[parent] == "missing" and not any(a["path"] == parent and a["kind"] == "directory-create" for a in actions[:index]): raise ValueError("missing observed parent directory action")


def _validate_atomic_action(action: Mapping[str, object]) -> str:
    if not isinstance(action, Mapping): raise ValueError("action must be a mapping")
    expected = _DIRECTORY_ACTION_KEYS if action.get("kind") == "directory-create" else _FILE_ACTION_KEYS
    if set(action) != expected: raise ValueError("action has unknown, missing, or hidden fields")
    path = _normalized_path(action["path"]); kind = action["kind"]; first = _mapping(START_INITIALIZATION_CONTRACT, "first_run")
    if kind not in _strings(first, "allowed_atomic_kinds") or not isinstance(action["material_change"], str) or not action["material_change"].strip() or action["form"] != "atomic" or action["expanded_paths"] != [path]: raise ValueError("invalid atomic action")
    if any(token in action["material_change"].casefold() for token in _strings(first, "forbidden_action_forms")): raise ValueError("action uses a forbidden bulk form")
    if (kind in {"directory-create", "delete"} and action["sha256"] is not None) or (kind not in {"directory-create", "delete"} and (not isinstance(action["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", action["sha256"]) is None)): raise ValueError("invalid action digest")
    if any(path == root or path.startswith(root + "/") for root in _strings(first, "forbidden_roots")) or (kind == "directory-create" and (path not in _strings(first, "allowed_parent_directories") or action["required_by"] not in _strings(first, "approved_targets") or not action["required_by"].startswith(path + "/"))) or (kind != "directory-create" and path not in _strings(first, "approved_targets")): raise ValueError("action target is outside approved authority")
    return path


def _reconcile_writes(actions: Sequence[Mapping[str, object]], writes: Sequence[Mapping[str, object]]) -> None:
    if len(actions) != len(writes): raise ValueError("actual writes do not match approved actions")
    for action, write in zip(actions, writes, strict=True):
        if not isinstance(write, Mapping) or set(write) != _WRITE_KEYS or write.get("type") != "write" or tuple(write[k] for k in ("path", "kind", "material_change", "sha256")) != tuple(action[k] for k in ("path", "kind", "material_change", "sha256")): raise ValueError("actual write differs from approved action")


def _writes_from_session(session: Mapping[str, object]) -> list[Mapping[str, object]]: return [e for e in _event_mappings(session["events"]) if e["type"] == "write"]
def _directory_observation(value: Mapping[str, object] | None) -> Mapping[str, str]:
    allowed = set(_strings(_mapping(START_INITIALIZATION_CONTRACT, "first_run"), "allowed_parent_directories"))
    if value is None: return {p: "directory" for p in allowed}
    if set(value) != allowed: raise ValueError("invalid observed parent-directory state")
    result = {p: ("directory" if state is True else "missing" if state is False else state) for p, state in value.items()}
    if any(state not in {"missing", "directory"} for state in result.values()): raise ValueError("unsafe observed parent-directory state")
    return result
def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"): raise ValueError("action path must be normalized")
    path = PurePosixPath(value)
    if any(part in {".", ".."} for part in path.parts) or path.as_posix() != value or "//" in value or re.search(r"[*?\[\]{}]", value): raise ValueError("action path is unsafe")
    return value
def _event_mappings(events: Sequence[object]) -> list[Mapping[str, object]]:
    if any(not isinstance(event, Mapping) or not isinstance(event.get("type"), str) for event in events): raise ValueError("Start events must be typed mappings")
    return list(events)
def _action_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(action, Mapping) for action in value): raise ValueError("Start actions must be mappings")
    return list(value)
def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    child = value.get(key)
    if not isinstance(child, Mapping): raise ValueError(f"Start initialization contract {key} is invalid")
    return child
def _strings(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    child = value.get(key)
    if not isinstance(child, list) or any(not isinstance(item, str) for item in child): raise ValueError(f"Start initialization contract {key} is invalid")
    return tuple(child)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog="Ledger schema version 1; documentation embeds the complete canonical schema.")
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--preflight", type=Path, metavar="LEDGER"); mode.add_argument("--audit", type=Path, metavar="LEDGER"); parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        ledger = json.loads((args.preflight or args.audit).read_text(encoding="utf-8"))
        result = preflight_session(ledger, args.project_root) if args.preflight else audit_session(ledger, args.project_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as error:
        print(f"start-initialization: {error}", file=sys.stderr); return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"))); return 0

if __name__ == "__main__": raise SystemExit(_main())
