"""Fail-closed preflight and audit for the bounded Start ledger."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    _BUNDLED_STUDIO_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_BUNDLED_STUDIO_ROOT))

from tools.codex_studio.engine_pack import _link_kind, load_studio_config


_CONTRACT_JSON = r'''{"authority":{"active_engine_pack":"none","engine":"unconfigured","engine_version":"","language":"","model_policy":"balanced","review_mode":"phase-gated"},"default_authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","execution":{"audit_reads":"link-safe filesystem path types and SHA-256 digests (file mode is not part of this material contract)","cli":"tools/codex_studio/start_initialization.py --preflight|--audit LEDGER --project-root PROJECT","ledger_schema_version":1},"first_run":{"action_unit":"filesystem path","allowed_atomic_kinds":["create","modify","merge","delete","directory-create","managed-block-edit"],"allowed_parent_directories":[".codex","production"],"approved_targets":[".codex/studio.toml","production/stage.txt"],"approval_sequence":["detect","select-next-step","initialization-changeset","approval","write"],"forbidden_action_forms":["glob","recursive","tree-copy","bulk"],"forbidden_roots":[".agents/skills",".codex/agents",".codex/agent-packs","Codex Studio Testing Framework","docs/engine-reference"],"initialization_changesets":1,"max_path_mutations":10,"pre_approval_writes":0,"replan_above_max_path_mutations":true,"speculative_empty_directories":false},"initialized":{"approval_pairs":{"review-mode-proposal":"review-mode-approval","stage-proposal":"stage-approval"},"initialization_changesets":0,"proposal_targets":{"review-mode-proposal":".codex/studio.toml","stage-proposal":"production/stage.txt"},"separate_proposals":true,"zero_unapproved_writes":true},"schema_version":1}'''
START_INITIALIZATION_CONTRACT: dict[str, object] = json.loads(_CONTRACT_JSON)
_FILE_ACTION_KEYS = {"path", "kind", "material_change", "form", "expanded_paths", "sha256"}
_DIRECTORY_ACTION_KEYS = _FILE_ACTION_KEYS | {"required_by"}
_WRITE_KEYS = {"type", "path", "kind", "material_change", "sha256"}


def _schema_file_action(path: str, material_change: str, content: str, *, kind: str = "create") -> dict[str, object]:
    return {"path": path, "kind": kind, "material_change": material_change, "form": "atomic", "expanded_paths": [path], "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _schema_write(action: Mapping[str, object]) -> dict[str, object]:
    return {"type": "write", **{key: action[key] for key in ("path", "kind", "material_change", "sha256")}}


_AUTHORITY_ACTION = _schema_file_action(".codex/studio.toml", "write the complete default authority", START_INITIALIZATION_CONTRACT["default_authority_toml"])
_STAGE_ACTION = _schema_file_action("production/stage.txt", "write the selected initial stage", "Concept\n")
_REVIEW_MODE_ACTION = _schema_file_action(".codex/studio.toml", "update review mode to full", "review_mode = \"full\"\n", kind="modify")


def _first_run_example(next_step: str) -> dict[str, object]:
    actions = [copy.deepcopy(_AUTHORITY_ACTION)]
    if next_step == "setup-engine": actions.append(copy.deepcopy(_STAGE_ACTION))
    return {"authority_state": "missing", "events": [{"type": "detect"}, {"type": "select-next-step", "next_step": next_step}, {"type": "initialization-changeset", "authority_toml": START_INITIALIZATION_CONTRACT["default_authority_toml"], "actions": actions}, {"type": "approval"}, *[_schema_write(action) for action in actions]]}


def _initialized_group(proposal: str, approval: str, action: Mapping[str, object]) -> list[dict[str, object]]:
    return [{"type": proposal, "actions": [copy.deepcopy(action)]}, {"type": approval}, _schema_write(action)]


_LEDGER_SCHEMA = {
    "ledger_schema_version": 1,
    "top_level": {"exact_keys": ["authority_state", "events"], "authority_state": ["missing", "initialized"], "events": "array"},
    "authority": {"default_toml_exact_bytes": START_INITIALIZATION_CONTRACT["default_authority_toml"], "default_toml_sha256": hashlib.sha256(START_INITIALIZATION_CONTRACT["default_authority_toml"].encode()).hexdigest(), "missing_requirement": "exactly one .codex/studio.toml create action and reconciled write with these bytes and digest"},
    "control_events": {"detect": {"exact_keys": ["type"]}, "select-next-step": {"exact_keys": ["type", "next_step"], "next_step": ["brainstorm", "setup-engine", "project-stage-detect"]}, "approval": {"exact_keys": ["type"]}, "stage-approval": {"exact_keys": ["type"]}, "review-mode-approval": {"exact_keys": ["type"]}},
    "events": {"initialization-changeset": {"exact_keys": ["type", "authority_toml", "actions"], "authority_toml": START_INITIALIZATION_CONTRACT["default_authority_toml"]}, "stage-proposal": {"exact_keys": ["type", "actions"]}, "review-mode-proposal": {"exact_keys": ["type", "actions"]}},
    "action": {"file_exact_keys": sorted(_FILE_ACTION_KEYS), "directory_exact_keys": sorted(_DIRECTORY_ACTION_KEYS), "path": "normalized repository-relative approved target", "kind": ["create", "modify", "merge", "delete", "directory-create", "managed-block-edit"], "form": "atomic", "expanded_paths": "[path]", "material_change": "non-empty string", "sha256": "64 lowercase hex for file actions; null for delete and directory-create", "required_by": "string (directory-create only)"},
    "write": {"exact_keys": sorted(_WRITE_KEYS), "type": "write", "fields": "repeat approved action path/kind/material_change/sha256 in order"},
    "ordering": {"first_run": {"exact_sequence": ["detect", "select-next-step", "initialization-changeset", "approval", "one write per action in action order"], "initialization_changesets": 1}, "initialized": {"exact_prefix": ["detect"], "repeating_group": ["unique proposal", "matching separate approval", "one write per action in action order"], "initialization_changesets": 0}},
    "initialized_groups": {"stage-proposal": {"approval": "stage-approval", "target": "production/stage.txt", "optional_parent": "production"}, "review-mode-proposal": {"approval": "review-mode-approval", "target": ".codex/studio.toml", "optional_parent": ".codex"}, "constraints": "each proposal type and mutation path appears at most once; optional missing parent immediately precedes its sole create or merge target"},
    "selection_stage_rule": "a production/stage.txt action exists if and only if select-next-step.next_step is setup-engine; brainstorm and project-stage-detect omit it",
    "write_reconciliation": {"cardinality": "exactly one write per approved action", "order": "same order as actions", "exact_fields": ["path", "kind", "material_change", "sha256"], "unapproved_writes": 0},
    "examples": {
        "first_run_brainstorm": _first_run_example("brainstorm"),
        "first_run_project_stage_detect": _first_run_example("project-stage-detect"),
        "first_run_setup_engine": _first_run_example("setup-engine"),
        "initialized_review_mode": {"authority_state": "initialized", "events": [{"type": "detect"}, *_initialized_group("review-mode-proposal", "review-mode-approval", _REVIEW_MODE_ACTION)]},
        "initialized_stage": {"authority_state": "initialized", "events": [{"type": "detect"}, *_initialized_group("stage-proposal", "stage-approval", _STAGE_ACTION)]},
        "initialized_stage_and_review_mode": {"authority_state": "initialized", "events": [{"type": "detect"}, *_initialized_group("stage-proposal", "stage-approval", _STAGE_ACTION), *_initialized_group("review-mode-proposal", "review-mode-approval", _REVIEW_MODE_ACTION)]},
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
        f"- Initialized repositories have {initialized['initialization_changesets']} Initialization changesets and retain unique proposal-specific stage and review-mode approval/write groups.",
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


def _relative_state(root: Path, relative: str) -> tuple[str, os.stat_result | None]:
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


def _raise_unsafe(message: str): raise ValueError(message)
def observed_directories(root: Path) -> dict[str, str]:
    safe = _real_root(root)
    identity = _identity(os.lstat(safe))
    observed = {path: _relative_state(safe, path)[0] for path in _strings(_mapping(START_INITIALIZATION_CONTRACT, "first_run"), "allowed_parent_directories")}
    _assert_root_identity(safe, identity)
    return observed


def validate_session(session: Mapping[str, object], *, directories: Mapping[str, object] | None = None, audit: bool = False) -> None:
    validate_contract(START_INITIALIZATION_CONTRACT)
    if not isinstance(session, Mapping) or set(session) != {"authority_state", "events"} or session.get("authority_state") not in {"missing", "initialized"} or not isinstance(session.get("events"), list): raise ValueError("invalid Start session schema")
    observed = _directory_observation(directories)
    (_validate_first_run if session["authority_state"] == "missing" else _validate_initialized)(session["events"], observed, audit=audit)


def preflight_session(session: Mapping[str, object], root: Path) -> dict[str, object]:
    if not isinstance(session, Mapping): raise ValueError("Start ledger must be a JSON object")
    safe = _real_root(root); identity = _identity(os.lstat(safe)); detected = detect_project_state(safe)
    if detected["authority_state"] == "repair-block": raise ValueError("invalid studio authority blocks Start initialization")
    if session.get("authority_state") != detected["authority_state"]: raise ValueError("Start ledger authority state differs from the observed project")
    validate_session(session, directories=observed_directories(safe)); _assert_root_identity(safe, identity); return {"contract_sha256": contract_fingerprint(), "ledger_schema_version": 1, "mode": "preflight", "status": "ok"}


def audit_session(session: Mapping[str, object], root: Path) -> dict[str, object]:
    if not isinstance(session, Mapping): raise ValueError("Start ledger must be a JSON object")
    safe = _real_root(root); identity = _identity(os.lstat(safe)); validate_session(session, directories=observed_directories(safe), audit=True); _assert_root_identity(safe, identity)
    for write in _writes_from_session(session):
        _assert_root_identity(safe, identity)
        state, meta = _relative_state(safe, write["path"])
        if write["kind"] == "delete":
            if state != "missing": raise ValueError(f"audit deleted path still exists: {write['path']}")
        elif write["kind"] == "directory-create":
            if state != "directory": raise ValueError(f"audit missing created directory: {write['path']}")
        elif state != "regular" or _secure_digest(safe, write["path"], meta) != write["sha256"]: raise ValueError(f"audit digest mismatch: {write['path']}")
        _assert_root_identity(safe, identity)
    return {"contract_sha256": contract_fingerprint(), "ledger_schema_version": 1, "mode": "audit", "status": "ok"}


def _secure_digest(root: Path, relative: str, before: os.stat_result | None) -> str:
    assert before is not None
    path = root / relative; descriptor = os.open(path, os.O_RDONLY | int(getattr(os, "O_BINARY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)))
    try:
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino): raise ValueError(f"audit target changed while opened: {relative}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024): digest.update(chunk)
    finally: os.close(descriptor)
    state, after = _relative_state(root, relative)
    if state != "regular" or after is None or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino): raise ValueError(f"audit target changed after read: {relative}")
    return digest.hexdigest()


def detect_project_state(root: Path) -> dict[str, object]:
    root = _real_root(root); identity = _identity(os.lstat(root)); state, _ = _relative_state(root, ".codex/studio.toml")
    authority_state, engine, error = "missing", "unconfigured", None
    if state == "regular":
        try: engine, authority_state = load_studio_config(root).engine, "initialized"
        except ValueError: authority_state, engine, error = "repair-block", None, "invalid-studio-authority"
    elif state != "missing": authority_state, engine, error = "repair-block", None, "invalid-studio-authority"
    roots = {"source_files": (root / "src", {".gd", ".cs", ".cpp", ".h", ".rs", ".py", ".js", ".ts"}), "design_docs": (root / "design/gdd", {".md"})}
    files = {name: [p for p in base.rglob("*") if base.is_dir() and p.is_file() and p.name not in {"AGENTS.md", ".gitkeep"} and p.suffix in suffixes] for name, (base, suffixes) in roots.items()}
    prototypes = [p for p in (root / "prototypes").iterdir() if p.is_dir()] if (root / "prototypes").is_dir() else []
    production = [p for base in (root / "production/sprints", root / "production/milestones") if base.is_dir() for p in base.rglob("*") if p.is_file() and p.name not in {"AGENTS.md", ".gitkeep"}]
    result = {"engine": engine, "authority_state": authority_state, "authority_error": error, **files, "prototypes": prototypes, "production_files": production, "fresh": authority_state != "repair-block" and engine == "unconfigured" and not (root / "design/gdd/game-concept.md").is_file() and not any(files.values()) and not prototypes and not production}
    _assert_root_identity(root, identity)
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
    digest = hashlib.sha256(START_INITIALIZATION_CONTRACT["default_authority_toml"].encode()).hexdigest()
    if len([a for a in actions if a["path"] == ".codex/studio.toml" and a["kind"] == "create" and a["sha256"] == digest]) != 1: raise ValueError("missing authority requires exact studio.toml action")
    _reconcile_writes(actions, typed[4:])


def _validate_initialized(events: Sequence[object], directories: Mapping[str, str], *, audit: bool) -> None:
    typed = _event_mappings(events)
    if not typed or typed[0] != {"type": "detect"}: raise ValueError("initialized repository protocol begins with detection")
    pairs = _mapping(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "approval_pairs"); targets = _mapping(_mapping(START_INITIALIZATION_CONTRACT, "initialized"), "proposal_targets"); seen_types, seen_paths, index = set(), set(), 1
    while index < len(typed):
        proposal = typed[index]; kind = proposal.get("type")
        if kind not in pairs or kind in seen_types or set(proposal) != {"type", "actions"} or index + 2 >= len(typed) or typed[index + 1] != {"type": pairs[kind]}: raise ValueError("initialized proposal lacks its exact separate approval")
        actions = _action_mappings(proposal["actions"]); _validate_actions(actions, directories, audit=audit); target = targets[kind]
        if [a["path"] for a in actions if a["kind"] != "directory-create"] != [target]: raise ValueError("proposal may mutate only its declared target")
        if len(actions) == 2 and not (actions[0]["kind"] == "directory-create" and actions[0]["required_by"] == target and actions[1]["path"] == target) or len(actions) not in {1, 2}: raise ValueError("proposal parent must immediately precede its sole target")
        if seen_paths.intersection(a["path"] for a in actions): raise ValueError("initialized proposal repeats a mutation path")
        writes = typed[index + 2:index + 2 + len(actions)]; _reconcile_writes(actions, writes); seen_types.add(kind); seen_paths.update(a["path"] for a in actions); index += 2 + len(actions)


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
