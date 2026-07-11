# Behavioral Spec: `$vertical-slice`

## Purpose

Verify that the vertical-slice workflow builds a production-quality end-to-end
slice only after approved design, architecture, UX, and engine setup are present.

## Preconditions

- A configured engine pack.
- Approved GDD, architecture, and UX artifacts for the slice.
- A bounded feature list and acceptance criteria.

## Required behavior

1. Reject missing upstream artifacts with a clear BLOCKED verdict.
2. Present one complete implementation changeset for approval.
3. Delegate only to direct child agent profiles.
4. Produce automated and manual evidence for the playable loop.
5. End with `PROCEED`, `PIVOT`, or `KILL`; never advance production implicitly.

## Failure cases

- No engine pack is active.
- The requested slice expands beyond the approved feature list.
- Required test or playtest evidence is absent.
- A material architecture conflict remains unresolved.
