import { describe, it, expect, beforeEach } from 'vitest';
import { stubFetchRoutes } from './helpers';
import { createTimelineStore } from '../src/lib/stores/timeline.svelte';
import type { ToolCallRecord } from '../src/lib/api/types';

beforeEach(() => localStorage.clear());

function record(seq: number, tool = 't'): ToolCallRecord {
  return {
    seq,
    tool,
    started_at: 1000 + seq,
    duration_ms: 1,
    success: true,
    error_message: null,
    input_preview: '',
    output_preview: '',
    input_truncated: false,
    output_truncated: false,
    input_tokens: 0,
    output_tokens: 0,
  };
}

describe('timeline store', () => {
  it('merges new records onto the front, dedups by seq, caps at 2000', async () => {
    let max_seq = 0;
    stubFetchRoutes({
      '/get_tool_call_timeline': () => {
        const records = [record(max_seq + 1)];
        max_seq += 1;
        return { records, max_seq };
      },
    });
    const store = createTimelineStore();
    await store.poll();
    await store.poll();
    expect(store.records.length).toBe(2);
    expect(store.records.map((r) => r.seq).sort()).toEqual([1, 2]);
    expect(store.cursor).toBe(2);
  });

  it('cursor uses ?? not || — preserves cursor when max_seq is 0 after a non-zero advance', async () => {
    let phase = 0;
    stubFetchRoutes({
      '/get_tool_call_timeline': () => {
        phase++;
        if (phase === 1) {
          return {
            records: [
              {
                seq: 5,
                tool: 't',
                started_at: 0,
                duration_ms: 0,
                success: true,
                error_message: null,
                input_preview: '',
                output_preview: '',
                input_truncated: false,
                output_truncated: false,
                input_tokens: 0,
                output_tokens: 0,
              },
            ],
            max_seq: 5,
          };
        }
        // Phase 2: simulate a server restart (or buffer clear) — max_seq=0.
        return { records: [], max_seq: 0 };
      },
    });
    const store = createTimelineStore();
    await store.poll();
    expect(store.cursor).toBe(5);
    await store.poll();
    // Under `||`: cursor would stay at 5 (because 0 is falsy and || picks the truthy 5).
    // Under `??`: cursor becomes 0 (because 0 is not nullish).
    expect(store.cursor).toBe(0);
  });

  it('caps the buffer at 2000 records', async () => {
    let next = 0;
    stubFetchRoutes({
      '/get_tool_call_timeline': () => {
        const batch = Array.from({ length: 600 }, () => {
          next += 1;
          return record(next);
        });
        return { records: batch, max_seq: next };
      },
    });
    const store = createTimelineStore();
    for (let i = 0; i < 4; i++) await store.poll(); // 2400 total
    expect(store.records.length).toBe(2000);
  });

  it('pause stops poll from advancing cursor', async () => {
    stubFetchRoutes({
      '/get_tool_call_timeline': () => ({ records: [record(1)], max_seq: 1 }),
    });
    const store = createTimelineStore();
    store.pause();
    await store.poll();
    expect(store.records.length).toBe(0);
    expect(store.cursor).toBeNull();
  });

  it('setFilter resets buffer and cursor', async () => {
    let next = 0;
    stubFetchRoutes({
      '/get_tool_call_timeline': () => {
        next += 1;
        return { records: [record(next, 't1')], max_seq: next };
      },
    });
    const store = createTimelineStore();
    await store.poll();
    expect(store.records.length).toBe(1);
    store.setFilter('t2');
    expect(store.records.length).toBe(0);
    expect(store.cursor).toBeNull();
    expect(store.filter).toBe('t2');
  });

  it('detects pausedGap when cursor jumps further than received batch size', async () => {
    let phase = 0;
    stubFetchRoutes({
      '/get_tool_call_timeline': () => {
        phase++;
        if (phase === 1) return { records: [record(10)], max_seq: 10 };
        // Phase 2: 5 records returned but server cursor jumped 50 → gap of 35.
        const records = [11, 12, 13, 14, 15].map((s) => record(s));
        return { records, max_seq: 50 };
      },
    });
    const store = createTimelineStore();
    await store.poll();
    expect(store.pausedGap).toBeNull();
    await store.poll();
    // newCursor=50, cursor=10, length=5 → 50-10-5 = 35
    expect(store.pausedGap).toBe(35);
  });

  it('does NOT raise pausedGap from the GLOBAL max_seq when a tool filter is active', async () => {
    // max_seq is global across all tools; with a filter the returned records are
    // a subset, so a delta beyond the filtered batch is normal, not a gap.
    let phase = 0;
    stubFetchRoutes({
      '/get_tool_call_timeline': () => {
        phase++;
        if (phase === 1) return { records: [record(10, 'mine')], max_seq: 10 };
        // Other tools advanced max_seq to 50, but only one 'mine' record arrived.
        return { records: [record(40, 'mine')], max_seq: 50 };
      },
    });
    localStorage.setItem('serena.timeline.v1', JSON.stringify({ filter: 'mine' }));
    const store = createTimelineStore();
    expect(store.filter).toBe('mine');
    await store.poll();
    await store.poll();
    // Pre-fix this would have reported 50-10-1 = 39 phantom skipped calls.
    expect(store.pausedGap).toBeNull();
  });
});
