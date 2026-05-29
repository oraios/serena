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
      nextIdx = res.max_idx;
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
