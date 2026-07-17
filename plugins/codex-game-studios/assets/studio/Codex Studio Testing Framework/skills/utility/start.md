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
- [ ] `production/stage.txt` and `.codex/studio.toml` are each written only after its exact complete proposal is approved.
- [ ] With no repository-root `.codex/studio.toml`, continue read-only project detection and present one `Initialization changeset` only after the selected next step.
- [ ] The initialization changeset has at most 10 path mutations and produces zero writes before explicit approval.
- [ ] The complete default authority is `engine = "unconfigured"`, `engine_version = ""`, `language = ""`, `review_mode = "phase-gated"`, `active_engine_pack = "none"`, and `model_policy = "balanced"`.
- [ ] Every created, modified, merged, or deleted filesystem path counts as one action, including directory creation and each file or managed-block edit. Each action lists one exact target and its material change; glob, recursive, tree-copy, and bulk actions are rejected, and a changeset that would exceed ten paths stops for replanning.
- [ ] Initialization must not create `.agents/skills/`, `.codex/agents/`, `.codex/agent-packs/`, `Codex Studio Testing Framework/`, unselected engine references, or speculative empty project directories; it must not initialize global or plugin resources.

<!-- start-initialization-contract:start
{"default_authority_toml":"engine = \"unconfigured\"\nengine_version = \"\"\nlanguage = \"\"\nreview_mode = \"phase-gated\"\nactive_engine_pack = \"none\"\nmodel_policy = \"balanced\"\n","first_run":{"action_unit":"filesystem path","counted_path_mutations":["create","modify","merge","delete","directory-create","managed-block-edit"],"forbidden_action_forms":["glob","recursive","tree-copy","bulk"],"forbidden_target_prefixes":[".agents/skills/",".codex/agents/",".codex/agent-packs/","Codex Studio Testing Framework/","docs/engine-reference/"],"initialization_changesets":1,"max_path_mutations":10,"pre_approval_writes":0,"replan_above_max_path_mutations":true}}
start-initialization-contract:end -->

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
4. State the complete default authority: `engine = "unconfigured"`,
   `engine_version = ""`, `language = ""`, `review_mode = "phase-gated"`,
   `active_engine_pack = "none"`, and `model_policy = "balanced"`.
5. Count every created, modified, merged, or deleted filesystem path as one
   action, including directory creation and each file or managed-block edit.
   List each exact target and material change; reject glob, recursive, tree-copy,
   and bulk actions, and stop to replan if more than ten paths would mutate.
6. Limit the changeset to at most 10 path mutations and produce zero writes
   before explicit approval.
7. Treat that one proposal as replacing the separate persistent proposals in
   Phases 4-6; include `production/stage.txt` only when the selected next step
   requires it.
8. Do not initialize global or plugin resources, `.agents/skills/`,
   `.codex/agents/`, `.codex/agent-packs/`, `Codex Studio Testing Framework/`,
   unselected engine references, or speculative empty project directories.

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
1. Derive the exact `production/stage.txt` value, present that one-file changeset, and wait for approval.
2. Read the current `review_mode`, then offer `Full`, `Phase-gated (recommended)`, and `Solo`.
3. Map the selection to `review_mode = "full"`, `review_mode = "phase-gated"`, or `review_mode = "solo"`.
4. Show the exact `.codex/studio.toml` diff changing only `review_mode`, preserving every other key and ordering, and wait for separate approval.
5. Treat an already-matching value as a no-op; if either proposal is declined, leave that artifact unchanged.
6. Ask whether to start the recommended skill; never auto-run it.

**Assertions:**
- [ ] Approval for the stage artifact does not authorize the later configuration edit.
- [ ] The configuration approval changes only `review_mode`.
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
