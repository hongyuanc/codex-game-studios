from __future__ import annotations

import dataclasses
import json
import pathlib
import re
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


def validate_hooks(path: pathlib.Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [ValidationIssue("error", str(path), f"invalid JSON: {error}")]

    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return [ValidationIssue("error", str(path), "missing hooks object")]

    for event, groups in hooks.items():
        if event not in SUPPORTED_HOOK_EVENTS:
            issues.append(ValidationIssue("error", str(path), f"unsupported hook event: {event}"))
        if not isinstance(groups, list):
            issues.append(ValidationIssue("error", str(path), f"hook event {event} must contain a list"))
            continue
        for group_index, group in enumerate(groups):
            handlers = group.get("hooks") if isinstance(group, dict) else None
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
                combined = f"{command}\n{windows}"
                if re.search(r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])", combined):
                    issues.append(ValidationIssue("error", str(path), f"{location} contains absolute user path"))
                if ".codex/hooks/hook_runner.py" not in command:
                    issues.append(ValidationIssue("error", str(path), f"{location} command must reference .codex/hooks/hook_runner.py"))
                if windows and ".codex/hooks/hook_runner.py" not in windows:
                    issues.append(ValidationIssue("error", str(path), f"{location} Windows command must reference .codex/hooks/hook_runner.py"))
    return issues
