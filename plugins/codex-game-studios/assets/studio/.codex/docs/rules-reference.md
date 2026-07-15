# Path-Specific Rules

Nested `AGENTS.md` files provide path-scoped instructions. The closest file in
the directory hierarchy governs work in that subtree.

| Rule File | Path Pattern | Enforces |
| ---- | ---- | ---- |
| `src/gameplay/AGENTS.md` | `src/gameplay/**` | Data-driven values, delta time, no UI references |
| `src/core/AGENTS.md` | `src/core/**` | Zero allocations in hot paths, thread safety, API stability |
| `src/ai/AGENTS.md` | `src/ai/**` | Performance budgets, debuggability, data-driven parameters |
| `src/networking/AGENTS.md` | `src/networking/**` | Server authority, versioned messages, security |
| `src/ui/AGENTS.md` | `src/ui/**` | No game-state ownership, localization readiness, accessibility |
| `design/gdd/AGENTS.md` | `design/gdd/**` | Required sections, formula format, edge cases |
| `design/narrative/AGENTS.md` | `design/narrative/**` | Lore consistency, character voice, canon levels |
| `assets/data/AGENTS.md` | `assets/data/**` | Data validity, naming conventions, schema rules |
| `tests/AGENTS.md` | `tests/**` | Test naming, coverage requirements, fixture patterns |
| `prototypes/AGENTS.md` | `prototypes/**` | Relaxed standards, README, documented hypothesis |
| `assets/shaders/AGENTS.md` | `assets/shaders/**` | Naming, performance targets, cross-platform rules |
