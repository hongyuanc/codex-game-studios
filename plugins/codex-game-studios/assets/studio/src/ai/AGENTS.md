# AI Instructions

## Applies To

All files below `src/ai/`.

## Required Practices

- Keep the AI update budget at 2ms per frame maximum and profile to verify it.
- Put behavior weights, perception ranges, timers, formation rules, flanking, and role assignments in tunable data files.
- Provide visualization hooks for paths, perception cones, decision trees, and other AI state; log every state-machine transition.
- Make AI telegraph intentions so players have time to read and react.
- Prefer utility or behavior-tree approaches over hard-coded conditional chains.
- Validate every AI input received from the network.

## Forbidden Practices

- Do not hardcode tunable AI parameters or group behavior.
- Do not ship opaque AI without state visualization and transition logging.
- Do not trust network-provided AI input without validation.

## Verification

Profile representative encounters against the 2ms budget, exercise visualization and transition logs, validate data loading, and test hostile network inputs.
