// A shared, ref-counted wall-clock tick. Components that render live relative
// timestamps ("2m ago") read `clock.now` reactively and bracket their lifetime
// with `clock.start()` / `clock.stop()` (typically in a `$effect`). The single
// interval runs only while at least one consumer is mounted, so a screen with
// 100 timeline rows pays for one timer, not 100.
export function createClockStore(intervalMs = 10_000) {
  let now = $state(Date.now());
  let timer: ReturnType<typeof setInterval> | null = null;
  let consumers = 0;
  return {
    get now() {
      return now;
    },
    start() {
      consumers++;
      if (!timer) {
        now = Date.now();
        timer = setInterval(() => (now = Date.now()), intervalMs);
      }
    },
    stop() {
      consumers = Math.max(0, consumers - 1);
      if (consumers === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    },
  };
}

export const clock = createClockStore();
