---
name: setup-engine
description: Use when you need to configure and safely activate one native Codex engine-specialist pack for Godot, Unity, or Unreal.
---

# Setup Engine

Use this skill when selecting, changing, refreshing, or upgrading the project's game engine. Engine selection is a material project decision. Keep it user-driven and make only one decision per turn.

## Supported packs

Exactly one of these packs may be active:

- Godot: `godot`
- Unity: `unity`
- Unreal Engine: `unreal`

Each immutable source pack contains exactly five Codex agent profiles under `.codex/agent-packs/<engine>/`. Activation copies those profiles into `.codex/agents/`; `.codex/active-engine.json` records their hashes and ownership. Never edit a source pack during setup.

## Gather decisions

Read `design/gdd/game-concept.md`, `AGENTS.md`, `.codex/studio.toml`, and `.codex/docs/technical-preferences.md` when present. Gather only missing information in this exact order:

1. **Engine** — Godot, Unity, or Unreal.
2. **Exact engine version** — verify the stable version against official engine documentation when the user has not supplied one.
3. **Primary language** — `gdscript` or `csharp` for Godot, `csharp` for Unity, and `cpp` or `blueprint` for Unreal.
4. **Target platform** — the concrete initial platform target.
5. **Primary input** — the dominant input method for that platform and game.
6. **Testing framework** — the engine-appropriate test framework to record.
7. **Performance budget** — accept defaults or gather the target frame/memory budget.

Ask exactly one unresolved decision, then stop and wait. Use `request_user_input` when it is available and appropriate. Ask a concise direct question otherwise. Never bundle independent decisions or silently choose an engine/version.

## Plan before mutation

Run a read-only plan with the chosen values:

```bash
python3 -m tools.codex_studio.engine_pack --root . --engine <engine> --version <exact-version> --language <primary-language> --dry-run
```

Replace the example values with the user's selection. The command must exit successfully. Present its complete activation plan, including every install, every removal, and the configuration change. Also summarize the proposed `AGENTS.md`, `.codex/docs/technical-preferences.md`, build/test command, and engine-reference updates as one bounded changeset.

Request explicit approval for that complete changeset. No project write is allowed before this approval. Do not run the apply command, edit preferences, or update references before approval. A dry run is not approval.

## Apply the approved pack

After explicit approval, run the exact corresponding transaction:

```bash
python3 -m tools.codex_studio.engine_pack --root . --engine <engine> --version <exact-version> --language <primary-language> --apply
```

The transaction rejects unmanaged collisions, symlinks/reparse points, modified generated profiles, malformed state, stale plans, source changes, and path traversal. It is serialized for cooperating writers and recoverable, not magically atomic to lock-ignorant readers or across arbitrary power-loss/filesystem behavior. Before mutation it persists the original agent tree, manifest, and studio configuration under `.codex/engine-pack-recovery`. It attempts byte-for-byte logical rollback on failure; if rollback itself fails, it preserves the only good backup and journal for explicit recovery:

```bash
python3 -m tools.codex_studio.engine_pack --root . --recover
```

If activation fails:

1. Stop all remaining setup writes.
2. Show the error and rollback evidence (engine, manifest presence/hash, config hash, managed-profile validation, and persistent journal state).
3. Never claim setup succeeded.
4. Resolve the safety issue only with the user; never delete or overwrite an unmanaged/modified file.

## Complete approved integration

Only after activation succeeds, apply the complete approved write scope:

- Update the Technology Stack and engine reference import in `AGENTS.md`.
- Populate `.codex/docs/technical-preferences.md`, including **Active Engine Pack**, exact build/test commands, naming conventions, platform/input choices, and routing to the five active profiles.
- Create or refresh `docs/engine-reference/<engine>/VERSION.md` from official documentation. Record exact version and verification date; add focused breaking-change references only where needed.
- Do not add speculative libraries or dependencies.

## Post-apply validation

Run all of the following before reporting success:

```bash
python3 -m unittest tests.studio.test_engine_pack tests.studio.test_setup_engine_skill -v
python3 -m unittest discover -s tests/studio -v
python3 -m tools.codex_studio.validate --root . --phase final
python3 -m tools.codex_studio.engine_pack --root . --engine <engine> --version <version> --language <language> --dry-run
```

Confirm that:

- `.codex/studio.toml` names the selected engine and pack.
- `.codex/active-engine.json` validates.
- The five active profiles exist and match their recorded hashes.
- Final repository validation accepts the configured core-plus-engine roster.
- The final dry run reports a no-op.
- The approved `AGENTS.md`, technical-preference, and engine-reference updates exist.

Report the engine/version/language, the five active profiles, build/test commands, reference status, and test results. Never claim success without post-apply validation.

## Refresh and upgrade

For a reference refresh, do not reactivate the pack unless the pack or engine selection changes. Verify official documentation, show the reference-only changeset, and obtain approval before writing.

For an engine upgrade, first audit breaking/deprecated APIs and present the migration impact. Obtain approval for the version/reference changes and source migration scope. Re-run the transactional activation only when its recorded version/language or source profiles must change, then complete the same validation gate.
