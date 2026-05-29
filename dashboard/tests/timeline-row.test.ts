import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import TimelineRow from '../src/components/overview/TimelineRow.svelte';
import type { TimelineDisplayRow } from '../src/lib/timelineRows';
import type { ToolCallRecord } from '../src/lib/api/types';

function historyRow(over: Partial<ToolCallRecord> = {}): TimelineDisplayRow {
  const record: ToolCallRecord = {
    seq: 1,
    tool: 'read_file',
    started_at: 1000,
    duration_ms: 12,
    success: true,
    error_message: null,
    input_preview: "{'relative_path': 'src/foo.py', 'flag': True}",
    output_preview: 'file contents here',
    input_truncated: false,
    output_truncated: false,
    input_tokens: 1234,
    output_tokens: 340,
    ...over,
  };
  return {
    kind: 'history',
    key: 'h:1',
    status: 'success',
    startedAt: 1000,
    tool: 'read_file',
    record,
  };
}

describe('TimelineRow', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  it('renders a status icon (not the old text label) with an accessible name', () => {
    const { getByLabelText, queryByText } = render(TimelineRow, { row: historyRow() });
    expect(getByLabelText('Success')).toBeInTheDocument();
    expect(queryByText('ok')).toBeNull();
  });

  it('shows a compact in/out token badge in the collapsed header', () => {
    const { getByText } = render(TimelineRow, { row: historyRow() });
    expect(getByText('↓1.2k')).toBeInTheDocument();
    expect(getByText('↑340')).toBeInTheDocument();
  });

  it('expands to show exact tokens and a pretty-printed input', async () => {
    const { container, getByText } = render(TimelineRow, { row: historyRow() });
    await fireEvent.click(container.querySelector('.head') as HTMLElement);
    // Exact (comma-grouped) token counts in the detail.
    expect(getByText(/1,234 in/)).toBeInTheDocument();
    expect(getByText(/340 out/)).toBeInTheDocument();
    // Python-dict input is reformatted as indented JSON.
    const pre = container.querySelector('pre.code') as HTMLElement;
    expect(pre.textContent).toContain('"relative_path": "src/foo.py"');
    expect(pre.textContent).toContain('"flag": true');
  });

  it('copies the formatted input to the clipboard', async () => {
    const { container, getByLabelText } = render(TimelineRow, { row: historyRow() });
    await fireEvent.click(container.querySelector('.head') as HTMLElement);
    await fireEvent.click(getByLabelText('Copy input'));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('"relative_path": "src/foo.py"'),
    );
  });
});
