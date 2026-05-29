<script lang="ts">
  import type { ToolStatsTotals } from '$lib/api/types';
  import { formatNumber, formatDurationMs, formatTokens } from '$lib/format';

  interface Props {
    totals: ToolStatsTotals | undefined;
  }
  let { totals }: Props = $props();

  const errorRate = $derived(
    totals && totals.num_calls > 0 ? (totals.num_errors / totals.num_calls) * 100 : 0,
  );
  const avgDurationMs = $derived(
    totals && totals.num_calls > 0 ? totals.total_duration_ms / totals.num_calls : 0,
  );
</script>

<div class="grid">
  <div class="card">
    <div class="title" data-card-title>Calls</div>
    <div class="main">{totals ? formatNumber(totals.num_calls) : '—'}</div>
    <div class="sub">
      {totals ? `error rate ${errorRate.toFixed(2)} %` : ''}
    </div>
  </div>
  <div class="card">
    <div class="title" data-card-title>Tokens</div>
    <div class="main">{totals ? formatTokens(totals.total_tokens) : '—'}</div>
    <div class="sub">{totals ? `total` : ''}</div>
  </div>
  <div class="card">
    <div class="title" data-card-title>Time</div>
    <div class="main">{totals ? formatDurationMs(totals.total_duration_ms) : '—'}</div>
    <div class="sub">{totals ? `avg ${formatDurationMs(avgDurationMs)} / call` : ''}</div>
  </div>
  <div class="card">
    <div class="title" data-card-title>Errors</div>
    <div class="main">{totals ? formatNumber(totals.num_errors) : '—'}</div>
    <div class="sub">{totals ? `${errorRate.toFixed(2)} % rate` : ''}</div>
  </div>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .card {
    padding: var(--space-3);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
  .title {
    color: var(--text-muted);
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: var(--space-1);
  }
  .main {
    font-family: var(--font-mono);
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.1;
  }
  .sub {
    color: var(--text-muted);
    font-size: 0.8em;
    margin-top: var(--space-1);
  }
  @media (max-width: 800px) {
    .grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
