<script lang="ts">
  import ChartPanel from './ChartPanel.svelte';
  import { stats } from '$lib/stores/stats.svelte';
  import { durationChartSpec } from '$lib/charts';

  let { onSliceClick }: { onSliceClick?: (_label: string) => void } = $props();
  const spec = $derived(durationChartSpec(stats.stats, stats.sortKey));
</script>

<ChartPanel title="Duration (avg / max ms)" {spec} height={360} {onSliceClick} />
