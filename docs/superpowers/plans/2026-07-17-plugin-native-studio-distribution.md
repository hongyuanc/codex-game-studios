# Plugin-Native Studio Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 73 Codex Game Studios workflows available immediately when the plugin is installed, with `$codex-game-studios:start` as the entry point and no mandatory repository-wide installation.

**Architecture:** Point the plugin skill component at the deterministic `assets/studio/.agents/skills/` catalog, then make canonical skill instructions portable between source and plugin locations. Fresh repositories use a bounded Start-driven initialization contract; the retained transaction manager is isolated to authenticated 1.0.0 compatibility, repair, migration, and uninstall.

**Tech Stack:** Python 3.11 standard library, Codex plugin manifests and Markdown skills, deterministic JSON payloads, `unittest`, and existing secure-filesystem/transaction modules.

## Global Constraints

- Plugin installation exposes exactly 73 studio skills and causes zero target-repository writes.
- The explicit entry point is `$codex-game-studios:start`.
- Fresh initialization contains at most ten mutating actions and never creates `.agents/skills/`.
- Static resources remain plugin-local; persistent project state remains repository-local.
- Unselected engine references are never copied into a fresh project.
- Existing public 1.0.0 installations retain digest-bound verify, repair, migration, and uninstall support.
- The plugin version becomes `2.0.0`; Python remains compatible with 3.11 and gains no runtime dependency.
- Never stage `.superpowers/sdd/*` or unrelated untracked plans.
- Do not push, tag, release, publish, or modify the real Embermarch repository without separate authorization.

---

### Task 1: Expose the native 73-skill catalog

**Files:**
- Modify: `plugins/codex-game-studios/.codex-plugin/plugin.json`
- Modify: `plugins/codex-game-studios/assets/payload-policy.json`
- Modify: `tools/codex_studio/validate.py`
- Modify: `tests/plugin/test_plugin_manifest.py`
- Modify: `tests/plugin/test_plugin_docs.py`
- Modify: `tests/plugin/test_release_contract.py`
- Delete: `plugins/codex-game-studios/skills/codex-game-studios/SKILL.md`
- Delete: `plugins/codex-game-studios/skills/codex-game-studios/references/install-contract.md`
- Delete: `plugins/codex-game-studios/skills/codex-game-studios/references/conflict-policy.md`
- Delete: `plugins/codex-game-studios/skills/codex-game-studios/references/recovery.md`
- Generate: `plugins/codex-game-studios/assets/payload-manifest.json`
- Generate: `plugins/codex-game-studios/assets/studio/tools/codex_studio/validate.py`

**Interfaces:**
- Consumes: `.agents/skills/<name>/SKILL.md` and the deterministic payload builder.
- Produces: `skills: "./assets/studio/.agents/skills/"`, version `2.0.0`, and exactly 73 discoverable plugin skills.

- [ ] **Step 1: Write the failing inventory test**

```python
def test_plugin_manifest_exposes_complete_native_skill_catalog(self):
    data = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    bundled = {
        path.parent.name
        for path in (PLUGIN / data["skills"]).resolve().glob("*/SKILL.md")
    }
    canonical = {
        path.parent.name for path in (ROOT / ".agents/skills").glob("*/SKILL.md")
    }
    self.assertEqual("2.0.0", data["version"])
    self.assertEqual("./assets/studio/.agents/skills/", data["skills"])
    self.assertEqual(canonical, bundled)
    self.assertEqual(73, len(bundled))
    self.assertFalse((PLUGIN / "skills/codex-game-studios/SKILL.md").exists())
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.plugin.test_plugin_manifest tests.plugin.test_plugin_docs`

Expected: FAIL because version 1.0.1 exposes only the duplicated manager skill.

- [ ] **Step 3: Implement the public manifest contract**

Set `version` to `2.0.0`, `skills` to `./assets/studio/.agents/skills/`, and `interface.defaultPrompt` to:

