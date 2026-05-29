# Dashboard Chart.js Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard Stats page's frappe-charts rendering with Chart.js, restoring structural parity with `main` (3 pie charts + 1 dual-axis token bar + datalabels) while keeping v2's Svelte architecture and token palette.

**Architecture:** Charting stays confined to `ChartPanel.svelte` (the sole importer of Chart.js) and `charts.ts` (pure, theme-agnostic spec builders). `ChartPanel` resolves palette + theme colors from CSS vars, registers `chartjs-plugin-datalabels` per-instance, builds the chart on a `<canvas>`, updates data in place, and re-applies colors on theme change. The frappe `removeChild` ResizeObserver workaround is deleted.

**Tech Stack:** Svelte 5 (runes), TypeScript, Vite, `chart.js@^4.5.1` (via `chart.js/auto`), `chartjs-plugin-datalabels@^2.2.0`, Vitest + jsdom + Testing Library.

**Working directory:** All commands run from `dashboard/` unless stated otherwise. Spec: `docs/superpowers/specs/2026-05-28-dashboard-chartjs-swap-design.md`.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `dashboard/package.json` | Drop `frappe-charts`; add `chart.js`, `chartjs-plugin-datalabels` | Modify |
| `dashboard/src/styles/tokens.css` | Add `--chart-grid` token (light + dark) | Modify |
| `dashboard/src/types/frappe-charts.d.ts` | frappe ambient types | **Delete** |
| `dashboard/src/types/chartjs-datalabels.d.ts` | Type-only import to apply the datalabels plugin's Chart.js augmentation | Create |
| `dashboard/src/lib/charts.ts` | Pure Chart.js spec builders (`pieSpec`, `tokensBarSpec`) | Rewrite |
| `dashboard/src/components/stats/ChartPanel.svelte` | Sole Chart.js integration: canvas lifecycle, color/theme injection, datalabels | Rewrite |
| `dashboard/src/components/stats/StatsPage.svelte` | 3 pies in grid + 1 full-width dual-axis bar | Modify |
| `dashboard/tests/charts.test.ts` | Unit-test the new builders | Rewrite |
| `dashboard/tests/chart-panel.test.ts` | Render test mocking `chart.js/auto` | Create |
| `dashboard/CLAUDE.md`, `dashboard/README.md` | Replace frappe notes with Chart.js notes | Modify |
| `src/serena/resources/dashboard/` | Built SPA output (CI-enforced) | Regenerate |

---

## Task 1: Swap dependencies and add the grid token

**Files:**
- Modify: `dashboard/package.json` (dependencies block)
- Modify: `dashboard/src/styles/tokens.css`

- [ ] **Step 1: Replace the charting dependency**

Run (from `dashboard/`):

```bash
npm uninstall frappe-charts
npm install chart.js@^4.5.1 chartjs-plugin-datalabels@^2.2.0
```

Expected: `package.json` `dependencies` now reads:

```json
  "dependencies": {
    "chart.js": "^4.5.1",
    "chartjs-plugin-datalabels": "^2.2.0"
  }
```

and `frappe-charts` is gone from `package.json` + `package-lock.json`.

- [ ] **Step 2: Add the `--chart-grid` token**

In `dashboard/src/styles/tokens.css`, add to the `:root` block (after `--chart-6`):

```css
  --chart-grid: #dddddd;
```

and add to the `[data-theme='dark']` block (after `--border-strong`):

```css
  --chart-grid: #444444;
```

- [ ] **Step 3: Verify install + typecheck baseline**

Run: `npm run check`
Expected: it FAILS only in `charts.ts` / `ChartPanel.svelte` / `frappe-charts.d.ts` because `frappe-charts` no longer resolves. That is expected at this stage — later tasks replace those files. (If it reports unrelated errors, stop and investigate.)

- [ ] **Step 4: Commit**

```bash
git add dashboard/package.json dashboard/package-lock.json dashboard/src/styles/tokens.css
git commit -m "build(dashboard): swap frappe-charts dep for chart.js + datalabels, add --chart-grid token"
```

