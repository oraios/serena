import { describe, it, expect } from 'vitest';
import { createStatsStore } from '../src/lib/stores/stats.svelte';
import { stubFetchRoutes } from './helpers';

describe('stats store', () => {
  it('refresh loads stats and the estimator name', async () => {
    stubFetchRoutes({
      '/get_tool_stats': {
        stats: { find_symbol: { num_times_called: 3, input_tokens: 1, output_tokens: 2 } },
      },
      '/get_token_count_estimator_name': { token_count_estimator_name: 'tiktoken' },
    });
    const store = createStatsStore();
    await store.refresh();
    expect(store.stats.find_symbol.num_times_called).toBe(3);
    expect(store.estimator).toBe('tiktoken');
  });

  it('clear resets stats to empty', async () => {
    stubFetchRoutes({ '/clear_tool_stats': { status: 'success' } });
    const store = createStatsStore();
    await store.clear();
    expect(store.stats).toEqual({});
  });
});
