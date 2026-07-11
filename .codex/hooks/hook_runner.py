#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import datetime as dt
import fnmatch
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
DYNAMIC_TOKEN_PREFIX = "__CGS_DYNAMIC_"
QUOTED_VARIABLE_PREFIX = "__CGS_QUOTED_VARIABLE_"
MAX_SHELL_RECURSION = 12
MAX_ALIAS_RECURSION = 12
PUSH_VALUE_OPTIONS = {
    "--exec",
    "--push-option",
    "--receive-pack",
    "--recurse-submodules",
    "--repo",
    "-o",
}
CLEAN_VALUE_OPTIONS = {"--exclude", "-e"}
GIT_OPTION_NAMES = {
    "reset": {
        "--hard", "--help", "--keep", "--merge", "--mixed", "--no-refresh",
        "--no-recurse-submodules", "--pathspec-file-nul", "--pathspec-from-file",
        "--quiet", "--recurse-submodules", "--refresh", "--soft",
    },
    "clean": {
        "--directory", "--dry-run", "--exclude", "--force", "--help",
        "--ignored", "--ignored-only", "--interactive", "--quiet",
    },
    "push": {
        "--all", "--atomic", "--branches", "--delete", "--dry-run", "--exec",
        "--follow-tags", "--force", "--force-if-includes", "--force-with-lease",
        "--help", "--mirror", "--no-signed", "--porcelain", "--progress",
        "--prune", "--push-option", "--quiet", "--receive-pack",
        "--recurse-submodules", "--repo", "--set-upstream", "--signed", "--tags",
        "--thin", "--verbose",
    },
}
KNOWN_GIT_SUBCOMMANDS = {
    "add", "bisect", "branch", "checkout", "cherry-pick", "clean", "clone",
    "commit", "config", "diff", "fetch", "grep", "init", "log", "merge",
    "mv", "pull", "push", "rebase", "reset", "restore", "revert", "rm",
    "show", "sparse-checkout", "stash", "status", "switch", "tag", "worktree",
}
ENV_VALUE_OPTIONS = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}
ENV_SPLIT_OPTIONS = {"-S", "--split-string"}
SUDO_VALUE_OPTIONS = {
    "-C", "--close-from", "-g", "--group", "-h", "--host", "-p", "--prompt",
    "-R", "--chroot", "-r", "--role", "-T", "--command-timeout", "-t", "--type",
    "-u", "--user",
}


@dataclasses.dataclass(frozen=True)
class HookResult:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclasses.dataclass(frozen=True)
class GitInvocation:
    subcommand: str
    args: tuple[str, ...]
    ambiguous_destructive: bool = False
    config_overrides: tuple[tuple[str, str], ...] = ()
    context_options: tuple[str, ...] = ()


class AliasResolutionError(ValueError):
    pass


class UnsafePathError(OSError):
    pass


class StagedInspectionError(OSError):
    pass


def _is_link_or_reparse(info: object) -> bool:
    mode = int(getattr(info, "st_mode", 0))
    attributes = int(getattr(info, "st_file_attributes", 0))
    reparse_tag = int(getattr(info, "st_reparse_tag", 0))
    reparse_attribute = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return stat.S_ISLNK(mode) or bool(attributes & reparse_attribute) or bool(reparse_tag)


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
        word_start = cursor
        word_quote: str | None = None
        while cursor < len(line):
            current = line[cursor]
            if word_quote:
                if current == word_quote:
                    word_quote = None
                elif current == "\\" and word_quote == '"':
                    cursor += 1
                cursor += 1
                continue
            if current in {"'", '"'}:
                word_quote = current
                cursor += 1
                continue
            if current == "\\" and cursor + 1 < len(line):
                cursor += 2
                continue
            if current.isspace() or current in ";&|<>":
                break
            cursor += 1
        raw_delimiter = line[word_start:cursor]
        try:
            parsed_delimiter = shlex.split(raw_delimiter, posix=True)
        except ValueError:
            parsed_delimiter = []
        delimiter = parsed_delimiter[0] if len(parsed_delimiter) == 1 else ""
        index = max(cursor, word_start + 1)
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


