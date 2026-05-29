<script lang="ts">
  import { theme } from '$lib/stores/theme.svelte';
  import ThemeToggle from './ThemeToggle.svelte';
  import BannerCarousel from '../banners/BannerCarousel.svelte';
  type View = 'overview' | 'logs' | 'stats';
  let {
    active,
    onnavigate,
    onshutdown,
  }: { active: View; onnavigate: (_v: View) => void; onshutdown: () => void } = $props();
  const logoSrc = $derived(
    theme.current === 'dark' ? 'serena-logo-dark-mode.svg' : 'serena-logo.svg',
  );
</script>

<header class="header">
  <div class="header-left">
    <div class="logo-container"><img id="serena-logo" src={logoSrc} alt="Serena" /></div>
    <div id="platinum-banners" class="header-banner"><BannerCarousel target="platinum" /></div>
  </div>
  <nav class="header-nav">
    <div class="header-actions">
      <ThemeToggle />
      <button type="button" class="shutdown-button" onclick={() => onshutdown()}>
        Shutdown Server
      </button>
    </div>
    <div class="header-tabs">
      <button
        type="button"
        class="header-tab"
        class:active={active === 'overview'}
        onclick={() => onnavigate('overview')}>Overview</button
      >
      <button
        type="button"
        class="header-tab"
        class:active={active === 'logs'}
        onclick={() => onnavigate('logs')}>Logs</button
      >
      <button
        type="button"
        class="header-tab"
        class:active={active === 'stats'}
        onclick={() => onnavigate('stats')}>Stats</button
      >
    </div>
  </nav>
</header>

<style>
  /* Card-bar header matching legacy .header. */
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
    padding: var(--space-6);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    min-height: 150px;
    max-width: var(--max-width);
    margin: 0 auto;
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: var(--space-6);
  }
  .header-banner {
    display: flex;
    align-items: center;
  }
  #serena-logo {
    height: 130px;
  }
  .header-nav {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-3);
  }
  .header-actions {
    position: relative;
    display: flex;
    gap: var(--space-2);
  }
  .shutdown-button {
    background: var(--bg-secondary-btn);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
    color: var(--text-primary);
    font-family: var(--font-sans);
  }
  .shutdown-button:hover {
    background: var(--bg-card);
  }
  .header-tabs {
    display: flex;
    gap: var(--space-4);
  }
  .header-tab {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-primary);
    font-family: var(--font-sans);
    padding-bottom: var(--space-1);
  }
  .header-tab.active {
    color: var(--accent);
    border-bottom: 2px solid var(--accent);
  }
</style>
