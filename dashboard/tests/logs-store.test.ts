import { describe, it, expect, vi } from 'vitest';
import { createLogsStore } from '../src/lib/stores/logs.svelte';

describe('logs store', () => {
  it('appends only new messages by tracking max_idx', async () => {
    const responses = [
      { messages: ['a', 'b'], max_idx: 2, active_project: 'p' },
      { messages: ['c'], max_idx: 3, active_project: 'p' },
    ];
    let call = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(new Response(JSON.stringify(responses[call++]), { status: 200 })),
      ),
    );
    const store = createLogsStore();
    await store.poll();
    expect(store.lines).toEqual(['a', 'b']);
    await store.poll();
    expect(store.lines).toEqual(['a', 'b', 'c']);
  });
});
