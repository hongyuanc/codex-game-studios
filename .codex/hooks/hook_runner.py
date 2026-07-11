#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
from typing import Callable


ACTIONS = {
    "session-start",
    "detect-gaps",
    "validate-command",
    "validate-assets",
    "validate-skill-change",
    "pre-compact",
    "post-compact",
    "subagent-start",
    "subagent-stop",
    "session-stop",
}
SOURCE_SUFFIXES = {".gd", ".cs", ".cpp", ".c", ".h", ".hpp", ".rs", ".py", ".js", ".ts"}
GDD_SECTIONS = (
    "Overview",
    "Player Fantasy",
    "Detailed Rules",
    "Formulas",
    "Edge Cases",
    "Dependencies",
    "Tuning Knobs",
    "Acceptance Criteria",
)
DESTRUCTIVE_GIT = re.compile(
    r"\bgit\s+(?:"
    r"reset\s+--hard\b|"
    r"clean\s+-[^\s;|&]*f[^\s;|&]*|"
    r"push\b[^\n;|&]*(?:--force(?:-with-lease)?\b|(?:^|\s)-f(?:\s|$))"
    r")",
    re.MULTILINE,
)


@dataclasses.dataclass(frozen=True)
class HookResult:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _system_message(message: str) -> HookResult:
    return HookResult(stdout=json.dumps({"systemMessage": message}, ensure_ascii=False) + "\n")


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _relative_files(root: pathlib.Path, directory: str, suffix: str | None = None) -> list[pathlib.Path]:
    base = root / directory
    if not base.is_dir():
        return []
    return [
        path
        for path in base.rglob("*")
        if path.is_file() and (suffix is None or path.suffix == suffix)
    ]


def tool_command(event: dict) -> str:
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command", ""))


def changed_paths(event: dict) -> set[str]:
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return set()
    direct_path = tool_input.get("file_path")
    paths = {str(direct_path)} if direct_path else set()
    paths.update(
        re.findall(
            r"^\*\*\* (?:Add|Update|Delete) File: (.+)$",
            tool_command(event),
            re.MULTILINE,
        )
    )
    return {path.strip().replace("\\", "/") for path in paths if path.strip()}


def repository_paths(event: dict, root: pathlib.Path) -> set[str]:
    root = root.resolve()
    safe: set[str] = set()
    for raw_path in changed_paths(event):
        candidate = pathlib.Path(raw_path)
        candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] != ".git":
            safe.add(relative.as_posix())
    return safe


def _staged_paths(root: pathlib.Path) -> list[str]:
    result = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _staged_text(root: pathlib.Path, relative: str) -> str | None:
    result = _git(root, "show", f":{relative}")
    return result.stdout if result.returncode == 0 else None


def _validate_commit(root: pathlib.Path) -> HookResult:
    warnings: list[str] = []
    for relative in _staged_paths(root):
        text = _staged_text(root, relative)
        if text is None:
            continue
        if relative.startswith("assets/data/") and relative.endswith(".json"):
            try:
                json.loads(text)
            except json.JSONDecodeError:
                return HookResult(2, stderr=f"BLOCKED: {relative} is not valid JSON\n")
        if relative.startswith("design/gdd/") and relative.endswith(".md"):
            for section in GDD_SECTIONS:
                if not re.search(rf"^#+\s+{re.escape(section)}\s*$", text, re.IGNORECASE | re.MULTILINE):
                    warnings.append(f"DESIGN: {relative} missing required section: {section}")
        if relative.startswith("src/gameplay/") and re.search(
            r"\b(?:damage|health|speed|rate|chance|cost|duration)\s*[:=]\s*[0-9]+",
            text,
            re.IGNORECASE,
        ):
            warnings.append(f"CODE: {relative} may contain a hardcoded gameplay value; use data files.")
        if relative.startswith("src/") and re.search(
            r"\b(?:TODO|FIXME|HACK)\b(?!\([^\n)]+\))",
            text,
        ):
            warnings.append(f"STYLE: {relative} has a malformed TODO/FIXME/HACK; use TODO(name) format.")
    if warnings:
        return _system_message("Commit validation warnings:\n" + "\n".join(warnings))
    return HookResult()


