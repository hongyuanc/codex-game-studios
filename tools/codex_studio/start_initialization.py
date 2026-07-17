"""Preflight and audit the bounded, approval-gated Start initialization ledger."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Mapping, Sequence

if __package__ in {None, ""}:
    _BUNDLED_STUDIO_ROOT = Path(__file__).resolve().parents[2]
    if str(_BUNDLED_STUDIO_ROOT) not in sys.path:
        sys.path.insert(0, str(_BUNDLED_STUDIO_ROOT))

from tools.codex_studio.engine_pack import load_studio_config


_CONTRACT_JSON = r'''{"authority":{"active_engine_pack":"none","engine":"unconfigured","engine_version":"","language":"","model_policy":"balanced","review_mode":"phase-gated"},"default_authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","execution":{"audit_reads":"filesystem path types and SHA-256 digests","cli":"tools/codex_studio/start_initialization.py --preflight|--audit LEDGER --project-root PROJECT","ledger_schema":"authority_state plus ordered events; action and write records have exact declared keys"},"first_run":{"action_unit":"filesystem path","allowed_atomic_kinds":["create","modify","merge","delete","directory-create","managed-block-edit"],"allowed_parent_directories":[".codex","production"],"approved_targets":[".codex/studio.toml","production/stage.txt"],"approval_sequence":["detect","select-next-step","initialization-changeset","approval","write"],"forbidden_action_forms":["glob","recursive","tree-copy","bulk"],"forbidden_roots":[".agents/skills",".codex/agents",".codex/agent-packs","Codex Studio Testing Framework","docs/engine-reference"],"initialization_changesets":1,"max_path_mutations":10,"pre_approval_writes":0,"replan_above_max_path_mutations":true,"speculative_empty_directories":false},"initialized":{"approval_pairs":{"review-mode-proposal":"review-mode-approval","stage-proposal":"stage-approval"},"initialization_changesets":0,"proposal_targets":{"review-mode-proposal":".codex/studio.toml","stage-proposal":"production/stage.txt"},"separate_proposals":true,"zero_unapproved_writes":true},"schema_version":1}'''
START_INITIALIZATION_CONTRACT: dict[str, object] = json.loads(_CONTRACT_JSON)
_FILE_ACTION_KEYS = {"path", "kind", "material_change", "form", "expanded_paths", "sha256"}
_DIRECTORY_ACTION_KEYS = _FILE_ACTION_KEYS | {"required_by"}
_WRITE_KEYS = {"type", "path", "kind", "material_change", "sha256"}


def contract() -> dict[str, object]:
    """Return an isolated copy of the sole Start initialization contract."""

    return copy.deepcopy(START_INITIALIZATION_CONTRACT)


def contract_fingerprint(value: Mapping[str, object] | None = None) -> str:
    """Return the canonical SHA-256 fingerprint for a contract mapping."""

    source = START_INITIALIZATION_CONTRACT if value is None else value
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def contract_summary(value: Mapping[str, object] | None = None) -> str:
    """Render the exact controlling Start prose from the normative contract."""

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
        f"- Initialized repositories have {initialized['initialization_changesets']} Initialization changesets and retain unique separate stage and review-mode proposal/approval/write groups.",
        f"- Installed execution uses `{execution['cli']}`. Preflight reads the observed project state; audit reads {execution['audit_reads']} after the approved writes.",
    ))


def validate_contract(value: Mapping[str, object]) -> None:
    """Fail closed unless a candidate is exactly the approved contract."""

    if not isinstance(value, Mapping) or contract_fingerprint(value) != contract_fingerprint():
        raise ValueError("Start initialization contract differs from the approved normative source")
    first, initialized = _mapping(value, "first_run"), _mapping(value, "initialized")
    if value.get("schema_version") != 1 or first["action_unit"] != "filesystem path":
        raise ValueError("unsupported Start initialization contract")
    if first["initialization_changesets"] != 1 or first["max_path_mutations"] != 10 or first["pre_approval_writes"] != 0:
        raise ValueError("invalid first-run mutation boundary")
    if first["replan_above_max_path_mutations"] is not True or first["speculative_empty_directories"] is not False:
        raise ValueError("invalid first-run safety controls")
    if tuple(_strings(first, "approval_sequence")) != ("detect", "select-next-step", "initialization-changeset", "approval", "write"):
        raise ValueError("invalid first-run approval ordering")
    if initialized["initialization_changesets"] != 0 or initialized["separate_proposals"] is not True or initialized["zero_unapproved_writes"] is not True:
        raise ValueError("invalid initialized-repository protocol")


def validate_documentation(runtime_text: str, framework_text: str) -> None:
    """Bind both Start documents' contract-derived prose to the production source."""

    marker = f"<!-- start-initialization-contract:sha256={contract_fingerprint()} -->"
    summary = f"<!-- start-initialization-summary:start\n{contract_summary()}\nstart-initialization-summary:end -->"
    for label, text in (("runtime", runtime_text), ("framework", framework_text)):
        if text.count(marker) != 1 or text.count(summary) != 1:
            raise ValueError(f"{label} Start contract documentation is missing or stale")


