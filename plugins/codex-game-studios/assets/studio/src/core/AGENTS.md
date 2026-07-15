# Core Engine Instructions

## Applies To

All files below `src/core/`.

## Required Practices

- Maintain ZERO allocations in update, rendering, physics, and other hot paths by pre-allocating, pooling, and reusing resources.
- Make every engine API thread-safe or explicitly document it as single-thread-only.
- Profile before and after every optimization and preserve the measured results.
- Keep dependencies directed from gameplay toward the engine; give every public API a usage example.
- Give public-interface changes a deprecation period and migration guide.
- Use RAII or equivalent deterministic cleanup and design every engine system for graceful degradation.
- Before writing engine API code, consult `docs/engine-reference/` for the configured version and verify the API there.

## Forbidden Practices

- Do not allocate in hot paths or perform avoidable scene/tree queries each frame.
- Do not make core engine code depend on gameplay code.
- Do not optimize without before-and-after measurements or use an unverified engine API.

## Verification

Run the configured engine tests and profiler, verify allocation and timing budgets, and compare every changed engine API with `docs/engine-reference/`.
