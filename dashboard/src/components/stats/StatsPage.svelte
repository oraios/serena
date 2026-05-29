<script lang="ts">
  import { onMount } from 'svelte';
  import { stats } from '$lib/stores/stats.svelte';
  import { pieSpec, tokensBarSpec } from '$lib/charts';
  import ChartPanel from './ChartPanel.svelte';
  import StatsSummary from './StatsSummary.svelte';
  import SortSelector from './SortSelector.svelte';
  import DurationChart from './DurationChart.svelte';
  import RateChart from './RateChart.svelte';
  import DrillDownPanel from './DrillDownPanel.svelte';
  import Button from '../common/Button.svelte';

  let { onOpenInTimeline }: { onOpenInTimeline?: (_tool: string) => void } = $props();

  const hasStats = $derived(Object.keys(stats.stats).length > 0);
  const drill = (label: string) => stats.setDrillTool(label);

  onMount(() => {
    void stats.refresh();
  });
</script>

<div class="controls">
  <Button onclick={() => stats.refresh()}>Refresh Stats</Button>
  <Button onclick={() => stats.clear()}>Clear Stats</Button>
  <span class="spacer"></span>
  <SortSelector />
</div>

{#if hasStats}
  <StatsSummary stats={stats.stats} />
  <div class="estimator-name">Token estimator: {stats.estimator}</div>
  <div class="charts-grid">
    <ChartPanel
      title="Tool Calls"
      height={360}
      spec={pieSpec(stats.stats, 'num_times_called')}
      onSliceClick={drill}
    />
    <ChartPanel
      title="Input Tokens"
      height={360}
      spec={pieSpec(stats.stats, 'input_tokens')}
      onSliceClick={drill}
    />
    <ChartPanel
      title="Output Tokens"
      height={360}
      spec={pieSpec(stats.stats, 'output_tokens')}
      onSliceClick={drill}
    />
  </div>
  <div class="charts-bars">
    <ChartPanel
      title="Token Usage (by tool)"
      height={460}
      spec={tokensBarSpec(stats.stats, stats.sortKey)}
      onSliceClick={drill}
    />
  </div>
  <div class="charts-bars">
    <DurationChart onSliceClick={drill} />
  </div>
  <div class="charts-bars">
    <RateChart />
  </div>
{:else}
  <div class="no-stats-message">No tool stats collected yet.</div>
{/if}

<DrillDownPanel {onOpenInTimeline} />

<style>
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
  .spacer {
    flex: 1;
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