def observed_directories(root: Path) -> dict[str, bool]:
    """Read the only parent directories the Start ledger may create."""

    root = Path(root)
    first = _mapping(START_INITIALIZATION_CONTRACT, "first_run")
    return {path: (root / path).is_dir() for path in _strings(first, "allowed_parent_directories")}


def validate_session(session: Mapping[str, object], *, directories: Mapping[str, bool] | None = None, audit: bool = False) -> None:
    """Validate a planned Start ledger against observed parent-directory state."""

    validate_contract(START_INITIALIZATION_CONTRACT)
    if set(session) != {"authority_state", "events"} or session.get("authority_state") not in {"missing", "initialized"} or not isinstance(session.get("events"), list):
        raise ValueError("invalid Start session schema")
    observed = _directory_observation(directories)
    if session["authority_state"] == "missing":
        _validate_first_run(session["events"], observed, audit=audit)
    else:
        _validate_initialized(session["events"], observed, audit=audit)


def preflight_session(session: Mapping[str, object], root: Path) -> dict[str, object]:
    """Validate a proposed ledger against the actual pre-write project state."""

    detected = detect_project_state(root)
    if detected["authority_state"] == "repair-block":
        raise ValueError("invalid studio authority blocks Start initialization")
    if session.get("authority_state") != detected["authority_state"]:
        raise ValueError("Start ledger authority state differs from the observed project")
    validate_session(session, directories=observed_directories(root))
    return {"contract_sha256": contract_fingerprint(), "mode": "preflight", "status": "ok"}


def audit_session(session: Mapping[str, object], root: Path) -> dict[str, object]:
    """Audit actual post-write paths and digests against the approved ledger."""

    validate_session(session, directories=observed_directories(root), audit=True)
    for write in _writes_from_session(session):
        path = Path(root) / write["path"]
        kind = write["kind"]
        if kind == "directory-create":
            if not path.is_dir():
                raise ValueError(f"audit missing created directory: {write['path']}")
        elif kind == "delete":
            if path.exists():
                raise ValueError(f"audit deleted path still exists: {write['path']}")
        else:
            if not path.is_file() or _sha256_path(path) != write["sha256"]:
                raise ValueError(f"audit digest mismatch: {write['path']}")
    return {"contract_sha256": contract_fingerprint(), "mode": "audit", "status": "ok"}


def detect_project_state(root: Path) -> dict[str, object]:
    """Read Start state, returning repair-block for every present invalid authority."""

    root = Path(root)
    studio_path = root / ".codex/studio.toml"
    authority_state, engine, authority_error = "missing", "unconfigured", None
    if studio_path.exists() or studio_path.is_symlink():
        try:
            engine = load_studio_config(root).engine
            authority_state = "initialized"
        except ValueError:
            authority_state, engine, authority_error = "repair-block", None, "invalid-studio-authority"
    instruction_only, source_suffixes = {"AGENTS.md", ".gitkeep"}, {".gd", ".cs", ".cpp", ".h", ".rs", ".py", ".js", ".ts"}
    source_root, design_root, prototype_root = root / "src", root / "design/gdd", root / "prototypes"
    source_files = [path for path in source_root.rglob("*") if source_root.is_dir() and path.is_file() and path.name not in instruction_only and path.suffix in source_suffixes]
    design_docs = [path for path in design_root.rglob("*.md") if design_root.is_dir() and path.name not in instruction_only]
    prototypes = [path for path in prototype_root.iterdir() if path.is_dir()] if prototype_root.is_dir() else []
    production_files = [path for directory in (root / "production/sprints", root / "production/milestones") if directory.is_dir() for path in directory.rglob("*") if path.is_file() and path.name not in instruction_only]
    return {"engine": engine, "authority_state": authority_state, "authority_error": authority_error, "source_files": source_files, "design_docs": design_docs, "prototypes": prototypes, "production_files": production_files, "fresh": authority_state != "repair-block" and engine == "unconfigured" and not (root / "design/gdd/game-concept.md").is_file() and not source_files and not design_docs and not prototypes and not production_files}


