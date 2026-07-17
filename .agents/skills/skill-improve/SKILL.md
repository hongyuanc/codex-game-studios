---
name: skill-improve
description: "Use when a Codex skill has validation failures or warnings that need an approved test-fix-retest cycle."
---

## Codex Interaction Contract

- Ask one decision question per turn and wait for the answer before asking another.
- Use `request_user_input` for structured choices when it is available; otherwise ask the same concise question directly.
- Use Codex custom agents by role and profile when delegation is useful.
- Treat any approved write as one complete proposed changeset. Before writing, present every target path and material edit together; do not add unlisted files or behavior.
- A new path, expanded scope, or material change requires a revised complete proposed changeset and fresh approval.

## Skill Edit Boundary

Validation is read-only and needs no approval. Show the exact proposed edit set as a complete changeset and receive explicit approval before applying it. Preserve the original content, retest the same checks, and keep edits only when the retest score does not regress; otherwise restore the original skill without using a destructive Git command.

### Native readiness gate for `$skill-test`

Before invoking `$skill-test`, confirm that `skill-test` is present in the
current task's available skill catalog. If unavailable, report
`Staged dependency: $skill-test is not available`, defer the handoff, and do
not search for or copy a repository-local skill file.

# Skill Improve

Runs an improvement loop on a single skill:
test → fix → retest → keep or revert.

---

## Phase 1: Parse Argument

Read the skill name from the first argument. If missing, output usage and stop:

```
Usage: $skill-improve [skill-name]
Example: $skill-improve tech-debt
```

Confirm that `[name]` is present in the current task's available skill catalog.
If unavailable, stop with:
"Skill '[name]' not found."

---

## Phase 2: Baseline Test

Run `$skill-test static [name]` and record the baseline score:
- Count of FAILs
- Count of WARNs
- Which specific checks failed (Check 1–7)

Display to the user:
```
Static baseline:   [N] failures, [M] warnings
Failing: Check 4 (no ask-before-write), Check 5 (no handoff)
```

If baseline is 0 FAILs and 0 WARNs, note it and proceed to Phase 2b.

### Phase 2b: Category Baseline

Check whether `../../../Codex Studio Testing Framework/catalog.yaml` exists. If it does not, report `Staged dependency: Codex Studio Testing Framework is not migrated yet` and skip the category baseline; static improvement remains available. If it exists, look up the skill's `category:` field there.

If no `category:` field is found, display:
"Category: not yet assigned — skipping category checks."
and skip to Phase 3.

If category is found, run `$skill-test category [name]` and record the category baseline:
- Count of FAILs
- Count of WARNs
- Which specific category rubric metrics failed

Display to the user:
```
Category baseline: [N] failures, [M] warnings  ([category] rubric)
```

If BOTH static and category baselines are 0 FAILs and 0 WARNs, stop:
"This skill already passes all static and category checks. No improvements needed."

---

## Phase 3: Diagnose

Read the full skill resource resolved by `[name]` in the available skill catalog.

For each failing or warning **static** check, identify the exact gap:

- **Check 1 fail** → native validator issue or missing trigger-oriented frontmatter
- **Check 2 fail** → how many phases found vs. minimum required
- **Check 3 fail** → no verdict keywords anywhere in the skill body
- **Check 4 fail** → a writing workflow lacks one complete proposed changeset approval
- **Check 5 warn** → no follow-up or next-step section at the end
- **Check 6 warn** → delegated work lacks bounded child tasks, depth limit, parent synthesis, or no-child-mutation rules
- **Check 7 warn** → the dollar-prefixed invocation contract is missing or does not match documented modes

For each failing or warning **category** check (if category was assigned in Phase 2b),
identify the exact gap in the skill's text. For example:
- If G2 fails (gate mode, full directors not spawned): skill body never references all 4
  PHASE-GATE director prompts
- If A2 fails (authoring approval): the complete proposed changeset does not list every target and material edit
- If T3 fails (team, BLOCKED not surfaced): skill doesn't halt dependent work on blocked agent

Show the full combined diagnosis to the user before proposing any changes.

---

## Phase 4: Propose Exact Edit Set

For each failing assertion, show the smallest before/after edit. Combine these
into the exact proposed edit set, list the catalog-resolved skill resource as
the only target, and request explicit approval before applying. If approval is
declined, stop without changing the skill.

---

## Phase 5: Apply and Retest

After approval, preserve the original skill content in memory, apply only the approved edits, and rerun the same static and category checks used for the baseline. Display before/after failures and warnings. The retest score does not regress only when failures do not increase and warnings do not increase at equal failure count.

Use this comparison schema:

```
Static:   Before [N] failures, [M] warnings  →  After [N'] failures, [M'] warnings
Category: Before [N] failures, [M] warnings  →  After [N'] failures, [M'] warnings  (if applicable)
Combined change: improved / no change / worse
```

---

## Phase 6: Verdict

If the retest score improves or stays equal, keep the approved changes and report the evidence. If it regresses, restore the original skill immediately from the preserved content, rerun the baseline checks to prove restoration, and report that the proposed edit set was rejected. Do not use Git checkout or another destructive operation for restoration.
## Phase 7: Next Steps

- Run `$skill-test static all` to find the next skill with failures.
- Run `$skill-improve [next-name]` to continue the loop on another skill.
- Run `$skill-test audit` to see overall coverage progress.
