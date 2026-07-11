from __future__ import annotations

import ast
import collections
import dataclasses
import json
import pathlib
import re
import shlex
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
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if len(tokens) != 3 or pathlib.PurePosixPath(tokens[0]).name not in {"python", "python3"}:
        return None
    if tokens[1] != "$(git rev-parse --show-toplevel)/.codex/hooks/hook_runner.py":
        return None
    return tokens[2] if re.fullmatch(r"[a-z][a-z-]*", tokens[2]) else None


def _windows_hook_action(command: str) -> str | None:
    matches = re.findall(
        r"\.codex/hooks/hook_runner\.py[^A-Za-z0-9-]+([a-z][a-z-]*)(?=[\s\"']|$)",
        command,
    )
    return matches[0] if len(matches) == 1 else None


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
