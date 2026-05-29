<script lang="ts">
  import { stats } from '$lib/stores/stats.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import { formatDurationMs, formatNumber, percentile } from '$lib/format';

  interface Props {
    onOpenInTimeline?: (_tool: string) => void;
  }
  let { onOpenInTimeline }: Props = $props();

  const tool = $derived(stats.drillTool);
  const entry = $derived(tool ? stats.stats[tool] : undefined);

  const recordsForTool = $derived(tool ? timeline.records.filter((r) => r.tool === tool) : []);
  const durations = $derived(recordsForTool.map((r) => r.duration_ms));
  const p95 = $derived(percentile(durations, 95));
  const recentErrors = $derived(recordsForTool.filter((r) => !r.success).slice(0, 5));
  const last20 = $derived(recordsForTool.slice(0, 20));

  const errorRate = $derived(
    entry && entry.num_times_called > 0
      ? ((entry.num_errors ?? 0) / entry.num_times_called) * 100
      : 0,
  );
  const avg = $derived(
    entry && entry.num_times_called > 0
      ? (entry.total_duration_ms ?? 0) / entry.num_times_called
      : 0,
  );
</script>

{#if tool}
  <aside class="panel" aria-label="Tool details">
    <header>
      <h3>{tool}</h3>
      <button
        type="button"
        class="close"
        aria-label="Close"
        onclick={() => stats.setDrillTool(null)}>×</button
      >
    </header>
    {#if !entry}
      <p class="empty">No data for this tool.</p>
    {:else}
      <dl class="grid">
        <dt>Calls</dt>
        <dd>{formatNumber(entry.num_times_called)}</dd>
        <dt>Errors</dt>
        <dd>{formatNumber(entry.num_errors ?? 0)} ({errorRate.toFixed(2)} %)</dd>
        <dt>Avg</dt>
        <dd>{formatDurationMs(avg)}</dd>
        <dt>p95</dt>
        <dd>{formatDurationMs(p95)}</dd>
        <dt>Total</dt>
        <dd>{formatDurationMs(entry.total_duration_ms ?? 0)}</dd>
        <dt>Max</dt>
        <dd>{formatDurationMs(entry.max_duration_ms ?? 0)}</dd>
      </dl>
      <p class="hint">p95 based on last {recordsForTool.length} calls in the live buffer.</p>

      {#if recentErrors.length > 0}
        <h4>Recent errors</h4>
        <ul class="errors">
          {#each recentErrors as r (r.seq)}
            <li>
              {new Date(r.started_at * 1000).toISOString().slice(11, 19)} — {r.error_message}
            </li>
          {/each}
        </ul>
      {/if}

      <h4>Last {Math.min(20, last20.length)} calls</h4>
      <ul class="calls">
        {#each last20 as r (r.seq)}
          <li>
            <span>{new Date(r.started_at * 1000).toISOString().slice(11, 19)}</span>
            <span>{formatDurationMs(r.duration_ms)}</span>
            <span class={r.success ? 'ok' : 'err'}>{r.success ? 'ok' : 'ERR'}</span>
          </li>
        {/each}
      </ul>

      {#if onOpenInTimeline}
        <button type="button" class="open" onclick={() => onOpenInTimeline?.(tool)}
          >Open in Timeline →</button
        >
      {/if}
    {/if}
  </aside>
{/if}

<style>
  .panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 340px;
    background: var(--bg-elevated);
    border-left: 1px solid var(--border-strong);
    box-shadow: var(--shadow-elevated);
    padding: var(--space-3);
    overflow-y: auto;
    z-index: 40;
  }
  header {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-2);
  }
  header h3 {
    margin: 0;
    font-family: var(--font-mono);
    color: var(--text-primary);
  }
  .close {
    margin-left: auto;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    font-size: 1.4em;
    cursor: pointer;
  }
  .close:hover {
    color: var(--accent);
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-1) var(--space-2);
    margin: 0;
  }
  dt {
    color: var(--text-secondary);
  }
  dd {
    margin: 0;
    font-weight: 600;
    color: var(--text-primary);
  }
  .hint {
    color: var(--text-muted);
    font-size: 0.85em;
  }
  h4 {
    margin: var(--space-3) 0 var(--space-1);
    font-size: 0.95em;
    color: var(--text-primary);
  }
  .errors,
  .calls {
    list-style: none;
    margin: 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
    color: var(--text-primary);
  }
  .calls li {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: var(--space-2);
  }
  .ok {
    color: var(--success);
  }
  .err {
    color: var(--log-error);
  }
  .empty {
    color: var(--text-muted);
  }
  .open {
    margin-top: var(--space-3);
    background: var(--accent);
    color: var(--text-on-accent);
    border: 0;
    border-radius: var(--radius);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
  }
  .open:hover {
    background: var(--accent-hover);
  }
</style>
