# Skill Test Spec: $start

## Codex Runtime Contract

- Runtime skill: `.agents/skills/start/SKILL.md`
- Runtime name: `start`
- Runtime trigger description: `Use when a first-time user needs project-state detection and guidance to the correct Codex Game Studios workflow.`
- Native invocation: `$start`
- Discovery contract: YAML frontmatter contains exactly `name` and `description`; the name matches the skill directory and the description is nonblank and trigger-oriented.
- Structured decisions: each `request_user_input` call contains 1–3 questions and each question contains 2–3 options. `$start` asks one decision per turn.
- Custom-agent delegation: if needed, the maximum delegation depth is 1; the parent agent synthesizes all evidence and owns user interaction.
- Write boundary: discovery is read-only. Before either permitted write, the parent presents the exact target path and material edit as one complete proposed changeset, then obtains approval. For a plugin-native first run, one bounded `Initialization changeset` is shown before any write.

## Skill Summary

`$start` first detects repository state, then asks two ordered decisions that
classify the project as Path A, B, C, or D. Engine configuration authority is
`.codex/studio.toml`; `engine = "unconfigured"` means `$setup-engine` is needed.
When that repository authority is absent, `$codex-game-studios:start` continues
read-only detection and presents a bounded initialization proposal only after the
next step is selected.
After routing, the skill may propose `production/stage.txt` and a change to the
`review_mode` key in `.codex/studio.toml`. Each write has its own exact proposal
and approval gate. Onboarding performs project-state routing; `$setup-engine`
owns engine selection and configuration.
For a first run, the one Initialization changeset replaces the separate persistent proposals in Phases 4-6.

## Static Assertions

- [ ] State detection reads `.codex/studio.toml` and treats `engine = "unconfigured"` as no active engine pack.
- [ ] Artifact detection checks `design/gdd/game-concept.md`, source files under `src/`, subdirectories under `prototypes/`, Markdown files under `design/gdd/`, and files under `production/sprints/` or `production/milestones/`.
- [ ] Artifact counts exclude every nested `AGENTS.md` and instruction-only files such as `.gitkeep`.
- [ ] The first prompt is "Which broad starting point best describes this project?" with exactly `New or exploratory` and `Defined or existing`.
- [ ] Wait for the first answer before asking the path follow-up.
- [ ] The second prompt has exactly two options: Paths A/B after `New or exploratory`, or Paths C/D after `Defined or existing`.
- [ ] No next skill is run automatically.
- [ ] Path A/B/C maps to stage `Concept`; Path D maps to `Concept`, `Systems Design`, or `Technical Setup` from observed artifacts.
- [ ] Review depth offers exactly `Full`, `Phase-gated (recommended)`, and `Solo`, mapping to `review_mode = "full"`, `review_mode = "phase-gated"`, and `review_mode = "solo"`.
- [ ] A current `review_mode` outside `full`, `phase-gated`, or `solo` is an invalid-authority repair block in detection, preflight, and audit.
- [ ] `production/stage.txt` and `.codex/studio.toml` are each written only after its exact complete proposal is approved; stage uses `create` only for missing, `modify` or `merge` only for existing regular, never `delete`, and audits to the approved digest.
- [ ] With no repository-root `.codex/studio.toml`, invoke `tools.codex_studio.start_initialization` for read-only detection and event-ledger validation before presenting a proposal or allowing any write.
- [ ] Installed execution uses `./assets/studio/tools/codex_studio/start_initialization.py --preflight LEDGER.json --project-root PROJECT_ROOT`; the JSON ledger has `authority_state` and ordered events, and output has `status`, `mode`, and `contract_sha256`. Run `--audit` after writes to check actual filesystem path types and digests.

