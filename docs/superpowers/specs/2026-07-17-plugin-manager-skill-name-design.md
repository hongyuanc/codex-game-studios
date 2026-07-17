# Plugin Manager Skill Name Design

## Goal

Remove the duplicated `Codex Game Studios: Codex Game Studios` label shown by
Codex while preserving the Codex Game Studios plugin identity and lifecycle
behavior.

## Decision

Keep the plugin identifier and display name unchanged:

- identifier: `codex-game-studios`
- display name: `Codex Game Studios`

Rename the plugin's single bundled lifecycle skill from
`codex-game-studios` to `manager`. Codex will therefore present the bundled
skill as `Codex Game Studios: Manager` instead of repeating the plugin name.

## Compatibility

The manager continues to support exactly five operations: `install`, `update`,
`verify`, `repair`, and `uninstall`. The manager scripts, plan schema, approval
protocol, installed payload, and repository state format do not change.

Public documentation and the plugin's default prompt will use the namespaced
skill invocation `$codex-game-studios:manager <operation>`. This makes the
plugin/skill boundary explicit and avoids relying on the old duplicated skill
name.

Because the discoverable skill identifier changes, the plugin version will be
bumped from `1.0.1` to `1.0.2`. Users must refresh the marketplace, install or
update the plugin, and start a new task before invoking the renamed skill.

## Alternatives Rejected

- Keep both names unchanged: preserves the old invocation but retains the
  confusing duplicated label.
- Rename the plugin: removes one repeated phrase but changes the stable plugin
  identifier, marketplace install coordinate, cache namespace, and public
  identity.
- Remove the bundled skill: eliminates the suffix but also removes the
  lifecycle workflow that safely drives the retained manager.

## Verification

- Contract tests assert the skill frontmatter name is `manager` and the old
  duplicated plugin/skill pair is absent.
- Documentation tests assert the namespaced invocation
  `$codex-game-studios:manager` is used consistently.
- Plugin manifest, payload freshness, complete plugin tests, and complete studio
  tests pass after the 1.0.2 rebuild.
- A disposable fresh-repository install, verify, and uninstall lifecycle passes
  without changing pre-existing project files.

## Scope Boundaries

This change does not push, release, publish, modify the real Embermarch
repository, or alter the plugin manager's filesystem behavior.
