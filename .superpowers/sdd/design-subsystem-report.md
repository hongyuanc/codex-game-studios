# Design Skills Subsystem Report

## Scope

Converted exactly these 29 design-facing skills to Codex-native workflows:

`adopt`, `architecture-decision`, `architecture-review`, `art-bible`, `asset-audit`, `asset-spec`, `balance-check`, `brainstorm`, `consistency-check`, `content-audit`, `create-architecture`, `create-control-manifest`, `design-review`, `design-system`, `gate-check`, `help`, `map-systems`, `perf-profile`, `project-stage-detect`, `propagate-design-change`, `prototype`, `quick-design`, `review-all-gdds`, `scope-check`, `start`, `tech-debt`, `ux-design`, `ux-review`, and `vertical-slice`.

Supporting changes add `validate_skill(path)` to `tools/codex_studio/validate.py` and the focused contract suite at `tests/studio/test_design_skills.py`.

## TDD Evidence

1. RED: `python3 -m unittest tests.studio.test_design_skills -v` failed to import because `validate_skill` did not exist.
2. RED after minimal validator: the exact skill-set test passed, while native validation reported 107 Claude metadata, interaction, delegation, model, or path issues.
3. RED after the mechanical metadata/path pass: native validation still reported 25 skill-level semantic violations, proving the semantic conversion remained required.
4. GREEN after semantic conversion: `python3 -m unittest tests.studio.test_design_skills -v` passed 2 tests.
5. Full studio GREEN: `python3 -m unittest discover -s tests/studio -v` passed 8 tests in 0.068 seconds with no failures or warnings.

## Semantic Audit

- Every selected skill has exactly two frontmatter fields: `name` and one concrete trigger `description`.
- Claude models, tool metadata, interaction primitives, delegation primitives, `.claude`/`.Codex` paths, and Claude naming were removed.
- Skill invocations use `$skill`; filesystem paths, report names, artifact paths, URLs, and regular-expression content retain slash semantics.
- Interactive workflows ask at most one question per turn and wait for the answer.
- Concept, art, GDD, UX, prototype, and vertical-slice workflows retain material section approval. An approved section or explicitly listed changeset authorizes its bounded write without a second per-file prompt.
- Review and audit workflows cite repository evidence, keep reviewed source artifacts read-only during analysis, and require separate explicit authorization for fixes. Report and tracking writes retain explicit path approval.
- Delegation targets named Codex custom-agent roles. Material architecture choices and conflicts route through the Sol `technical-director`; domain reviews retain their named specialist roles and parallel boundaries.
- ADR status, TR-ID, traceability, control-manifest version, asset ID, asset-manifest, verdict vocabulary, phase gates, and original artifact output paths were preserved.
- `asset-spec` now presents the spec and asset-manifest updates as one explicit full changeset before writing.
- Fresh-project and missing-engine discovery routes are explicit: `$start` and `$setup-engine` respectively.

Required manual audit command returned no matches:

```text
rg -n 'AskUserQuestion|TodoWrite|Task tool|subagent_type|\.Codex/|\.claude/|model: (opus|sonnet|haiku)|allowed-tools:' [29 selected skill directories]
```

An extended audit also found no residual slash-command syntax, corrupted `$skill` path substitutions, Claude search/edit tool terminology, multi-tab interaction syntax, or per-file approval mandates in the selected skills.

## Changed Files

- `tools/codex_studio/validate.py`
- `tests/studio/test_design_skills.py`
- The 29 `.agents/skills/<name>/SKILL.md` files listed in Scope
- `.superpowers/sdd/design-subsystem-report.md`

No delivery skills, operations/team skills, `setup-engine`, hooks, public documentation, or `docs/superpowers` files were changed by this subsystem.

## Commit

This report is included in the single local commit `feat: port design workflows to Codex`. The authoritative final hash is returned with the subsystem completion status because amending a commit to embed its own hash would change that hash.

## Self-Review and Concerns

- Scope review: changes are limited to the validator, its focused tests, the named 29 skills, and this report.
- Behavioral review: output paths, verdicts, gates, traceability contracts, prerequisites, and domain outputs remain present.
- Safety review: phase-gated design approval remains intact; source-fixing review paths require separate authorization.
- No blocking concern remains. The automated validator deliberately checks native structural hazards; the richer workflow guarantees are additionally documented and verified by the semantic audit rather than a natural-language parser.
