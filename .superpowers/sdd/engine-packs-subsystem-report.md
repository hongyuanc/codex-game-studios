# Engine Packs Subsystem Report

## Scope

Implemented the Codex-native engine-pack transaction and converted the final
studio skill, `$setup-engine`. The immutable source inventory remains exactly
three packs (`godot`, `unity`, and `unreal`) with five profiles per pack.

## TDD Evidence

Initial focused RED:

```text
python3 -m unittest tests.studio.test_engine_pack tests.studio.test_setup_engine_skill -v
Ran 3 tests
FAILED (failures=2, errors=1)
```

The engine suite failed to import because
`tools.codex_studio.engine_pack` did not exist. The setup contracts separately
failed on legacy Claude metadata/primitives, absent native transaction commands,
and the missing technical-preference integration.

The first GREEN checkpoint passed 19 tests covering dry-run/apply basics,
three-pack/five-profile inventory, collisions, modified hashes, symlinks,
malformed state, traversal, stale plans, source drift, rollback checkpoints,
idempotence, unmanaged preservation, CLI exits, and the native setup skill.

An adversarial second RED added Windows-style traversal, forged-plan escape,
and real remove-failure contracts:

```text
python3 -m unittest \
  tests.studio.test_engine_pack.EnginePackTests.test_windows_style_manifest_traversal_is_rejected \
  tests.studio.test_engine_pack.EnginePackTests.test_forged_plan_cannot_remove_a_path_outside_managed_agents \
  tests.studio.test_engine_pack.EnginePackTests.test_actual_remove_failure_rolls_back -v
Ran 3 tests
FAILED (failures=3)
```

The failures proved that backslash traversal needed platform-independent
rejection, plans needed canonical re-derivation before mutation, and managed
removal needed an injectable transaction boundary. Those protections were
implemented before the final GREEN run. A final RED/GREEN cycle also rejected
a symlinked `.codex` control directory so parent-directory traversal cannot
redirect the transaction outside the project.

Final focused GREEN:

```text
python3 -m unittest tests.studio.test_engine_pack tests.studio.test_setup_engine_skill -v
Ran 24 tests
OK
```

## Transaction Contract

- Planning is immutable, deterministic, and read-only. It validates the exact
  pack inventory, profile filenames/TOML identities, studio config, active
  manifest, generated hashes, target collisions, symlinks, and path safety.
- Plans bind the project state and every source-profile hash. Apply rejects
  stale/concurrent plans, source changes, a different root, or any forged plan
  path/configuration before mutation.
- Apply backs up `.codex/agents`, `.codex/active-engine.json`, and
  `.codex/studio.toml`; removes only hash-verified managed profiles; copies the
  selected five; atomically replaces manifest/config; and validates the result.
- Failures during removal, mid-copy, manifest/config write, atomic replace, or
  post-validation restore agent-directory content/symlinks, manifest
  presence/content, and studio configuration presence/content byte-for-byte.
- Unmanaged agents are preserved. Managed edits, unmanaged collisions,
  malformed manifests/configs, unsafe filenames, source/profile symlinks, a
  symlinked control directory, and both POSIX/Windows traversal are rejected.
- Reapplying the same engine/version/language with unchanged sources is a true
  byte-for-byte no-op.

## Skill Contract

`$setup-engine` now uses native Codex frontmatter and terminology. It gathers
one decision per turn, uses `request_user_input` when available, runs a concrete
`--dry-run`, presents the complete activation plan, and requires explicit
approval before `--apply` or related documentation writes. It reports rollback
evidence on failure and cannot claim success before focused/full tests, manifest
and hash validation, a final no-op dry run, and confirmation of the five active
profiles.

## Verification

```text
python3 -m unittest discover -s tests/studio -q
Ran 160 tests in 1.768s
OK

python3 -m py_compile tools/codex_studio/engine_pack.py
exit 0

forbidden legacy-pattern scan of .agents/skills/setup-engine/SKILL.md
clean
```

Repository-root dry-run exited 0, printed exactly five deterministic Godot
`INSTALL` entries, no `REMOVE` entries, and the exact target configuration:

```text
CONFIG engine=godot version=4.6 language=gdscript
```

## Changed Files

- `tools/codex_studio/engine_pack.py`
- `tests/studio/test_engine_pack.py`
- `tests/studio/test_setup_engine_skill.py`
- `tests/studio/fixtures/engine-project/.codex/studio.toml`
- `.agents/skills/setup-engine/SKILL.md`
- `.codex/docs/technical-preferences.md`
- `.superpowers/sdd/engine-packs-subsystem-report.md`

## Self-Review and Concerns

- The transaction uses only Python standard-library modules and deterministic
  JSON/TOML serialization; no dependency was added.
- The source profile packs were validated but not modified.
- Public migration docs/plans and unrelated subsystem files were not staged.
- The fixture-root CLI example in the original plan cannot run standalone
  because the fixture intentionally contains only studio state; tests copy the
  authoritative packs into each isolated fixture. The equivalent repository-root
  dry run and subprocess CLI tests both pass without mutation.
- No functional concern remains. Ready for independent review.
