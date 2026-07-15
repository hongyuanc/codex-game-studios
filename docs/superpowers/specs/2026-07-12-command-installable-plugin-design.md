# Command-installable Codex Game Studios Plugin Design

> **Status:** Approved design
> **Date:** 2026-07-12
> **Publisher:** `hongyuanc`
> **Primary distribution:** Public Codex Plugins Directory
> **Package:** `codex-game-studios`

## 1. Purpose

Package Codex Game Studios as a native Codex plugin that users install once and
then apply safely to any Git game repository with:

```text
$codex-game-studios install
```

The manager remains installed through Codex and supports installation, updates,
verification, repair, and uninstall. A game repository receives the complete
operational studio, not the source repository's maintainer and release files.

## 2. Goals

- Make the public Plugins Directory the primary distribution path.
- Require only `$codex-game-studios install` inside each target repository after
  the plugin has been installed once.
- Support fresh and existing Git game repositories.
- Install the complete operational studio, not a partial skills-only mode.
- Preserve project-owned work and unrelated Codex configuration.
- Produce a complete read-only plan before every mutation.
- Bind approval to the exact source payload and target state.
- Make install, update, repair, and uninstall recoverable.
- Operate without network access after the plugin itself is installed.
- Retain upstream MIT attribution in the plugin and every installed copy.
- Validate on Windows, macOS, and Linux before public release.

## 3. Non-goals

- Publishing through npm, PyPI, `pipx`, or `uvx` in version 1.
- Supporting component selection such as skills-only or no-hooks installs.
- Overwriting customized framework files silently.
- Replacing a game's README, root license, security policy, contributor guide,
  GitHub templates, or CI configuration.
- Installing source-repository release plans, migration evidence, or maintainer
  tests into game repositories.
- Selecting a game engine during plugin installation; `$setup-engine` remains
  the engine-selection workflow after studio installation.
- Making arbitrary multi-file updates atomically visible to lock-ignorant
  readers or claiming a cross-filesystem power-loss guarantee.

## 4. User experience

### 4.1 Public release

The user installs **Codex Game Studios** once from the Codex Plugins Directory.
The manager skill is then available across repositories.

Inside a target game repository:

```text
$codex-game-studios install
```

The manager displays a complete installation plan, obtains explicit approval,
applies the recoverable transaction, validates the result, and directs the user
to `$start`.

### 4.2 Prerelease testing

Before public-directory acceptance, testers use the GitHub marketplace:

```bash
codex plugin marketplace add hongyuanc/codex-game-studios --ref v1.0.0-rc.1
codex plugin add codex-game-studios@codex-game-studios
```

They then invoke the same manager skill in each game repository.

### 4.3 Manager operations

```text
$codex-game-studios install
$codex-game-studios update
$codex-game-studios verify
$codex-game-studios repair
$codex-game-studios uninstall
```

- `install`: apply the embedded full operational payload to an uninstalled
  repository.
- `update`: move an installed repository to the plugin's embedded payload
  version while preserving customizations and stopping on conflicts.
- `verify`: perform read-only ownership, hash, managed-block, configuration,
  hook, agent, skill, engine-pack, and reference validation.
- `repair`: restore missing or corrupted uncustomized managed files from the
  currently installed payload version.
- `uninstall`: remove only safely removable manager-owned content and managed
  blocks; preserve customized or project-owned files and report them.

## 5. Plugin layout

```text
.agents/plugins/marketplace.json
plugins/
  codex-game-studios/
    .codex-plugin/
      plugin.json
    LICENSE
    ATTRIBUTION.md
    README.md
    skills/
      codex-game-studios/
        SKILL.md
        references/
          install-contract.md
          conflict-policy.md
          recovery.md
    scripts/
      studio_manager.py
      payload.py
      transaction.py
      managed_blocks.py
    assets/
      payload-manifest.json
      studio/
        ... generated operational payload ...
```

