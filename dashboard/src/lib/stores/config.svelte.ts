import { fetchConfigOverview } from '$lib/api/endpoints';
import type { ResponseConfigOverview } from '$lib/api/types';

export function createConfigStore() {
  let data = $state<ResponseConfigOverview | null>(null);
  let lastJson = '';

  return {
    get data() {
      return data;
    },
    async poll() {
      const next = await fetchConfigOverview();
      const json = JSON.stringify(next);
      if (json !== lastJson) {
        data = next;
        lastJson = json;
      }
    },
  };
}

export const config = createConfigStore();
