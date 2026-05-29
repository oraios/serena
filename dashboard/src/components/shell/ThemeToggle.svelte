<script lang="ts">
  import { theme } from '$lib/stores/theme.svelte';
  const tooltip = $derived(
    theme.current === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
  );
</script>

<button
  class="theme-toggle"
  type="button"
  aria-label={tooltip}
  title={tooltip}
  onclick={() => theme.toggle()}
>
  <span class="icon" aria-hidden="true">{theme.current === 'dark' ? '☀' : '🌙'}</span>
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
  .icon {
    font-size: 18px;
    line-height: 1;
  }
</style>