def _validate_first_run(events: Sequence[object], directories: Mapping[str, bool], *, audit: bool) -> None:
    first, typed = _mapping(START_INITIALIZATION_CONTRACT, "first_run"), _event_mappings(events)
    prefix = list(_strings(first, "approval_sequence"))[:-1]
    if [event["type"] for event in typed[:len(prefix)]] != prefix or any(event["type"] != "write" for event in typed[len(prefix):]):
        raise ValueError("first-run events violate the approved ordering")
    changeset = typed[2] if len(typed) >= 3 else None
    if not isinstance(changeset, Mapping) or set(changeset) != {"type", "authority_toml", "actions"}:
        raise ValueError("invalid Initialization changeset schema")
    if changeset["authority_toml"] != START_INITIALIZATION_CONTRACT["default_authority_toml"]:
        raise ValueError("Initialization changeset authority differs from the six-field default")
    actions = _action_mappings(changeset["actions"])
    if not actions or len(actions) > first["max_path_mutations"]:
        raise ValueError("Initialization changeset path-mutation cap is violated")
    _validate_actions(actions, directories, audit=audit)
    default_digest = hashlib.sha256(START_INITIALIZATION_CONTRACT["default_authority_toml"].encode()).hexdigest()
    authority_actions = [action for action in actions if action["path"] == ".codex/studio.toml"]
    if len(authority_actions) != 1 or authority_actions[0]["kind"] != "create" or authority_actions[0]["sha256"] != default_digest:
        raise ValueError("missing authority requires the exact studio.toml create action")
    _reconcile_writes(actions, typed[len(prefix):])


def _validate_initialized(events: Sequence[object], directories: Mapping[str, bool], *, audit: bool) -> None:
    initialized, typed = _mapping(START_INITIALIZATION_CONTRACT, "initialized"), _event_mappings(events)
    if not typed or typed[0] != {"type": "detect"}:
        raise ValueError("initialized repository protocol begins with detection")
    pairs, targets, seen_types, seen_paths, index = _mapping(initialized, "approval_pairs"), _mapping(initialized, "proposal_targets"), set(), set(), 1
    while index < len(typed):
        proposal = typed[index]
        proposal_type = proposal["type"]
        if proposal_type not in pairs or proposal_type in seen_types or set(proposal) != {"type", "actions"}:
            raise ValueError("initialized proposals must be unique recognized action groups")
        if index + 2 >= len(typed) or typed[index + 1] != {"type": pairs[proposal_type]}:
            raise ValueError("initialized proposal lacks its separate approval")
        actions = _action_mappings(proposal["actions"])
        _validate_actions(actions, directories, audit=audit)
        if sum(action["path"] == targets[proposal_type] for action in actions) != 1:
            raise ValueError("initialized proposal lacks its required target action")
        if seen_paths.intersection(action["path"] for action in actions):
            raise ValueError("initialized proposal repeats a mutation path")
        writes = typed[index + 2:index + 2 + len(actions)]
        _reconcile_writes(actions, writes)
        seen_types.add(proposal_type)
        seen_paths.update(action["path"] for action in actions)
        index += 2 + len(actions)
    if not initialized["zero_unapproved_writes"] or not initialized["separate_proposals"]:
        raise ValueError("initialized protocol safety controls are disabled")


def _validate_actions(actions: Sequence[Mapping[str, object]], directories: Mapping[str, bool], *, audit: bool) -> None:
    paths = [_validate_atomic_action(action) for action in actions]
    if len(paths) != len(set(paths)):
        raise ValueError("approved actions must have unique paths")
    for index, action in enumerate(actions):
        path, kind = action["path"], action["kind"]
        if kind != "directory-create":
            continue
        required_by = action["required_by"]
        child_indexes = [child_index for child_index, child in enumerate(actions) if child["path"] == required_by]
        if len(child_indexes) != 1 or child_indexes[0] <= index or actions[child_indexes[0]]["kind"] not in {"create", "merge"}:
            raise ValueError("parent directory must precede one required create or merge child")
        if not audit and directories[path]:
            raise ValueError("parent directory creation is unnecessary because it already exists")
    for index, action in enumerate(actions):
        if action["kind"] not in {"create", "merge"}:
            continue
        parent = PurePosixPath(action["path"]).parent.as_posix()
        if parent in directories and not directories[parent]:
            parents = [item for item in actions[:index] if item["path"] == parent and item["kind"] == "directory-create"]
            if len(parents) != 1:
                raise ValueError("missing observed parent directory action")


