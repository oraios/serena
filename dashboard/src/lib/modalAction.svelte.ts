import type { MutationResult } from './api/mutation';

/**
 * Owns the busy/error lifecycle shared by every mutating modal. Callers pass a function
 * returning a normalized MutationResult (wrap raw endpoints with `runMutation`), plus an
 * onSuccess callback (typically `onclose`). Must be a `.svelte.ts` module so it can hold $state.
 */
export function createModalAction() {
  let busy = $state(false);
  let error = $state('');
  return {
    get busy() {
      return busy;
    },
    get error() {
      return error;
    },
    clearError() {
      error = '';
    },
    async run(
      fn: () => Promise<MutationResult<unknown>>,
      onSuccess: () => void,
    ): Promise<MutationResult<unknown>> {
      busy = true;
      error = '';
      const res = await fn();
      busy = false;
      if (!res.ok) {
        error = res.message ?? '';
        return res;
      }
      onSuccess();
      return res;
    },
  };
}
