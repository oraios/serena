import { describe, it, expect } from 'vitest';
import { runMutation } from '../src/lib/api/mutation';
import { ApiError } from '../src/lib/api/client';

describe('runMutation', () => {
  it('returns ok for a success body', async () => {
    const r = await runMutation(async () => ({ status: 'success' as const }));
    expect(r.ok).toBe(true);
  });

  it('returns the error message when the body reports status:error (HTTP 200 path)', async () => {
    const r = await runMutation(async () => ({ status: 'error' as const, message: 'boom' }));
    expect(r).toEqual({ ok: false, message: 'boom', data: { status: 'error', message: 'boom' } });
  });

  it('catches a thrown ApiError (non-2xx path)', async () => {
    const r = await runMutation(async () => {
      throw new ApiError(500, 'HTTP 500 for /x');
    });
    expect(r.ok).toBe(false);
    expect(r.message).toContain('HTTP 500');
  });

  it('exposes the resolved body as data for callers needing extra fields', async () => {
    const r = await runMutation(async () => ({ status: 'success' as const, was_cancelled: true }));
    expect(r.data).toEqual({ status: 'success', was_cancelled: true });
  });
});
