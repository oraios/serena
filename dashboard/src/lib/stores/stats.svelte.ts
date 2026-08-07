import { fetchToolStats, clearToolStats, fetchEstimatorName } from '$lib/api/endpoints';
import type { ToolStats } from '$lib/api/types';

export type SortKey = 'calls' | 'tokens' | 'duration_total' | 'duration_avg' | 'errors';

export function createStatsStore() {
  let stats = $state<ToolStats>({});
  let estimator = $state('unknown');
  let sortKey = $state<SortKey>('calls');
  let drillTool = $state<string | null>(null);

  return {
    get stats() {
      return stats;
    },
    get estimator() {
      return estimator;
    },
    get sortKey() {
      return sortKey;
    },
    get drillTool() {
      return drillTool;
    },
    setSortKey(k: SortKey) {
      sortKey = k;
    },
    setDrillTool(t: string | null) {
      drillTool = t;
    },
    async refresh() {
      stats = (await fetchToolStats()).stats;
      estimator = (await fetchEstimatorName()).token_count_estimator_name;
    },
    async clear() {
      await clearToolStats();
      stats = {};
      drillTool = null;
    },
  };
}

export const stats = createStatsStore();
