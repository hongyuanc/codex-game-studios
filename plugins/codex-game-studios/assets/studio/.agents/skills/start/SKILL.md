---
name: start
description: Use when a first-time user needs project-state detection and guidance to the correct Codex Game Studios workflow.
---

## Codex-native operating rules

Ask one decision per turn and wait for the answer before asking another. A
`request_user_input` call contains 1-3 questions only when genuinely independent,
and each question contains 2-3 mutually exclusive options. Discovery is read-only
until a documented artifact changeset and target path are shown and approved.
Fresh projects route from `$start`; engine-dependent work with no configured
engine routes to `$setup-engine`.

# Guided Onboarding


This skill may update two persistent artifacts after showing their exact changes
and receiving explicit approval: `production/stage.txt` and
`.codex/studio.toml`. `.codex/studio.toml` is the sole persistent review-mode authority.
Never create a separate review-mode file.

This skill is the entry point for new users. It does NOT assume you have a game idea, an engine preference, or any prior experience. It asks first, then routes you to the right workflow.

---

## Plugin-native first run

Invoke this workflow as `$codex-game-studios:start` when the installed plugin is
the available entry point. A missing repository-root `.codex/studio.toml` is not
an error: continue read-only project detection, report that repository authority
is absent, and let the observed artifacts determine the onboarding path. Do not
infer a configured engine from another file.

Before presenting a persistent proposal, invoke the production
`tools.codex_studio.start_initialization` planning/validation interface with the
read-only project state and proposed event ledger. Do not present or perform a
write if it rejects the ledger. Its emitted normative contract controls every
first-run initialization rule below; the fingerprint and generated summary are
checked mechanically in both runtime and framework documentation.

For an installed plugin, execute the plugin-relative file
`./assets/studio/tools/codex_studio/start_initialization.py` from the plugin
root: `python3 -B ./assets/studio/tools/codex_studio/start_initialization.py
--preflight LEDGER.json --project-root PROJECT_ROOT`. `LEDGER.json` is one JSON
object with `authority_state` (`missing` or `initialized`) and ordered `events`.
An initialization event contains `authority_toml` and exact atomic `actions`; a
write repeats each approved action's `path`, `kind`, `material_change`, and
`sha256` in order. The command emits one JSON object with `status`, `mode`, and
`contract_sha256`; exit status 2 is a fail-closed validation error. After writes,
run the same path with `--audit` so the bundled validator reads actual path types
and file digests rather than trusting prospective write records.

<!-- start-initialization-contract:sha256=6b4e1c5018bc00ad7c0c5b03b815d1dbb14474826b81e8b3f0176f02c89c6fad -->
<!-- start-initialization-summary:start
- First run has exactly 1 Initialization changeset and at most 10 unique path mutations; each mutation is one filesystem path.
- The only first-run project-owned file targets are `.codex/studio.toml`, `production/stage.txt`; a parent directory is created only when observed missing, before a required create or merge child, never for delete or speculation.
- Each action and write has an exact closed schema, one normalized target, material change, and SHA-256 digest where content exists; actions use `create`, `modify`, `merge`, `delete`, `directory-create`, `managed-block-edit` and never `glob`, `recursive`, `tree-copy`, `bulk` or aliases.
- Forbidden roots and every descendant are `.agents/skills`, `.codex/agents`, `.codex/agent-packs`, `Codex Studio Testing Framework`, `docs/engine-reference`; all other paths are outside selected and approved project authority.
- No writes precede approval (0); writes match approved actions exactly in order, and a plan above the cap replans (True).
- The six-field default authority is `active_engine_pack = "none"`; `engine = "unconfigured"`; `engine_version = ""`; `language = ""`; `model_policy = "balanced"`; `review_mode = "phase-gated"`, and missing authority must create and write its exact bytes.
- Initialized repositories have 0 Initialization changesets and retain unique separate stage and review-mode proposal/approval/write groups.
- Installed execution uses `tools/codex_studio/start_initialization.py --preflight|--audit LEDGER --project-root PROJECT`. Preflight reads the observed project state; audit reads filesystem path types and SHA-256 digests after the approved writes.
start-initialization-summary:end -->

On first run, this one Initialization changeset replaces the separate persistent
proposals in Phases 4-6. It may include `production/stage.txt` only when that
selected next step requires it; after approval, skip those separate persistent
proposals.

