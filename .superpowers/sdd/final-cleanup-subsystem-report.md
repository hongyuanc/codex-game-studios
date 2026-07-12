# Final Cleanup Subsystem Report

## Scope

This report records the Codex-only public surface, testing-framework migration,
repository validator, coverage proof, and the exact authorized deletion map.
Historical migration specs and plans remain intact and are excluded from runtime
dependency checks.

## TDD checkpoints

- Public documentation contracts failed first on legacy product names, paths, and
  653 slash-style skill invocations; they now pass with dollar-prefixed skills.
- Testing-framework contracts failed first because the native directory did not
  exist. Exact legacy agent/skill/template parity then passed. Catalog comparison
  exposed the missing `vertical-slice` behavioral spec, which was added to close
  the exact 49-agent/73-skill inventory.
- Repository validation contracts failed first because composition, count,
  reference, phase, and coverage functions did not exist. The pre-cleanup gate
  now composes agent, skill, hook, inventory, reference, and coverage validation.
- Minor hardening added exact 34/15 and 3×5 agent assertions,
  `devops-engineer` Terra/high routing, forbidden `agent:` and `maxTurns:`
  skill metadata, an exact 29-skill design inventory assertion, native
  `$skill-test` framework behavior, and corrected `$team-ui` quick-reference
  wording.
- Final-review tests failed first on public/runtime prose that still described
  the legacy host, mechanically renamed framework contracts, mutable coverage
  evidence, replacement-name inventory bypasses, permissive file reads,
  symlinked destinations, and alternate-root hook validation. The remediated
  gate rejects each case and passes without skips.

## Pre-cleanup evidence

- `python3 -m unittest discover -s tests/studio -v`: **200 tests, OK**
- `python3 -m tools.codex_studio.validate --root . --phase pre-cleanup`:
  **Codex Studio validation: PASS**
- Coverage manifest: **203 unique legacy runtime sources**, each with
  one existing destination or a justified removal.
- Framework parity: all legacy files under `agents/`, `skills/`, and
  `templates/` preserved; one deliberate native extension adds the previously
  missing `vertical-slice` spec.

## Exact authorized deletion map

The pre-cleanup gate passed before this map was applied.

### Legacy runtime artifacts (203)

