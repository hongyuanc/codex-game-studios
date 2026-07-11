#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import pathlib
import re
import shlex
import stat
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
SHELL_BOUNDARIES = {";", "&", "&&", "|", "||", "(", ")", "{", "}", "\n"}
SHELL_COMMAND_PREFIXES = {"!", "do", "elif", "else", "if", "then", "time", "until", "while"}
GIT_GLOBAL_VALUE_OPTIONS = {
    "-C",
    "-c",
    "--config-env",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--super-prefix",
    "--work-tree",
}
GIT_GLOBAL_FLAG_OPTIONS = {
    "-p",
    "--paginate",
    "--no-pager",
    "--bare",
    "--no-replace-objects",
    "--literal-pathspecs",
    "--glob-pathspecs",
    "--noglob-pathspecs",
    "--icase-pathspecs",
    "--no-optional-locks",
    "--no-advice",
}
GIT_GLOBAL_TERMINAL_OPTIONS = {"--version", "--help", "-h", "--html-path", "--man-path", "--info-path"}
PROTECTED_BRANCHES = {"develop", "main", "master"}


@dataclasses.dataclass(frozen=True)
class HookResult:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclasses.dataclass(frozen=True)
class GitInvocation:
    subcommand: str
    args: tuple[str, ...]


class UnsafePathError(OSError):
    pass


class StagedInspectionError(OSError):
    pass


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


def _heredoc_specs(line: str) -> list[tuple[str, bool]]:
    specs: list[tuple[str, bool]] = []
    index = 0
    quote: str | None = None
    while index < len(line):
        character = line[index]
        if quote:
            if character == quote:
                quote = None
            elif character == "\\" and quote == '"':
                index += 1
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "#":
            break
        if character == "\\":
            index += 2
            continue
        if line.startswith("<<<", index) or not line.startswith("<<", index):
            index += 1
            continue
        cursor = index + 2
        strip_tabs = cursor < len(line) and line[cursor] == "-"
        if strip_tabs:
            cursor += 1
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1
        delimiter_quote = line[cursor] if cursor < len(line) and line[cursor] in {"'", '"'} else None
        if delimiter_quote:
            cursor += 1
            end = line.find(delimiter_quote, cursor)
            if end == -1:
                break
            delimiter = line[cursor:end]
            index = end + 1
        else:
            match = re.match(r"[^\s;&|<>]+", line[cursor:])
            if not match:
                index = cursor + 1
                continue
            delimiter = match.group(0)
            index = cursor + len(delimiter)
        if delimiter:
            specs.append((delimiter, strip_tabs))
    return specs


def _strip_heredoc_bodies(script: str) -> str:
    lines = script.splitlines(keepends=True)
    output: list[str] = []
    pending: list[tuple[str, bool]] = []
    for line in lines:
        if pending:
            delimiter, strip_tabs = pending[0]
            candidate = line.rstrip("\r\n")
            if strip_tabs:
                candidate = candidate.lstrip("\t")
            output.append("\n" if line.endswith("\n") else "")
            if candidate == delimiter:
                pending.pop(0)
            continue
        output.append(line)
        pending.extend(_heredoc_specs(line))
    return "".join(output)


def _shell_segments(script: str) -> list[list[str]]:
    prepared = re.sub(r"\\\r?\n", " ", _strip_heredoc_bodies(script))
    lexer = shlex.shlex(prepared, posix=True, punctuation_chars=";&|(){}<>\n")
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in SHELL_BOUNDARIES or any(character in token for character in ";&|(){}\n"):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _command_tokens(segment: list[str]) -> list[str]:
    tokens = list(segment)
    while tokens and tokens[0] in SHELL_COMMAND_PREFIXES:
        tokens.pop(0)
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens.pop(0)
    if tokens and tokens[0] == "env":
        tokens.pop(0)
        while tokens and (tokens[0].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0])):
            tokens.pop(0)
    while tokens and tokens[0] in {"command", "builtin", "exec", "sudo"}:
        tokens.pop(0)
        while tokens and tokens[0].startswith("-"):
            tokens.pop(0)
    return tokens


def _git_invocation(segment: list[str]) -> GitInvocation | None:
    tokens = _command_tokens(segment)
    if not tokens or pathlib.PurePosixPath(tokens[0]).name != "git":
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in GIT_GLOBAL_TERMINAL_OPTIONS:
            return None
        if token in GIT_GLOBAL_FLAG_OPTIONS:
            index += 1
            continue
        if token in GIT_GLOBAL_VALUE_OPTIONS:
            if index + 1 >= len(tokens):
                return None
            index += 2
            continue
        if any(token.startswith(option + "=") for option in GIT_GLOBAL_VALUE_OPTIONS if option.startswith("--")):
            index += 1
            continue
        if (token.startswith("-C") and token != "-C") or (token.startswith("-c") and token != "-c"):
            index += 1
            continue
        if token.startswith("-"):
            return None
        break
    if index >= len(tokens):
        return None
    return GitInvocation(tokens[index], tuple(tokens[index + 1 :]))


