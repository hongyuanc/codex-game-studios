from __future__ import annotations

import ast
import argparse
import collections
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import sys
import tomllib


ALLOWED_MODELS = {"gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"}
ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh"}
REQUIRED_AGENT_FIELDS = {"name", "description", "developer_instructions", "model", "model_reasoning_effort"}
EXPECTED_CORE_NAMES = set("""accessibility-specialist ai-programmer analytics-engineer art-director
audio-director community-manager creative-director devops-engineer economy-designer
engine-programmer game-designer gameplay-programmer lead-programmer level-designer
live-ops-designer localization-lead narrative-director network-programmer
performance-analyst producer prototyper qa-lead qa-tester release-manager
security-engineer sound-designer systems-designer technical-artist technical-director
tools-programmer ui-programmer ux-designer world-builder writer""".split())
EXPECTED_PACK_NAMES = {
    "godot": set("""godot-csharp-specialist godot-gdextension-specialist
        godot-gdscript-specialist godot-shader-specialist godot-specialist""".split()),
    "unity": set("""unity-addressables-specialist unity-dots-specialist
        unity-shader-specialist unity-specialist unity-ui-specialist""".split()),
    "unreal": set("""ue-blueprint-specialist ue-gas-specialist
        ue-replication-specialist ue-umg-specialist unreal-specialist""".split()),
}
EXPECTED_SKILL_NAMES = set("""adopt architecture-decision architecture-review art-bible asset-audit
asset-spec balance-check brainstorm bug-report bug-triage changelog code-review
consistency-check content-audit create-architecture create-control-manifest
create-epics create-stories day-one-patch design-review design-system dev-story
estimate gate-check help hotfix launch-checklist localize map-systems milestone-review
onboard patch-notes perf-profile playtest-report project-stage-detect
propagate-design-change prototype qa-plan quick-design regression-suite
release-checklist retrospective reverse-document review-all-gdds scope-check
security-audit setup-engine skill-improve skill-test smoke-check soak-test sprint-plan
sprint-status start story-done story-readiness team-audio team-combat team-level
team-live-ops team-narrative team-polish team-qa team-release team-ui tech-debt
test-evidence-review test-flakiness test-helpers test-setup ux-design ux-review
vertical-slice""".split())
FORBIDDEN_SKILL_PATTERNS = {
    r"\bAskUserQuestion\b": "Claude interaction primitive",
    r"\bTodoWrite\b": "Claude task primitive",
    r"\bTask tool\b|\bsubagent_type\b": "Claude delegation primitive",
    r"(?i:\bTask calls?\b|\btask-call(?:s|ing)?\b)": "non-native task-call syntax",
    r"\.Codex/|\.claude/": "non-native path",
    r"^model:\s*(opus|sonnet|haiku)\s*$": "Claude model metadata",
    r"^allowed-tools:": "Claude tool metadata",
    r"^agent:": "Claude agent metadata",
    r"^maxTurns:": "Claude turn-limit metadata",
}
SUPPORTED_HOOK_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "PostCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}
EXPECTED_EVENT_ACTIONS = {
    "SessionStart": ("session-start", "detect-gaps"),
    "PreToolUse": ("validate-command",),
    "PostToolUse": ("validate-assets", "validate-skill-change"),
    "PreCompact": ("pre-compact",),
    "PostCompact": ("post-compact",),
    "SubagentStart": ("subagent-start",),
    "SubagentStop": ("subagent-stop",),
    "Stop": ("session-stop",),
}
EXPECTED_HOOK_MATCHERS = {
    "SessionStart": "startup|resume|clear|compact",
    "PreToolUse": "Bash",
    "PostToolUse": "Edit|Write|apply_patch",
    "PreCompact": "auto|manual",
    "PostCompact": "auto|manual",
    "SubagentStart": "",
    "SubagentStop": "",
    "Stop": None,
}
ALLOWED_GROUP_FIELDS = {"matcher", "hooks"}
ALLOWED_HANDLER_FIELDS = {"type", "command", "commandWindows", "timeout"}
REQUIRED_DOCS = {
    "agent-coordination-map.md",
    "agent-roster.md",
    "coding-standards.md",
    "context-management.md",
    "coordination-rules.md",
    "director-gates.md",
    "directory-structure.md",
    "hooks-reference.md",
    "quick-start.md",
    "review-workflow.md",
    "rules-reference.md",
    "setup-requirements.md",
    "skills-reference.md",
    "technical-preferences.md",
    "workflow-catalog.yaml",
}
EXPECTED_TEMPLATE_PATHS = set("""accessibility-requirements.md architecture-decision-record.md
architecture-doc-from-code.md architecture-traceability.md art-bible.md
changelog-template.md collaborative-protocols/design-agent-protocol.md
collaborative-protocols/implementation-agent-protocol.md
collaborative-protocols/leadership-agent-protocol.md concept-doc-from-prototype.md
design-doc-from-implementation.md difficulty-curve.md economy-model.md faction-design.md
game-concept.md game-design-document.md game-pillars.md hud-design.md incident-response.md
interaction-pattern-library.md level-design-document.md milestone-definition.md
narrative-character-sheet.md pitch-document.md player-journey.md post-mortem.md
project-stage-report.md prototype-report.md release-checklist-template.md release-notes.md
risk-register-entry.md skill-test-spec.md sound-bible.md sprint-plan.md systems-index.md
technical-design-document.md test-evidence.md test-plan.md ux-spec.md
vertical-slice-report.md""".split())
EXPECTED_INSTRUCTION_PATHS = {
    "assets/data/AGENTS.md",
    "assets/shaders/AGENTS.md",
    "design/gdd/AGENTS.md",
    "design/narrative/AGENTS.md",
    "prototypes/AGENTS.md",
    "src/ai/AGENTS.md",
    "src/core/AGENTS.md",
    "src/gameplay/AGENTS.md",
    "src/networking/AGENTS.md",
    "src/ui/AGENTS.md",
    "tests/AGENTS.md",
}
RUNTIME_FORBIDDEN_PATTERNS = {
    r"CLAUDE\.md": "legacy durable-guidance filename",
    r"\.claude/": "legacy runtime path",
    r"\.Codex/": "incorrect Codex path casing",
    r"\bAskUserQuestion\b": "legacy interaction primitive",
    r"(?i:\bTask calls?\b|\bTask tool\b)": "legacy delegation primitive",
    r"\bsubagent_type\b": "legacy agent metadata",
    r"(?m)^\s*(?:allowed-tools|argument-hint|user-invocable)\s*:": "legacy metadata",
    r"\bclaude-(?:opus|sonnet|haiku)[-\w.]*\b": "legacy model identifier",
    r"\bAnthropic\b": "legacy runtime routing",
    r"\bClaude(?: Code)?\b": "legacy runtime product name",
}
MACHINE_PATH = re.compile(r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])")
COVERAGE_ENTRY_COUNT = 203
COVERAGE_SOURCE_SET_SHA256 = "37580b38a3b505292d524d4432239ff571741fb9ace8787544ec6643e34feef0"
COVERAGE_CONTRACT_SHA256 = "899296b2dbb4553303606dad787912d834bc81beba6c9e0a8bc44cf15d149cde"
FRAMEWORK_PARITY_COUNT = 127
FRAMEWORK_PARITY_SHA256 = "64c28b7715ddf487e3e63325fcf561e2b5953a71203dd71a08286f27799f37a4"


