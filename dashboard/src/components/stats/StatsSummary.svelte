<script lang="ts">
  import type { ToolStats } from '$lib/api/types';
  import { formatNumber } from '$lib/format';
  let { stats }: { stats: ToolStats } = $props();
  const totals = $derived(
    Object.values(stats).reduce(
      (acc, s) => ({
        calls: acc.calls + s.num_times_called,
        input: acc.input + s.input_tokens,
        output: acc.output + s.output_tokens,
      }),
      { calls: 0, input: 0, output: 0 },
    ),
  );
</script>

<div class="kpi-strip" role="group" aria-label="Tool usage totals">
  <div class="kpi">
    <span class="kpi-label">Calls</span>
    <span class="kpi-value">{formatNumber(totals.calls)}</span>
  </div>
  <div class="kpi">
    <span class="kpi-label">Input tokens</span>
    <span class="kpi-value">{formatNumber(totals.input)}</span>
  </div>
  <div class="kpi">
    <span class="kpi-label">Output tokens</span>
    <span class="kpi-value">{formatNumber(totals.output)}</span>
  </div>
  <div class="kpi kpi-total">
    <span class="kpi-label">Total tokens</span>
    <span class="kpi-value" data-testid="total-tokens"
      >{formatNumber(totals.input + totals.output)}</span
    >
  </div>
</div>

<style>
  .kpi-strip {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .kpi {
    flex: 1 1 0;
    min-width: 140px;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    padding: var(--space-3) var(--space-4);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
  }
  .kpi-total {
    border-color: var(--accent);
  }
  .kpi-label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .kpi-value {
    font-family: var(--font-mono);
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.1;
  }
  .kpi-total .kpi-value {
    color: var(--accent);
  }
</style>
