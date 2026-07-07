import { describe, it, expect, vi } from 'vitest';
import { createModalAction } from '../src/lib/modalAction.svelte';

describe('createModalAction', () => {
  it('calls onSuccess and never sets error when the action succeeds', async () => {
    const action = createModalAction();
    const onSuccess = vi.fn();
    await action.run(async () => ({ ok: true }), onSuccess);
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(action.error).toBe('');
    expect(action.busy).toBe(false);
  });

  it('sets error and skips onSuccess when the action fails', async () => {
    const action = createModalAction();
    const onSuccess = vi.fn();
    await action.run(async () => ({ ok: false, message: 'boom' }), onSuccess);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(action.error).toBe('boom');
    expect(action.busy).toBe(false);
  });
});
