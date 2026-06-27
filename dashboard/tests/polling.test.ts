import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPoller } from '../src/lib/polling';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('createPoller', () => {
  it('runs immediately and on each interval, and stops', async () => {
    const fn = vi.fn().mockResolvedValue(undefined);
    const poller = createPoller(fn, 1000);
    poller.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fn).toHaveBeenCalledTimes(2);
    poller.stop();
    await vi.advanceTimersByTimeAsync(2000);
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('does not call fn again while a previous call is still in flight', async () => {
    let resolveFirst!: () => void;
    const firstDone = new Promise<void>((r) => {
      resolveFirst = r;
    });
    const fn = vi.fn().mockReturnValueOnce(firstDone).mockResolvedValue(undefined);

    const poller = createPoller(fn, 1000);
    poller.start();
    expect(fn).toHaveBeenCalledTimes(1); // immediate call, still pending

    await vi.advanceTimersByTimeAsync(1000);
    expect(fn).toHaveBeenCalledTimes(1); // interval fired but guard skipped it

    resolveFirst();
    await Promise.resolve(); // flush microtasks so inFlight clears

    await vi.advanceTimersByTimeAsync(1000);
    expect(fn).toHaveBeenCalledTimes(2); // now the next tick runs

    poller.stop();
  });
});
