from __future__ import annotations

import dataclasses
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
    r"\.Codex/|\.claude/": "non-native path",
    r"^model:\s*(opus|sonnet|haiku)\s*$": "Claude model metadata",
    r"^allowed-tools:": "Claude tool metadata",
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