| Source | Destination | Action |
| --- | --- | --- |
| `.claude/agent-memory/lead-programmer/MEMORY.md` | `remove-without-replacement` | remove |
| `.claude/agents/accessibility-specialist.md` | `.codex/agents/accessibility-specialist.toml` | migrate |
| `.claude/agents/ai-programmer.md` | `.codex/agents/ai-programmer.toml` | migrate |
| `.claude/agents/analytics-engineer.md` | `.codex/agents/analytics-engineer.toml` | migrate |
| `.claude/agents/art-director.md` | `.codex/agents/art-director.toml` | migrate |
| `.claude/agents/audio-director.md` | `.codex/agents/audio-director.toml` | migrate |
| `.claude/agents/community-manager.md` | `.codex/agents/community-manager.toml` | migrate |
| `.claude/agents/creative-director.md` | `.codex/agents/creative-director.toml` | migrate |
| `.claude/agents/devops-engineer.md` | `.codex/agents/devops-engineer.toml` | migrate |
| `.claude/agents/economy-designer.md` | `.codex/agents/economy-designer.toml` | migrate |
| `.claude/agents/engine-programmer.md` | `.codex/agents/engine-programmer.toml` | migrate |
| `.claude/agents/game-designer.md` | `.codex/agents/game-designer.toml` | migrate |
| `.claude/agents/gameplay-programmer.md` | `.codex/agents/gameplay-programmer.toml` | migrate |
| `.claude/agents/godot-csharp-specialist.md` | `.codex/agent-packs/godot/godot-csharp-specialist.toml` | migrate |
| `.claude/agents/godot-gdextension-specialist.md` | `.codex/agent-packs/godot/godot-gdextension-specialist.toml` | migrate |
| `.claude/agents/godot-gdscript-specialist.md` | `.codex/agent-packs/godot/godot-gdscript-specialist.toml` | migrate |
| `.claude/agents/godot-shader-specialist.md` | `.codex/agent-packs/godot/godot-shader-specialist.toml` | migrate |
| `.claude/agents/godot-specialist.md` | `.codex/agent-packs/godot/godot-specialist.toml` | migrate |
| `.claude/agents/lead-programmer.md` | `.codex/agents/lead-programmer.toml` | migrate |
| `.claude/agents/level-designer.md` | `.codex/agents/level-designer.toml` | migrate |
| `.claude/agents/live-ops-designer.md` | `.codex/agents/live-ops-designer.toml` | migrate |
| `.claude/agents/localization-lead.md` | `.codex/agents/localization-lead.toml` | migrate |
| `.claude/agents/narrative-director.md` | `.codex/agents/narrative-director.toml` | migrate |
| `.claude/agents/network-programmer.md` | `.codex/agents/network-programmer.toml` | migrate |
| `.claude/agents/performance-analyst.md` | `.codex/agents/performance-analyst.toml` | migrate |
| `.claude/agents/producer.md` | `.codex/agents/producer.toml` | migrate |
| `.claude/agents/prototyper.md` | `.codex/agents/prototyper.toml` | migrate |
| `.claude/agents/qa-lead.md` | `.codex/agents/qa-lead.toml` | migrate |
| `.claude/agents/qa-tester.md` | `.codex/agents/qa-tester.toml` | migrate |
| `.claude/agents/release-manager.md` | `.codex/agents/release-manager.toml` | migrate |
| `.claude/agents/security-engineer.md` | `.codex/agents/security-engineer.toml` | migrate |
| `.claude/agents/sound-designer.md` | `.codex/agents/sound-designer.toml` | migrate |
| `.claude/agents/systems-designer.md` | `.codex/agents/systems-designer.toml` | migrate |
| `.claude/agents/technical-artist.md` | `.codex/agents/technical-artist.toml` | migrate |
| `.claude/agents/technical-director.md` | `.codex/agents/technical-director.toml` | migrate |
| `.claude/agents/tools-programmer.md` | `.codex/agents/tools-programmer.toml` | migrate |
| `.claude/agents/ue-blueprint-specialist.md` | `.codex/agent-packs/unreal/ue-blueprint-specialist.toml` | migrate |
| `.claude/agents/ue-gas-specialist.md` | `.codex/agent-packs/unreal/ue-gas-specialist.toml` | migrate |
| `.claude/agents/ue-replication-specialist.md` | `.codex/agent-packs/unreal/ue-replication-specialist.toml` | migrate |
| `.claude/agents/ue-umg-specialist.md` | `.codex/agent-packs/unreal/ue-umg-specialist.toml` | migrate |
| `.claude/agents/ui-programmer.md` | `.codex/agents/ui-programmer.toml` | migrate |
| `.claude/agents/unity-addressables-specialist.md` | `.codex/agent-packs/unity/unity-addressables-specialist.toml` | migrate |
| `.claude/agents/unity-dots-specialist.md` | `.codex/agent-packs/unity/unity-dots-specialist.toml` | migrate |
| `.claude/agents/unity-shader-specialist.md` | `.codex/agent-packs/unity/unity-shader-specialist.toml` | migrate |
| `.claude/agents/unity-specialist.md` | `.codex/agent-packs/unity/unity-specialist.toml` | migrate |
| `.claude/agents/unity-ui-specialist.md` | `.codex/agent-packs/unity/unity-ui-specialist.toml` | migrate |
| `.claude/agents/unreal-specialist.md` | `.codex/agent-packs/unreal/unreal-specialist.toml` | migrate |
| `.claude/agents/ux-designer.md` | `.codex/agents/ux-designer.toml` | migrate |
| `.claude/agents/world-builder.md` | `.codex/agents/world-builder.toml` | migrate |
| `.claude/agents/writer.md` | `.codex/agents/writer.toml` | migrate |
| `.claude/docs/CLAUDE-local-template.md` | `remove-without-replacement` | remove |
| `.claude/docs/agent-coordination-map.md` | `.codex/docs/agent-coordination-map.md` | migrate |
| `.claude/docs/agent-roster.md` | `.codex/docs/agent-roster.md` | migrate |
| `.claude/docs/coding-standards.md` | `.codex/docs/coding-standards.md` | migrate |
| `.claude/docs/context-management.md` | `.codex/docs/context-management.md` | migrate |
| `.claude/docs/coordination-rules.md` | `.codex/docs/coordination-rules.md` | migrate |
| `.claude/docs/director-gates.md` | `.codex/docs/director-gates.md` | migrate |
| `.claude/docs/directory-structure.md` | `.codex/docs/directory-structure.md` | migrate |
| `.claude/docs/hooks-reference.md` | `.codex/docs/hooks-reference.md` | migrate |
| `.claude/docs/hooks-reference/hook-input-schemas.md` | `remove-without-replacement` | remove |
| `.claude/docs/hooks-reference/post-merge-asset-validation.md` | `remove-without-replacement` | remove |
| `.claude/docs/hooks-reference/post-sprint-retrospective.md` | `remove-without-replacement` | remove |
| `.claude/docs/hooks-reference/pre-commit-code-quality.md` | `remove-without-replacement` | remove |
| `.claude/docs/hooks-reference/pre-commit-design-check.md` | `remove-without-replacement` | remove |
| `.claude/docs/hooks-reference/pre-push-test-gate.md` | `remove-without-replacement` | remove |
| `.claude/docs/quick-start.md` | `.codex/docs/quick-start.md` | migrate |
| `.claude/docs/review-workflow.md` | `.codex/docs/review-workflow.md` | migrate |
| `.claude/docs/rules-reference.md` | `.codex/docs/rules-reference.md` | migrate |
| `.claude/docs/settings-local-template.md` | `remove-without-replacement` | remove |
| `.claude/docs/setup-requirements.md` | `.codex/docs/setup-requirements.md` | migrate |
| `.claude/docs/skills-reference.md` | `.codex/docs/skills-reference.md` | migrate |
| `.claude/docs/technical-preferences.md` | `.codex/docs/technical-preferences.md` | migrate |
| `.claude/docs/templates/accessibility-requirements.md` | `.codex/docs/templates/accessibility-requirements.md` | migrate |
| `.claude/docs/templates/architecture-decision-record.md` | `.codex/docs/templates/architecture-decision-record.md` | migrate |
| `.claude/docs/templates/architecture-doc-from-code.md` | `.codex/docs/templates/architecture-doc-from-code.md` | migrate |
| `.claude/docs/templates/architecture-traceability.md` | `.codex/docs/templates/architecture-traceability.md` | migrate |
| `.claude/docs/templates/art-bible.md` | `.codex/docs/templates/art-bible.md` | migrate |
| `.claude/docs/templates/changelog-template.md` | `.codex/docs/templates/changelog-template.md` | migrate |
| `.claude/docs/templates/collaborative-protocols/design-agent-protocol.md` | `.codex/docs/templates/collaborative-protocols/design-agent-protocol.md` | migrate |
| `.claude/docs/templates/collaborative-protocols/implementation-agent-protocol.md` | `.codex/docs/templates/collaborative-protocols/implementation-agent-protocol.md` | migrate |
| `.claude/docs/templates/collaborative-protocols/leadership-agent-protocol.md` | `.codex/docs/templates/collaborative-protocols/leadership-agent-protocol.md` | migrate |
| `.claude/docs/templates/concept-doc-from-prototype.md` | `.codex/docs/templates/concept-doc-from-prototype.md` | migrate |
| `.claude/docs/templates/design-doc-from-implementation.md` | `.codex/docs/templates/design-doc-from-implementation.md` | migrate |
| `.claude/docs/templates/difficulty-curve.md` | `.codex/docs/templates/difficulty-curve.md` | migrate |
| `.claude/docs/templates/economy-model.md` | `.codex/docs/templates/economy-model.md` | migrate |
| `.claude/docs/templates/faction-design.md` | `.codex/docs/templates/faction-design.md` | migrate |
| `.claude/docs/templates/game-concept.md` | `.codex/docs/templates/game-concept.md` | migrate |
| `.claude/docs/templates/game-design-document.md` | `.codex/docs/templates/game-design-document.md` | migrate |
| `.claude/docs/templates/game-pillars.md` | `.codex/docs/templates/game-pillars.md` | migrate |
| `.claude/docs/templates/hud-design.md` | `.codex/docs/templates/hud-design.md` | migrate |
| `.claude/docs/templates/incident-response.md` | `.codex/docs/templates/incident-response.md` | migrate |
| `.claude/docs/templates/interaction-pattern-library.md` | `.codex/docs/templates/interaction-pattern-library.md` | migrate |
| `.claude/docs/templates/level-design-document.md` | `.codex/docs/templates/level-design-document.md` | migrate |
| `.claude/docs/templates/milestone-definition.md` | `.codex/docs/templates/milestone-definition.md` | migrate |
| `.claude/docs/templates/narrative-character-sheet.md` | `.codex/docs/templates/narrative-character-sheet.md` | migrate |
| `.claude/docs/templates/pitch-document.md` | `.codex/docs/templates/pitch-document.md` | migrate |
| `.claude/docs/templates/player-journey.md` | `.codex/docs/templates/player-journey.md` | migrate |
| `.claude/docs/templates/post-mortem.md` | `.codex/docs/templates/post-mortem.md` | migrate |
| `.claude/docs/templates/project-stage-report.md` | `.codex/docs/templates/project-stage-report.md` | migrate |
| `.claude/docs/templates/prototype-report.md` | `.codex/docs/templates/prototype-report.md` | migrate |
| `.claude/docs/templates/release-checklist-template.md` | `.codex/docs/templates/release-checklist-template.md` | migrate |
| `.claude/docs/templates/release-notes.md` | `.codex/docs/templates/release-notes.md` | migrate |
| `.claude/docs/templates/risk-register-entry.md` | `.codex/docs/templates/risk-register-entry.md` | migrate |
| `.claude/docs/templates/skill-test-spec.md` | `.codex/docs/templates/skill-test-spec.md` | migrate |
| `.claude/docs/templates/sound-bible.md` | `.codex/docs/templates/sound-bible.md` | migrate |
| `.claude/docs/templates/sprint-plan.md` | `.codex/docs/templates/sprint-plan.md` | migrate |
| `.claude/docs/templates/systems-index.md` | `.codex/docs/templates/systems-index.md` | migrate |
| `.claude/docs/templates/technical-design-document.md` | `.codex/docs/templates/technical-design-document.md` | migrate |
| `.claude/docs/templates/test-evidence.md` | `.codex/docs/templates/test-evidence.md` | migrate |
| `.claude/docs/templates/test-plan.md` | `.codex/docs/templates/test-plan.md` | migrate |
| `.claude/docs/templates/ux-spec.md` | `.codex/docs/templates/ux-spec.md` | migrate |
| `.claude/docs/templates/vertical-slice-report.md` | `.codex/docs/templates/vertical-slice-report.md` | migrate |
| `.claude/docs/workflow-catalog.yaml` | `.codex/docs/workflow-catalog.yaml` | migrate |
| `.claude/rules/ai-code.md` | `src/ai/AGENTS.md` | migrate |
| `.claude/rules/data-files.md` | `assets/data/AGENTS.md` | migrate |
| `.claude/rules/design-docs.md` | `design/gdd/AGENTS.md` | migrate |
| `.claude/rules/engine-code.md` | `src/core/AGENTS.md` | migrate |
| `.claude/rules/gameplay-code.md` | `src/gameplay/AGENTS.md` | migrate |
| `.claude/rules/narrative.md` | `design/narrative/AGENTS.md` | migrate |
| `.claude/rules/network-code.md` | `src/networking/AGENTS.md` | migrate |
| `.claude/rules/prototype-code.md` | `prototypes/AGENTS.md` | migrate |
| `.claude/rules/shader-code.md` | `assets/shaders/AGENTS.md` | migrate |
| `.claude/rules/test-standards.md` | `tests/AGENTS.md` | migrate |
| `.claude/rules/ui-code.md` | `src/ui/AGENTS.md` | migrate |
| `.claude/skills/adopt/SKILL.md` | `.agents/skills/adopt/SKILL.md` | migrate |
| `.claude/skills/architecture-decision/SKILL.md` | `.agents/skills/architecture-decision/SKILL.md` | migrate |
| `.claude/skills/architecture-review/SKILL.md` | `.agents/skills/architecture-review/SKILL.md` | migrate |
| `.claude/skills/art-bible/SKILL.md` | `.agents/skills/art-bible/SKILL.md` | migrate |
| `.claude/skills/asset-audit/SKILL.md` | `.agents/skills/asset-audit/SKILL.md` | migrate |
| `.claude/skills/asset-spec/SKILL.md` | `.agents/skills/asset-spec/SKILL.md` | migrate |
| `.claude/skills/balance-check/SKILL.md` | `.agents/skills/balance-check/SKILL.md` | migrate |
| `.claude/skills/brainstorm/SKILL.md` | `.agents/skills/brainstorm/SKILL.md` | migrate |
| `.claude/skills/bug-report/SKILL.md` | `.agents/skills/bug-report/SKILL.md` | migrate |
| `.claude/skills/bug-triage/SKILL.md` | `.agents/skills/bug-triage/SKILL.md` | migrate |
| `.claude/skills/changelog/SKILL.md` | `.agents/skills/changelog/SKILL.md` | migrate |
| `.claude/skills/code-review/SKILL.md` | `.agents/skills/code-review/SKILL.md` | migrate |
| `.claude/skills/consistency-check/SKILL.md` | `.agents/skills/consistency-check/SKILL.md` | migrate |
| `.claude/skills/content-audit/SKILL.md` | `.agents/skills/content-audit/SKILL.md` | migrate |
| `.claude/skills/create-architecture/SKILL.md` | `.agents/skills/create-architecture/SKILL.md` | migrate |
| `.claude/skills/create-control-manifest/SKILL.md` | `.agents/skills/create-control-manifest/SKILL.md` | migrate |
| `.claude/skills/create-epics/SKILL.md` | `.agents/skills/create-epics/SKILL.md` | migrate |
| `.claude/skills/create-stories/SKILL.md` | `.agents/skills/create-stories/SKILL.md` | migrate |
| `.claude/skills/day-one-patch/SKILL.md` | `.agents/skills/day-one-patch/SKILL.md` | migrate |
| `.claude/skills/design-review/SKILL.md` | `.agents/skills/design-review/SKILL.md` | migrate |
| `.claude/skills/design-system/SKILL.md` | `.agents/skills/design-system/SKILL.md` | migrate |
| `.claude/skills/dev-story/SKILL.md` | `.agents/skills/dev-story/SKILL.md` | migrate |
| `.claude/skills/estimate/SKILL.md` | `.agents/skills/estimate/SKILL.md` | migrate |
| `.claude/skills/gate-check/SKILL.md` | `.agents/skills/gate-check/SKILL.md` | migrate |
| `.claude/skills/help/SKILL.md` | `.agents/skills/help/SKILL.md` | migrate |
| `.claude/skills/hotfix/SKILL.md` | `.agents/skills/hotfix/SKILL.md` | migrate |
| `.claude/skills/launch-checklist/SKILL.md` | `.agents/skills/launch-checklist/SKILL.md` | migrate |
| `.claude/skills/localize/SKILL.md` | `.agents/skills/localize/SKILL.md` | migrate |
| `.claude/skills/map-systems/SKILL.md` | `.agents/skills/map-systems/SKILL.md` | migrate |
| `.claude/skills/milestone-review/SKILL.md` | `.agents/skills/milestone-review/SKILL.md` | migrate |
| `.claude/skills/onboard/SKILL.md` | `.agents/skills/onboard/SKILL.md` | migrate |
| `.claude/skills/patch-notes/SKILL.md` | `.agents/skills/patch-notes/SKILL.md` | migrate |
| `.claude/skills/perf-profile/SKILL.md` | `.agents/skills/perf-profile/SKILL.md` | migrate |
| `.claude/skills/playtest-report/SKILL.md` | `.agents/skills/playtest-report/SKILL.md` | migrate |
| `.claude/skills/project-stage-detect/SKILL.md` | `.agents/skills/project-stage-detect/SKILL.md` | migrate |
| `.claude/skills/propagate-design-change/SKILL.md` | `.agents/skills/propagate-design-change/SKILL.md` | migrate |
| `.claude/skills/prototype/SKILL.md` | `.agents/skills/prototype/SKILL.md` | migrate |
| `.claude/skills/qa-plan/SKILL.md` | `.agents/skills/qa-plan/SKILL.md` | migrate |
| `.claude/skills/quick-design/SKILL.md` | `.agents/skills/quick-design/SKILL.md` | migrate |
| `.claude/skills/regression-suite/SKILL.md` | `.agents/skills/regression-suite/SKILL.md` | migrate |
| `.claude/skills/release-checklist/SKILL.md` | `.agents/skills/release-checklist/SKILL.md` | migrate |
| `.claude/skills/retrospective/SKILL.md` | `.agents/skills/retrospective/SKILL.md` | migrate |
| `.claude/skills/reverse-document/SKILL.md` | `.agents/skills/reverse-document/SKILL.md` | migrate |
| `.claude/skills/review-all-gdds/SKILL.md` | `.agents/skills/review-all-gdds/SKILL.md` | migrate |
| `.claude/skills/scope-check/SKILL.md` | `.agents/skills/scope-check/SKILL.md` | migrate |
| `.claude/skills/security-audit/SKILL.md` | `.agents/skills/security-audit/SKILL.md` | migrate |
| `.claude/skills/setup-engine/SKILL.md` | `.agents/skills/setup-engine/SKILL.md` | migrate |
| `.claude/skills/skill-improve/SKILL.md` | `.agents/skills/skill-improve/SKILL.md` | migrate |
| `.claude/skills/skill-test/SKILL.md` | `.agents/skills/skill-test/SKILL.md` | migrate |
| `.claude/skills/smoke-check/SKILL.md` | `.agents/skills/smoke-check/SKILL.md` | migrate |
| `.claude/skills/soak-test/SKILL.md` | `.agents/skills/soak-test/SKILL.md` | migrate |
| `.claude/skills/sprint-plan/SKILL.md` | `.agents/skills/sprint-plan/SKILL.md` | migrate |
| `.claude/skills/sprint-status/SKILL.md` | `.agents/skills/sprint-status/SKILL.md` | migrate |
| `.claude/skills/start/SKILL.md` | `.agents/skills/start/SKILL.md` | migrate |
| `.claude/skills/story-done/SKILL.md` | `.agents/skills/story-done/SKILL.md` | migrate |
| `.claude/skills/story-readiness/SKILL.md` | `.agents/skills/story-readiness/SKILL.md` | migrate |
| `.claude/skills/team-audio/SKILL.md` | `.agents/skills/team-audio/SKILL.md` | migrate |
| `.claude/skills/team-combat/SKILL.md` | `.agents/skills/team-combat/SKILL.md` | migrate |
| `.claude/skills/team-level/SKILL.md` | `.agents/skills/team-level/SKILL.md` | migrate |
| `.claude/skills/team-live-ops/SKILL.md` | `.agents/skills/team-live-ops/SKILL.md` | migrate |
| `.claude/skills/team-narrative/SKILL.md` | `.agents/skills/team-narrative/SKILL.md` | migrate |
| `.claude/skills/team-polish/SKILL.md` | `.agents/skills/team-polish/SKILL.md` | migrate |
| `.claude/skills/team-qa/SKILL.md` | `.agents/skills/team-qa/SKILL.md` | migrate |
| `.claude/skills/team-release/SKILL.md` | `.agents/skills/team-release/SKILL.md` | migrate |
| `.claude/skills/team-ui/SKILL.md` | `.agents/skills/team-ui/SKILL.md` | migrate |
| `.claude/skills/tech-debt/SKILL.md` | `.agents/skills/tech-debt/SKILL.md` | migrate |
| `.claude/skills/test-evidence-review/SKILL.md` | `.agents/skills/test-evidence-review/SKILL.md` | migrate |
| `.claude/skills/test-flakiness/SKILL.md` | `.agents/skills/test-flakiness/SKILL.md` | migrate |
| `.claude/skills/test-helpers/SKILL.md` | `.agents/skills/test-helpers/SKILL.md` | migrate |
| `.claude/skills/test-setup/SKILL.md` | `.agents/skills/test-setup/SKILL.md` | migrate |
| `.claude/skills/ux-design/SKILL.md` | `.agents/skills/ux-design/SKILL.md` | migrate |
| `.claude/skills/ux-review/SKILL.md` | `.agents/skills/ux-review/SKILL.md` | migrate |
| `.claude/skills/vertical-slice/SKILL.md` | `.agents/skills/vertical-slice/SKILL.md` | migrate |
| `.claude/statusline.sh` | `remove-without-replacement` | remove |
| `CCGS Skill Testing Framework/CLAUDE.md` | `Codex Studio Testing Framework/AGENTS.md` | migrate |
| `CLAUDE.md` | `AGENTS.md` | migrate |
| `design/CLAUDE.md` | `design/gdd/AGENTS.md` | migrate |
| `docs/CLAUDE.md` | `remove-without-replacement` | remove |
| `src/CLAUDE.md` | `src/core/AGENTS.md` | migrate |