@dataclasses.dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


def _read_utf8_file(path: pathlib.Path, label: str) -> tuple[str | None, list[ValidationIssue]]:
    if path.is_symlink():
        return None, [ValidationIssue("error", str(path), f"{label} must not be a symlink")]
    try:
        if not path.is_file():
            return None, [ValidationIssue("error", str(path), f"{label} must be a regular file")]
        data = path.read_bytes()
    except OSError as error:
        return None, [ValidationIssue("error", str(path), f"cannot read {label}: {error}")]
    if b"\x00" in data:
        return None, [ValidationIssue("error", str(path), f"{label} contains NUL bytes")]
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError as error:
        return None, [ValidationIssue("error", str(path), f"{label} is not valid UTF-8: {error}")]


def validate_agent(path: pathlib.Path) -> list[ValidationIssue]:
    text, issues = _read_utf8_file(path, "agent profile")
    if text is None:
        return issues
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return [ValidationIssue("error", str(path), f"invalid TOML: {error}")]
    if set(data) != REQUIRED_AGENT_FIELDS:
        issues.append(
            ValidationIssue(
                "error", str(path),
                f"agent fields must be exactly {sorted(REQUIRED_AGENT_FIELDS)}, got {sorted(data)}",
            )
        )
    for field in sorted(REQUIRED_AGENT_FIELDS - set(data)):
        issues.append(ValidationIssue("error", str(path), f"missing required field: {field}"))
    if isinstance(data.get("name"), str) and data["name"] != path.stem:
        issues.append(ValidationIssue("error", str(path), "agent name must match profile filename"))
    if "model" in data and data["model"] not in ALLOWED_MODELS:
        issues.append(ValidationIssue("error", str(path), f"unsupported model: {data['model']}"))
    if "model_reasoning_effort" in data and data["model_reasoning_effort"] not in ALLOWED_EFFORTS:
        issues.append(ValidationIssue("error", str(path), f"unsupported reasoning effort: {data['model_reasoning_effort']}"))
    return issues