For a present, readable `.codex/studio.toml`, preserve the initialized-repository
protocol below, including its separate stage and review-mode approvals. An
unreadable or invalid TOML authority remains a repair case: show its exact repair
changeset and stop without writing until the user approves it.

---

## Phase 1: Detect Project State

Before asking anything, silently gather context so you can tailor your guidance.
Do not emit a raw scan log; Phase 2 presents the relevant evidence as a concise
project-state summary before asking the user to confirm the starting point.

Check:
- **Engine configured?** Read `.codex/studio.toml`. If it is missing, continue
  read-only project detection under the plugin-native first-run protocol. If it
  is unreadable or invalid TOML, report that the canonical studio authority is
  unavailable, do not infer values from another file, offer restoration or an
  explicitly approved repair, then stop with `Verdict: **BLOCKED**`. If it contains
  `engine = "unconfigured"`, no engine pack is active. Use
  `.codex/docs/technical-preferences.md` only for the selected engine's detailed
  preferences after activation.
- **Game concept exists?** Check for `design/gdd/game-concept.md`.
- **Source code exists?** repository file search for source files in `src/` (`*.gd`, `*.cs`, `*.cpp`, `*.h`, `*.rs`, `*.py`, `*.js`, `*.ts`).
- **Prototypes exist?** Check for subdirectories in `prototypes/`.
- **Design docs exist?** Count real game-design Markdown artifacts in
  `design/gdd/`; exclude every nested `AGENTS.md` and instruction-only files such as `.gitkeep` from artifact counts.
- **Production artifacts?** Check for files in `production/sprints/` or `production/milestones/`.

Store these findings internally to validate the user's self-assessment and tailor recommendations.

When the engine is unconfigured and there are **No concept, source, prototype, design, or production artifacts**, classify the repository as fresh and route to `$brainstorm` after the onboarding decision below.

---

## Phase 2: Confirm the Detected Starting Point

This is the first thing the user sees. Summarize the classification and show the concrete evidence you found:
configured engine value, concept path or absence,
source-file count, prototype directories, design-document count, and production
artifact paths. Do not ask the user to choose a state contradicted by the
repository.

Use two sequential two-option decisions so every `request_user_input` call fits
the native schema.

First ask: "Which broad starting point best describes this project?"

- `New or exploratory` — no formalized game concept or implementation yet.
- `Defined or existing` — a clear concept or existing project artifacts are present.

Wait. If the user selects **New or exploratory**, ask one follow-up:

- `No idea yet (Path A)` — explore what to make.
- `Vague idea (Path B)` — develop a rough theme, feeling, or genre.

If the user selects **Defined or existing**, ask one follow-up instead:

- `Clear concept (Path C)` — formalize a known genre and core mechanic.
- `Existing work (Path D)` — organize or continue existing docs, prototypes, or code.

Wait for the second selection before routing. Never batch the two decisions.

---

## Phase 3: Confirm the Workflow Path

#### If A: No idea yet

The user needs creative exploration before anything else.

1. Acknowledge that starting from zero is completely fine
2. Briefly explain what `$brainstorm` does (guided ideation using professional frameworks — MDA, player psychology, verb-first design). Mention that it has two modes: `$brainstorm open` for fully open exploration, or `$brainstorm [hint]` if they have even a vague theme (e.g., "space", "cozy", "horror").
3. Recommend running `$brainstorm open` as the next step, but invite them to use a hint if something comes to mind
4. Show the recommended path:
   **Concept phase:**
   - `$brainstorm open` — discover your game concept
   - `$setup-engine` — configure the engine (brainstorm will recommend one)
   - `$prototype` — throwaway concept build: validate the core idea is fun before designing (1–3 days)
   - `$art-bible` — define visual identity (uses the Visual Identity Anchor brainstorm produces)
   - `$map-systems` — decompose the concept into systems
   - `$design-system` — author a GDD for each MVP system
   - `$review-all-gdds` — cross-system consistency check
   - `$gate-check` — validate readiness before architecture work
   **Architecture phase:**
   - `$create-architecture` — produce the master architecture blueprint and Required ADR list
   - `$architecture-decision (×N)` — record key technical decisions, following the Required ADR list
   - `$create-control-manifest` — compile decisions into an actionable rules sheet
   - `$architecture-review` — validate architecture coverage
   **Pre-Production phase:**
   - `$ux-design` — author UX specs for key screens (main menu, HUD, core interactions)
   - `$vertical-slice` — production-quality end-to-end build to validate the full game loop
   - `$playtest-report (×1+)` — document each vertical slice playtest session
   - `$create-epics` — map systems to epics
   - `$create-stories` — break epics into implementable stories
   - `$sprint-plan` — plan the first sprint
   **Production phase:** → pick up stories with `$dev-story`