<!-- start-initialization-contract:sha256=a6b2b182e7d40eb29ebf7ecbc61c45a66daff0902251782bd3da927c59b44145 -->
<!-- start-initialization-summary:start
- First run has exactly 1 Initialization changeset and at most 10 unique path mutations; each mutation is one filesystem path.
- The only first-run project-owned file targets are `.codex/studio.toml`, `production/stage.txt`; a parent directory is created only when observed missing, before a required create or merge child, never for delete or speculation.
- Each action and write has an exact closed schema, one normalized target, material change, and SHA-256 digest where content exists; actions use `create`, `modify`, `merge`, `delete`, `directory-create`, `managed-block-edit` and never `glob`, `recursive`, `tree-copy`, `bulk` or aliases.
- Forbidden roots and every descendant are `.agents/skills`, `.codex/agents`, `.codex/agent-packs`, `Codex Studio Testing Framework`, `docs/engine-reference`; all other paths are outside selected and approved project authority.
- No writes precede approval (0); writes match approved actions exactly in order, and a plan above the cap replans (True).
- The six-field default authority is `active_engine_pack = "none"`; `engine = "unconfigured"`; `engine_version = ""`; `language = ""`; `model_policy = "balanced"`; `review_mode = "phase-gated"`, and missing authority must create and write its exact bytes.
- Initialized repositories have 0 Initialization changesets and retain unique proposal-specific stage and review-mode approval/write groups; stage uses `create`, `modify`, `merge`, bound to its observed preimage, and must audit as a regular digest-matching file; review mode is a full-file `modify` from and to one of `full`, `phase-gated`, `solo`, preserving every other authority value.
- Installed execution uses `tools/codex_studio/start_initialization.py --preflight|--audit LEDGER --project-root PROJECT` and ledger schema version 1. Preflight and audit are link/reparse-safe; link-safe filesystem path types and SHA-256 digests (file mode is not part of this material contract).
start-initialization-summary:end -->
<!-- start-initialization-ledger-schema:sha256=51b3d3e87945534950f85ee25e18c06a25ec236e46db0de22d9bd42fdda07d0f -->
<!-- start-initialization-ledger-schema:start
{"action":{"directory_exact_keys":["expanded_paths","form","kind","material_change","path","required_by","sha256"],"expanded_paths":"[path]","file_exact_keys":["expanded_paths","form","kind","material_change","path","sha256"],"form":"atomic","kind":["create","modify","merge","delete","directory-create","managed-block-edit"],"material_change":"non-empty string","path":"normalized repository-relative approved target","required_by":"string (directory-create only)","sha256":"64 lowercase hex for file actions; null for delete and directory-create"},"authority":{"default_toml_exact_bytes":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","default_toml_sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc","missing_requirement":"exactly one .codex/studio.toml create action and reconciled write with these bytes and digest"},"control_events":{"approval":{"exact_keys":["type"]},"detect":{"exact_keys":["type"]},"review-mode-approval":{"exact_keys":["type"]},"select-next-step":{"exact_keys":["type","next_step"],"next_step":["brainstorm","setup-engine","project-stage-detect"]},"stage-approval":{"exact_keys":["type"]}},"events":{"initialization-changeset":{"authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","exact_keys":["type","authority_toml","actions"]},"review-mode-proposal":{"authority_before_exact_keys":["engine","engine_version","language","review_mode","active_engine_pack","model_policy"],"exact_keys":["type","review_mode","authority_before","actions"],"review_mode":["full","phase-gated","solo"]},"stage-proposal":{"exact_keys":["type","actions"]}},"example_envelope":{"exact_keys":["initial_state","session","write_contents"],"initial_state":{"directories":{".codex":["missing","directory"],"production":["missing","directory"]},"exact_keys":["directories","files"],"files":"exact repository-relative UTF-8 pre-images"},"write_contents":"exact UTF-8 post-image for every non-directory, non-delete approved action"},"examples":{"first_run_brainstorm":{"initial_state":{"directories":{".codex":"missing","production":"missing"},"files":{}},"session":{"authority_state":"missing","events":[{"type":"detect"},{"next_step":"brainstorm","type":"select-next-step"},{"actions":[{"expanded_paths":[".codex"],"form":"atomic","kind":"directory-create","material_change":"create the authority parent","path":".codex","required_by":".codex/studio.toml","sha256":null},{"expanded_paths":[".codex/studio.toml"],"form":"atomic","kind":"create","material_change":"write the complete default authority","path":".codex/studio.toml","sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc"}],"authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","type":"initialization-changeset"},{"type":"approval"},{"kind":"directory-create","material_change":"create the authority parent","path":".codex","sha256":null,"type":"write"},{"kind":"create","material_change":"write the complete default authority","path":".codex/studio.toml","sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc","type":"write"}]},"write_contents":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n"}},"first_run_project_stage_detect":{"initial_state":{"directories":{".codex":"missing","production":"missing"},"files":{}},"session":{"authority_state":"missing","events":[{"type":"detect"},{"next_step":"project-stage-detect","type":"select-next-step"},{"actions":[{"expanded_paths":[".codex"],"form":"atomic","kind":"directory-create","material_change":"create the authority parent","path":".codex","required_by":".codex/studio.toml","sha256":null},{"expanded_paths":[".codex/studio.toml"],"form":"atomic","kind":"create","material_change":"write the complete default authority","path":".codex/studio.toml","sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc"}],"authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","type":"initialization-changeset"},{"type":"approval"},{"kind":"directory-create","material_change":"create the authority parent","path":".codex","sha256":null,"type":"write"},{"kind":"create","material_change":"write the complete default authority","path":".codex/studio.toml","sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc","type":"write"}]},"write_contents":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n"}},"first_run_setup_engine":{"initial_state":{"directories":{".codex":"missing","production":"missing"},"files":{}},"session":{"authority_state":"missing","events":[{"type":"detect"},{"next_step":"setup-engine","type":"select-next-step"},{"actions":[{"expanded_paths":[".codex"],"form":"atomic","kind":"directory-create","material_change":"create the authority parent","path":".codex","required_by":".codex/studio.toml","sha256":null},{"expanded_paths":[".codex/studio.toml"],"form":"atomic","kind":"create","material_change":"write the complete default authority","path":".codex/studio.toml","sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc"},{"expanded_paths":["production"],"form":"atomic","kind":"directory-create","material_change":"create the stage parent","path":"production","required_by":"production/stage.txt","sha256":null},{"expanded_paths":["production/stage.txt"],"form":"atomic","kind":"create","material_change":"write the selected initial stage","path":"production/stage.txt","sha256":"3c6356e0cc11bc22b99269b314ec6de24caf3e2fae6e9afac763023004f8ae7d"}],"authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","type":"initialization-changeset"},{"type":"approval"},{"kind":"directory-create","material_change":"create the authority parent","path":".codex","sha256":null,"type":"write"},{"kind":"create","material_change":"write the complete default authority","path":".codex/studio.toml","sha256":"b36b0604a2a9ef02ffc036ad91e885c4db0beefcd4be0516f17695924b7d79fc","type":"write"},{"kind":"directory-create","material_change":"create the stage parent","path":"production","sha256":null,"type":"write"},{"kind":"create","material_change":"write the selected initial stage","path":"production/stage.txt","sha256":"3c6356e0cc11bc22b99269b314ec6de24caf3e2fae6e9afac763023004f8ae7d","type":"write"}]},"write_contents":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","production/stage.txt":"Concept\n"}},"initialized_review_mode":{"initial_state":{"directories":{".codex":"directory","production":"missing"},"files":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n"}},"session":{"authority_state":"initialized","events":[{"type":"detect"},{"actions":[{"expanded_paths":[".codex/studio.toml"],"form":"atomic","kind":"modify","material_change":"update only review_mode to full in the complete authority","path":".codex/studio.toml","sha256":"7acbd4b6ccda7ae0f07bf5a78f33ecaa2b24ad7cc398a881e3b6c0b7aebf83da"}],"authority_before":{"active_engine_pack":"none","engine":"unconfigured","engine_version":"","language":"","model_policy":"balanced","review_mode":"phase-gated"},"review_mode":"full","type":"review-mode-proposal"},{"type":"review-mode-approval"},{"kind":"modify","material_change":"update only review_mode to full in the complete authority","path":".codex/studio.toml","sha256":"7acbd4b6ccda7ae0f07bf5a78f33ecaa2b24ad7cc398a881e3b6c0b7aebf83da","type":"write"}]},"write_contents":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"full\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n"}},"initialized_stage":{"initial_state":{"directories":{".codex":"directory","production":"missing"},"files":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n"}},"session":{"authority_state":"initialized","events":[{"type":"detect"},{"actions":[{"expanded_paths":["production"],"form":"atomic","kind":"directory-create","material_change":"create the stage parent","path":"production","required_by":"production/stage.txt","sha256":null},{"expanded_paths":["production/stage.txt"],"form":"atomic","kind":"create","material_change":"write the selected initial stage","path":"production/stage.txt","sha256":"3c6356e0cc11bc22b99269b314ec6de24caf3e2fae6e9afac763023004f8ae7d"}],"type":"stage-proposal"},{"type":"stage-approval"},{"kind":"directory-create","material_change":"create the stage parent","path":"production","sha256":null,"type":"write"},{"kind":"create","material_change":"write the selected initial stage","path":"production/stage.txt","sha256":"3c6356e0cc11bc22b99269b314ec6de24caf3e2fae6e9afac763023004f8ae7d","type":"write"}]},"write_contents":{"production/stage.txt":"Concept\n"}},"initialized_stage_and_review_mode":{"initial_state":{"directories":{".codex":"directory","production":"missing"},"files":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n"}},"session":{"authority_state":"initialized","events":[{"type":"detect"},{"actions":[{"expanded_paths":["production"],"form":"atomic","kind":"directory-create","material_change":"create the stage parent","path":"production","required_by":"production/stage.txt","sha256":null},{"expanded_paths":["production/stage.txt"],"form":"atomic","kind":"create","material_change":"write the selected initial stage","path":"production/stage.txt","sha256":"3c6356e0cc11bc22b99269b314ec6de24caf3e2fae6e9afac763023004f8ae7d"}],"type":"stage-proposal"},{"type":"stage-approval"},{"kind":"directory-create","material_change":"create the stage parent","path":"production","sha256":null,"type":"write"},{"kind":"create","material_change":"write the selected initial stage","path":"production/stage.txt","sha256":"3c6356e0cc11bc22b99269b314ec6de24caf3e2fae6e9afac763023004f8ae7d","type":"write"},{"actions":[{"expanded_paths":[".codex/studio.toml"],"form":"atomic","kind":"modify","material_change":"update only review_mode to full in the complete authority","path":".codex/studio.toml","sha256":"7acbd4b6ccda7ae0f07bf5a78f33ecaa2b24ad7cc398a881e3b6c0b7aebf83da"}],"authority_before":{"active_engine_pack":"none","engine":"unconfigured","engine_version":"","language":"","model_policy":"balanced","review_mode":"phase-gated"},"review_mode":"full","type":"review-mode-proposal"},{"type":"review-mode-approval"},{"kind":"modify","material_change":"update only review_mode to full in the complete authority","path":".codex/studio.toml","sha256":"7acbd4b6ccda7ae0f07bf5a78f33ecaa2b24ad7cc398a881e3b6c0b7aebf83da","type":"write"}]},"write_contents":{".codex/studio.toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"full\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","production/stage.txt":"Concept\n"}}},"initialized_groups":{"constraints":"each proposal type and mutation path appears at most once; only a stage proposal may include its observed-missing production parent immediately before the create or merge target","review-mode-proposal":{"action_kind":"modify","approval":"review-mode-approval","optional_parent":null,"post_image":"canonical complete six-field authority_before with only review_mode changed from one closed current value to a different closed target value; action/write SHA-256 matches exact post-image","target":".codex/studio.toml"},"stage-proposal":{"action_kind":["create","modify","merge"],"approval":"stage-approval","optional_parent":"production","post_image":"successful audit requires regular production/stage.txt whose SHA-256 matches the action and write","preimage":"create requires missing; modify or merge requires existing regular","target":"production/stage.txt"}},"ledger_schema_version":1,"ordering":{"first_run":{"exact_sequence":["detect","select-next-step","initialization-changeset","approval","one write per action in action order"],"initialization_changesets":1},"initialized":{"exact_prefix":["detect"],"initialization_changesets":0,"repeating_group":["unique proposal","matching separate approval","one write per action in action order"]}},"selection_stage_rule":"a production/stage.txt action exists if and only if select-next-step.next_step is setup-engine; it uses create for missing or modify/merge for existing regular and always leaves a digest-bound regular file; brainstorm and project-stage-detect omit it","top_level":{"authority_state":["missing","initialized"],"events":"array","exact_keys":["authority_state","events"]},"write":{"exact_keys":["kind","material_change","path","sha256","type"],"fields":"repeat approved action path/kind/material_change/sha256 in order","type":"write"},"write_reconciliation":{"cardinality":"exactly one write per approved action","exact_fields":["path","kind","material_change","sha256"],"order":"same order as actions","unapproved_writes":0}}
start-initialization-ledger-schema:end -->

