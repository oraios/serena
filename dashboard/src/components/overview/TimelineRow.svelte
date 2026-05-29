<script lang="ts">
  import type { ToolCallRecord } from '$lib/api/types';
  import { formatDurationMs } from '$lib/format';

  interface Props {
    record: ToolCallRecord;
  }
  let { record }: Props = $props();
  let expanded = $state(false);
  let showFullInput = $state(false);
  let showFullOutput = $state(false);

  const time = $derived(
    new Date(record.started_at * 1000).toISOString().split('T')[1].slice(0, 12),
  );
  const statusClass = $derived(record.success ? 'ok' : 'err');
</script>

<li class="row" class:expanded data-timeline-row>
  <button
    class="head"
    type="button"
    onclick={() => (expanded = !expanded)}
    aria-expanded={expanded}
  >
    <span class="chev">{expanded ? '▾' : '▸'}</span>
    <span class="time">{time}</span>
    <span class="tool">{record.tool}</span>
    <span class="duration">{formatDurationMs(record.duration_ms)}</span>
    <span class="status {statusClass}">{record.success ? 'ok' : 'ERR'}</span>
  </button>
  {#if expanded}
    <div class="detail">
      <div><span class="k">seq:</span> {record.seq}</div>
      <div><span class="k">started:</span> {new Date(record.started_at * 1000).toISOString()}</div>
      <div><span class="k">duration:</span> {formatDurationMs(record.duration_ms)}</div>
      {#if record.error_message}
        <div class="err"><span class="k">error:</span> {record.error_message}</div>
      {/if}
      <div class="block">
        <div class="k">input:</div>
        <pre class="code">{showFullInput || record.input_preview.length < 400
            ? record.input_preview
            : record.input_preview.slice(0, 400) + '…'}</pre>
        {#if record.input_preview.length >= 400}
          <button type="button" class="link" onclick={() => (showFullInput = !showFullInput)}>
            {showFullInput ? 'Show less' : 'Show full'}
          </button>
        {/if}
        {#if record.input_truncated}
          <div class="note">(server-truncated at 8 KB)</div>
        {/if}
      </div>
      <div class="block">
        <div class="k">output:</div>
        <pre class="code">{showFullOutput || record.output_preview.length < 400
            ? record.output_preview
            : record.output_preview.slice(0, 400) + '…'}</pre>
        {#if record.output_preview.length >= 400}
          <button type="button" class="link" onclick={() => (showFullOutput = !showFullOutput)}>
            {showFullOutput ? 'Show less' : 'Show full'}
          </button>
        {/if}
        {#if record.output_truncated}
          <div class="note">(server-truncated at 8 KB)</div>
        {/if}
      </div>
    </div>
  {/if}
</li>

<style>
  .row {
    border-bottom: 1px solid var(--border);
    list-style: none;
  }
  .head {
    width: 100%;
    display: grid;
    grid-template-columns: 24px 110px 1fr 70px 50px;
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
    color: var(--text-muted);
  }
  .tool {
    color: var(--text-primary);
  }
  .duration {
    color: var(--text-muted);
  }
  .status.ok {
    color: var(--success);
  }
  .status.err {
    color: var(--log-error);
  }
  .detail {
    padding: var(--space-2) var(--space-3) var(--space-3) calc(24px + var(--space-2));
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
