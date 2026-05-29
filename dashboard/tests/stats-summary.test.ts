import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StatsSummary from '../src/components/stats/StatsSummary.svelte';

describe('StatsSummary', () => {
  it('shows a Total tokens row equal to input + output', () => {
    render(StatsSummary, {
      props: {
        stats: {
          a: { num_times_called: 1, input_tokens: 10, output_tokens: 5 },
          b: { num_times_called: 2, input_tokens: 40, output_tokens: 20 },
        },
      },
    });
    expect(screen.getByText('Total tokens')).toBeInTheDocument();
    expect(screen.getByTestId('total-tokens')).toHaveTextContent('75');
  });
});