`plugin.json` uses:

```json
{
  "name": "codex-game-studios",
  "version": "1.0.0",
  "description": "Install and manage a complete Codex-native game-development studio in a repository.",
  "author": {
    "name": "hongyuanc"
  },
  "repository": "https://github.com/hongyuanc/codex-game-studios",
  "homepage": "https://github.com/hongyuanc/codex-game-studios",
  "license": "MIT",
  "keywords": ["codex", "game-development", "godot", "unity", "unreal"],
  "skills": "./skills/",
  "interface": {
    "displayName": "Codex Game Studios",
    "shortDescription": "Install a complete Codex-native game studio.",
    "longDescription": "Safely install, update, verify, repair, and remove a coordinated Codex game-development studio in Git repositories.",
    "developerName": "hongyuanc",
    "category": "Developer Tools",
    "capabilities": ["Read", "Write"],
    "websiteURL": "https://github.com/hongyuanc/codex-game-studios",
    "defaultPrompt": [
      "Use $codex-game-studios install to add the studio to this game repository."
    ]
  }
}
```

The plugin does not register its embedded project hooks as plugin lifecycle
hooks. Project hooks become active only after the user approves installation,
reviews the repository configuration, and trusts the repository.

## 6. Operational payload boundary

The generated payload includes the complete usable studio:

- a managed Codex Game Studios block for root `AGENTS.md`;
- nested `AGENTS.md` instructions for existing studio scopes;
- `.agents/skills/` with all 73 project workflows;
- `.codex/agents/` with the 34 core profiles;
- `.codex/agent-packs/` with the three immutable five-profile engine packs;
- `.codex/hooks.json` and `.codex/hooks/`;
- `.codex/docs/` references and templates;
- `.codex/studio.toml`;
- studio-owned keys for `.codex/config.toml`;
- `tools/codex_studio/`, including engine-pack and installed-mode validation;
- `Codex Studio Testing Framework/` references used by runtime skills;
- required nested instruction directories and `.gitkeep` files;
- `docs/COLLABORATIVE-DESIGN-PRINCIPLE.md` and `docs/WORKFLOW-GUIDE.md`;
- `docs/engine-reference/`;
- a plugin-installed attribution and MIT notice under
  `.codex/codex-game-studios/legal/`.

The payload excludes source-repository maintenance material:

- root `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, and
  `UPGRADING.md`;
- `.github/` issue templates, workflows, CODEOWNERS, and funding metadata;
- `docs/superpowers/` design and implementation plans;
- `.superpowers/` development reports;
- `production/migration/` source-migration evidence;
- source-repository release automation and release notes;
- repository-maintainer tests that validate the public template itself;
- Git metadata, caches, recovery data, virtual environments, and local state.

The plugin carries its manager and integration tests. It runs target-facing
verification from the plugin against the installed repository rather than
copying maintainer tests into the game's test organization.

## 7. Payload generation and integrity

A standard-library Python release builder generates
`plugins/codex-game-studios/assets/studio/` from an explicit allowlist.

For every payload entry, `payload-manifest.json` records:

- relative path;
- entry type;
- normalized mode;
- SHA-256 hash for regular files;
- ownership category;
- shared-file merge strategy, when applicable;
- whether the entry is required for installed-mode validation.

Generation fails on:

- symlinks, junctions, reparse/name-surrogate points, or special files;
- absolute, parent-traversal, malformed, non-normalized, or duplicate paths;
- unexpected files beneath allowlisted roots;
- missing required files;
- source/payload byte drift;
- a manifest version different from the plugin version;
- omitted MIT or attribution files.

The generated payload tree is committed transparently rather than stored only
as an opaque compressed archive. Tests prove exact source-to-payload parity for
every generated entry.

## 8. Target installation state

The installed repository records manager state beneath:

```text
.codex/codex-game-studios/
  installation.json
  manager.lock
  recovery/
  legal/
    LICENSE
    ATTRIBUTION.md
