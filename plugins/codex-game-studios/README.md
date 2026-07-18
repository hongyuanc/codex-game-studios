# Codex Game Studios

Codex Game Studios is a plugin-native game-development studio. Installing the
plugin immediately makes all 73 studio skills available; it does not install a
studio tree into a game repository.

## Requirements

- Codex with this plugin installed
- A Git repository in which you want to manage the studio
- Godot, Unity, or Unreal installed separately before running or exporting a game

The plugin is currently distributed through the repository marketplace and is
not yet listed in the public Codex Plugins Directory.

## Start a new game project

Use the same fresh-project sequence in the Codex app and Codex CLI:

1. Install Codex Game Studios from the repository marketplace.
2. Start a new Codex task in the game repository.
3. Run `$codex-game-studios:start`.

### Codex app

1. Clone and open the
   [Codex Game Studios source repository](https://github.com/hongyuanc/codex-game-studios)
   in the Codex app.
2. Open **Plugins**, select the **Codex Game Studios** repository marketplace,
   and install the plugin.
3. Open the game repository. Start a new Codex task so Codex loads the plugin.
4. Run `$codex-game-studios:start` as an in-Codex skill invocation, not a shell
   command.

### Codex CLI

Add the repository marketplace and install from the published `main` branch:

```bash
codex plugin marketplace add hongyuanc/codex-game-studios --ref main
codex plugin add codex-game-studios@codex-game-studios
```

Start a new Codex task in the game repository after installation. Then run
`$codex-game-studios:start` as an in-Codex skill invocation, not a shell command.
The plugin makes all 73 studio skills immediately available after installation, and
plugin installation and skill discovery make zero writes to the game repository.
Start detects the repository read-only first and asks for approval only for a
small project-specific state changeset (at most ten mutations). It never copies
the global skill catalog into the repository or creates `.agents/skills/`.
All 73 explicit installed-plugin commands use the unambiguous
`$codex-game-studios:<skill>` form.

Use `$codex-game-studios:setup-engine` after Start to choose a separately
installed Godot, Unity, or Unreal toolchain.

## Legacy 1.0.0 lifecycle support

Fresh repositories use Start only. When Start detects an authenticated schema-1
installation record, it offers four choices:

- verify legacy installation;
- repair legacy installation;
- migrate to plugin-native; or
- uninstall legacy installation.

Verification is read-only. Every mutating legacy choice presents a complete
digest-bound plan and requires explicit approval; customized and project-owned
files remain preserved. This help remains available only through Start during
the 1.0.0 migration window.

## License and attribution

The plugin retains the MIT License and `Copyright (c) 2026 Donchitos` for the
upstream work from
https://github.com/Donchitos/Claude-Code-Game-Studios. See [ATTRIBUTION.md](ATTRIBUTION.md)
for the independent Codex-native adaptation notice and modification summary.
