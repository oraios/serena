import { fetchLogMessages, clearLogs as apiClearLogs } from '$lib/api/endpoints';

export function createLogsStore() {
  let lines = $state<string[]>([]);
  let nextIdx = $state(0);
  let activeProject = $state<string | null>(null);

  return {
    get lines() {
      return lines;
    },
    get activeProject() {
      return activeProject;
    },
    async poll() {
      const res = await fetchLogMessages(nextIdx);
      if (res.messages.length) lines = [...lines, ...res.messages];
      // `max_idx` is the 0-based index of the *last* message returned and
      // `get_log_messages(from_idx)` is inclusive of `from_idx`, so the next
      // fetch must start one past the last seen index — otherwise every poll
      // re-fetches and re-appends the tail line. See LogBuffer in
      // src/serena/util/logging.py.
      nextIdx = res.max_idx + 1;
      activeProject = res.active_project;
    },
    async clear() {
      await apiClearLogs();
      lines = [];
      nextIdx = 0;
    },
  };
}

export const logs = createLogsStore();
