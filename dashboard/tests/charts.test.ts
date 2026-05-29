import { describe, it, expect } from 'vitest';
import { toPieData, toSingleSeriesBar } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  a: { num_times_called: 2, input_tokens: 10, output_tokens: 5 },
  b: { num_times_called: 8, input_tokens: 40, output_tokens: 20 },
};

describe('charts data', () => {
  it('builds pie data for a chosen metric, sorted descending', () => {
    const pie = toPieData(stats, 'num_times_called');
    expect(pie.labels).toEqual(['b', 'a']);
    expect(pie.datasets[0].values).toEqual([8, 2]);
  });
  it('builds a single-series bar for one token metric, sorted descending', () => {
    const bar = toSingleSeriesBar(stats, 'output_tokens', 'Output Tokens');
    expect(bar.labels).toEqual(['b', 'a']);
    expect(bar.datasets).toHaveLength(1);
    expect(bar.datasets[0].name).toBe('Output Tokens');
    expect(bar.datasets[0].values).toEqual([20, 5]);
  });
});
