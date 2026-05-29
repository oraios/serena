import type { ChartConfiguration } from 'chart.js';
import type { Context as DataLabelsContext } from 'chartjs-plugin-datalabels';
import type { ToolStats, ToolStatEntry, ToolCallRecord } from './api/types';
import type { SortKey } from './stores/stats.svelte';

export type ChartSpec =
  | ChartConfiguration<'pie'>
  | ChartConfiguration<'bar'>
  | ChartConfiguration<'line'>;

function sortedEntries(stats: ToolStats, key: keyof ToolStatEntry): Array<[string, ToolStatEntry]> {
  return Object.entries(stats).sort((a, b) => {
    const av = (a[1][key] as number | undefined) ?? 0;
    const bv = (b[1][key] as number | undefined) ?? 0;
    return bv - av;
  });
}

// Pie config for one metric. Colours are injected by ChartPanel from CSS vars;
// datalabels render the raw value in bold white on each slice — but only on
// slices ≥4% of the total, so tiny slices don't pile labels into a smudge.
// Legend sits below the pie so all three pies in the row share the same width.
// NOTE: pies stay sorted by their OWN metric (largest slice first) — that's
// intrinsic to pie semantics. The store-wide `sortKey` only drives the order of
// the tokens bar + DurationChart, not the pies.
const PIE_LABEL_MIN_FRACTION = 0.04;

export function pieSpec(stats: ToolStats, key: keyof ToolStatEntry): ChartConfiguration<'pie'> {
  const entries = sortedEntries(stats, key);
  return {
    type: 'pie',
    data: {
      labels: entries.map(([n]) => n),
      datasets: [{ data: entries.map(([, s]) => (s[key] as number | undefined) ?? 0) }],
    },
    options: {
      plugins: {
        legend: { display: true, position: 'bottom', labels: {} },
        datalabels: {
          display: (ctx: DataLabelsContext) => {
            const data = ctx.dataset.data as number[];
            const total = data.reduce((a, b) => a + b, 0);
            if (total === 0) return false;
            return data[ctx.dataIndex] / total >= PIE_LABEL_MIN_FRACTION;
          },
          color: '#ffffff',
          font: { weight: 'bold' },
          formatter: (v) => v,
        },
      },
    },
  };
}

// Sort tools by a store-wide SortKey. Returns just the names, in descending
// score order; ties keep insertion order via Array.sort's stability.
export function sortToolsBy(stats: ToolStats, key: SortKey): string[] {
  const score = (v: ToolStatEntry): number => {
    switch (key) {
      case 'calls':
        return v.num_times_called;
      case 'tokens':
        return (v.input_tokens ?? 0) + (v.output_tokens ?? 0);
      case 'duration_total':
        return v.total_duration_ms ?? 0;
      case 'duration_avg':
        return v.num_times_called > 0 ? (v.total_duration_ms ?? 0) / v.num_times_called : 0;
      case 'errors':
        return v.num_errors ?? 0;
    }
  };
  return Object.entries(stats)
    .sort((a, b) => score(b[1]) - score(a[1]))
    .map(([name]) => name);
}

// Combined input/output token bar with two y axes (parity with main).
// Order driven by the store-wide `sortKey`. Datalabels off.
export function tokensBarSpec(stats: ToolStats, sortKey: SortKey): ChartConfiguration<'bar'> {
  const labels = sortToolsBy(stats, sortKey);
  const input = labels.map((n) => stats[n]?.input_tokens ?? 0);
  const output = labels.map((n) => stats[n]?.output_tokens ?? 0);
  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Input Tokens', data: input, yAxisID: 'y' },
        { label: 'Output Tokens', data: output, yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true,
      layout: { padding: { bottom: 8 } },
      plugins: {
        legend: { display: true, labels: {} },
        datalabels: { display: false },
      },
      scales: {
        x: { ticks: { maxRotation: 35, padding: 8 } },
        y: {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          title: { display: true, text: 'Input Tokens' },
        },
        y1: {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          title: { display: true, text: 'Output Tokens' },
          grid: { drawOnChartArea: false },
        },
      },
    },
  };
}

