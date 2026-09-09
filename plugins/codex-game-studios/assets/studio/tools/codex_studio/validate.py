from __future__ import annotations

import ast
import argparse
import collections
import contextlib
import dataclasses
from datetime import datetime
import hashlib
import json
import ntpath
import os
import pathlib
import re
import stat
import sys
import tomllib
import unicodedata
import uuid

if __package__ in {None, ""}:
    _BUNDLED_STUDIO_ROOT = pathlib.Path(__file__).resolve().parents[2]
    bundled_studio_root = str(_BUNDLED_STUDIO_ROOT)
    if bundled_studio_root not in sys.path:
        sys.path.insert(0, bundled_studio_root)

from tools.codex_studio.agent_delegation import (
    ALLOWED_MODELS,
    ALLOWED_REASONING_EFFORTS,
    CORE_ROLE_NAMES,
    ENGINE_ROLE_NAMES,
    ROLE_FIELDS,
    validate_delegation_skill,
)
from tools.codex_studio.engine_pack import load_studio_config, validate_activation


ALLOWED_EFFORTS = set(ALLOWED_REASONING_EFFORTS)
REQUIRED_AGENT_FIELDS = set(ROLE_FIELDS)
EXPECTED_CORE_NAMES = set(CORE_ROLE_NAMES)
EXPECTED_PACK_NAMES = {engine: set(names) for engine, names in ENGINE_ROLE_NAMES.items()}
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
_PLUGIN_SKILL_INVOCATION = re.compile(
    r"(?<![A-Za-z0-9_$])\$("
    + "|".join(
        sorted(map(re.escape, EXPECTED_SKILL_NAMES), key=len, reverse=True)
    )
    + r")(?![A-Za-z0-9_-])"
)
# enforcement-literal-start
FORBIDDEN_SKILL_PATTERNS = {
    r"\bAskUserQuestion\b": "Claude interaction primitive",
    r"\bTodoWrite\b": "Claude task primitive",
    r"\bTask tool\b|\bsubagent_type\b": "Claude delegation primitive",
    r"(?i:\bTask calls?\b|\btask-call(?:s|ing)?\b)": "non-native task-call syntax",
    r"(?-i:\.Codex/)|\.claude/": "non-native path",
}
FORBIDDEN_SKILL_FRONTMATTER = {
    "model": "Claude model metadata",
    "allowed-tools": "Claude tool metadata",
    "agent": "Claude agent metadata",
    "maxturns": "Claude turn-limit metadata",
}
# enforcement-literal-end
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
    "plugin-agent-delegation.md",
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
# enforcement-literal-start
RUNTIME_FORBIDDEN_PATTERNS = {
    r"CLAUDE\.md": "legacy durable-guidance filename",
    r"\.claude/": "legacy runtime path",
    r"(?-i:\.Codex/)": "incorrect Codex path casing",
    r"\bAskUserQuestion\b": "legacy interaction primitive",
    r"(?i:\bTask calls?\b|\bTask tool\b)": "legacy delegation primitive",
    r"\bsubagent_type\b": "legacy agent metadata",
    r"(?m)^\s*(?:allowed-tools|argument-hint|user-invocable)\s*:": "legacy metadata",
    r"\bclaude-(?:opus|sonnet|haiku)[-\w.]*\b": "legacy model identifier",
    r"\bAnthropic\b": "legacy runtime routing",
    r"\bClaude(?: Code)?\b": "legacy runtime product name",
}
MACHINE_PATH = re.compile(r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])")
# enforcement-literal-end
PLUGIN_SKILL_PROBE = re.compile(r"\.agents/skills/[a-z0-9-]+/SKILL\.md")
EXPECTED_PLUGIN_SKILL_DEPENDENCIES = {
    "bug-report": ("hotfix",),
    "bug-triage": ("team-qa",),
    "dev-story": ("team-qa",),
    "help": ("[command]",),
    "skill-improve": ("skill-test",),
    "skill-test": ("[name]",),
    "smoke-check": ("setup-engine",),
    "sprint-plan": ("team-qa",),
    "story-done": ("team-qa",),
    "test-evidence-review": ("team-qa",),
    "test-helpers": ("setup-engine", "skill-test"),
    "test-setup": ("setup-engine",),
}
PLUGIN_SKILL_RESOURCE_CANDIDATE = re.compile(
    r"\.codex/(?:docs/|studio\.toml)|docs/engine-reference/|"
    r"Codex Studio Testing Framework/",
    flags=re.IGNORECASE,
)
PLUGIN_SKILL_RESOURCE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:"
    r"\.codex/studio\.toml|"
    r"\.codex/docs/technical-preferences\.md|"
    r"\.\./\.\./\.\./(?:"
    r"\.codex/docs/(?!technical-preferences\.md)[A-Za-z0-9_./*<>\[\]-]+|"
    r"docs/engine-reference/[A-Za-z0-9_./*<>\[\]-]*|"
    r"Codex Studio Testing Framework/[A-Za-z0-9_./*<>\[\]-]+"
    r"))(?=$|[\s`'\"),:;\]}])"
)
COVERAGE_ENTRY_COUNT = 203
COVERAGE_SOURCE_SET_SHA256 = "37580b38a3b505292d524d4432239ff571741fb9ace8787544ec6643e34feef0"
COVERAGE_CONTRACT_SHA256 = "899296b2dbb4553303606dad787912d834bc81beba6c9e0a8bc44cf15d149cde"
FRAMEWORK_PARITY_COUNT = 127
FRAMEWORK_SOURCE_COMMIT = "7bad60b7e0e71723b4b745e36950492d714595a3"
FRAMEWORK_SOURCE_ROOT = "CCGS Skill Testing Framework"
FRAMEWORK_PARITY_SHA256 = "4cd4ae46dc9e26217361f3a4cea6bea427ddb1efc7c41668c62c01e9521dce4c"

ENFORCEMENT_START = "# enforcement-" + "literal-start"
ENFORCEMENT_END = "# enforcement-" + "literal-end"
ENFORCEMENT_INLINE = "# enforcement-" + "literal"
HISTORY_START = "<!-- historical-" + "source-start -->"
HISTORY_END = "<!-- historical-" + "source-end -->"
UPSTREAM_ATTRIBUTION_START = "<!-- upstream-" + "attribution-start -->"
UPSTREAM_ATTRIBUTION_END = "<!-- upstream-" + "attribution-end -->"
UPSTREAM_ATTRIBUTION_PROVIDER_LABELS = {
    "legacy runtime routing",
    "legacy runtime product name",
}


@dataclasses.dataclass(frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


def _strip_bounded_markers(
    text: str,
    *,
    start: str,
    end: str,
    inline: str | None = None,
) -> tuple[str, list[str]]:
    """Remove explicitly exempted lines while rejecting ambiguous marker use."""
    active = False
    cleaned: list[str] = []
    errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        has_start = start in line
        has_end = end in line
        if has_start and has_end:
            errors.append(f"markers must be on separate lines (line {line_number})")
            cleaned.append("")
            continue
        if has_start:
            if active:
                errors.append(f"markers must not nest (line {line_number})")
            active = True
            cleaned.append("")
            continue
        if has_end:
            if not active:
                errors.append(f"closing marker has no matching start (line {line_number})")
            active = False
            cleaned.append("")
            continue
        if active or (inline is not None and inline in line):
            cleaned.append("")
        else:
            cleaned.append(line)
    if active:
        errors.append("opening marker has no matching end")
    return "\n".join(cleaned), errors


def _strip_exactly_one_bounded_block(
    text: str,
    *,
    start: str,
    end: str,
) -> tuple[str, list[str]]:
    """Strip one exact-line block, returning original text for any malformed use."""
    lines = text.splitlines()
    marker_lines = [
        (line_number, line)
        for line_number, line in enumerate(lines, start=1)
        if start in line or end in line
    ]
    if not marker_lines:
        return text, []

    errors = [
        f"markers must be exact standalone lines (line {line_number})"
        for line_number, line in marker_lines
        if line not in {start, end}
    ]
    cleaned, bounded_errors = _strip_bounded_markers(
        text,
        start=start,
        end=end,
    )
    errors.extend(bounded_errors)
    if lines.count(start) != 1 or lines.count(end) != 1:
        errors.append("markers must define exactly one block")
    if errors:
        return text, errors
    return cleaned, []


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
    normalized_fields = {field.lower() for field in fields}
    for field, label in FORBIDDEN_SKILL_FRONTMATTER.items():
        if field in normalized_fields:
            issues.append(ValidationIssue("error", str(path), f"contains {label}"))
    for pattern, label in FORBIDDEN_SKILL_PATTERNS.items():
        if re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE):
            issues.append(ValidationIssue("error", str(path), f"contains {label}"))
    for message in validate_delegation_skill(path.parent.name, text):
        issues.append(ValidationIssue("error", str(path), message))
    return issues


