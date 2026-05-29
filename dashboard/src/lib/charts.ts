import type { ToolStats, ToolStatEntry } from './api/types';

export interface FrappeData {
  labels: string[];
  datasets: Array<{ name?: string; values: number[] }>;
}

function sortedEntries(stats: ToolStats, key: keyof ToolStatEntry): Array<[string, ToolStatEntry]> {
  return Object.entries(stats).sort((a, b) => b[1][key] - a[1][key]);
}

export function toPieData(stats: ToolStats, key: keyof ToolStatEntry): FrappeData {
  const entries = sortedEntries(stats, key);
  return {
    labels: entries.map(([n]) => n),
    datasets: [{ values: entries.map(([, s]) => s[key]) }],
  };
}

export function toSingleSeriesBar(
  stats: ToolStats,
  key: 'input_tokens' | 'output_tokens',
  name: string,
): FrappeData {
  const entries = sortedEntries(stats, key);
  return {
    labels: entries.map(([n]) => n),
    datasets: [{ name, values: entries.map(([, s]) => s[key]) }],
  };
}
