export type Theme = 'light' | 'dark';
const KEY = 'serena-dashboard-theme';

export function createThemeStore() {
  let current = $state<Theme>('light');

  function apply(t: Theme) {
    current = t;
    document.documentElement.setAttribute('data-theme', t);
  }

  return {
    get current() {
      return current;
    },
    init() {
      const stored = localStorage.getItem(KEY) as Theme | null;
      const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
      apply(stored ?? (prefersDark ? 'dark' : 'light'));
    },
    toggle() {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      apply(next);
      localStorage.setItem(KEY, next);
    },
  };
}

export const theme = createThemeStore();
