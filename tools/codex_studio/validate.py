from __future__ import annotations

import ast
import argparse
import collections
import dataclasses
import json
import pathlib
import re
import sys
import tomllib


ALLOWED_MODELS = {"gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"}
ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh"}
REQUIRED_AGENT_FIELDS = {"name", "description", "developer_instructions", "model", "model_reasoning_effort"}
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
RUNTIME_FORBIDDEN = {
    "Claude Code": "Claude runtime product name",
    "AskUserQuestion": "Claude interaction primitive",
    "Task tool": "Claude delegation primitive",
    "subagent_type": "Claude agent metadata",
    ".claude/": "Claude runtime path",
    ".Codex/": "incorrect Codex path casing",
}
MACHINE_PATH = re.compile(r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])")


@dataclasses.dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


def validate_agent(path: pathlib.Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return [ValidationIssue("error", str(path), f"invalid TOML: {error}")]
    for field in sorted(REQUIRED_AGENT_FIELDS - set(data)):
        issues.append(ValidationIssue("error", str(path), f"missing required field: {field}"))
    if "model" in data and data["model"] not in ALLOWED_MODELS:
        issues.append(ValidationIssue("error", str(path), f"unsupported model: {data['model']}"))
    if "model_reasoning_effort" in data and data["model_reasoning_effort"] not in ALLOWED_EFFORTS:
        issues.append(ValidationIssue("error", str(path), f"unsupported reasoning effort: {data['model_reasoning_effort']}"))
    return issues


def validate_skill(path: pathlib.Path) -> list[ValidationIssue]:
    text = path.read_text(encoding="utf-8")
    issues: list[ValidationIssue] = []
    if not text.startswith("---\n"):
        issues.append(ValidationIssue("error", str(path), "missing YAML frontmatter"))
    frontmatter = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    for field in ("name:", "description:"):
        if field not in frontmatter:
            issues.append(ValidationIssue("error", str(path), f"missing required metadata: {field[:-1]}"))
    for pattern, label in FORBIDDEN_SKILL_PATTERNS.items():
        if re.search(pattern, text, flags=re.MULTILINE):
            issues.append(ValidationIssue("error", str(path), f"contains {label}"))
    return issues


def _runtime_hook_contract() -> tuple[set[str], set[str]]:
    runner = pathlib.Path(__file__).resolve().parents[2] / ".codex/hooks/hook_runner.py"
    tree = ast.parse(runner.read_text(encoding="utf-8"), filename=str(runner))
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


def validate_hooks(path: pathlib.Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [ValidationIssue("error", str(path), f"invalid JSON: {error}")]

    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return [ValidationIssue("error", str(path), "missing hooks object")]

    try:
        runtime_actions, runtime_handlers = _runtime_hook_contract()
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
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = data.get("name")
    return name if isinstance(name, str) else None


def validate_repository_counts(root: pathlib.Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
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
    names = [_profile_name(path) for path in [*core, *packed]]
    if None not in names and len(set(names)) != 49:
        issues.append(
            ValidationIssue("error", ".codex", "agent roster must contain 49 unique role names")
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
        count = len(list((pack_root / engine).glob("*.toml")))
        if count != 5:
            issues.append(
                ValidationIssue("error", f".codex/agent-packs/{engine}", f"expected 5 profiles, found {count}")
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
    missing_docs = sorted(name for name in REQUIRED_DOCS if not (docs / name).is_file())
    if missing_docs:
        issues.append(ValidationIssue("error", ".codex/docs", f"missing required documents: {missing_docs}"))
    templates = [path for path in (docs / "templates").rglob("*") if path.is_file()]
    if len(templates) != 40:
        issues.append(ValidationIssue("error", ".codex/docs/templates", f"expected 40 templates, found {len(templates)}"))
    return issues


def _coverage_entries(path: pathlib.Path) -> tuple[list[dict[str, str]], list[ValidationIssue]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [], [ValidationIssue("error", str(path), f"cannot read coverage manifest: {error}")]
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in lines:
        source_match = re.fullmatch(r"  - source: (.+)", line)
        field_match = re.fullmatch(r"    (destination|action|reason): (.+)", line)
        if source_match:
            if current is not None:
                entries.append(current)
            current = {"source": source_match.group(1).strip()}
        elif field_match and current is not None:
            current[field_match.group(1)] = field_match.group(2).strip()
    if current is not None:
        entries.append(current)
    return entries, []


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
    seen: set[str] = set()
    for entry in entries:
        source = entry.get("source", "")
        if not source or source in seen:
            issues.append(ValidationIssue("error", _relative(root, manifest), f"duplicate or blank source: {source!r}"))
        seen.add(source)
        destination = entry.get("destination", "")
        action = entry.get("action", "")
        reason = entry.get("reason", "")
        if not reason:
            issues.append(ValidationIssue("error", source, "coverage reason is blank"))
        if action == "migrate":
            if not destination or destination == "remove-without-replacement" or not (root / destination).exists():
                issues.append(ValidationIssue("error", source, f"migration destination does not exist: {destination}"))
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
    return issues


def _runtime_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: set[pathlib.Path] = set()
    direct = [
        root / "AGENTS.md", root / "README.md", root / "CONTRIBUTING.md",
        root / "SECURITY.md", root / "docs/WORKFLOW-GUIDE.md",
    ]
    files.update(path for path in direct if path.is_file())
    for relative in (".agents", ".codex", ".github", "docs/examples", "Codex Studio Testing Framework"):
        base = root / relative
        if base.exists():
            files.update(path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    files.update(root / relative for relative in EXPECTED_INSTRUCTION_PATHS if (root / relative).is_file())
    return sorted(files)


def validate_runtime_references(root: pathlib.Path, phase: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if phase not in {"pre-cleanup", "final"}:
        return [ValidationIssue("error", ".", f"unsupported validation phase: {phase}")]
    issues.extend(validate_coverage_manifest(root, phase))
    for path in _runtime_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative = _relative(root, path)
        for token, label in RUNTIME_FORBIDDEN.items():
            if token in text:
                issues.append(ValidationIssue("error", relative, f"contains {label}"))
        if MACHINE_PATH.search(text):
            issues.append(ValidationIssue("error", relative, "contains machine-specific absolute path"))
    return issues


def validate_repository(root: pathlib.Path, phase: str) -> list[ValidationIssue]:
    root = root.resolve()
    if phase not in {"pre-cleanup", "final"}:
        return [ValidationIssue("error", ".", f"unsupported validation phase: {phase}")]
    issues: list[ValidationIssue] = []
    for path in sorted((root / ".codex/agents").glob("*.toml")):
        issues.extend(validate_agent(path))
    for path in sorted((root / ".codex/agent-packs").glob("*/*.toml")):
        issues.extend(validate_agent(path))
    for path in sorted((root / ".agents/skills").glob("*/SKILL.md")):
        issues.extend(validate_skill(path))
    issues.extend(validate_hooks(root / ".codex/hooks.json"))
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
