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
      <button
        type="button"
        class="icon-button shutdown-button"
        aria-label="Shutdown Server"
        title="Shutdown Server"
        onclick={() => onshutdown()}
      >
        <span class="icon" aria-hidden="true">⏻</span>
      </button>
    </div>
    <div class="header-tabs" role="tablist">
      <button
        type="button"
        class="header-tab"
        class:active={active === 'overview'}
        aria-current={active === 'overview' ? 'page' : undefined}
        onclick={() => onnavigate('overview')}>Overview</button
      >
      <button
        type="button"
        class="header-tab"
        class:active={active === 'logs'}
        aria-current={active === 'logs' ? 'page' : undefined}
        onclick={() => onnavigate('logs')}>Logs</button
      >
      <button
        type="button"
        class="header-tab"
        class:active={active === 'stats'}
        aria-current={active === 'stats' ? 'page' : undefined}
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
    gap: var(--space-4);
  }
  .header-actions {
    position: relative;
    display: flex;
    gap: var(--space-2);
  }
  .icon-button {
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
  .icon-button:hover {
    background: var(--bg-card);
  }
  .icon-button .icon {
    font-size: 18px;
    line-height: 1;
  }
  .shutdown-button:hover {
    color: var(--danger, #c0392b);
    border-color: var(--danger, #c0392b);
  }
  .header-tabs {
    display: flex;
    gap: var(--space-5);
  }
  .header-tab {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-sm);
    border-bottom: 3px solid transparent;
    transition:
      background-color 120ms ease,
      color 120ms ease,
      border-color 120ms ease;
  }
  .header-tab:hover {
    background: var(--bg-secondary-btn);
  }
  .header-tab.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }
</style>