def validate_plugin_skill_catalog(
    root: pathlib.Path, plugin: pathlib.Path
) -> list[ValidationIssue]:
    """Validate exact source/bundle parity and plugin-relative skill resources."""

    issues: list[ValidationIssue] = []
    source = root / ".agents/skills"
    bundled = plugin / "assets/studio/.agents/skills"
    for catalog, label in ((source, "source"), (bundled, "bundled")):
        relative = _relative(root, catalog)
        if catalog.is_symlink() or not catalog.is_dir():
            issues.append(
                ValidationIssue(
                    "error", relative, f"plugin skill {label} catalog must be a regular directory"
                )
            )

    def catalog_paths(catalog: pathlib.Path) -> dict[str, pathlib.Path]:
        paths: dict[str, pathlib.Path] = {}
        if not catalog.is_dir() or catalog.is_symlink():
            return paths
        try:
            entries = sorted(catalog.iterdir(), key=lambda path: path.name)
        except OSError as error:
            issues.append(
                ValidationIssue(
                    "error", _relative(root, catalog), f"cannot read plugin skill catalog: {error}"
                )
            )
            return paths
        for directory in entries:
            if directory.is_symlink():
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, directory),
                        "plugin skill directory must not be a symlink",
                    )
                )
                continue
            if directory.is_dir():
                paths[directory.name] = directory / "SKILL.md"
        return paths

    source_paths = catalog_paths(source)
    bundled_paths = catalog_paths(bundled)
    source_names = set(source_paths)
    bundled_names = set(bundled_paths)
    if source_names != EXPECTED_SKILL_NAMES:
        issues.append(
            ValidationIssue(
                "error",
                _relative(root, source),
                "plugin skill source inventory differs; "
                f"missing={sorted(EXPECTED_SKILL_NAMES - source_names)}, "
                f"extra={sorted(source_names - EXPECTED_SKILL_NAMES)}",
            )
        )
    if bundled_names != source_names:
        issues.append(
            ValidationIssue(
                "error",
                _relative(root, bundled),
                "plugin skill bundled inventory differs; "
                f"missing={sorted(source_names - bundled_names)}, "
                f"extra={sorted(bundled_names - source_names)}",
            )
        )

    for name in sorted(source_names | bundled_names):
        source_path = source_paths.get(name)
        bundled_path = bundled_paths.get(name)
        if source_path is None or bundled_path is None:
            continue
        source_text, source_issues = _read_utf8_file(source_path, "source skill")
        bundled_text, bundled_issues = _read_utf8_file(bundled_path, "bundled skill")
        issues.extend(source_issues)
        issues.extend(bundled_issues)
        issues.extend(validate_skill(bundled_path))
        if source_text is None or bundled_text is None:
            continue
        expected_bundled_text = _PLUGIN_SKILL_INVOCATION.sub(
            lambda match: f"$codex-game-studios:{match.group(1)}", source_text
        )
        if expected_bundled_text != bundled_text:
            issues.append(
                ValidationIssue(
                    "error",
                    _relative(root, bundled_path),
                    f"bundled plugin skill differs from canonical namespace transform: {name}",
                )
            )
        if PLUGIN_SKILL_PROBE.search(source_text):
            issues.append(
                ValidationIssue(
                    "error",
                    _relative(root, source_path),
                    "skill probes a repository-local skill installation",
                )
            )
        expected_dependencies = EXPECTED_PLUGIN_SKILL_DEPENDENCIES.get(name, ())
        source_lines = source_text.splitlines()
        for dependency in expected_dependencies:
            heading = f"### Native readiness gate for `${dependency}`"
            heading_lines = [
                index for index, line in enumerate(source_lines) if line == heading
            ]
            actual_gate = ""
            if len(heading_lines) == 1:
                start = heading_lines[0] + 1
                end = next(
                    (
                        index
                        for index in range(start, len(source_lines))
                        if source_lines[index].startswith("#")
                    ),
                    len(source_lines),
                )
                actual_gate = " ".join("\n".join(source_lines[start:end]).split())
            expected_gate = " ".join(
                (
                    f"Before invoking or routing to `${dependency}`, confirm that "
                    f"`{dependency}` is present in the current task's available skill "
                    "catalog. If unavailable, report "
                    f"`Staged dependency: ${dependency} is not available`, defer the "
                    f"handoff, do not invoke `${dependency}`, do not route to "
                    f"`${dependency}`, and do not search for or copy a repository-local "
                    "skill file."
                ).split()
            )
            if len(heading_lines) != 1 or actual_gate != expected_gate:
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, source_path),
                        "plugin skill dependency contract is incomplete for "
                        f"{dependency}: expected one bounded normalized fail-closed gate",
                    )
                )
        valid_resources = list(PLUGIN_SKILL_RESOURCE.finditer(source_text))
        valid_spans = [match.span() for match in valid_resources]
        for candidate in PLUGIN_SKILL_RESOURCE_CANDIDATE.finditer(source_text):
            if not any(start <= candidate.start() and candidate.end() <= end for start, end in valid_spans):
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, source_path),
                        f"invalid plugin skill resource reference near: {candidate.group()}",
                    )
                )
        for code_span in re.finditer(r"`([^`\n]+)`", source_text):
            value = code_span.group(1)
            if not PLUGIN_SKILL_RESOURCE_CANDIDATE.search(value):
                continue
            if PLUGIN_SKILL_RESOURCE.fullmatch(value) is None:
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, source_path),
                        f"invalid plugin skill resource token: {value}",
                    )
                )
        studio = plugin / "assets/studio"
        for resource in valid_resources:
            token = resource.group()
            if not token.startswith("../../../"):
                continue
            relative_resource = token.removeprefix("../../../")
            normalized_resource = pathlib.PurePosixPath(relative_resource)
            if (
                normalized_resource.is_absolute()
                or ".." in normalized_resource.parts
                or normalized_resource.as_posix() != relative_resource.rstrip("/")
            ):
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, source_path),
                        f"plugin skill resource path is not lexically contained: {token}",
                    )
                )
                continue
            if any(marker in token for marker in "[]<>*"):
                continue
            target = studio / relative_resource
            try:
                resolved_studio = studio.resolve(strict=True)
                resolved_target = target.resolve(strict=True)
                resolved_target.relative_to(resolved_studio)
            except (OSError, ValueError):
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, source_path),
                        f"plugin skill resource target does not exist or escapes the bundle: {token}",
                    )
                )
                continue
            current = target
            unsafe = False
            while current != studio:
                if current.is_symlink():
                    unsafe = True
                    break
                current = current.parent
            if unsafe or not (resolved_target.is_file() or resolved_target.is_dir()):
                issues.append(
                    ValidationIssue(
                        "error",
                        _relative(root, source_path),
                        f"plugin skill resource target is not a regular bundled resource: {token}",
                    )
                )
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
                if re.search(r"(?:/Users/|/home/|[A-Za-z]:[\\/]Users[\\/])", combined):  # enforcement-literal
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


