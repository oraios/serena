import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import SummaryCards from '../src/components/overview/SummaryCards.svelte';
import type { ToolStatsTotals } from '../src/lib/api/types';

const totals: ToolStatsTotals = {
  num_calls: 1234,
  num_errors: 7,
  total_duration_ms: 90123,
  total_tokens: 5678,
};

describe('SummaryCards', () => {
  it('renders four cards with formatted values', () => {
    const { container } = render(SummaryCards, { totals });
    const headings = container.querySelectorAll('[data-card-title]');
    expect(headings.length).toBe(4);
    const labels = Array.from(headings).map((n) => n.textContent?.trim());
    expect(labels).toEqual(['Calls', 'Tokens', 'Time', 'Errors']);
    expect(container.textContent).toContain('1,234');
    expect(container.textContent).toContain('7');
  });

  it('renders em-dashes when totals is undefined (older backend)', () => {
    const { container } = render(SummaryCards, { totals: undefined });
    expect(container.textContent).toContain('—');
  });
});