def _normalize_continuations(script: str) -> str:
    return re.sub(r"(?:\\|`)\r?\n", " ", script)


def _dollar_substitution_end(script: str, start: int) -> int | None:
    depth = 1
    quote: str | None = None
    index = start + 2
    while index < len(script):
        character = script[index]
        if quote:
            if character == quote:
                quote = None
            elif character == "\\" and quote == '"':
                index += 1
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "\\":
            index += 1
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _backtick_substitution_end(script: str, start: int) -> int | None:
    index = start + 1
    while index < len(script):
        if script[index] == "\\":
            index += 2
            continue
        if script[index] == "`":
            return index
        index += 1
    return None


def _replace_command_substitutions(script: str) -> tuple[str, list[str]]:
    output: list[str] = []
    substitutions: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(script):
        character = script[index]
        if quote == "'":
            output.append(character)
            if character == "'":
                quote = None
            index += 1
            continue
        if character == "'" and quote is None:
            quote = "'"
            output.append(character)
            index += 1
            continue
        if character == '"':
            quote = None if quote == '"' else '"'
            output.append(character)
            index += 1
            continue
        if character == "\\" and index + 1 < len(script):
            output.extend((character, script[index + 1]))
            index += 2
            continue
        if script.startswith("$(", index):
            end = _dollar_substitution_end(script, index)
            if end is None:
                raise ValueError("unterminated command substitution")
            marker = f"{DYNAMIC_TOKEN_PREFIX}{len(substitutions)}__"
            substitutions.append(script[index + 2 : end])
            output.append(marker)
            index = end + 1
            continue
        if character == "`":
            end = _backtick_substitution_end(script, index)
            if end is None:
                raise ValueError("unterminated backtick substitution")
            marker = f"{DYNAMIC_TOKEN_PREFIX}{len(substitutions)}__"
            substitutions.append(script[index + 1 : end])
            output.append(marker)
            index = end + 1
            continue
        output.append(character)
        index += 1
    return "".join(output), substitutions


def _mark_quoted_variable_expansions(script: str) -> str:
    output: list[str] = []
    quote: str | None = None
    index = 0
    variable = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
    while index < len(script):
        character = script[index]
        if character == "\\" and index + 1 < len(script):
            output.extend((character, script[index + 1]))
            index += 2
            continue
        if character == "'" and quote != '"':
            quote = None if quote == "'" else "'"
            output.append(character)
            index += 1
            continue
        if character == '"' and quote != "'":
            quote = None if quote == '"' else '"'
            output.append(character)
            index += 1
            continue
        if quote == '"' and character == "$":
            match = variable.match(script, index)
            if match:
                name = match.group(1) or match.group(2)
                output.append(f"{QUOTED_VARIABLE_PREFIX}{name}__")
                index = match.end()
                continue
        output.append(character)
        index += 1
    return "".join(output)


def _shell_segments(script: str) -> list[list[str]]:
    lexer = shlex.shlex(script, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    tokens = list(lexer)
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in SHELL_BOUNDARIES or (
            token and all(character in ";&|()\n" for character in token)
        ):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _resolve_variable_token(token: str, variables: dict[str, str | None]) -> list[str]:
    quoted = re.fullmatch(
        rf"{re.escape(QUOTED_VARIABLE_PREFIX)}([A-Za-z_][A-Za-z0-9_]*)__", token
    )
    if quoted:
        value = variables.get(quoted.group(1))
        return [value] if value is not None else [f"{DYNAMIC_TOKEN_PREFIX}VARIABLE__"]
    match = re.fullmatch(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))", token)
    if not match:
        return [token]
    name = match.group(1) or match.group(2)
    value = variables.get(name)
    if value is None:
        return [f"{DYNAMIC_TOKEN_PREFIX}VARIABLE__"]
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return [f"{DYNAMIC_TOKEN_PREFIX}VARIABLE__"]


