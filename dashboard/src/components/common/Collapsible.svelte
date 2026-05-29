<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    title,
    open = false,
    children,
  }: { title: string; open?: boolean; children: Snippet } = $props();
  // eslint-disable-next-line svelte/valid-compile
  let expanded = $state(open);

  function toggle() {
    expanded = !expanded;
  }
</script>

<section class="collapsible">
  <h2 class="collapsible-header">
    <button type="button" class="collapsible-trigger" onclick={toggle} aria-expanded={expanded}>
      <span class="collapsible-title">{title}</span>
      <span class="toggle-icon" class:open={expanded}>▼</span>
    </button>
  </h2>
  {#if expanded}
    <div class="collapsible-content">{@render children()}</div>
  {/if}
</section>

<style>
  .collapsible-header {
    margin: 0;
    font-size: inherit;
    font-weight: inherit;
  }

  .collapsible-trigger {
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    width: 100%;
    background: none;
    border: none;
    padding: 0;
    text-align: left;
  }

  .collapsible-title {
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 15px;
    font-weight: 600;
    color: var(--text-muted);
  }

  .collapsible-trigger:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .toggle-icon {
    font-size: 10px;
    color: var(--text-muted);
    transition: transform 0.2s;
  }

  .toggle-icon.open {
    transform: rotate(180deg);
  }

  .collapsible-content {
    margin-top: var(--space-3);
  }
</style>
