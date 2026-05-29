# Dashboard Stats Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the Stats page so the pies have room to breathe, the dual-axis bar's x-axis isn't crowded, summary numbers carry thousands separators, and the controls feel like a toolbar instead of two floating buttons.

**Architecture:** All changes stay inside the existing Stats components. `charts.ts` gains polish on existing specs (pie legend → right, datalabels skip tiny slices; bar gets tick padding + a sane `maxRotation`). `ChartPanel.svelte` gains an optional `height` prop so `StatsPage.svelte` can size pies at 280px and the bar at 340px. `StatsSummary.svelte` formats numbers via `Intl.NumberFormat`. `StatsPage.svelte` groups the buttons into a styled toolbar. No new dependencies; no changes to API or stores.

**Tech Stack:** Svelte 5 (runes), TypeScript, Vitest + jsdom + Testing Library, Chart.js 4 + `chartjs-plugin-datalabels`.

**Working directory:** `dashboard/` unless noted.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `dashboard/src/lib/format.ts` | Add a tiny `formatNumber(n)` helper using `Intl.NumberFormat`. | Modify |
| `dashboard/src/components/stats/StatsSummary.svelte` | Use `formatNumber` for the four totals; same table structure otherwise. | Modify |
| `dashboard/tests/stats-summary.test.ts` | Add a case asserting thousands-separator formatting; keep the existing case. | Modify |
| `dashboard/src/components/stats/ChartPanel.svelte` | Add an optional `height: number = 240` prop; canvas-wrap uses it. | Modify |
| `dashboard/src/lib/charts.ts` | `pieSpec`: legend moves to the right, `datalabels.display` becomes a callback that hides labels for slices < 4%. `tokensBarSpec`: `scales.x.ticks.maxRotation = 35`, `scales.x.ticks.padding = 8`, `layout.padding.bottom = 8`. | Modify |
| `dashboard/tests/charts.test.ts` | Update pie datalabels assertion to handle the callback; assert legend position right; assert bar tick options. | Modify |
| `dashboard/src/components/stats/StatsPage.svelte` | Pass `height={280}` to pies and `height={340}` to the bar; promote `.controls` into a styled toolbar with separator. | Modify |
| `src/serena/resources/dashboard/` | Regenerated bundle (CI-enforced). | Regenerate |

---

## Task 1: Number formatting in StatsSummary

**Files:**
- Modify: `dashboard/src/lib/format.ts`
- Modify: `dashboard/src/components/stats/StatsSummary.svelte`
- Modify: `dashboard/tests/stats-summary.test.ts`

- [ ] **Step 1: Add the failing test case**

Open `dashboard/tests/stats-summary.test.ts`. Replace the entire file with:

```ts
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StatsSummary from '../src/components/stats/StatsSummary.svelte';

describe('StatsSummary', () => {
  it('shows a Total tokens row equal to input + output', () => {
    render(StatsSummary, {
      props: {
        stats: {
          a: { num_times_called: 1, input_tokens: 10, output_tokens: 5 },
          b: { num_times_called: 2, input_tokens: 40, output_tokens: 20 },
        },
      },
    });
    expect(screen.getByText('Total tokens')).toBeInTheDocument();
    expect(screen.getByTestId('total-tokens')).toHaveTextContent('75');
  });

  it('formats large numbers with thousands separators', () => {
    render(StatsSummary, {
      props: {
        stats: {
          a: { num_times_called: 1500, input_tokens: 12_345, output_tokens: 9_876 },
        },
      },
    });
    expect(screen.getByText('1,500')).toBeInTheDocument();
    expect(screen.getByText('12,345')).toBeInTheDocument();
    expect(screen.getByText('9,876')).toBeInTheDocument();
    expect(screen.getByTestId('total-tokens')).toHaveTextContent('22,221');
  });
});
```

- [ ] **Step 2: Run test to verify the new case fails**

Run: `npm test -- stats-summary`

Expected: 1 PASS, 1 FAIL — the new case fails because numbers render without commas.

- [ ] **Step 3: Add `formatNumber` to `format.ts`**

Open `dashboard/src/lib/format.ts`. Append to the end of the file (after the existing exports):

```ts
const numberFormatter = new Intl.NumberFormat('en-US');

// Thousands-separated integer formatter. Locale fixed to 'en-US' to keep
// rendering identical across browsers and CI; numbers are the user-facing
// stat totals (Tool Calls, tokens) where commas read naturally.
export function formatNumber(n: number): string {
  return numberFormatter.format(n);
}
```

- [ ] **Step 4: Wire `formatNumber` into `StatsSummary.svelte`**

Replace the entire contents of `dashboard/src/components/stats/StatsSummary.svelte` with:

