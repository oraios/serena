<script lang="ts">
  import { createTimelineStore } from '$lib/stores/timeline.svelte';
  import FilterDropdown from '../common/FilterDropdown.svelte';
  import TimelineRow from './TimelineRow.svelte';

  // Plain (non-type) import so `typeof createTimelineStore` works for ReturnType.
  type TimelineStore = ReturnType<typeof createTimelineStore>;

  interface Props {
    store: TimelineStore;
    toolNames: string[];
  }
  let { store, toolNames }: Props = $props();

  const filterOpts = $derived(toolNames.map((n) => ({ value: n, label: n })));
  const totalPages = $derived(Math.max(1, Math.ceil(store.records.length / store.pageSize)));
  const start = $derived((store.page - 1) * store.pageSize);
  const visible = $derived(store.records.slice(start, start + store.pageSize));
</script>

<section class="card">
  <header class="head">
    <h3 class="title">Tool Call Timeline</h3>
    <div class="controls">
      <FilterDropdown
        options={filterOpts}
        value={store.filter}
        placeholder="All tools"
        onChange={(v) => store.setFilter(v)}
      />
      <button
        type="button"
        class="ctrl"
        aria-label={store.paused ? 'Resume' : 'Pause'}
        onclick={() => store.togglePause()}>{store.paused ? '▶ Resume' : '⏸ Pause'}</button
      >
      <button type="button" class="ctrl" aria-label="Clear view" onclick={() => store.clearView()}>
        ↻ Clear
      </button>
    </div>
  </header>

  {#if store.pausedGap}
    <div class="banner">
      ({store.pausedGap.toLocaleString()} calls while paused — view truncated)
    </div>
  {/if}
  {#if store.error}
    <div class="banner error">Live updates paused — reconnecting…</div>
  {/if}

  <div class="pager">
    <label>
      Page size
      <select
        onchange={(e) => store.setPageSize(Number((e.target as HTMLSelectElement).value))}
        value={String(store.pageSize)}
      >
        <option value="25">25</option>
        <option value="50">50</option>
        <option value="100">100</option>
      </select>
    </label>
    <span class="grow"></span>
    <button type="button" onclick={() => store.setPage(1)} disabled={store.page <= 1}>«</button>
    <button type="button" onclick={() => store.setPage(store.page - 1)} disabled={store.page <= 1}
      >‹</button
    >
    <span class="pageinfo">page {store.page} of {totalPages}</span>
    <button
      type="button"
      onclick={() => store.setPage(store.page + 1)}
      disabled={store.page >= totalPages}>›</button
    >
    <button
      type="button"
      onclick={() => store.setPage(totalPages)}
      disabled={store.page >= totalPages}>»</button
    >
  </div>

  <ul class="list">
    {#each visible as r (r.seq)}
      <TimelineRow record={r} />
    {/each}
    {#if visible.length === 0}
      <li class="empty">No calls yet.</li>
    {/if}
  </ul>
</section>

<style>
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3);
    box-shadow: var(--shadow);
    margin-bottom: var(--space-3);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-2);
  }
  .title {
    margin: 0;
    font-size: 1em;
  }
  .controls {
    margin-left: auto;
    display: flex;
    gap: var(--space-2);
  }
  .ctrl {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
    font-family: inherit;
  }
  .ctrl:hover {
    background: var(--bg-secondary-btn);
  }
  .pager {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border);
  }
  .pager button {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }
  .pager button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .grow {
    flex: 1;
  }
  .pageinfo {
    color: var(--text-muted);
    font-size: 0.9em;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .empty {
    color: var(--text-muted);
    padding: var(--space-3);
    text-align: center;
  }
  .banner {
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-2);
    color: var(--text-muted);
    margin-bottom: var(--space-2);
  }
  .banner.error {
    border-color: var(--log-error);
    color: var(--log-error);
  }
</style>
