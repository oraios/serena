import type { ChartConfiguration } from 'chart.js';
import type { Context as DataLabelsContext } from 'chartjs-plugin-datalabels';
import type { ToolStats, ToolStatEntry } from './api/types';

export type ChartSpec = ChartConfiguration<'pie'> | ChartConfiguration<'bar'>;

function sortedEntries(stats: ToolStats, key: keyof ToolStatEntry): Array<[string, ToolStatEntry]> {
  return Object.entries(stats).sort((a, b) => b[1][key] - a[1][key]);
}

// Pie config for one metric. Colours are injected by ChartPanel from CSS vars;
// datalabels render the raw value in bold white on each slice — but only on
// slices ≥4% of the total, so tiny slices don't pile labels into a smudge.
// Legend sits below the pie so all three pies in the row share the same width.
const PIE_LABEL_MIN_FRACTION = 0.04;

export function pieSpec(stats: ToolStats, key: keyof ToolStatEntry): ChartConfiguration<'pie'> {
  const entries = sortedEntries(stats, key);
  return {
    type: 'pie',
    data: {
      labels: entries.map(([n]) => n),
      datasets: [{ data: entries.map(([, s]) => s[key]) }],
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

// Combined input/output token bar with two y axes (parity with main).
// Sorted by input tokens; output uses the same tool order. Datalabels off.
export function tokensBarSpec(stats: ToolStats): ChartConfiguration<'bar'> {
  const entries = sortedEntries(stats, 'input_tokens');
  return {
    type: 'bar',
    data: {
      labels: entries.map(([n]) => n),
      datasets: [
        { label: 'Input Tokens', data: entries.map(([, s]) => s.input_tokens), yAxisID: 'y' },
        { label: 'Output Tokens', data: entries.map(([, s]) => s.output_tokens), yAxisID: 'y1' },
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