## Test Cases

### Case 1: Happy Path — Fresh repository routes to Path A

**Fixture:**
- `.codex/studio.toml` contains `engine = "unconfigured"` and `review_mode = "phase-gated"`.
- No `design/gdd/game-concept.md`, qualifying files in `src/`, subdirectories in `prototypes/`, Markdown files in `design/gdd/`, or files in `production/sprints/` and `production/milestones/`.

**Input:** `$start`; choose `New or exploratory`, then `No idea yet (Path A)`.

**Expected behavior:**
1. Read all project-state artifacts before prompting.
2. Ask "Which broad starting point best describes this project?" with `New or exploratory` and `Defined or existing`.
3. Wait for the first answer before asking the path follow-up.
4. Ask `No idea yet (Path A)` versus `Vague idea (Path B)`.
5. Recommend `$brainstorm open` and derive `Concept` for `production/stage.txt`.
6. Show the exact stage-file proposal and wait for approval before writing it.
7. Read `review_mode` from `.codex/studio.toml`; offer `Full`, `Phase-gated (recommended)`, and `Solo`.
8. Show the exact one-key configuration diff and wait for separate approval.
9. Ask whether to start `$brainstorm`; do not run it automatically.

**Assertions:**
- [ ] The two decisions occur in order and in separate turns.
- [ ] The fresh-state classification agrees with the observed artifact inventory.
- [ ] No file is written during discovery or routing, and each later write has a separate exact approval.
- [ ] Verdict is COMPLETE after the user is oriented and handed off.

