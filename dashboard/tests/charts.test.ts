import { describe, it, expect } from 'vitest';
import {
  pieSpec,
  tokensBarSpec,
  durationChartSpec,
  bucketRecordsByMinute,
  rateChartSpec,
  sortToolsBy,
} from '../src/lib/charts';
import type { ToolStats, ToolCallRecord } from '../src/lib/api/types';

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
  it('builds a dual-dataset bar ordered by the sortKey', () => {
    // 'calls' → b (8) before a (2)
    const spec = tokensBarSpec(stats, 'calls');
    expect(spec.type).toBe('bar');
    expect(spec.data.labels).toEqual(['b', 'a']);
    expect(spec.data.datasets).toHaveLength(2);
  });
  it('assigns input to the left y axis and output to the right y1 axis', () => {
    const spec = tokensBarSpec(stats, 'tokens');
    // tokens → b (60) before a (15)
    const [input, output] = spec.data.datasets;
    expect(input.label).toBe('Input Tokens');
    expect(input.data).toEqual([40, 10]);
    expect(input.yAxisID).toBe('y');
    expect(output.label).toBe('Output Tokens');
    expect(output.data).toEqual([20, 5]);
    expect(output.yAxisID).toBe('y1');
  });
  it('disables datalabels on the bar', () => {
    const spec = tokensBarSpec(stats, 'calls');
    expect(spec.options?.plugins?.datalabels?.display).toBe(false);
  });
  it('caps x-tick rotation and pads the axis so labels do not crowd', () => {
    const spec = tokensBarSpec(stats, 'calls');
    const xScale = spec.options?.scales?.x as
      | { ticks?: { maxRotation?: number; padding?: number } }
      | undefined;
    expect(xScale?.ticks?.maxRotation).toBe(35);
    expect(xScale?.ticks?.padding).toBe(8);
    const layoutPadding = (spec.options?.layout?.padding ?? {}) as { bottom?: number };
    expect(layoutPadding.bottom).toBe(8);
  });
});

describe('durationChartSpec', () => {
  it('builds Avg + Max datasets ordered by sortKey', () => {
    const s: ToolStats = {
      a: {
        num_times_called: 10,
        input_tokens: 0,
        output_tokens: 0,
        total_duration_ms: 100,
        max_duration_ms: 20,
      },
      b: {
        num_times_called: 5,
        input_tokens: 0,
        output_tokens: 0,
        total_duration_ms: 50,
        max_duration_ms: 30,
      },
    };
    const spec = durationChartSpec(s, 'duration_total');
    expect(spec.type).toBe('bar');
    // total_duration_ms: a=100 > b=50 → labels ['a','b']
    expect(spec.data.labels).toEqual(['a', 'b']);
    expect(spec.data.datasets).toHaveLength(2);
    const avg = spec.data.datasets.find((d) => d.label === 'Avg (ms)');
    expect(avg?.data).toEqual([10, 10]); // 100/10, 50/5
    const max = spec.data.datasets.find((d) => d.label === 'Max (ms)');
    expect(max?.data).toEqual([20, 30]);
  });
  it('returns 0 avg for tools with 0 calls and missing durations', () => {
    const s: ToolStats = {
      x: { num_times_called: 0, input_tokens: 0, output_tokens: 0 },
    };
    const spec = durationChartSpec(s, 'calls');
    expect(spec.data.datasets[0].data).toEqual([0]);
    expect(spec.data.datasets[1].data).toEqual([0]);
  });
});

function rec(started_at: number, tool = 't'): ToolCallRecord {
  return {
    seq: 0,
    tool,
    started_at,
    duration_ms: 0,
    success: true,
    error_message: null,
    input_preview: '',
    output_preview: '',
    input_truncated: false,
    output_truncated: false,
  };
}

