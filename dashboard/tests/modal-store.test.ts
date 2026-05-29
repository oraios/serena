import { describe, it, expect } from 'vitest';
import { createModalStore } from '../src/lib/stores/modal.svelte';

describe('modal store', () => {
  it('opens and closes a single active modal', () => {
    const m = createModalStore();
    expect(m.active).toBeNull();
    m.open({ kind: 'shutdown' });
    expect(m.active?.kind).toBe('shutdown');
    m.close();
    expect(m.active).toBeNull();
  });
});
