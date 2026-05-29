import type { QueuedExecution, ToolCallRecord } from './api/types';

export type RowStatus = 'success' | 'fail' | 'running' | 'cancelled';
export const ALL_STATUSES: readonly RowStatus[] = [
  'success',
  'fail',
  'running',
  'cancelled',
] as const;

export type TimelineDisplayRow =
  | {
      kind: 'history';
      key: string;
      status: 'success' | 'fail';
      startedAt: number;
      tool: string;
      record: ToolCallRecord;
    }
  | {
      kind: 'live';
      key: string;
      status: 'running' | 'cancelled';
      startedAt: number;
      tool: string;
      execution: QueuedExecution;
    };

function historyRow(record: ToolCallRecord): TimelineDisplayRow {
  return {
    kind: 'history',
    key: `h:${record.seq}`,
    status: record.success ? 'success' : 'fail',
    startedAt: record.started_at,
    tool: record.tool,
    record,
  };
}

function liveRow(execution: QueuedExecution, status: 'running' | 'cancelled'): TimelineDisplayRow {
  // started_at can be null for tasks still queued — sort them to the very top.
  const startedAt = execution.started_at ?? Number.POSITIVE_INFINITY;
  return {
    kind: 'live',
    key: `e:${status}:${execution.task_id}`,
    status,
    startedAt,
    tool: execution.name,
    execution,
  };
}

export interface MergeInput {
  records: ToolCallRecord[];
  queued: QueuedExecution[];
  cancelled: QueuedExecution[];
  tool: string | null;
  statuses: ReadonlySet<RowStatus>;
}

export function mergeTimelineRows({
  records,
  queued,
  cancelled,
  tool,
  statuses,
}: MergeInput): TimelineDisplayRow[] {
  const rows: TimelineDisplayRow[] = [];
  for (const r of records) rows.push(historyRow(r));
  // Only surface user-facing tasks; internal executions (e.g. _get_config_overview) are noise.
  for (const e of queued) if (e.logged && e.is_running) rows.push(liveRow(e, 'running'));
  for (const e of cancelled) if (e.logged) rows.push(liveRow(e, 'cancelled'));

  const filtered = rows.filter((r) => {
    if (!statuses.has(r.status)) return false;
    if (tool && r.tool !== tool) return false;
    return true;
  });
  // Most recent first; +∞ (queued-but-not-started) bubbles to the top.
  filtered.sort((a, b) => b.startedAt - a.startedAt);
  return filtered;
}