```json
["Use $codex-game-studios:start to begin in this game repository."]
```

Preserve author/repository/homepage/license/keywords. Update the payload policy and installed validator version, delete the obsolete manager skill tree, and change release filename assertions from `1.0.1` to `2.0.0`.

- [ ] **Step 4: Rebuild and verify**

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root .`

Expected: `generated codex-game-studios payload 2.0.0`.

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root . --check`

Expected: `Codex Game Studios payload: FRESH`.

- [ ] **Step 5: Run GREEN and commit**

Run: `python3.11 -m unittest -v tests.plugin.test_plugin_manifest tests.plugin.test_plugin_docs tests.plugin.test_release_contract`

```bash
git add plugins/codex-game-studios tools/codex_studio/validate.py \
  tests/plugin/test_plugin_manifest.py tests/plugin/test_plugin_docs.py \
  tests/plugin/test_release_contract.py
git commit -m "feat: expose native studio skill catalog" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 2: Make skill dependencies and static resources portable

**Files:**
- Create: `tests/plugin/test_plugin_skill_catalog.py`
- Modify: `tools/codex_studio/validate.py`
- Modify: `tests/studio/test_repository_validation.py`
- Modify dependency-bearing skills: `bug-report`, `bug-triage`, `dev-story`, `help`, `skill-improve`, `skill-test`, `smoke-check`, `sprint-plan`, `story-done`, `test-evidence-review`, `test-helpers`, and `test-setup` under `.agents/skills/<name>/SKILL.md`
- Modify every canonical skill reported by: `rg -l '\.codex/docs/|docs/engine-reference/|Codex Studio Testing Framework/' .agents/skills/*/SKILL.md`
- Generate: `plugins/codex-game-studios/assets/studio/.agents/skills/*/SKILL.md`
- Generate: `plugins/codex-game-studios/assets/payload-manifest.json`

**Interfaces:**
- Consumes: Codex skill-relative resource resolution.
- Produces: `validate_plugin_skill_catalog(root: pathlib.Path, plugin: pathlib.Path) -> list[ValidationIssue]`; skill discovery instead of repo-local file probes; `../../../` bundled-resource paths.

- [ ] **Step 1: Write failing portability tests**

```python
class PluginSkillCatalogTests(unittest.TestCase):
    def test_catalog_has_source_parity_and_valid_skills(self):
        source = ROOT / ".agents/skills"
        bundled = PLUGIN / "assets/studio/.agents/skills"
        names = {path.parent.name for path in source.glob("*/SKILL.md")}
        self.assertEqual(73, len(names))
        for name in sorted(names):
            self.assertEqual(
                (source / name / "SKILL.md").read_bytes(),
                (bundled / name / "SKILL.md").read_bytes(),
            )
            self.assertEqual([], validate_skill(bundled / name / "SKILL.md"))

    def test_skills_do_not_probe_repo_local_skill_installation(self):
        pattern = re.compile(r"\.agents/skills/[a-z0-9-]+/SKILL\.md")
        for path in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
            self.assertIsNone(pattern.search(path.read_text()), path)
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.plugin.test_plugin_skill_catalog`

Expected: FAIL on hardcoded dependency probes and unresolved static paths.

- [ ] **Step 3: Replace physical probes with catalog checks**

Use this contract, substituting the actual dependency name:

```markdown
Before invoking `$team-qa`, confirm that `team-qa` is present in the current
task's available skill catalog. If unavailable, report
`Staged dependency: $team-qa is not available`, defer the handoff, and do not
search for or copy a repository-local skill file.
```

- [ ] **Step 4: Correct all resource references**

Apply these exact rules:

```text
Bundled static rule/template: ../../../.codex/docs/<path>
Bundled engine reference:     ../../../docs/engine-reference/<engine>/<path>
Bundled testing reference:    ../../../Codex Studio Testing Framework/<path>
Persistent authority:         repository-root `.codex/studio.toml`
Persistent preferences:       repository-root `.codex/docs/technical-preferences.md`
```

Make final repository validation enforce the same rules using `validate_plugin_skill_catalog`.

- [ ] **Step 5: Rebuild, run GREEN, and commit**

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root .`