def _record_assignments(segment: list[str], variables: dict[str, str | None]) -> None:
    tokens = list(segment)
    while tokens and tokens[0] in SHELL_COMMAND_PREFIXES:
        tokens.pop(0)
    for token in tokens:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", token, re.DOTALL)
        if not match:
            break
        value = match.group(2)
        variables[match.group(1)] = (
            value
            if "$" not in value
            and DYNAMIC_TOKEN_PREFIX not in value
            and QUOTED_VARIABLE_PREFIX not in value
            and "`" not in value
            else None
        )


def _command_tokens(segment: list[str], variables: dict[str, str | None] | None = None) -> list[str]:
    variables = variables or {}
    tokens = list(segment)
    while tokens and tokens[0] in SHELL_COMMAND_PREFIXES:
        tokens.pop(0)
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens.pop(0)
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(_resolve_variable_token(token, variables))
    tokens = expanded
    while tokens:
        wrapper = pathlib.PurePosixPath(tokens[0]).name.lower()
        if wrapper == "env":
            tokens.pop(0)
            while tokens:
                token = tokens[0]
                option = token.split("=", 1)[0]
                compact_split = token.startswith("-S") and token != "-S"
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token):
                    tokens.pop(0)
                elif option in ENV_SPLIT_OPTIONS or compact_split:
                    tokens.pop(0)
                    if compact_split:
                        value = token[2:]
                    elif "=" in token:
                        value = token.split("=", 1)[1]
                    elif tokens:
                        value = tokens.pop(0)
                    else:
                        return []
                    try:
                        tokens = shlex.split(value, posix=True) + tokens
                    except ValueError:
                        return [f"{DYNAMIC_TOKEN_PREFIX}ENV_SPLIT__"]
                elif option in ENV_VALUE_OPTIONS:
                    tokens.pop(0)
                    if "=" not in token and tokens:
                        tokens.pop(0)
                elif token == "--":
                    tokens.pop(0)
                    break
                elif token.startswith("-"):
                    tokens.pop(0)
                else:
                    break
            continue
        if wrapper == "command":
            tokens.pop(0)
            if tokens and tokens[0] in {"-v", "-V", "--version"}:
                return []
            while tokens and (tokens[0].startswith("-") or tokens[0] == "--"):
                terminal = tokens.pop(0)
                if terminal == "--":
                    break
            continue
        if wrapper == "sudo":
            tokens.pop(0)
            while tokens:
                token = tokens[0]
                option = token.split("=", 1)[0]
                if option in SUDO_VALUE_OPTIONS:
                    tokens.pop(0)
                    if "=" not in token and len(token) == len(option) and tokens:
                        tokens.pop(0)
                elif token == "--":
                    tokens.pop(0)
                    break
                elif token.startswith("-"):
                    tokens.pop(0)
                else:
                    break
            continue
        if wrapper == "exec":
            tokens.pop(0)
            while tokens:
                if tokens[0] == "-a":
                    tokens.pop(0)
                    if tokens:
                        tokens.pop(0)
                elif tokens[0] == "--":
                    tokens.pop(0)
                    break
                elif tokens[0].startswith("-"):
                    tokens.pop(0)
                else:
                    break
            continue
        if wrapper == "builtin":
            tokens.pop(0)
            while tokens and tokens[0].startswith("-"):
                tokens.pop(0)
            continue
        break
    return tokens