```svelte
<script lang="ts">
  import type { ToolStats } from '$lib/api/types';
  import { formatNumber } from '$lib/format';
  let { stats }: { stats: ToolStats } = $props();
  const totals = $derived(
    Object.values(stats).reduce(
      (acc, s) => ({
        calls: acc.calls + s.num_times_called,
        input: acc.input + s.input_tokens,
        output: acc.output + s.output_tokens,
      }),
      { calls: 0, input: 0, output: 0 },
    ),
  );
</script>

<table class="stats-summary-block">
  <tbody>
    <tr><td>Total calls</td><td>{formatNumber(totals.calls)}</td></tr>
    <tr><td>Total input tokens</td><td>{formatNumber(totals.input)}</td></tr>
    <tr><td>Total output tokens</td><td>{formatNumber(totals.output)}</td></tr>
    <tr><td>Total tokens</td><td data-testid="total-tokens">{formatNumber(totals.input + totals.output)}</td></tr>
  </tbody>
</table>

<style>
  table {
    width: 100%;
    border-collapse: collapse;
  }
  td {
    padding: var(--space-2);
    border-bottom: 1px solid var(--border);
    font-family: var(--font-mono);
  }
</style>
```

- [ ] **Step 5: Run test to verify both pass**

Run: `npm test -- stats-summary`

Expected: 2/2 PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/format.ts dashboard/src/components/stats/StatsSummary.svelte dashboard/tests/stats-summary.test.ts
git commit -m "feat(dashboard): thousands-separated totals in StatsSummary"
```

---

## Task 2: ChartPanel `height` prop

**Files:**
- Modify: `dashboard/src/components/stats/ChartPanel.svelte`

- [ ] **Step 1: Add the `height` prop with a default**

In `dashboard/src/components/stats/ChartPanel.svelte`, change the props destructure line:

```ts
  let { title, spec }: { title: string; spec: ChartSpec } = $props();
```

to:

```ts
  let { title, spec, height = 240 }: { title: string; spec: ChartSpec; height?: number } = $props();
```

- [ ] **Step 2: Apply the height via inline style**

In the same file, change:

```svelte
  <div class="canvas-wrap"><canvas bind:this={canvas}></canvas></div>
```

to:

```svelte
  <div class="canvas-wrap" style="height: {height}px"><canvas bind:this={canvas}></canvas></div>
```

And remove the `height: 240px;` rule from the `.canvas-wrap` style block so the only remaining rule is `position: relative;`:

```css
  .canvas-wrap {
    position: relative;
  }
```

- [ ] **Step 3: Run the chart-panel tests to verify they still pass**

Run: `npm test -- chart-panel`

Expected: 3/3 PASS. (The default 240 keeps existing behaviour identical.)

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/stats/ChartPanel.svelte
git commit -m "feat(dashboard): ChartPanel accepts an optional height prop"
```

---

## Task 3: Pie polish — right-side legend + smart datalabels

**Files:**
- Modify: `dashboard/src/lib/charts.ts`
- Modify: `dashboard/tests/charts.test.ts`

- [ ] **Step 1: Update the failing tests**

In `dashboard/tests/charts.test.ts`, replace the entire `describe('pieSpec', ...)` block with:

```ts
describe('pieSpec', () => {
  it('builds a pie config for a metric, sorted descending', () => {
    const spec = pieSpec(stats, 'num_times_called');
    expect(spec.type).toBe('pie');
    expect(spec.data.labels).toEqual(['b', 'a']);
    expect(spec.data.datasets[0].data).toEqual([8, 2]);
  });
  it('renders the legend on the right of the pie', () => {
    const spec = pieSpec(stats, 'input_tokens');
    expect(spec.options?.plugins?.legend?.position).toBe('right');
  });
  it('hides datalabels on slices smaller than 4% of the total', () => {
    const spec = pieSpec(stats, 'num_times_called');
    const display = spec.options?.plugins?.datalabels?.display;
    expect(typeof display).toBe('function');
    // a 5/100 slice (5%) is shown; a 3/100 slice (3%) is hidden.
    // Datalabels passes a context with { dataIndex, dataset: { data } }.
    const show = (display as (ctx: unknown) => boolean)({
      dataIndex: 0,
      dataset: { data: [5, 95] },
    });
    const hide = (display as (ctx: unknown) => boolean)({
      dataIndex: 0,
      dataset: { data: [3, 97] },
    });
    expect(show).toBe(true);
    expect(hide).toBe(false);
  });
});
```

(Leave the `tokensBarSpec` describe block unchanged — Task 4 updates it.)

- [ ] **Step 2: Run the tests to verify the new pie cases fail**

Run: `npm test -- charts`

Expected: the two new pie cases (`renders the legend on the right of the pie`, `hides datalabels on slices smaller than 4%`) FAIL; the others PASS.