Run: `python3.11 -m unittest -v tests.plugin.test_plugin_skill_catalog tests.studio.test_repository_validation`

```bash
git add .agents/skills plugins/codex-game-studios/assets \
  tools/codex_studio/validate.py tests/plugin/test_plugin_skill_catalog.py \
  tests/studio/test_repository_validation.py
git commit -m "fix: make studio skills plugin-portable" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 3: Make Start perform bounded first-run initialization

**Files:**
- Modify: `.agents/skills/start/SKILL.md`
- Modify: `Codex Studio Testing Framework/skills/utility/start.md`
- Modify: `tests/studio/test_start_skill.py`
- Modify: `tests/studio/test_testing_framework.py`
- Modify: `tests/plugin/test_plugin_skill_catalog.py`
- Generate: `plugins/codex-game-studios/assets/studio/.agents/skills/start/SKILL.md`
- Generate: `plugins/codex-game-studios/assets/payload-manifest.json`

**Interfaces:**
- Consumes: Git root, available skill catalog, optional repository-root studio authority, and existing game artifacts.
- Produces: a maximum-ten-action `Initialization changeset`, zero writes until approval, and no global-resource installation.

- [ ] **Step 1: Write failing Start tests**

```python
def test_start_supports_plugin_native_uninitialized_repository(self):
    text = START.read_text()
    self.assertIn("$codex-game-studios:start", text)
    self.assertIn("Initialization changeset", text)
    self.assertIn("at most 10 mutating actions", text)
    self.assertIn("zero writes before explicit approval", text)
    self.assertIn("must not create `.agents/skills/`", text)
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.studio.test_start_skill tests.studio.test_testing_framework tests.plugin.test_plugin_skill_catalog`

Expected: FAIL because Start currently treats missing authority as an error.

- [ ] **Step 3: Add the first-run protocol**

```markdown
## Plugin-native first run

If repository-root `.codex/studio.toml` is absent, continue read-only project
detection. Present one `Initialization changeset` containing only persistent
project authority required by the selected next step. It must contain at most
10 mutating actions and produce zero writes before explicit approval. It must
not create `.agents/skills/`, `.codex/agents/`, `.codex/agent-packs/`,
`Codex Studio Testing Framework/`, unselected engine references, or speculative
empty project directories.
```

Document default authority values: engine/version/language `unconfigured`, `review_mode = "phase-gated"`, and `active_engine_pack = "none"`.

- [ ] **Step 4: Rebuild, run GREEN, and commit**

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root .`

Run: `python3.11 -m unittest -v tests.studio.test_start_skill tests.studio.test_testing_framework tests.plugin.test_plugin_skill_catalog`

