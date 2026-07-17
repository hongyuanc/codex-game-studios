"""Fail-closed plugin-local role resolution and delegation route contracts."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
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
ALLOWED_MODELS = frozenset({"gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"})
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


def _bundle_path(bundle_root: Path, relative: Path) -> Path:
    root = Path(bundle_root).absolute()
    candidate = root / relative
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("role path escapes plugin bundle") from error
    root_metadata = _safe_metadata(root, "plugin bundle root")
    assert root_metadata is not None
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError(f"plugin bundle root is not a directory: {root}")
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        metadata = _safe_metadata(current, "role path ancestor")
        assert metadata is not None
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"role path ancestor is not a directory: {current}")
    return candidate


def _entry_exists(bundle_root: Path, relative: Path) -> bool:
    candidate = _bundle_path(bundle_root, relative)
    metadata = _safe_metadata(candidate, "role candidate", missing_ok=True)
    if metadata is None:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"role candidate is not a regular TOML file: {candidate}")
    return True


def _secure_role_bytes(bundle_root: Path, relative: Path) -> tuple[Path, bytes]:
    candidate = _bundle_path(bundle_root, relative)
    before = _safe_metadata(candidate, "role contract")
    assert before is not None
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"role contract is not a regular TOML file: {candidate}")
    flags = (
        os.O_RDONLY
        | int(getattr(os, "O_BINARY", 0))
        | int(getattr(os, "O_NOFOLLOW", 0))
        | int(getattr(os, "O_CLOEXEC", 0))
        | int(getattr(os, "O_NONBLOCK", 0))
    )
    try:
        descriptor = os.open(candidate, flags)
    except OSError as error:
        raise ValueError(f"cannot securely open role contract: {error}") from error
    try:
        opened = os.fstat(descriptor)
        if _link_kind(opened) or not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"role contract is not a stable regular file: {candidate}")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"role contract changed while opening: {candidate}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = _safe_metadata(candidate, "role contract")
        assert after is not None
        if (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"role contract changed while reading: {candidate}")
        return candidate, b"".join(chunks)
    finally:
        os.close(descriptor)


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
    core_exists = _entry_exists(bundle_root, core_relative)
    active_exists = (
        _entry_exists(bundle_root, active_relative) if active_relative is not None else False
    )
    if core_exists and active_exists:
        raise ValueError(f"ambiguous role contract exists in core and active pack: {role}")
    if core_member:
        relative = core_relative
        source_kind = "core"
    else:
        assert active_relative is not None
        relative = active_relative
        source_kind = active_pack
    path, raw = _secure_role_bytes(bundle_root, relative)
    return _parse_contract(raw, path, role, source_kind)


def decide_route(
    *, native_result: str, default_result: str, model_supported: bool
) -> RouteDecision:
    """Apply the closed native/default/single-agent route state machine."""

    native_states = {"success", "blocked", "absent", "unavailable"}
    default_states = {"success", "blocked", "absent", "unavailable", "not-attempted"}
    if native_result not in native_states or default_result not in default_states:
        raise ValueError("invalid delegation route state")
    if native_result in {"success", "blocked"}:
        return RouteDecision(
            "native", "SUCCESS" if native_result == "success" else "BLOCKED", None
        )
    if not model_supported:
        return RouteDecision("approval-required", "BLOCKED", None)
    if default_result in {"success", "blocked"}:
        return RouteDecision(
            "default", "SUCCESS" if default_result == "success" else "BLOCKED", None
        )
    if default_result in {"absent", "unavailable"}:
        return RouteDecision("single-agent", "FALLBACK", "single-agent fallback")
    raise ValueError("default route has not been attempted")


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