### Case 2: Plugin-native First Run — Missing configuration proposes bounded authority

**Fixture:**
- Repository-root `.codex/studio.toml` is missing.
- The repository may contain any observed game artifacts, but no global or plugin
  resource has been initialized.

**Input:** `$start`

**Expected behavior:**
1. Continue read-only project detection and summarize the observed evidence.
2. Let the user select the normal onboarding path; do not infer a configured
   engine from `.codex/docs/technical-preferences.md`.
3. After the selected next step, show one `Initialization changeset` containing
   only persistent authority required by that step.
4. Invoke the production initialization contract validator and show the generated
   contract summary with the proposed ledger.
5. Treat that one proposal as replacing the separate persistent proposals in
   Phases 4-6; include `production/stage.txt` only when the selected next step
   requires it.

**Assertions:**
- [ ] Missing authority is not treated as a configured engine or an onboarding error.
- [ ] No initialization write occurs before the complete changeset is explicitly approved.
- [ ] The proposal initializes only the selected repository authority, never global or plugin resources.

### Case 3: Project-State Boundary — Defined concept routes to Path C

**Fixture:**
- `.codex/studio.toml` contains `engine = "unconfigured"`.
- `design/gdd/game-concept.md` exists; no source or production artifacts exist.

**Input:** `$start`; choose `Defined or existing`, then `Clear concept (Path C)`.

