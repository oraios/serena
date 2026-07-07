export interface Poller {
  start(): void;
  stop(): void;
}

export function createPoller(fn: () => Promise<void> | void, intervalMs: number): Poller {
  let timer: ReturnType<typeof setInterval> | null = null;
  let inFlight = false;

  const tick = async () => {
    if (inFlight) return;
    inFlight = true;
    try {
      await fn();
    } finally {
      inFlight = false;
    }
  };

  return {
    start() {
      if (timer) return;
      void tick();
      timer = setInterval(() => void tick(), intervalMs);
    },
    stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
      // Allow a fresh start() to poll immediately even if a previous call is still
      // in flight; that orphaned call's (void) result is simply discarded.
      inFlight = false;
    },
  };
}
