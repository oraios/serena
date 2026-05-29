<script lang="ts">
  import { stats } from '$lib/stores/stats.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import { formatDurationMs, formatNumber, percentile } from '$lib/format';
  import Icon from '../common/Icon.svelte';
  import { X, ArrowRight, TriangleAlert } from '@lucide/svelte';

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
  // Largest duration in the visible slice — scales the per-call latency bars.
  const maxVisible = $derived(Math.max(1, ...last20.map((r) => r.duration_ms)));

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
  const hasErrors = $derived((entry?.num_errors ?? 0) > 0);

  function hhmmss(epochSec: number): string {
    return new Date(epochSec * 1000).toISOString().slice(11, 19);
  }
</script>

{#if tool}
  <aside class="panel" aria-label="Tool details">
    <header>
      <div class="title">
        <span class="eyebrow">Tool details</span>
        <h3>{tool}</h3>
      </div>
      <button
        type="button"
        class="close"
        aria-label="Close"
        onclick={() => stats.setDrillTool(null)}><Icon icon={X} size={16} /></button
      >
    </header>

    {#if !entry}
      <p class="empty">No data for this tool.</p>
    {:else}
      <div class="metrics">
        <div class="tile span-3">
          <span class="tile-label">Calls</span>
          <span class="tile-value">{formatNumber(entry.num_times_called)}</span>
        </div>
        <div class="tile span-3" class:tile--bad={hasErrors} class:tile--ok={!hasErrors}>
          <span class="tile-label">Errors</span>
          <span class="tile-value"
            >{formatNumber(entry.num_errors ?? 0)}<span class="tile-sub"
              >{errorRate.toFixed(1)}%</span
            ></span
          >
        </div>
        <div class="tile">
          <span class="tile-label">Avg</span>
          <span class="tile-value">{formatDurationMs(avg)}</span>
        </div>
        <div class="tile">
          <span class="tile-label">p95</span>
          <span class="tile-value">{formatDurationMs(p95)}</span>
        </div>
        <div class="tile">
          <span class="tile-label">Max</span>
          <span class="tile-value">{formatDurationMs(entry.max_duration_ms ?? 0)}</span>
        </div>
        <div class="tile span-6">
          <span class="tile-label">Total time</span>
          <span class="tile-value">{formatDurationMs(entry.total_duration_ms ?? 0)}</span>
        </div>
      </div>
      <p class="hint">p95 based on the last {recordsForTool.length} calls in the live buffer.</p>

      {#if recentErrors.length > 0}
        <div class="errors-block">
          <h4><Icon icon={TriangleAlert} size={13} /> Recent errors</h4>
          <ul class="errors">
            {#each recentErrors as r (r.seq)}
              <li>
                <span class="err-time">{hhmmss(r.started_at)}</span>
                <span class="err-msg">{r.error_message}</span>
              </li>
            {/each}
          </ul>
        </div>
      {/if}

      <div class="calls-head">
        <h4>Last {Math.min(20, last20.length)} calls</h4>
        <span class="calls-scale">peak {formatDurationMs(maxVisible)}</span>
      </div>
      <ul class="calls">
        {#each last20 as r (r.seq)}
          <li class:is-err={!r.success}>
            <span class="dot" class:err={!r.success} aria-hidden="true"></span>
            <span class="c-time">{hhmmss(r.started_at)}</span>
            <span class="bar" aria-hidden="true">
              <span
                class="bar-fill"
                class:err={!r.success}
                style="width: {Math.max(3, (r.duration_ms / maxVisible) * 100)}%"
              ></span>
            </span>
            <span class="c-dur">{formatDurationMs(r.duration_ms)}</span>
          </li>
        {/each}
      </ul>

      {#if onOpenInTimeline}
        <button type="button" class="open" onclick={() => onOpenInTimeline?.(tool)}
          >Open in Timeline <Icon icon={ArrowRight} size={14} /></button
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
    width: 360px;
    background: var(--bg-elevated);
    border-left: 1px solid var(--border-strong);
    box-shadow: var(--shadow-elevated);
    overflow-y: auto;
    z-index: 40;
    animation: slide-in 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes slide-in {
    from {
      transform: translateX(16px);
      opacity: 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .panel {
      animation: none;
    }
  }

  header {
    position: sticky;
    top: 0;
    z-index: 1;
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--bg-elevated);
    border-bottom: 1px solid var(--border);
  }
  .title {
    min-width: 0;
  }
  .eyebrow {
    display: block;
    font-size: 0.66rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 2px;
  }
  header h3 {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 1rem;
    color: var(--text-primary);
    overflow-wrap: anywhere;
  }
  .close {
    margin-left: auto;
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .close:hover {
    color: var(--text-primary);
    background: var(--bg-secondary-btn);
    border-color: var(--border);
  }

  /* ---- metric tiles ---- */
  .metrics {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: var(--space-2);
    padding: var(--space-3) var(--space-3) 0;
  }
  .span-3 {
    grid-column: span 3;
  }
  .span-6 {
    grid-column: span 6;
  }
  .tile {
    grid-column: span 2;
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: var(--space-2) var(--space-3);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .tile-label {
    font-size: 0.66rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .tile-value {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.1;
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
  }
  .tile-sub {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-muted);
  }
  .tile--ok {
    border-color: color-mix(in srgb, var(--success) 35%, var(--border));
    background: color-mix(in srgb, var(--success) 8%, var(--bg-card));
  }
  .tile--ok .tile-value {
    color: var(--success);
  }
  .tile--bad {
    border-color: color-mix(in srgb, var(--log-error) 45%, var(--border));
    background: color-mix(in srgb, var(--log-error) 9%, var(--bg-card));
  }
  .tile--bad .tile-value,
  .tile--bad .tile-sub {
    color: var(--log-error);
  }

  .hint {
    color: var(--text-muted);
    font-size: 0.78rem;
    padding: 0 var(--space-3);
    margin: var(--space-2) 0 0;
  }

  h4 {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  /* ---- recent errors ---- */
  .errors-block {
    margin: var(--space-3) var(--space-3) 0;
    padding: var(--space-2) var(--space-3);
    background: color-mix(in srgb, var(--log-error) 7%, var(--bg-card));
    border: 1px solid color-mix(in srgb, var(--log-error) 30%, var(--border));
    border-left: 3px solid var(--log-error);
    border-radius: var(--radius);
  }
  .errors-block h4 {
    color: var(--log-error);
    margin-bottom: var(--space-2);
  }
  .errors {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .errors li {
    display: flex;
    gap: var(--space-2);
    font-size: 0.78rem;
  }
  .err-time {
    flex: none;
    font-family: var(--font-mono);
    color: var(--text-muted);
  }
  .err-msg {
    color: var(--text-secondary);
    overflow-wrap: anywhere;
  }

  /* ---- last N calls ---- */
  .calls-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: var(--space-4) var(--space-3) var(--space-2);
  }
  .calls-scale {
    font-size: 0.72rem;
    font-family: var(--font-mono);
    color: var(--text-muted);
  }
  .calls {
    list-style: none;
    margin: 0;
    padding: 0 var(--space-3) var(--space-3);
    display: flex;
    flex-direction: column;
  }
  .calls li {
    display: grid;
    grid-template-columns: 8px auto 1fr auto;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-1);
    border-radius: var(--radius-sm);
  }
  .calls li:hover {
    background: var(--bg-secondary-btn);
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--success);
  }
  .dot.err {
    background: var(--log-error);
  }
  .c-time {
    font-family: var(--font-mono);
    font-size: 0.76rem;
    color: var(--text-muted);
  }
  .bar {
    height: 6px;
    background: var(--bg-secondary-btn);
    border-radius: 99px;
    overflow: hidden;
  }
  .bar-fill {
    display: block;
    height: 100%;
    background: var(--accent);
    border-radius: 99px;
  }
  .bar-fill.err {
    background: var(--log-error);
  }
  .c-dur {
    font-family: var(--font-mono);
    font-size: 0.76rem;
    font-weight: 600;
    color: var(--text-primary);
    text-align: right;
    min-width: 52px;
  }

  .empty {
    color: var(--text-muted);
    padding: var(--space-3);
  }

  .open {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: calc(100% - 2 * var(--space-3));
    margin: 0 var(--space-3) var(--space-4);
    background: var(--accent);
    color: var(--text-on-accent);
    border: 0;
    border-radius: var(--radius);
    padding: var(--space-2) var(--space-3);
    font-weight: 600;
    cursor: pointer;
  }
  .open:hover {
    background: var(--accent-hover);
  }
</style>