---

## Task 2: Chart.js spec builders in `charts.ts` (TDD)

**Files:**
- Create: `dashboard/src/types/chartjs-datalabels.d.ts`
- Rewrite: `dashboard/src/lib/charts.ts`
- Rewrite: `dashboard/tests/charts.test.ts`

- [ ] **Step 1: Write the failing test**

Replace the entire contents of `dashboard/tests/charts.test.ts` with:

```ts
import { describe, it, expect } from 'vitest';
import { pieSpec, tokensBarSpec } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  a: { num_times_called: 2, input_tokens: 10, output_tokens: 5 },
  b: { num_times_called: 8, input_tokens: 40, output_tokens: 20 },
};

describe('pieSpec', () => {
  it('builds a pie config for a metric, sorted descending', () => {
    const spec = pieSpec(stats, 'num_times_called');
    expect(spec.type).toBe('pie');
    expect(spec.data.labels).toEqual(['b', 'a']);
    expect(spec.data.datasets[0].data).toEqual([8, 2]);
  });
  it('enables datalabels on pies', () => {
    const spec = pieSpec(stats, 'input_tokens');
    expect(spec.options?.plugins?.datalabels?.display).toBe(true);
  });
});

describe('tokensBarSpec', () => {
  it('builds a dual-dataset bar sorted descending by input tokens', () => {
    const spec = tokensBarSpec(stats);
    expect(spec.type).toBe('bar');
    expect(spec.data.labels).toEqual(['b', 'a']);
    expect(spec.data.datasets).toHaveLength(2);
  });
  it('assigns input to the left y axis and output to the right y1 axis', () => {
    const spec = tokensBarSpec(stats);
    const [input, output] = spec.data.datasets;
    expect(input.label).toBe('Input Tokens');
    expect(input.data).toEqual([40, 10]);
    expect(input.yAxisID).toBe('y');
    expect(output.label).toBe('Output Tokens');
    expect(output.data).toEqual([20, 5]);
    expect(output.yAxisID).toBe('y1');
  });
  it('disables datalabels on the bar', () => {
    const spec = tokensBarSpec(stats);
    expect(spec.options?.plugins?.datalabels?.display).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- charts`
Expected: FAIL — `pieSpec`/`tokensBarSpec` are not exported from `../src/lib/charts` (and `frappe-charts` may still error).

- [ ] **Step 3: Add the datalabels type augmentation file**

Create `dashboard/src/types/chartjs-datalabels.d.ts`:

```ts
// Type-only side-effect import: pulls in chartjs-plugin-datalabels' module
// augmentation so `options.plugins.datalabels` typechecks across the project.
// Erased at runtime (.d.ts files emit nothing); the runtime import lives in
// ChartPanel.svelte. Replaces the old frappe-charts.d.ts ambient shim.
import 'chartjs-plugin-datalabels';
```

- [ ] **Step 4: Write the builders**

Replace the entire contents of `dashboard/src/lib/charts.ts` with:

```ts
import type { ChartConfiguration } from 'chart.js';
import type { ToolStats, ToolStatEntry } from './api/types';

export type ChartSpec = ChartConfiguration<'pie'> | ChartConfiguration<'bar'>;

function sortedEntries(stats: ToolStats, key: keyof ToolStatEntry): Array<[string, ToolStatEntry]> {
  return Object.entries(stats).sort((a, b) => b[1][key] - a[1][key]);
}

// Pie config for one metric. Colours are injected by ChartPanel from CSS vars;
// datalabels render the raw value in bold white on each slice.
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
        legend: { display: true, labels: {} },
        datalabels: { display: true, color: '#ffffff', font: { weight: 'bold' }, formatter: (v) => v },
      },
    },
  };
}

// Combined input/output token bar with two y axes (parity with main).
// Sorted by input tokens; output uses the same tool order. Datalabels off.
export function tokensBarSpec(stats: ToolStats): ChartConfiguration<'bar'> {
  const entries = sortedEntries(stats, 'input_tokens');
  return {
    type: 'bar',
    data: {
      labels: entries.map(([n]) => n),
      datasets: [
        { label: 'Input Tokens', data: entries.map(([, s]) => s.input_tokens), yAxisID: 'y' },
        { label: 'Output Tokens', data: entries.map(([, s]) => s.output_tokens), yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true, labels: {} },
        datalabels: { display: false },
      },
      scales: {
        x: {},
        y: {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          title: { display: true, text: 'Input Tokens' },
        },
        y1: {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          title: { display: true, text: 'Output Tokens' },
          grid: { drawOnChartArea: false },
        },
      },
    },
  };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test -- charts`