```bash
git add .agents/skills/start/SKILL.md \
  'Codex Studio Testing Framework/skills/utility/start.md' \
  plugins/codex-game-studios/assets tests/studio/test_start_skill.py \
  tests/studio/test_testing_framework.py tests/plugin/test_plugin_skill_catalog.py
git commit -m "feat: add plugin-native Start initialization" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 4: Make agent coordination plugin-portable

**Files:**
- Create: `.codex/docs/plugin-agent-delegation.md`
- Modify: `.codex/docs/coordination-rules.md`
- Modify every skill reported by: `rg -l '\b(delegate|spawn|subagent|custom-agent)\b' .agents/skills/*/SKILL.md`
- Modify: `tests/studio/test_agents.py`
- Modify: `tests/studio/test_delivery_skills.py`
- Modify: `tests/plugin/test_plugin_skill_catalog.py`
- Generate: `plugins/codex-game-studios/assets/studio/.codex/docs/plugin-agent-delegation.md`
- Generate: `plugins/codex-game-studios/assets/studio/.agents/skills/*/SKILL.md`
- Generate: `plugins/codex-game-studios/assets/payload-manifest.json`

**Interfaces:**
- Consumes: plugin-local role TOML via `../../../.codex/agents/<role>.toml`, engine-pack TOML, and current collaboration capabilities.
- Produces: native named role -> default delegated agent with explicit role contract -> single-agent fallback.

- [ ] **Step 1: Write failing delegation tests**

```python
def test_delegating_skills_use_plugin_portable_role_protocol(self):
    for path in delegating_skill_paths():
        self.assertIn(
            "../../../.codex/docs/plugin-agent-delegation.md",
            path.read_text(),
            path,
        )
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.studio.test_agents tests.studio.test_delivery_skills tests.plugin.test_plugin_skill_catalog`

Expected: FAIL because no shared plugin delegation protocol exists.

- [ ] **Step 3: Create and reference the routing contract**

```markdown
1. If the collaboration API exposes the named role, delegate with that role.
2. Otherwise read `../../../.codex/agents/<role>.toml`, pass its complete role
   contract to a default delegated agent, and preserve supported model settings.
3. If delegation is unavailable, execute the bounded role checklist in the
   current agent and label the evidence `single-agent fallback`.
```

Require direct-child ownership, bounded tasks, parent synthesis, and no copying role TOML into the project. Add this exact preflight to each delegating skill:

```markdown
Resolve every role through `../../../.codex/docs/plugin-agent-delegation.md`;
do not require a repository-local `.codex/agents/` or `.codex/agent-packs/` tree.
```

- [ ] **Step 4: Rebuild, run GREEN, and commit**

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root .`

Run: `python3.11 -m unittest -v tests.studio.test_agents tests.studio.test_delivery_skills tests.plugin.test_plugin_skill_catalog`

```bash
git add .codex/docs .agents/skills plugins/codex-game-studios/assets \
  tests/studio/test_agents.py tests/studio/test_delivery_skills.py \
  tests/plugin/test_plugin_skill_catalog.py
git commit -m "feat: add plugin-portable agent delegation" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 5: Authenticate the public 1.0.0 legacy payload

**Files:**
- Modify: `.gitignore`
- Create: `plugins/codex-game-studios/assets/legacy/1.0.0/payload-manifest.json`
- Create: `plugins/codex-game-studios/assets/legacy/1.0.0/studio.zip`
- Create: `plugins/codex-game-studios/scripts/legacy_payload.py`
- Modify: `tools/codex_studio/package_plugin.py`
- Modify: `tests/plugin/test_payload.py`
- Modify: `tests/plugin/test_release_contract.py`

**Interfaces:**
- Consumes: exact public payload from commit `b854a442399610f61e5d30b7861dfd5633503fcb`.
- Produces: `load_legacy_payload(plugin: Path, version: str) -> LegacyPayload`; `verified_legacy_snapshot(plugin: Path, version: str) -> ContextManager[tuple[Path, PayloadManifest]]`; supported versions `frozenset({"1.0.0"})`.

- [ ] **Step 1: Write failing capsule tests**

```python
def test_public_legacy_payload_is_authenticated_and_complete(self):
    legacy = load_legacy_payload(PLUGIN, "1.0.0")
    self.assertEqual("1.0.0", legacy.manifest.version)
    with verified_legacy_snapshot(PLUGIN, "1.0.0") as (root, manifest):
        self.assertEqual([], verify_manifest_snapshot(root, manifest))
        self.assertTrue((root / "assets/studio/.agents/skills/start/SKILL.md").is_file())
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.plugin.test_payload tests.plugin.test_release_contract`

Expected: FAIL because the legacy capsule interface is absent.

- [ ] **Step 3: Implement the capsule loader**

```python
@dataclasses.dataclass(frozen=True)
class LegacyPayload:
    version: str
    archive: Path
    manifest: PayloadManifest