def validate_skill(path: pathlib.Path) -> list[ValidationIssue]:
    text, issues = _read_utf8_file(path, "skill file")
    if text is None:
        return issues
    fields: dict[str, str] = {}
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        issues.append(ValidationIssue("error", str(path), "missing YAML frontmatter"))
        frontmatter = ""
    else:
        frontmatter = text.split("---\n", 2)[1]
    malformed = False
    for line in frontmatter.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9_-]*):\s*(.+)", line)
        if not match or match.group(1) in fields:
            malformed = True
            continue
        fields[match.group(1)] = match.group(2).strip().strip('"')
    if malformed or set(fields) != {"name", "description"}:
        issues.append(
            ValidationIssue(
                "error", str(path),
                f"skill frontmatter fields must be exactly ['description', 'name'], got {sorted(fields)}",
            )
        )
    if fields.get("name") != path.parent.name:
        issues.append(ValidationIssue("error", str(path), "skill name must match directory name"))
    if "description" in fields and not fields["description"].strip():
        issues.append(ValidationIssue("error", str(path), "skill description must not be blank"))
    for pattern, label in FORBIDDEN_SKILL_PATTERNS.items():
        if re.search(pattern, text, flags=re.MULTILINE):
            issues.append(ValidationIssue("error", str(path), f"contains {label}"))
    return issues


def _runtime_hook_contract(root: pathlib.Path) -> tuple[set[str], set[str]]:
    runner = root / ".codex/hooks/hook_runner.py"
    text, issues = _read_utf8_file(runner, "hook runner")
    if text is None:
        raise OSError("; ".join(issue.message for issue in issues))
    tree = ast.parse(text, filename=str(runner))
    actions: set[str] = set()
    handlers: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if "ACTIONS" in names:
                actions = set(ast.literal_eval(node.value))
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "HANDLERS" and isinstance(node.value, ast.Dict):
                handlers = {ast.literal_eval(key) for key in node.value.keys}
    return actions, handlers


def _posix_hook_action(command: str) -> str | None:
    match = re.fullmatch(
        r'python3 "\$\(git rev-parse --show-toplevel\)/\.codex/hooks/hook_runner\.py" ([a-z][a-z-]*)',
        command,
    )
    return match.group(1) if match else None


def _windows_hook_action(command: str) -> str | None:
    prefix = (
        "powershell -NoProfile -Command \"$root = git rev-parse --show-toplevel; "
        "py -3 ($root + '/.codex/hooks/hook_runner.py') "
    )
    match = re.fullmatch(re.escape(prefix) + r"([a-z][a-z-]*)" + re.escape('"'), command)
    return match.group(1) if match else None