def git_invocations(script: str) -> list[GitInvocation]:
    invocations = [invocation for segment in _shell_segments(script) if (invocation := _git_invocation(segment))]
    return invocations


def _short_flag(args: tuple[str, ...], flag: str) -> bool:
    return any(
        token.startswith("-")
        and not token.startswith("--")
        and flag in token[1:]
        for token in args
    )


def _dry_run(invocation: GitInvocation) -> bool:
    return "--dry-run" in invocation.args or _short_flag(invocation.args, "n")


def _destructive(invocation: GitInvocation) -> bool:
    if invocation.subcommand == "reset":
        return "--hard" in invocation.args
    if invocation.subcommand == "clean":
        forced = "--force" in invocation.args or _short_flag(invocation.args, "f")
        return forced and not _dry_run(invocation)
    if invocation.subcommand == "push":
        forced = any(
            argument == "--force"
            or argument.startswith("--force-with-lease")
            or argument == "--force-if-includes"
            or argument == "--mirror"
            for argument in invocation.args
        )
        forced = forced or _short_flag(invocation.args, "f")
        forced = forced or any(argument.startswith("+") for argument in invocation.args)
        return forced and not _dry_run(invocation)
    return False


def _safe_relative_path(root: pathlib.Path, value: str | pathlib.Path) -> pathlib.Path:
    trusted_root = root.resolve()
    lexical_root = pathlib.Path(os.path.abspath(root))
    raw = pathlib.Path(value)
    if ".." in raw.parts:
        raise UnsafePathError(f"unsafe traversal in repository path: {value}")
    candidate = pathlib.Path(os.path.abspath(raw if raw.is_absolute() else lexical_root / raw))
    relative = None
    for candidate_root in (lexical_root, trusted_root):
        try:
            relative = candidate.relative_to(candidate_root)
            break
        except ValueError:
            continue
    if relative is None:
        raise UnsafePathError(f"unsafe path outside repository: {value}")
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise UnsafePathError(f"unsafe repository path: {value}")
    current = trusted_root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise UnsafePathError(f"unsafe symlinked repository path: {relative.as_posix()}")
    return relative


def _safe_path(root: pathlib.Path, relative: str | pathlib.Path) -> pathlib.Path:
    return root.resolve() / _safe_relative_path(root, relative)


def _safe_read_text(
    root: pathlib.Path,
    relative: str | pathlib.Path,
    *,
    errors: str = "strict",
) -> str:
    path = _safe_path(root, relative)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8", errors=errors)


def _safe_is_file(root: pathlib.Path, relative: str | pathlib.Path) -> bool:
    try:
        return _safe_path(root, relative).is_file()
    except UnsafePathError:
        raise


def _safe_mkdir(root: pathlib.Path, relative: pathlib.Path) -> pathlib.Path:
    trusted_root = root.resolve()
    current = trusted_root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            current.mkdir()
            mode = current.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise UnsafePathError(f"unsafe session directory: {relative.as_posix()}")
    return current


def _relative_files(root: pathlib.Path, directory: str, suffix: str | None = None) -> list[pathlib.Path]:
    base = _safe_path(root, directory)
    if not base.is_dir():
        return []
    files: list[pathlib.Path] = []
    for current, directories, names in os.walk(base, followlinks=False):
        current_path = pathlib.Path(current)
        directories[:] = [
            name
            for name in directories
            if not (current_path / name).is_symlink()
        ]
        for name in names:
            path = current_path / name
            relative = path.relative_to(root.resolve())
            try:
                _safe_relative_path(root, relative)
            except UnsafePathError:
                continue
            if path.is_file() and (suffix is None or path.suffix == suffix):
                files.append(path)
    return files


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
            r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$",
            tool_command(event),
            re.MULTILINE,
        )
    )
    return {path.strip().replace("\\", "/") for path in paths if path.strip()}


def repository_paths(event: dict, root: pathlib.Path) -> set[str]:
    safe: set[str] = set()
    for raw_path in changed_paths(event):
        try:
            relative = _safe_relative_path(root, raw_path)
        except UnsafePathError:
            continue
        if relative.parts and relative.parts[0] != ".git":
            safe.add(relative.as_posix())
    return safe


def _staged_paths(root: pathlib.Path) -> list[str]:
    result = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if result.returncode != 0:
        raise StagedInspectionError(result.stderr.strip() or "git could not inspect the staged index")
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def _staged_text(root: pathlib.Path, relative: str) -> str | None:
    result = _git(root, "show", f":{relative}")
    if result.returncode != 0:
        raise StagedInspectionError(result.stderr.strip() or f"git could not read staged file {relative}")
    return result.stdout


