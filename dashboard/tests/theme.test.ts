import { describe, it, expect, beforeEach } from 'vitest';
import { createThemeStore } from '../src/lib/stores/theme.svelte';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('theme store', () => {
  it('persists and applies the theme on toggle', () => {
    const t = createThemeStore();
    t.init();
    const first = t.current;
    t.toggle();
    expect(t.current).not.toBe(first);
    expect(document.documentElement.getAttribute('data-theme')).toBe(t.current);
    expect(localStorage.getItem('serena-dashboard-theme')).toBe(t.current);
  });
});
