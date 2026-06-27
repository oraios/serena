<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchUnreadNews, markNewsRead } from '$lib/api/endpoints';
  import { sortNewsEntries } from '$lib/news';
  let items = $state<Array<[string, string]>>([]);
  async function load() {
    items = sortNewsEntries((await fetchUnreadNews()).news);
  }
  onMount(() => {
    void load();
  });
  async function dismiss(id: string) {
    await markNewsRead(id);
    items = items.filter(([k]) => k !== id);
  }
</script>

{#if items.length}
  <section class="news-section">
    <h2>What's New</h2>
    {#each items as [id, html] (id)}
      <div class="news-item">
        <!-- eslint-disable-next-line svelte/no-at-html-tags -- server-trusted news HTML from Serena backend -->
        <div class="news-body">{@html html}</div>
        <button class="news-dismiss" onclick={() => dismiss(id)}>Mark as read</button>
      </div>
    {/each}
  </section>
{/if}

<style>
  .news-item {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3);
    margin-bottom: var(--space-3);
    background: var(--bg-card);
    box-shadow: var(--shadow);
  }
  .news-dismiss {
    margin-top: var(--space-2);
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-3);
    cursor: pointer;
    color: var(--text-primary);
  }
</style>
