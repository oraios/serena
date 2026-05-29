import { describe, it, expect, vi } from 'vitest';
import { getJson, postJson, putJson, ApiError } from '../src/lib/api/client';
import { stubFetchJson } from './helpers';

describe('client', () => {
  it('getJson parses JSON on success', async () => {
    stubFetchJson({ a: 1 });
    expect(await getJson<{ a: number }>('/x')).toEqual({ a: 1 });
  });

  it('postJson sends a JSON body', async () => {
    const f = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    await postJson('/y', { name: 'go' });
    expect(f).toHaveBeenCalledWith(
      '/y',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'go' }),
      }),
    );
  });

  it('throws ApiError on non-2xx', async () => {
    stubFetchJson('nope', 500);
    await expect(getJson('/z')).rejects.toBeInstanceOf(ApiError);
  });

  it('putJson issues a PUT', async () => {
    const f = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    await putJson('/shutdown');
    expect(f).toHaveBeenCalledWith('/shutdown', expect.objectContaining({ method: 'PUT' }));
  });
});