def _git_from_tokens(tokens: list[str], *, dynamic_executable: bool = False) -> GitInvocation | None:
    index = 1
    config_overrides: list[tuple[str, str]] = []
    context_options: list[str] = []
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
        if token == "-c":
            if index + 1 >= len(tokens):
                return None
            key, separator, value = tokens[index + 1].partition("=")
            if separator:
                config_overrides.append((key.lower(), value))
            index += 2
            continue
        if token.startswith("-c") and token != "-c":
            key, separator, value = token[2:].partition("=")
            if separator:
                config_overrides.append((key.lower(), value))
            index += 1
            continue
        if token in GIT_GLOBAL_VALUE_OPTIONS:
            if index + 1 >= len(tokens):
                return None
            if token in {"-C", "--git-dir", "--work-tree"}:
                context_options.extend((token, tokens[index + 1]))
            index += 2
            continue
        matching_value_option = next(
            (
                option
                for option in GIT_GLOBAL_VALUE_OPTIONS
                if option.startswith("--") and token.startswith(option + "=")
            ),
            None,
        )
        if matching_value_option:
            if matching_value_option in {"--git-dir", "--work-tree"}:
                context_options.append(token)
            index += 1
            continue
        if token.startswith("-C") and token != "-C":
            context_options.append(token)
            index += 1
            continue
        if token.startswith("-"):
            return None
        break
    if index >= len(tokens):
        return None
    subcommand = tokens[index]
    args = tuple(tokens[index + 1 :])
    dynamic_subcommand = DYNAMIC_TOKEN_PREFIX in subcommand or "$" in subcommand
    ambiguous = dynamic_executable or (
        dynamic_subcommand
        and (
            "--hard" in args
            or "--force" in args
            or any(argument.startswith("--force-") or argument.startswith("+") for argument in args)
            or _short_flag(_option_prefix(args), "f")
        )
    )
    return GitInvocation(
        subcommand,
        args,
        ambiguous,
        tuple(config_overrides),
        tuple(context_options),
    )


def _git_invocation(
    segment: list[str],
    variables: dict[str, str | None] | None = None,
) -> GitInvocation | None:
    tokens = _command_tokens(segment, variables)
    if not tokens:
        return None
    dynamic_executable = DYNAMIC_TOKEN_PREFIX in tokens[0] or "$" in tokens[0]
    executable = pathlib.PurePosixPath(tokens[0]).name.lower()
    if executable in {"git", "git.exe"}:
        return _git_from_tokens(tokens)
    if dynamic_executable:
        candidate = _git_from_tokens(["git", *tokens[1:]])
        if candidate and _destructive(candidate):
            return dataclasses.replace(candidate, ambiguous_destructive=True)
    return None


def _recursive_invocations(
    script: str,
    variables: dict[str, str | None],
    depth: int,
    max_depth: int = MAX_SHELL_RECURSION,
) -> list[GitInvocation]:
    if depth > max_depth:
        raise RecursionError("shell command nesting exceeds safety limit")
    normalized = _normalize_continuations(script)
    without_heredocs = _strip_heredoc_bodies(normalized)
    prepared, substitutions = _replace_command_substitutions(without_heredocs)
    prepared = _mark_quoted_variable_expansions(prepared)
    invocations: list[GitInvocation] = []
    for substitution in substitutions:
        invocations.extend(
            _recursive_invocations(substitution, dict(variables), depth + 1, max_depth)
        )
    for segment in _shell_segments(prepared):
        _record_assignments(segment, variables)
        tokens = _command_tokens(segment, variables)
        if not tokens:
            continue
        executable = pathlib.PurePosixPath(tokens[0]).name.lower()
        if executable in {"bash", "sh", "zsh"} and "-c" in tokens[1:]:
            command_index = tokens.index("-c", 1) + 1
            if command_index >= len(tokens):
                raise ValueError("shell -c is missing its command string")
            nested = tokens[command_index]
            if DYNAMIC_TOKEN_PREFIX in nested or "$" in nested:
                if re.search(r"\b(?:reset|clean|push)\b", " ".join(tokens[command_index:])):
                    invocations.append(GitInvocation("dynamic", (), True))
            else:
                invocations.extend(
                    _recursive_invocations(nested, dict(variables), depth + 1, max_depth)
                )
            continue
        if executable == "eval":
            nested = " ".join(tokens[1:])
            if DYNAMIC_TOKEN_PREFIX in nested or "$" in nested:
                if re.search(r"\b(?:reset|clean|push)\b", nested):
                    invocations.append(GitInvocation("dynamic", (), True))
            elif nested:
                invocations.extend(
                    _recursive_invocations(nested, dict(variables), depth + 1, max_depth)
                )
            continue
        invocation = _git_invocation(segment, variables)
        if invocation:
            invocations.append(invocation)
    return invocations


