<script lang="ts">
  import { untrack } from 'svelte';
  import Chart from 'chart.js/auto';
  import ChartDataLabels from 'chartjs-plugin-datalabels';
  import type { ChartConfiguration, ChartDataset, ChartEvent, ActiveElement } from 'chart.js';
  import type { ChartSpec } from '$lib/charts';
  import { theme } from '$lib/stores/theme.svelte';

  let {
    title,
    spec,
    height = 240,
    onSliceClick,
  }: {
    title?: string;
    spec: ChartSpec;
    height?: number;
    onSliceClick?: (_label: string) => void;
  } = $props();
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
      cssVar('--chart-6', '#4db6ac'),
      cssVar('--chart-7', '#e57aa8'),
      cssVar('--chart-8', '#a1887f'),
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
    const sliceColors = (chart.data.labels ?? []).map((_label, i) => colors[i % colors.length]);

    if (spec.type === 'pie') {
      chart.data.datasets[0].backgroundColor = sliceColors;
    } else if (spec.type === 'bar' && chart.data.datasets.length === 2) {
      // Dual-axis bar (tokens / duration): input semi-transparent fill + solid
      // border, output solid. Narrow once — `ChartDataset<'pie'|'bar'>` resolves
      // `borderWidth` to `never`.
      const input = chart.data.datasets[0] as ChartDataset<'bar'>;
      const output = chart.data.datasets[1] as ChartDataset<'bar'>;
      input.backgroundColor = sliceColors.map((c) => c + '80');
      input.borderColor = sliceColors;
      input.borderWidth = 2;
      output.backgroundColor = sliceColors;
    } else if (spec.type === 'line') {
      // Per-dataset colours indexed by dataset position (tools or single line).
      chart.data.datasets.forEach((ds, i) => {
        const lineDs = ds as ChartDataset<'line'>;
        const col = colors[i % colors.length];
        lineDs.borderColor = col;
        // Stacked-area uses semi-transparent fill; the single-line non-stacked
        // dataset has fill:false so backgroundColor doesn't matter visually.
        lineDs.backgroundColor = col + '66';
        lineDs.pointBackgroundColor = col;
        lineDs.pointBorderColor = col;
      });
    }

    const o = chart.options as ChartConfiguration['options'] & {
      plugins?: { legend?: { labels?: { color?: string } } };
      scales?: Record<
        string,
        { ticks?: { color?: string }; grid?: { color?: string }; title?: { color?: string } }
      >;
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
  // datalabels per-instance instead of globally. Splice onSliceClick into
  // options.onClick BEFORE construction so it survives data updates (B23).
  $effect(() => {
    if (!canvas) return;
    const node = canvas;
    const created = untrack(() => {
      const config = { ...spec, plugins: [ChartDataLabels] } as ChartConfiguration;
      const baseOnClick = (config.options as { onClick?: unknown } | undefined)?.onClick as
        | ((_evt: ChartEvent, _elements: ActiveElement[], _chartInstance: Chart) => void)
        | undefined;
      const handler = (evt: ChartEvent, elements: ActiveElement[], chartInstance: Chart) => {
        if (elements.length > 0 && onSliceClick) {
          const idx = elements[0].index;
          const label = chartInstance.data.labels?.[idx];
          if (typeof label === 'string') onSliceClick(label);
        }
        if (typeof baseOnClick === 'function') baseOnClick(evt, elements, chartInstance);
      };
      config.options = { ...(config.options ?? {}), onClick: handler };
      return new Chart(node, config);
    });
    chart = created;
    untrack(() => applyTheme());
    return () => {
      chart = null;
      created.destroy();
    };
  });

  // Data-only updates: copy labels/data from the new spec and recolour in place.
  // B25: if the dataset COUNT changed (e.g. RateChart stacked toggle flips 1↔N),
  // replace the array wholesale — mutating dataset[i].data only handles same-shape
  // updates and silently drops added datasets.
  $effect(() => {
    const next = spec;
    if (!chart) return;
    chart.data.labels = next.data.labels ?? [];
    if (chart.data.datasets.length !== next.data.datasets.length) {
      chart.data.datasets = next.data.datasets;
      chart.update('none');
    } else {
      next.data.datasets.forEach((ds, i) => {
        if (chart!.data.datasets[i]) chart!.data.datasets[i].data = ds.data;
      });
    }
    applyTheme();
  });

  // Re-apply colours when the theme flips.
  $effect(() => {
    void theme.current;
    if (chart) applyTheme();
  });
</script>

<div class="chart-group">
  {#if title}<h3>{title}</h3>{/if}
  <div class="canvas-wrap" style="height: {height}px"><canvas bind:this={canvas}></canvas></div>
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
  }
</style>
