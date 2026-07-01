import { describe, it, expect, vi } from 'vitest';
import { createLogsStore } from '../src/lib/stores/logs.svelte';

/**
 * Stateful fake of the backend LogBuffer (src/serena/util/logging.py):
 * - `max_idx` is the 0-based index of the *last* message.
 * - `get_log_messages(from_idx)` returns messages starting at `from_idx`
 *   **inclusive**.
 * Replaying that contract is what catches the off-by-one where the store
 * re-fetched the tail line every poll.
 */
function fakeBackend(initial: string[] = []) {
  const buffer = [...initial];
  const respond = (startIdx: number) => {
    const from = Math.max(startIdx, 0);
    const messages = buffer.slice(from);
    return { messages, max_idx: buffer.length - 1, active_project: 'p' };
  };
  vi.stubGlobal(
    'fetch',
    vi.fn((_url: string, init?: RequestInit) => {
      const body = init?.body ? JSON.parse(init.body as string) : {};
      const startIdx = typeof body.start_idx === 'number' ? body.start_idx : 0;
      return Promise.resolve(new Response(JSON.stringify(respond(startIdx)), { status: 200 }));
    }),
  );
  return { append: (...m: string[]) => buffer.push(...m) };
}

describe('logs store', () => {
  it('appends only new messages by tracking max_idx', async () => {
    const backend = fakeBackend(['a', 'b']);
    const store = createLogsStore();
    await store.poll();
    expect(store.lines).toEqual(['a', 'b']);
    backend.append('c');
    await store.poll();
    expect(store.lines).toEqual(['a', 'b', 'c']);
  });

  it('does not re-append the tail line when no new messages arrive', async () => {
    fakeBackend(['a', 'b']);
    const store = createLogsStore();
    await store.poll();
    await store.poll();
    await store.poll();
    // Regression: previously each idle poll re-fetched index max_idx (inclusive)
    // and duplicated the last line unboundedly.
    expect(store.lines).toEqual(['a', 'b']);
  });

  it('starts from an empty buffer without duplicating', async () => {
    const backend = fakeBackend([]);
    const store = createLogsStore();
    await store.poll();
    expect(store.lines).toEqual([]);
    backend.append('first');
    await store.poll();
    expect(store.lines).toEqual(['first']);
    await store.poll();
    expect(store.lines).toEqual(['first']);
  });
});