def git_invocations(script: str) -> list[GitInvocation]:
    return _recursive_invocations(script, {}, 0)


def _alias_value(invocation: GitInvocation, root: pathlib.Path) -> str | None:
    key = f"alias.{invocation.subcommand.lower()}"
    inline = dict(invocation.config_overrides)
    if key in inline:
        return inline[key]
    result = _git(root, *invocation.context_options, "config", "--get", key)
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise AliasResolutionError(result.stderr.strip() or f"could not read {key}")
    return result.stdout.rstrip("\r\n")


def _expand_alias_invocation(
    invocation: GitInvocation,
    root: pathlib.Path,
    *,
    depth: int = 0,
    seen: frozenset[str] = frozenset(),
    limit: int = MAX_ALIAS_RECURSION,
) -> list[GitInvocation]:
    subcommand = invocation.subcommand.lower()
    if subcommand in KNOWN_GIT_SUBCOMMANDS or invocation.ambiguous_destructive:
        return [invocation]
    if subcommand in seen:
        raise AliasResolutionError(f"Git alias loop detected at alias.{subcommand}")
    if depth > limit:
        raise AliasResolutionError("Git alias nesting exceeds safety limit")
    value = _alias_value(invocation, root)
    if value is None:
        return [invocation]
    next_seen = seen | {subcommand}
    if value.startswith("!"):
        nested_script = value[1:]
        if invocation.args:
            nested_script += " " + " ".join(shlex.quote(argument) for argument in invocation.args)
        try:
            nested = git_invocations(nested_script)
        except (OSError, RecursionError, TypeError, UnicodeError, ValueError) as error:
            try:
                nested = _recursive_invocations(
                    nested_script, {}, 0, MAX_SHELL_RECURSION * 8
                )
            except (OSError, RecursionError, TypeError, UnicodeError, ValueError):
                if _recognized_destructive_intent(nested_script):
                    return [GitInvocation("dynamic", (), True)]
                if _recognized_commit_intent(nested_script):
                    return [GitInvocation("commit", ())]
                raise AliasResolutionError(
                    f"could not inspect shell Git alias.{subcommand}: {error}"
                ) from error
        expanded: list[GitInvocation] = []
        for candidate in nested:
            candidate = dataclasses.replace(
                candidate,
                config_overrides=(
                    invocation.config_overrides + candidate.config_overrides
                ),
                context_options=(
                    invocation.context_options + candidate.context_options
                ),
            )
            expanded.extend(
                _expand_alias_invocation(
                    candidate, root, depth=depth + 1, seen=next_seen, limit=limit
                )
            )
        return expanded
    try:
        alias_tokens = shlex.split(value, posix=True)
    except ValueError as error:
        raise AliasResolutionError(f"malformed Git alias.{subcommand}: {error}") from error
    if not alias_tokens:
        raise AliasResolutionError(f"empty Git alias.{subcommand}")
    candidate = _git_from_tokens(["git", *alias_tokens, *invocation.args])
    if candidate is None:
        raise AliasResolutionError(f"could not parse Git alias.{subcommand}")
    candidate = dataclasses.replace(
        candidate,
        config_overrides=invocation.config_overrides + candidate.config_overrides,
        context_options=invocation.context_options + candidate.context_options,
    )
    return _expand_alias_invocation(
        candidate, root, depth=depth + 1, seen=next_seen, limit=limit
    )


