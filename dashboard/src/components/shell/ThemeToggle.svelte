<script lang="ts">
  import { theme } from '$lib/stores/theme.svelte';
</script>

<button class="theme-toggle" onclick={() => theme.toggle()}>
  <span style="height:21px">{theme.current === 'dark' ? '☀' : '🌙'}</span>
  <span>{theme.current === 'dark' ? 'Light' : 'Dark'}</span>
</button>

<style>
  .theme-toggle {
    display: inline-flex;
    gap: var(--space-2);
    align-items: center;
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
    color: var(--text-primary);
  }
</style>
