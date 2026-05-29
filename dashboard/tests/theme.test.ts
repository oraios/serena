import { describe, it, expect, beforeEach } from 'vitest';
import { createThemeStore } from '../src/lib/stores/theme.svelte';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('theme store', () => {
  it('defaults to the system preference', () => {
    const t = createThemeStore();
    t.init();
    expect(t.preference).toBe('system');
    expect(['light', 'dark']).toContain(t.current);
    expect(document.documentElement.getAttribute('data-theme')).toBe(t.current);
  });

  it('persists and applies an explicit preference', () => {
    const t = createThemeStore();
    t.init();
    t.set('dark');
    expect(t.preference).toBe('dark');
    expect(t.current).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem('serena-dashboard-theme')).toBe('dark');

    t.set('light');
    expect(t.current).toBe('light');
    expect(localStorage.getItem('serena-dashboard-theme')).toBe('light');
  });

  it('restores a stored preference on init', () => {
    localStorage.setItem('serena-dashboard-theme', 'dark');
    const t = createThemeStore();
    t.init();
    expect(t.preference).toBe('dark');
    expect(t.current).toBe('dark');
  });

  it('toggle flips to an explicit opposite theme', () => {
    const t = createThemeStore();
    t.init();
    const first = t.current;
    t.toggle();
    expect(t.current).not.toBe(first);
    expect(t.preference).toBe(t.current);
  });
});
