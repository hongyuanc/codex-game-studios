# Codex Game Studios

Codex Game Studios installs and manages a complete Codex-native
game-development studio in an existing or new Git repository. Project
operations use the embedded payload and make no network requests.

## Requirements

- Codex with this plugin installed
- Python 3.11 or newer
- A Git repository in which you want to manage the studio
- Godot, Unity, or Unreal installed separately before running or exporting a game

The plugin is currently distributed through the repository marketplace and is
not yet listed in the public Codex Plugins Directory.

In the Codex app, clone and open the
[Codex Game Studios repository](https://github.com/hongyuanc/codex-game-studios),
open **Plugins**, select the **Codex Game Studios** repository marketplace, and
install the plugin. Start a new Codex task in the target Git repository so the
newly installed plugin is loaded.

For the Codex CLI, add the repository marketplace and install from the
published `main` branch:

```bash
codex plugin marketplace add hongyuanc/codex-game-studios --ref main
codex plugin add codex-game-studios@codex-game-studios
```

Start a new Codex session in the target Git repository after installation.

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
invoke `$start` to configure the studio, then use `$setup-engine` to select the
installed Godot, Unity, or Unreal toolchain. The manager is retained after
project installation, and every project operation continues to use its embedded
payload with no network requests.

## License and attribution

The plugin retains the MIT License and `Copyright (c) 2026 Donchitos` for the
upstream work from
https://github.com/Donchitos/Claude-Code-Game-Studios. See [ATTRIBUTION.md](ATTRIBUTION.md)
for the independent Codex-native adaptation notice and modification summary.
