<script lang="ts">
  import Icon from './Icon.svelte';
  import { ChevronDown, X, Check } from '@lucide/svelte';

  interface Option {
    value: string;
    label: string;
  }

  interface Props {
    options: Option[];
    value: string | null;
    placeholder?: string;
    onChange?: (_v: string | null) => void;
  }

  let { options, value, placeholder = 'All', onChange }: Props = $props();

  let open = $state(false);
  let query = $state('');
  let highlight = $state(0);
  let inputEl: HTMLInputElement | undefined = $state();
  let rootEl: HTMLDivElement | undefined = $state();

  const filtered = $derived(
    options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())),
  );

  function toggle() {
    open = !open;
    if (open) {
      const idx = filtered.findIndex((o) => o.value === value);
      highlight = idx >= 0 ? idx : 0;
      queueMicrotask(() => inputEl?.focus());
    }
  }

  function selectAt(idx: number) {
    const o = filtered[idx];
    if (!o) return;
    onChange?.(o.value);
    open = false;
    query = '';
  }

  function clear(e: Event) {
    e.stopPropagation();
    onChange?.(null);
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlight = Math.min(filtered.length - 1, highlight + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlight = Math.max(0, highlight - 1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      selectAt(highlight);
    } else if (e.key === 'Escape') {
      open = false;
    }
  }

  function onClickOutside(e: MouseEvent) {
    if (!rootEl) return;
    if (!rootEl.contains(e.target as Node)) {
      open = false;
    }
  }

  $effect(() => {
    if (open) {
      document.addEventListener('mousedown', onClickOutside);
      return () => document.removeEventListener('mousedown', onClickOutside);
    }
  });

  const display = $derived(
    value ? (options.find((o) => o.value === value)?.label ?? value) : placeholder,
  );
</script>

<div bind:this={rootEl} class="root" class:active={value !== null}>
  <button
    type="button"
    class="trigger"
    aria-haspopup="listbox"
    aria-expanded={open}
    onclick={toggle}
  >
    <span class="label">{display}</span>
    {#if value !== null}
      <span
        role="button"
        tabindex="0"
        aria-label="Clear filter"
        class="clear"
        onclick={clear}
        onkeydown={(e) => e.key === 'Enter' && clear(e)}><Icon icon={X} size={12} /></span
      >
    {/if}
    <span class="chev" aria-hidden="true"><Icon icon={ChevronDown} size={12} /></span>
  </button>

  {#if open}
    <div class="panel" role="listbox">
      <input
        bind:this={inputEl}
        bind:value={query}
        placeholder="Filter…"
        class="filter-input"
        onkeydown={onKey}
      />
      <ul class="list">
        {#each filtered as o, i (o.value)}
          <li
            role="option"
            aria-selected={o.value === value}
            class:highlight={i === highlight}
            onmouseenter={() => (highlight = i)}
            onclick={() => selectAt(i)}
            onkeydown={(e) => e.key === 'Enter' && selectAt(i)}
          >
            <span class="check"
              >{#if o.value === value}<Icon icon={Check} size={12} />{/if}</span
            >
            <span>{o.label}</span>
          </li>
        {/each}
        {#if filtered.length === 0}
          <li class="empty">No matches</li>
        {/if}
      </ul>
    </div>
  {/if}
</div>

<style>
  .root {
    position: relative;
    display: inline-block;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-primary);
    border-radius: var(--radius);
    cursor: pointer;
    font-family: inherit;
  }
  .root.active .trigger {
    border-color: var(--accent);
  }
  .clear {
    color: var(--text-muted);
    cursor: pointer;
    user-select: none;
  }
  .clear:hover {
    color: var(--accent);
  }
  .chev {
    color: var(--text-muted);
  }
  .panel {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 200px;
    background: var(--bg-card);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    z-index: 50;
  }
  .filter-input {
    width: 100%;
    padding: var(--space-2);
    border: none;
    border-bottom: 1px solid var(--border);
    background: transparent;
    color: var(--text-primary);
    font-family: inherit;
    outline: none;
  }
  .filter-input:focus {
    border-bottom-color: var(--accent);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: var(--space-1) 0;
    max-height: 240px;
    overflow-y: auto;
  }
  .list li {
    display: flex;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }
  .list li.highlight {
    background: var(--bg-secondary-btn);
  }
  .check {
    width: 1em;
    color: var(--accent);
  }
  .empty {
    color: var(--text-muted);
    padding: var(--space-2);
  }
</style>
