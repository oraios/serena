# Dashboard charting: frappe-charts → Chart.js

**Date:** 2026-05-28
**Branch:** `dashboard_v2`
**Status:** Approved design, ready for implementation plan

## Summary

Replace the dashboard Stats page's charting library, **frappe-charts**, with
**Chart.js** (the library `main` uses), restoring structural parity with the
pre-rewrite dashboard while keeping the v2 Svelte architecture and design
language intact.

The swap is contained: only `ChartPanel.svelte`, `charts.ts`, the
`frappe-charts` type shim, and `StatsPage.svelte` touch charting today, and the
project rule "Charts go **only** through `ChartPanel.svelte`" is preserved.

## Motivation

- **Library parity with `main`.** `main` renders the Stats page with Chart.js +
  `chartjs-plugin-datalabels`; the v2 rewrite diverged to frappe-charts.
- **Delete a workaround.** frappe-charts redraws from a `ResizeObserver`
  callback and calls `removeChild` on already-detached nodes, throwing a benign
  `NotFoundError`. v2 currently carries a window-level error suppressor plus a
  split create-effect/update-effect to dodge it (`ChartPanel.svelte`). Chart.js
  has no such teardown race, so the entire workaround is removed.

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Goal | **Structural parity with `main`**: 3 pies + 1 wide dual-axis token bar + datalabels |
| Palette | **Keep v2's token palette** (`--accent`, `--chart-2…6`), read via CSS vars — not main's hardcoded hex |
| Delivery | **npm-bundled** (no CDN); SPA ships self-contained in the wheel |
| Registration | **`chart.js/auto`** (simplicity over manual tree-shaking) |
| Datalabels | **On the pies, off the dual-axis bar** (keeps the bar clean) |
| Versions | `chart.js@^4.5.1`, `chartjs-plugin-datalabels@^2.2.0` (peer: chart.js ≥3) |

## Target chart set (parity with `main`)

Three pie charts in the existing 3-column `charts-grid`:

1. **Tool Calls** — `num_times_called` per tool
2. **Input Tokens** — `input_tokens` per tool
3. **Output Tokens** — `output_tokens` per tool

Each pie: a displayed legend and datalabels showing the raw value (white, bold).

One **full-width dual-axis bar** below the grid (replaces v2's two separate
single-series token bars):

- Dataset **Input Tokens** → left axis `y`, semi-transparent fill + solid border.
- Dataset **Output Tokens** → right axis `y1`, solid fill.
- `y1` grid uses `drawOnChartArea: false`; both axes `beginAtZero`, titled.
- Datalabels **disabled** on this chart.

All charts sorted descending by their metric (existing `charts.ts` behavior).

## Components & changes

### `src/lib/charts.ts` — Chart.js spec builders (theme-agnostic, pure)

Replace the `FrappeData` builders (`toPieData`, `toSingleSeriesBar`) with
builders that return Chart.js-shaped configs. They stay **pure and
colorless** — the panel injects resolved CSS-var colors — so they remain
unit-testable without a DOM.

- `pieSpec(stats, key)` → `{ type: 'pie', data: { labels, datasets:[{ data }] }, options }`
  with a legend and per-instance datalabels (white, bold, value formatter).
- `tokensBarSpec(stats)` → `{ type: 'bar', data: { labels, datasets:[input, output] }, options }`
  with `yAxisID: 'y'` / `'y1'`, the two scale definitions, axis titles, and
  datalabels disabled.

Keep the descending-sort helper. Builders set everything **except** concrete
colors and theme-dependent text/grid colors; those are merged in by the panel.

### `src/components/stats/ChartPanel.svelte` — sole Chart.js integration point

- The **only** module importing `chart.js`/`chartjs-plugin-datalabels`; uses
  `chart.js/auto`.
- Props: `{ title: string; spec: ChartSpec }` (spec produced by `charts.ts`).
- Renders a `<canvas>`. On mount: resolve palette (`--accent`, `--chart-2…6`)
  and theme colors (`--text`, new `--chart-grid`) from CSS vars, merge into the
  spec's datasets/options, register datalabels **per-instance**
  (inline `plugins: [ChartDataLabels]`, not `Chart.register` globally), and
  construct the chart.
- **Data change** → mutate the chart's data and call `chart.update()` in place.
- **Theme change** (`theme.current`) → re-resolve colors, re-apply to
  datasets/scale/legend options, `chart.update()`. No recreate.
- Unmount → `chart.destroy()`.
- **Delete** the `removeChildSuppressor`, the window-level `error` listener, and
  the untrack-based effect split. A single straightforward lifecycle replaces
  them.

### `src/components/stats/StatsPage.svelte`

- Pies unchanged in `charts-grid`, now fed by `pieSpec(...)`.
- The two single-series bar `ChartPanel`s collapse into **one** full-width
  `ChartPanel` fed by `tokensBarSpec(stats.stats)`, matching main's layout.

### `src/styles/tokens.css`

- Add `--chart-grid`: light `#ddd`, dark (`[data-theme='dark']`) `#444`, so the
  bar's gridlines stay token-driven (text uses the existing `--text`).

### Cleanup

- Delete `src/types/frappe-charts.d.ts`.
- `package.json`: remove `frappe-charts`; add `chart.js` + `chartjs-plugin-datalabels`.
- Update the frappe-specific notes in `CLAUDE.md` (the "Charts" section and the
  frappe gotcha) and `README.md` (the frappe CSS/types note) to describe the
  Chart.js setup, the `chart.js/auto` choice, and the jsdom canvas-mock gotcha.

## Testing

- **`tests/charts.test.ts`** — retarget to the new builders (no canvas needed):
  - `pieSpec`: labels/data sorted descending for a chosen metric.
  - `tokensBarSpec`: two datasets, correct `yAxisID` (`y` / `y1`), values sorted
    descending, datalabels disabled in options.
- **New `ChartPanel` render test** — mock `chart.js` (jsdom has no canvas
  backend): assert the component constructs a chart from the passed spec, calls
  `update()` on a data prop change, and `destroy()` on unmount.
- Existing `stats-store.test.ts` / `stats-summary.test.ts` are unaffected.

## Build contract (CI-enforced)

After source changes, from `dashboard/`:

1. `npm run check` (svelte-check) and `npm test` (Vitest) pass.
2. `npm run lint` / `npm run format`.
3. `npm run build` — regenerates hashed assets into
   `../src/serena/resources/dashboard/`.
4. **Stage all** changes (a partial stage can leave files prettier-dirty and
   fail CI's `prettier --check`), including the regenerated build output.

## Risks & mitigations

- **jsdom has no canvas** → ChartPanel tests must mock `chart.js`. Documented as
  a CLAUDE.md gotcha.
- **Bundle size** grows (frappe ~70 kB → chart.js + datalabels ~200 kB
  minified). Acceptable for a local dashboard; `chart.js/auto` is chosen for
  simplicity over manual tree-shaking. Revisit only if size becomes a concern.
- **Backend contract untouched.** This is a frontend-only change; the
  `/get_tool_stats` shape and all routes in `vite.config.ts` `API_ROUTES` are
  unchanged.

## Out of scope

- No backend / API changes.
- No changes to other dashboard pages (Overview, Logs, Modals).
- No new chart types or interactions beyond main's parity set.