def _expand_aliases(
    invocations: list[GitInvocation],
    root: pathlib.Path,
    *,
    limit: int = MAX_ALIAS_RECURSION,
) -> list[GitInvocation]:
    expanded: list[GitInvocation] = []
    for invocation in invocations:
        expanded.extend(_expand_alias_invocation(invocation, root, limit=limit))
    return expanded


def _short_flag(args: tuple[str, ...], flag: str) -> bool:
    return any(
        token.startswith("-")
        and not token.startswith("--")
        and flag in token[1:]
        for token in args
    )


def _option_prefix(args: tuple[str, ...]) -> tuple[str, ...]:
    try:
        end = args.index("--")
    except ValueError:
        end = len(args)
    return args[:end]


def _canonical_option(subcommand: str, token: str) -> str:
    if not token.startswith("--"):
        return token
    name, separator, value = token.partition("=")
    names = GIT_OPTION_NAMES.get(subcommand.lower(), set())
    if name in names:
        resolved = name
    else:
        matches = sorted(option for option in names if option.startswith(name))
        resolved = matches[0] if len(matches) == 1 else name
    return resolved + (separator + value if separator else "")


def _option_tokens(invocation: GitInvocation) -> tuple[str, ...]:
    args = _option_prefix(invocation.args)
    value_options = (
        PUSH_VALUE_OPTIONS
        if invocation.subcommand.lower() == "push"
        else CLEAN_VALUE_OPTIONS
        if invocation.subcommand.lower() == "clean"
        else set()
    )
    options: list[str] = []
    index = 0
    while index < len(args):
        raw_argument = args[index]
        argument = _canonical_option(invocation.subcommand, raw_argument)
        if argument in value_options:
            index += 2
            continue
        if any(
            argument.startswith(option + "=")
            for option in value_options
            if option.startswith("--")
        ) or any(
            argument.startswith(option) and argument != option
            for option in value_options
            if option.startswith("-") and not option.startswith("--")
        ):
            index += 1
            continue
        if argument.startswith("-"):
            options.append(argument)
        index += 1
    return tuple(options)


def _dry_run(invocation: GitInvocation) -> bool:
    options = _option_tokens(invocation)
    return "--dry-run" in options or _short_flag(options, "n")


def _destructive(invocation: GitInvocation) -> bool:
    if invocation.ambiguous_destructive:
        return True
    options = _option_tokens(invocation)
    if invocation.subcommand == "reset":
        return "--hard" in options
    if invocation.subcommand == "clean":
        forced = "--force" in options or _short_flag(options, "f")
        return forced and not _dry_run(invocation)
    if invocation.subcommand == "push":
        forced = any(
            argument == "--force"
            or argument.startswith("--force-with-lease")
            or argument == "--force-if-includes"
            or argument == "--mirror"
            for argument in options
        )
        forced = forced or _short_flag(options, "f")
        forced = forced or any(refspec.startswith("+") for refspec in _push_refspecs(invocation.args))
        return forced and not _dry_run(invocation)
    return False


def _safe_relative_path(root: pathlib.Path, value: str | pathlib.Path) -> pathlib.Path:
    try:
        raw_text = os.fspath(value)
    except (TypeError, ValueError) as error:
        raise UnsafePathError(f"unsafe malformed repository path: {value!r}") from error
    if not isinstance(raw_text, str):
        raise UnsafePathError(f"unsafe non-text repository path: {value!r}")
    if "\x00" in raw_text or any(0xD800 <= ord(character) <= 0xDFFF for character in raw_text):
        raise UnsafePathError("unsafe malformed repository path")
    try:
        trusted_root = root.resolve()
        lexical_root = pathlib.Path(os.path.abspath(root))
        raw = pathlib.Path(raw_text)
    except (OSError, TypeError, ValueError) as error:
        raise UnsafePathError(f"unsafe malformed repository path: {raw_text!r}") from error
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
            info = current.lstat()
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            raise UnsafePathError(f"unsafe repository path metadata: {relative.as_posix()}") from error
        if _is_link_or_reparse(info):
            raise UnsafePathError(f"unsafe linked or reparse repository path: {relative.as_posix()}")
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
            info = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            info = current.lstat()
        except (OSError, ValueError) as error:
            raise UnsafePathError(f"unsafe session directory: {relative.as_posix()}") from error
        if _is_link_or_reparse(info) or not stat.S_ISDIR(info.st_mode):
            raise UnsafePathError(f"unsafe session directory: {relative.as_posix()}")
    return current