def _expected_active_agents_for_pack(active_engine_pack: str) -> set[str]:
    """Return the exact active routing set for one already-parsed pack value."""

    names = set(EXPECTED_CORE_NAMES)
    if active_engine_pack != "none":
        if active_engine_pack not in EXPECTED_PACK_NAMES:
            raise ValueError("active engine pack is unsupported")
        names.update(EXPECTED_PACK_NAMES[active_engine_pack])
    return names


def expected_active_agents(root: pathlib.Path) -> set[str]:
    """Return the exact configured 34- or 39-profile active routing set."""

    return _expected_active_agents_for_pack(load_studio_config(root).active_engine_pack)


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

    try:
        studio = load_studio_config(root)
    except (OSError, ValueError) as error:
        studio = None
        issues.append(
            ValidationIssue(
                "error",
                ".codex/studio.toml",
                f"invalid studio configuration: {error}",
            )
        )
    expected_active_names = (
        _expected_active_agents_for_pack(studio.active_engine_pack)
        if studio is not None else set(EXPECTED_CORE_NAMES)
    )

    require_count(".codex/agents", core, len(expected_active_names))
    require_count(".codex/agent-packs", packed, 15)
    require_count(".agents/skills", skills, 73)
    core_files = {path.stem for path in core}
    core_entries = {
        path.name for path in (root / ".codex/agents").iterdir()
        if path.is_file() or path.is_symlink()
    } if (root / ".codex/agents").is_dir() else set()
    expected_core_entries = {f"{name}.toml" for name in expected_active_names}
    if core_entries != expected_core_entries:
        issues.append(
            ValidationIssue("error", ".codex/agents", f"approved active profile files differ; missing={sorted(expected_core_entries - core_entries)}, extra={sorted(core_entries - expected_core_entries)}")
        )
    if core_files != expected_active_names:
        issues.append(
            ValidationIssue(
                "error", ".codex/agents",
                f"approved active agent identities differ; missing={sorted(expected_active_names - core_files)}, extra={sorted(core_files - expected_active_names)}",
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

    for message in validate_activation(root):
        issues.append(ValidationIssue("error", ".codex/active-engine.json", message))

    instructions = {
        _relative(root, path)
        for path in root.rglob("AGENTS.md")
        if path != root / "AGENTS.md"
        and path.relative_to(root).parts[:1] != ("plugins",)
        and path.relative_to(root).parts[:2] != ("tests", "plugin")
        and "Codex Studio Testing Framework" not in path.parts
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
        for path in (root / ".claude").rglob("*")  # enforcement-literal
        if path.is_file()
    } if (root / ".claude").is_dir() else set()  # enforcement-literal
    sources.update(_relative(root, path) for path in root.rglob("CLAUDE.md"))  # enforcement-literal
    return sources


def validate_coverage_manifest(root: pathlib.Path, phase: str) -> list[ValidationIssue]:
    manifest = root / "production/migration/claude-to-codex-coverage.yaml"  # enforcement-literal
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
        for relative in (".claude", "CCGS Skill Testing Framework"):  # enforcement-literal
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
    source_commit = data.get("source_commit")
    source_root = data.get("source_root")
    if source_commit != FRAMEWORK_SOURCE_COMMIT:
        issues.append(ValidationIssue("error", _relative(root, path), "parity source commit does not match"))
    if source_root != FRAMEWORK_SOURCE_ROOT:
        issues.append(ValidationIssue("error", _relative(root, path), "parity source root does not match"))
    canonical_parts: list[str] = [f"source_commit\0{source_commit}", f"source_root\0{source_root}"]
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
        expected_destination = "Codex Studio Testing Framework/" + ("AGENTS.md" if source == "CLAUDE.md" else source)  # enforcement-literal
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
    expected_native = {
        entry.get("destination") for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("destination"), str)
    } | set(expected_extensions)
    framework_root = root / "Codex Studio Testing Framework"
    actual_native: set[str] = set()
    if framework_root.is_symlink() or not framework_root.is_dir():
        issues.append(ValidationIssue("error", _relative(root, framework_root), "native framework root must be a regular directory"))
    else:
        for native_path in framework_root.rglob("*"):
            relative_native = _relative(root, native_path)
            if native_path.is_symlink():
                issues.append(ValidationIssue("error", relative_native, "native framework entry must not be a symlink"))
            elif native_path.is_file():
                actual_native.add(relative_native)
    if actual_native != expected_native:
        issues.append(ValidationIssue(
            "error", _relative(root, framework_root),
            "exact native framework inventory does not match; "
            f"missing={sorted(expected_native - actual_native)}, extra={sorted(actual_native - expected_native)}",
        ))
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
        "assets", "docs", "design", "prototypes", "src", "tools", "tests", "production",
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
        def walk_error(error: OSError) -> None:
            error_path = pathlib.Path(error.filename) if error.filename else base
            issues.append(ValidationIssue(
                "error", _relative(root, error_path),
                f"cannot traverse runtime directory: {error}",
            ))

        for current, directories, filenames in os.walk(
            base, followlinks=False, onerror=walk_error
        ):
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
        for relative in (".claude", "CCGS Skill Testing Framework"):  # enforcement-literal
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
        if relative.startswith("tests/") or relative == "tools/codex_studio/validate.py":
            text, marker_errors = _strip_bounded_markers(
                text,
                start=ENFORCEMENT_START,
                end=ENFORCEMENT_END,
                inline=ENFORCEMENT_INLINE,
            )
            issues.extend(ValidationIssue("error", relative, error) for error in marker_errors)
        elif ENFORCEMENT_START in text or ENFORCEMENT_END in text or ENFORCEMENT_INLINE in text:
            issues.append(ValidationIssue("error", relative, "enforcement-literal markers are restricted to validator tests and implementation"))
        if relative == "UPGRADING.md":
            text, marker_errors = _strip_bounded_markers(
                text, start=HISTORY_START, end=HISTORY_END
            )
            issues.extend(ValidationIssue("error", relative, error) for error in marker_errors)
        provider_scan_text = text
        if relative == "README.md":
            provider_scan_text, marker_errors = _strip_exactly_one_bounded_block(
                text,
                start=UPSTREAM_ATTRIBUTION_START,
                end=UPSTREAM_ATTRIBUTION_END,
            )
            issues.extend(
                ValidationIssue("error", relative, error)
                for error in marker_errors
            )
        elif UPSTREAM_ATTRIBUTION_START in text or UPSTREAM_ATTRIBUTION_END in text:
            issues.append(ValidationIssue(
                "error",
                relative,
                "upstream attribution markers are restricted to README.md",
            ))
        for pattern, label in RUNTIME_FORBIDDEN_PATTERNS.items():
            scan_text = (
                provider_scan_text
                if label in UPSTREAM_ATTRIBUTION_PROVIDER_LABELS
                else text
            )
            if re.search(pattern, scan_text, flags=re.MULTILINE | re.IGNORECASE):
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
    if phase == "final":
        plugin = (root / "plugins/codex-game-studios").resolve()
        issues.extend(validate_plugin_skill_catalog(root, plugin))
    return issues


_INSTALLATION_STATE = ".codex/codex-game-studios/installation.json"
_MANAGER_LOCK = ".codex/codex-game-studios/manager.lock"
_MANAGER_ALLOWED_CHILDREN = {"installation.json", "manager.lock", "recovery", "legal"}
_INSTALLED_STATE_KEYS = {
    "schema_version", "plugin_version", "payload_digest", "transaction_id",
    "installed_at", "managed_paths", "decisions", "validator_version",
    "journal_status", "checksum",
}
_MIGRATION_STATE_KEYS = {
    "schema_version", "plugin_version", "legacy_version",
    "legacy_state_checksum", "preserved_paths", "migrated_at", "checksum",
}
_INSTALLED_PATH_KEYS = {"path", "installed_hash", "ownership", "merge", "block_hash"}
# payload-inventory-attestation:start
_INSTALLED_INVENTORY_ENTRY_COUNT = 516
_INSTALLED_INVENTORY_SHA256 = "24612ab38e1457dd72d3c485cd790ed5af78a5db8433886c9aa5476ce1b0d02a"
# payload-inventory-attestation:end
_INSTALLED_VERSION = "2.0.1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


class _SecureInstalledRoot:
    """Pinned, component-wise no-follow read boundary for installed validation."""

    def __init__(self, root: pathlib.Path, *, windows_api=None):
        self._windows_api = windows_api
        if self._windows_api is None and os.name == "nt":
            self._windows_api = _NativeWindowsApi()
        if self._windows_api is not None:
            native_root = pathlib.Path(root).absolute() if os.name == "nt" else root
            self._windows_root = pathlib.PureWindowsPath(str(native_root))
            if not self._windows_root.is_absolute():
                raise ValueError("Windows repository root must be absolute")
            self.root = root
        else:
            self.root = pathlib.Path(root).absolute()
            self._windows_root = None
        self.fd: int | None = None
        self.identity: tuple[int, int] | None = None
        self._windows_handles: list[int] = []
        self._windows_identity: tuple[int, int] | None = None
        self._windows_canonical_root: pathlib.PureWindowsPath | None = None

    @staticmethod
    def _unsafe(metadata: os.stat_result) -> bool:
        attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
        reparse = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
        return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse) or bool(getattr(metadata, "st_reparse_tag", 0))

    def __enter__(self) -> "_SecureInstalledRoot":
        if self._windows_api is not None:
            return self._windows_enter()
        current = pathlib.Path(self.root.anchor)
        for part in self.root.parts[1:]:
            current = current / part
            metadata = os.lstat(current)
            if self._unsafe(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise OSError(f"unsafe root ancestor: {current}")
        flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)) | int(getattr(os, "O_CLOEXEC", 0))
        self.fd = os.open(self.root, flags)
        opened = os.fstat(self.fd)
        current_metadata = os.lstat(self.root)
        if self._unsafe(opened) or not stat.S_ISDIR(opened.st_mode) or (opened.st_dev, opened.st_ino) != (current_metadata.st_dev, current_metadata.st_ino):
            raise OSError("repository root changed while pinning")
        self.identity = (opened.st_dev, opened.st_ino)
        return self

    def verify(self) -> None:
        if self._windows_api is not None:
            self._windows_verify()
            return
        assert self.fd is not None and self.identity is not None
        opened = os.fstat(self.fd)
        current = os.lstat(self.root)
        if self._unsafe(current) or (opened.st_dev, opened.st_ino) != self.identity or (current.st_dev, current.st_ino) != self.identity:
            raise OSError("repository root changed during validation")

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._windows_api is not None:
            try:
                if exc_type is None:
                    self._windows_verify()
            finally:
                for handle in reversed(self._windows_handles):
                    self._windows_api.close(handle)
                self._windows_handles.clear()
            return
        try:
            if exc_type is None:
                self.verify()
        finally:
            if self.fd is not None:
                os.close(self.fd)

    @contextlib.contextmanager
    def _open(self, relative: str, *, directory: bool | None = None):
        if self._windows_api is not None:
            with self._windows_open(relative, directory=directory) as opened:
                yield opened
            return
        assert self.fd is not None
        parts = pathlib.PurePosixPath(relative).parts
        descriptor = os.dup(self.fd)
        try:
            for index, part in enumerate(parts):
                final = index == len(parts) - 1
                flags = os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0)) | int(getattr(os, "O_CLOEXEC", 0)) | int(getattr(os, "O_NONBLOCK", 0))
                if not final or directory is True:
                    flags |= int(getattr(os, "O_DIRECTORY", 0))
                child = os.open(part, flags, dir_fd=descriptor)
                metadata = os.fstat(child)
                if self._unsafe(metadata) or (not final and not stat.S_ISDIR(metadata.st_mode)):
                    os.close(child)
                    raise OSError(f"unsafe path component: {relative}")
                os.close(descriptor)
                descriptor = child
            metadata = os.fstat(descriptor)
            if directory is True and not stat.S_ISDIR(metadata.st_mode):
                raise OSError(f"expected directory: {relative}")
            if directory is False and not stat.S_ISREG(metadata.st_mode):
                raise OSError(f"expected regular file: {relative}")
            yield descriptor, metadata
        finally:
            os.close(descriptor)

    def read(self, relative: str) -> bytes:
        if self._windows_api is not None:
            with self._windows_open(relative, directory=False) as (handle, before):
                content = self._windows_api.read(handle)
                after = self._windows_api.info(handle)
                if self._windows_signature(before) != self._windows_signature(after):
                    raise OSError(f"file changed during secure read: {relative}")
                self._windows_verify()
                return content
        with self._open(relative, directory=False) as (descriptor, before):
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise OSError(f"file changed during secure read: {relative}")
            self.verify()
            return b"".join(chunks)

    def kind(self, relative: str) -> str:
        if self._windows_api is not None:
            with self._windows_open(relative) as (_, metadata):
                if not metadata.disk or metadata.kind not in {"file", "directory"}:
                    raise OSError(f"special file is forbidden: {relative}")
                return metadata.kind
        with self._open(relative) as (_, metadata):
            if stat.S_ISREG(metadata.st_mode):
                return "file"
            if stat.S_ISDIR(metadata.st_mode):
                return "directory"
            raise OSError(f"special file is forbidden: {relative}")

    def walk_files(self, relative: str) -> set[str]:
        if self._windows_api is not None:
            result: set[str] = set()
            with self._windows_open(relative, directory=True) as (handle, _):
                path = self._windows_canonical_path(
                    self._windows_api.final_path(handle)
                )
                prefix = pathlib.PurePosixPath(relative)
                if relative == ".":
                    prefix = pathlib.PurePosixPath()
                self._windows_walk(handle, path, prefix, result)
            self._windows_verify()
            return result
        result: set[str] = set()
        with self._open(relative, directory=True) as (descriptor, _):
            self._walk_descriptor(descriptor, pathlib.PurePosixPath(relative), result)
        self.verify()
        return result

    def _walk_descriptor(self, descriptor: int, prefix: pathlib.PurePosixPath, result: set[str]) -> None:
        for name in sorted(os.listdir(descriptor)):
            flags = os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0)) | int(getattr(os, "O_CLOEXEC", 0)) | int(getattr(os, "O_NONBLOCK", 0))
            relative = (prefix / name).as_posix()
            try:
                child = os.open(name, flags, dir_fd=descriptor)
            except OSError as error:
                raise OSError(f"unsafe path cannot be opened without following links: {relative}: {error}") from error
            try:
                metadata = os.fstat(child)
                if self._unsafe(metadata):
                    raise OSError(f"unsafe link or reparse point: {relative}")
                if stat.S_ISDIR(metadata.st_mode):
                    self._walk_descriptor(child, prefix / name, result)
                elif stat.S_ISREG(metadata.st_mode):
                    result.add(relative)
                else:
                    raise OSError(f"special file is forbidden: {relative}")
            finally:
                os.close(child)

    @staticmethod
    def _windows_signature(metadata) -> tuple[object, ...]:
        return (
            metadata.identity,
            metadata.kind,
            metadata.reparse,
            metadata.disk,
            metadata.size,
            metadata.write_time,
        )

    @staticmethod
    def _windows_normalize(path: str) -> str:
        if path.startswith("\\\\?\\UNC\\"):
            path = "\\\\" + path[8:]
        elif path.startswith("\\\\?\\"):
            path = path[4:]
        return ntpath.normcase(ntpath.normpath(path))

    @staticmethod
    def _windows_canonical_path(path: str) -> pathlib.PureWindowsPath:
        if path.startswith("\\\\?\\UNC\\"):
            path = "\\\\" + path[8:]
        elif path.startswith("\\\\?\\"):
            path = path[4:]
        return pathlib.PureWindowsPath(ntpath.normpath(path))

    def _windows_paths(self) -> list[pathlib.PureWindowsPath]:
        assert self._windows_root is not None
        current = pathlib.PureWindowsPath(self._windows_root.anchor)
        paths = [current]
        for part in self._windows_root.parts[1:]:
            current = current / part
            paths.append(current)
        return paths

    def _windows_open_checked(
        self,
        path: pathlib.PureWindowsPath,
        *,
        directory: bool | None = None,
        expected_parent: pathlib.PureWindowsPath | None = None,
        expected_final: pathlib.PureWindowsPath | None = None,
        manager_lock: bool = False,
    ):
        assert self._windows_api is not None and self._windows_root is not None
        flags = self._windows_api.FILE_FLAG_OPEN_REPARSE_POINT | self._windows_api.FILE_FLAG_BACKUP_SEMANTICS
        share = self._windows_api.FILE_SHARE_READ
        if manager_lock:
            share |= self._windows_api.FILE_SHARE_WRITE
        handle = self._windows_api.open(str(path), flags=flags, share=share)
        try:
            metadata = self._windows_api.info(handle)
            if metadata.reparse:
                raise OSError(f"reparse point is forbidden: {path}")
            if not metadata.disk or metadata.kind not in {"file", "directory"}:
                raise OSError(f"special file is forbidden: {path}")
            if directory is True and metadata.kind != "directory":
                raise OSError(f"expected directory: {path}")
            if directory is False and metadata.kind != "file":
                raise OSError(f"expected regular file: {path}")
            final_path = self._windows_canonical_path(
                self._windows_api.final_path(handle)
            )
            if expected_parent is not None and self._windows_normalize(
                str(final_path.parent)
            ) != self._windows_normalize(str(expected_parent)):
                raise OSError(
                    f"opened handle final path escapes pinned directory chain: {path}"
                )
            if expected_final is not None and self._windows_normalize(
                str(final_path)
            ) != self._windows_normalize(str(expected_final)):
                raise OSError(
                    f"repository root canonical final path changed: {path}"
                )
            return handle, metadata, final_path
        except BaseException:
            self._windows_api.close(handle)
            raise

    def _windows_enter(self) -> "_SecureInstalledRoot":
        try:
            canonical_parent = None
            for path in self._windows_paths():
                handle, metadata, canonical_path = self._windows_open_checked(
                    path,
                    directory=True,
                    expected_parent=canonical_parent,
                )
                self._windows_handles.append(handle)
                canonical_parent = canonical_path
            self._windows_identity = metadata.identity
            self._windows_canonical_root = canonical_path
            return self
        except BaseException:
            for handle in reversed(self._windows_handles):
                self._windows_api.close(handle)
            self._windows_handles.clear()
            raise

    def _windows_verify(self) -> None:
        assert (
            self._windows_root is not None
            and self._windows_identity is not None
            and self._windows_canonical_root is not None
        )
        handle, metadata, _ = self._windows_open_checked(
            self._windows_root,
            directory=True,
            expected_final=self._windows_canonical_root,
        )
        try:
            if metadata.identity != self._windows_identity:
                raise OSError("repository root changed during validation")
        finally:
            self._windows_api.close(handle)

    @contextlib.contextmanager
    def _windows_open(self, relative: str, *, directory: bool | None = None):
        assert (
            self._windows_api is not None
            and self._windows_root is not None
            and self._windows_canonical_root is not None
        )
        pure = pathlib.PurePosixPath(relative)
        if pure.is_absolute() or any(part in {".."} or "\\" in part for part in pure.parts):
            raise OSError(f"unsafe relative path: {relative}")
        if not pure.parts or pure.parts == (".",):
            handle = self._windows_handles[-1]
            metadata = self._windows_api.info(handle)
            if directory is False:
                raise OSError(f"expected regular file: {relative}")
            yield handle, metadata
            return
        opened: list[int] = []
        current = self._windows_canonical_root
        canonical_parent = self._windows_canonical_root
        try:
            parts = [part for part in pure.parts if part not in {"", "."}]
            for index, part in enumerate(parts):
                current /= part
                expected = directory if index == len(parts) - 1 else True
                logical_path = pathlib.PurePosixPath(*parts[: index + 1]).as_posix()
                handle, metadata, canonical_path = self._windows_open_checked(
                    current,
                    directory=expected,
                    expected_parent=canonical_parent,
                    manager_lock=(logical_path == _MANAGER_LOCK),
                )
                opened.append(handle)
                current = canonical_path
                canonical_parent = canonical_path
            yield opened[-1], metadata
        finally:
            for handle in reversed(opened):
                self._windows_api.close(handle)

    def _windows_walk(
        self,
        descriptor: int,
        directory: pathlib.PureWindowsPath,
        prefix: pathlib.PurePosixPath,
        result: set[str],
    ) -> None:
        assert self._windows_api is not None
        for name in sorted(self._windows_api.listdir(descriptor)):
            if not name or name in {".", ".."} or "/" in name or "\\" in name:
                raise OSError(f"unsafe directory entry: {name!r}")
            path = directory / name
            relative = prefix / name
            try:
                handle, metadata, canonical_path = self._windows_open_checked(
                    path,
                    expected_parent=directory,
                    manager_lock=(relative.as_posix() == _MANAGER_LOCK),
                )
            except OSError as error:
                raise OSError(
                    f"unsafe operational path {relative.as_posix()}: {error}"
                ) from error
            try:
                if metadata.kind == "directory":
                    self._windows_walk(
                        handle, canonical_path, relative, result
                    )
                elif metadata.kind == "file":
                    result.add(relative.as_posix())
                else:
                    raise OSError(f"special file is forbidden: {relative.as_posix()}")
            finally:
                self._windows_api.close(handle)


