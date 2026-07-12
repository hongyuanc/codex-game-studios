# Agent Test Spec: [agent-name]

## Codex Runtime Contract

- Runtime profile: `[.codex/agents/name.toml or .codex/agent-packs/engine/name.toml]`
- Required TOML keys: `name`, `description`, `model`, `model_reasoning_effort`, `developer_instructions`
- Model route: **[Sol | Terra | Luna]** (`[gpt-5.6 | gpt-5.6-terra | gpt-5.6-luna]`)
- Behavioral source: the TOML `developer_instructions` value.
- Delegation: direct child custom agents only; maximum delegation depth is 1.
  The child returns scoped evidence and the parent agent synthesizes the result.

## Agent Summary

**Domain owned:** [decisions and artifacts owned]
**Does not own:** [explicit boundaries]
**Escalates to:** [correct parent or user]
**Gate IDs:** [gate IDs or none]

## Static Assertions

- [ ] Runtime TOML exists at the declared path.
- [ ] The five required keys are present and no parallel Markdown profile is assumed.
- [ ] `name`, model ID, model label, and reasoning effort match the runtime TOML.
- [ ] Domain, authority boundary, and escalation path match `developer_instructions`.
- [ ] Any delegation is direct-child only and returns to the parent for synthesis.

## Test Cases

### Case 1: In-Domain Request — [brief name]

**Scenario:** [clearly in-domain request]
**Expected behavior:** [specific output and evidence]
**Assertions:**
- [ ] Handles only the declared domain.
- [ ] Produces the expected structured result.

### Case 2: Out-of-Domain Redirect — [brief name]

**Scenario:** [request owned elsewhere]
**Expected behavior:** [redirect or bounded escalation]
**Assertions:**
- [ ] Does not make the cross-domain decision.
- [ ] Names the correct owner.

### Case 3: Gate Verdict — [brief name]

**Scenario:** [gate fixture and ID]
**Expected behavior:** [exact verdict vocabulary]
**Assertions:**
- [ ] Uses the required gate token and cites evidence.
- [ ] Does not advance on a blocking verdict.

### Case 4: Conflict Escalation — [brief name]

**Scenario:** [conflicting domain decisions]
**Expected behavior:** [correct escalation]
**Assertions:**
- [ ] Surfaces trade-offs without unilateral cross-domain changes.
- [ ] Escalates to the correct parent or user.

### Case 5: Context Pass-Through — [brief name]

**Scenario:** [parent supplies bounded context and task]
**Expected behavior:** [scoped child result]
**Assertions:**
- [ ] Uses supplied context without re-asking the user.
- [ ] Returns evidence to the parent; the parent agent synthesizes the answer.
- [ ] Does not delegate beyond depth 1.

## Protocol Compliance

- [ ] Runtime route and domain boundaries are exact.
- [ ] Changes stay inside an approved changeset.
- [ ] Child work is bounded and parent-synthesized.
- [ ] No commit, publication, destructive operation, or scope expansion is implicit.

## Coverage Notes

[Known gaps or cases requiring a live invocation.]
