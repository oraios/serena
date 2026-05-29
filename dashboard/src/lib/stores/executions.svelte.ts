import { fetchQueuedExecutions, fetchLastExecution, cancelExecution } from '$lib/api/endpoints';
import { runMutation } from '$lib/api/mutation';
import type { QueuedExecution } from '$lib/api/types';

export function createExecutionsStore() {
  let queued = $state<QueuedExecution[]>([]);
  let last = $state<QueuedExecution | null>(null);
  // Client-side list of cancelled/abandoned tasks for the Cancelled Executions panel
  // (legacy behaviour: there is no backend endpoint for this).
  let cancelled = $state<QueuedExecution[]>([]);
  let cancelError = $state('');
  // task_ids with an in-flight cancel, to dedupe concurrent double-clicks on a
  // queued item's × (which would otherwise fire two requests for the same task).
  const inFlight = new Set<number>();

  return {
    get queued() {
      return queued;
    },
    get last() {
      return last;
    },
    get cancelled() {
      return cancelled;
    },
    get cancelError() {
      return cancelError;
    },
    clearCancelError() {
      cancelError = '';
    },
    async pollQueued() {
      queued = (await fetchQueuedExecutions()).queued_executions;
    },
    async pollLast() {
      // Only surface user-facing (logged) executions. The backend runs internal tasks
      // (e.g. _get_config_overview every second) with logged=False; without this filter
      // the "Last Execution" panel would almost always show an internal task. Matches legacy.
      const latest = (await fetchLastExecution()).last_execution;
      last = latest && latest.logged ? latest : null;
    },
    async cancel(execution: QueuedExecution) {
      if (inFlight.has(execution.task_id)) return { ok: false };
      inFlight.add(execution.task_id);
      cancelError = '';
      try {
        const res = await runMutation(() => cancelExecution(execution.task_id));
        if (!res.ok) {
          cancelError = res.message ?? 'Failed to cancel execution';
          return res;
        }
        // Dedupe: a queued item can be cancelled again before the next poll removes
        // it, so guard against recording the same task twice (duplicate {#each} key).
        if (!cancelled.some((c) => c.task_id === execution.task_id)) {
          cancelled = [...cancelled, execution];
        }
        return res;
      } finally {
        inFlight.delete(execution.task_id);
      }
    },
  };
}

export const executions = createExecutionsStore();
