export type Theme = 'light' | 'dark';
export type ThemePref = 'system' | 'light' | 'dark';
const KEY = 'serena-dashboard-theme';

export function createThemeStore() {
  let preference = $state<ThemePref>('system');
  let current = $state<Theme>('light');

  function systemTheme(): Theme {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function apply() {
    current = preference === 'system' ? systemTheme() : preference;
    document.documentElement.setAttribute('data-theme', current);
  }

  return {
    // Resolved theme actually in effect ('light' | 'dark').
    get current() {
      return current;
    },
    // User's selection ('system' | 'light' | 'dark').
    get preference() {
      return preference;
    },
    init() {
      const stored = localStorage.getItem(KEY) as ThemePref | null;
      preference = stored ?? 'system';
      apply();
      // Track OS changes while following the system preference.
      window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
        if (preference === 'system') apply();
      });
    },
    set(pref: ThemePref) {
      preference = pref;
      apply();
      localStorage.setItem(KEY, pref);
    },
    toggle() {
      this.set(current === 'dark' ? 'light' : 'dark');
    },
  };
}

export const theme = createThemeStore();