#### If B: Vague idea

1. Ask them to share their vague idea — even a few words is enough
2. Validate the idea as a starting point (don't judge or redirect)
3. Recommend running `$brainstorm [their hint]` to develop it
4. Show the recommended path:
   **Concept phase:**
   - `$brainstorm [hint]` — develop the idea into a full concept
   - `$setup-engine` — configure the engine
   - `$prototype` — throwaway concept build: validate the core idea is fun before designing (1–3 days)
   - `$art-bible` — define visual identity (uses the Visual Identity Anchor brainstorm produces)
   - `$map-systems` — decompose the concept into systems
   - `$design-system` — author a GDD for each MVP system
   - `$review-all-gdds` — cross-system consistency check
   - `$gate-check` — validate readiness before architecture work
   **Architecture phase:**
   - `$create-architecture` — produce the master architecture blueprint and Required ADR list
   - `$architecture-decision (×N)` — record key technical decisions, following the Required ADR list
   - `$create-control-manifest` — compile decisions into an actionable rules sheet
   - `$architecture-review` — validate architecture coverage
   **Pre-Production phase:**
   - `$ux-design` — author UX specs for key screens (main menu, HUD, core interactions)
   - `$vertical-slice` — production-quality end-to-end build to validate the full game loop
   - `$playtest-report (×1+)` — document each vertical slice playtest session
   - `$create-epics` — map systems to epics
   - `$create-stories` — break epics into implementable stories
   - `$sprint-plan` — plan the first sprint
   **Production phase:** → pick up stories with `$dev-story`

#### If C: Clear concept

1. Ask them to describe their concept in one sentence — genre and core mechanic. Use plain text, not one-question prompt (it's an open response).
2. Acknowledge the concept, then ask one concise question and wait for the answer to offer two paths:
   - **Prompt**: "How would you like to proceed?"
   - **Options**:
     - `Formalize it first` — Run `$brainstorm [concept]` to structure it into a proper game concept document
     - `Jump straight in` — Go to `$setup-engine` now and write the GDD manually afterward
3. Show the recommended path:
   **Concept phase:**
   - `$brainstorm` or `$setup-engine` — (their pick from step 2)
   - `$prototype` — throwaway concept build: validate the core idea is fun before designing (1–3 days)
   - `$art-bible` — define visual identity (after brainstorm if run, or after concept doc exists)
   - `$design-review` — validate the concept doc
   - `$map-systems` — decompose the concept into individual systems
   - `$design-system` — author a GDD for each MVP system
   - `$review-all-gdds` — cross-system consistency check
   - `$gate-check` — validate readiness before architecture work
   **Architecture phase:**
   - `$create-architecture` — produce the master architecture blueprint and Required ADR list
   - `$architecture-decision (×N)` — record key technical decisions, following the Required ADR list
   - `$create-control-manifest` — compile decisions into an actionable rules sheet
   - `$architecture-review` — validate architecture coverage
   **Pre-Production phase:**
   - `$ux-design` — author UX specs for key screens (main menu, HUD, core interactions)
   - `$vertical-slice` — production-quality end-to-end build to validate the full game loop
   - `$playtest-report (×1+)` — document each vertical slice playtest session
   - `$create-epics` — map systems to epics
   - `$create-stories` — break epics into implementable stories
   - `$sprint-plan` — plan the first sprint
   **Production phase:** → pick up stories with `$dev-story`

#### If D: Existing work

1. Share what you found in Phase 1:
   - "I can see you have [X source files / Y design docs / Z prototypes]..."
   - "Your engine is [configured as X / not yet configured]..."

2. **Sub-case D1 — Early stage** (engine not configured or only a game concept exists):
   - Recommend `$setup-engine` first if engine not configured
   - Then `$project-stage-detect` for a gap inventory

   **Sub-case D2 — GDDs, ADRs, or stories already exist:**
   - Explain: "Having files isn't the same as the template's skills being able to use them. GDDs might be missing required sections. `$adopt` checks this specifically."
   - Recommend:
     1. `$project-stage-detect` — understand what phase and what's missing entirely
     2. `$adopt` — audit whether existing artifacts are in the right internal format

3. Show the recommended path for D2:
   - `$project-stage-detect` — phase detection + existence gaps
   - `$adopt` — format compliance audit + migration plan
   - `$setup-engine` — if engine not configured
   - `$design-system retrofit [path]` — fill missing GDD sections
   - `$architecture-decision retrofit [path]` — add missing ADR sections
   - `$architecture-review` — bootstrap the TR requirement registry
   - `$gate-check` — validate readiness for next phase

---

## Phase 4: Propose the Initial Stage Artifact

After confirming the starting path (and before asking about review mode), derive the initial stage value for `production/stage.txt`:

Stage mapping:
- **Path A, B, or C (starting from scratch)**: write `Concept`
- **Path D, existing project, engine not configured or only a game concept exists**: write `Concept`
- **Path D, existing project with GDDs but no architecture documents**: write `Systems Design`
- **Path D, existing project with full architecture (ADRs, architecture doc)**: write `Technical Setup`

Show the derived stage value and path, then ask one concise approval question. If approved, create the `production/` directory if needed and write the value. If declined, leave the file unchanged and continue without claiming the stage was saved.

Say: "I've set `production/stage.txt` to `[stage]` — this anchors project-stage
detection and `$help` routing."

---

## Phase 5: Select Review Depth

Read the current `review_mode` from `.codex/studio.toml`, then show it with the
three available choices. Ask one concise question and wait for the answer:

- **Prompt**: "Review mode is currently `[current]`. Which review depth should the studio use across sessions?"
- **Options**:
  - `Full` — Director specialists review at each key workflow step. Best for teams, learning the workflow, or when you want thorough feedback on every decision.
  - `Phase-gated (recommended)` — Use lean optional-review depth while phase-transition and other mandatory director gates still run. Balanced for solo developers and small teams.
  - `Solo` — Skip optional director consultation for maximum speed; gates explicitly marked required still run.

Map the selection to the proposed persistent value:
- `Full` → `review_mode = "full"`
- `Phase-gated (recommended)` → `review_mode = "phase-gated"`
- `Solo` → `review_mode = "solo"`

Selecting a mode chooses a proposal; it does not write the configuration.

---

## Phase 6: Approve the Studio Configuration Changeset

Show the exact `.codex/studio.toml` diff that changes only `review_mode` and ask
for explicit approval of that one-file changeset. Preserve the engine, version,
language, active engine pack, model policy, comments, and key order byte-for-byte.
If the selected value already matches, report a no-op and do not rewrite the
file. If approval is declined, leave `.codex/studio.toml` unchanged and continue
without claiming the selection was saved.

Never create a separate review-mode file, even as a compatibility fallback.

---

## Phase 7: Confirm Before Proceeding

After presenting the recommended path, ask one concise question and wait for the answer to ask the user which step they'd like to take first. Never auto-run the next skill.

- **Prompt**: "Would you like to start with [recommended first step]?"
- **Options**:
  - `Yes, let's start with [recommended first step]`
  - `I'd like to do something else first`

---

## Phase 8: Hand Off

When the user confirms their next step, respond with a single short line: "Type `[skill command]` to begin." Nothing else. Do not re-explain the skill or add encouragement. The `$start` skill's job is done.

Verdict: **COMPLETE** — user oriented and handed off to next step.

---

## Edge Cases

- **User picks D but project is empty**: Gently redirect — "It looks like the project is a fresh template with no artifacts yet. Would Path A or B be a better fit?"
- **User picks A but project has code**: Mention what you found — "I noticed there's already code in `src/`. Did you mean to pick D (existing work)?"
- **User is returning (engine configured, concept exists)**: Skip onboarding entirely — "It looks like you're already set up! Your engine is [X] and you have a game concept at `design/gdd/game-concept.md`. Review mode: `[configured review mode]`. Want to pick up where you left off? Try `$sprint-plan` or just tell me what you'd like to work on."
- **User doesn't fit any option**: Let them describe their situation in their own words and adapt.

---

## Collaborative Protocol

1. **Ask first** — never assume the user's state or intent
2. **Present options** — give clear paths, not mandates
3. **User decides** — they pick the direction
4. **No auto-execution** — recommend the next skill, don't run it without asking
5. **Adapt** — if the user's situation doesn't fit a template, listen and adjust
