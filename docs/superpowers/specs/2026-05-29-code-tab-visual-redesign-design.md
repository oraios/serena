# Code Tab Visual Redesign — Design

**Date:** 2026-05-29
**Branch:** `dashboard_v2`
**Scope:** `dashboard/src/components/code/*` + lucide icon migration across the dashboard
**Backend:** No changes. `/code/*` HTTP API stays frozen.

## Goals

1. Make the **Symbols (file)** view visually scannable: kind-icons + tree grouping replace the flat 3-column CSV-style table.
2. **Hide the Diagnostics panel** behind a third middle-pane tab; recover ~320px of horizontal space when not in use.
3. Persistently warn that diagnostics is slow, so users opt in deliberately.
4. Replace ad-hoc Unicode/emoji affordances across the dashboard with **lucide icons** for a coherent visual language.

## Non-Goals

- Backend changes. `/code/list_dir`, `/code/file_symbols`, `/code/workspace_symbol_search`, `/code/diagnostics_summary` are unchanged.
- File-content viewer / syntax highlighting. Symbols outline only.
- New diagnostics-streaming protocol. Refresh stays manual.
- Auto-refreshing diagnostics when files change.

---

## Foundation

### Dependency

Add `@lucide/svelte` (^1.17.0, official Svelte 5 package — `lucide-svelte` is the legacy Svelte 3/4 name) to `dashboard/package.json`. Tree-shakable per-icon imports honor `currentColor`, so all icons inherit our CSS tokens.

### Icon component wrapper

New `src/components/common/Icon.svelte`:

