import { describe, it, expect } from 'vitest';
import { pieSpec, tokensBarSpec } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  a: { num_times_called: 2, input_tokens: 10, output_tokens: 5 },
  b: { num_times_called: 8, input_tokens: 40, output_tokens: 20 },
};

describe('pieSpec', () => {
  it('builds a pie config for a metric, sorted descending', () => {
    const spec = pieSpec(stats, 'num_times_called');
    expect(spec.type).toBe('pie');
    expect(spec.data.labels).toEqual(['b', 'a']);
    expect(spec.data.datasets[0].data).toEqual([8, 2]);
  });
  it('renders the legend below the pie', () => {
    const spec = pieSpec(stats, 'input_tokens');
    expect(spec.options?.plugins?.legend?.position).toBe('bottom');
  });
  it('hides datalabels on slices smaller than 4% of the total', () => {
    const spec = pieSpec(stats, 'num_times_called');
    const display = spec.options?.plugins?.datalabels?.display;
    expect(typeof display).toBe('function');
    // a 5/100 slice (5%) is shown; a 3/100 slice (3%) is hidden.
    // Datalabels passes a context with { dataIndex, dataset: { data } }.
    const show = (display as (ctx: unknown) => boolean)({
      dataIndex: 0,
      dataset: { data: [5, 95] },
    });
    const hide = (display as (ctx: unknown) => boolean)({
      dataIndex: 0,
      dataset: { data: [3, 97] },
    });
    expect(show).toBe(true);
    expect(hide).toBe(false);
  });
});

describe('tokensBarSpec', () => {
  it('builds a dual-dataset bar sorted descending by input tokens', () => {
    const spec = tokensBarSpec(stats);
    expect(spec.type).toBe('bar');
    expect(spec.data.labels).toEqual(['b', 'a']);
    expect(spec.data.datasets).toHaveLength(2);
  });
  it('assigns input to the left y axis and output to the right y1 axis', () => {
    const spec = tokensBarSpec(stats);
    const [input, output] = spec.data.datasets;
    expect(input.label).toBe('Input Tokens');
    expect(input.data).toEqual([40, 10]);
    expect(input.yAxisID).toBe('y');
    expect(output.label).toBe('Output Tokens');
    expect(output.data).toEqual([20, 5]);
    expect(output.yAxisID).toBe('y1');
  });
  it('disables datalabels on the bar', () => {
    const spec = tokensBarSpec(stats);
    expect(spec.options?.plugins?.datalabels?.display).toBe(false);
  });
  it('caps x-tick rotation and pads the axis so labels do not crowd', () => {
    const spec = tokensBarSpec(stats);
    const xScale = spec.options?.scales?.x as
      | { ticks?: { maxRotation?: number; padding?: number } }
      | undefined;
    expect(xScale?.ticks?.maxRotation).toBe(35);
    expect(xScale?.ticks?.padding).toBe(8);
    const layoutPadding = (spec.options?.layout?.padding ?? {}) as { bottom?: number };
    expect(layoutPadding.bottom).toBe(8);
  });
});