### Legacy testing framework (127 files)

The three behavioral-spec trees map path-for-path to the native framework.
Root guidance maps to `AGENTS.md`; the catalog, README, and rubric map to their
same filenames.

| Source | Destination |
| --- | --- |
| `CCGS Skill Testing Framework/CLAUDE.md` | `Codex Studio Testing Framework/AGENTS.md` |
| `CCGS Skill Testing Framework/README.md` | `Codex Studio Testing Framework/README.md` |
| `CCGS Skill Testing Framework/agents/directors/art-director.md` | `Codex Studio Testing Framework/agents/directors/art-director.md` |
| `CCGS Skill Testing Framework/agents/directors/creative-director.md` | `Codex Studio Testing Framework/agents/directors/creative-director.md` |
| `CCGS Skill Testing Framework/agents/directors/producer.md` | `Codex Studio Testing Framework/agents/directors/producer.md` |
| `CCGS Skill Testing Framework/agents/directors/technical-director.md` | `Codex Studio Testing Framework/agents/directors/technical-director.md` |
| `CCGS Skill Testing Framework/agents/engine/godot/godot-csharp-specialist.md` | `Codex Studio Testing Framework/agents/engine/godot/godot-csharp-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/godot/godot-gdextension-specialist.md` | `Codex Studio Testing Framework/agents/engine/godot/godot-gdextension-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/godot/godot-gdscript-specialist.md` | `Codex Studio Testing Framework/agents/engine/godot/godot-gdscript-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/godot/godot-shader-specialist.md` | `Codex Studio Testing Framework/agents/engine/godot/godot-shader-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/godot/godot-specialist.md` | `Codex Studio Testing Framework/agents/engine/godot/godot-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unity/unity-addressables-specialist.md` | `Codex Studio Testing Framework/agents/engine/unity/unity-addressables-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unity/unity-dots-specialist.md` | `Codex Studio Testing Framework/agents/engine/unity/unity-dots-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unity/unity-shader-specialist.md` | `Codex Studio Testing Framework/agents/engine/unity/unity-shader-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unity/unity-specialist.md` | `Codex Studio Testing Framework/agents/engine/unity/unity-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unity/unity-ui-specialist.md` | `Codex Studio Testing Framework/agents/engine/unity/unity-ui-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unreal/ue-blueprint-specialist.md` | `Codex Studio Testing Framework/agents/engine/unreal/ue-blueprint-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unreal/ue-gas-specialist.md` | `Codex Studio Testing Framework/agents/engine/unreal/ue-gas-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unreal/ue-replication-specialist.md` | `Codex Studio Testing Framework/agents/engine/unreal/ue-replication-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unreal/ue-umg-specialist.md` | `Codex Studio Testing Framework/agents/engine/unreal/ue-umg-specialist.md` |
| `CCGS Skill Testing Framework/agents/engine/unreal/unreal-specialist.md` | `Codex Studio Testing Framework/agents/engine/unreal/unreal-specialist.md` |
| `CCGS Skill Testing Framework/agents/leads/audio-director.md` | `Codex Studio Testing Framework/agents/leads/audio-director.md` |
| `CCGS Skill Testing Framework/agents/leads/game-designer.md` | `Codex Studio Testing Framework/agents/leads/game-designer.md` |
| `CCGS Skill Testing Framework/agents/leads/lead-programmer.md` | `Codex Studio Testing Framework/agents/leads/lead-programmer.md` |
| `CCGS Skill Testing Framework/agents/leads/level-designer.md` | `Codex Studio Testing Framework/agents/leads/level-designer.md` |
| `CCGS Skill Testing Framework/agents/leads/narrative-director.md` | `Codex Studio Testing Framework/agents/leads/narrative-director.md` |
| `CCGS Skill Testing Framework/agents/leads/qa-lead.md` | `Codex Studio Testing Framework/agents/leads/qa-lead.md` |
| `CCGS Skill Testing Framework/agents/leads/systems-designer.md` | `Codex Studio Testing Framework/agents/leads/systems-designer.md` |
| `CCGS Skill Testing Framework/agents/operations/analytics-engineer.md` | `Codex Studio Testing Framework/agents/operations/analytics-engineer.md` |
| `CCGS Skill Testing Framework/agents/operations/community-manager.md` | `Codex Studio Testing Framework/agents/operations/community-manager.md` |
| `CCGS Skill Testing Framework/agents/operations/devops-engineer.md` | `Codex Studio Testing Framework/agents/operations/devops-engineer.md` |
| `CCGS Skill Testing Framework/agents/operations/economy-designer.md` | `Codex Studio Testing Framework/agents/operations/economy-designer.md` |
| `CCGS Skill Testing Framework/agents/operations/live-ops-designer.md` | `Codex Studio Testing Framework/agents/operations/live-ops-designer.md` |
| `CCGS Skill Testing Framework/agents/operations/localization-lead.md` | `Codex Studio Testing Framework/agents/operations/localization-lead.md` |
| `CCGS Skill Testing Framework/agents/operations/release-manager.md` | `Codex Studio Testing Framework/agents/operations/release-manager.md` |
| `CCGS Skill Testing Framework/agents/qa/accessibility-specialist.md` | `Codex Studio Testing Framework/agents/qa/accessibility-specialist.md` |
| `CCGS Skill Testing Framework/agents/qa/qa-tester.md` | `Codex Studio Testing Framework/agents/qa/qa-tester.md` |
| `CCGS Skill Testing Framework/agents/qa/security-engineer.md` | `Codex Studio Testing Framework/agents/qa/security-engineer.md` |
| `CCGS Skill Testing Framework/agents/specialists/ai-programmer.md` | `Codex Studio Testing Framework/agents/specialists/ai-programmer.md` |
| `CCGS Skill Testing Framework/agents/specialists/engine-programmer.md` | `Codex Studio Testing Framework/agents/specialists/engine-programmer.md` |
| `CCGS Skill Testing Framework/agents/specialists/gameplay-programmer.md` | `Codex Studio Testing Framework/agents/specialists/gameplay-programmer.md` |
| `CCGS Skill Testing Framework/agents/specialists/network-programmer.md` | `Codex Studio Testing Framework/agents/specialists/network-programmer.md` |
| `CCGS Skill Testing Framework/agents/specialists/performance-analyst.md` | `Codex Studio Testing Framework/agents/specialists/performance-analyst.md` |
| `CCGS Skill Testing Framework/agents/specialists/prototyper.md` | `Codex Studio Testing Framework/agents/specialists/prototyper.md` |
| `CCGS Skill Testing Framework/agents/specialists/sound-designer.md` | `Codex Studio Testing Framework/agents/specialists/sound-designer.md` |
| `CCGS Skill Testing Framework/agents/specialists/technical-artist.md` | `Codex Studio Testing Framework/agents/specialists/technical-artist.md` |
| `CCGS Skill Testing Framework/agents/specialists/tools-programmer.md` | `Codex Studio Testing Framework/agents/specialists/tools-programmer.md` |
| `CCGS Skill Testing Framework/agents/specialists/ui-programmer.md` | `Codex Studio Testing Framework/agents/specialists/ui-programmer.md` |
| `CCGS Skill Testing Framework/agents/specialists/ux-designer.md` | `Codex Studio Testing Framework/agents/specialists/ux-designer.md` |
| `CCGS Skill Testing Framework/agents/specialists/world-builder.md` | `Codex Studio Testing Framework/agents/specialists/world-builder.md` |
| `CCGS Skill Testing Framework/agents/specialists/writer.md` | `Codex Studio Testing Framework/agents/specialists/writer.md` |
| `CCGS Skill Testing Framework/catalog.yaml` | `Codex Studio Testing Framework/catalog.yaml` |
| `CCGS Skill Testing Framework/quality-rubric.md` | `Codex Studio Testing Framework/quality-rubric.md` |
| `CCGS Skill Testing Framework/skills/analysis/asset-audit.md` | `Codex Studio Testing Framework/skills/analysis/asset-audit.md` |
| `CCGS Skill Testing Framework/skills/analysis/balance-check.md` | `Codex Studio Testing Framework/skills/analysis/balance-check.md` |
| `CCGS Skill Testing Framework/skills/analysis/code-review.md` | `Codex Studio Testing Framework/skills/analysis/code-review.md` |
| `CCGS Skill Testing Framework/skills/analysis/consistency-check.md` | `Codex Studio Testing Framework/skills/analysis/consistency-check.md` |
| `CCGS Skill Testing Framework/skills/analysis/content-audit.md` | `Codex Studio Testing Framework/skills/analysis/content-audit.md` |
| `CCGS Skill Testing Framework/skills/analysis/estimate.md` | `Codex Studio Testing Framework/skills/analysis/estimate.md` |
| `CCGS Skill Testing Framework/skills/analysis/perf-profile.md` | `Codex Studio Testing Framework/skills/analysis/perf-profile.md` |
| `CCGS Skill Testing Framework/skills/analysis/scope-check.md` | `Codex Studio Testing Framework/skills/analysis/scope-check.md` |
| `CCGS Skill Testing Framework/skills/analysis/security-audit.md` | `Codex Studio Testing Framework/skills/analysis/security-audit.md` |
| `CCGS Skill Testing Framework/skills/analysis/tech-debt.md` | `Codex Studio Testing Framework/skills/analysis/tech-debt.md` |
| `CCGS Skill Testing Framework/skills/analysis/test-evidence-review.md` | `Codex Studio Testing Framework/skills/analysis/test-evidence-review.md` |
| `CCGS Skill Testing Framework/skills/analysis/test-flakiness.md` | `Codex Studio Testing Framework/skills/analysis/test-flakiness.md` |
| `CCGS Skill Testing Framework/skills/authoring/architecture-decision.md` | `Codex Studio Testing Framework/skills/authoring/architecture-decision.md` |
| `CCGS Skill Testing Framework/skills/authoring/art-bible.md` | `Codex Studio Testing Framework/skills/authoring/art-bible.md` |
| `CCGS Skill Testing Framework/skills/authoring/create-architecture.md` | `Codex Studio Testing Framework/skills/authoring/create-architecture.md` |
| `CCGS Skill Testing Framework/skills/authoring/design-system.md` | `Codex Studio Testing Framework/skills/authoring/design-system.md` |
| `CCGS Skill Testing Framework/skills/authoring/quick-design.md` | `Codex Studio Testing Framework/skills/authoring/quick-design.md` |
| `CCGS Skill Testing Framework/skills/authoring/ux-design.md` | `Codex Studio Testing Framework/skills/authoring/ux-design.md` |
| `CCGS Skill Testing Framework/skills/authoring/ux-review.md` | `Codex Studio Testing Framework/skills/authoring/ux-review.md` |
| `CCGS Skill Testing Framework/skills/gate/gate-check.md` | `Codex Studio Testing Framework/skills/gate/gate-check.md` |
| `CCGS Skill Testing Framework/skills/pipeline/create-control-manifest.md` | `Codex Studio Testing Framework/skills/pipeline/create-control-manifest.md` |
| `CCGS Skill Testing Framework/skills/pipeline/create-epics.md` | `Codex Studio Testing Framework/skills/pipeline/create-epics.md` |
| `CCGS Skill Testing Framework/skills/pipeline/create-stories.md` | `Codex Studio Testing Framework/skills/pipeline/create-stories.md` |
| `CCGS Skill Testing Framework/skills/pipeline/dev-story.md` | `Codex Studio Testing Framework/skills/pipeline/dev-story.md` |
| `CCGS Skill Testing Framework/skills/pipeline/map-systems.md` | `Codex Studio Testing Framework/skills/pipeline/map-systems.md` |
| `CCGS Skill Testing Framework/skills/pipeline/propagate-design-change.md` | `Codex Studio Testing Framework/skills/pipeline/propagate-design-change.md` |
| `CCGS Skill Testing Framework/skills/readiness/story-done.md` | `Codex Studio Testing Framework/skills/readiness/story-done.md` |
| `CCGS Skill Testing Framework/skills/readiness/story-readiness.md` | `Codex Studio Testing Framework/skills/readiness/story-readiness.md` |
| `CCGS Skill Testing Framework/skills/review/architecture-review.md` | `Codex Studio Testing Framework/skills/review/architecture-review.md` |
| `CCGS Skill Testing Framework/skills/review/design-review.md` | `Codex Studio Testing Framework/skills/review/design-review.md` |
| `CCGS Skill Testing Framework/skills/review/review-all-gdds.md` | `Codex Studio Testing Framework/skills/review/review-all-gdds.md` |
| `CCGS Skill Testing Framework/skills/sprint/changelog.md` | `Codex Studio Testing Framework/skills/sprint/changelog.md` |
| `CCGS Skill Testing Framework/skills/sprint/milestone-review.md` | `Codex Studio Testing Framework/skills/sprint/milestone-review.md` |
| `CCGS Skill Testing Framework/skills/sprint/patch-notes.md` | `Codex Studio Testing Framework/skills/sprint/patch-notes.md` |
| `CCGS Skill Testing Framework/skills/sprint/retrospective.md` | `Codex Studio Testing Framework/skills/sprint/retrospective.md` |
| `CCGS Skill Testing Framework/skills/sprint/sprint-plan.md` | `Codex Studio Testing Framework/skills/sprint/sprint-plan.md` |
| `CCGS Skill Testing Framework/skills/sprint/sprint-status.md` | `Codex Studio Testing Framework/skills/sprint/sprint-status.md` |
| `CCGS Skill Testing Framework/skills/team/team-audio.md` | `Codex Studio Testing Framework/skills/team/team-audio.md` |
| `CCGS Skill Testing Framework/skills/team/team-combat.md` | `Codex Studio Testing Framework/skills/team/team-combat.md` |
| `CCGS Skill Testing Framework/skills/team/team-level.md` | `Codex Studio Testing Framework/skills/team/team-level.md` |
| `CCGS Skill Testing Framework/skills/team/team-live-ops.md` | `Codex Studio Testing Framework/skills/team/team-live-ops.md` |
| `CCGS Skill Testing Framework/skills/team/team-narrative.md` | `Codex Studio Testing Framework/skills/team/team-narrative.md` |
| `CCGS Skill Testing Framework/skills/team/team-polish.md` | `Codex Studio Testing Framework/skills/team/team-polish.md` |
| `CCGS Skill Testing Framework/skills/team/team-qa.md` | `Codex Studio Testing Framework/skills/team/team-qa.md` |
| `CCGS Skill Testing Framework/skills/team/team-release.md` | `Codex Studio Testing Framework/skills/team/team-release.md` |
| `CCGS Skill Testing Framework/skills/team/team-ui.md` | `Codex Studio Testing Framework/skills/team/team-ui.md` |
| `CCGS Skill Testing Framework/skills/utility/adopt.md` | `Codex Studio Testing Framework/skills/utility/adopt.md` |
| `CCGS Skill Testing Framework/skills/utility/asset-spec.md` | `Codex Studio Testing Framework/skills/utility/asset-spec.md` |
| `CCGS Skill Testing Framework/skills/utility/brainstorm.md` | `Codex Studio Testing Framework/skills/utility/brainstorm.md` |
| `CCGS Skill Testing Framework/skills/utility/bug-report.md` | `Codex Studio Testing Framework/skills/utility/bug-report.md` |
| `CCGS Skill Testing Framework/skills/utility/bug-triage.md` | `Codex Studio Testing Framework/skills/utility/bug-triage.md` |
| `CCGS Skill Testing Framework/skills/utility/day-one-patch.md` | `Codex Studio Testing Framework/skills/utility/day-one-patch.md` |
| `CCGS Skill Testing Framework/skills/utility/help.md` | `Codex Studio Testing Framework/skills/utility/help.md` |
| `CCGS Skill Testing Framework/skills/utility/hotfix.md` | `Codex Studio Testing Framework/skills/utility/hotfix.md` |
| `CCGS Skill Testing Framework/skills/utility/launch-checklist.md` | `Codex Studio Testing Framework/skills/utility/launch-checklist.md` |
| `CCGS Skill Testing Framework/skills/utility/localize.md` | `Codex Studio Testing Framework/skills/utility/localize.md` |
| `CCGS Skill Testing Framework/skills/utility/onboard.md` | `Codex Studio Testing Framework/skills/utility/onboard.md` |
| `CCGS Skill Testing Framework/skills/utility/playtest-report.md` | `Codex Studio Testing Framework/skills/utility/playtest-report.md` |
| `CCGS Skill Testing Framework/skills/utility/project-stage-detect.md` | `Codex Studio Testing Framework/skills/utility/project-stage-detect.md` |
| `CCGS Skill Testing Framework/skills/utility/prototype.md` | `Codex Studio Testing Framework/skills/utility/prototype.md` |
| `CCGS Skill Testing Framework/skills/utility/qa-plan.md` | `Codex Studio Testing Framework/skills/utility/qa-plan.md` |
| `CCGS Skill Testing Framework/skills/utility/regression-suite.md` | `Codex Studio Testing Framework/skills/utility/regression-suite.md` |
| `CCGS Skill Testing Framework/skills/utility/release-checklist.md` | `Codex Studio Testing Framework/skills/utility/release-checklist.md` |
| `CCGS Skill Testing Framework/skills/utility/reverse-document.md` | `Codex Studio Testing Framework/skills/utility/reverse-document.md` |
| `CCGS Skill Testing Framework/skills/utility/setup-engine.md` | `Codex Studio Testing Framework/skills/utility/setup-engine.md` |
| `CCGS Skill Testing Framework/skills/utility/skill-improve.md` | `Codex Studio Testing Framework/skills/utility/skill-improve.md` |
| `CCGS Skill Testing Framework/skills/utility/skill-test.md` | `Codex Studio Testing Framework/skills/utility/skill-test.md` |
| `CCGS Skill Testing Framework/skills/utility/smoke-check.md` | `Codex Studio Testing Framework/skills/utility/smoke-check.md` |
| `CCGS Skill Testing Framework/skills/utility/soak-test.md` | `Codex Studio Testing Framework/skills/utility/soak-test.md` |
| `CCGS Skill Testing Framework/skills/utility/start.md` | `Codex Studio Testing Framework/skills/utility/start.md` |
| `CCGS Skill Testing Framework/skills/utility/test-helpers.md` | `Codex Studio Testing Framework/skills/utility/test-helpers.md` |
| `CCGS Skill Testing Framework/skills/utility/test-setup.md` | `Codex Studio Testing Framework/skills/utility/test-setup.md` |
| `CCGS Skill Testing Framework/templates/agent-test-spec.md` | `Codex Studio Testing Framework/templates/agent-test-spec.md` |
| `CCGS Skill Testing Framework/templates/skill-test-spec.md` | `Codex Studio Testing Framework/templates/skill-test-spec.md` |