SUPPORTED_LEGACY_VERSIONS = frozenset({"1.0.0"})

def load_legacy_payload(plugin: Path, version: str) -> LegacyPayload:
    if version not in SUPPORTED_LEGACY_VERSIONS:
        raise LegacyPayloadError("unsupported legacy plugin version")
    base = plugin / "assets/legacy" / version
    manifest = load_manifest(base / "payload-manifest.json")
    if manifest.version != version:
        raise LegacyPayloadError("legacy payload version mismatch")
    return LegacyPayload(version, base / "studio.zip", manifest)
```

`verified_legacy_snapshot` extracts into a private temporary directory and rejects absolute paths, `..`, duplicate normalized names, links, special files, undeclared entries, mode drift, and hash drift before yielding. Generate the archive deterministically from public commit `b854a44`; runtime must not depend on Git history or network access.

Add exactly `!plugins/codex-game-studios/assets/legacy/1.0.0/studio.zip`
after the global `*.zip` rule in `.gitignore`; do not allowlist any other
archive path.

- [ ] **Step 4: Run GREEN and commit**

Run: `python3.11 -m unittest -v tests.plugin.test_payload tests.plugin.test_release_contract`

```bash
git add .gitignore plugins/codex-game-studios/assets/legacy \
  plugins/codex-game-studios/scripts/legacy_payload.py \
  tools/codex_studio/package_plugin.py tests/plugin/test_payload.py \
  tests/plugin/test_release_contract.py
git commit -m "feat: authenticate legacy studio payload" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 6: Add digest-bound legacy migration

**Files:**
- Modify: `plugins/codex-game-studios/scripts/models.py`
- Modify: `plugins/codex-game-studios/scripts/studio_manager.py`
- Modify: `plugins/codex-game-studios/scripts/transaction.py`
- Modify: `tools/codex_studio/validate.py`
- Modify: `.agents/skills/start/SKILL.md`
- Create: `tests/plugin/test_legacy_migration.py`
- Modify: `tests/plugin/test_manager_planning.py`
- Modify: `tests/plugin/test_manager_cli.py`
- Modify: `tests/plugin/test_lifecycle_integration.py`
- Generate: `plugins/codex-game-studios/assets/studio/tools/codex_studio/validate.py`
- Generate: `plugins/codex-game-studios/assets/payload-manifest.json`

**Interfaces:**
- Consumes: authenticated 1.0.0 `InstallationState`, Task 5 legacy snapshot, observations, and existing digest-bound transactions.
- Produces: operation `migrate`; schema-2 `MigrationState`; Start routes for legacy verify/repair/migrate/uninstall.

- [ ] **Step 1: Write failing migration tests**

```python
def test_migrate_removes_only_unchanged_redundant_legacy_paths(self):
    write_legacy_100_fixture(self.repo, PLUGIN)
    customized = self.repo / ".agents/skills/start/SKILL.md"
    customized.write_text("user customization\n")
    plan = plan_operation("migrate", self.repo, PLUGIN, new_approval_context("migrate"))
    self.assertNotIn(
        ".agents/skills/start/SKILL.md",
        {action.path for action in plan.actions if action.kind == "remove"},
    )
    self.assertIn(
        ".agents/skills/start/SKILL.md",
        {action.path for action in plan.actions if action.kind == "preserve"},
    )
```

```python
def test_legacy_migration_rolls_back_exactly(self):
    write_legacy_100_fixture(self.repo, PLUGIN)
    before = snapshot_tree(self.repo)
    approved = approved_plan("migrate", self.repo)
    with failpoint("after-first-remove"):
        result = apply_approved(approved)
    self.assertEqual("ROLLED_BACK", result.status)
    self.assertEqual(before, snapshot_tree(self.repo))
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.plugin.test_legacy_migration tests.plugin.test_manager_planning tests.plugin.test_manager_cli`

