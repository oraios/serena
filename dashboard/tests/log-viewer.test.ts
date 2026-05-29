import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import LogViewer from '../src/components/logs/LogViewer.svelte';

describe('LogViewer', () => {
  it('renders a line per message with a level class', () => {
    const { container } = render(LogViewer, {
      props: { lines: ['INFO hello', 'ERROR boom'], toolNames: [] },
    });
    const rows = container.querySelectorAll('.log-line');
    expect(rows.length).toBe(2);
    expect(rows[1].classList.contains('error')).toBe(true);
  });
});