def _validate_atomic_action(action: Mapping[str, object]) -> str:
    if not isinstance(action, Mapping):
        raise ValueError("action must be a mapping")
    kind = action.get("kind")
    expected = _DIRECTORY_ACTION_KEYS if kind == "directory-create" else _FILE_ACTION_KEYS
    if set(action) != expected:
        raise ValueError("action has unknown, missing, or hidden fields")
    path, first = _normalized_path(action["path"]), _mapping(START_INITIALIZATION_CONTRACT, "first_run")
    if kind not in _strings(first, "allowed_atomic_kinds") or not isinstance(action["material_change"], str) or not action["material_change"].strip():
        raise ValueError("action kind or material change is invalid")
    if action["form"] != "atomic" or any(token in action["material_change"].casefold() for token in _strings(first, "forbidden_action_forms")):
        raise ValueError("action uses a forbidden bulk or expanded form")
    if action["expanded_paths"] != [path]:
        raise ValueError("action must declare exactly one unexpanded path")
    digest = action["sha256"]
    if kind in {"directory-create", "delete"}:
        if digest is not None:
            raise ValueError("directory and delete actions have no content digest")
    elif not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("file action requires a SHA-256 digest")
    if any(path == root or path.startswith(root + "/") for root in _strings(first, "forbidden_roots")):
        raise ValueError("action targets a forbidden root or descendant")
    if kind == "directory-create":
        if path not in _strings(first, "allowed_parent_directories") or action["required_by"] not in _strings(first, "approved_targets") or not action["required_by"].startswith(path + "/"):
            raise ValueError("directory creation is outside approved scope or speculative")
    elif path not in _strings(first, "approved_targets"):
        raise ValueError("action target is outside selected and approved project authority")
    return path


def _reconcile_writes(actions: Sequence[Mapping[str, object]], writes: Sequence[Mapping[str, object]]) -> None:
    if len(actions) != len(writes):
        raise ValueError("actual writes do not match the approved path-mutation count")
    seen: set[str] = set()
    for action, write in zip(actions, writes, strict=True):
        if not isinstance(write, Mapping) or set(write) != _WRITE_KEYS or write.get("type") != "write":
            raise ValueError("write event has unapproved, missing, or hidden fields")
        if write["path"] in seen or tuple(write[key] for key in ("path", "kind", "material_change", "sha256")) != tuple(action[key] for key in ("path", "kind", "material_change", "sha256")):
            raise ValueError("actual write differs from the approved unique atomic action")
        seen.add(write["path"])


def _writes_from_session(session: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [event for event in _event_mappings(session["events"]) if event["type"] == "write"]


def _directory_observation(value: Mapping[str, bool] | None) -> Mapping[str, bool]:
    first = _mapping(START_INITIALIZATION_CONTRACT, "first_run")
    allowed = set(_strings(first, "allowed_parent_directories"))
    if value is None:
        return {path: True for path in allowed}
    if set(value) != allowed or any(type(present) is not bool for present in value.values()):
        raise ValueError("invalid observed parent-directory state")
    return value


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise ValueError("action path must be a normalized repository-relative path")
    path = PurePosixPath(value)
    if any(part in {".", ".."} for part in path.parts) or path.as_posix() != value or "//" in value or re.search(r"[*?\[\]{}]", value):
        raise ValueError("action path contains traversal, alias, or glob")
    return value


def _event_mappings(events: Sequence[object]) -> list[Mapping[str, object]]:
    if any(not isinstance(event, Mapping) or not isinstance(event.get("type"), str) for event in events):
        raise ValueError("Start events must be typed mappings")
    return list(events)


def _action_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(action, Mapping) for action in value):
        raise ValueError("Start actions must be mappings")
    return list(value)


def _mapping(value: Mapping[str, object], key: str) -> Mapping[str, object]:
    child = value.get(key)
    if not isinstance(child, Mapping):
        raise ValueError(f"Start initialization contract {key} is invalid")
    return child


def _strings(value: Mapping[str, object], key: str) -> tuple[str, ...]:
    child = value.get(key)
    if not isinstance(child, list) or any(not isinstance(item, str) for item in child):
        raise ValueError(f"Start initialization contract {key} is invalid")
    return tuple(child)


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", type=Path, metavar="LEDGER")
    mode.add_argument("--audit", type=Path, metavar="LEDGER")
    parser.add_argument("--project-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        ledger = json.loads((arguments.preflight or arguments.audit).read_text(encoding="utf-8"))
        result = preflight_session(ledger, arguments.project_root) if arguments.preflight else audit_session(ledger, arguments.project_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        print(f"start-initialization: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
