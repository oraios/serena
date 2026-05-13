# Memory Maintenance

## Discovery Model

- Agents start with the full memory name list and should read `mem:core` first as the routing entry point.
- All other memory discovery comes from memory names plus routing already read.
- Routing is useful only before the target memory is selected. Once a memory is open, target-selection text inside it can no longer help decide to read it.
- Therefore, never put self-referential selection cues in a memory body: no "Start here", "Use when", "Use before", "Use after", or "read this when..." openers.
  Such self-referential cues are an error mode: they are unreachable for selection, duplicate routing that belongs upstream, and drift independently from the actual routing graph.
- Add routing only when names are insufficient, ambiguous, or a non-obvious dependency/order matters. Do not add tautological routing such as "frontend debugging -> frontend/debugging".
- Routing can live outside core memories when needed, but core memories own most module-level routing because they are read before focused memories in that subfolder.
- Top-level/startup memory is `mem:core`; top-level memory in each memory subfolder is `<folder>/core` (for example `mem:frontend/core`).
- Memory references must use a mem: prefix inside backticks, e.g. `mem:frontend/core`.
- Do not add an index that simply re-lists the focused-memory names, the memory name list is already visible. 
  Only add routing pointers when a target memory's name is not self-explanatory or when a some aspect should be routed to multiple memories.

## Style

Dense agent notes, not prose docs. Prefer invariants, paths, commands, terse bullets. Avoid obvious context, rationale, and examples unless they prevent likely mistakes. Keep guidance durable and generalizable, not task-local.

## Add/update threshold

Add or update memory only for stable, non-obvious project conventions that avoid complex rediscovery.

Do not add: quick-read/rg facts; generic language/framework knowledge; one-off task notes; volatile line-level details; behavior likely to change soon.

Operational constants (commands, paths, version pins): phrase as current behavior; before changing the value, update it in the owning memory and run `serena memories check` to catch references that need updating.

## Graph Ownership

- Project-level routing: `mem:core`.
- Module-level routing/source maps: module core memories.
- Focused memories: topic details only; assume relevant routing was read before selection.

## Maintenance Actions

- Renamed/removed/split/merged/superseded memory: update all references. Done automatically if handled via Serena's memory rename tool.
- Stale paths/namespaces/commands/behavior: update or remove in owning memory. If working with Serena, call `serena memories check` for a report.
- Split catch-all memory when sections are commonly needed independently or agents must read unrelated domains to reach needed topic.
- Retire/delete memory when owning module/subsystem is removed or replaced; remove all references.
- Added/renamed/split/moved/deleted memory: update affected routing only where names are insufficient.
- Before finishing: list memories for old names and key new names to catch stale/missing references.