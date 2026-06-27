<script lang="ts">
  import type { ToolStatsSummary } from '$lib/api/types';
  let { stats }: { stats: ToolStatsSummary } = $props();
  const sorted = $derived(Object.entries(stats).sort((a, b) => b[1].num_calls - a[1].num_calls));
  const max = $derived(Math.max(1, ...sorted.map(([, s]) => s.num_calls)));
</script>

{#if sorted.length}
  <div class="bars">
    {#each sorted as [name, s] (name)}
      <div class="bar-row">
        <span class="bar-name" data-testid="tool-bar-name">{name}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width:{(s.num_calls / max) * 100}%"></div>
        </div>
        <span class="bar-count">{s.num_calls}</span>
      </div>
    {/each}
  </div>
{:else}
  <div class="no-stats-message">No tool usage yet.</div>
{/if}

<style>
  .bar-row {
    display: grid;
    grid-template-columns: 1fr 3fr auto;
    gap: var(--space-2);
    align-items: center;
    margin: var(--space-1) 0;
  }
  .bar-name {
    font-family: var(--font-mono);
    font-size: 12px;
  }
  .bar-track {
    background: var(--bg-secondary-btn);
    border-radius: var(--radius-sm);
    height: 14px;
  }
  .bar-fill {
    background: var(--accent);
    height: 100%;
    border-radius: var(--radius-sm);
  }
  .bar-count {
    font-size: 12px;
    color: var(--text-muted);
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
