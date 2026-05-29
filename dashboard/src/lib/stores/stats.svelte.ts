import { fetchToolStats, clearToolStats, fetchEstimatorName } from '$lib/api/endpoints';
import type { ToolStats } from '$lib/api/types';

export function createStatsStore() {
  let stats = $state<ToolStats>({});
  let estimator = $state('unknown');

  return {
    get stats() {
      return stats;
    },
    get estimator() {
      return estimator;
    },
    async refresh() {
      stats = (await fetchToolStats()).stats;
      estimator = (await fetchEstimatorName()).token_count_estimator_name;
    },
    async clear() {
      await clearToolStats();
      stats = {};
    },
  };
}

export const stats = createStatsStore();