**Expected behavior:**
1. Detect the concept before asking questions.
2. Offer `Clear concept (Path C)` and `Existing work (Path D)` only after the first answer.
3. Ask for the concept in one sentence.
4. Offer `Formalize it first` versus `Jump straight in` and wait.
5. Route to `$brainstorm [concept]` or `$setup-engine` according to that decision.

**Assertions:**
- [ ] Existing concept evidence is reflected in the recommendation.
- [ ] Engine choice is deferred to `$setup-engine`.
- [ ] No workflow is auto-run.

### Case 4: Returning User — Configured engine and concept skip onboarding

**Fixture:**
- `.codex/studio.toml` contains a configured engine and readable review mode.
- `design/gdd/game-concept.md` exists.

**Input:** `$start`

**Expected behavior:**
1. Detect the returning state: `engine configured, concept exists`.
2. Skip onboarding entirely; do not ask the Path A–D questions.
3. Report the configured engine, concept path, and current review mode.
4. Offer `$sprint-plan` or a free-form next request without auto-running either.

**Assertions:**
- [ ] Returning-user behavior exactly matches the runtime edge-case branch.
- [ ] No onboarding decision or persistent write is proposed.
- [ ] No existing artifact is overwritten and no workflow is auto-run.

### Case 5: Final Gate — Stage and review-depth writes are separately approved