## Final-review remediation

- Public documentation, contribution/security guidance, GitHub templates,
  examples, runtime docs, and the upgrade guide now describe Codex-native
  components and dollar-prefixed skill invocation. The upgrade guide retains a
  complete preserve/merge/verify/rollback method while confining legacy names
  to historical migration context.
- All 49 agent specifications now assert their exact TOML path, schema, and
  Sol/Terra/Luna route. All 73 skill specifications now assert runtime
  discovery, `$skill` invocation, one decision per turn, native question
  cardinality, bounded delegation, parent synthesis, and five behavioral cases.
  The `vertical-slice` extension contains the same complete protocol.
- The final validator now reads UTF-8 strictly, rejects NUL data, unreadable and
  non-regular files, symlinks, unsafe relative paths, alternate-root leakage,
  legacy directories even when empty, and any identity substitution in the
  agent, skill, instruction, document, or template inventories.
- Coverage is pinned to the exact 203-entry source set and full mapping digest.
  Testing-framework parity is durably recorded in
  `production/migration/testing-framework-parity.json` with 127 source object
  hashes, exact native mappings, a contract digest, and the deliberate native
  `vertical-slice` extension.
- `$start` has a dedicated executable contract test for fresh-project routing,
  `.codex/studio.toml`, sequential two-option questions, and valid native
  question schema.