Expected: PASS (all 5 cases).

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/charts.ts dashboard/src/types/chartjs-datalabels.d.ts dashboard/tests/charts.test.ts
git commit -m "feat(dashboard): Chart.js spec builders (pieSpec, tokensBarSpec)"
```

---

## Task 3: Rewrite `ChartPanel.svelte` (sole Chart.js integration)

**Files:**
- Rewrite: `dashboard/src/components/stats/ChartPanel.svelte`
- Create: `dashboard/tests/chart-panel.test.ts`

- [ ] **Step 1: Write the failing render test**

Create `dashboard/tests/chart-panel.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/svelte';
import ChartPanel from '../src/components/stats/ChartPanel.svelte';
import { pieSpec } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

// jsdom has no canvas backend — mock Chart.js entirely.
const instance = {
  data: { labels: [] as unknown[], datasets: [{}, {}] as Record<string, unknown>[] },
  options: { plugins: { legend: { labels: {} } }, scales: {} },
  update: vi.fn(),
  destroy: vi.fn(),
};
const ChartMock = vi.fn(() => instance);
vi.mock('chart.js/auto', () => ({ default: ChartMock }));
vi.mock('chartjs-plugin-datalabels', () => ({ default: {} }));

const stats: ToolStats = { a: { num_times_called: 5, input_tokens: 1, output_tokens: 1 } };

