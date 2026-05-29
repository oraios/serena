<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import {
    countByKind,
    pluralizeKind,
    flattenForDisplay,
    getKindMeta,
    KIND_ORDER,
    type DisplayRow,
  } from '$lib/symbolTree';
  import Icon from '../common/Icon.svelte';
  import {
    ChevronRight,
    ChevronDown,
    ChevronsDown,
    ChevronsUp,
    Search,
    Copy,
    Check,
  } from '@lucide/svelte';

  const path = $derived(code.selected_path);
  const symbols = $derived(path ? code.file_symbols[path] : undefined);
  const error = $derived(path ? code.file_symbol_errors[path] : undefined);
  const filter = $derived(path ? code.getSymbolFilter(path) : '');
  const EMPTY_EXPANDED: ReadonlySet<string> = new Set();
  const expanded = $derived<ReadonlySet<string>>(
    path ? code.getExpandedSymbols(path) : EMPTY_EXPANDED,
  );

  const rows = $derived<DisplayRow[]>(symbols ? flattenForDisplay(symbols, expanded, filter) : []);
  const counts = $derived(symbols ? countByKind(symbols) : {});
  const pathParts = $derived(path ? path.split('/') : []);

  let copiedKey = $state<string | null>(null);
  let barH = $state(0);
  let filterTimer: ReturnType<typeof setTimeout> | null = null;

  function retry() {
    if (path) void code.loadFileSymbols(path, true);
  }

  function onFilterInput(e: Event) {
    const value = (e.target as HTMLInputElement).value;
    const p = path;
    if (!p) return;
    // Debounced 100ms (spec §"Filter input") — re-filtering walks the whole tree.
    if (filterTimer) clearTimeout(filterTimer);
    filterTimer = setTimeout(() => code.setSymbolFilter(p, value), 100);
  }

  function clickBreadcrumb(idx: number) {
    if (!path) return;
    const target = pathParts.slice(0, idx + 1).join('/');
    if (idx < pathParts.length - 1) {
      // Expand-only: a breadcrumb click reveals the directory, never collapses it.
      code.expandPath(target);
    }
  }

  async function copyLoc(row: DisplayRow) {
    if (!path) return;
    const ref = `${path}:${row.symbol.range.start.line + 1}`;
    try {
      await navigator.clipboard.writeText(ref);
      copiedKey = row.key;
      setTimeout(() => {
        if (copiedKey === row.key) copiedKey = null;
      }, 1000);
    } catch {
      /* clipboard unavailable — silently ignore */
    }
  }

  function onRowChevron(row: DisplayRow) {
    if (!path || !row.hasChildren) return;
    code.toggleSymbolExpand(path, row.key);
  }
</script>