- Standardizes `size` (default `16`), `stroke-width` (default `1.75` — heavier than Lucide's `2` default reads cleaner at 16px against our background tokens), and `aria-hidden`/`aria-label` ergonomics.
- Consumers may either pass a lucide component via slot to `Icon.svelte`, or import lucide directly when local sizing is needed (e.g., 14px inside a chip). The wrapper exists to set sensible defaults, not as a forced indirection.

### Code-tab layout

`CodePage.svelte` grid changes from `260px 1fr 320px` → `260px 1fr`. The right `.diagnostics` column is removed. The middle pane's tab nav gains a third tab.

### Store change

`code.middle_pane` type widens from `'symbols' | 'search'` to `'symbols' | 'search' | 'diagnostics'`. One-line change in `src/lib/stores/code.svelte.ts`.

---

## Symbols (file) view redesign

Tree-grouped, indented outline with colored kind-icons. No per-row borders. Hierarchy comes from indentation + a subtle indent-guide line (`box-shadow: inset 1px 0` per depth level).

### Header bar (sticky at top of the pane)

- **Breadcrumb:** `src › services › context_analysis_service.py`. Path segments are clickable to navigate the tree (`code.expanded` toggle + scroll into view); final filename is bold and not clickable.
- **Counts row:** e.g. `2 classes · 18 methods · 7 variables`. Shows every kind present in the current file, in the fixed order Class → Interface → Enum → Function → Method → Property → Field → Variable → Constant → Module → other. Pluralized via a tiny `pluralizeKind(kind, count)` helper in `symbolTree.ts`. Derived via `countByKind(symbols)`.
- **Right-aligned controls:** filter input (with `Search` prefix icon), expand-all (`ChevronsDown`) and collapse-all (`ChevronsUp`) icon buttons.

### Filter input

- Debounced 100ms.
- Pure-substring case-insensitive match against symbol name. No fuzzy library — `name.toLowerCase().includes(query.toLowerCase())` is sufficient for outline filtering at typical file sizes (≤1k symbols).
- When filter is non-empty: matching rows stay; **parents of matches** stay (with non-matching siblings hidden); non-matching branches collapse.

### Row anatomy

```
[16px kind icon]  Name              28:1
```

- **Kind icon:** lucide icon in a kind-colored container (18×18, 6px rounded square, kind color at 18% alpha background + 100% alpha foreground stroke).
- **Name:** monospace, normal weight. Selected row gets `--bg` background + left accent bar.
- **Line:col:** muted, tabular-nums, `cursor: pointer`. Click copies `path:line` to clipboard with a 1-second `Check` icon swap and the row label flashing "copied". Tooltip: "Copy path:line".

### Kind icon palette (lucide → token)

| Kind | Icon | Color token |
| --- | --- | --- |
| Class | `Box` | `--chart-6` (gold) |
| Method | `Diamond` | `--chart-5` (purple) |
| Function | `Sigma` | `--chart-2` (blue) |
| Variable | `Variable` | `--chart-3` (green) |
| Field | `Hash` | `--chart-4` (rose) |
| Property | `Tag` | `--accent` (orange) |
| Interface | `Braces` | `--chart-2` |
| Enum | `List` | `--chart-3` |
| Constant | `Lock` | `--accent` |
| Module | `Package` | `--text-muted` |
| _fallback_ | `Code2` | `--text-muted` |

Palette mirrors VS Code outline conventions but maps to our existing chart tokens for theme cohesion (light + dark).

### Sticky parent header

When the user scrolls past a class/function start, the parent's name row pins to the top of the list (just below the header bar) via pure CSS `position: sticky; top: 0` on the parent-row's name container. No `IntersectionObserver` needed.

### Expand state

Per-file `Set<string>` (key = `name:line`) on the store, alongside the existing `file_symbols` cache. New store actions: `expandAll(path)`, `collapseAll(path)`, `toggleExpand(path, key)`. **Default:** expand-all (matches the current flat-list "you see everything" behavior).

### Pure helpers — `src/lib/symbolTree.ts`

- `countByKind(symbols: FileSymbol[]): Record<string, number>` — for the counts row.
- `filterTree(symbols: FileSymbol[], query: string): FileSymbol[]` — prunes non-matching branches; preserves parents of matches.
- `flattenForDisplay(symbols: FileSymbol[], expanded: Set<string>, filter: string): DisplayRow[]` — flat array of `{ symbol, depth, hasChildren, isExpanded, key }` for the rendered list. Keeps the component template trivial.

Unit-tested independently; the component imports these and renders the flat array.

---

## Diagnostics tab

### Placement

`DiagnosticsPanel.svelte` moves into the middle pane as the third tab. Tab label: `Diagnostics (project)`. When `code.diag_files.length > 0`, the tab shows a muted count badge (e.g., `Diagnostics (project) · 12`).

### Persistent slow-warning banner

Always visible at the top of the tab (not gated by `diag_loading`):

> ⚠ Computing diagnostics is slow and temporarily delays other LSP tools. Use only when needed.

`TriangleAlert` lucide icon, accent-toned `border-left`, muted body text. Independent from the existing "Computing diagnostics…" spinner banner, which keeps showing during in-flight refresh.

### Severity filter chips

Above the file list, below the slow-warning:

```
[Errors (12)]  [Warnings (34)]  [Info (5)]  [Hints (0)]
```

Each chip is a toggle with its severity icon (`CircleAlert` / `TriangleAlert` / `Info` / `Lightbulb`) and color. Multi-select. Stored as `code.diag_severity_filter: Set<DiagnosticSeverity>`. Convention: **empty set means show all** (so a fresh load is not blank). Counts come from a new derived `code.diag_counts` getter.

### Refresh button

Icon button: `RotateCw` (spinning when `diag_loading`) + text label. Top-right of the pane, replaces the existing `↻ Refresh` text button.

---

## Global drive-by icon migrations (full sweep)

Pure visual swaps — no behavior changes. Done in a separate commit inside the same PR for review hygiene.

| File | Replace | With (lucide) |
| --- | --- | --- |
| `ThemeToggle.svelte` | `☀` / `🌙` emoji | `Sun` / `Moon` |
| `Header.svelte` | `⏻` | `Server` |
| `FileTree.svelte` | `▾` / `▸`, `⚠` | `ChevronDown` / `ChevronRight`, `TriangleAlert` |
| `Timeline.svelte` | `▶` / `⏸`, `↻`, `✓` / `✗` | `Play` / `Pause`, `RotateCw`, `CheckCircle` / `XCircle` |
| `TimelineRow.svelte` | `▾` / `▸`, `×` | `ChevronDown` / `ChevronRight`, `X` |
| `Combobox.svelte` | `▾` | `ChevronDown` |
| `FilterDropdown.svelte` | `▾`, `×`, `✓` | `ChevronDown`, `X`, `Check` |
| `Collapsible.svelte` | `▼` | `ChevronDown` |
| `LogToolbar.svelte` | text "copied" + nothing | `Copy` / `Check` |
| `EditMemoryModal.svelte` | `✎`, `✓` | `Pencil`, `Check` |
| `ConfigCard.svelte` | `×` | `X` |
| `DrillDownPanel.svelte` | `×`, `→` | `X`, `ArrowRight` |
| `WorkspaceSearch.svelte` (Code tab) | _no icon today_ | `Search` prefix |

---

## Component boundaries (after redesign)

```
CodePage.svelte                     — 2-col grid + tab nav
├── FileTree.svelte                 — chevron + warning icons swapped to lucide
└── middle pane:
    ├── FileSymbols.svelte          — uses symbolTree helpers; renders header + rows
    │   ├── (snippet) symbol row    — icon badge + name + line:col
    │   └── (snippet) header bar    — breadcrumb + counts + filter + expand/collapse-all
    ├── WorkspaceSearch.svelte      — Search prefix icon added
    └── DiagnosticsPanel.svelte     — slow-warning banner + severity chips + file list
```

Each unit:

- **FileSymbols.svelte** — props in (none; reads `code` store), events out (`code.selectPath`, `code.toggleExpand`, etc.). Renders only — all logic lives in `symbolTree.ts` helpers or the store.
- **symbolTree.ts** — pure functions, no Svelte deps. Imports `FileSymbol` from `$lib/api/types`. Unit-tested.
- **Icon.svelte** — pure presentational. Sets default size/stroke-width and a11y attrs.

## Data flow

Unchanged from current Phase 6 design:

```
user clicks file in FileTree
  → code.selectPath(path)
  → code.loadFileSymbols(path) (cached)
  → FileSymbols re-derives via $derived
```

New: filter input + expand state are local to the symbols view but persisted on the store keyed by `path`, so switching files and back preserves them.

## Error handling

Unchanged. Existing `error-card` pattern in each pane stays. The slow-warning is **informational**, not an error.

- `FileSymbols` — show `error-card` with `Retry` button when `code.file_symbol_errors[path]` is set.
- `WorkspaceSearch` — existing `error-banner`.
- `DiagnosticsPanel` — existing `error-card` for `code.diag_error`.

## Testing

| Layer | Test | Notes |
| --- | --- | --- |
| `symbolTree.ts` | unit | filter/count/flatten edge cases: empty tree, no matches, deep nesting, all-collapsed |
| `FileSymbols.svelte` | render + interaction | renders kind icons; filter prunes branches; expand-all/collapse-all work; click `line:col` copies `path:line` (stub `navigator.clipboard`) and flashes confirmation |
| `DiagnosticsPanel.svelte` | render + interaction | persistent slow-warning visible without loading; severity chips toggle; counts match; tab badge appears when files > 0 |
| `CodePage.svelte` | render | three tabs switch panes; right column is gone |
| `pollers.ts` | existing tests | no change expected; `pollersForView` is layout-agnostic |
| Drive-by icon swaps | existing component tests | each existing test asserting on icon character should be updated to assert on a more stable selector (button role + aria-label) |

## Migration steps (for the implementation plan)

1. Install `@lucide/svelte`, add `Icon.svelte`.
2. Migrate `FileTree.svelte` chevrons + warning (smallest, isolated change — proves the icon pipeline).
3. Add `symbolTree.ts` + tests.
4. Rebuild `FileSymbols.svelte` against the new helpers; add the header bar; add icon badges + sticky parent + copy-to-clipboard.
5. Migrate `WorkspaceSearch.svelte` Search prefix icon.
6. Move `DiagnosticsPanel.svelte` into the third middle tab; add slow-warning banner + severity chips; refactor refresh button.
7. Update `CodePage.svelte` layout to 2-col grid.
8. Update `code.svelte.ts` types + `diag_severity_filter`, `diag_counts` getter, expand actions.
9. Drive-by icon sweep across non-Code components.
10. `npm run format`, `npm run check`, `npm test`, `npm run build`, commit regenerated `../src/serena/resources/dashboard/` per build-output contract.

## Risks

- **Bundle size:** lucide is tree-shaken per-icon (~1KB each). With ~25 icons total across the sweep, ~25KB pre-gzip — acceptable.
- **Drive-by sweep churn:** broad diff. Mitigated by isolating it to its own commit so the Code-tab redesign and the icon migration can be reviewed separately.
- **Stickiness on parent rows:** depends on the row staying within the scroll container. If a future refactor wraps rows in a different overflow context, stickiness will silently break. Add a render test that asserts `position: sticky` on the parent row.
- **Theme coverage:** kind-color palette must look correct in both light and dark. Verified against existing `--chart-*` tokens, which already ship both themes.
