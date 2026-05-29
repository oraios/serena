<script lang="ts">
  import {
    formatDurationMs,
    formatNumber,
    formatTokens,
    formatRelativeTime,
    prettyArgs,
  } from '$lib/format';
  import type { TimelineDisplayRow } from '$lib/timelineRows';
  import type { RowStatus } from '$lib/timelineRows';
  import { clock } from '$lib/stores/clock.svelte';
  import Icon from '../common/Icon.svelte';
  import {
    ChevronRight,
    ChevronDown,
    X,
    CheckCircle,
    XCircle,
    Loader,
    Ban,
    Copy,
    Check,
  } from '@lucide/svelte';

  interface Props {
    row: TimelineDisplayRow;
    isLatest?: boolean;
    oncancel?: (_row: TimelineDisplayRow) => void;
  }
  let { row, isLatest = false, oncancel }: Props = $props();
  let expanded = $state(false);
  let showFullInput = $state(false);
  let showFullOutput = $state(false);
  let copied = $state<'input' | 'output' | null>(null);

  // Keep the shared wall-clock ticking only while rows are mounted (ref-counted).
  $effect(() => {
    clock.start();
    return () => clock.stop();
  });

  // Same status → icon/label mapping the filter chips use (Timeline.svelte), so a
  // row's glyph matches its chip.
  const STATUS_ICON: Record<RowStatus, typeof CheckCircle> = {
    success: CheckCircle,
    fail: XCircle,
    running: Loader,
    cancelled: Ban,
  };
  const STATUS_TITLE: Record<RowStatus, string> = {
    success: 'Success',
    fail: 'Failed',
    running: 'Running',
    cancelled: 'Cancelled',
  };

  const time = $derived(
    Number.isFinite(row.startedAt)
      ? new Date(row.startedAt * 1000).toISOString().split('T')[1].slice(0, 8)
      : '--:--:--',
  );
  const relTime = $derived(formatRelativeTime(row.startedAt, clock.now));
  const durationLabel = $derived(
    row.kind === 'history'
      ? formatDurationMs(row.record.duration_ms)
      : row.execution.duration_ms != null
        ? formatDurationMs(row.execution.duration_ms)
        : '—',
  );

  // Pretty-printed input/output (only history rows carry previews).
  const fmtInput = $derived(row.kind === 'history' ? prettyArgs(row.record.input_preview) : '');
  const fmtOutput = $derived(row.kind === 'history' ? prettyArgs(row.record.output_preview) : '');

  async function copy(which: 'input' | 'output', text: string) {
    try {
      await navigator.clipboard.writeText(text);
      copied = which;
      setTimeout(() => {
        if (copied === which) copied = null;
      }, 1200);
    } catch {
      // Clipboard unavailable (insecure context / denied) — silently no-op.
    }
  }
</script>