def _validate_commit(root: pathlib.Path) -> HookResult:
    warnings: list[str] = []
    try:
        for relative in _staged_paths(root):
            text = _staged_text(root, relative)
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
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        return HookResult(2, stderr=f"BLOCKED: staged commit inspection failed: {error}\n")
    if warnings:
        return _system_message("Commit validation warnings:\n" + "\n".join(warnings))
    return HookResult()


def _branch_name(refspec: str) -> str:
    destination = refspec.rsplit(":", 1)[-1].lstrip("+")
    if destination.startswith("refs/heads/"):
        destination = destination.removeprefix("refs/heads/")
    return destination


def _protected_push(invocation: GitInvocation, root: pathlib.Path) -> HookResult:
    explicit = next(
        (
            branch
            for argument in invocation.args
            if not argument.startswith("-")
            for branch in [_branch_name(argument)]
            if branch in PROTECTED_BRANCHES
        ),
        None,
    )
    branch_result = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    current = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    branch = explicit or (current if current in PROTECTED_BRANCHES else "")
    if branch:
        return _system_message(
            f"Push to protected branch '{branch}' detected. Verify the build and unit tests pass and no S1/S2 bugs remain."
        )
    return HookResult()


def _validate_command(event: dict, root: pathlib.Path) -> HookResult:
    invocations = git_invocations(tool_command(event))
    if any(_destructive(invocation) for invocation in invocations):
        return HookResult(
            2,
            stderr="Destructive Git command blocked by Codex Game Studios policy.\n",
        )
    if any(invocation.subcommand == "commit" for invocation in invocations):
        return _validate_commit(root)
    for invocation in invocations:
        if invocation.subcommand == "push":
            result = _protected_push(invocation, root)
            if result.stdout:
                return result
    return HookResult()


def _validate_assets(event: dict, root: pathlib.Path) -> HookResult:
    warnings: list[str] = []
    relative_paths: set[str] = set()
    for raw_path in changed_paths(event):
        try:
            relative = _safe_relative_path(root, raw_path)
        except UnsafePathError as error:
            warnings.append(f"SAFETY: unsafe edited path ignored: {error}")
            continue
        if relative.parts and relative.parts[0] != ".git":
            relative_paths.add(relative.as_posix())
    for relative in sorted(relative_paths):
        if not relative.startswith("assets/"):
            continue
        path = _safe_path(root, relative)
        filename = path.name
        if re.search(r"[A-Z\s-]", filename):
            warnings.append(f"NAMING: {relative} must use lowercase names with underscores.")
        if relative.startswith("assets/data/") and relative.endswith(".json") and path.is_file():
            try:
                json.loads(_safe_read_text(root, relative))
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
    directory = _safe_path(root, relative)
    if not directory.is_dir():
        return None
    candidates = [
        path
        for path in directory.glob(pattern)
        if _safe_is_file(root, path.relative_to(root.resolve()))
    ]
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
    bugs = sum(
        1
        for directory in ("tests/playtest", "production")
        for path in _relative_files(root, directory, ".md")
        if path.name.startswith("BUG-")
    )
    if bugs:
        lines.append(f"Open bugs: {bugs}")
    source_files = _relative_files(root, "src")
    source_texts = [
        _safe_read_text(root, path.relative_to(root.resolve()), errors="ignore")
        for path in source_files
    ]
    todos = sum(text.count("TODO") for text in source_texts)
    fixmes = sum(text.count("FIXME") for text in source_texts)
    if todos or fixmes:
        lines.append(f"Code health: {todos} TODOs, {fixmes} FIXMEs in src/")
    try:
        state_text = _safe_read_text(root, "production/session-state/active.md", errors="replace")
    except FileNotFoundError:
        state_text = None
    except UnsafePathError as error:
        state_text = None
        lines.append(f"SAFETY: unsafe session state was ignored: {error}")
    if state_text is not None:
        lines.extend(
            [
                "Active session state detected at production/session-state/active.md; read it to continue.",
                "Quick summary:",
                *state_text.splitlines()[-20:],
            ]
        )
    lines.append("===================================")
    return HookResult(stdout="\n".join(lines) + "\n")