## Contract-closure remediation

- `.codex/studio.toml` is now the only persistent review-depth authority.
  `$start` detects real project artifacts first, asks ordered project-state
  decisions, proposes `production/stage.txt` separately, and writes a selected
  `review_mode` only through an explicitly approved `.codex/studio.toml`
  changeset. `phase-gated` means lean optional review while mandatory director
  gates remain active; `solo` also preserves explicitly required gates.
- Runtime `$skill-test`, its framework spec, and the quality rubric share the
  exact `validate_skill` discovery contract: frontmatter contains only `name`
  and `description`, the name matches the directory, and the description is
  nonblank. Static validation does not require a literal prefix or judge
  whether the prose is trigger-oriented. All 73 shipped skills are checked
  against the runtime validator.
- Every framework agent spec records and is tested against both the exact
  `model` and exact `model_reasoning_effort` in its TOML profile. Framework
  paths now resolve to real native locations. Authoring specs require either a
  complete approved changeset for multi-file/atomic work or sequential bounded
  section approval before a section write; the framework `$start` cases mirror
  the runtime project-state and artifact sequence.
- Runtime traversal now covers `assets/`, `src/`, and `prototypes/` in addition
  to the prior roots, rejects file and directory symlinks, and reports
  `os.walk` read failures as validation errors. Tests and the validator itself
  receive no whole-file exemption: enforcement literals require balanced,
  explicit line or block markers. Upgrade-history exceptions likewise require
  balanced, non-nested historical markers.
