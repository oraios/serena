import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as api from '../src/lib/api/endpoints';

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
});

describe('endpoints', () => {
  it('fetchConfigOverview GETs /get_config_overview', async () => {
    await api.fetchConfigOverview();
    expect(fetchMock).toHaveBeenCalledWith('/get_config_overview');
  });
  it('fetchLogMessages POSTs /get_log_messages with start_idx', async () => {
    await api.fetchLogMessages(5);
    expect(fetchMock).toHaveBeenCalledWith(
      '/get_log_messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ start_idx: 5 }),
      }),
    );
  });
  it('shutdown PUTs /shutdown', async () => {
    await api.shutdown();
    expect(fetchMock).toHaveBeenCalledWith('/shutdown', expect.objectContaining({ method: 'PUT' }));
  });
});