describe('ChartPanel', () => {
  it('constructs a Chart from the spec and renders the title', () => {
    const { getByText } = render(ChartPanel, {
      props: { title: 'Tool Calls', spec: pieSpec(stats, 'num_times_called') },
    });
    expect(getByText('Tool Calls')).toBeInTheDocument();
    expect(ChartMock).toHaveBeenCalledTimes(1);
    const config = ChartMock.mock.calls[0][1] as { type: string };
    expect(config.type).toBe('pie');
  });

  it('destroys the chart on unmount', () => {
    const { unmount } = render(ChartPanel, {
      props: { title: 'Tool Calls', spec: pieSpec(stats, 'num_times_called') },
    });
    unmount();
    expect(instance.destroy).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- chart-panel`
Expected: FAIL — current `ChartPanel.svelte` imports `frappe-charts` (unresolved) and renders a `<div>`, not the new lifecycle.

- [ ] **Step 3: Rewrite the component**

Replace the entire contents of `dashboard/src/components/stats/ChartPanel.svelte` with:

```svelte
<script lang="ts">
  import { untrack } from 'svelte';
  import Chart from 'chart.js/auto';
  import ChartDataLabels from 'chartjs-plugin-datalabels';
  import type { ChartConfiguration } from 'chart.js';
  import type { ChartSpec } from '$lib/charts';
  import { theme } from '$lib/stores/theme.svelte';

  let { title, spec }: { title: string; spec: ChartSpec } = $props();
  let canvas = $state<HTMLCanvasElement | null>(null);
  let chart: Chart | null = null;

  function cssVar(name: string, fallback: string): string {
    if (typeof document === 'undefined') return fallback;
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }
  function palette(): string[] {
    return [
      cssVar('--accent', '#eaa45d'),
      cssVar('--chart-2', '#6aa3d8'),
      cssVar('--chart-3', '#7fb77e'),
      cssVar('--chart-4', '#d88c8c'),
      cssVar('--chart-5', '#b39ddb'),
      cssVar('--chart-6', '#e0a458'),
    ];
  }

  // Re-resolve palette + theme colours from CSS vars and write them onto the live
  // chart, then redraw. Called after create, on data change, and on theme change —
  // Chart.js updates in place, so no teardown (and no frappe removeChild race).
  function applyTheme(): void {
    if (!chart) return;
    const colors = palette();
    const text = cssVar('--text-primary', '#1f2328');
    const grid = cssVar('--chart-grid', '#dddddd');
    const sliceColors = (chart.data.labels ?? []).map((_, i) => colors[i % colors.length]);

    if (spec.type === 'pie') {
      chart.data.datasets[0].backgroundColor = sliceColors;
    } else {
      // Dual-axis bar: input semi-transparent fill + solid border, output solid.
      chart.data.datasets[0].backgroundColor = sliceColors.map((c) => c + '80');
      chart.data.datasets[0].borderColor = sliceColors;
      chart.data.datasets[0].borderWidth = 2;
      chart.data.datasets[1].backgroundColor = sliceColors;
    }

    const o = chart.options as ChartConfiguration['options'] & {
      plugins?: { legend?: { labels?: { color?: string } } };
      scales?: Record<string, { ticks?: { color?: string }; grid?: { color?: string }; title?: { color?: string } }>;
    };
    if (o.plugins?.legend?.labels) o.plugins.legend.labels.color = text;
    if (o.scales) {
      for (const axis of Object.values(o.scales)) {
        if (!axis) continue;
        axis.ticks = { ...axis.ticks, color: text };
        axis.grid = { ...axis.grid, color: grid };
        if (axis.title) axis.title.color = text;
      }
    }
    chart.update();
  }

  // Create once per canvas bind. Reads `spec` via untrack so data changes don't
  // recreate the chart (the data-effect below handles those in place). Registers
  // datalabels per-instance instead of globally.
  $effect(() => {
    if (!canvas) return;
    const node = canvas;
    const created = untrack(
      () => new Chart(node, { ...spec, plugins: [ChartDataLabels] } as ChartConfiguration),
    );
    chart = created;
    untrack(() => applyTheme());
    return () => {
      chart = null;
      created.destroy();
    };
  });

  // Data-only updates: copy labels/data from the new spec and recolour in place.
  $effect(() => {
    const next = spec;
    if (!chart) return;
    chart.data.labels = next.data.labels ?? [];
    next.data.datasets.forEach((ds, i) => {
      if (chart!.data.datasets[i]) chart!.data.datasets[i].data = ds.data;
    });
    applyTheme();
  });

  // Re-apply colours when the theme flips.
  $effect(() => {
    void theme.current;
    if (chart) applyTheme();
  });
</script>

<div class="chart-group">
  <h3>{title}</h3>
  <div class="canvas-wrap"><canvas bind:this={canvas}></canvas></div>
</div>

<style>
  .chart-group {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-4);
    box-shadow: var(--shadow);
  }
  .canvas-wrap {
    position: relative;
    height: 240px;
  }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- chart-panel`
Expected: PASS (both cases).

- [ ] **Step 5: Verify typecheck is clean for charts files**

Run: `npm run check`
Expected: no errors in `charts.ts` or `ChartPanel.svelte`. `StatsPage.svelte` still errors (it imports the removed `toPieData`/`toSingleSeriesBar`) — fixed in Task 4.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/stats/ChartPanel.svelte dashboard/tests/chart-panel.test.ts
git commit -m "feat(dashboard): Chart.js ChartPanel with in-place theme/data updates; drop frappe removeChild workaround"
```

---

## Task 4: Wire StatsPage to the new specs

**Files:**
- Modify: `dashboard/src/components/stats/StatsPage.svelte`

- [ ] **Step 1: Update imports and chart markup**

In `dashboard/src/components/stats/StatsPage.svelte`, change the import line:

```ts
  import { toPieData, toSingleSeriesBar } from '$lib/charts';
```

to:

```ts
  import { pieSpec, tokensBarSpec } from '$lib/charts';
```

Then replace the three pie `ChartPanel`s and the two bar `ChartPanel`s. Replace this block:

```svelte
  <div class="charts-grid">
    <ChartPanel title="Tool Calls" type="pie" data={toPieData(stats.stats, 'num_times_called')} />
    <ChartPanel title="Input Tokens" type="pie" data={toPieData(stats.stats, 'input_tokens')} />
    <ChartPanel title="Output Tokens" type="pie" data={toPieData(stats.stats, 'output_tokens')} />
  </div>
  <div class="charts-bars">
    <ChartPanel
      title="Input Tokens (by tool)"
      type="bar"
      valuesOverPoints
      data={toSingleSeriesBar(stats.stats, 'input_tokens', 'Input Tokens')}
    />
    <ChartPanel
      title="Output Tokens (by tool)"
      type="bar"
      valuesOverPoints
      data={toSingleSeriesBar(stats.stats, 'output_tokens', 'Output Tokens')}
    />
  </div>
```

with:

```svelte
  <div class="charts-grid">
    <ChartPanel title="Tool Calls" spec={pieSpec(stats.stats, 'num_times_called')} />
    <ChartPanel title="Input Tokens" spec={pieSpec(stats.stats, 'input_tokens')} />
    <ChartPanel title="Output Tokens" spec={pieSpec(stats.stats, 'output_tokens')} />
  </div>
  <div class="charts-bars">
    <ChartPanel title="Token Usage (by tool)" spec={tokensBarSpec(stats.stats)} />
  </div>
```

(Leave the `<style>` block, controls, `StatsSummary`, and `estimator-name` markup unchanged — `.charts-grid` and `.charts-bars` styles still apply; `.charts-bars` now holds one full-width chart.)

- [ ] **Step 2: Typecheck the whole project**

Run: `npm run check`
Expected: PASS, no errors.

- [ ] **Step 3: Run the full test suite**

Run: `npm test`
Expected: PASS — all suites green (charts, chart-panel, stats-store, stats-summary, and the rest).

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/stats/StatsPage.svelte
git commit -m "feat(dashboard): render 3 pies + 1 dual-axis token bar via Chart.js specs"
```

---

## Task 5: Delete the frappe shim and update docs

**Files:**
- Delete: `dashboard/src/types/frappe-charts.d.ts`
- Modify: `dashboard/CLAUDE.md`
- Modify: `dashboard/README.md`

- [ ] **Step 1: Delete the obsolete ambient type file**

```bash
git rm dashboard/src/types/frappe-charts.d.ts
```

- [ ] **Step 2: Update `CLAUDE.md`**

In `dashboard/CLAUDE.md`, replace the entire `## Charts (ChartPanel.svelte)` section (currently describing the frappe create/update effects and the removeChild suppressor) with:

```markdown
## Charts (`ChartPanel.svelte`)

Chart.js wrapper (`chart.js/auto`). `charts.ts` builds pure, colourless
`ChartSpec`s (`pieSpec`, `tokensBarSpec`); `ChartPanel` is the **only** importer
of `chart.js`/`chartjs-plugin-datalabels`. It resolves the palette
(`--accent`, `--chart-2…6`) and theme colours (`--text-primary`, `--chart-grid`)
from CSS vars and writes them onto the live chart. A **create-effect** builds the
chart once per canvas bind (reads `spec` via `untrack`); a **data-effect** copies
labels/data in place on `spec` change; a **theme-effect** re-applies colours on
`theme.current`. All three end in `chart.update()` — no teardown, so there is no
frappe-style `removeChild` race to suppress. `chartjs-plugin-datalabels` is
registered **per-instance** (`plugins: [ChartDataLabels]`), enabled on the pies
and disabled on the dual-axis bar.
```

Then, in the `## Gotchas` section, replace the two `frappe-charts@1.6.2` bullet(s) with:

```markdown
- **Charts use `chart.js/auto`** (auto-registers all controllers/scales — simpler
  than manual tree-shaking). `chartjs-plugin-datalabels` is registered per-chart,
  not globally. Its Chart.js type augmentation is loaded via the type-only
  `src/types/chartjs-datalabels.d.ts`.
- **jsdom has no canvas backend** — component tests that mount a chart must
  `vi.mock('chart.js/auto', ...)` and `vi.mock('chartjs-plugin-datalabels', ...)`
  (see `tests/chart-panel.test.ts`).
```

- [ ] **Step 3: Update `README.md`**

In `dashboard/README.md`, replace the `frappe-charts@1.6.2 ships no compiled CSS …` bullet (the one referencing `src/types/frappe-charts.d.ts`) with:

```markdown
- **Charts use Chart.js** (`chart.js/auto`) + `chartjs-plugin-datalabels`, wrapped
  by `src/components/stats/ChartPanel.svelte` (the only file importing them).
  Series colours come from CSS vars, not hardcoded hex.
```

- [ ] **Step 4: Verify no frappe references remain**

Run (from repo root):

```bash
grep -rn "frappe" dashboard/src dashboard/tests dashboard/package.json dashboard/CLAUDE.md dashboard/README.md
```

Expected: no output (exit 1).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/types/frappe-charts.d.ts dashboard/CLAUDE.md dashboard/README.md
git commit -m "docs(dashboard): document Chart.js setup; remove frappe shim and notes"
```

---

## Task 6: Lint, format, build, and stage the regenerated output

**Files:**
- Modify (generated): `src/serena/resources/dashboard/index.html` + `src/serena/resources/dashboard/assets/`

- [ ] **Step 1: Lint and format**

Run (from `dashboard/`):

```bash
npm run lint
npm run format
```

Expected: lint passes; format rewrites any unformatted files.

- [ ] **Step 2: Full check + tests once more**

```bash
npm run check && npm test
```

Expected: both PASS.

- [ ] **Step 3: Build the SPA**

```bash
npm run build
```

Expected: `prebuild` clears `../src/serena/resources/dashboard/assets/`, then Vite writes a fresh hashed bundle there plus `index.html`. No frappe chunk in the output; a `chart.js` chunk present.

- [ ] **Step 4: Stage ALL changes (build output + any format fixes)**

From repo root:

```bash
git add -A dashboard src/serena/resources/dashboard
git status
```

Expected: staged changes include the regenerated `src/serena/resources/dashboard/index.html` and `assets/*`. Verify nothing is left unstaged (a partial stage fails CI's `prettier --check`).

- [ ] **Step 5: Commit**

```bash
git commit -m "build(dashboard): regenerate Chart.js dashboard bundle"
```

- [ ] **Step 6: Manual smoke check (optional but recommended)**

Start any Serena MCP server with the dashboard enabled, populate some tool stats (see the user's `run-dashboard-emulate-tool-calls` memory), open the dashboard, go to the Stats tab, and confirm: 3 pies with value datalabels, 1 wide dual-axis bar (Input left / Output right), correct token-palette colours, and that toggling the theme recolours legends/axes/grid without console errors.

---

## Self-Review Notes (verified against spec)

- **Spec coverage:** library swap (T1), token palette via CSS vars (T3 `palette()`), `chart.js/auto` (T3), datalabels on pies / off bar (T2 specs + T3 per-instance register), dual-axis bar parity (T2 `tokensBarSpec`), StatsPage layout 3 pies + 1 bar (T4), `--chart-grid` token (T1), delete frappe shim + suppressor (T3/T5), retargeted unit test + new component test (T2/T3), docs (T5), build contract (T6). All covered.
- **Type consistency:** `ChartSpec`, `pieSpec`, `tokensBarSpec`, `applyTheme`, `palette`, `cssVar` names are used identically across tasks. `ChartPanel` prop is `spec` (not `data`/`type`) everywhere it's consumed (T4).
- **No placeholders:** every code/command step shows full content.
```
