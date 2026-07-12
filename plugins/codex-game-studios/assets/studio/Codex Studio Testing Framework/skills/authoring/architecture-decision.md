# Skill Test Spec: $architecture-decision

## Codex Runtime Contract

- Runtime skill: `.agents/skills/architecture-decision/SKILL.md`
- Runtime name: `architecture-decision`
- Runtime trigger description: `Create or revise an Architecture Decision Record for a significant technical choice.`
- Native invocation: `$architecture-decision`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$architecture-decision` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: ACCEPTED, PROPOSED, CONCERNS
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff at the end
- [ ] Documents that TD-ADR is required in every review mode
- [ ] Documents that new ADR status remains Proposed; acceptance is a separate lifecycle decision
- [ ] Mentions engine version stamp from `docs/engine-reference/`

---

## Director Gate Checks

TD-ADR is required in `full`, `phase-gated`, and `solo`. It delegates to the
technical-director after the ADR draft and engine-specialist validation are
complete. Review mode never skips this material architecture gate. This workflow
does not invoke a lead-programmer feasibility gate. A new ADR remains
`Status: Proposed` in every mode; acceptance is a separate lifecycle decision.

---

## Test Cases

### Case 1: Happy Path — New ADR for rendering approach, TD-ADR approves

**Fixture:**
- `docs/architecture/` exists with no existing ADR for rendering
- `docs/engine-reference/[engine]/VERSION.md` exists
- `.codex/studio.toml` contains `full`

**Input:** `$architecture-decision rendering-approach`

**Expected behavior:**
1. Skill guides user through each required section (Status, Context, Decision, Consequences, Alternatives, Related ADRs)
2. Engine version is stamped into the ADR from `docs/engine-reference/`
3. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
4. After all sections and engine validation, TD-ADR runs
5. TD-ADR returns APPROVED
6. ADR Status remains Proposed
7. Skill writes `docs/architecture/adr-NNN-rendering-approach.md`
8. `docs/architecture/tr-registry.yaml` updated if new TR-IDs are defined

**Assertions:**
- [ ] All 6 required sections are authored and written
- [ ] Engine version reference is stamped in the ADR
- [ ] TD-ADR runs in full mode
- [ ] ADR Status remains Proposed after TD-ADR approval
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] File is written to `docs/architecture/adr-NNN-[name].md`

---

### Case 2: Failure Path — TD-ADR returns CONCERNS

**Fixture:**
- ADR draft is complete (all sections filled)
- `.codex/studio.toml` contains `full`
- TD-ADR gate returns CONCERNS: "The decision does not address [specific concern]"

**Input:** `$architecture-decision [topic]`

**Expected behavior:**
1. TD-ADR gate spawns and returns CONCERNS with specific feedback
2. Skill surfaces the concerns to the user
3. ADR Status remains Proposed (not Accepted)
4. User is asked: revise the decision to address concerns, or accept as Proposed
5. ADR is written with Status: Proposed if concerns are not resolved

**Assertions:**
- [ ] TD-ADR concerns are shown to the user verbatim
- [ ] ADR Status is Proposed (not Accepted) when TD-ADR returns CONCERNS
- [ ] Skill does NOT set Status: Accepted while CONCERNS are unresolved
- [ ] User is given the option to revise and re-run the gate

---

### Case 3: Phase-gated Mode — Required TD-ADR runs; ADR written as Proposed

**Fixture:**
- `.codex/studio.toml` contains `phase-gated`
- ADR draft is authored for a new technical decision

**Input:** `$architecture-decision [topic]`

**Expected behavior:**
1. Skill guides user through all 6 sections
2. After draft and engine validation are complete, TD-ADR runs
3. The technical-director returns an evidence-backed verdict
4. ADR is written with Status: Proposed
5. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.

**Assertions:**
- [ ] TD-ADR runs in phase-gated mode
- [ ] ADR Status is Proposed in phase-gated mode
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Skill writes the ADR after user approval

---

### Case 4: Edge Case — ADR already exists for this topic

**Fixture:**
- `docs/architecture/` contains an existing ADR covering the same topic
- The existing ADR has Status: Accepted

**Input:** `$architecture-decision [same-topic]`

**Expected behavior:**
1. Skill detects an existing ADR covering the same topic
2. Skill asks: "An ADR for [topic] already exists ([filename]). Update it, or create a new superseding ADR?"
3. User selects update or supersede
4. Skill does NOT silently create a duplicate ADR

**Assertions:**
- [ ] Skill detects the existing ADR before authoring begins
- [ ] User is offered update or supersede options — no silent duplicate
- [ ] If update: skill opens the existing ADR for section-by-section revision
- [ ] If supersede: new ADR references the superseded one in Related ADRs section

---

### Case 5: Director Gate — TD-ADR runs in every mode; new status stays Proposed

**Fixture:**
- ADR draft is complete
- Three scenarios: full, phase-gated, and solo

**Full mode, TD-ADR APPROVED:**
- ADR Status remains Proposed

**Assertions (both approved):**
- [ ] ADR frontmatter/header shows `Status: Proposed`
- [ ] TD-ADR appears as APPROVED in output

**Any mode, TD-ADR returns CONCERNS:**
- ADR Status stays Proposed

**Assertions (CONCERNS):**
- [ ] ADR frontmatter/header shows `Status: Proposed`
- [ ] Concerns are listed in output
- [ ] Skill does NOT set Status: Accepted when any gate returns CONCERNS

**Phase-gated/solo mode:**
- TD-ADR still runs and ADR Status remains Proposed

**Assertions (phase-gated/solo):**
- [ ] ADR Status is Proposed in phase-gated mode
- [ ] ADR Status is Proposed in solo mode
- [ ] TD-ADR output appears in phase-gated and solo mode

---

## Protocol Compliance

- [ ] All 6 required sections authored before gate review
- [ ] Engine version stamped in ADR from `docs/engine-reference/`
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] TD-ADR runs in full, phase-gated, and solo modes
- [ ] No lead-programmer feasibility gate is part of this workflow
- [ ] New ADR Status remains Proposed regardless of review mode
- [ ] Ends with next-step handoff: `$architecture-review` or `$create-control-manifest`

---

## Coverage Notes

- ADR numbering (auto-incrementing NNN) is not independently fixture-tested —
  the skill reads existing ADR filenames to assign the next number.
- Related ADRs section linking (supersedes / related-to) is tested structurally
  via Case 4 but not all link types are individually verified.
- The TR-registry update (when new TR-IDs are defined in the ADR) is part of the
  write phase — tested implicitly via Case 1.
