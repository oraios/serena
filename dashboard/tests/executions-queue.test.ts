import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, getAllByRole } from '@testing-library/svelte';
import ExecutionsQueue from '../src/components/overview/ExecutionsQueue.svelte';
import { exec } from './helpers';

describe('ExecutionsQueue', () => {
  it('renders a cancel button for a queued (non-running) item and emits the execution', async () => {
    const item = exec({ task_id: 9, is_running: false, name: 'queued-task' });
    const oncancelexecution = vi.fn();
    render(ExecutionsQueue, { props: { items: [item], cancelError: '', oncancelexecution } });
    await fireEvent.click(screen.getByTestId('cancel-btn'));
    expect(oncancelexecution).toHaveBeenCalledWith(item);
  });

  it('shows a cancel button for every logged item', () => {
    const { container } = render(ExecutionsQueue, {
      props: {
        items: [
          exec({ task_id: 1, is_running: true, name: 'run' }),
          exec({ task_id: 2, name: 'queued' }),
        ],
        oncancelexecution: vi.fn(),
      },
    });
    expect(getAllByRole(container, 'button').length).toBe(2);
  });

  it('hides unlogged background tasks', () => {
    const { container, queryByText } = render(ExecutionsQueue, {
      props: {
        items: [
          exec({ task_id: 1, is_running: true, name: 'logged-task' }),
          exec({ task_id: 2, name: '_get_config_overview', logged: false }),
        ],
        oncancelexecution: vi.fn(),
      },
    });
    expect(container.querySelectorAll('.execution-item').length).toBe(1);
    expect(queryByText('_get_config_overview')).toBeNull();
  });

  it('shows the cancel error when set', () => {
    render(ExecutionsQueue, {
      props: { items: [exec({})], cancelError: 'too late', oncancelexecution: vi.fn() },
    });
    expect(screen.getByText('too late')).toBeInTheDocument();
  });
});