def _protected_push(command: str, root: pathlib.Path) -> HookResult:
    if not re.search(r"\bgit\s+push\b", command):
        return HookResult()
    protected = {"develop", "main", "master"}
    explicit = next(
        (branch for branch in sorted(protected) if re.search(rf"(?:^|\s){branch}(?:\s|$)", command)),
        None,
    )
    branch_result = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    current = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    branch = explicit or (current if current in protected else "")
    if branch:
        return _system_message(
            f"Push to protected branch '{branch}' detected. Verify the build and unit tests pass and no S1/S2 bugs remain."
        )
    return HookResult()


def _validate_command(event: dict, root: pathlib.Path) -> HookResult:
    command = tool_command(event)
    if DESTRUCTIVE_GIT.search(command):
        return HookResult(
            2,
            stderr="Destructive Git command blocked by Codex Game Studios policy.\n",
        )
    if re.search(r"\bgit\s+commit\b", command):
        return _validate_commit(root)
    return _protected_push(command, root)


def _validate_assets(event: dict, root: pathlib.Path) -> HookResult:
    warnings: list[str] = []
    for relative in sorted(repository_paths(event, root)):
        if not relative.startswith("assets/"):
            continue
        path = root / relative
        filename = path.name
        if re.search(r"[A-Z\s-]", filename):
            warnings.append(f"NAMING: {relative} must use lowercase names with underscores.")
        if relative.startswith("assets/data/") and relative.endswith(".json") and path.is_file():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                warnings.append(f"FORMAT: {relative} is not valid JSON; fix it before commit.")
    if warnings:
        return _system_message("Asset validation warnings:\n" + "\n".join(warnings))
    return HookResult()


def _validate_skill_change(event: dict, root: pathlib.Path) -> HookResult:
    skills: set[str] = set()
    for relative in repository_paths(event, root):
        match = re.match(r"\.agents/skills/([^/]+)/", relative)
        if match:
            skills.add(match.group(1))
    if not skills:
        return HookResult()
    commands = ", ".join(f"$skill-test static {skill}" for skill in sorted(skills))
    return _system_message(f"Skill files changed. Run {commands} before handoff.")


def _latest_markdown(root: pathlib.Path, relative: str, pattern: str = "*.md") -> pathlib.Path | None:
    directory = root / relative
    if not directory.is_dir():
        return None
    candidates = list(directory.glob(pattern))
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _session_start(event: dict, root: pathlib.Path) -> HookResult:
    del event
    lines = ["=== Codex Game Studios — Session Context ==="]
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch.returncode == 0 and branch.stdout.strip():
        lines.append(f"Branch: {branch.stdout.strip()}")
        recent = _git(root, "log", "--oneline", "-5")
        if recent.returncode == 0 and recent.stdout.strip():
            lines.extend(["Recent commits:", *[f"  {line}" for line in recent.stdout.splitlines()]])
    sprint = _latest_markdown(root, "production/sprints", "sprint-*.md")
    milestone = _latest_markdown(root, "production/milestones")
    if sprint:
        lines.append(f"Active sprint: {sprint.stem}")
    if milestone:
        lines.append(f"Active milestone: {milestone.stem}")
    bugs = sum(len(list((root / directory).rglob("BUG-*.md"))) for directory in ("tests/playtest", "production") if (root / directory).is_dir())
    if bugs:
        lines.append(f"Open bugs: {bugs}")
    source_files = _relative_files(root, "src")
    todos = sum(path.read_text(encoding="utf-8", errors="ignore").count("TODO") for path in source_files)
    fixmes = sum(path.read_text(encoding="utf-8", errors="ignore").count("FIXME") for path in source_files)
    if todos or fixmes:
        lines.append(f"Code health: {todos} TODOs, {fixmes} FIXMEs in src/")
    state = root / "production/session-state/active.md"
    if state.is_file():
        state_lines = state.read_text(encoding="utf-8", errors="replace").splitlines()
        lines.extend(
            [
                "Active session state detected at production/session-state/active.md; read it to continue.",
                "Quick summary:",
                *state_lines[-20:],
            ]
        )
    lines.append("===================================")
    return HookResult(stdout="\n".join(lines) + "\n")


