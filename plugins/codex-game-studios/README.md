# Codex Game Studios

Codex Game Studios installs and manages a complete Codex-native
game-development studio in an existing or new Git repository. Project
operations use the embedded payload and make no network requests.

## Requirements

- Codex with this plugin installed
- Python 3.11 or newer
- A Git repository in which you want to manage the studio

## Operations

Invoke one operation from the target repository:

```text
$codex-game-studios install
$codex-game-studios update
$codex-game-studios verify
$codex-game-studios repair
$codex-game-studios uninstall
```

`install`, `update`, `repair`, and `uninstall` first display a complete,
digest-bound action plan. Nothing changes until you explicitly approve that
exact plan. `verify` is read-only and runs without an approval step. Existing
game content and unrelated Codex configuration remain project-owned; conflicts
stop mutation instead of being silently overwritten.

See the manager skill's install contract, conflict policy, and recovery guide
for the complete safety protocol. After a successful first installation,
invoke `$start` to configure the studio.

## License and attribution

The plugin retains the MIT License and `Copyright (c) 2026 Donchitos` for the
upstream work from
https://github.com/Donchitos/Claude-Code-Game-Studios. See [ATTRIBUTION.md](ATTRIBUTION.md)
for the independent Codex-native adaptation notice and modification summary.
