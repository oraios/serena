import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/svelte';
import { tick } from 'svelte';
import ChartPanel from '../src/components/stats/ChartPanel.svelte';
import { pieSpec } from '../src/lib/charts';
import { theme } from '../src/lib/stores/theme.svelte';
import type { ToolStats } from '../src/lib/api/types';

// jsdom has no canvas backend — mock Chart.js entirely.
// Use vi.hoisted so the variables are available when vi.mock factories run
// (vi.mock calls are hoisted to the top of the file by Vitest).
const { ChartMock, instance } = vi.hoisted(() => {
  const instance = {
    data: { labels: [] as unknown[], datasets: [{}, {}] as Record<string, unknown>[] },
    options: { plugins: { legend: { labels: {} } }, scales: {} },
    update: vi.fn(),
    destroy: vi.fn(),
  };
  const ChartMock = vi.fn(() => instance);
  return { ChartMock, instance };
});

vi.mock('chart.js/auto', () => ({ default: ChartMock }));
vi.mock('chartjs-plugin-datalabels', () => ({ default: {} }));

const stats: ToolStats = { a: { num_times_called: 5, input_tokens: 1, output_tokens: 1 } };

beforeEach(() => {
  ChartMock.mockClear();
  instance.update.mockClear();
  instance.destroy.mockClear();
  // Reset shared mock state so per-test assertions on `instance.data` are isolated.
  instance.data.labels = [];
  instance.data.datasets = [{}, {}];
});

describe('ChartPanel', () => {
  it('constructs a Chart from the spec and renders the title', () => {
    const { getByText } = render(ChartPanel, {
      props: { title: 'Tool Calls', spec: pieSpec(stats, 'num_times_called') },
    });
    expect(getByText('Tool Calls')).toBeInTheDocument();
    expect(ChartMock).toHaveBeenCalledTimes(1);
    const config = (ChartMock.mock.calls[0] as unknown as [unknown, { type: string }])[1];
    expect(config.type).toBe('pie');
  });

  it('destroys the chart on unmount', () => {
    const { unmount } = render(ChartPanel, {
      props: { title: 'Tool Calls', spec: pieSpec(stats, 'num_times_called') },
    });
    unmount();
    expect(instance.destroy).toHaveBeenCalled();
  });

  it('updates in place on spec change without re-constructing the chart', async () => {
    const { rerender } = render(ChartPanel, {
      props: { title: 'Tool Calls', spec: pieSpec(stats, 'num_times_called') },
    });
    expect(ChartMock).toHaveBeenCalledTimes(1);
    const updateCallsBefore = instance.update.mock.calls.length;
    const nextStats: ToolStats = {
      a: { num_times_called: 5, input_tokens: 1, output_tokens: 1 },
      b: { num_times_called: 9, input_tokens: 2, output_tokens: 2 },
    };
    await rerender({ title: 'Tool Calls', spec: pieSpec(nextStats, 'num_times_called') });
    expect(ChartMock).toHaveBeenCalledTimes(1); // not re-constructed
    expect(instance.update.mock.calls.length).toBeGreaterThan(updateCallsBefore);
    // Data-effect must actually copy the new labels/data onto the live chart —
    // not just call update(). pieSpec sorts descending by metric.
    expect(instance.data.labels).toEqual(['b', 'a']);
    expect(instance.data.datasets[0].data).toEqual([9, 5]);
  });

  it('re-applies colours when the theme flips', async () => {
    render(ChartPanel, {
      props: { title: 'Tool Calls', spec: pieSpec(stats, 'num_times_called') },
    });
    const updateCallsBefore = instance.update.mock.calls.length;
    const initialTheme = theme.current;
    try {
      theme.toggle();
      await tick();
      expect(instance.update.mock.calls.length).toBeGreaterThan(updateCallsBefore);
      // Theme-effect runs applyTheme(), which writes a colour onto legend labels.
      // jsdom's getComputedStyle returns '' for un-stylesheet'd vars → applyTheme
      // falls back to the hardcoded default, but it still writes *something*.
      const legend = instance.options.plugins.legend.labels as { color?: string };
      expect(legend.color).toBeTruthy();
    } finally {
      if (theme.current !== initialTheme) theme.toggle();
    }
  });
});
