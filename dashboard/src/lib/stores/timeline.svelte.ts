import { fetchToolCallTimeline } from '$lib/api/endpoints';
import type { ToolCallRecord } from '$lib/api/types';

const BUFFER_CAP = 2000;
const BATCH_LIMIT = 200;

export function createTimelineStore() {
  let records = $state<ToolCallRecord[]>([]);
  let cursor = $state<number | null>(null);
  let filter = $state<string | null>(null);
  let paused = $state(false);
  let page = $state(1);
  let pageSize = $state(25);
  let pausedGap = $state<number | null>(null);
  let error = $state<string | null>(null);

  function mergeIncoming(incoming: ToolCallRecord[]) {
    if (incoming.length === 0) return;
    const seen = new Set(records.map((r) => r.seq));
    const fresh = incoming.filter((r) => !seen.has(r.seq));
    if (fresh.length === 0) return;
    // Sort the fresh batch first (incoming order may be ascending or arbitrary).
    fresh.sort((a, b) => b.seq - a.seq);
    // Fast path: every fresh record is strictly newer than the head of `records`.
    // Avoids the O(n log n) full sort on every poll under the steady state where
    // the server always returns records monotonically newer than what we hold.
    const headSeq = records.length > 0 ? records[0].seq : -Infinity;
    let next: ToolCallRecord[];
    if (fresh[fresh.length - 1].seq > headSeq) {
      next = [...fresh, ...records];
    } else {
      next = [...fresh, ...records];
      next.sort((a, b) => b.seq - a.seq);
    }
    if (next.length > BUFFER_CAP) {
      next.length = BUFFER_CAP;
    }
    records = next;
  }

  return {
    get records() {
      return records;
    },
    get cursor() {
      return cursor;
    },
    get filter() {
      return filter;
    },
    get paused() {
      return paused;
    },
    get page() {
      return page;
    },
    get pageSize() {
      return pageSize;
    },
    get pausedGap() {
      return pausedGap;
    },
    get error() {
      return error;
    },
    async poll() {
      if (paused) return;
      try {
        const resp = await fetchToolCallTimeline({
          since_seq: cursor ?? undefined,
          tool: filter ?? undefined,
          limit: BATCH_LIMIT,
        });
        // Cursor coalescing: USE `??` not `||` so server-reported 0 doesn't
        // fall back to the previous cursor value.
        const newCursor = resp.max_seq ?? cursor;
        // If the server advanced the cursor further than the batch we received,
        // we missed records (e.g. pause-and-resume across a busy window).
        // Surface the gap so the UI can hint at it.
        if (cursor !== null && newCursor !== null && newCursor - cursor > resp.records.length) {
          const skipped = newCursor - cursor - resp.records.length;
          if (skipped > 0) pausedGap = skipped;
        }
        mergeIncoming(resp.records);
        cursor = newCursor;
        error = null;
      } catch (e) {
        error = e instanceof Error ? e.message : String(e);
      }
    },
    pause() {
      paused = true;
    },
    resume() {
      paused = false;
      pausedGap = null;
    },
    togglePause() {
      paused = !paused;
      if (!paused) pausedGap = null;
    },
    clearView() {
      records = [];
      pausedGap = null;
      page = 1;
    },
    setFilter(tool: string | null) {
      filter = tool;
      records = [];
      cursor = null;
      page = 1;
    },
    setPage(p: number) {
      page = Math.max(1, p);
    },
    setPageSize(size: number) {
      pageSize = size;
      page = 1;
    },
  };
}

export const timeline = createTimelineStore();
