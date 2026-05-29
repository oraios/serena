import { fetchToolCallTimeline } from '$lib/api/endpoints';
import type { ToolCallRecord } from '$lib/api/types';
import { ALL_STATUSES, type RowStatus } from '$lib/timelineRows';

const BUFFER_CAP = 2000;
const BATCH_LIMIT = 200;
const STORAGE_KEY = 'serena.timeline.v1';

interface PersistedState {
  filter: string | null;
  statusFilter: RowStatus[];
  paused: boolean;
}

function loadPersisted(): Partial<PersistedState> {
  if (typeof localStorage === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Partial<PersistedState>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function savePersisted(state: PersistedState): void {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // quota or denied — silent; persistence is best-effort
  }
}

function sanitizeStatuses(input: unknown): Set<RowStatus> {
  if (Array.isArray(input)) {
    const allowed = new Set<RowStatus>(ALL_STATUSES);
    const out = new Set<RowStatus>();
    for (const v of input)
      if (typeof v === 'string' && allowed.has(v as RowStatus)) out.add(v as RowStatus);
    if (out.size > 0) return out;
  }
  return new Set<RowStatus>(ALL_STATUSES);
}

export function createTimelineStore() {
  const persisted = loadPersisted();
  let records = $state<ToolCallRecord[]>([]);
  let cursor = $state<number | null>(null);
  let filter = $state<string | null>(
    typeof persisted.filter === 'string' ? persisted.filter : null,
  );
  let paused = $state(persisted.paused === true);
  let page = $state(1);
  let pageSize = $state(25);
  let pausedGap = $state<number | null>(null);
  let error = $state<string | null>(null);
  let statusFilter = $state<Set<RowStatus>>(sanitizeStatuses(persisted.statusFilter));

  function persist() {
    savePersisted({ filter, statusFilter: [...statusFilter], paused });
  }

  function mergeIncoming(incoming: ToolCallRecord[]) {
    if (incoming.length === 0) return;
    const seen = new Set(records.map((r) => r.seq));
    const fresh = incoming.filter((r) => !seen.has(r.seq));
    if (fresh.length === 0) return;
    fresh.sort((a, b) => b.seq - a.seq);
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
    get statusFilter() {
      return statusFilter;
    },
    async poll() {
      if (paused) return;
      try {
        const resp = await fetchToolCallTimeline({
          since_seq: cursor ?? undefined,
          tool: filter ?? undefined,
          limit: BATCH_LIMIT,
        });
        const newCursor = resp.max_seq ?? cursor;
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
      persist();
    },
    resume() {
      paused = false;
      pausedGap = null;
      persist();
    },
    togglePause() {
      paused = !paused;
      if (!paused) pausedGap = null;
      persist();
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
      persist();
    },
    toggleStatus(status: RowStatus) {
      const next = new Set(statusFilter);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      // Empty filter would hide everything — disallow it and snap back to all.
      statusFilter = next.size === 0 ? new Set(ALL_STATUSES) : next;
      page = 1;
      persist();
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