// Avg + Max duration per tool, ordered by sortKey. ChartPanel handles colors
// from CSS vars — we leave dataset background/border off here (the dual-axis
// branch in ChartPanel handles two-dataset bars).
export function durationChartSpec(stats: ToolStats, sortKey: SortKey): ChartConfiguration<'bar'> {
  const labels = sortToolsBy(stats, sortKey);
  const avg = labels.map((n) => {
    const e = stats[n];
    if (!e || e.num_times_called <= 0) return 0;
    return (e.total_duration_ms ?? 0) / e.num_times_called;
  });
  const max = labels.map((n) => stats[n]?.max_duration_ms ?? 0);
  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Avg (ms)', data: avg, yAxisID: 'y' },
        { label: 'Max (ms)', data: max, yAxisID: 'y1' },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { bottom: 8 } },
      plugins: {
        legend: { display: true, labels: {} },
        datalabels: { display: false },
      },
      scales: {
        x: { ticks: { maxRotation: 35, padding: 8 } },
        y: {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          title: { display: true, text: 'Avg (ms)' },
        },
        y1: {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          title: { display: true, text: 'Max (ms)' },
          grid: { drawOnChartArea: false },
        },
      },
    },
  };
}

export interface MinuteBucket {
  // epoch seconds for the START of this minute bucket
  start: number;
  count: number;
  byTool: Record<string, number>;
}

/**
 * Bucket records into per-minute counts. Returns windowMinutes+1 buckets aligned
 * so the current minute (containing nowEpochS) is the LAST bucket. Locks the
 * legacy off-by-one bug — calls landing in the in-progress minute mustn't be
 * dropped.
 */
export function bucketRecordsByMinute(
  records: ToolCallRecord[],
  nowEpochS: number,
  windowMinutes: number,
): MinuteBucket[] {
  const currentMinuteStart = Math.floor(nowEpochS / 60) * 60;
  const oldestMinuteStart = currentMinuteStart - windowMinutes * 60;
  const total = windowMinutes + 1;
  const buckets: MinuteBucket[] = Array.from({ length: total }, (_, i) => ({
    start: oldestMinuteStart + i * 60,
    count: 0,
    byTool: {},
  }));
  for (const r of records) {
    if (r.started_at < oldestMinuteStart) continue;
    if (r.started_at >= currentMinuteStart + 60) continue;
    const idx = Math.floor((r.started_at - oldestMinuteStart) / 60);
    if (idx < 0 || idx >= total) continue;
    buckets[idx].count += 1;
    buckets[idx].byTool[r.tool] = (buckets[idx].byTool[r.tool] ?? 0) + 1;
  }
  return buckets;
}

// Per-minute call rate. When `stacked` is true, draws one filled line per tool
// and stacks the y axis (B21); otherwise a single non-filled "Calls / min" line.
// ChartPanel re-applies colors from CSS vars after construction.
export function rateChartSpec(
  records: ToolCallRecord[],
  nowEpochS: number,
  windowMinutes: number,
  stacked: boolean,
  tools: string[],
): ChartConfiguration<'line'> {
  const buckets = bucketRecordsByMinute(records, nowEpochS, windowMinutes);
  const labels = buckets.map((b) =>
    new Date(b.start * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  );
  if (!stacked) {
    return {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Calls / min',
            data: buckets.map((b) => b.count),
            fill: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, labels: {} },
          datalabels: { display: false },
        },
        scales: {
          x: { ticks: { maxRotation: 0, padding: 4 } },
          y: { beginAtZero: true, ticks: { maxTicksLimit: 8 } },
        },
      },
    };
  }
  return {
    type: 'line',
    data: {
      labels,
      datasets: tools.map((t) => ({
        label: t,
        data: buckets.map((b) => b.byTool[t] ?? 0),
        fill: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: {} },
        datalabels: { display: false },
      },
      scales: {
        x: { stacked: true, ticks: { maxRotation: 0, padding: 4 } },
        y: { stacked: true, beginAtZero: true, ticks: { maxTicksLimit: 8 } },
      },
    },
  };
}