<li class="row" class:expanded class:latest={isLatest} data-timeline-row data-status={row.status}>
  <div class="head-wrap">
    <button
      class="head"
      type="button"
      onclick={() => (expanded = !expanded)}
      aria-expanded={expanded}
    >
      <span class="chev"><Icon icon={expanded ? ChevronDown : ChevronRight} size={12} /></span>
      <span class="time">
        <span class="abs">{time}</span>
        {#if relTime}<span class="rel">{relTime}</span>{/if}
      </span>
      <span class="tool">{row.tool}</span>
      {#if row.kind === 'history'}
        <span class="tokens" title="input / output tokens">
          <span class="tok-in">↓{formatTokens(row.record.input_tokens)}</span>
          <span class="tok-out">↑{formatTokens(row.record.output_tokens)}</span>
        </span>
      {:else}
        <span class="tokens"></span>
      {/if}
      <span class="duration">{durationLabel}</span>
      <span class="status {row.status}" title={STATUS_TITLE[row.status]}>
        <Icon
          icon={STATUS_ICON[row.status]}
          size={14}
          label={STATUS_TITLE[row.status]}
          class={row.status === 'running' ? 'spin' : ''}
        />
      </span>
    </button>
    {#if row.kind === 'live' && row.status === 'running' && oncancel}
      <button
        type="button"
        class="cancel"
        aria-label="Cancel {row.tool}"
        data-testid="cancel-btn"
        onclick={() => oncancel?.(row)}><Icon icon={X} size={12} /></button
      >
    {/if}
  </div>
  {#if expanded}
    {#if row.kind === 'history'}
      {@const record = row.record}
      <div class="detail">
        <div><span class="k">seq:</span> {record.seq}</div>
        <div>
          <span class="k">started:</span>
          {new Date(record.started_at * 1000).toISOString()}
        </div>
        <div><span class="k">duration:</span> {formatDurationMs(record.duration_ms)}</div>
        <div>
          <span class="k">tokens:</span>
          <span class="tok-in">↓ {formatNumber(record.input_tokens)} in</span>
          <span class="tok-sep">·</span>
          <span class="tok-out">↑ {formatNumber(record.output_tokens)} out</span>
        </div>
        {#if record.error_message}
          <div class="err"><span class="k">error:</span> {record.error_message}</div>
        {/if}
        <div class="block">
          <div class="block-head">
            <span class="k">input:</span>
            <button
              type="button"
              class="copy"
              aria-label="Copy input"
              onclick={() => copy('input', fmtInput)}
            >
              <Icon icon={copied === 'input' ? Check : Copy} size={12} />
              {copied === 'input' ? 'Copied' : 'Copy'}
            </button>
          </div>
          <pre class="code">{showFullInput || fmtInput.length < 400
              ? fmtInput
              : fmtInput.slice(0, 400) + '…'}</pre>
          {#if fmtInput.length >= 400}
            <button type="button" class="link" onclick={() => (showFullInput = !showFullInput)}>
              {showFullInput ? 'Show less' : 'Show full'}
            </button>
          {/if}
          {#if record.input_truncated}
            <div class="note">(server-truncated at 8 KB)</div>
          {/if}
        </div>
        <div class="block">
          <div class="block-head">
            <span class="k">output:</span>
            <button
              type="button"
              class="copy"
              aria-label="Copy output"
              onclick={() => copy('output', fmtOutput)}
            >
              <Icon icon={copied === 'output' ? Check : Copy} size={12} />
              {copied === 'output' ? 'Copied' : 'Copy'}
            </button>
          </div>
          <pre class="code">{showFullOutput || fmtOutput.length < 400
              ? fmtOutput
              : fmtOutput.slice(0, 400) + '…'}</pre>
          {#if fmtOutput.length >= 400}
            <button type="button" class="link" onclick={() => (showFullOutput = !showFullOutput)}>
              {showFullOutput ? 'Show less' : 'Show full'}
            </button>
          {/if}
          {#if record.output_truncated}
            <div class="note">(server-truncated at 8 KB)</div>
          {/if}
        </div>
      </div>
    {:else}
      {@const exec = row.execution}
      <div class="detail">
        <div><span class="k">task id:</span> #{exec.task_id}</div>
        <div>
          <span class="k">name:</span>
          {exec.display_name || exec.name}
        </div>
        {#if exec.started_at}
          <div>
            <span class="k">started:</span>
            {new Date(exec.started_at * 1000).toISOString()}
          </div>
        {:else}
          <div><span class="k">started:</span> (queued, not yet running)</div>
        {/if}
        {#if exec.finished_at}
          <div>
            <span class="k">finished:</span>
            {new Date(exec.finished_at * 1000).toISOString()}
          </div>
        {/if}
        {#if exec.error_message}
          <div class="err"><span class="k">error:</span> {exec.error_message}</div>
        {/if}
      </div>
    {/if}
  {/if}
</li>

<style>
  .row {
    border-bottom: 1px solid var(--border);
    list-style: none;
  }
  .row.latest {
    background: color-mix(in srgb, var(--accent) 6%, transparent);
    border-left: 3px solid var(--accent);
  }
  .head-wrap {
    display: flex;
    align-items: center;
  }
  .head {
    flex: 1;
    display: grid;
    grid-template-columns: 20px auto 1fr auto 64px 22px;
    gap: var(--space-2);
    align-items: center;
    background: transparent;
    border: 0;
    color: var(--text-primary);
    cursor: pointer;
    padding: var(--space-1) var(--space-2);
    text-align: left;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .head:hover {
    background: var(--bg-secondary-btn);
  }
  .chev {
    color: var(--text-muted);
  }
  .time {
    display: flex;
    align-items: baseline;
    gap: var(--space-1);
    white-space: nowrap;
  }
  .time .abs {
    color: var(--text-muted);
  }
  .time .rel {
    color: var(--text-muted);
    opacity: 0.7;
    font-size: 0.85em;
  }
  .tool {
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tokens {
    display: inline-flex;
    gap: var(--space-2);
    color: var(--text-muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .tok-in {
    color: var(--accent);
  }
  .tok-out {
    color: var(--success);
  }
  .tok-sep {
    color: var(--text-muted);
  }
  .duration {
    color: var(--text-muted);
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .status {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .status.success {
    color: var(--success);
  }
  .status.fail {
    color: var(--log-error);
  }
  .status.running {
    color: var(--accent);
  }
  .status.cancelled {
    color: var(--text-muted);
  }
  .status :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .cancel {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--log-error);
    font-weight: bold;
    font-size: 16px;
    line-height: 1;
    padding: 0 var(--space-2);
  }
  .cancel:hover {
    background: var(--bg-secondary-btn);
  }
  .detail {
    padding: var(--space-2) var(--space-3) var(--space-3) calc(20px + var(--space-2));
    font-family: var(--font-mono);
    font-size: 0.85em;
    color: var(--text-primary);
  }
  .k {
    color: var(--text-muted);
    margin-right: var(--space-1);
  }
  .block {
    margin-top: var(--space-2);
  }
  .block-head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .copy {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    font-family: inherit;
    font-size: 0.9em;
    padding: 1px var(--space-1);
  }
  .copy:hover {
    background: var(--bg-secondary-btn);
    color: var(--text-primary);
  }
  .code {
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-2);
    white-space: pre-wrap;
    word-break: break-all;
    margin: var(--space-1) 0;
  }
  .link {
    background: transparent;
    border: 0;
    color: var(--accent);
    cursor: pointer;
    padding: 0;
  }
  .note {
    color: var(--text-muted);
    font-size: 0.85em;
  }
  .err {
    color: var(--log-error);
  }
</style>