Expected: FAIL because `migrate` and schema-2 state do not exist.

- [ ] **Step 3: Add strict migration state**

```python
@dataclasses.dataclass(frozen=True)
class MigrationState:
    schema_version: int
    plugin_version: str
    legacy_version: str
    legacy_state_checksum: str
    preserved_paths: tuple[str, ...]
    migrated_at: str
    checksum: str
```

Implement canonical serialization/checksum verification, exact keys, normalized sorted unique preserved paths, and schema value `2`. Write it to `.codex/codex-game-studios/installation.json` only as the transaction's final state write.

- [ ] **Step 4: Implement planning and application**

Add `migrate` to `OPERATIONS`. Preserve these project paths:

```python
PERSISTENT_PROJECT_PATHS = frozenset({
    ".codex/studio.toml",
    ".codex/docs/technical-preferences.md",
    ".codex/config.toml",
    "AGENTS.md",
    ".gitignore",
})
```

Treat `.agents/skills/`, `.codex/agents/`, `.codex/agent-packs/`, `.codex/hooks/`, `Codex Studio Testing Framework/`, and `docs/engine-reference/` as redundant legacy prefixes. Remove only securely observed entries matching authenticated type/mode/hash. Preserve customized files and directories with user children. Reuse transaction snapshot, journal, rollback, validation, and replan checks.

Route schema-1 version 1.0.0 verify/repair/uninstall through the verified legacy snapshot. Route schema-2 state through plugin-native validation.

- [ ] **Step 5: Update Start routing**

```markdown
If repository-root `.codex/codex-game-studios/installation.json` is schema 1,
offer exactly `verify legacy installation`, `repair legacy installation`,
`migrate to plugin-native`, or `uninstall legacy installation`. Never migrate
automatically. Present the complete digest-bound plan before approval.
```

- [ ] **Step 6: Run GREEN, rebuild, and commit**

Run: `python3.11 -m unittest -v tests.plugin.test_legacy_migration tests.plugin.test_manager_planning tests.plugin.test_manager_cli tests.plugin.test_transaction tests.plugin.test_lifecycle_integration`

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root .`

```bash
git add plugins/codex-game-studios/scripts plugins/codex-game-studios/assets \
  tools/codex_studio/validate.py .agents/skills/start/SKILL.md \
  tests/plugin/test_legacy_migration.py tests/plugin/test_manager_planning.py \
  tests/plugin/test_manager_cli.py tests/plugin/test_lifecycle_integration.py
git commit -m "feat: migrate legacy studio installations" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 7: Replace public onboarding and release contracts

**Files:**
- Modify: `README.md`
- Modify: `plugins/codex-game-studios/README.md`
- Modify: `plugins/codex-game-studios/ATTRIBUTION.md`
- Modify: `tests/studio/test_public_docs.py`
- Modify: `tests/plugin/test_plugin_docs.py`
- Modify: `tests/plugin/test_release_contract.py`

**Interfaces:**
- Consumes: Tasks 1-6 behavior.
- Produces: one fresh flow—install, new task, `$codex-game-studios:start`—plus separate legacy help.

- [ ] **Step 1: Write failing documentation tests**

```python
def test_readme_uses_plugin_native_start_flow(self):
    text = (ROOT / "README.md").read_text()
    self.assertIn("$codex-game-studios:start", text)
    self.assertIn("all 73 studio skills", text)
    self.assertNotIn("$codex-game-studios install", text)
```

- [ ] **Step 2: Run RED**

Run: `python3.11 -m unittest -v tests.studio.test_public_docs tests.plugin.test_plugin_docs tests.plugin.test_release_contract`

Expected: FAIL on the old manager-first instructions.

- [ ] **Step 3: Rewrite onboarding**

Document this exact sequence for app and CLI:

```text
1. Install Codex Game Studios from the repository marketplace.
2. Start a new Codex task in the game repository.
3. Run $codex-game-studios:start.
```