<div class="root" style:--bar-h="{barH}px">
  {#if !path}
    <p class="empty">Select a file from the tree.</p>
  {:else if error !== undefined}
    <div class="error-card">
      <strong>Failed to load symbols.</strong>
      <div class="msg">{error}</div>
      <button type="button" class="retry" onclick={retry}>Retry</button>
    </div>
  {:else if symbols === undefined}
    <p class="empty">Loading…</p>
  {:else}
    <header class="bar" bind:offsetHeight={barH}>
      <nav class="breadcrumb" aria-label="File path">
        {#each pathParts as part, i (i)}
          {#if i > 0}<span class="sep" aria-hidden="true">›</span>{/if}
          {#if i < pathParts.length - 1}
            <button type="button" class="crumb" onclick={() => clickBreadcrumb(i)}>{part}</button>
          {:else}
            <span class="crumb leaf">{part}</span>
          {/if}
        {/each}
      </nav>
      <div class="counts">
        {#each KIND_ORDER.filter((k) => counts[k]) as k, i (k)}
          {#if i > 0}<span class="dot">·</span>{/if}
          <span>{pluralizeKind(k, counts[k])}</span>
        {/each}
        {#if Object.keys(counts).length === 0}
          <span class="muted">No symbols.</span>
        {/if}
      </div>
      <div class="controls">
        <label class="filter">
          <Icon icon={Search} size={14} />
          <input
            type="search"
            placeholder="Filter symbols…"
            value={filter}
            oninput={onFilterInput}
          />
        </label>
        <button
          type="button"
          class="icon-btn"
          aria-label="Expand all"
          title="Expand all"
          onclick={() => path && code.expandAllSymbols(path)}
        >
          <Icon icon={ChevronsDown} size={14} />
        </button>
        <button
          type="button"
          class="icon-btn"
          aria-label="Collapse all"
          title="Collapse all"
          onclick={() => path && code.collapseAllSymbols(path)}
        >
          <Icon icon={ChevronsUp} size={14} />
        </button>
      </div>
    </header>

    {#if rows.length === 0 && symbols.length > 0}
      <p class="empty">No matches.</p>
    {:else if symbols.length === 0}
      <p class="empty">No symbols.</p>
    {:else}
      <ul class="list">
        {#each rows as row (row.key)}
          {@const meta = getKindMeta(row.symbol.kind)}
          <li
            class="row"
            class:has-children={row.hasChildren}
            class:depth-0={row.depth === 0}
            style:--depth={row.depth}
            style:--kind-color="var({meta.colorVar})"
          >
            {#if row.hasChildren}
              <button
                type="button"
                class="chev"
                aria-label={row.isExpanded ? 'Collapse' : 'Expand'}
                onclick={() => onRowChevron(row)}
              >
                <Icon icon={row.isExpanded ? ChevronDown : ChevronRight} size={12} />
              </button>
            {:else}
              <span class="chev" aria-hidden="true"></span>
            {/if}
            <span class="badge" title={meta.label}>
              <Icon icon={meta.icon} size={12} />
            </span>
            <span class="name">{row.symbol.name}</span>
            <button type="button" class="loc" title="Copy path:line" onclick={() => copyLoc(row)}>
              {#if copiedKey === row.key}
                <Icon icon={Check} size={12} />
                <span>copied</span>
              {:else}
                <span>{row.symbol.range.start.line + 1}:{row.symbol.range.start.character + 1}</span
                >
                <Icon icon={Copy} size={12} class="copy-icon" />
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-3);
  }
  .bar {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--bg-elevated);
    border-bottom: 1px solid var(--border);
    padding: var(--space-2);
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas:
      'crumb controls'
      'counts counts';
    gap: var(--space-1) var(--space-2);
  }
  .breadcrumb {
    grid-area: crumb;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1);
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .crumb {
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 0;
  }
  .crumb:hover {
    color: var(--text-primary);
    text-decoration: underline;
  }
  .crumb.leaf {
    color: var(--text-primary);
    font-weight: 600;
    cursor: default;
  }
  .sep {
    color: var(--text-muted);
  }
  .counts {
    grid-area: counts;
    color: var(--text-secondary);
    font-size: 0.8em;
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .dot {
    color: var(--text-muted);
  }
  .muted {
    color: var(--text-muted);
  }
  .controls {
    grid-area: controls;
    display: flex;
    align-items: center;
    gap: var(--space-1);
  }
  .filter {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 0 var(--space-2);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-secondary);
  }
  .filter input {
    background: transparent;
    border: 0;
    padding: var(--space-1);
    color: var(--text-primary);
    font-family: inherit;
    font-size: 0.85em;
    outline: none;
    width: 140px;
  }
  .icon-btn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: var(--space-1);
    color: var(--text-secondary);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .icon-btn:hover {
    color: var(--text-primary);
    background: var(--bg);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .row {
    display: grid;
    grid-template-columns: 18px 22px 1fr auto;
    align-items: center;
    gap: var(--space-2);
    padding: 2px var(--space-2);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    color: var(--text-primary);
    position: relative;
  }
  .row:hover {
    background: var(--bg);
  }
  /* Subtle indent guide: a 1px column drawn at each depth.
     Depth 0 has no guide (no parent to draw under). */
  .row::before {
    content: '';
    position: absolute;
    left: calc(var(--space-2) + var(--depth, 0) * var(--space-3) - var(--space-1));
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border);
    opacity: 0.6;
  }
  .row.depth-0::before {
    opacity: 0;
  }
  .chev {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    cursor: pointer;
  }
  span.chev {
    cursor: default;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--kind-color) 18%, transparent);
    color: var(--kind-color);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .loc {
    background: transparent;
    border: 0;
    color: var(--text-muted);
    font-family: inherit;
    font-size: 0.95em;
    cursor: pointer;
    font-variant-numeric: tabular-nums;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .loc:hover {
    color: var(--text-primary);
  }
  .row:hover .loc :global(.copy-icon) {
    opacity: 1;
  }
  .loc :global(.copy-icon) {
    opacity: 0;
    transition: opacity 0.12s;
  }
  /* Sticky depth-0 parents only — nested parents shouldn't stack at top:0.
     Pin BELOW the sticky header bar (--bar-h), otherwise the opaque, higher
     z-index bar (which also sits at top:0) hides the pinned parent entirely. */
  .row.has-children.depth-0 {
    position: sticky;
    top: var(--bar-h, 0px);
    background: var(--bg-elevated);
    z-index: 1;
  }
  .error-card {
    background: var(--bg);
    border: 1px solid var(--log-error);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--log-error);
    margin: var(--space-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .error-card .msg {
    font-family: var(--font-mono);
    font-size: 0.85em;
    color: var(--text-primary);
  }
  .retry {
    align-self: flex-start;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    color: var(--text-primary);
    cursor: pointer;
  }
</style>