def _relative_files(root: pathlib.Path, directory: str, suffix: str | None = None) -> list[pathlib.Path]:
    base = _safe_path(root, directory)
    if not base.is_dir():
        return []
    files: list[pathlib.Path] = []
    for current, directories, names in os.walk(base, followlinks=False):
        current_path = pathlib.Path(current)
        safe_directories: list[str] = []
        for name in directories:
            directory_path = current_path / name
            try:
                if not _is_link_or_reparse(directory_path.lstat()):
                    safe_directories.append(name)
            except (OSError, ValueError):
                continue
        directories[:] = safe_directories
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
    paths = {direct_path} if isinstance(direct_path, str) and direct_path else set()
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
    except (
        OSError,
        UnicodeError,
        subprocess.SubprocessError,
        RecursionError,
        TypeError,
        ValueError,
    ) as error:
        return HookResult(2, stderr=f"BLOCKED: staged commit inspection failed: {error}\n")
    if warnings:
        return _system_message("Commit validation warnings:\n" + "\n".join(warnings))
    return HookResult()


def _branch_name(refspec: str) -> str:
    destination = refspec.rsplit(":", 1)[-1].lstrip("+")
    if destination.startswith("refs/heads/"):
        destination = destination.removeprefix("refs/heads/")
    return destination


def _push_refspecs(args: tuple[str, ...]) -> tuple[str, ...]:
    positionals: list[str] = []
    repository_from_option = False
    options = True
    index = 0
    while index < len(args):
        raw_argument = args[index]
        argument = _canonical_option("push", raw_argument)
        if options and argument == "--":
            options = False
            index += 1
            continue
        if options and argument in PUSH_VALUE_OPTIONS:
            repository_from_option = repository_from_option or argument == "--repo"
            index += 2
            continue
        if options and any(argument.startswith(option + "=") for option in PUSH_VALUE_OPTIONS if option.startswith("--")):
            repository_from_option = repository_from_option or argument.startswith("--repo=")
            index += 1
            continue
        if options and argument.startswith("-"):
            index += 1
            continue
        positionals.append(argument)
        index += 1
    if repository_from_option:
        return tuple(positionals)
    return tuple(positionals[1:]) if positionals else ()


def _push_modes(args: tuple[str, ...]) -> set[str]:
    modes: set[str] = set()
    for argument in _option_tokens(GitInvocation("push", args)):
        canonical = _canonical_option("push", argument).partition("=")[0]
        if canonical in {"--all", "--branches", "--mirror", "--tags"}:
            modes.add(canonical)
    return modes


def _refspec_covers_protected(refspec: str) -> bool:
    if refspec == ":":
        return True
    destination = refspec.rsplit(":", 1)[-1].lstrip("+")
    if "*" not in destination:
        return False
    candidates = (
        (f"refs/heads/{branch}" for branch in PROTECTED_BRANCHES)
        if destination.startswith("refs/")
        else iter(PROTECTED_BRANCHES)
    )
    return any(fnmatch.fnmatchcase(candidate, destination) for candidate in candidates)