**Fixture:**
- Any Path A–D state.
- A starting path has been confirmed and `.codex/studio.toml` is readable.

**Input:** Continue `$start` after routing.

**Expected behavior:**
1. Derive the exact `production/stage.txt` value, bind `create` to missing or `modify`/`merge` to existing regular, present that one-file changeset, and wait for approval; never propose stage deletion, and audit the successful write as a regular file with the approved digest.
2. Read the current `review_mode`, then offer `Full`, `Phase-gated (recommended)`, and `Solo`.
3. Map the selection to `review_mode = "full"`, `review_mode = "phase-gated"`, or `review_mode = "solo"`.
4. Show the exact complete canonical `.codex/studio.toml` post-image and diff changing only `review_mode`, preserving every other six-field value; propose one full-file `modify` with the matching digest and wait for separate approval.
5. Treat an already-matching value as a no-op; if either proposal is declined, leave that artifact unchanged.
6. Ask whether to start the recommended skill; never auto-run it.

**Assertions:**
- [ ] Approval for the stage artifact does not authorize the later configuration edit.
- [ ] The configuration approval records the closed target value and current exact six-field authority, changes only `review_mode`, and cannot delete or truncate the authority.
- [ ] New paths or scope expansion require fresh approval.
- [ ] The final handoff names the chosen native `$skill` invocation.
- [ ] No director agents or director gate IDs are involved.

## Protocol Compliance

- [ ] Project-state discovery precedes user questions.
- [ ] A missing canonical configuration continues read-only detection; unreadable or invalid canonical configuration returns `Verdict: **BLOCKED**` before onboarding.
- [ ] A returning user with `engine configured, concept exists` skips onboarding entirely.
- [ ] Ordered decisions map exactly to Paths A–D.
- [ ] `.codex/studio.toml` is the engine and persistent review-depth authority; no separate review-depth file is used.
- [ ] Discovery and routing are read-only.
- [ ] The parent obtains exact complete-changeset approval before each permitted write.
- [ ] Completion hands control back to the user.

## Coverage Notes

- This spec validates routing and approval behavior, not the downstream engine
  selection performed by `$setup-engine`.
- Visual rendering of `request_user_input` remains a manual Codex UI check.