def _detect_gaps(event: dict, root: pathlib.Path) -> HookResult:
    del event
    source_files = [path for path in _relative_files(root, "src") if path.suffix.lower() in SOURCE_SUFFIXES]
    design_files = _relative_files(root, "design/gdd", ".md")
    engine_text = ""
    preferences = root / ".codex/docs/technical-preferences.md"
    if preferences.is_file():
        engine_text = preferences.read_text(encoding="utf-8", errors="ignore")
    fresh = not source_files and not (root / "design/gdd/game-concept.md").is_file() and (
        not engine_text or "TO BE CONFIGURED" in engine_text or "[CHOOSE" in engine_text
    )
    lines = ["=== Checking for Documentation Gaps ==="]
    if fresh:
        lines.append("NEW PROJECT: no configured engine, game concept, or source code. Run $start.")
    if len(source_files) > 50 and len(design_files) < 5:
        lines.append(f"GAP: {len(source_files)} source files but only {len(design_files)} design documents. Run $reverse-document or $project-stage-detect.")
    prototypes = root / "prototypes"
    if prototypes.is_dir():
        undocumented = sorted(path.name for path in prototypes.iterdir() if path.is_dir() and not (path / "README.md").is_file() and not (path / "CONCEPT.md").is_file())
        if undocumented:
            lines.append("GAP: undocumented prototypes: " + ", ".join(undocumented) + ". Run $reverse-document.")
    if (root / "src/core").is_dir():
        adrs = _relative_files(root, "docs/architecture", ".md")
        if len(adrs) < 3:
            lines.append(f"GAP: core systems exist but only {len(adrs)} architecture records. Run $architecture-decision.")
    gameplay = root / "src/gameplay"
    if gameplay.is_dir():
        for system in sorted(path for path in gameplay.iterdir() if path.is_dir()):
            count = sum(1 for path in system.rglob("*") if path.is_file())
            if count >= 5 and not (root / f"design/gdd/{system.name}-system.md").is_file() and not (root / f"design/gdd/{system.name}.md").is_file():
                lines.append(f"GAP: gameplay system {system.name} has {count} files and no design document. Run $reverse-document.")
    if len(source_files) > 100 and not (root / "production/sprints").is_dir() and not (root / "production/milestones").is_dir():
        lines.append("GAP: large codebase has no production planning. Run $sprint-plan.")
    lines.append("For a complete analysis, run $project-stage-detect.")
    return HookResult(stdout="\n".join(lines) + "\n")