def _protected_push(invocation: GitInvocation, root: pathlib.Path) -> HookResult:
    refspecs = _push_refspecs(invocation.args)
    modes = _push_modes(invocation.args)
    broad = bool(modes & {"--all", "--branches", "--mirror"}) or any(
        _refspec_covers_protected(refspec) for refspec in refspecs
    )
    protected = sorted(
        PROTECTED_BRANCHES
        if broad
        else {
            branch
            for refspec in refspecs
            for branch in [_branch_name(refspec)]
            if branch in PROTECTED_BRANCHES
        }
    )
    if not refspecs and "--tags" not in modes and not broad:
        branch_result = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        current = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
        if current in PROTECTED_BRANCHES:
            protected.append(current)
    if protected:
        return _system_message("\n".join(
            f"Push to protected branch '{branch}' detected. Verify the build and unit tests pass and no S1/S2 bugs remain."
            for branch in protected
        ))
    return HookResult()


def _recognized_commit_intent(command: str) -> bool:
    return bool(re.search(r"(?is)\bgit(?:\.exe)?\b.*\bcommit\b", command))


def _recognized_destructive_intent(command: str) -> bool:
    executable = (
        r'''(?:\bgit(?:\.exe)?\b|["']?\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|'''
        r'''[A-Za-z_][A-Za-z0-9_]*)["']?)'''
    )
    pattern = re.compile(
        rf"(?is){executable}[^;&|\n]{{0,1024}}?\b(reset|clean|push)\b([^;&|\n)]*)"
    )
    for match in pattern.finditer(command):
        subcommand, tail = match.groups()
        try:
            args = tuple(shlex.split(tail, posix=True))
        except ValueError:
            args = tuple(re.findall(r"--[^\s;&|)]+|-[A-Za-z]+|\+[^\s;&|)]+", tail))
        if _destructive(GitInvocation(subcommand.lower(), args)):
            return True
    return False


def _result_message(result: HookResult) -> str:
    if not result.stdout:
        return ""
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()
    return str(payload.get("systemMessage", "")).strip()


def _validate_command(event: dict, root: pathlib.Path) -> HookResult:
    command = tool_command(event)
    try:
        invocations = _expand_aliases(git_invocations(command), root)
    except (OSError, RecursionError, TypeError, UnicodeError, ValueError) as error:
        try:
            invocations = _recursive_invocations(
                command, {}, 0, MAX_SHELL_RECURSION * 8
            )
            invocations = _expand_aliases(
                invocations, root, limit=MAX_ALIAS_RECURSION * 8
            )
            if any(invocation.subcommand.lower() == "commit" for invocation in invocations):
                return HookResult(
                    2,
                    stderr=(
                        "BLOCKED: command parser failed for recognized Git safety "
                        f"intent: {error}\n"
                    ),
                )
        except (OSError, RecursionError, TypeError, UnicodeError, ValueError):
            if _recognized_commit_intent(command) or _recognized_destructive_intent(command):
                return HookResult(2, stderr=f"BLOCKED: command parser failed for recognized Git safety intent: {error}\n")
            label = "Git alias" if isinstance(error, AliasResolutionError) else "Command safety parser"
            return _system_message(
                f"{label} could not inspect this inert or unrecognized command: {error}"
            )
    if any(_destructive(invocation) for invocation in invocations):
        return HookResult(
            2,
            stderr="Destructive Git command blocked by Codex Game Studios policy.\n",
        )
    messages: list[str] = []
    if any(invocation.subcommand.lower() == "commit" for invocation in invocations):
        commit_result = _validate_commit(root)
        if commit_result.exit_code == 2:
            return commit_result
        commit_message = _result_message(commit_result)
        if commit_message:
            messages.append(commit_message)
    for invocation in invocations:
        if invocation.subcommand.lower() == "push":
            result = _protected_push(invocation, root)
            message = _result_message(result)
            if message:
                messages.append(message)
    return _system_message("\n".join(messages)) if messages else HookResult()


def _validate_assets(event: dict, root: pathlib.Path) -> HookResult:
    warnings: list[str] = []
    tool_input = event.get("tool_input", {})
    if isinstance(tool_input, dict):
        direct_path = tool_input.get("file_path")
        if direct_path is not None and not isinstance(direct_path, str):
            warnings.append("SAFETY: unsafe malformed edited path ignored")
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