@dataclasses.dataclass(frozen=True)
class _WindowsHandleInfo:
    identity: tuple[int, int]
    kind: str
    reparse: bool
    disk: bool
    size: int
    write_time: int


class _NativeWindowsApi:
    """Minimal ctypes Win32 surface for handle-pinned installed validation."""

    FILE_SHARE_READ = 0x1
    FILE_SHARE_WRITE = 0x2
    FILE_SHARE_DELETE = 0x4
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes

        class ByHandleFileInformation(ctypes.Structure):
            _fields_ = [
                ("dwFileAttributes", wintypes.DWORD),
                ("ftCreationTime", wintypes.FILETIME),
                ("ftLastAccessTime", wintypes.FILETIME),
                ("ftLastWriteTime", wintypes.FILETIME),
                ("dwVolumeSerialNumber", wintypes.DWORD),
                ("nFileSizeHigh", wintypes.DWORD),
                ("nFileSizeLow", wintypes.DWORD),
                ("nNumberOfLinks", wintypes.DWORD),
                ("nFileIndexHigh", wintypes.DWORD),
                ("nFileIndexLow", wintypes.DWORD),
            ]

        self.ByHandleFileInformation = ByHandleFileInformation
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(ByHandleFileInformation)]
        self.kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
        self.kernel32.GetFileType.argtypes = [wintypes.HANDLE]
        self.kernel32.GetFileType.restype = wintypes.DWORD
        self.kernel32.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        self.kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        self.kernel32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
        self.kernel32.SetFilePointerEx.restype = wintypes.BOOL
        self.kernel32.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        self.kernel32.ReadFile.restype = wintypes.BOOL

    def _error(self, operation: str) -> OSError:
        code = self.ctypes.get_last_error()
        return OSError(code, f"{operation} failed: {self.ctypes.FormatError(code)}")

    def open(self, path: str, *, flags: int, share: int) -> int:
        access = 0x0001 | 0x0080  # FILE_READ_DATA/LIST_DIRECTORY | FILE_READ_ATTRIBUTES
        handle = self.kernel32.CreateFileW(path, access, share, None, 3, flags, None)
        invalid = self.ctypes.c_void_p(-1).value
        if handle == invalid:
            raise self._error("CreateFileW")
        return int(handle)

    def close(self, handle: int) -> None:
        if not self.kernel32.CloseHandle(handle):
            raise self._error("CloseHandle")

    def info(self, handle: int) -> _WindowsHandleInfo:
        data = self.ByHandleFileInformation()
        if not self.kernel32.GetFileInformationByHandle(handle, self.ctypes.byref(data)):
            raise self._error("GetFileInformationByHandle")
        attributes = int(data.dwFileAttributes)
        identity = (int(data.dwVolumeSerialNumber), (int(data.nFileIndexHigh) << 32) | int(data.nFileIndexLow))
        size = (int(data.nFileSizeHigh) << 32) | int(data.nFileSizeLow)
        write_time = (int(data.ftLastWriteTime.dwHighDateTime) << 32) | int(data.ftLastWriteTime.dwLowDateTime)
        return _WindowsHandleInfo(
            identity=identity,
            kind="directory" if attributes & 0x10 else "file",
            reparse=bool(attributes & 0x400),
            disk=self.kernel32.GetFileType(handle) == 0x1,
            size=size,
            write_time=write_time,
        )

    def final_path(self, handle: int) -> str:
        size = self.kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)
        if not size:
            raise self._error("GetFinalPathNameByHandleW")
        buffer = self.ctypes.create_unicode_buffer(size + 1)
        written = self.kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise self._error("GetFinalPathNameByHandleW")
        return buffer.value

    def read(self, handle: int) -> bytes:
        if not self.kernel32.SetFilePointerEx(handle, 0, None, 0):
            raise self._error("SetFilePointerEx")
        chunks: list[bytes] = []
        while True:
            buffer = self.ctypes.create_string_buffer(1024 * 1024)
            count = self.wintypes.DWORD()
            if not self.kernel32.ReadFile(handle, buffer, len(buffer), self.ctypes.byref(count), None):
                raise self._error("ReadFile")
            if count.value == 0:
                return b"".join(chunks)
            chunks.append(buffer.raw[:count.value])

    def listdir(self, handle: int) -> list[str]:
        return os.listdir(self.final_path(handle))


