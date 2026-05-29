<script lang="ts">
  import ChartPanel from './ChartPanel.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import { rateChartSpec } from '$lib/charts';

  type WindowMinutes = 15 | 30 | 60 | 360;
  let windowMinutes = $state<WindowMinutes>(15);
  let stacked = $state(false);
  let enabledTools = $state<Set<string>>(new Set());

  const allTools = $derived(Array.from(new Set(timeline.records.map((r) => r.tool))).sort());
  // When stacked is on and the user hasn't picked any tool, show all of them.
  const activeTools = $derived(
    stacked ? allTools.filter((t) => enabledTools.size === 0 || enabledTools.has(t)) : [],
  );

  // Re-bucket on every tick so the current minute keeps catching live calls
  // (B17 — current minute is the LAST bucket, never dropped).
  let nowS = $state(Math.floor(Date.now() / 1000));
  $effect(() => {
    const id = setInterval(() => {
      nowS = Math.floor(Date.now() / 1000);
    }, 5_000);
    return () => clearInterval(id);
  });

  const spec = $derived(rateChartSpec(timeline.records, nowS, windowMinutes, stacked, activeTools));

  function showAll() {
    enabledTools = new Set(allTools);
  }
  function disableAll() {
    enabledTools = new Set();
  }
</script>

<section class="card">
  <header class="head">
    <h3>Tool Call Rate</h3>
    <div class="controls">
      <label>
        Window
        <select
          value={String(windowMinutes)}
          onchange={(e) =>
            (windowMinutes = Number((e.target as HTMLSelectElement).value) as WindowMinutes)}
        >
          <option value="15">15 m</option>
          <option value="30">30 m</option>
          <option value="60">1 h</option>
          <option value="360">6 h</option>
        </select>
      </label>
      <label>
        <input type="checkbox" bind:checked={stacked} /> per-tool stacked
      </label>
      {#if stacked}
        <button type="button" onclick={showAll}>Show all</button>
        <button type="button" onclick={disableAll}>Disable all</button>
      {/if}
    </div>
  </header>
  <ChartPanel {spec} height={280} />
  {#if windowMinutes >= 60}
    <p class="hint">
      Buffer is capped at 2000 records — long windows may show only the recent portion.
    </p>
  {/if}
</section>

<style>
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3);
    box-shadow: var(--shadow);
  }
  .head {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-2);
  }
  .head h3 {
    margin: 0;
    font-size: 1em;
    color: var(--text-primary);
  }
  .controls {
    margin-left: auto;
    display: flex;
    gap: var(--space-2);
    align-items: center;
    color: var(--text-secondary);
  }
  .controls select,
  .controls button {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-primary);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }
  .hint {
    color: var(--text-muted);
    font-size: 0.85em;
    margin: var(--space-1) 0 0;
  }
</style>
