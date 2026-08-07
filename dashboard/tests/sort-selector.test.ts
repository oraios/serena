import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import SortSelector from '../src/components/stats/SortSelector.svelte';
import { sortToolsBy } from '../src/lib/charts';
import { createStatsStore } from '../src/lib/stores/stats.svelte';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  read_file: { num_times_called: 10, input_tokens: 100, output_tokens: 100 },
  find_symbol: { num_times_called: 50, input_tokens: 20, output_tokens: 20 },
  shell: { num_times_called: 2, input_tokens: 500, output_tokens: 500 },
};

describe('sortToolsBy', () => {
  it('sorts by calls desc', () => {
    expect(sortToolsBy(stats, 'calls')).toEqual(['find_symbol', 'read_file', 'shell']);
  });
  it('sorts by tokens desc (input + output)', () => {
    expect(sortToolsBy(stats, 'tokens')).toEqual(['shell', 'read_file', 'find_symbol']);
  });
  it('sorts by duration_total desc, treats missing as 0', () => {
    const s: ToolStats = {
      a: { num_times_called: 1, input_tokens: 0, output_tokens: 0, total_duration_ms: 500 },
      b: { num_times_called: 1, input_tokens: 0, output_tokens: 0, total_duration_ms: 1500 },
      c: { num_times_called: 1, input_tokens: 0, output_tokens: 0 },
    };
    expect(sortToolsBy(s, 'duration_total')).toEqual(['b', 'a', 'c']);
  });
  it('sorts by duration_avg desc (total / calls)', () => {
    const s: ToolStats = {
      a: { num_times_called: 10, input_tokens: 0, output_tokens: 0, total_duration_ms: 500 }, // 50
      b: { num_times_called: 2, input_tokens: 0, output_tokens: 0, total_duration_ms: 300 }, // 150
    };
    expect(sortToolsBy(s, 'duration_avg')).toEqual(['b', 'a']);
  });
  it('sorts by errors desc, treats missing as 0', () => {
    const s: ToolStats = {
      a: { num_times_called: 10, input_tokens: 0, output_tokens: 0, num_errors: 5 },
      b: { num_times_called: 10, input_tokens: 0, output_tokens: 0, num_errors: 1 },
      c: { num_times_called: 10, input_tokens: 0, output_tokens: 0 },
    };
    expect(sortToolsBy(s, 'errors')).toEqual(['a', 'b', 'c']);
  });
});

describe('stats store sortKey', () => {
  it('defaults to "calls" and setSortKey mutates it', () => {
    const store = createStatsStore();
    expect(store.sortKey).toBe('calls');
    store.setSortKey('tokens');
    expect(store.sortKey).toBe('tokens');
  });
});

describe('SortSelector component', () => {
  it('renders all sort options and updates the store on change', async () => {
    const { getByLabelText, container } = render(SortSelector);
    const select = getByLabelText(/Sort by/i) as HTMLSelectElement;
    const options = Array.from(container.querySelectorAll('option')).map((o) => o.value);
    expect(options).toEqual(['calls', 'tokens', 'duration_total', 'duration_avg', 'errors']);
    await fireEvent.change(select, { target: { value: 'errors' } });
    // The shared singleton store should now reflect the new value.
    const { stats: storeSingleton } = await import('../src/lib/stores/stats.svelte');
    expect(storeSingleton.sortKey).toBe('errors');
  });
});
