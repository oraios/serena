<script lang="ts">
  import type { ToolStats } from '$lib/api/types';
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

<table class="stats-summary-block">
  <tbody>
    <tr><td>Total calls</td><td>{totals.calls}</td></tr>
    <tr><td>Total input tokens</td><td>{totals.input}</td></tr>
    <tr><td>Total output tokens</td><td>{totals.output}</td></tr>
    <tr><td>Total tokens</td><td data-testid="total-tokens">{totals.input + totals.output}</td></tr>
  </tbody>
</table>

<style>
  table {
    width: 100%;
    border-collapse: collapse;
  }
  td {
    padding: var(--space-2);
    border-bottom: 1px solid var(--border);
    font-family: var(--font-mono);
  }
</style>
