# Active Hooks

Hooks are declared in `.codex/hooks.json`. Commands resolve from the repository
root and receive Codex JSON on standard input. Implementations live in
`.codex/hooks/` and must not contain user-specific absolute paths.

| Hook | Event / tool | Action |
| ---- | ---- | ---- |
| `validate-commit.sh` | `exec_command` before a matching `git commit` | Validates design sections, JSON data, hardcoded values, and TODO format |
| `validate-push.sh` | `exec_command` before a matching `git push` | Warns on protected-branch pushes |
| `validate-assets.sh` | `apply_patch` after asset changes | Checks asset naming and JSON validity |
| `validate-skill-change.sh` | `apply_patch` after skill changes | Recommends `$skill-test` for the changed skill |
| `session-start.sh` | `SessionStart` | Loads sprint, milestone, Git, and recoverable session context |
| `detect-gaps.sh` | `SessionStart` | Suggests `$start`, `$reverse-document`, or `$project-stage-detect` when prerequisites are missing |
| `pre-compact.sh` | `PreCompact` | Checkpoints active work before compaction |
| `post-compact.sh` | `PostCompact` | Restores attention to the file-backed checkpoint |
| `log-agent.sh` | `SubagentStart` | Starts a bounded delegation audit record |
| `log-agent-stop.sh` | `SubagentStop` | Completes the delegation audit record |
| `session-stop.sh` | `Stop` | Summarizes work and updates the session log |
| `notify.sh` | optional notification event | Emits a desktop notification when supported |

Tool hooks inspect Codex fields such as the tool name and arguments. Edit hooks
must understand `apply_patch`; command hooks must understand `exec_command`.
Optional quality checks warn and fail open when a dependency is unavailable.
Only clear safety violations, such as destructive Git operations, should block.
