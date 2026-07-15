# Gameplay Instructions

## Applies To

All files below `src/gameplay/`.

## Required Practices

- Source all gameplay values from external configuration or data files; document the design document implemented by each feature.
- Use delta time for every time-dependent calculation so behavior is frame-rate independent.
- Communicate with UI through events or signals, define a clear interface for every gameplay system, and keep logic separate from presentation.
- Define state machines with explicit, documented transition tables.
- Write unit tests for all gameplay logic and inject game-state dependencies.

## Forbidden Practices

- Do not hardcode tunable gameplay values.
- Do not directly reference UI implementation types.
- Do not use static singletons for game state; use dependency injection.

## Verification

Run the engine-specific unit tests configured by `$setup-engine`, verify gameplay data files parse, and confirm time-dependent tests cover more than one delta time.
