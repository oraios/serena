<script lang="ts">
  import { createTimelineStore } from '$lib/stores/timeline.svelte';
  import type { createExecutionsStore } from '$lib/stores/executions.svelte';
  import type { QueuedExecution } from '$lib/api/types';
  import {
    ALL_STATUSES,
    mergeTimelineRows,
    type RowStatus,
    type TimelineDisplayRow,
  } from '$lib/timelineRows';
  import FilterDropdown from '../common/FilterDropdown.svelte';
  import Icon from '../common/Icon.svelte';
  import TimelineRow from './TimelineRow.svelte';
  import { Play, Pause, RotateCw, X, CheckCircle, XCircle, Loader, Ban } from '@lucide/svelte';

  type TimelineStore = ReturnType<typeof createTimelineStore>;
  type ExecutionsStore = ReturnType<typeof createExecutionsStore>;

  interface Props {
    store: TimelineStore;
    executions: ExecutionsStore;
    toolNames: string[];
    oncancelexecution: (_ex: QueuedExecution) => void;
  }
  let { store, executions, toolNames, oncancelexecution }: Props = $props();

  const STATUS_LABELS: Record<RowStatus, string> = {
    success: 'Success',
    fail: 'Failed',
    running: 'Running',
    cancelled: 'Cancelled',
  };

  const STATUS_ICONS: Record<RowStatus, typeof CheckCircle> = {
    success: CheckCircle,
    fail: XCircle,
    running: Loader,
    cancelled: Ban,
  };

  const filterOpts = $derived(toolNames.map((n) => ({ value: n, label: n })));

  const mergedRows = $derived(
    mergeTimelineRows({
      records: store.records,
      queued: executions.queued,
      cancelled: executions.cancelled,
      tool: store.filter,
      statuses: store.statusFilter,
    }),
  );
  const totalPages = $derived(Math.max(1, Math.ceil(mergedRows.length / store.pageSize)));
  const start = $derived((store.page - 1) * store.pageSize);
  const visible = $derived(mergedRows.slice(start, start + store.pageSize));

  function handleCancel(row: TimelineDisplayRow) {
    if (row.kind === 'live' && row.status === 'running') {
      oncancelexecution(row.execution);
    }
  }
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
        onclick={() => store.togglePause()}
        ><Icon icon={store.paused ? Play : Pause} size={12} />
        {store.paused ? 'Resume' : 'Pause'}</button
      >
      <button type="button" class="ctrl" aria-label="Clear view" onclick={() => store.clearView()}>
        <Icon icon={RotateCw} size={12} /> Clear
      </button>
    </div>
  </header>

  <div class="status-filter" role="group" aria-label="Status filter">
    {#each ALL_STATUSES as s (s)}
      <button
        type="button"
        class="chip {s}"
        class:active={store.statusFilter.has(s)}
        aria-pressed={store.statusFilter.has(s)}
        onclick={() => store.toggleStatus(s)}
        ><Icon icon={STATUS_ICONS[s]} size={12} />
        {STATUS_LABELS[s]}</button
      >
    {/each}
  </div>

  {#if executions.cancelError}
    <div class="banner error" role="alert">
      Cancel failed: {executions.cancelError}
      <button
        type="button"
        class="link"
        onclick={() => executions.clearCancelError()}
        aria-label="Dismiss"><Icon icon={X} size={14} /></button
      >
    </div>
  {/if}
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
    {#each visible as r, i (r.key)}
      <TimelineRow
        row={r}
        isLatest={store.page === 1 && i === 0}
        oncancel={r.kind === 'live' && r.status === 'running' ? handleCancel : undefined}
      />
    {/each}
    {#if visible.length === 0}
      <li class="empty">No calls match the current filter.</li>
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
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
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
  .status-filter {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-muted);
    border-radius: 999px;
    padding: 2px 10px;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.85em;
  }
  .chip:hover {
    background: var(--bg-secondary-btn);
  }
  .chip.active {
    color: var(--text-primary);
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }
  .chip.success.active {
    border-color: var(--success);
    background: color-mix(in srgb, var(--success) 12%, transparent);
  }
  .chip.fail.active {
    border-color: var(--log-error);
    background: color-mix(in srgb, var(--log-error) 12%, transparent);
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
    display: flex;
    align-items: center;
    gap: var(--space-2);
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
  .link {
    background: transparent;
    border: 0;
    color: inherit;
    cursor: pointer;
    margin-left: auto;
    padding: 0 var(--space-2);
    font-size: 1.1em;
  }
</style>