State that all 73 skills become available and plugin installation writes nothing to the game repository. Explain that Start asks approval only for small project-specific state. Put 1.0.0 verify/repair/migrate/uninstall under a separate legacy section.

- [ ] **Step 4: Run GREEN and commit**

Run: `python3.11 -m unittest -v tests.studio.test_public_docs tests.plugin.test_plugin_docs tests.plugin.test_release_contract`

```bash
git add README.md plugins/codex-game-studios/README.md \
  plugins/codex-game-studios/ATTRIBUTION.md tests/studio/test_public_docs.py \
  tests/plugin/test_plugin_docs.py tests/plugin/test_release_contract.py
git commit -m "docs: simplify plugin-native onboarding" \
  -m "Design: docs/superpowers/specs/2026-07-17-plugin-native-studio-distribution-design.md"
```

---

### Task 8: Complete the release gate

**Files:**
- Modify only for a bounded defect found by verification; use a new RED/GREEN fix commit and never weaken a test.

**Interfaces:**
- Consumes: Tasks 1-7.
- Produces: independently reviewable local 2.0.0 candidate with no publication.

- [ ] **Step 1: Verify payload and repository**

Run: `python3.11 tools/codex_studio/build_plugin_payload.py --root . --check`

Expected: `Codex Game Studios payload: FRESH`.

Run: `python3.11 -m tools.codex_studio.validate --root . --phase final`

Expected: `Codex Studio validation: PASS`.

- [ ] **Step 2: Run focused suites twice**

```bash
python3.11 -m unittest -v \
  tests.plugin.test_plugin_manifest \
  tests.plugin.test_plugin_skill_catalog \
  tests.plugin.test_legacy_migration \
  tests.plugin.test_lifecycle_integration
```

Expected: all tests pass twice with identical counts.

- [ ] **Step 3: Run the disposable plugin-native behavioral smoke**

Create a disposable Git repository with Embermarch's existing `.editorconfig`,
`.gitattributes`, `.gitignore`, and `project.godot`. Load the built plugin from
its local marketplace in a fresh Codex task, invoke
`$codex-game-studios:start`, approve only its bounded initialization changeset,
then invoke `$codex-game-studios:setup-engine` for Godot. Record evidence that:

```text
all 73 plugin skills were available before repository initialization
the initial changeset contained at most 10 mutating actions
.agents/skills/ was never created
pre-existing Embermarch fixture bytes were unchanged
only Godot reference material was read or selected
```

Run `$codex-game-studios:skill-test` against the installed `start` and
`setup-engine` skills. Expected: both behavioral evaluations PASS. Never use
the real Embermarch repository for this smoke.

- [ ] **Step 4: Run complete suites**

Run: `python3.11 -m unittest discover -s tests/plugin -v`

Run: `python3.11 -m unittest discover -s tests/studio -v`

Expected: all tests pass; only explicitly native-Windows cases may skip on macOS.

- [ ] **Step 5: Run static checks**

```bash
python3.11 -m compileall -q plugins/codex-game-studios/scripts tools/codex_studio tests/plugin tests/studio
git diff --check
rg -n '\$codex-game-studios install|Codex Game Studios: Codex Game Studios' README.md plugins tests
```

Expected: compilation succeeds, diff check emits nothing, and the stale-string scan returns no public/runtime matches.

- [ ] **Step 6: Request independent review**

The reviewer must inspect skill discovery, resource safety, Start's ten-action boundary, agent fallback semantics, legacy archive authentication, migration preservation/rollback, versioning, docs, and tests. The reviewer must not edit or commit.

- [ ] **Step 7: Require native Windows CI before publication**

After a separately authorized push, require successful Windows lifecycle smoke, Plugin (Windows), Plugin (Ubuntu), Plugin (macOS), complete studio suite, and dependent verified-artifacts job. Do not tag, release, or publish from this plan.
