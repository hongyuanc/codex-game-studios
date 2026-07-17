"""Validate the bounded, approval-gated Start initialization workflow."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Mapping, Sequence


_CONTRACT_JSON = r'''{"authority":{"active_engine_pack":"none","engine":"unconfigured","engine_version":"","language":"","model_policy":"balanced","review_mode":"phase-gated"},"default_authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","first_run":{"action_unit":"filesystem path","allowed_atomic_kinds":["create","modify","merge","delete","directory-create","managed-block-edit"],"allowed_parent_directories":[".codex","production"],"approved_targets":[".codex/studio.toml","production/stage.txt"],"approval_sequence":["detect","select-next-step","initialization-changeset","approval","write"],"forbidden_action_forms":["glob","recursive","tree-copy","bulk"],"forbidden_roots":[".agents/skills",".codex/agents",".codex/agent-packs","Codex Studio Testing Framework","docs/engine-reference"],"initialization_changesets":1,"max_path_mutations":10,"pre_approval_writes":0,"replan_above_max_path_mutations":true,"speculative_empty_directories":false},"initialized":{"approval_pairs":{"review-mode-proposal":"review-mode-approval","stage-proposal":"stage-approval"},"initialization_changesets":0,"proposal_targets":{"review-mode-proposal":".codex/studio.toml","stage-proposal":"production/stage.txt"},"separate_proposals":true,"zero_unapproved_writes":true},"schema_version":1}'''
START_INITIALIZATION_CONTRACT: dict[str, object] = json.loads(_CONTRACT_JSON)


def contract() -> dict[str, object]:
    """Return an isolated copy of the sole Start initialization contract."""

    return copy.deepcopy(START_INITIALIZATION_CONTRACT)


def contract_fingerprint(value: Mapping[str, object] | None = None) -> str:
    """Return the canonical SHA-256 fingerprint for a contract mapping."""

    source = START_INITIALIZATION_CONTRACT if value is None else value
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def contract_summary(value: Mapping[str, object] | None = None) -> str:
    """Render the exact controlling Start prose from the normative contract."""

    source = START_INITIALIZATION_CONTRACT if value is None else value
    first = _mapping(source, "first_run")
    initialized = _mapping(source, "initialized")
    authority = _mapping(source, "authority")
    targets = ", ".join(f"`{target}`" for target in _strings(first, "approved_targets"))
    parents = ", ".join(f"`{directory}`" for directory in _strings(first, "allowed_parent_directories"))
    roots = ", ".join(f"`{root}`" for root in _strings(first, "forbidden_roots"))
    kinds = ", ".join(f"`{kind}`" for kind in _strings(first, "allowed_atomic_kinds"))
    forms = ", ".join(f"`{form}`" for form in _strings(first, "forbidden_action_forms"))
    return "\n".join(
        (
            f"- First run has exactly {first['initialization_changesets']} Initialization changeset and at most {first['max_path_mutations']} path mutations; each mutation is one {first['action_unit']}.",
            f"- The only first-run project-owned file targets are {targets}; directory creation is allowed only for {parents} when required by one of those files, never as a speculative empty directory.",
            f"- Each action has one normalized exact target and material change, uses one of {kinds}, and may not use {forms} or an expanded alias.",
            f"- Forbidden roots and every descendant are {roots}; all other paths are outside the selected and approved project authority.",
            f"- No writes precede approval ({first['pre_approval_writes']}); after approval, writes match the approved actions exactly in order, and a plan above the cap must replan ({first['replan_above_max_path_mutations']}).",
            "- The six-field default authority is " + "; ".join(f"`{key} = {json.dumps(item)}`" for key, item in authority.items()) + ".",
            f"- Initialized repositories have {initialized['initialization_changesets']} Initialization changesets and retain separate stage and review-mode proposals, each with its own approval before its matching write ({initialized['zero_unapproved_writes']}).",
        )
    )


def validate_contract(value: Mapping[str, object]) -> None:
    """Fail closed unless a candidate is exactly the approved contract."""

    if not isinstance(value, Mapping) or contract_fingerprint(value) != contract_fingerprint():
        raise ValueError("Start initialization contract differs from the approved normative source")
    first = _mapping(value, "first_run")
    initialized = _mapping(value, "initialized")
    authority = _mapping(value, "authority")
    if value.get("schema_version") != 1:
        raise ValueError("unsupported Start initialization contract schema")
    if tuple(authority) != (
        "active_engine_pack", "engine", "engine_version", "language", "model_policy", "review_mode"
    ):
        raise ValueError("Start initialization authority must contain six fields")
    if first["action_unit"] != "filesystem path" or first["initialization_changesets"] != 1:
        raise ValueError("invalid first-run action unit or changeset count")
    if first["max_path_mutations"] != 10 or first["pre_approval_writes"] != 0:
        raise ValueError("invalid first-run mutation boundary")
    if first["replan_above_max_path_mutations"] is not True or first["speculative_empty_directories"] is not False:
        raise ValueError("invalid first-run safety controls")
    if tuple(_strings(first, "approval_sequence")) != (
        "detect", "select-next-step", "initialization-changeset", "approval", "write"
    ):
        raise ValueError("invalid first-run approval ordering")
    if initialized["initialization_changesets"] != 0 or initialized["separate_proposals"] is not True:
        raise ValueError("invalid initialized-repository protocol")
    if initialized["zero_unapproved_writes"] is not True:
        raise ValueError("initialized writes must require approval")


def validate_documentation(runtime_text: str, framework_text: str) -> None:
    """Bind both Start documents' contract-derived prose to the production source."""

    validate_contract(START_INITIALIZATION_CONTRACT)
    fingerprint_marker = f"<!-- start-initialization-contract:sha256={contract_fingerprint()} -->"
    summary = contract_summary()
    summary_marker = f"<!-- start-initialization-summary:start\n{summary}\nstart-initialization-summary:end -->"
    for label, text in (("runtime", runtime_text), ("framework", framework_text)):
        if text.count(fingerprint_marker) != 1:
            raise ValueError(f"{label} Start contract fingerprint marker is missing or stale")
        if text.count(summary_marker) != 1:
            raise ValueError(f"{label} Start contract summary is missing or stale")


