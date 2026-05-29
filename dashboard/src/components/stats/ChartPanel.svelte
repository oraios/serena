<script module lang="ts">
  let removeChildSuppressorInstalled = false;
  /**
   * Frappe Charts redraws from a ResizeObserver callback; during initial grid layout (and on
   * teardown) that redraw can call removeChild on a node Svelte — or Frappe's own cleanup — has
   * already detached, throwing a benign NotFoundError. Because it surfaces asynchronously from the
   * observer callback, a try/catch around our Chart usage can't reach it, so we install a single
   * window-level handler that swallows exactly that message and lets everything else through.
   * NOTE: update()-in-place removed most teardown, but the ResizeObserver still fires this on
   * initial grid layout and on theme-recreate/unmount, so the suppressor is still required
   * (verified via Playwright runtime check).
   */
  function installFrappeRemoveChildSuppressor(): void {
    if (removeChildSuppressorInstalled || typeof window === 'undefined') return;
    removeChildSuppressorInstalled = true;
    window.addEventListener(
      'error',
      (event: ErrorEvent) => {
        const msg = event.message ?? '';
        if (msg.includes('removeChild') && msg.includes('not a child')) {
          event.preventDefault();
          event.stopImmediatePropagation();
        }
      },
      true,
    );
  }
</script>

<script lang="ts">
  import { untrack } from 'svelte';
  import { Chart } from 'frappe-charts';
  import type { FrappeData } from '$lib/charts';
  import { theme } from '$lib/stores/theme.svelte';

  installFrappeRemoveChildSuppressor();

  let {
    title,
    data,
    type,
    valuesOverPoints = false,
  }: {
    title: string;
    data: FrappeData;
    type: 'pie' | 'percentage' | 'bar';
    valuesOverPoints?: boolean;
  } = $props();
  let el = $state<HTMLDivElement | null>(null);

  function cssVar(name: string, fallback: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }
  function seriesColors(): string[] {
    return [
      cssVar('--accent', '#eaa45d'),
      cssVar('--chart-2', '#6aa3d8'),
      cssVar('--chart-3', '#7fb77e'),
      cssVar('--chart-4', '#d88c8c'),
      cssVar('--chart-5', '#b39ddb'),
      cssVar('--chart-6', '#e0a458'),
    ];
  }

  let chartRef: Chart | null = null;

  // Recreate the chart only when the theme changes (colors are baked in at construction) or
  // when `el` (re)binds. `data`/`title`/`type` are read via untrack() so a data change does
  // NOT re-run this effect — the separate update-effect below handles data in place, avoiding
  // the full DOM teardown that previously triggered the ResizeObserver removeChild race.
  $effect(() => {
    void theme.current; // re-run on theme change
    if (!el) return; // reading `el` makes (re)bind a dependency, which we want
    const node = el;
    const chart = untrack(() => {
      node.innerHTML = '';
      return new Chart(node, {
        title,
        data,
        type,
        height: type === 'bar' ? 240 : 220,
        colors: seriesColors(),
        valuesOverPoints: valuesOverPoints ? 1 : 0,
      });
    });
    chartRef = chart;
    return () => {
      chartRef = null;
      try {
        chart.destroy();
      } catch {
        /* frappe removeChild race on teardown */
      }
    };
  });

  // Data-only updates: read `data` (registers the dependency) and diff in place. Skips when
  // the chart hasn't been built yet — the create-effect renders the first frame.
  $effect(() => {
    const next = data;
    if (chartRef) chartRef.update(next);
  });
</script>

<div class="chart-group">
  <h3>{title}</h3>
  <div bind:this={el}></div>
</div>

<style>
  .chart-group {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-4);
    box-shadow: var(--shadow);
  }
</style>
