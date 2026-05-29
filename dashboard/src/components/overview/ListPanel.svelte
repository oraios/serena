<script lang="ts">
  import Card from '../common/Card.svelte';
  import Collapsible from '../common/Collapsible.svelte';
  let { title, items }: { title: string; items: Array<{ name: string; active?: boolean }> } =
    $props();
</script>

<Card>
  <Collapsible {title}>
    {#if items.length}
      <ul class="list-panel">
        {#each items as item (item.name)}<li class:active={item.active}>{item.name}</li>{/each}
      </ul>
    {:else}
      <div class="no-stats-message">None.</div>
    {/if}
  </Collapsible>
</Card>

<style>
  .list-panel {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 340px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .list-panel li {
    padding: var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-elevated);
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-primary);
  }
  .list-panel li.active {
    background: var(--accent);
    color: var(--text-on-accent);
    border-color: var(--accent);
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
