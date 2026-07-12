# Agent Roster

The 34 engine-independent profiles live in `.codex/agents/`. Fifteen engine
profiles live in `.codex/agent-packs/{godot,unity,unreal}/`; `$setup-engine`
activates exactly one five-profile pack without touching user-created agents.
When a task spans multiple domains, the coordinating agent (usually `producer`
or the domain lead) delegates bounded work to specialists.

Sol uses `gpt-5.6`, Terra uses `gpt-5.6-terra`, and Luna uses
`gpt-5.6-luna`. Agent TOMLs are authoritative for routing.

## Tier 1 -- Leadership Agents (Sol)
| Agent | Domain | When to Use |
|-------|--------|-------------|
| `creative-director` | High-level vision | Major creative decisions, pillar conflicts, tone/direction |
| `technical-director` | Technical vision | Architecture decisions, tech stack choices, performance strategy |
| `producer` | Production management | Sprint planning, milestone tracking, risk management, coordination |

## Tier 2 -- Department Lead Agents (Terra)
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

## Tier 3 -- Specialist Agents (Terra or Luna)
| Agent | Domain | Model | When to Use |
|-------|--------|-------|-------------|
| `systems-designer` | Systems design | Terra | Specific mechanic implementation, formula design, loops |
| `level-designer` | Level design | Terra | Level layouts, pacing, encounter design, flow |
| `economy-designer` | Economy/balance | Terra | Resource economies, loot tables, progression curves |
| `gameplay-programmer` | Gameplay code | Terra | Feature implementation, gameplay systems code |
| `engine-programmer` | Engine systems | Terra | Core engine, rendering, physics, memory management |
| `ai-programmer` | AI systems | Terra | Behavior trees, pathfinding, NPC logic, state machines |
| `network-programmer` | Networking | Terra | Netcode, replication, lag compensation, matchmaking |
| `tools-programmer` | Dev tools | Terra | Editor extensions, pipeline tools, debug utilities |
| `ui-programmer` | UI implementation | Terra | UI framework, screens, widgets, data binding |
| `technical-artist` | Tech art | Terra | Shaders, VFX, optimization, art pipeline tools |
| `sound-designer` | Sound design | Terra | SFX design docs, audio event lists, mixing notes |
| `writer` | Dialogue/lore | Terra | Dialogue writing, lore entries, item descriptions |
| `world-builder` | World/lore design | Terra | World rules, faction design, history, geography |
| `qa-tester` | Test execution | Luna | Writing test cases, bug reports, test checklists |
| `performance-analyst` | Performance | Terra | Profiling, optimization recs, memory analysis |
| `devops-engineer` | Build/deploy | Terra | CI/CD, build scripts, version control workflow |
| `analytics-engineer` | Telemetry | Terra | Event tracking, dashboards, A/B test design |
| `ux-designer` | UX flows | Terra | User flows, wireframes, accessibility, input handling |
| `prototyper` | Rapid prototyping | Terra | Throwaway prototypes, mechanic testing, feasibility validation |
| `security-engineer` | Security | Terra | Anti-cheat, exploit prevention, save encryption, network security |
| `accessibility-specialist` | Accessibility | Terra | WCAG compliance, colorblind modes, remapping, text scaling |
| `live-ops-designer` | Live operations | Terra | Seasons, events, battle passes, retention, live economy |
| `community-manager` | Community | Luna | Patch notes, player feedback, crisis comms, community health |

## Engine-Specific Agents (only the active pack is available)

### Engine Leads

| Agent | Engine | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `unreal-specialist` | Unreal Engine 5 | Terra | Blueprint vs C++, GAS overview, UE subsystems, Unreal optimization |
| `unity-specialist` | Unity | Terra | MonoBehaviour vs DOTS, Addressables, URP/HDRP, Unity optimization |
| `godot-specialist` | Godot 4 | Terra | GDScript patterns, node/scene architecture, signals, Godot optimization |

### Unreal Engine Sub-Specialists

| Agent | Subsystem | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `ue-gas-specialist` | Gameplay Ability System | Terra | Abilities, gameplay effects, attribute sets, tags, prediction |
| `ue-blueprint-specialist` | Blueprint Architecture | Terra | BP/C++ boundary, graph standards, naming, BP optimization |
| `ue-replication-specialist` | Networking/Replication | Terra | Property replication, RPCs, prediction, relevancy, bandwidth |
| `ue-umg-specialist` | UMG/CommonUI | Terra | Widget hierarchy, data binding, CommonUI input, UI performance |

### Unity Sub-Specialists

| Agent | Subsystem | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `unity-dots-specialist` | DOTS/ECS | Terra | Entity Component System, Jobs, Burst compiler, hybrid renderer |
| `unity-shader-specialist` | Shaders/VFX | Terra | Shader Graph, VFX Graph, URP/HDRP customization, post-processing |
| `unity-addressables-specialist` | Asset Management | Terra | Addressable groups, async loading, memory, content delivery |
| `unity-ui-specialist` | UI Toolkit/UGUI | Terra | UI Toolkit, UXML/USS, UGUI Canvas, data binding, cross-platform input |

### Godot Sub-Specialists

| Agent | Subsystem | Model | When to Use |
| ---- | ---- | ---- | ---- |
| `godot-gdscript-specialist` | GDScript | Terra | Static typing, design patterns, signals, coroutines, GDScript performance |
| `godot-csharp-specialist` | C# / .NET | Terra | .NET patterns, [Signal] delegates, async, nullable types, type-safe node access |
| `godot-shader-specialist` | Shaders/Rendering | Terra | Godot shading language, visual shaders, particles, post-processing |
| `godot-gdextension-specialist` | GDExtension | Terra | C++/Rust bindings, native performance, custom nodes, build systems |
