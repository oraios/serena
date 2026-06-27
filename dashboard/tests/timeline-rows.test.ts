import { describe, it, expect } from 'vitest';
import { ALL_STATUSES, mergeTimelineRows, type RowStatus } from '../src/lib/timelineRows';
import type { QueuedExecution, ToolCallRecord } from '../src/lib/api/types';

function rec(seq: number, tool: string, started_at: number, success = true): ToolCallRecord {
  return {
    seq,
    tool,
    started_at,
    duration_ms: 1,
    success,
    error_message: null,
    input_preview: '',
    output_preview: '',
    input_tokens: 0,
    output_tokens: 0,
  };
}

function ex(task_id: number, name: string, opts: Partial<QueuedExecution> = {}): QueuedExecution {
  return {
    task_id,
    is_running: true,
    name,
    display_name: name,
    finished_successfully: false,
    logged: true,
    started_at: null,
    finished_at: null,
    duration_ms: null,
    error_message: null,
    ...opts,
  };
}

const ALL = new Set<RowStatus>(ALL_STATUSES);

describe('mergeTimelineRows', () => {
  it('sorts by started_at desc with running-but-not-started bubbling to the top', () => {
    const rows = mergeTimelineRows({
      records: [rec(1, 'a', 10), rec(2, 'b', 30), rec(3, 'c', 20)],
      queued: [ex(99, 'pending')], // started_at null → +∞ → top
      cancelled: [],
      tool: null,
      statuses: ALL,
    });
    expect(rows.map((r) => r.tool)).toEqual(['pending', 'b', 'c', 'a']);
  });

  it('filters by tool name', () => {
    const rows = mergeTimelineRows({
      records: [rec(1, 'a', 10), rec(2, 'b', 20)],
      queued: [],
      cancelled: [],
      tool: 'b',
      statuses: ALL,
    });
    expect(rows.map((r) => r.tool)).toEqual(['b']);
  });

  it('filters by status — only success leaves history with success only', () => {
    const rows = mergeTimelineRows({
      records: [rec(1, 'a', 10, true), rec(2, 'b', 20, false)],
      queued: [ex(99, 'live', { started_at: 25 })],
      cancelled: [],
      tool: null,
      statuses: new Set<RowStatus>(['success']),
    });
    expect(rows.map((r) => r.tool)).toEqual(['a']);
  });

  it('drops unlogged queued and unlogged cancelled — internal tasks are not noise', () => {
    const rows = mergeTimelineRows({
      records: [],
      queued: [ex(1, 'noisy', { logged: false, started_at: 100 })],
      cancelled: [ex(2, 'noisy2', { logged: false, started_at: 50 })],
      tool: null,
      statuses: ALL,
    });
    expect(rows).toEqual([]);
  });

  it('drops queued items that are not running (just queued, not yet picked up)', () => {
    const rows = mergeTimelineRows({
      records: [],
      queued: [ex(1, 'idle', { is_running: false, started_at: 5 })],
      cancelled: [],
      tool: null,
      statuses: ALL,
    });
    expect(rows).toEqual([]);
  });

  it('maps history success/fail correctly and live to running/cancelled', () => {
    const rows = mergeTimelineRows({
      records: [rec(1, 'a', 10, true), rec(2, 'b', 20, false)],
      queued: [ex(3, 'c', { started_at: 30 })],
      cancelled: [ex(4, 'd', { started_at: 40 })],
      tool: null,
      statuses: ALL,
    });
    const byTool = Object.fromEntries(rows.map((r) => [r.tool, r.status]));
    expect(byTool).toEqual({ a: 'success', b: 'fail', c: 'running', d: 'cancelled' });
  });
});
