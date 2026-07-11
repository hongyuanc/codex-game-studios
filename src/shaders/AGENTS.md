# Shader Instructions

## Applies To

All shader files below `src/shaders/`.

## Required Practices

- Name files `[type]_[category]_[name].[ext]`, use the engine's shader-type prefix, and include authorship and purpose at the top.
- Give uniforms descriptive names and hints, group related parameters, and comment non-obvious calculations.
- Document target platforms, render pipeline, complexity budget, keywords, variants, and total variant count.
- Use appropriate precision, minimize fragment texture samples, provide lower-quality fallback versions, and strip unused variants.
- Use a horizontal then vertical two-pass approach for blur effects.

## Forbidden Practices

- Do not use unexplained magic numbers, texture reads inside loops, or dynamic branching in fragment shaders when `step`, `mix`, or `smoothstep` is suitable.
- Do not mix render pipelines in one directory or create undocumented shader variants.

## Verification

Compile all variants, inspect texture samples and dynamic branching, test minimum-spec target hardware and every supported render pipeline, and verify each fallback and variant budget.