describe('bucketRecordsByMinute', () => {
  it('emits windowMinutes + 1 buckets, with the current minute as the last bucket', () => {
    const now = 1_700_000_000; // arbitrary epoch s
    const nowAligned = Math.floor(now / 60) * 60;
    const records = [
      rec(nowAligned + 5), // in current minute
      rec(nowAligned - 30), // in current minute (0–59s of nowAligned -1? actually previous-minute bucket)
      rec(nowAligned - 65), // 1 minute ago
    ];
    const buckets = bucketRecordsByMinute(records, nowAligned + 10, 15);
    expect(buckets.length).toBe(16); // 15 + 1
    // Current-minute calls (>= nowAligned and < nowAligned+60) land in the LAST bucket
    expect(buckets[buckets.length - 1].count).toBe(1);
    // nowAligned - 30 is one minute before nowAligned → second-to-last bucket
    // nowAligned - 65 is two minutes before nowAligned → third-to-last bucket
    expect(buckets[buckets.length - 2].count).toBe(1);
    expect(buckets[buckets.length - 3].count).toBe(1);
  });

  it('returns 0-count buckets for empty minutes', () => {
    const now = 1_700_000_000;
    const buckets = bucketRecordsByMinute([], now, 5);
    expect(buckets.length).toBe(6);
    expect(buckets.every((b) => b.count === 0)).toBe(true);
  });

  it('tracks per-tool counts in byTool', () => {
    const now = 1_700_000_000;
    const nowAligned = Math.floor(now / 60) * 60;
    const records = [
      rec(nowAligned + 1, 'find_symbol'),
      rec(nowAligned + 2, 'find_symbol'),
      rec(nowAligned + 3, 'read_file'),
    ];
    const buckets = bucketRecordsByMinute(records, nowAligned, 5);
    const last = buckets[buckets.length - 1];
    expect(last.byTool['find_symbol']).toBe(2);
    expect(last.byTool['read_file']).toBe(1);
  });
});

describe('sortToolsBy', () => {
  it('orders tools by the given key in descending score', () => {
    const s: ToolStats = {
      a: { num_times_called: 2, input_tokens: 10, output_tokens: 5 },
      b: { num_times_called: 8, input_tokens: 40, output_tokens: 20 },
      c: { num_times_called: 5, input_tokens: 20, output_tokens: 10 },
    };
    expect(sortToolsBy(s, 'calls')).toEqual(['b', 'c', 'a']);
    expect(sortToolsBy(s, 'tokens')).toEqual(['b', 'c', 'a']);
  });
  it('keeps insertion order for ties (Array.sort stability)', () => {
    // Three tools with identical scores: insertion order must be preserved.
    const s: ToolStats = {
      first: { num_times_called: 5, input_tokens: 0, output_tokens: 0 },
      second: { num_times_called: 5, input_tokens: 0, output_tokens: 0 },
      third: { num_times_called: 5, input_tokens: 0, output_tokens: 0 },
    };
    expect(sortToolsBy(s, 'calls')).toEqual(['first', 'second', 'third']);
  });
  it('handles missing optional fields by treating them as 0', () => {
    const s: ToolStats = {
      a: { num_times_called: 1, input_tokens: 0, output_tokens: 0 }, // no duration fields
      b: {
        num_times_called: 1,
        input_tokens: 0,
        output_tokens: 0,
        total_duration_ms: 50,
      },
    };
    expect(sortToolsBy(s, 'duration_total')).toEqual(['b', 'a']);
    expect(sortToolsBy(s, 'errors')).toEqual(['a', 'b']); // tie at 0 → insertion order
  });
});

describe('rateChartSpec', () => {
  it('produces a single non-filled line dataset when stacked=false', () => {
    const spec = rateChartSpec([], Date.now() / 1000, 15, false, []);
    expect(spec.type).toBe('line');
    expect(spec.data.datasets.length).toBe(1);
    expect(spec.data.datasets[0].fill).toBe(false);
    expect(spec.data.labels?.length).toBe(16);
  });
  it('produces per-tool filled datasets when stacked=true', () => {
    const spec = rateChartSpec([], Date.now() / 1000, 15, true, ['a', 'b', 'c']);
    expect(spec.data.datasets.length).toBe(3);
    expect(spec.data.datasets.every((d) => d.fill === true)).toBe(true);
  });
  it('enables stacked scales when stacked=true', () => {
    const spec = rateChartSpec([], Date.now() / 1000, 15, true, ['a']);
    const x = spec.options?.scales?.x as { stacked?: boolean } | undefined;
    const y = spec.options?.scales?.y as { stacked?: boolean } | undefined;
    expect(x?.stacked).toBe(true);
    expect(y?.stacked).toBe(true);
  });
});