def validate_hooks(path: pathlib.Path, root: pathlib.Path | None = None) -> list[ValidationIssue]:
    text, issues = _read_utf8_file(path, "hook configuration")
    if text is None:
        return issues
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return [ValidationIssue("error", str(path), f"invalid JSON: {error}")]

    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return [ValidationIssue("error", str(path), "missing hooks object")]

    try:
        runtime_root = root.resolve() if root is not None else pathlib.Path(__file__).resolve().parents[2]
        runtime_actions, runtime_handlers = _runtime_hook_contract(runtime_root)
    except (OSError, SyntaxError, ValueError) as error:
        issues.append(ValidationIssue("error", str(path), f"cannot load hook runner contract: {error}"))
        runtime_actions, runtime_handlers = set(), set()
    if runtime_actions != runtime_handlers:
        issues.append(
            ValidationIssue(
                "error",
                str(path),
                "runner ACTIONS and HANDLERS are not in parity",
            )
        )

    configured: list[tuple[str, str]] = []
    for event, groups in hooks.items():
        if event not in SUPPORTED_HOOK_EVENTS:
            issues.append(ValidationIssue("error", str(path), f"unsupported hook event: {event}"))
        if not isinstance(groups, list):
            issues.append(ValidationIssue("error", str(path), f"hook event {event} must contain a list"))
            continue
        for group_index, group in enumerate(groups):
            handlers = group.get("hooks") if isinstance(group, dict) else None
            location = f"{event} group {group_index}"
            if isinstance(group, dict):
                extra_group_fields = set(group) - ALLOWED_GROUP_FIELDS
                if extra_group_fields:
                    issues.append(
                        ValidationIssue(
                            "error",
                            str(path),
                            f"{location} has unsupported group fields: {sorted(extra_group_fields)}",
                        )
                    )
                matcher = group.get("matcher")
                if matcher is not None and not isinstance(matcher, str):
                    issues.append(ValidationIssue("error", str(path), f"{location} matcher must be a string"))
                if isinstance(matcher, str):
                    try:
                        re.compile(matcher)
                    except re.error as error:
                        issues.append(ValidationIssue("error", str(path), f"{location} has invalid matcher regex: {error}"))
                expected_matcher = EXPECTED_HOOK_MATCHERS.get(event)
                if matcher != expected_matcher:
                    issues.append(
                        ValidationIssue(
                            "error",
                            str(path),
                            f"{location} expected matcher {expected_matcher!r}, got {matcher!r}",
                        )
                    )
            if not isinstance(handlers, list) or not handlers:
                issues.append(
                    ValidationIssue(
                        "error",
                        str(path),
                        f"hook event {event} group {group_index} has no handlers",
                    )
                )
                continue
            for handler_index, handler in enumerate(handlers):
                location = f"{event} group {group_index} handler {handler_index}"
                if not isinstance(handler, dict):
                    issues.append(ValidationIssue("error", str(path), f"{location} must be an object"))
                    continue
                extra_handler_fields = set(handler) - ALLOWED_HANDLER_FIELDS
                if extra_handler_fields:
                    issues.append(
                        ValidationIssue(
                            "error",
                            str(path),
                            f"{location} has unsupported handler fields: {sorted(extra_handler_fields)}",
                        )
                    )
                if handler.get("type") != "command":
                    issues.append(
                        ValidationIssue(
                            "error",
                            str(path),
                            f"{location} has unsupported handler type: {handler.get('type')}",
                        )
                    )
                command = handler.get("command")
                windows = handler.get("commandWindows")
                if not isinstance(command, str) or not command.strip():
                    issues.append(ValidationIssue("error", str(path), f"{location} missing command"))
                    command = ""
                if not isinstance(windows, str) or not windows.strip():
                    issues.append(
                        ValidationIssue("error", str(path), f"{location} missing Windows command override")
                    )
                    windows = ""
                timeout = handler.get("timeout")
                if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
                    issues.append(
                        ValidationIssue(
                            "error",
                            str(path),
                            f"{location} timeout must be a positive integer",
                        )
                    )
                combined = f"{command}\n{windows}"
                if re.search(r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])", combined):
                    issues.append(ValidationIssue("error", str(path), f"{location} contains absolute user path"))
                if ".codex/hooks/hook_runner.py" not in command:
                    issues.append(ValidationIssue("error", str(path), f"{location} command must reference .codex/hooks/hook_runner.py"))
                if windows and ".codex/hooks/hook_runner.py" not in windows:
                    issues.append(ValidationIssue("error", str(path), f"{location} Windows command must reference .codex/hooks/hook_runner.py"))
                if "$(git rev-parse --show-toplevel)/.codex/hooks/hook_runner.py" not in command:
                    issues.append(ValidationIssue("error", str(path), f"{location} must use a repository-root runner invocation"))
                if windows and "git rev-parse --show-toplevel" not in windows:
                    issues.append(ValidationIssue("error", str(path), f"{location} Windows command must use a repository-root runner invocation"))
                posix_action = _posix_hook_action(command)
                windows_action = _windows_hook_action(windows)
                if posix_action is None:
                    issues.append(ValidationIssue("error", str(path), f"{location} has invalid runner invocation"))
                if windows and windows_action is None:
                    issues.append(ValidationIssue("error", str(path), f"{location} has invalid Windows runner invocation"))
                if posix_action and windows_action and posix_action != windows_action:
                    issues.append(ValidationIssue("error", str(path), f"{location} POSIX and Windows actions differ"))
                action = posix_action or windows_action
                if action:
                    configured.append((event, action))

    configured_actions = [action for _event, action in configured]
    counts = collections.Counter(configured_actions)
    duplicates = sorted(action for action, count in counts.items() if count > 1)
    if duplicates:
        issues.append(ValidationIssue("error", str(path), f"duplicate hook action: {duplicates}"))
    missing = sorted(runtime_actions - set(configured_actions))
    if missing:
        issues.append(ValidationIssue("error", str(path), f"missing required hook actions: {missing}"))
    unknown = sorted(set(configured_actions) - runtime_actions)
    if unknown:
        issues.append(ValidationIssue("error", str(path), f"unknown configured hook actions: {unknown}"))
    if set(configured_actions) != runtime_handlers:
        issues.append(ValidationIssue("error", str(path), "configured actions are not in parity with runner HANDLERS"))
    for event, expected in EXPECTED_EVENT_ACTIONS.items():
        actual = tuple(action for configured_event, action in configured if configured_event == event)
        if actual != expected:
            issues.append(
                ValidationIssue(
                    "error",
                    str(path),
                    f"event action mapping for {event} must be {expected}, got {actual}",
                )
            )
    return issues


