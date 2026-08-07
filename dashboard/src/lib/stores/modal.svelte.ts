import type { QueuedExecution } from '$lib/api/types';

export type ModalState =
  | { kind: 'shutdown' }
  | { kind: 'cancelExecution'; execution: QueuedExecution }
  | { kind: 'addLanguage' }
  | { kind: 'removeLanguage'; language: string }
  | { kind: 'editMemory'; name: string }
  | { kind: 'deleteMemory'; name: string }
  | { kind: 'createMemory' }
  | { kind: 'editSerenaConfig' };

export function createModalStore() {
  let active = $state<ModalState | null>(null);
  return {
    get active() {
      return active;
    },
    open(s: ModalState) {
      active = s;
    },
    close() {
      active = null;
    },
  };
}

export const modal = createModalStore();