def _installed_issue(path: str, message: str) -> ValidationIssue:
    return ValidationIssue("error", path, message)


def _load_installed_state(raw: bytes) -> tuple[dict[str, object] | None, list[ValidationIssue]]:
    try:
        document = json.loads(raw.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("installation state must be a JSON object")
        schema_version = document.get("schema_version")
        expected_keys = (
            _MIGRATION_STATE_KEYS
            if schema_version == 2 else _INSTALLED_STATE_KEYS
        )
        if set(document) != expected_keys:
            raise ValueError("installation state schema has missing or unknown fields")
        checksum = document.get("checksum")
        body = dict(document)
        body.pop("checksum", None)
        canonical = (json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        if not isinstance(checksum, str) or hashlib.sha256(canonical).hexdigest() != checksum:
            raise ValueError("installation state checksum mismatch")
        complete = (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        if raw != complete:
            raise ValueError("installation state is not canonical JSON")
        if schema_version == 2:
            if document.get("plugin_version") != _INSTALLED_VERSION:
                raise ValueError("unsupported migrated plugin version")
            if document.get("legacy_version") != "1.0.0":
                raise ValueError("unsupported migrated legacy version")
            legacy_state_checksum = document.get("legacy_state_checksum")
            if not isinstance(legacy_state_checksum, str) or not _HASH.fullmatch(
                legacy_state_checksum
            ):
                raise ValueError("invalid legacy state checksum")
            migrated_at = document.get("migrated_at")
            if not isinstance(migrated_at, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", migrated_at
            ):
                raise ValueError("malformed migrated_at")
            try:
                datetime.strptime(migrated_at, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as error:
                raise ValueError("malformed migrated_at") from error
            preserved = document.get("preserved_paths")
            if not isinstance(preserved, list):
                raise ValueError("preserved paths are malformed")
            normalized = [_normalize_installed_path(path) for path in preserved]
            if normalized != sorted(normalized) or len(normalized) != len(
                {path.casefold() for path in normalized}
            ):
                raise ValueError("preserved paths are unsorted or duplicated")
            return document, []
        if schema_version != 1:
            raise ValueError("unsupported installation state schema")
        if document.get("plugin_version") != _INSTALLED_VERSION:
            raise ValueError("unsupported installed plugin version")
        if not _HASH.fullmatch(str(document.get("payload_digest", ""))):
            raise ValueError("invalid payload provenance digest")
        for key in ("transaction_id", "installed_at", "validator_version"):
            if not isinstance(document.get(key), str) or not document[key]:
                raise ValueError(f"malformed {key}")
        parsed_uuid = uuid.UUID(document["transaction_id"])
        if str(parsed_uuid) != document["transaction_id"]:
            raise ValueError("malformed transaction_id")
        timestamp = datetime.fromisoformat(document["installed_at"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("malformed installed_at")
        if document.get("journal_status") not in {"clean", "committed"}:
            raise ValueError("installation journal is not terminal")
        if not isinstance(document.get("managed_paths"), list):
            raise ValueError("managed path ownership is missing")
        decisions = document.get("decisions")
        if not isinstance(decisions, list):
            raise ValueError("installation decisions are malformed")
        decision_bytes: list[bytes] = []
        decision_paths: list[str] = []
        shared_decisions: dict[str, str] = {}
        for decision in decisions:
            if not isinstance(decision, dict) or not isinstance(decision.get("path"), str):
                raise ValueError("installation decision is malformed")
            kind = decision.get("kind")
            path = _normalize_installed_path(decision["path"])
            if kind == "managed-block":
                if set(decision) != {"kind", "path", "outcome"} or decision.get("outcome") not in {"adopt", "merge"}:
                    raise ValueError("managed-block decision is malformed")
            elif kind == "toml-keys":
                if set(decision) != {"kind", "path", "outcome", "owned_values"} or decision.get("outcome") not in {"adopt", "merge"}:
                    raise ValueError("TOML decision is malformed")
                values = decision.get("owned_values")
                if not isinstance(values, dict) or set(values) != {"agents.max_depth", "agents.max_threads", "features.hooks"} or type(values["agents.max_depth"]) is not int or type(values["agents.max_threads"]) is not int or type(values["features.hooks"]) is not bool:
                    raise ValueError("TOML decision values are malformed")
            elif kind == "preserved-collision":
                if set(decision) != {"kind", "path", "reason", "target_hash"} or decision.get("reason") not in {"unmanaged-collision", "customized-managed-file", "historical-remnant"}:
                    raise ValueError("collision decision is malformed")
                target_hash = decision.get("target_hash")
                if target_hash is not None and not _HASH.fullmatch(str(target_hash)):
                    raise ValueError("collision decision hash is malformed")
            else:
                raise ValueError("unknown installation decision kind")
            if kind in {"managed-block", "toml-keys"}:
                shared_decisions[path] = str(kind)
            decision_paths.append(path.casefold())
            decision_bytes.append((json.dumps(decision, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode())
        if decision_bytes != sorted(decision_bytes) or len(decision_bytes) != len(set(decision_bytes)) or len(decision_paths) != len(set(decision_paths)):
            raise ValueError("installation decisions are unsorted or duplicated")
        records = document["managed_paths"]
        record_paths: list[str] = []
        shared_records: dict[str, str] = {}
        projection: list[list[object]] = []
        for record in records:
            if not isinstance(record, dict) or set(record) != _INSTALLED_PATH_KEYS:
                raise ValueError("managed path record is malformed")
            path = _normalize_installed_path(record.get("path"))
            ownership, merge = record.get("ownership"), record.get("merge")
            installed_hash, block_hash = record.get("installed_hash"), record.get("block_hash")
            if ownership not in {"dedicated", "shared"} or (ownership == "dedicated" and merge is not None) or (ownership == "shared" and merge not in {"managed-block", "toml-keys"}):
                raise ValueError("managed ownership contract is malformed")
            if installed_hash is not None and not _HASH.fullmatch(str(installed_hash)):
                raise ValueError("installed ownership hash is malformed")
            if ownership == "shared" and installed_hash is None:
                raise ValueError("shared installed hash is missing")
            if merge == "managed-block":
                if not _HASH.fullmatch(str(block_hash)):
                    raise ValueError("managed block hash is malformed")
            elif block_hash is not None:
                raise ValueError("unexpected managed block hash")
            record_paths.append(path)
            if ownership == "shared":
                shared_records[path] = str(merge)
            expected_hash = installed_hash if ownership == "dedicated" and path != "tools/codex_studio/validate.py" else None
            projection.append([path, ownership, merge, "directory" if installed_hash is None else "file", expected_hash])
        if record_paths != sorted(record_paths) or len(record_paths) != len({path.casefold() for path in record_paths}):
            raise ValueError("managed paths are unsorted or duplicated")
        if shared_records != shared_decisions:
            raise ValueError("shared ownership decisions do not match managed paths")
        projection_bytes = (json.dumps(projection, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        if len(projection) != _INSTALLED_INVENTORY_ENTRY_COUNT or hashlib.sha256(projection_bytes).hexdigest() != _INSTALLED_INVENTORY_SHA256:
            raise ValueError("authenticated installed inventory does not match")
        return document, []
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError, KeyError) as error:
        return None, [_installed_issue(_INSTALLATION_STATE, str(error))]


def _normalize_installed_path(value: object) -> str:
    if not isinstance(value, str) or not value or unicodedata.normalize("NFC", value) != value or "\\" in value or "\x00" in value:
        raise ValueError("managed path is unsafe or not NFC-normalized")
    pure = pathlib.PurePosixPath(value)
    if pure.is_absolute() or pure.as_posix() != value or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("managed path is unsafe or non-normalized")
    return value


def _validate_shared_content(record: dict[str, object], decisions: list[object], content: bytes) -> list[ValidationIssue]:
    path = str(record["path"])
    merge = record["merge"]
    if merge == "managed-block":
        start = b"<!-- codex-game-studios:start -->"
        end = b"<!-- codex-game-studios:end -->"
        if content.count(start) != 1 or content.count(end) != 1 or content.index(start) >= content.index(end):
            return [_installed_issue(path, "managed block markers are missing or malformed")]
        line_end = content.find(b"\n", content.index(end))
        stop = len(content) if line_end < 0 else line_end + 1
        block = content[content.rfind(b"\n", 0, content.index(start)) + 1:stop]
        candidates = {hashlib.sha256(block).hexdigest(), hashlib.sha256(b"\n" + block).hexdigest()}
        if record["block_hash"] not in candidates:
            return [_installed_issue(path, "managed block differs from recorded ownership hash")]
    elif merge == "toml-keys":
        decision = next(item for item in decisions if isinstance(item, dict) and item.get("kind") == "toml-keys" and item.get("path") == path)
        try:
            parsed = tomllib.loads(content.decode("utf-8"))
            actual = {
                "agents.max_depth": parsed["agents"]["max_depth"],
                "agents.max_threads": parsed["agents"]["max_threads"],
                "features.hooks": parsed["features"]["hooks"],
            }
        except (UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as error:
            return [_installed_issue(path, f"owned TOML contract is invalid: {error}")]
        if actual != decision["owned_values"]:
            return [_installed_issue(path, "owned TOML values differ from installation state")]
    return []


def _validate_installed_repository_secure(root: pathlib.Path) -> tuple[list[ValidationIssue], bytes | None]:
    """Return installed issues and the exact securely read canonical state."""

    issues: list[ValidationIssue] = []
    state_raw: bytes | None = None
    try:
        with _SecureInstalledRoot(pathlib.Path(root)) as secure:
            state_raw = secure.read(_INSTALLATION_STATE)
            state, state_issues = _load_installed_state(state_raw)
            if state is None:
                return state_issues, state_raw
            if state.get("schema_version") == 2:
                preserved = state["preserved_paths"]
                assert isinstance(preserved, list)
                for path in preserved:
                    try:
                        secure.kind(str(path))
                    except OSError as error:
                        issues.append(_installed_issue(
                            str(path), f"recorded preserved path is unavailable: {error}"
                        ))
                secure.verify()
                return sorted(
                    issues, key=lambda issue: (issue.path, issue.message)
                ), state_raw
            records = state["managed_paths"]
            decisions = state["decisions"]
            assert isinstance(records, list) and isinstance(decisions, list)
            recorded_files: set[str] = set()
            configured_files: set[str] = set()
            try:
                studio = tomllib.loads(secure.read(".codex/studio.toml").decode("utf-8"))
                expected_studio_fields = {"engine", "engine_version", "language", "review_mode", "active_engine_pack", "model_policy"}
                if set(studio) != expected_studio_fields or any(not isinstance(studio.get(key), str) for key in expected_studio_fields):
                    raise ValueError("studio config fields are not exact strings")
                if studio["review_mode"] != "phase-gated" or studio["model_policy"] != "balanced":
                    raise ValueError("non-engine studio authority differs from installed baseline")
                expected_active_names = _expected_active_agents_for_pack(
                    studio["active_engine_pack"]
                )
                engine = studio.get("engine")
                active_pack = studio.get("active_engine_pack")
                if engine == "unconfigured" and active_pack != "none":
                    raise ValueError("unconfigured studio must not activate an engine pack")
                if engine in EXPECTED_PACK_NAMES:
                    if active_pack != engine:
                        raise ValueError("configured engine and active pack differ")
                    allowed_languages = {
                        "godot": {"gdscript", "csharp"},
                        "unity": {"csharp"},
                        "unreal": {"cpp", "blueprint", "cpp-blueprint"},
                    }
                    version = studio["engine_version"]
                    language = studio["language"]
                    if not version or version != version.strip() or any(unicodedata.category(character).startswith("C") or unicodedata.category(character) in {"Zl", "Zp"} for character in version):
                        raise ValueError("configured engine version is invalid")
                    if language not in allowed_languages[engine]:
                        raise ValueError("configured engine language is invalid")
                    active = json.loads(secure.read(".codex/active-engine.json").decode("utf-8"))
                    generated = active.get("generated") if isinstance(active, dict) and active.get("engine") == engine else None
                    expected_names = {
                        f"{name}.toml"
                        for name in expected_active_names - EXPECTED_CORE_NAMES
                    }
                    if not isinstance(generated, dict) or set(generated) != expected_names:
                        raise ValueError("active engine manifest does not declare exactly five profiles")
                    for name, expected_hash in generated.items():
                        if not _HASH.fullmatch(str(expected_hash)):
                            raise ValueError("active engine manifest contains an invalid hash")
                        active_path = f".codex/agents/{name}"
                        pack_path = f".codex/agent-packs/{engine}/{name}"
                        active_content = secure.read(active_path)
                        pack_content = secure.read(pack_path)
                        if hashlib.sha256(active_content).hexdigest() != expected_hash or active_content != pack_content:
                            raise ValueError(f"active profile does not match immutable pack: {name}")
                        configured_files.add(active_path)
                elif engine != "unconfigured":
                    raise ValueError("unsupported configured engine")
            except (OSError, UnicodeError, tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError) as error:
                issues.append(_installed_issue(".codex/studio.toml", f"configured routing is invalid: {error}"))
            for record in records:
                assert isinstance(record, dict)
                path = str(record["path"])
                expected_kind = "directory" if record["installed_hash"] is None else "file"
                try:
                    actual_kind = secure.kind(path)
                    if actual_kind != expected_kind:
                        issues.append(_installed_issue(path, f"managed path has wrong type: expected {expected_kind}"))
                        continue
                    if actual_kind == "file":
                        content = secure.read(path)
                        recorded_files.add(path)
                        if record["ownership"] == "shared":
                            issues.extend(_validate_shared_content(record, decisions, content))
                        elif path == ".codex/studio.toml" and configured_files:
                            pass
                        elif hashlib.sha256(content).hexdigest() != record["installed_hash"]:
                            issues.append(_installed_issue(path, "managed file differs from recorded ownership hash"))
                except OSError as error:
                    issues.append(_installed_issue(path, f"secure managed-path inspection failed: {error}"))

            control_files = secure.walk_files(".codex/codex-game-studios")
            for path in control_files:
                relative = pathlib.PurePosixPath(path).relative_to(".codex/codex-game-studios").as_posix()
                if relative != "installation.json" and not relative.startswith(("legal/", "recovery/")) and relative != "manager.lock":
                    issues.append(_installed_issue(path, "unrecorded manager write"))
            for operational_root in (
                ".agents/skills", ".codex/agents", ".codex/agent-packs", ".codex/hooks",
                ".codex/docs", "tools/codex_studio", "Codex Studio Testing Framework",
                "docs/engine-reference",
            ):
                try:
                    operational_files = secure.walk_files(operational_root)
                except OSError as error:
                    issues.append(_installed_issue(operational_root, f"secure operational-tree inspection failed: {error}"))
                    continue
                for path in operational_files:
                    if path not in recorded_files and path not in configured_files:
                        issues.append(_installed_issue(path, "unrecorded write beneath manager-owned operational root"))
            secure.verify()
    except (OSError, ValueError) as error:
        issues.append(_installed_issue(".", f"secure installed validation failed: {error}"))
    return sorted(issues, key=lambda issue: (issue.path, issue.message)), state_raw


def validate_installed_repository(root: pathlib.Path) -> list[ValidationIssue]:
    """Securely validate a checksum-bound installed operational repository."""

    return _validate_installed_repository_secure(root)[0]


def validate_plugin_native_project(
    target_root: pathlib.Path, *, source_root: pathlib.Path,
) -> list[ValidationIssue]:
    """Validate fresh plugin-native engine activation without legacy payload state."""

    target_input = pathlib.Path(target_root).absolute()
    source_input = pathlib.Path(source_root).absolute()
    target = target_input.resolve()
    source = source_input.resolve()
    trusted_source = pathlib.Path(__file__).resolve().parents[2]
    if source.resolve() != trusted_source:
        return [_installed_issue("--source-root", "plugin-native source root must equal this validator's bundled studio root")]
    if source.resolve() == target.resolve():
        return [_installed_issue("--source-root", "plugin-native source root must differ from the target root")]
    activation_issues = validate_activation(target_input, source_root=source_input)
    if activation_issues:
        return [_installed_issue(".codex", issue) for issue in activation_issues]
    issues: list[ValidationIssue] = []
    try:
        with _SecureInstalledRoot(target) as target_secure, _SecureInstalledRoot(source) as source_secure:
            studio = tomllib.loads(target_secure.read(".codex/studio.toml").decode("utf-8"))
            fields = {
                "engine", "engine_version", "language", "review_mode", "active_engine_pack", "model_policy",
            }
            if set(studio) != fields or any(not isinstance(studio.get(key), str) for key in fields):
                raise ValueError("studio configuration must contain exactly six string authority fields")
            engine = studio["engine"]
            active_pack = studio["active_engine_pack"]
            if engine == "unconfigured":
                if active_pack != "none":
                    raise ValueError("unconfigured project has an active engine pack")
                for relative in (".codex/active-engine.json", ".codex/agents"):
                    try:
                        target_secure.kind(relative)
                    except OSError:
                        continue
                    raise ValueError("unconfigured project retains active engine state")
            elif engine in EXPECTED_PACK_NAMES and active_pack == engine:
                expected_names = {f"{name}.toml" for name in EXPECTED_PACK_NAMES[engine]}
                manifest = json.loads(target_secure.read(".codex/active-engine.json").decode("utf-8"))
                generated = manifest.get("generated") if isinstance(manifest, dict) and manifest.get("engine") == engine else None
                if not isinstance(generated, dict) or set(generated) != expected_names:
                    raise ValueError("active engine manifest does not declare exactly five selected profiles")
                source_paths = source_secure.walk_files(f".codex/agent-packs/{engine}")
                if source_paths != {f".codex/agent-packs/{engine}/{name}" for name in expected_names}:
                    raise ValueError("selected source engine pack does not contain exactly five expected profiles")
                for name in sorted(expected_names):
                    expected_hash = generated[name]
                    if not isinstance(expected_hash, str) or not _HASH.fullmatch(expected_hash):
                        raise ValueError(f"active engine manifest hash is invalid: {name}")
                    active = target_secure.read(f".codex/agents/{name}")
                    source_profile = source_secure.read(f".codex/agent-packs/{engine}/{name}")
                    if hashlib.sha256(active).hexdigest() != expected_hash or active != source_profile:
                        raise ValueError(f"active profile does not match selected source pack: {name}")
            else:
                raise ValueError("configured engine and active pack are invalid or disagree")
            target_secure.verify()
            source_secure.verify()
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, json.JSONDecodeError, ValueError) as error:
        issues.append(_installed_issue(".codex", f"plugin-native validation failed: {error}"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Codex Game Studios")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--mode", choices=("source", "installed", "plugin-native"), default="source")
    parser.add_argument("--phase", choices=("pre-cleanup", "final"), default="final")
    parser.add_argument("--skill-file", type=pathlib.Path)
    parser.add_argument("--source-root", type=pathlib.Path)
    args = parser.parse_args(argv)
    if args.skill_file is not None:
        if args.mode != "source" or args.source_root is not None:
            parser.error("--skill-file cannot be combined with --mode or --source-root")
        issues = validate_skill(args.skill_file)
        for issue in issues:
            print(f"{issue.severity.upper()} {issue.path}: {issue.message}")
        if any(issue.severity == "error" for issue in issues):
            print("Skill validation: FAIL")
            return 1
        print("Skill validation: PASS")
        return 0
    if args.mode == "plugin-native":
        if args.source_root is None:
            parser.error("--mode plugin-native requires --source-root")
        if args.phase != "final":
            parser.error("--mode plugin-native requires --phase final")
        issues = validate_plugin_native_project(args.root, source_root=args.source_root)
    else:
        if args.source_root is not None:
            parser.error("--source-root is only valid with --mode plugin-native")
        issues = validate_repository(args.root, args.phase) if args.mode == "source" else validate_installed_repository(args.root)
    for issue in issues:
        print(f"{issue.severity.upper()} {issue.path}: {issue.message}")
    if any(issue.severity == "error" for issue in issues):
        print("Codex Studio validation: FAIL")
        return 1
    print("Codex Studio validation: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