- Framework parity pins source commit
  `7bad60b7e0e71723b4b745e36950492d714595a3` and source root
  `CCGS Skill Testing Framework` into the contract digest. The validator
  rejects metadata tampering and any extra, missing, or symlinked native file
  outside the exact 127 mappings plus the `vertical-slice` extension.

## Runtime/framework semantic alignment

- `$start` now classifies the clean checkout as fresh by excluding nested
  `AGENTS.md`, `.gitkeep`, and other instruction-only placeholders from artifact
  evidence. Missing, unreadable, or invalid `.codex/studio.toml` blocks instead
  of guessing, while a configured engine plus concept takes the returning-user
  route and skips onboarding.
- Mandatory `*-PHASE-GATE` directors run in `full`, `phase-gated`, and `solo`;
  only optional gates vary by review mode. The framework now matches the runtime
  contracts for optional TD-MANIFEST and CD-PLAYTEST gates and mandatory
  TD-CHANGE-IMPACT review.
- The design-system, art-bible, UX-design, and create-architecture framework
  specs preserve their runtime incremental workflow: present one section,
  obtain section approval, write only that bounded section, then update session
  progress without requesting duplicate per-file approval.
- Create-architecture reads back and finalizes the already assembled document
  without a second whole-document write. TD-ARCHITECTURE remains mandatory in
  every review mode, while LP-FEASIBILITY, CD-GDD-ALIGN, and AD-ART-BIBLE run
  only in full mode. AD-ART-BIBLE delegates to `art-director`, and the canonical
  art bible path is `design/art/art-bible.md`.