def _append(root: pathlib.Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(text)


def _pre_compact(event: dict, root: pathlib.Path) -> HookResult:
    del event
    lines = ["Session state before compaction", f"Timestamp: {_now()}"]
    state = root / "production/session-state/active.md"
    if state.is_file():
        state_lines = state.read_text(encoding="utf-8", errors="replace").splitlines()
        lines.extend(["Active session state:", *state_lines[:100]])
        if len(state_lines) > 100:
            lines.append(f"... truncated ({len(state_lines)} total lines)")
    else:
        lines.append("No active session state file; consider maintaining production/session-state/active.md.")
    for title, args in (
        ("Unstaged changes", ("diff", "--name-only")),
        ("Staged changes", ("diff", "--cached", "--name-only")),
        ("Untracked files", ("ls-files", "--others", "--exclude-standard")),
    ):
        result = _git(root, *args)
        if result.returncode == 0 and result.stdout.strip():
            lines.extend([title + ":", *[f"- {item}" for item in result.stdout.splitlines()]])
    wip: list[str] = []
    for path in _relative_files(root, "design/gdd", ".md"):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if re.search(r"TODO|WIP|PLACEHOLDER|\[TO BE|\[TBD\]", line):
                wip.append(f"{path.relative_to(root).as_posix()}:{number}: {line}")
    if wip:
        lines.extend(["Design documents in progress:", *wip])
    lines.append("After compaction, read production/session-state/active.md and the files listed above.")
    _append(root, "production/session-logs/compaction-log.txt", f"Context compaction occurred at {_now()}.\n")
    return _system_message("\n".join(lines))


def _post_compact(event: dict, root: pathlib.Path) -> HookResult:
    del event
    state = root / "production/session-state/active.md"
    if state.is_file():
        count = len(state.read_text(encoding="utf-8", errors="replace").splitlines())
        message = f"Context restored. Read production/session-state/active.md ({count} lines) now to restore task decisions and open questions."
    else:
        message = "Context restored. No production/session-state/active.md exists; inspect production/session-logs/ if work was in progress."
    return _system_message(message)


def _agent_name(event: dict) -> str:
    for field in ("agent_type", "agent_name", "agent_id"):
        value = event.get(field)
        if value:
            return str(value).replace("\n", " ")[:160]
    return "unknown"


def _subagent_start(event: dict, root: pathlib.Path) -> HookResult:
    _append(root, "production/session-logs/agent-audit.log", f"{_now()} | Agent invoked: {_agent_name(event)}\n")
    return HookResult()


def _subagent_stop(event: dict, root: pathlib.Path) -> HookResult:
    _append(root, "production/session-logs/agent-audit.log", f"{_now()} | Agent completed: {_agent_name(event)}\n")
    return HookResult()


def _session_stop(event: dict, root: pathlib.Path) -> HookResult:
    del event
    state = root / "production/session-state/active.md"
    sections: list[str] = []
    if state.is_file():
        sections.extend([f"## Archived Session State: {_stamp()}", state.read_text(encoding="utf-8", errors="replace"), "---", ""])
    commits = _git(root, "log", "--oneline", "--since=8 hours ago")
    modified = _git(root, "diff", "--name-only")
    if (commits.returncode == 0 and commits.stdout.strip()) or (modified.returncode == 0 and modified.stdout.strip()):
        sections.append(f"## Session End: {_stamp()}")
        if commits.stdout.strip():
            sections.extend(["### Commits", commits.stdout.rstrip()])
        if modified.stdout.strip():
            sections.extend(["### Uncommitted Changes", modified.stdout.rstrip()])
        sections.extend(["---", ""])
    if sections:
        _append(root, "production/session-logs/session-log.md", "\n".join(sections) + "\n")
    return HookResult()


HANDLERS: dict[str, Callable[[dict, pathlib.Path], HookResult]] = {
    "session-start": _session_start,
    "detect-gaps": _detect_gaps,
    "validate-command": _validate_command,
    "validate-assets": _validate_assets,
    "validate-skill-change": _validate_skill_change,
    "pre-compact": _pre_compact,
    "post-compact": _post_compact,
    "subagent-start": _subagent_start,
    "subagent-stop": _subagent_stop,
    "session-stop": _session_stop,
}


def handle(action: str, event: dict, root: pathlib.Path) -> HookResult:
    handler = HANDLERS.get(action)
    if handler is None:
        return _system_message(f"Unknown Codex Game Studios hook action '{action}'; continuing without it.")
    try:
        return handler(event, root.resolve())
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        return _system_message(f"Hook action '{action}' could not complete ({error}); continuing.")


def _repository_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(event, dict) or len(argv) < 2:
        return 0
    result = handle(argv[1], event, _repository_root())
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
