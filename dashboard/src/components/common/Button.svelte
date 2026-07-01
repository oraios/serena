<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    variant = 'primary',
    disabled = false,
    onclick,
    children,
  }: {
    variant?: 'primary' | 'secondary' | 'danger';
    disabled?: boolean;
    onclick?: () => void;
    children: Snippet;
  } = $props();
</script>

<button class="btn {variant}" {disabled} {onclick}>{@render children()}</button>

<style>
  .btn {
    font-family: var(--font-sans);
    font-weight: 500;
    border: none;
    border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-4);
    cursor: pointer;
  }
  .primary {
    background: var(--accent);
    color: var(--text-on-accent);
  }
  .primary:hover {
    background: var(--accent-hover);
  }
  .secondary {
    background: var(--bg-secondary-btn);
    color: var(--text-primary);
  }
  .secondary:hover {
    background: var(--btn-secondary-hover);
  }
  .danger {
    background: var(--log-error);
    color: var(--text-on-accent);
  }
  .btn:disabled {
    background: var(--btn-disabled);
    cursor: not-allowed;
  }
</style>