def validate_session(session: Mapping[str, object]) -> None:
    """Validate a planned Start event ledger before any persistent write occurs."""

    validate_contract(START_INITIALIZATION_CONTRACT)
    state = session.get("authority_state")
    events = session.get("events")
    if state not in {"missing", "initialized"} or not isinstance(events, list):
        raise ValueError("invalid Start session")
    if state == "missing":
        _validate_first_run(events)
    else:
        _validate_initialized(events)


def detect_project_state(root: Path) -> dict[str, object]:
    """Read project state for Start without making persistent changes."""

    root = Path(root)
    studio_path = root / ".codex/studio.toml"
    authority_state = "initialized" if studio_path.is_file() else "missing"
    engine = "unconfigured"
    if authority_state == "initialized":
        import tomllib

        studio = tomllib.loads(studio_path.read_text(encoding="utf-8"))
        engine = studio.get("engine", "unconfigured")
    instruction_only = {"AGENTS.md", ".gitkeep"}
    source_suffixes = {".gd", ".cs", ".cpp", ".h", ".rs", ".py", ".js", ".ts"}
    source_root = root / "src"
    design_root = root / "design/gdd"
    prototype_root = root / "prototypes"
    source_files = [
        path for path in source_root.rglob("*") if source_root.is_dir()
        and path.is_file() and path.name not in instruction_only and path.suffix in source_suffixes
    ]
    design_docs = [
        path for path in design_root.rglob("*.md") if design_root.is_dir()
        and path.name not in instruction_only
    ]
    prototypes = [path for path in prototype_root.iterdir() if path.is_dir()] if prototype_root.is_dir() else []
    production_files = [
        path
        for directory in (root / "production/sprints", root / "production/milestones")
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.is_file() and path.name not in instruction_only
    ]
    return {
        "engine": engine,
        "authority_state": authority_state,
        "source_files": source_files,
        "design_docs": design_docs,
        "prototypes": prototypes,
        "production_files": production_files,
        "fresh": (
            engine == "unconfigured"
            and not (root / "design/gdd/game-concept.md").is_file()
            and not source_files
            and not design_docs
            and not prototypes
            and not production_files
        ),
    }


def _validate_first_run(events: Sequence[object]) -> None:
    first = _mapping(START_INITIALIZATION_CONTRACT, "first_run")
    typed_events = _event_mappings(events)
    changesets = [event for event in typed_events if event["type"] == "initialization-changeset"]
    if len(changesets) != first["initialization_changesets"]:
        raise ValueError("missing authority requires exactly one Initialization changeset")
    if sum(event["type"] == "write" for event in typed_events) < 1:
        raise ValueError("Initialization changeset must produce its approved writes")
    sequence = [event["type"] for event in typed_events]
    prefix = list(_strings(first, "approval_sequence"))[:-1]
    if sequence[: len(prefix)] != prefix or any(kind != "write" for kind in sequence[len(prefix):]):
        raise ValueError("first-run events violate the approved ordering")
    approval_index = len(prefix) - 1
    if sum(event["type"] == "write" for event in typed_events[:approval_index]) != first["pre_approval_writes"]:
        raise ValueError("first-run writes occurred before approval")
    changeset = changesets[0]
    if changeset.get("authority_toml") != START_INITIALIZATION_CONTRACT["default_authority_toml"]:
        raise ValueError("Initialization changeset authority differs from the six-field default")
    actions = _action_mappings(changeset.get("actions"))
    if not actions or len(actions) > first["max_path_mutations"]:
        raise ValueError("Initialization changeset path-mutation cap is violated")
    for action in actions:
        _validate_atomic_action(action, actions, first)
    writes = typed_events[len(prefix):]
    _reconcile_writes(actions, writes)


