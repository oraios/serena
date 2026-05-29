import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import Timeline from '../src/components/overview/Timeline.svelte';
import { createTimelineStore } from '../src/lib/stores/timeline.svelte';
import type { ToolCallRecord } from '../src/lib/api/types';

function rec(seq: number, tool = 'read_file', success = true): ToolCallRecord {
  return {
    seq,
    tool,
    started_at: 1000 + seq,
    duration_ms: seq,
    success,
    error_message: success ? null : 'Err',
    input_preview: `in${seq}`,
    output_preview: `out${seq}`,
    input_truncated: false,
    output_truncated: false,
  };
}

describe('Timeline', () => {
  it('renders rows from the store and paginates', () => {
    const store = createTimelineStore();
    // Test-only setup: push records via cast. Production never does this.
    for (let i = 1; i <= 60; i++)
      (store as unknown as { records: ToolCallRecord[] }).records.push(rec(i));
    store.setPageSize(25);
    const { container } = render(Timeline, { store, toolNames: ['read_file'] });
    expect(container.querySelectorAll('[data-timeline-row]').length).toBe(25);
  });

  it('toggle pause sets paused state', async () => {
    const store = createTimelineStore();
    const { getByLabelText } = render(Timeline, { store, toolNames: [] });
    await fireEvent.click(getByLabelText(/pause/i));
    expect(store.paused).toBe(true);
  });

  it('clear view empties records', async () => {
    const store = createTimelineStore();
    (store as unknown as { records: ToolCallRecord[] }).records.push(rec(1));
    const { getByLabelText } = render(Timeline, { store, toolNames: [] });
    await fireEvent.click(getByLabelText(/clear/i));
    expect(store.records.length).toBe(0);
  });
});