- The stage coverage matrix classifies inline gates that skip in lean/solo as
  optional across Concept, Systems Design, Pre-Production, Production, and
  Polish. Only TD-ARCHITECTURE, TD-ADR, and the named phase-transition
  PHASE-GATE panels remain in Required cells. Cross-contract tests compare the
  table with the corresponding runtime and framework skip semantics.
- `$architecture-decision` runs mandatory TD-ADR review in full, phase-gated,
  and solo modes, does not invoke LP-FEASIBILITY, and keeps new ADRs Proposed
  pending their separate lifecycle acceptance decision.
- `$map-systems` runs optional full-mode gates sequentially at their owning
  phases: TD-SYSTEM-BOUNDARY after dependency approval, PR-SCOPE after priority
  approval, and CD-SYSTEMS after the approved initial index write. The index and
  canonical active session record share one complete initial changeset; any
  post-write creative-director revision requires a separately approved exact
  revision changeset. Phase-gated and solo record all three gate skips.
- `$skill-test` Check 4 accepts both approved workflow shapes and rejects any
  write before its appropriate complete-changeset or bounded-section approval.
- Cross-runtime/framework tests pin these start routing, gate-mode, incremental
  authoring, and structural skill-validation semantics.

## Known limitation

The hook runner defends repository boundaries with reviewed path checks and
no-follow-style validation, but its check/read sequence is not an atomic
filesystem transaction. A hostile concurrent writer could create a TOCTOU race.
The project does not claim otherwise; hook tests cover the practical symlink and
reparse-point cases.