- [ ] **Step 3: Implement the polish in `pieSpec`**

In `dashboard/src/lib/charts.ts`, replace the entire `pieSpec` function with:

```ts
// Pie config for one metric. Colours are injected by ChartPanel from CSS vars;
// datalabels render the raw value in bold white on each slice — but only on
// slices ≥4% of the total, so tiny slices don't pile labels into a smudge.
// Legend is right-anchored so the pie itself gets the full vertical space.
const PIE_LABEL_MIN_FRACTION = 0.04;

export function pieSpec(stats: ToolStats, key: keyof ToolStatEntry): ChartConfiguration<'pie'> {
  const entries = sortedEntries(stats, key);
  return {
    type: 'pie',
    data: {
      labels: entries.map(([n]) => n),
      datasets: [{ data: entries.map(([, s]) => s[key]) }],
    },
    options: {
      plugins: {
        legend: { display: true, position: 'right', labels: {} },
        datalabels: {
          display: (ctx: { dataIndex: number; dataset: { data: number[] } }) => {
            const data = ctx.dataset.data;
            const total = data.reduce((a, b) => a + b, 0);
            if (total === 0) return false;
            return data[ctx.dataIndex] / total >= PIE_LABEL_MIN_FRACTION;
          },
          color: '#ffffff',
          font: { weight: 'bold' },
          formatter: (v) => v,
        },
      },
    },
  };
}
```

(Add the `PIE_LABEL_MIN_FRACTION` constant near the top of the file, just above `pieSpec`.)

- [ ] **Step 4: Run the tests to verify they all pass**

Run: `npm test -- charts`

Expected: 6/6 PASS (3 pie cases + the 3 unchanged bar cases).

- [ ] **Step 5: Bump pie chart panel height to 280 in StatsPage**

In `dashboard/src/components/stats/StatsPage.svelte`, replace the three pie `ChartPanel` lines:

```svelte
    <ChartPanel title="Tool Calls" spec={pieSpec(stats.stats, 'num_times_called')} />
    <ChartPanel title="Input Tokens" spec={pieSpec(stats.stats, 'input_tokens')} />
    <ChartPanel title="Output Tokens" spec={pieSpec(stats.stats, 'output_tokens')} />
```

with:

```svelte
    <ChartPanel title="Tool Calls" height={280} spec={pieSpec(stats.stats, 'num_times_called')} />
    <ChartPanel title="Input Tokens" height={280} spec={pieSpec(stats.stats, 'input_tokens')} />
    <ChartPanel title="Output Tokens" height={280} spec={pieSpec(stats.stats, 'output_tokens')} />
```

- [ ] **Step 6: Typecheck and commit**

Run: `npm run check`
Expected: 0 errors.

```bash
git add dashboard/src/lib/charts.ts dashboard/tests/charts.test.ts dashboard/src/components/stats/StatsPage.svelte
git commit -m "feat(dashboard): pie polish — right legend, hide labels on <4% slices, taller panel"
```

---

## Task 4: Bar polish — tick rotation, padding, taller panel

**Files:**
- Modify: `dashboard/src/lib/charts.ts`
- Modify: `dashboard/tests/charts.test.ts`
- Modify: `dashboard/src/components/stats/StatsPage.svelte`

- [ ] **Step 1: Add the failing test**

In `dashboard/tests/charts.test.ts`, inside the existing `describe('tokensBarSpec', ...)` block, add this case at the end (after `disables datalabels on the bar`):

```ts
  it('caps x-tick rotation and pads the axis so labels do not crowd', () => {
    const spec = tokensBarSpec(stats);
    const xScale = spec.options?.scales?.x as { ticks?: { maxRotation?: number; padding?: number } } | undefined;
    expect(xScale?.ticks?.maxRotation).toBe(35);
    expect(xScale?.ticks?.padding).toBe(8);
    const layoutPadding = (spec.options?.layout?.padding ?? {}) as { bottom?: number };
    expect(layoutPadding.bottom).toBe(8);
  });
```

- [ ] **Step 2: Run the tests to verify the new case fails**

Run: `npm test -- charts`

Expected: the new case FAILS (current `scales.x` is `{}`).

- [ ] **Step 3: Implement the bar polish in `tokensBarSpec`**

In `dashboard/src/lib/charts.ts`, in the `tokensBarSpec` function, replace the `options` block. Locate this section:

```ts
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: {} },
        datalabels: { display: false },
      },
      scales: {
        x: {},
```

…and replace it with:

```ts
    options: {
      responsive: true,
      layout: { padding: { bottom: 8 } },
      plugins: {
        legend: { display: true, labels: {} },
        datalabels: { display: false },
      },
      scales: {
        x: { ticks: { maxRotation: 35, padding: 8 } },
```