def _detect_gaps(event: dict, root: pathlib.Path) -> HookResult:
    del event
    source_files = [path for path in _relative_files(root, "src") if path.suffix.lower() in SOURCE_SUFFIXES]
    design_files = _relative_files(root, "design/gdd", ".md")
    engine_text = ""
    try:
        engine_text = _safe_read_text(root, ".codex/docs/technical-preferences.md", errors="ignore")
    except FileNotFoundError:
        pass
    concept_exists = _safe_is_file(root, "design/gdd/game-concept.md")
    fresh = not source_files and not concept_exists and (
        not engine_text or "TO BE CONFIGURED" in engine_text or "[CHOOSE" in engine_text
    )
    lines = ["=== Checking for Documentation Gaps ==="]
    if fresh:
        lines.append("NEW PROJECT: no configured engine, game concept, or source code. Run $start.")
    if len(source_files) > 50 and len(design_files) < 5:
        lines.append(f"GAP: {len(source_files)} source files but only {len(design_files)} design documents. Run $reverse-document or $project-stage-detect.")
    prototypes = _safe_path(root, "prototypes")
    if prototypes.is_dir():
        prototype_directories: list[pathlib.Path] = []
        for path in prototypes.iterdir():
            relative = path.relative_to(root.resolve())
            _safe_relative_path(root, relative)
            if path.is_dir():
                prototype_directories.append(path)
        undocumented = sorted(
            path.name
            for path in prototype_directories
            if not _safe_is_file(root, path.relative_to(root.resolve()) / "README.md")
            and not _safe_is_file(root, path.relative_to(root.resolve()) / "CONCEPT.md")
        )
        if undocumented:
            lines.append("GAP: undocumented prototypes: " + ", ".join(undocumented) + ". Run $reverse-document.")
    core_or_engine_files = [
        path
        for path in source_files
        if path.relative_to(root.resolve()).parts[:2] in {("src", "core"), ("src", "engine")}
    ]
    if core_or_engine_files:
        adrs = _relative_files(root, "docs/architecture", ".md")
        if len(adrs) < 3:
            lines.append(f"GAP: core systems exist but only {len(adrs)} architecture records. Run $architecture-decision.")
    gameplay = _safe_path(root, "src/gameplay")
    if gameplay.is_dir():
        systems: list[pathlib.Path] = []
        for path in gameplay.iterdir():
            _safe_relative_path(root, path.relative_to(root.resolve()))
            if path.is_dir():
                systems.append(path)
        for system in sorted(systems):
            count = sum(
                1
                for path in _relative_files(root, system.relative_to(root).as_posix())
                if path.suffix.lower() in SOURCE_SUFFIXES
            )
            has_system_doc = _safe_is_file(root, f"design/gdd/{system.name}-system.md")
            has_short_doc = _safe_is_file(root, f"design/gdd/{system.name}.md")
            if count >= 5 and not has_system_doc and not has_short_doc:
                lines.append(f"GAP: gameplay system {system.name} has {count} files and no design document. Run $reverse-document.")
    if len(source_files) > 100 and not _safe_path(root, "production/sprints").is_dir() and not _safe_path(root, "production/milestones").is_dir():
        lines.append("GAP: large codebase has no production planning. Run $sprint-plan.")
    lines.append("For a complete analysis, run $project-stage-detect.")
    return HookResult(stdout="\n".join(lines) + "\n")


def _append(root: pathlib.Path, relative: str, text: str) -> None:
    relative_path = _safe_relative_path(root, relative)
    _safe_mkdir(root, relative_path.parent)
    path = _safe_path(root, relative_path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(text)


def _pre_compact(event: dict, root: pathlib.Path) -> HookResult:
    del event
    lines = ["Session state before compaction", f"Timestamp: {_now()}"]
    try:
        state_text = _safe_read_text(root, "production/session-state/active.md", errors="replace")
    except FileNotFoundError:
        state_text = None
    if state_text is not None:
        state_lines = state_text.splitlines()
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
        relative = path.relative_to(root.resolve())
        for number, line in enumerate(_safe_read_text(root, relative, errors="ignore").splitlines(), 1):
            if re.search(r"TODO|WIP|PLACEHOLDER|\[TO BE|\[TBD\]", line):
                wip.append(f"{relative.as_posix()}:{number}: {line}")
    if wip:
        lines.extend(["Design documents in progress:", *wip])
    lines.append("After compaction, read production/session-state/active.md and the files listed above.")
    _append(root, "production/session-logs/compaction-log.txt", f"Context compaction occurred at {_now()}.\n")
    return _system_message("\n".join(lines))


def _post_compact(event: dict, root: pathlib.Path) -> HookResult:
    del event
    try:
        state_text = _safe_read_text(root, "production/session-state/active.md", errors="replace")
    except FileNotFoundError:
        state_text = None
    if state_text is not None:
        count = len(state_text.splitlines())
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
    sections: list[str] = []
    try:
        state_text = _safe_read_text(root, "production/session-state/active.md", errors="replace")
    except FileNotFoundError:
        state_text = None
    if state_text is not None:
        sections.extend([f"## Archived Session State: {_stamp()}", state_text, "---", ""])
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
        return handler(event, root)
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
