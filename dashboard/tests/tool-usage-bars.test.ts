import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import ToolUsageBars from '../src/components/overview/ToolUsageBars.svelte';

describe('ToolUsageBars', () => {
  it('renders tools sorted by call count descending', () => {
    const { getAllByTestId } = render(ToolUsageBars, {
      props: { stats: { a: { num_calls: 1 }, b: { num_calls: 5 } } },
    });
    const names = getAllByTestId('tool-bar-name').map((n) => n.textContent);
    expect(names).toEqual(['b', 'a']);
  });
});
