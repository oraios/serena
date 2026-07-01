<script lang="ts">
  import { stats, type SortKey } from '$lib/stores/stats.svelte';

  const options: { value: SortKey; label: string }[] = [
    { value: 'calls', label: 'Calls' },
    { value: 'tokens', label: 'Tokens' },
    { value: 'duration_total', label: 'Total duration' },
    { value: 'duration_avg', label: 'Avg duration' },
    { value: 'errors', label: 'Errors' },
  ];
</script>

<label class="root">
  <span>Sort by</span>
  <select
    value={stats.sortKey}
    onchange={(e) => stats.setSortKey((e.target as HTMLSelectElement).value as SortKey)}
  >
    {#each options as o (o.value)}
      <option value={o.value}>{o.label}</option>
    {/each}
  </select>
</label>

<style>
  .root {
    display: inline-flex;
    gap: var(--space-2);
    align-items: center;
    color: var(--text-secondary);
  }
  select {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-primary);
    padding: var(--space-1) var(--space-2);
  }
</style>