def _relative(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _profile_name(path: pathlib.Path) -> str | None:
    text, issues = _read_utf8_file(path, "agent profile")
    if text is None or issues:
        return None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return None
    name = data.get("name")
    return name if isinstance(name, str) else None


def validate_repository_counts(root: pathlib.Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for relative in (".codex", ".codex/agents", ".codex/agent-packs", ".agents", ".agents/skills"):
        path = root / relative
        if path.is_symlink():
            issues.append(ValidationIssue("error", relative, "runtime directory must not be a symlink"))
    core = sorted((root / ".codex/agents").glob("*.toml"))
    packed = sorted((root / ".codex/agent-packs").glob("*/*.toml"))
    skills = sorted((root / ".agents/skills").glob("*/SKILL.md"))

    def require_count(label: str, paths: list[pathlib.Path], expected: int) -> None:
        if len(paths) != expected:
            issues.append(
                ValidationIssue(
                    "error", label, f"expected {expected} files, found {len(paths)}"
                )
            )

    require_count(".codex/agents", core, 34)
    require_count(".codex/agent-packs", packed, 15)
    require_count(".agents/skills", skills, 73)
    core_files = {path.stem for path in core}
    core_entries = {
        path.name for path in (root / ".codex/agents").iterdir()
        if path.is_file() or path.is_symlink()
    } if (root / ".codex/agents").is_dir() else set()
    expected_core_entries = {f"{name}.toml" for name in EXPECTED_CORE_NAMES}
    if core_entries != expected_core_entries:
        issues.append(
            ValidationIssue("error", ".codex/agents", f"approved core profile files differ; missing={sorted(expected_core_entries - core_entries)}, extra={sorted(core_entries - expected_core_entries)}")
        )
    if core_files != EXPECTED_CORE_NAMES:
        issues.append(
            ValidationIssue(
                "error", ".codex/agents",
                f"approved core agent identities differ; missing={sorted(EXPECTED_CORE_NAMES - core_files)}, extra={sorted(core_files - EXPECTED_CORE_NAMES)}",
            )
        )
    names = [_profile_name(path) for path in [*core, *packed]]
    expected_all = EXPECTED_CORE_NAMES | set().union(*EXPECTED_PACK_NAMES.values())
    if None not in names and set(names) != expected_all:
        issues.append(
            ValidationIssue("error", ".codex", "agent roster identities do not match the approved 49 roles")
        )
    elif None in names:
        issues.append(ValidationIssue("error", ".codex", "agent profile is missing a name"))

    pack_root = root / ".codex/agent-packs"
    pack_names = {path.name for path in pack_root.iterdir() if path.is_dir()} if pack_root.is_dir() else set()
    if pack_names != {"godot", "unity", "unreal"}:
        issues.append(
            ValidationIssue("error", ".codex/agent-packs", f"expected Godot, Unity, and Unreal packs, found {sorted(pack_names)}")
        )
    for engine in ("godot", "unity", "unreal"):
        identities = {path.stem for path in (pack_root / engine).glob("*.toml")}
        entries = {
            path.name for path in (pack_root / engine).iterdir()
            if path.is_file() or path.is_symlink()
        } if (pack_root / engine).is_dir() else set()
        expected_entries = {f"{name}.toml" for name in EXPECTED_PACK_NAMES[engine]}
        if entries != expected_entries:
            issues.append(
                ValidationIssue("error", f".codex/agent-packs/{engine}", f"approved packed profile files differ; missing={sorted(expected_entries - entries)}, extra={sorted(entries - expected_entries)}")
            )
        if identities != EXPECTED_PACK_NAMES[engine]:
            issues.append(
                ValidationIssue(
                    "error", f".codex/agent-packs/{engine}",
                    f"approved packed identities differ; missing={sorted(EXPECTED_PACK_NAMES[engine] - identities)}, extra={sorted(identities - EXPECTED_PACK_NAMES[engine])}",
                )
            )

    skill_names = {path.parent.name for path in skills}
    if skill_names != EXPECTED_SKILL_NAMES:
        issues.append(
            ValidationIssue(
                "error", ".agents/skills",
                f"approved skill identities differ; missing={sorted(EXPECTED_SKILL_NAMES - skill_names)}, extra={sorted(skill_names - EXPECTED_SKILL_NAMES)}",
            )
        )

    studio_path = root / ".codex/studio.toml"
    try:
        studio = tomllib.loads(studio_path.read_text(encoding="utf-8"))
        if studio.get("engine") != "unconfigured" or studio.get("active_engine_pack") != "none":
            issues.append(
                ValidationIssue("error", ".codex/studio.toml", "template must remain unconfigured with no active engine pack")
            )
    except (OSError, tomllib.TOMLDecodeError) as error:
        issues.append(ValidationIssue("error", ".codex/studio.toml", f"invalid studio configuration: {error}"))

    instructions = {
        _relative(root, path)
        for path in root.rglob("AGENTS.md")
        if path != root / "AGENTS.md" and "Codex Studio Testing Framework" not in path.parts
    }
    if instructions != EXPECTED_INSTRUCTION_PATHS:
        issues.append(
            ValidationIssue(
                "error",
                "AGENTS.md",
                f"expected 11 nested instruction boundaries; missing={sorted(EXPECTED_INSTRUCTION_PATHS - instructions)}, extra={sorted(instructions - EXPECTED_INSTRUCTION_PATHS)}",
            )
        )

    docs = root / ".codex/docs"
    actual_docs = {path.name for path in docs.iterdir() if path.is_file()} if docs.is_dir() else set()
    if actual_docs != REQUIRED_DOCS:
        issues.append(
            ValidationIssue("error", ".codex/docs", f"approved documents differ; missing={sorted(REQUIRED_DOCS - actual_docs)}, extra={sorted(actual_docs - REQUIRED_DOCS)}")
        )
    templates = {
        path.relative_to(docs / "templates").as_posix()
        for path in (docs / "templates").rglob("*") if path.is_file()
    } if (docs / "templates").is_dir() else set()
    if templates != EXPECTED_TEMPLATE_PATHS:
        issues.append(
            ValidationIssue("error", ".codex/docs/templates", f"approved templates differ; missing={sorted(EXPECTED_TEMPLATE_PATHS - templates)}, extra={sorted(templates - EXPECTED_TEMPLATE_PATHS)}")
        )
    return issues


def _coverage_entries(path: pathlib.Path) -> tuple[list[dict[str, str]], list[ValidationIssue]]:
    text, issues = _read_utf8_file(path, "coverage manifest")
    if text is None:
        return [], issues
    lines = text.splitlines()
    if len(lines) < 2 or lines[0] != "version: 1" or lines[1] != "entries:":
        issues.append(ValidationIssue("error", str(path), "coverage manifest must declare exactly version 1 and entries"))
        return [], issues
    body = lines[2:]
    if len(body) % 4:
        issues.append(ValidationIssue("error", str(path), "coverage entries must use the exact four-line schema"))
    entries: list[dict[str, str]] = []
    for index in range(0, len(body) - len(body) % 4, 4):
        chunk = body[index:index + 4]
        matches = (
            re.fullmatch(r"  - source: (\S.*)", chunk[0]),
            re.fullmatch(r"    destination: (\S.*)", chunk[1]),
            re.fullmatch(r"    action: (migrate|remove)", chunk[2]),
            re.fullmatch(r"    reason: (\S.*)", chunk[3]),
        )
        if not all(matches):
            issues.append(ValidationIssue("error", str(path), f"malformed coverage entry at body line {index + 1}"))
            continue
        entries.append(
            {
                "source": matches[0].group(1),
                "destination": matches[1].group(1),
                "action": matches[2].group(1),
                "reason": matches[3].group(1),
            }
        )
    return entries, issues


def _safe_relative_path(value: str) -> bool:
    path = pathlib.PurePosixPath(value)
    return bool(value) and not path.is_absolute() and "\\" not in value and all(part not in {"", ".", ".."} for part in path.parts)


def _contained_regular_file(root: pathlib.Path, relative: str) -> tuple[bool, str]:
    if not _safe_relative_path(relative):
        return False, "path is not a safe repository-relative path"
    candidate = root / relative
    if candidate.is_symlink():
        return False, "destination must not be a symlink"
    current = candidate.parent
    while current != root and current != current.parent:
        if current.is_symlink():
            return False, "destination parent must not be a symlink"
        current = current.parent
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False, "destination must exist inside the repository"
    if not candidate.is_file():
        return False, "destination must be a regular file"
    return True, ""


def _legacy_sources(root: pathlib.Path) -> set[str]:
    sources = {
        _relative(root, path)
        for path in (root / ".claude").rglob("*")
        if path.is_file()
    } if (root / ".claude").is_dir() else set()
    sources.update(_relative(root, path) for path in root.rglob("CLAUDE.md"))
    return sources


def validate_coverage_manifest(root: pathlib.Path, phase: str) -> list[ValidationIssue]:
    manifest = root / "production/migration/claude-to-codex-coverage.yaml"
    entries, issues = _coverage_entries(manifest)
    if issues:
        return issues
    canonical_entries = sorted(entries, key=lambda entry: entry["source"])
    source_digest = hashlib.sha256(
        "\n".join(entry["source"] for entry in canonical_entries).encode("utf-8")
    ).hexdigest()
    contract_digest = hashlib.sha256(
        json.dumps(canonical_entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if len(entries) != COVERAGE_ENTRY_COUNT:
        issues.append(ValidationIssue("error", _relative(root, manifest), f"coverage must contain exactly {COVERAGE_ENTRY_COUNT} entries, found {len(entries)}"))
    if source_digest != COVERAGE_SOURCE_SET_SHA256:
        issues.append(ValidationIssue("error", _relative(root, manifest), "approved coverage source-set digest does not match"))
    if contract_digest != COVERAGE_CONTRACT_SHA256:
        issues.append(ValidationIssue("error", _relative(root, manifest), "approved coverage contract digest does not match"))
    seen: set[str] = set()
    for entry in entries:
        source = entry.get("source", "")
        if not _safe_relative_path(source):
            issues.append(ValidationIssue("error", source or _relative(root, manifest), "coverage source is not a safe repository-relative path"))
        if not source or source in seen:
            issues.append(ValidationIssue("error", _relative(root, manifest), f"duplicate or blank source: {source!r}"))
        seen.add(source)
        destination = entry.get("destination", "")
        action = entry.get("action", "")
        reason = entry.get("reason", "")
        if not reason:
            issues.append(ValidationIssue("error", source, "coverage reason is blank"))
        if action == "migrate":
            valid, message = _contained_regular_file(root, destination)
            if not valid:
                issues.append(ValidationIssue("error", source, f"invalid migration destination {destination!r}: {message}"))
        elif action == "remove":
            if destination != "remove-without-replacement":
                issues.append(ValidationIssue("error", source, "remove action must use remove-without-replacement"))
        else:
            issues.append(ValidationIssue("error", source, f"unsupported coverage action: {action}"))

    actual = _legacy_sources(root)
    if phase == "pre-cleanup":
        if actual != seen:
            issues.append(
                ValidationIssue(
                    "error", _relative(root, manifest),
                    f"coverage does not match legacy inventory; missing={sorted(actual - seen)}, extra={sorted(seen - actual)}",
                )
            )
    elif phase == "final":
        remaining = sorted(source for source in seen if (root / source).exists())
        if remaining:
            issues.append(ValidationIssue("error", _relative(root, manifest), f"legacy source remains: {remaining}"))
        if actual:
            issues.append(ValidationIssue("error", ".", f"legacy source remains: {sorted(actual)}"))
        for relative in (".claude", "CCGS Skill Testing Framework"):
            path = root / relative
            if path.exists() or path.is_symlink():
                issues.append(ValidationIssue("error", relative, "legacy directory remains"))
    return issues


def validate_testing_framework_parity(root: pathlib.Path) -> list[ValidationIssue]:
    path = root / "production/migration/testing-framework-parity.json"
    text, issues = _read_utf8_file(path, "testing-framework parity evidence")
    if text is None:
        return issues
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return [ValidationIssue("error", _relative(root, path), f"invalid parity JSON: {error}")]
    required = {"version", "source_commit", "source_root", "source_file_count", "contract_sha256", "entries", "native_extensions"}
    if not isinstance(data, dict) or set(data) != required:
        return [ValidationIssue("error", _relative(root, path), "parity evidence fields are not exact")]
    entries = data.get("entries") if isinstance(data.get("entries"), list) else []
    if data.get("version") != 1 or data.get("source_file_count") != FRAMEWORK_PARITY_COUNT or len(entries) != FRAMEWORK_PARITY_COUNT:
        issues.append(ValidationIssue("error", _relative(root, path), f"parity evidence must contain exactly {FRAMEWORK_PARITY_COUNT} version-1 entries"))
    canonical_parts: list[str] = []
    sources: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"source", "source_sha256", "destination"}:
            issues.append(ValidationIssue("error", _relative(root, path), "parity entry fields are not exact"))
            continue
        source = entry.get("source", "")
        digest = entry.get("source_sha256", "")
        destination = entry.get("destination", "")
        if source in sources or not _safe_relative_path(source):
            issues.append(ValidationIssue("error", _relative(root, path), f"unsafe or duplicate parity source: {source!r}"))
        sources.add(source)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            issues.append(ValidationIssue("error", _relative(root, path), f"invalid source SHA-256 for {source!r}"))
        expected_destination = "Codex Studio Testing Framework/" + ("AGENTS.md" if source == "CLAUDE.md" else source)
        if destination != expected_destination:
            issues.append(ValidationIssue("error", _relative(root, path), f"invalid native mapping for {source!r}"))
        valid, message = _contained_regular_file(root, destination)
        if not valid:
            issues.append(ValidationIssue("error", destination, message))
        canonical_parts.append(f"{source}\0{digest}\0{destination}")
    digest = hashlib.sha256("\n".join(canonical_parts).encode("utf-8")).hexdigest()
    if data.get("contract_sha256") != FRAMEWORK_PARITY_SHA256 or digest != FRAMEWORK_PARITY_SHA256:
        issues.append(ValidationIssue("error", _relative(root, path), "testing-framework parity contract digest does not match"))
    expected_extensions = ["Codex Studio Testing Framework/skills/utility/vertical-slice.md"]
    if data.get("native_extensions") != expected_extensions:
        issues.append(ValidationIssue("error", _relative(root, path), "native framework extension set does not match"))
    for extension in expected_extensions:
        valid, message = _contained_regular_file(root, extension)
        if not valid:
            issues.append(ValidationIssue("error", extension, message))
    return issues


def _runtime_files(root: pathlib.Path) -> tuple[list[pathlib.Path], list[ValidationIssue]]:
    files: set[pathlib.Path] = set()
    issues: list[ValidationIssue] = []
    direct = (
        "AGENTS.md", "README.md", "CONTRIBUTING.md", "SECURITY.md",
        "UPGRADING.md", ".gitignore",
    )
    for relative in direct:
        path = root / relative
        if path.is_symlink():
            issues.append(ValidationIssue("error", relative, "runtime file must not be a symlink"))
        elif path.is_file():
            files.add(path)
        else:
            issues.append(ValidationIssue("error", relative, "required runtime file is missing"))

    roots = (
        ".agents", ".codex", ".github", "Codex Studio Testing Framework",
        "docs", "design", "tools", "tests", "production",
    )
    excluded_prefixes = ("docs/superpowers/", "production/migration/")
    for relative in roots:
        base = root / relative
        if base.is_symlink():
            issues.append(ValidationIssue("error", relative, "runtime directory must not be a symlink"))
            continue
        if not base.is_dir():
            issues.append(ValidationIssue("error", relative, "required runtime directory is missing"))
            continue
        for current, directories, filenames in os.walk(base, followlinks=False):
            current_path = pathlib.Path(current)
            kept: list[str] = []
            for name in directories:
                child = current_path / name
                child_relative = _relative(root, child) + "/"
                if name == "__pycache__" or child_relative.startswith(excluded_prefixes):
                    continue
                if child.is_symlink():
                    issues.append(ValidationIssue("error", _relative(root, child), "runtime directory must not be a symlink"))
                    continue
                kept.append(name)
            directories[:] = kept
            for name in filenames:
                path = current_path / name
                relative_path = _relative(root, path)
                if relative_path.startswith(excluded_prefixes) or path.suffix in {".pyc", ".pyo"}:
                    continue
                if path.is_symlink():
                    issues.append(ValidationIssue("error", relative_path, "runtime file must not be a symlink"))
                    continue
                files.add(path)
    return sorted(files), issues


def validate_runtime_references(root: pathlib.Path, phase: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if phase not in {"pre-cleanup", "final"}:
        return [ValidationIssue("error", ".", f"unsupported validation phase: {phase}")]
    if phase == "final":
        for relative in (".claude", "CCGS Skill Testing Framework"):
            path = root / relative
            if path.exists() or path.is_symlink():
                issues.append(ValidationIssue("error", relative, "legacy directory remains"))
    issues.extend(validate_coverage_manifest(root, phase))
    issues.extend(validate_testing_framework_parity(root))
    runtime_files, discovery_issues = _runtime_files(root)
    issues.extend(discovery_issues)
    slash_skill = re.compile(
        r"(?<![A-Za-z0-9_.-])/((?:" + "|".join(sorted(map(re.escape, EXPECTED_SKILL_NAMES))) + r"))(?![A-Za-z0-9_.-])"
    )
    for path in runtime_files:
        text, read_issues = _read_utf8_file(path, "runtime file")
        issues.extend(read_issues)
        if text is None:
            continue
        relative = _relative(root, path)
        integrity_only = relative.startswith("tests/") or relative == "tools/codex_studio/validate.py"
        if integrity_only:
            continue
        for pattern, label in RUNTIME_FORBIDDEN_PATTERNS.items():
            if relative == "UPGRADING.md" and label in {
                "legacy durable-guidance filename", "legacy runtime path",
                "legacy model identifier", "legacy runtime product name",
            }:
                continue
            if re.search(pattern, text, flags=re.MULTILINE):
                issues.append(ValidationIssue("error", relative, f"contains {label}"))
        if slash_skill.search(text):
            issues.append(ValidationIssue("error", relative, "contains slash-style invocation for a known skill"))
        if MACHINE_PATH.search(text):
            issues.append(ValidationIssue("error", relative, "contains machine-specific absolute path"))
    return issues


def validate_repository(root: pathlib.Path, phase: str) -> list[ValidationIssue]:
    if phase not in {"pre-cleanup", "final"}:
        return [ValidationIssue("error", ".", f"unsupported validation phase: {phase}")]
    if root.is_symlink():
        return [ValidationIssue("error", str(root), "repository root must not be a symlink")]
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        return [ValidationIssue("error", str(root), f"cannot resolve repository root: {error}")]
    issues: list[ValidationIssue] = []
    for name in sorted(EXPECTED_CORE_NAMES):
        path = root / ".codex/agents" / f"{name}.toml"
        issues.extend(validate_agent(path))
    for engine, names in sorted(EXPECTED_PACK_NAMES.items()):
        for name in sorted(names):
            issues.extend(validate_agent(root / ".codex/agent-packs" / engine / f"{name}.toml"))
    for name in sorted(EXPECTED_SKILL_NAMES):
        path = root / ".agents/skills" / name / "SKILL.md"
        issues.extend(validate_skill(path))
    issues.extend(validate_hooks(root / ".codex/hooks.json", root=root))
    issues.extend(validate_repository_counts(root))
    issues.extend(validate_runtime_references(root, phase))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Codex Game Studios")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--phase", choices=("pre-cleanup", "final"), default="final")
    args = parser.parse_args(argv)
    issues = validate_repository(args.root, args.phase)
    for issue in issues:
        print(f"{issue.severity.upper()} {issue.path}: {issue.message}")
    if any(issue.severity == "error" for issue in issues):
        print("Codex Studio validation: FAIL")
        return 1
    print("Codex Studio validation: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
