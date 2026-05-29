<script lang="ts">
  import type { Snippet, Component } from 'svelte';
  import Icon from './Icon.svelte';

  interface Props {
    label: string; // aria-label for the trigger button
    icon: Component<{
      size?: number | string;
      strokeWidth?: number | string;
      class?: string;
      'aria-hidden'?: 'true' | 'false' | boolean;
    }>;
    iconSize?: number;
    title?: string; // optional heading + dialog aria-label
    align?: 'left' | 'right';
    children: Snippet;
  }
  let { label, icon, iconSize = 16, title, align = 'right', children }: Props = $props();

  let open = $state(false);
  let root: HTMLElement;

  function toggle() {
    open = !open;
  }
  function onWindowKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && open) open = false;
  }
  function onWindowClick(e: MouseEvent) {
    // The trigger's own click toggles `open` before this bubbles to window;
    // a click inside `root` never closes, a click outside always does.
    if (open && root && !root.contains(e.target as Node)) open = false;
  }
</script>

<svelte:window onkeydown={onWindowKey} onclick={onWindowClick} />

<span class="popover-root" bind:this={root}>
  <button
    type="button"
    class="trigger"
    aria-label={label}
    aria-haspopup="dialog"
    aria-expanded={open}
    onclick={toggle}
  >
    <Icon {icon} size={iconSize} />
  </button>
  {#if open}
    <div class="panel" class:left={align === 'left'} role="dialog" aria-label={title ?? label}>
      {#if title}<h4 class="panel-title">{title}</h4>{/if}
      <div class="panel-body">{@render children()}</div>
    </div>
  {/if}
</span>

<style>
  .popover-root {
    position: relative;
    display: inline-flex;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: var(--space-1);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .trigger:hover,
  .trigger[aria-expanded='true'] {
    color: var(--text-primary);
    background: var(--bg);
  }
  .panel {
    position: absolute;
    top: calc(100% + var(--space-1));
    right: 0;
    z-index: 10;
    width: 320px;
    max-width: 80vw;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: 0 6px 24px color-mix(in srgb, var(--text-primary) 18%, transparent);
    padding: var(--space-2);
    text-align: left;
  }
  .panel.left {
    right: auto;
    left: 0;
  }
  .panel-title {
    margin: 0 0 var(--space-1);
    font-size: 0.9em;
    color: var(--text-primary);
  }
  .panel-body {
    color: var(--text-secondary);
    font-size: 0.85em;
  }
</style>
