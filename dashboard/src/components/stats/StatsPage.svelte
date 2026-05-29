<script lang="ts">
  import { onMount } from 'svelte';
  import { stats } from '$lib/stores/stats.svelte';
  import { toPieData, toSingleSeriesBar } from '$lib/charts';
  import ChartPanel from './ChartPanel.svelte';
  import StatsSummary from './StatsSummary.svelte';
  import Button from '../common/Button.svelte';
  const hasStats = $derived(Object.keys(stats.stats).length > 0);
  onMount(() => {
    void stats.refresh();
  });
</script>

<div class="controls">
  <Button onclick={() => stats.refresh()}>Refresh Stats</Button>
  <Button onclick={() => stats.clear()}>Clear Stats</Button>
</div>

{#if hasStats}
  <StatsSummary stats={stats.stats} />
  <div class="estimator-name">Token estimator: {stats.estimator}</div>
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
{:else}
  <div class="no-stats-message">No tool stats collected yet.</div>
{/if}

<style>
  .controls {
    display: flex;
    gap: var(--space-3);
    margin-bottom: var(--space-4);
  }
  .charts-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  .charts-bars {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-4);
    margin-top: var(--space-4);
  }
  @media (max-width: 1000px) {
    .charts-grid {
      grid-template-columns: 1fr;
    }
  }
  .estimator-name {
    color: var(--text-muted);
    margin: var(--space-2) 0;
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
