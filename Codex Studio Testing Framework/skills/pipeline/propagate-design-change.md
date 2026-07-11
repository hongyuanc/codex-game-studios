# Skill Test Spec: $propagate-design-change

## Codex Runtime Contract

- Runtime skill: `.agents/skills/propagate-design-change/SKILL.md`
- Runtime name: `propagate-design-change`
- Runtime trigger description: `Trace an approved GDD change through ADRs and architecture artifacts and report affected decisions.`
- Native invocation: `$propagate-design-change`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$propagate-design-change` is tested against the exact runtime discovery contract above. The five
cases below preserve its domain fixtures, expected outputs, verdict vocabulary, review
modes, and edge conditions.

Validation is read-only. If the workflow writes, the parent first presents one
complete proposed changeset containing every target path and material edit; any
new path or scope expansion requires fresh approval. If it delegates, direct
children return scoped evidence and the parent synthesizes the result.

---

## Static Assertions (Structural)

Verified automatically by `$skill-test static` — no fixture needed.

- [ ] Runtime YAML frontmatter has only the required discovery fields `name` and `description`, and both match the contract above
- [ ] Has ≥2 phase headings
- [ ] Contains verdict keywords: COMPLETE, BLOCKED, NO IMPACT
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end
- [ ] Documents that changes are proposed, not applied automatically

---

## Director Gate Checks

No director gates — this skill spawns no director gate agents during analysis.
The impact report is a mechanical tracing operation; no creative or technical
director review is required at the analysis stage.

---

## Test Cases

### Case 1: Happy Path — GDD revision affects 2 stories and 1 epic

**Fixture:**
- `design/gdd/[system].md` exists and has been recently revised (git diff shows changes)
- `production/epics/[layer]/EPIC-[system].md` references this GDD
- 2 story files reference TR-IDs from this GDD
- The changed GDD section affects the acceptance criteria of both stories

**Input:** `$propagate-design-change design/gdd/[system].md`

**Expected behavior:**
1. Skill reads the revised GDD and identifies what changed (git diff or content comparison)
2. Skill scans ADRs, TR-registry, epics, and stories for references to this GDD
3. Skill produces an impact report: 1 epic affected, 2 stories affected
4. Skill shows the proposed change for each artifact
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
6. Applies changes only after one complete proposed changeset lists every affected artifact and is approved

**Assertions:**
- [ ] Impact report identifies all 3 affected artifacts (1 epic + 2 stories)
- [ ] Each affected artifact's proposed change is shown before asking to write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill applies no change until the complete affected-artifact changeset is approved
- [ ] Verdict is COMPLETE after all approved changes are applied

---

### Case 2: No Impact — Changed GDD has no downstream references

**Fixture:**
- `design/gdd/[system].md` exists and has been revised
- No ADRs, stories, or epics reference this GDD's TR-IDs or GDD path

**Input:** `$propagate-design-change design/gdd/[system].md`

**Expected behavior:**
1. Skill reads the revised GDD
2. Skill scans all ADRs, stories, and epics for references
3. No references found
4. Skill outputs: "No downstream impact found for [system].md — no artifacts reference this GDD."
5. No write operations are performed

**Assertions:**
- [ ] Skill outputs the "No downstream impact found" message
- [ ] Verdict is NO IMPACT
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill does NOT error or crash when no references are found

---

### Case 3: In-Progress Story Warning — Referenced story is currently being developed

**Fixture:**
- A story referencing this GDD has `Status: In Progress`
- The developer has already started implementing this story

**Input:** `$propagate-design-change design/gdd/[system].md`

**Expected behavior:**
1. Skill identifies the In Progress story as an affected artifact
2. Skill outputs an elevated warning: "CAUTION: [story-file] is currently In Progress — a developer may be working on this. Coordinate before updating."
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
4. User can still approve or skip the update for that story

**Assertions:**
- [ ] In Progress story is flagged with an elevated warning (distinct from regular affected-artifact entries)
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill still offers to update the story — the warning does not block the option
- [ ] Other (non-In-Progress) artifacts are not affected by this warning

---

### Case 4: Edge Case — No argument provided

**Fixture:**
- Multiple GDDs exist in `design/gdd/`

**Input:** `$propagate-design-change` (no argument)

**Expected behavior:**
1. Skill detects no argument is provided
2. Skill outputs a usage error: "No GDD specified. Usage: $propagate-design-change design/gdd/[system].md"
3. Skill lists recently modified GDDs as suggestions (git log)
4. No analysis is performed

**Assertions:**
- [ ] Skill outputs a usage error when no argument is given
- [ ] Usage example is shown with the correct path format
- [ ] No impact analysis is performed without a target GDD
- [ ] Skill does NOT silently pick a GDD without user input

---

### Case 5: Director Gate — No gate spawned regardless of review mode

**Fixture:**
- A GDD has been revised with downstream references
- `.codex/studio.toml` exists with `full`

**Input:** `$propagate-design-change design/gdd/[system].md`

**Expected behavior:**
1. Skill reads the GDD and traces downstream references
2. Skill does NOT read `.codex/studio.toml`
3. No director gate agents are spawned at any point
4. Impact report is produced and the complete affected-artifact changeset proceeds to approval

**Assertions:**
- [ ] No director gate agents are spawned (no CD-, TD-, PR-, AD- prefixed gates)
- [ ] Skill does NOT read `.codex/studio.toml`
- [ ] Output contains no "Gate: [GATE-ID]" or gate-skipped entries
- [ ] Review mode has no effect on this skill's behavior

---

## Protocol Compliance

- [ ] Reads revised GDD and all potentially affected artifacts before producing impact report
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] In Progress stories flagged with elevated warning before their approval ask
- [ ] No director gates — no .codex/studio.toml read
- [ ] Ends with next-step handoff appropriate to verdict (COMPLETE or NO IMPACT)

---

## Coverage Notes

- ADR impact (when a GDD change requires an ADR update or new ADR) follows the
  same complete affected-artifact changeset pattern as story/epic updates — not independently
  fixture-tested.
- TR-registry impact (when changed GDD requires new or updated TR-IDs) is part
  of the analysis phase but not independently fixture-tested.
- The git diff comparison method (detecting what changed in the GDD) is a runtime
  concern — fixtures use pre-arranged content differences.
