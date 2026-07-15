# Prototype Instructions

## Applies To

All files below `prototypes/`.

## Required Practices

- Keep each prototype in `prototypes/[name]/` with a `README.md` documenting the hypothesis, how to run it, status, and findings.
- Optimize for learning: hardcoded values, minimal documentation, simple architecture, global state, duplicated code, debug output, placeholders, and quick solutions are allowed here.
- When a prototype succeeds, use its findings to inform production design and rewrite the feature to production standards.
- Preserve a concluded prototype for reference only while it remains useful; archive or delete it after findings are captured.

## Forbidden Practices

- Production code must not import or reference prototype code.
- Prototypes must not modify files outside `prototypes/` and must not be deployed or shipped.
- Do not migrate prototype code directly into production or grow it into production through incremental cleanup; production code must be rewritten.

## Verification

Confirm the prototype is self-contained, its `README.md` covers hypothesis/run/status/findings, no production references point into it, and build or release manifests exclude it.
