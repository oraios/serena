import { describe, it, expect } from 'vitest';
import { createConfigStore } from '../src/lib/stores/config.svelte';
import { stubFetchJson } from './helpers';

const overview = { serena_version: '1.0', active_project: null, languages: [] };

describe('config store', () => {
  it('keeps the same reference when the polled body is unchanged', async () => {
    stubFetchJson(overview);
    const store = createConfigStore();
    await store.poll();
    const first = store.data;
    await store.poll();
    expect(store.data).toBe(first); // dedup via JSON compare → no reassignment
  });

  it('updates data when the polled body changes', async () => {
    const fetchMock = stubFetchJson(overview);
    const store = createConfigStore();
    await store.poll();
    const first = store.data;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ...overview, serena_version: '2.0' }), { status: 200 }),
    );
    await store.poll();
    expect(store.data).not.toBe(first);
    expect(store.data?.serena_version).toBe('2.0');
  });
});
