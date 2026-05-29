<script module lang="ts">
  // Per-instance counter for unique title ids (so aria-labelledby resolves even
  // with multiple modals mounted across a session).
  let modalUid = 0;
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onDestroy } from 'svelte';
  let {
    open = false,
    title = '',
    error = '',
    onclose,
    children,
  }: {
    open?: boolean;
    title?: string;
    error?: string;
    onclose: () => void;
    children: Snippet;
  } = $props();

  let contentEl = $state<HTMLDivElement | null>(null);
  let previouslyFocused: HTMLElement | null = null;
  const titleId = `modal-title-${modalUid++}`;

  // Move focus into the dialog when it opens, and restore it to the trigger on close,
  // so keyboard/screen-reader users land inside the modal instead of behind it.
  $effect(() => {
    if (open && contentEl) {
      previouslyFocused = document.activeElement as HTMLElement | null;
      contentEl.focus();
    }
  });
  onDestroy(() => previouslyFocused?.focus());

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      onclose();
      return;
    }
    if (e.key !== 'Tab' || !open || !contentEl) return;
    const focusable = contentEl.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const activeEl = document.activeElement;
    // Initial focus sits on the dialog container (tabindex=-1), which is NOT in
    // the focusable list. Treat "focus not within the list" as a boundary too,
    // otherwise the very first Shift+Tab escapes the trap to the page behind.
    const withinList = Array.prototype.indexOf.call(focusable, activeEl) !== -1;
    if (e.shiftKey && (activeEl === first || !withinList)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (activeEl === last || !withinList)) {
      e.preventDefault();
      first.focus();
    }
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <div class="backdrop" role="presentation" onclick={onclose} onkeydown={onKey}>
    <div
      class="modal-content"
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? titleId : undefined}
      tabindex="-1"
      bind:this={contentEl}
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => {
        // Run the trap/Escape logic here (keydowns inside the dialog never reach the
        // window listener), then stop propagation so the window handler can't double-fire.
        onKey(e);
        e.stopPropagation();
      }}
    >
      <button type="button" class="modal-close" aria-label="Close" onclick={onclose}>&times;</button
      >
      {#if title}<h3 id={titleId}>{title}</h3>{/if}
      {#if error}<p class="modal-error" role="alert">{error}</p>{/if}
      {@render children()}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(2px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal-content {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-6);
    max-width: 600px;
    width: 90%;
    box-shadow: var(--shadow-elevated);
    position: relative;
  }

  .modal-error {
    color: var(--log-error);
    margin: 0 0 var(--space-3);
  }

  .modal-close {
    position: absolute;
    top: var(--space-3);
    right: var(--space-4);
    cursor: pointer;
    font-size: 22px;
    color: var(--text-muted);
    background: none;
    border: none;
    line-height: 1;
    padding: 0;
  }
</style>
