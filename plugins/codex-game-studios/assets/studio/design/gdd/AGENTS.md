# Game Design Document Instructions

## Applies To

All files below `design/gdd/`.

## Required Practices

- Include all eight sections: Overview, Player Fantasy, Detailed Rules, Formulas, Edge Cases, Dependencies, Tuning Knobs, and Acceptance Criteria.
- Define formula variables, expected ranges, and example calculations.
- State explicit Edge Cases outcomes and bidirectional Dependencies.
- Give each Tuning Knob a safe range and gameplay effect; link every balance value to its formula or rationale.
- Make Acceptance Criteria objectively testable by QA.
- Write incrementally: create the skeleton, then complete one section at a time with user approval between sections and persist each approved section immediately.

## Forbidden Practices

- Do not use hand-waving requirements such as "should feel good."
- Do not omit required sections, leave edge-case behavior implicit, or define one-way dependencies.
- Do not batch unapproved sections into a design document.

## Verification

Run `$design-review`, confirm all eight sections and bidirectional links, recalculate formulas and ranges, and verify the recorded user approval for each completed section.
