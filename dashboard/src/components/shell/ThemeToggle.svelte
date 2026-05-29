<script lang="ts">
  import { theme, type ThemePref } from '$lib/stores/theme.svelte';
  import Icon from '../common/Icon.svelte';
  import { Monitor, Sun, Moon } from '@lucide/svelte';

  const order: ThemePref[] = ['system', 'light', 'dark'];
  const meta: Record<ThemePref, { label: string; icon: typeof Sun }> = {
    system: { label: 'System', icon: Monitor },
    light: { label: 'Light', icon: Sun },
    dark: { label: 'Dark', icon: Moon },
  };

  const next = $derived(order[(order.indexOf(theme.preference) + 1) % order.length]);

  function cycle() {
    theme.set(next);
  }
</script>

<button
  class="theme-toggle"
  type="button"
  aria-label={`Theme: ${meta[theme.preference].label}. Switch to ${meta[next].label}`}
  title={`Theme: ${meta[theme.preference].label} (click for ${meta[next].label})`}
  onclick={cycle}
>
  <Icon icon={meta[theme.preference].icon} size={18} />
</button>

<style>
  .theme-toggle {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    cursor: pointer;
    color: var(--text-primary);
    padding: 0;
    line-height: 1;
  }
  .theme-toggle:hover {
    background: var(--bg-card);
  }
</style>