```

`installation.json` records:

- schema version;
- installed plugin and payload version;
- installation transaction identifier;
- installed timestamp;
- source payload-manifest digest;
- each managed path and its installed hash;
- each shared-file managed block and its installed block hash;
- each preserved collision or approved merge decision;
- installed-mode validator version;
- recovery journal status.

The installation record is checksummed. Missing, malformed, unsupported, or
checksum-invalid state blocks mutation and routes the user to read-only
diagnosis or an explicitly approved recovery workflow.

## 9. Shared-file merging

Shared files are never replaced wholesale.

### 9.1 `AGENTS.md`

The manager appends or updates one exact managed block:

```text
<!-- codex-game-studios:start -->
... durable studio instructions ...
<!-- codex-game-studios:end -->
```

Existing project guidance remains outside the block. Duplicate, nested,
unbalanced, or malformed manager markers are conflicts. If existing guidance
materially contradicts the studio safety, engine, or collaboration contract,
the plan reports the lines and stops for user resolution.

### 9.2 `.codex/config.toml`

The manager owns only the approved studio keys, initially:

- `agents.max_depth`;
- `agents.max_threads`;
- `features.hooks`.

Unrelated tables and keys are preserved byte-for-byte where possible. A
different existing value is a visible merge decision, never an automatic
overwrite.

### 9.3 `.gitignore`

When ignore rules are required, they use one exact managed block. Existing
rules and comments are preserved. The block follows the same marker integrity
and ownership-hash rules as `AGENTS.md`.

## 10. Ownership and conflict policy

Dedicated payload paths use strict ownership hashes.

- Missing target: create it.
- Existing byte-identical target: adopt it into the installation record.
- Existing unowned different target: conflict; do not overwrite.
- Managed target matching its recorded hash: eligible for update or removal.
- Managed target differing from its recorded hash: customized conflict;
  preserve it and stop the relevant mutation.
- User-created path absent from the manifest: never remove it.
- Game-owned paths under `src/`, `assets/`, `design/`, `docs/architecture/`, and
  `production/`: never modify except for exact dedicated studio paths already
  approved in the payload manifest.

Version 1 does not perform semantic three-way merges of customized framework
files. It presents base, installed, and incoming hashes plus paths and asks the
user to resolve the file before retrying.

## 11. Transaction protocol

Every mutating operation uses:

1. Resolve and validate the Git repository root.
2. Verify the embedded payload manifest and every payload entry.
3. Read and validate existing installation state.
4. Inspect all target paths without following links.
5. Produce a complete deterministic plan with create, adopt, merge, preserve,
   conflict, update, backup, and removal actions.
6. Compute a digest binding the operation, plugin version, payload digest,
   installation state, shared-file state, and target-file hashes.
7. Show the plan and request explicit approval.
8. After approval, acquire `.codex/codex-game-studios/manager.lock` with a
   cooperative process lock and bounded timeout. Creating the control directory
   and lock is the first authorized project mutation.
9. Recompute the digest while holding the lock; abort if anything changed.
10. Persist a same-filesystem recovery snapshot and journal before payload or
    shared-file mutation.
11. Apply actions through path-safe temporary-file replacement or
    descriptor/handle-safe operations as appropriate.
12. Run installed-mode validation.
13. Persist the checksummed installation record and mark the journal committed.
14. Retain only the documented recovery generation after success.
15. Release the manager lock on every success or failure path; a retained lock
    file is inert when no process holds its operating-system lock.

If application or validation fails, the manager attempts byte-for-byte logical
rollback and verifies the restored state. If rollback fails, it preserves the
only good recovery snapshot and journal, stops all writes, and reports explicit
recovery instructions. It never claims success after incomplete rollback.

## 12. Operation-specific behavior

### 12.1 Install

- Requires a Git repository and Python 3.11 or newer.
- Refuses an existing valid installation record; use `update` or `verify`.
- Allows existing studio-identical files to be adopted.
- Stops on every unowned non-identical collision.
- Ends by running installed-mode validation and recommending `$start`.

### 12.2 Update

- Updates only files still matching recorded ownership hashes.
- Preserves and reports customized managed files.
- Stops before writing when conflicts exist.
- Updates shared managed blocks independently from surrounding project content.
- Records the new plugin/payload version only after final validation passes.

### 12.3 Verify

- Is always read-only.
- Verifies state checksum, payload provenance, managed paths, customized files,
  blocks, Codex configuration, skills, agents, hooks, engine packs, references,
  and installed legal notices.
- Distinguishes missing, corrupted, customized, unmanaged-collision, stale, and
  unsupported-version findings.

### 12.4 Repair

- Repairs only missing or corrupted uncustomized manager-owned content.
- Is not an implicit update. Repair proceeds only when the plugin's embedded
  payload version and digest match the version recorded by the repository.
  Otherwise it directs the user to install the matching plugin release or run
  `update` with the currently installed plugin.
- Requires a plan, approval, recovery snapshot, and final validation.
- Refuses to overwrite a customized or newly occupied path.

### 12.5 Uninstall

- Removes only files matching recorded manager-owned hashes.
- Removes only valid manager-owned shared blocks.
- Preserves customized managed files, user files, game artifacts, and unrelated
  configuration.
- Reports preserved framework remnants for manual resolution.
- Removes installation state only when the remaining state is internally
  consistent and final uninstall validation passes.
- Retains the attribution/license notice when preserved MIT-covered framework
  content remains in the repository.

## 13. Installed-mode validation

The existing source-template validator gains a distinct installed mode. Source
validation remains strict about the public framework repository. Installed mode
validates only operational requirements and tolerates game-owned repository
content.

Installed mode checks:

- installation-record schema and checksum;
- operational payload ownership and hashes;
- shared managed-block integrity;
- 34 core agents and three immutable five-profile engine packs;
- configured-state 34/39 active-agent rules;
- 73 project skills;
- Codex configuration and hook registrations;
- no unsafe links, special files, traversal, or machine-specific paths;
- required studio docs, templates, testing-framework references, and engine
  references;
- MIT license and upstream attribution under the installation-state legal path;
- absence of unrecorded manager writes outside the operational allowlist.

`$codex-game-studios verify` invokes installed mode directly. Source-repository
CI runs both source mode and representative installed-mode fixtures.

## 14. Security and trust boundaries

- Plugin installation and project installation are separate trust events.
- The manager makes no network requests during project operations.
- All source payload bytes are embedded and hash-verified.
- Project hooks are not enabled as plugin hooks before project installation.
- Planning and verification are read-only; they do not create a project lock or
  installation-state directory.
- Mutation requires explicit approval of a digest-bound plan.
- The manager writes only beneath the resolved repository root and refuses
  links, junctions, reparse/name-surrogate points, special files, malformed
  Unicode, NULs, traversal, and root changes.
- Hooks remain best-effort defense-in-depth; Codex permissions, approvals, and
  durable instructions remain the authorization boundary.
- The plugin requests no authentication and collects no secrets or telemetry.
- Install records contain paths and hashes only, not source contents or user
  data.

## 15. Licensing and attribution

The upstream project is
[Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios)
and is distributed under the MIT License.

Every plugin package and installed operational payload must include:

- the complete upstream MIT license text;
- `Copyright (c) 2026 Donchitos`;
- the upstream repository URL;
- identification as an independent Codex-native adaptation;
- a description of the Codex-native modifications;
- no claim of endorsement by Donchitos, Anthropic, or OpenAI;
- `Copyright (c) 2026 hongyuanc` for the Codex-native modifications, without
  removing or replacing the upstream notice.

`ATTRIBUTION.md` also inventories third-party material and its separate license
when present. Release validation fails on a missing notice, unknown bundled
third-party asset, or incompatible license. Marketplace policy, trademark, and
brand compliance remain separate release gates from the MIT permission.

## 16. Versioning

Plugin and payload versions are identical:

```text
Plugin: 1.0.0
Payload: 1.0.0
Git tag: v1.0.0
```

Release candidates use semver prereleases such as `v1.0.0-rc.1`. The manager
rejects an unsupported future installation-state schema, downgrade without an
explicitly supported path, or plugin/payload version mismatch.

Marketplace prerelease sources pin a tag or immutable commit. Public-directory
submission uses the final validated version.

## 17. Testing and release gates

### 17.1 Unit and contract tests

- plugin and marketplace manifest schemas;
- payload path normalization, hashing, and allowlist enforcement;
- ownership-manifest schema and checksum;
- exact managed-block parsing and malformed-marker rejection;
- TOML merge ownership and unrelated-key preservation;
- plan determinism and digest invalidation;
- link/reparse/special-file rejection;
- descriptor/handle cleanup and error preservation;
- operation-specific conflict classification.

### 17.2 Transaction tests

- fresh install;
- install over existing `AGENTS.md`, Codex config, and `.gitignore`;
- adoption of byte-identical framework files;
- refusal of unowned collisions;
- repository mutation after plan approval but before apply;
- injected failure at each journal phase;
- successful rollback and rollback failure preservation;
- update with unchanged and customized managed files;
- verify findings for missing, corrupted, customized, and stale state;
- repair refusal on customized targets;
- uninstall with clean and customized managed content;
- repeated operations and concurrent writer refusal.

### 17.3 End-to-end tests

- install into fresh, Godot, Unity, and Unreal fixtures;
- run `$setup-engine` after installation for each engine;
- switch engine packs and validate hashes;
- run manager verify after engine activation;
- update from the prior release fixture;
- uninstall while preserving representative game artifacts and custom Codex
  settings;
- install and use the plugin from a local marketplace snapshot.

### 17.4 Platform matrix

Release CI runs on native Windows, macOS, and Linux with Python 3.11 or newer.
No public release is marked fully cross-platform without a native Windows
transaction run.

### 17.5 Release checklist

- full source studio suite passes;
- source final validator passes;
- plugin tests and installed-mode fixtures pass;
- generated payload is fresh and source-identical;
- plugin/payload versions match the Git tag;
- license, attribution, security, repository, and publisher metadata are
  complete;
- prerelease marketplace installation succeeds;
- release archive checksums are published;
- public Plugins Directory submission package is review-ready.

## 18. Error reporting

Manager errors use stable categories and actionable messages:

- `UNSUPPORTED_ENVIRONMENT`
- `UNSAFE_PATH`
- `INVALID_PAYLOAD`
- `INVALID_INSTALLATION_STATE`
- `LOCKED`
- `STALE_PLAN`
- `UNMANAGED_COLLISION`
- `CUSTOMIZED_MANAGED_FILE`
- `VALIDATION_FAILED`
- `ROLLBACK_FAILED`

Every failure reports the operation, affected relative paths, whether any write
occurred, recovery/journal state, and the exact safe next action. Messages never
disclose file contents, secrets, or machine-specific absolute paths in public
logs.

## 19. Success criteria

Version 1 is complete when:

1. A user installs the public plugin once and can run
   `$codex-game-studios install` in a game repository.
2. The manager installs the full operational studio without replacing
   game-owned repository metadata or content.
3. Fresh and existing-repository installs are plan-first, approval-bound,
   recoverable, and validated.
4. Update, verify, repair, and uninstall honor strict ownership and
   customization preservation.
5. The embedded payload is deterministic, transparent, version-matched, and
   license-complete.
6. Source and installed validation modes both pass.
7. Native Windows, macOS, and Linux CI passes.
8. The GitHub prerelease marketplace flow works.
9. The plugin package is ready for official Codex Plugins Directory review.
