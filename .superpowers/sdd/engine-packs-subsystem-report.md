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
- The first implementation was ready for review; the review findings and their
  remediation supersede that checkpoint below.

## Critical/Important Review Remediation

The independent review rejected the first in-process `TemporaryDirectory`
rollback design as insufficient for concurrent writers, interrupted processes,
Windows reparse-point safety, and forged ownership manifests. The remediation
was implemented test-first rather than weakening the findings.

### Remediation RED

The first remediation run failed at the missing durable recovery API and two
setup-flow semantic contracts:

```text
python3 -m unittest tests.studio.test_engine_pack tests.studio.test_setup_engine_skill -v
Ran 5 tests
FAILED (failures=2, errors=1)
```

Subsequent narrow RED runs reproduced all of the following before their fixes:

- Windows backslash traversal and mocked reparse/name-surrogate metadata.
- A forged plan that could name a path outside managed agents.
- A forged five-file manifest that attempted to claim custom files as managed.
- Symlinked root/control/pack/agents/config/manifest/lock/recovery paths.
- A target file or symlink created after locked revalidation.
- A second same-project activation entering while the first held the lock.
- Rollback failure without a durable recovery path.
- Invalid/empty/control-character CLI version and language values.
- Combined setup questions and mismatched dry-run/apply values.

### Remediation GREEN

Final focused and complete verification:

```text
python3 -m unittest tests.studio.test_engine_pack tests.studio.test_setup_engine_skill -q
Ran 43 tests
OK

python3 -m unittest discover -s tests/studio -q
Ran 179 tests in 3.052s
OK

python3 -m py_compile tools/codex_studio/engine_pack.py
exit 0
```

The CLI dry run exits 0 and reports all six configuration fields, including
unchanged `review_mode` and `model_policy`. Subprocess apply tests cover every
documented compatible primary language plus rejection of missing, incompatible,
or control-character-bearing values. Recovery tests preserve a persistent
journal/backup after rollback failure, reject corrupt backups by recorded hash,
and complete a later explicit `--recover` without deleting the only good copy.

### Corrected Transaction Model

- Cooperating writers are serialized by a same-project in-process lock plus
  POSIX `flock` or Windows byte-range lock. The canonical plan, source hashes,
  and logical project digest are revalidated while that lock is held.
- Destination profiles are created with exclusive/no-follow semantics using a
  directory file descriptor where supported. The fallback uses `O_EXCL` plus
  before/after parent and opened-target identity checks.
- `.codex/engine-pack-recovery` is a persistent same-filesystem journal. It
  records phase, original presence, agent-tree digest, and config/manifest
  hashes while retaining the original bytes/tree. Every successful restore
  keeps the canonical backup until replacement completes.
- An incomplete journal blocks new planning with an explicit `--recover`
  instruction. Apply detects and recovers incomplete state under the lock before
  revalidating a previously issued plan. Failed recovery retains the journal and
  both the original and rollback exceptions.
- Manifest ownership is authorized only when its exact filenames and hashes
  equal the declared immutable source pack. A forged manifest cannot authorize
  removal of custom files.
- POSIX symlinks and Windows junction/reparse/name-surrogate metadata are
  rejected for all transaction control paths. Source filenames pass the same
  traversal-safe filename validator before pack cardinality is trusted.
- Same-engine configuration-only updates do not rewrite profiles or the active
  manifest. TOML serialization round-trips quotes, backslashes, and Unicode.
- `$setup-engine` now asks seven decisions strictly one at a time and uses the
  exact selected engine/version/language in both the approved dry run and apply.

### Honest Residual Boundaries

This is a **serialized, recoverable transaction**, not a claim of magical
multi-file atomicity. Lock-ignorant readers may observe intermediate files while
the five profiles and two control files change. A hostile lock-ignorant process
can always race after a completed atomic operation; exclusive destination opens,
identity checks, hashes, and rollback narrow that risk but cannot coordinate an
uncooperative writer. Atomic `os.replace` behavior also depends on the local
filesystem. Journal files and phase replacements are flushed, but arbitrary
power loss can still defeat guarantees provided by the OS/filesystem cache or
directory durability semantics. Recovery artifacts are therefore retained on
any ambiguous or failed restore instead of claiming success or deleting the
only known-good backup.

## Recovery Integrity Follow-up

A second review correctly identified that durable location alone was not enough:
the journal also needed authenticated internal consistency and terminal-state
verification. Focused RED tests first demonstrated that the prior reader accepted
unbound roots/phases and that a silently corrupted restore could be retired.

The recovery journal now has a closed schema with:

- format version and an explicit allowed phase enum;
- canonical project-root binding;
- strict lowercase SHA-256 syntax;
- original and committed-target presence/digest metadata for agents, manifest,
  and config;
- a canonical SHA-256 checksum over every journal field except the checksum.

Unknown, missing, extra, malformed, mismatched, or incorrectly checksummed fields
are corrupt. Original presence flags must agree with both digest presence and
exact backup/absence artifacts, so a forged false flag cannot authorize moving
or deleting live state. `committed` and `rolled-back` journals verify live state
against the recorded target or original snapshot before retirement. Restore
also recomputes all six live presence/digest values before writing `rolled-back`;
silent copy/write corruption preserves the journal and only known-good backup.

`validate_activation` rejects incomplete recovery by default. The only bypass is
the private `_allow_current_transaction` path used while apply owns the project
lock and performs its own post-write validation. Direct API apply now enforces
the same exact version/language and control-free review/model policy contract as
the CLI. A POSIX subprocess test proves the OS lock rejects a second process;
non-POSIX platforms skip that specific test with an explicit reason while the
portable in-process contention test remains active.

Final follow-up verification:

```text
python3 -m unittest tests.studio.test_engine_pack tests.studio.test_setup_engine_skill -q
Ran 50 tests
OK

python3 -m unittest discover -s tests/studio -q
Ran 186 tests in 3.506s
OK

python3 -m py_compile tools/codex_studio/engine_pack.py
exit 0
```

The earlier fixture caveat remains unchanged: the minimal fixture stores studio
state only, and tests copy the authoritative immutable packs into an isolated
temporary project before CLI apply/recovery checks. Repository-root dry-run and
subprocess apply/lock tests provide the corresponding executable CLI evidence.
