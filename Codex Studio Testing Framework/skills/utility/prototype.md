# Skill Test Spec: $prototype

## Codex Runtime Contract

- Runtime skill: `.agents/skills/prototype/SKILL.md`
- Runtime name: `prototype`
- Runtime trigger description: `Build and evaluate a throwaway concept prototype before committing to full system design.`
- Native invocation: `$prototype`
- Discovery contract: only `name` and `description` are required in YAML frontmatter; invocation arguments and permissions belong in the workflow body or runtime policy.
- Structured decisions: when `request_user_input` is appropriate, each call contains 1–3 questions and each question contains 2–3 options. Ask one decision per turn; sequence unrelated decisions across turns.
- Custom-agent delegation: delegate only to a direct child custom agent. The maximum delegation depth is 1. Each child returns scoped findings and evidence, and the parent agent synthesizes the final result and owns user interaction.
- Methodology: retain five cases covering the happy path, a blocked/failure path, a mode or boundary variant, an edge case, and delegation/gate behavior.

---


## Skill Summary

`$prototype` is tested against the exact runtime discovery contract above. The five
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
- [ ] Contains verdict keywords: PROTOTYPE COMPLETE, PROTOTYPE ABANDONED
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Has a next-step handoff (e.g., `$design-system` to formalize, or archive)

---

## Director Gate Checks

None. Prototypes are throwaway validation artifacts. No director gates apply.

---

## Test Cases

### Case 1: Happy Path — Mechanic concept prototyped, findings documented

**Fixture:**
- `prototypes/` directory exists
- No existing prototype for "grapple-hook"

**Input:** `$prototype grapple-hook`

**Expected behavior:**
1. The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
2. After approval: creates `prototypes/grapple-hook/` directory and basic
   implementation skeleton (main scene, player controller extension)
3. Skill implements a minimal grapple hook mechanic (intentionally rough — no
   polish, hardcoded values acceptable)
4. Skill produces `prototypes/grapple-hook/findings.md` with:
   - What was tested
   - What worked
   - What didn't work
   - Recommendation (proceed / abandon / revise concept)
5. Verdict is PROTOTYPE COMPLETE

**Assertions:**
- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Implementation is isolated to `prototypes/` (not `src/`)
- [ ] `findings.md` is created with at minimum: tested/worked/didn't-work/recommendation
- [ ] Verdict is PROTOTYPE COMPLETE

---

### Case 2: Prototype Already Exists — Offers Extend, Replace, or Archive

**Fixture:**
- `prototypes/grapple-hook/` already exists from a previous prototype session
- It contains a basic implementation and a findings.md

**Input:** `$prototype grapple-hook`

**Expected behavior:**
1. Skill detects existing `prototypes/grapple-hook/` directory
2. Skill reports: "Prototype already exists for grapple-hook"
3. Skill presents 3 options:
   - Extend: add new features to the existing prototype
   - The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write.
   - Archive: move to `prototypes/archive/grapple-hook/` and start fresh
4. User selects; skill proceeds accordingly

**Assertions:**
- [ ] Existing prototype is detected and reported
- [ ] Exactly 3 options are presented (extend, replace, archive)
- [ ] The parent asks one explicit completion decision in its own turn
- [ ] Archive path moves (not deletes) the existing prototype

---

### Case 3: Prototype Validates Mechanic — Recommends Proceeding to Production

**Fixture:**
- Prototype implementation complete
- Findings: grapple hook mechanic is fun and technically feasible

**Input:** `$prototype grapple-hook` (prototype session complete)

**Expected behavior:**
1. After prototype is built and tested, findings are summarized
2. Recommendation in findings.md: "Mechanic validated — recommend proceeding
   to `$design-system` for full specification"
3. Skill handoff message explicitly suggests `$design-system grapple-hook`
4. Verdict is PROTOTYPE COMPLETE

**Assertions:**
- [ ] `findings.md` contains an explicit recommendation
- [ ] Recommendation references `$design-system` when mechanic is validated
- [ ] Handoff message echoes the recommendation
- [ ] Verdict is PROTOTYPE COMPLETE (not PROTOTYPE ABANDONED)

---

### Case 4: Prototype Reveals Mechanic is Unworkable — PROTOTYPE ABANDONED

**Fixture:**
- Prototype implemented for "procedural-dialogue"
- After testing: the mechanic creates incoherent dialogue trees and is
  frustrating to play

**Input:** `$prototype procedural-dialogue`

**Expected behavior:**
1. Prototype is built
2. Findings document the failure: incoherent output, player confusion, technical complexity
3. Recommendation in findings.md: "Mechanic not viable — abandoning"
4. `findings.md` documents the specific reasons the mechanic failed
5. Skill suggests alternatives in the handoff (e.g., curated dialogue instead)
6. Verdict is PROTOTYPE ABANDONED

**Assertions:**
- [ ] Verdict is PROTOTYPE ABANDONED (not PROTOTYPE COMPLETE)
- [ ] `findings.md` documents specific failure reasons (not vague)
- [ ] Alternative approaches are suggested in the handoff
- [ ] Prototype files are retained (not deleted) for reference

---

### Case 5: Director Gate Check — No gate; prototypes are validation artifacts

**Fixture:**
- Mechanic concept provided

**Input:** `$prototype wall-jump`

**Expected behavior:**
1. Skill creates and documents the prototype
2. No director agents are spawned
3. No gate IDs appear in output

**Assertions:**
- [ ] No director gate is invoked
- [ ] No gate skip messages appear
- [ ] Verdict is PROTOTYPE COMPLETE or PROTOTYPE ABANDONED — no gate verdict

---

## Protocol Compliance

- [ ] The parent presents one complete proposed changeset containing every target path and material edit, then obtains approval before any write
- [ ] Creates all files under `prototypes/` (not `src/`)
- [ ] Produces `findings.md` with tested/worked/didn't-work/recommendation
- [ ] Notes that production coding standards are intentionally relaxed
- [ ] Offers extend/replace/archive when prototype already exists
- [ ] Verdict is PROTOTYPE COMPLETE or PROTOTYPE ABANDONED

---

## Coverage Notes

- Prototype implementation quality (code style) is intentionally not tested —
  prototypes are throwaway artifacts and quality standards do not apply.
- The archiving mechanism is mentioned in Case 2 but the archive format is
  not assertion-tested in detail.
- Engine-specific prototype scaffolding (GDScript scenes vs. C# MonoBehaviour)
  follows the same flow with engine-appropriate file types.
