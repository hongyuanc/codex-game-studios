# Active Hooks

`.codex/hooks.json` registers Codex events. Each registration invokes a named
Python action in `.codex/hooks/hook_runner.py` and receives Codex JSON on
standard input.

| Action | Event | Behavior |
| --- | --- | --- |
| `session-start` | `SessionStart` | Loads Git, sprint, milestone, and recoverable session context |
| `detect-gaps` | `SessionStart` | Suggests `$start`, `$reverse-document`, or `$project-stage-detect` when prerequisites are missing |
| `validate-command` | `PreToolUse` | Parses command payloads and blocks unsafe or unauthorized Git execution |
| `validate-assets` | `PostToolUse` | Checks relevant asset naming and data validity after edits |
| `validate-skill-change` | `PostToolUse` | Recommends `$skill-test` after a skill changes |
| `pre-compact` | `PreCompact` | Writes a recoverable checkpoint before compaction |
| `post-compact` | `PostCompact` | Restores attention to the file-backed checkpoint |
| `subagent-start` | `SubagentStart` | Opens a bounded delegation audit record |
| `subagent-stop` | `SubagentStop` | Completes the delegation audit record |
| `session-stop` | `Stop` | Summarizes work and updates session state |

Tool hooks understand Codex payload fields for `exec_command` and
`apply_patch`. The command validator parses direct Git built-ins, wrappers,
shell boundaries, and relevant options before deciding whether execution is
safe. Ambiguous Git execution fails closed; optional quality checks fail open
with an actionable message.

## Testing hook changes

Add focused cases under `tests/studio/` for every behavior change. Include safe,
unsafe, malformed, and platform-relevant payloads. Then run:

```text
python3 -m unittest tests.studio.test_hook_runner -v
python3 -m unittest discover -s tests/studio -v
```

Hook code must not add user-specific absolute paths, undisclosed network access,
or secret collection. Commits, pushes, releases, and destructive operations
remain explicitly gated by the user.