def _validate_initialized(events: Sequence[object]) -> None:
    initialized = _mapping(START_INITIALIZATION_CONTRACT, "initialized")
    typed_events = _event_mappings(events)
    if any(event["type"] == "initialization-changeset" for event in typed_events):
        raise ValueError("initialized repositories must not receive Initialization changesets")
    if not typed_events or typed_events[0]["type"] != "detect":
        raise ValueError("initialized repository protocol begins with detection")
    proposals = _mapping(initialized, "approval_pairs")
    targets = _mapping(initialized, "proposal_targets")
    approved_actions: list[Mapping[str, object]] = []
    index = 1
    while index < len(typed_events):
        proposal = typed_events[index]
        proposal_type = proposal["type"]
        if proposal_type not in proposals:
            raise ValueError("initialized repositories require a separate recognized proposal")
        approval_type = proposals[proposal_type]
        if index + 1 >= len(typed_events) or typed_events[index + 1]["type"] != approval_type:
            raise ValueError("initialized proposal lacks its separate approval")
        action = proposal.get("action")
        if not isinstance(action, Mapping):
            raise ValueError("initialized proposal lacks one approved atomic action")
        _validate_atomic_action(action, [action], _mapping(START_INITIALIZATION_CONTRACT, "first_run"))
        if action["path"] != targets[proposal_type]:
            raise ValueError("initialized proposal targets the wrong project artifact")
        if index + 2 >= len(typed_events) or typed_events[index + 2]["type"] != "write":
            raise ValueError("initialized approval must be followed by its matching write")
        _reconcile_writes([action], [typed_events[index + 2]])
        approved_actions.append(action)
        index += 3
    if not initialized["zero_unapproved_writes"] or not initialized["separate_proposals"]:
        raise ValueError("initialized protocol safety controls are disabled")


def _validate_atomic_action(
    action: Mapping[str, object], actions: Sequence[Mapping[str, object]], first: Mapping[str, object]
) -> None:
    path = _normalized_path(action.get("path"))
    kind = action.get("kind")
    material_change = action.get("material_change")
    form = action.get("form")
    expanded_paths = action.get("expanded_paths")
    if kind not in _strings(first, "allowed_atomic_kinds"):
        raise ValueError("action kind is not an allowed atomic mutation")
    if not isinstance(material_change, str) or not material_change.strip():
        raise ValueError("action requires a material change")
    forbidden_forms = set(_strings(first, "forbidden_action_forms"))
    if form != "atomic" or any(token in material_change.casefold() for token in forbidden_forms):
        raise ValueError("action uses a forbidden bulk or expanded form")
    if not isinstance(expanded_paths, list) or expanded_paths != [path]:
        raise ValueError("action must declare exactly one unexpanded path")
    forbidden_roots = _strings(first, "forbidden_roots")
    if any(path == root or path.startswith(root + "/") for root in forbidden_roots):
        raise ValueError("action targets a forbidden root or descendant")
    targets = _strings(first, "approved_targets")
    directories = _strings(first, "allowed_parent_directories")
    if kind == "directory-create":
        if path not in directories:
            raise ValueError("directory creation is outside the approved project scope")
        required_by = action.get("required_by")
        if not isinstance(required_by, str) or required_by not in targets or not required_by.startswith(path + "/"):
            raise ValueError("speculative empty directory creation is forbidden")
        if not any(other.get("path") == required_by for other in actions):
            raise ValueError("directory creation requires its approved child action")
    elif path not in targets:
        raise ValueError("action target is outside selected and approved project authority")


def _reconcile_writes(actions: Sequence[Mapping[str, object]], writes: Sequence[Mapping[str, object]]) -> None:
    if len(actions) != len(writes):
        raise ValueError("actual writes do not match the approved path-mutation count")
    for action, write in zip(actions, writes, strict=True):
        if set(write) != {"type", "path", "kind", "material_change"}:
            raise ValueError("write event has unapproved or hidden fields")
        if write["type"] != "write":
            raise ValueError("approved action did not reconcile to a write")
        if tuple(write[key] for key in ("path", "kind", "material_change")) != tuple(
            action[key] for key in ("path", "kind", "material_change")
        ):
            raise ValueError("actual write differs from the approved atomic action")


def _normalized_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise ValueError("action path must be a normalized repository-relative path")
    path = PurePosixPath(value)
    if any(part in {".", ".."} for part in path.parts) or path.as_posix() != value or "//" in value:
        raise ValueError("action path contains traversal or an alias")
    if re.search(r"[*?\[\]{}]", value):
        raise ValueError("action path must not be a glob")
    return value


def _event_mappings(events: Sequence[object]) -> list[Mapping[str, object]]:
    result: list[Mapping[str, object]] = []
    for event in events:
        if not isinstance(event, Mapping) or not isinstance(event.get("type"), str):
            raise ValueError("Start events must be typed mappings")
        result.append(event)
    return result


def _action_mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(action, Mapping) for action in value):
        raise ValueError("Initialization changeset actions must be mappings")
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