## Final automated gate

- `python3 -m unittest discover -s tests -v`:
  **253 tests, OK; zero skips**.
- `python3 -m tools.codex_studio.validate --root . --phase final`:
  **Codex Studio validation: PASS**.
- Exact inventories: **34 core + 15 packed = 49 unique agents**, **73 skills**,
  **11 nested instruction boundaries**, **3×5 engine packs**, **40 document
  templates**, **49 framework agent specs**, and **73 framework skill specs**.
- Operational runtime/public forbidden-reference and machine-path searches are
  clean after excluding exactly the retained historical evidence directories
  (`.superpowers/sdd/`, `docs/superpowers/`, and `production/migration/`) and
  the validator/test literal definitions that enforce the prohibition.
- Root README links and `AGENTS.md` imports resolve.
- Python compilation, JSON/TOML/YAML parsing, deterministic catalog/coverage
  and parity parsing, recursive link/path validation, and `git diff --check`:
  pass.
- `.claude/`, `CCGS Skill Testing Framework/`, and every `CLAUDE.md` source are
  absent after cleanup.

## Static/manual Codex smoke checklist

| Check | Evidence | Status |
| --- | --- | --- |
| `AGENTS.md` loads without broken references | Automated root-import resolution test | VERIFIED STATICALLY |
| All 73 skills appear in the selector | Runtime inventory and exact framework catalog are 73/73 | UI NOT EXERCISED |
| 34 core agents are available before engine selection | Native profile count and unconfigured studio tests | UI NOT EXERCISED |
| Hooks appear in the review screen with relative commands | Native hook JSON, command-template, and portability tests | UI NOT EXERCISED |
| `$start` identifies a fresh project | Dedicated fresh-project routing and native-question contract tests | VERIFIED STATICALLY; UI NOT EXERCISED |
| `$setup-engine` dry-run lists five profiles | Automated dry-run and pack-count tests | VERIFIED AUTOMATICALLY |
| Test activation reports the correct roster | Automated activation/manifest/studio/rollback tests | VERIFIED AUTOMATICALLY |
| Team skills delegate only to direct children and synthesize at parent | Static contracts for depth, bounded work, and parent synthesis | VERIFIED STATICALLY |

The UI-only items remain explicitly unverified because this implementation
environment does not expose a trusted Codex selector/hook-review session for
the isolated worktree.
