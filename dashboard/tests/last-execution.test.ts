import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import LastExecution from '../src/components/overview/LastExecution.svelte';
import type { QueuedExecution } from '../src/lib/api/types';

function exec(over: Partial<QueuedExecution>): QueuedExecution {
  return {
    task_id: 5,
    is_running: false,
    name: 'init',
    finished_successfully: true,
    logged: true,
    ...over,
  };
}

describe('LastExecution', () => {
  it('renders the status word, name, and #task_id for a success', () => {
    render(LastExecution, {
      props: { execution: exec({ task_id: 5, finished_successfully: true }) },
    });
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
    expect(screen.getByText('init')).toBeInTheDocument();
    expect(screen.getByText('#5')).toBeInTheDocument();
  });

  it('renders Failed for an unsuccessful, non-running execution', () => {
    render(LastExecution, {
      props: { execution: exec({ finished_successfully: false, is_running: false }) },
    });
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });
});
