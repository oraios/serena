import { describe, it, expect } from 'vitest';
import { createExecutionsStore } from '../src/lib/stores/executions.svelte';
import { exec, okBody, errBody, stubFetchJson } from './helpers';

describe('executions store: cancel', () => {
  it('records a cancelled execution on success', async () => {
    stubFetchJson(okBody({ was_cancelled: true, message: '' }));
    const store = createExecutionsStore();
    const r = await store.cancel(exec({ task_id: 7, name: 't', is_running: true }));
    expect(r.ok).toBe(true);
    expect(store.cancelled.map((c) => c.task_id)).toEqual([7]);
    expect(store.cancelError).toBe('');
  });

  it('sets cancelError and does not record on failure', async () => {
    stubFetchJson(errBody('too late'));
    const store = createExecutionsStore();
    const r = await store.cancel(exec({ task_id: 8 }));
    expect(r.ok).toBe(false);
    expect(store.cancelError).toBe('too late');
    expect(store.cancelled).toEqual([]);
  });

  it('does not record the same cancelled task twice', async () => {
    stubFetchJson(okBody({ was_cancelled: true, message: '' }));
    const store = createExecutionsStore();
    const e = exec({ task_id: 7 });
    await store.cancel(e);
    await store.cancel(e);
    expect(store.cancelled.map((c) => c.task_id)).toEqual([7]);
  });

  it('clearCancelError resets the error', async () => {
    stubFetchJson(errBody('too late'));
    const store = createExecutionsStore();
    await store.cancel(exec({ task_id: 8 }));
    expect(store.cancelError).toBe('too late');
    store.clearCancelError();
    expect(store.cancelError).toBe('');
  });
});
