# Agent Roster

The 34 engine-independent profiles live in `.codex/agents/`. Fifteen engine
profiles live in `.codex/agent-packs/{godot,unity,unreal}/`; `$setup-engine`
activates exactly one five-profile pack without touching user-created agents.
When a task spans multiple domains, the coordinating agent (usually `producer`
or the domain lead) delegates bounded work to specialists.

Sol uses `gpt-5.6`, Sol 6.1 uses `gpt-6.1-sol`, and Luna uses
`gpt-5.6-luna`. Agent TOMLs are authoritative for routing.

## Tier 1 -- Leadership Agents (Sol)
| Agent | Domain | When to Use |
|-------|--------|-------------|
| `creative-director` | High-level vision | Major creative decisions, pillar conflicts, tone/direction |
| `technical-director` | Technical vision | Architecture decisions, tech stack choices, performance strategy |
| `producer` | Production management | Sprint planning, milestone tracking, risk management, coordination |

## Tier 2 -- Department Lead Agents (Sol 6.1)
| Agent | Domain | When to Use |
|-------|--------|-------------|
| `game-designer` | Game design | Mechanics, systems, progression, economy, balancing |
| `lead-programmer` | Code architecture | System design, code review, API design, refactoring |
| `art-director` | Visual direction | Style guides, art bible, asset standards, UI/UX direction |
| `audio-director` | Audio direction | Music direction, sound palette, audio implementation strategy |
| `narrative-director` | Story and writing | Story arcs, world-building, character design, dialogue strategy |
| `qa-lead` | Quality assurance | Test strategy, bug triage, release readiness, regression planning |
| `release-manager` | Release pipeline | Build management, versioning, changelogs, deployment, rollbacks |
| `localization-lead` | Internationalization | String externalization, translation pipeline, locale testing |

## Tier 3 -- Specialist Agents (Sol 6.1 or Luna)
| Agent | Domain | Model | When to Use |
|-------|--------|-------|-------------|
| `systems-designer` | Systems design | Sol 6.1 | Specific mechanic implementation, formula design, loops |
| `level-designer` | Level design | Sol 6.1 | Level layouts, pacing, encounter design, flow |
| `economy-designer` | Economy/balance | Sol 6.1 | Resource economies, loot tables, progression curves |
| `gameplay-programmer` | Gameplay code | Sol 6.1 | Feature implementation, gameplay systems code |
| `engine-programmer` | Engine systems | Sol 6.1 | Core engine, rendering, physics, memory management |
| `ai-programmer` | AI systems | Sol 6.1 | Behavior trees, pathfinding, NPC logic, state machines |
| `network-programmer` | Networking | Sol 6.1 | Netcode, replication, lag compensation, matchmaking |
| `tools-programmer` | Dev tools | Sol 6.1 | Editor extensions, pipeline tools, debug utilities |
| `ui-programmer` | UI implementation | Sol 6.1 | UI framework, screens, widgets, data binding |
| `technical-artist` | Tech art | Sol 6.1 | Shaders, VFX, optimization, art pipeline tools |
| `sound-designer` | Sound design | Sol 6.1 | SFX design docs, audio event lists, mixing notes |
| `writer` | Dialogue/lore | Sol 6.1 | Dialogue writing, lore entries, item descriptions |
| `world-builder` | World/lore design | Sol 6.1 | World rules, faction design, history, geography |
| `qa-tester` | Test execution | Luna | Writing test cases, bug reports, test checklists |
| `performance-analyst` | Performance | Sol 6.1 | Profiling, optimization recs, memory analysis |
| `devops-engineer` | Build/deploy | Sol 6.1 | CI/CD, build scripts, version control workflow |
| `analytics-engineer` | Telemetry | Sol 6.1 | Event tracking, dashboards, A/B test design |
| `ux-designer` | UX flows | Sol 6.1 | User flows, wireframes, accessibility, input handling |
| `prototyper` | Rapid prototyping | Sol 6.1 | Throwaway prototypes, mechanic testing, feasibility validation |
| `security-engineer` | Security | Sol 6.1 | Anti-cheat, exploit prevention, save encryption, network security |
| `accessibility-specialist` | Accessibility | Sol 6.1 | WCAG compliance, colorblind modes, remapping, text scaling |
| `live-ops-designer` | Live operations | Sol 6.1 | Seasons, events, battle passes, retention, live economy |
| `community-manager` | Community | Luna | Patch notes, player feedback, crisis comms, community health |

## Engine-Specific Agents (only the active pack is available)

### Engine Leads

| Agent | Engine | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `unreal-specialist` | Unreal Engine 5 | Sol 6.1 | Blueprint vs C++, GAS overview, UE subsystems, Unreal optimization |
| `unity-specialist` | Unity | Sol 6.1 | MonoBehaviour vs DOTS, Addressables, URP/HDRP, Unity optimization |
| `godot-specialist` | Godot 4 | Sol 6.1 | GDScript patterns, node/scene architecture, signals, Godot optimization |

### Unreal Engine Sub-Specialists

| Agent | Subsystem | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `ue-gas-specialist` | Gameplay Ability System | Sol 6.1 | Abilities, gameplay effects, attribute sets, tags, prediction |
| `ue-blueprint-specialist` | Blueprint Architecture | Sol 6.1 | BP/C++ boundary, graph standards, naming, BP optimization |
| `ue-replication-specialist` | Networking/Replication | Sol 6.1 | Property replication, RPCs, prediction, relevancy, bandwidth |
| `ue-umg-specialist` | UMG/CommonUI | Sol 6.1 | Widget hierarchy, data binding, CommonUI input, UI performance |

### Unity Sub-Specialists

| Agent | Subsystem | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `unity-dots-specialist` | DOTS/ECS | Sol 6.1 | Entity Component System, Jobs, Burst compiler, hybrid renderer |
| `unity-shader-specialist` | Shaders/VFX | Sol 6.1 | Shader Graph, VFX Graph, URP/HDRP customization, post-processing |
| `unity-addressables-specialist` | Asset Management | Sol 6.1 | Addressable groups, async loading, memory, content delivery |
| `unity-ui-specialist` | UI Toolkit/UGUI | Sol 6.1 | UI Toolkit, UXML/USS, UGUI Canvas, data binding, cross-platform input |

### Godot Sub-Specialists

| Agent | Subsystem | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `godot-gdscript-specialist` | GDScript | Sol 6.1 | Static typing, design patterns, signals, coroutines, GDScript performance |
| `godot-csharp-specialist` | C# / .NET | Sol 6.1 | .NET patterns, [Signal] delegates, async, nullable types, type-safe node access |
| `godot-shader-specialist` | Shaders/Rendering | Sol 6.1 | Godot shading language, visual shaders, particles, post-processing |
| `godot-gdextension-specialist` | GDExtension | Sol 6.1 | C++/Rust bindings, native performance, custom nodes, build systems |