(Leave the `y` and `y1` scale blocks unchanged.)

- [ ] **Step 4: Run the tests to verify they all pass**

Run: `npm test -- charts`

Expected: 7/7 PASS.

- [ ] **Step 5: Bump bar chart panel height to 340 in StatsPage**

In `dashboard/src/components/stats/StatsPage.svelte`, replace:

```svelte
    <ChartPanel title="Token Usage (by tool)" spec={tokensBarSpec(stats.stats)} />
```

with:

```svelte
    <ChartPanel title="Token Usage (by tool)" height={340} spec={tokensBarSpec(stats.stats)} />
```

- [ ] **Step 6: Typecheck and commit**

Run: `npm run check`
Expected: 0 errors.

```bash
git add dashboard/src/lib/charts.ts dashboard/tests/charts.test.ts dashboard/src/components/stats/StatsPage.svelte
git commit -m "feat(dashboard): bar polish — capped x-tick rotation, tick + layout padding, taller panel"
```

---

## Task 5: Controls toolbar styling

**Files:**
- Modify: `dashboard/src/components/stats/StatsPage.svelte`

- [ ] **Step 1: Style `.controls` as a toolbar**

In `dashboard/src/components/stats/StatsPage.svelte`, replace the existing `.controls` CSS block:

```css
  .controls {
    display: flex;
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }
```

with:

```css
  .controls {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    margin-bottom: var(--space-4);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
```

(No markup changes; this just wraps the existing buttons in a visually-grouped toolbar consistent with the chart cards.)

- [ ] **Step 2: Run the full test suite + typecheck**

Run: `npm test && npm run check`

Expected: all tests PASS; 0 typecheck errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/stats/StatsPage.svelte
git commit -m "style(dashboard): group Stats controls into a card-style toolbar"
```

---

## Task 6: Lint, format, build, regenerate output

**Files:**
- Modify (generated): `src/serena/resources/dashboard/index.html` + `src/serena/resources/dashboard/assets/`

- [ ] **Step 1: Lint and format**

From `dashboard/`:

```bash
npm run lint
npm run format
```

Expected: lint passes; format rewrites any unformatted files.

- [ ] **Step 2: Full check + tests**

```bash
npm run check && npm test
```

Expected: both PASS.

- [ ] **Step 3: Build the SPA**

```bash
npm run build
```

Expected: `prebuild` clears the assets dir, Vite writes a fresh hashed bundle into `../src/serena/resources/dashboard/`. No new dependencies; bundle size shouldn't materially change.

- [ ] **Step 4: Stage ALL changes from repo root**

```bash
git add -A dashboard src/serena/resources/dashboard
git status
```

Expected: staged changes include the regenerated `src/serena/resources/dashboard/index.html` and `assets/*`. Verify nothing is left unstaged.

- [ ] **Step 5: Commit**

```bash
git commit -m "build(dashboard): regenerate bundle after Stats polish"
```

- [ ] **Step 6: Smoke check (optional, recommended)**

Restart the emulator script (`/tmp/emulate_dashboard.py`) — see the `run-dashboard-emulate-tool-calls` memory — open the Stats tab, and confirm:

- Summary totals show commas (e.g. `12,345`).
- Pies have legends on the right; small slices (e.g. `write_memory` at ~3/114 = ~2.6%) have NO datalabel; mid/large slices still do.
- Bar chart x-axis labels sit clear of the panel edge; rotation is moderate (~35°).
- Refresh / Clear buttons sit in a card-style toolbar consistent with the chart cards.
- Theme toggle still recolours legends, axes, grid, and ticks without console errors.

---

## Self-Review Notes (verified against the user's request)

- **Item 2 (pie polish):** right legend (`pieSpec` options + assertion in test), smart datalabels (callback hides slices < 4%), taller panel (height=280 in StatsPage). ✅
- **Item 3 (bar polish):** taller (height=340), `maxRotation: 35`, `ticks.padding: 8`, `layout.padding.bottom: 8`. ✅
- **Item 4 (number formatting + controls spacing):** `Intl.NumberFormat` via `formatNumber` in `format.ts`, applied to all four totals; controls become a card-style toolbar. ✅
- **Out of scope:** KPI cards (item 1) NOT included per user choice. No new dependencies; no API/store changes; backend untouched.
- **Type consistency:** `ChartPanel.svelte`'s new `height` prop is optional with a default (240), so the `chartjs-swap` chart-panel tests still pass without modification. The new pie `display` callback signature matches Chart.js datalabels' actual context shape (`{ dataIndex, dataset: { data } }`), kept narrow via `unknown`-typed cast in the test for stability.
- **No placeholders:** every step has explicit before/after code or commands.
