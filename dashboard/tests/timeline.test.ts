import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent, within } from '@testing-library/svelte';
import Timeline from '../src/components/overview/Timeline.svelte';
import { createTimelineStore } from '../src/lib/stores/timeline.svelte';
import { createExecutionsStore } from '../src/lib/stores/executions.svelte';
import type { QueuedExecution, ToolCallRecord } from '../src/lib/api/types';

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
    input_tokens: seq * 10,
    output_tokens: seq * 20,
  };
}

function execObj(task_id: number, name = 'long_task', is_running = true): QueuedExecution {
  return {
    task_id,
    is_running,
    name,
    display_name: name,
    finished_successfully: false,
    logged: true,
    started_at: 9999,
    finished_at: null,
    duration_ms: null,
    error_message: null,
  };
}

describe('Timeline', () => {
  beforeEach(() => localStorage.clear());

  it('renders rows from the store and paginates', () => {
    const store = createTimelineStore();
    const executions = createExecutionsStore();
    for (let i = 1; i <= 60; i++)
      (store as unknown as { records: ToolCallRecord[] }).records.push(rec(i));
    store.setPageSize(25);
    const { container } = render(Timeline, {
      store,
      executions,
      toolNames: ['read_file'],
      oncancelexecution: () => {},
    });
    expect(container.querySelectorAll('[data-timeline-row]').length).toBe(25);
  });

  it('toggle pause sets paused state', async () => {
    const store = createTimelineStore();
    const executions = createExecutionsStore();
    const { getByLabelText } = render(Timeline, {
      store,
      executions,
      toolNames: [],
      oncancelexecution: () => {},
    });
    await fireEvent.click(getByLabelText(/pause/i));
    expect(store.paused).toBe(true);
  });

  it('clear view empties records', async () => {
    const store = createTimelineStore();
    const executions = createExecutionsStore();
    (store as unknown as { records: ToolCallRecord[] }).records.push(rec(1));
    const { getByLabelText } = render(Timeline, {
      store,
      executions,
      toolNames: [],
      oncancelexecution: () => {},
    });
    await fireEvent.click(getByLabelText(/clear/i));
    expect(store.records.length).toBe(0);
  });

  it('renders a cancel button for running rows and fires oncancelexecution', async () => {
    const store = createTimelineStore();
    const executions = createExecutionsStore();
    (executions as unknown as { queued: QueuedExecution[] }).queued.push(execObj(42));
    let cancelled: QueuedExecution | null = null;
    const { getByTestId } = render(Timeline, {
      store,
      executions,
      toolNames: [],
      oncancelexecution: (ex) => (cancelled = ex),
    });
    await fireEvent.click(getByTestId('cancel-btn'));
    expect(cancelled).not.toBeNull();
    expect((cancelled as unknown as QueuedExecution).task_id).toBe(42);
  });

  it('status chips toggle visibility — disabling success hides successful history rows', async () => {
    const store = createTimelineStore();
    const executions = createExecutionsStore();
    (store as unknown as { records: ToolCallRecord[] }).records.push(
      rec(1, 'a', true),
      rec(2, 'b', false),
    );
    const { container, getByRole } = render(Timeline, {
      store,
      executions,
      toolNames: [],
      oncancelexecution: () => {},
    });
    expect(container.querySelectorAll('[data-timeline-row]').length).toBe(2);
    // Scope to the status-filter group: rows now also expose a "Success" status
    // icon, so an unscoped /Success/ button query is ambiguous.
    const statusFilter = getByRole('group', { name: /Status filter/ });
    await fireEvent.click(within(statusFilter).getByRole('button', { name: /Success/ }));
    expect(container.querySelectorAll('[data-timeline-row]').length).toBe(1);
    expect(container.querySelector('[data-timeline-row]')?.getAttribute('data-status')).toBe(
      'fail',
    );
  });
});
