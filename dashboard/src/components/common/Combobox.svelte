<script lang="ts">
  import Icon from './Icon.svelte';
  import { ChevronDown } from '@lucide/svelte';

  let {
    options,
    value = '',
    placeholder = 'Type to filter…',
    onselect,
  }: {
    options: string[];
    value?: string;
    placeholder?: string;
    onselect: (_v: string) => void;
  } = $props();

  // eslint-disable-next-line svelte/valid-compile
  let query = $state(value);
  let openList = $state(false);
  let root = $state<HTMLDivElement | null>(null);

  const filtered = $derived(options.filter((o) => o.toLowerCase().includes(query.toLowerCase())));

  function choose(o: string) {
    query = o;
    openList = false;
    onselect(o);
  }

  // Close only when focus actually leaves the combobox. Using focusout (rather than a
  // timed blur) makes option selection correct-by-construction for both mouse and keyboard:
  // clicking/tabbing to an option moves focus within the root, so the list stays open until
  // `choose` runs; tabbing away (relatedTarget outside the root) closes it.
  function onFocusOut(e: FocusEvent) {
    const next = e.relatedTarget as Node | null;
    if (next && root?.contains(next)) return;
    openList = false;
  }

  function onOptionKey(e: KeyboardEvent, o: string) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      choose(o);
    }
  }
</script>

<div class="combobox" bind:this={root} onfocusout={onFocusOut}>
  <input
    type="text"
    {placeholder}
    bind:value={query}
    onfocus={() => (openList = true)}
    oninput={() => (openList = true)}
    autocomplete="off"
    spellcheck="false"
  />
  <span class="combobox-caret" aria-hidden="true"><Icon icon={ChevronDown} size={12} /></span>
  {#if openList}
    {#if filtered.length}
      <ul class="combobox-options" role="listbox">
        {#each filtered as o (o)}
          <li
            role="option"
            aria-selected={o === query}
            tabindex="0"
            onclick={() => choose(o)}
            onkeydown={(e) => onOptionKey(e, o)}
          >
            {o}
          </li>
        {/each}
      </ul>
    {:else}
      <div class="combobox-empty">No options available</div>
    {/if}
  {/if}
</div>

<style>
  .combobox {
    position: relative;
  }

  input {
    width: 100%;
    padding: var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-card);
    color: var(--text-primary);
    font-family: var(--font-sans);
  }

  .combobox-caret {
    position: absolute;
    right: var(--space-2);
    top: var(--space-2);
    pointer-events: none;
  }

  .combobox-options {
    list-style: none;
    margin: 0;
    padding: 0;
    position: absolute;
    z-index: 5;
    width: 100%;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    max-height: 200px;
    overflow: auto;
  }

  .combobox-options li {
    padding: var(--space-2);
    cursor: pointer;
  }

  .combobox-options li:hover {
    background: var(--bg-secondary-btn);
  }

  .combobox-empty {
    padding: var(--space-2);
    color: var(--text-muted);
  }
</style>
