<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import type { FileSymbol } from '$lib/api/types';

  const path = $derived(code.selected_path);
  const symbols = $derived(path ? code.file_symbols[path] : undefined);
  const error = $derived(path ? code.file_symbol_errors[path] : undefined);

  function retry() {
    if (path) void code.loadFileSymbols(path, true);
  }
</script>

{#snippet symbolNode(s: FileSymbol, depth: number)}
  <li style:--depth={depth} class="row">
    <span class="kind">{s.kind}</span>
    <span class="name">{s.name}</span>
    <span class="loc">{s.range.start.line + 1}:{s.range.start.character + 1}</span>
  </li>
  {#if s.children && s.children.length > 0}
    {#each s.children as c (c.name + ':' + c.range.start.line)}
      {@render symbolNode(c, depth + 1)}
    {/each}
  {/if}
{/snippet}

<div class="root">
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
  {:else if symbols.length === 0}
    <p class="empty">No symbols.</p>
  {:else}
    <ul class="list">
      {#each symbols as s (s.name + ':' + s.range.start.line)}
        {@render symbolNode(s, 0)}
      {/each}
    </ul>
  {/if}
</div>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-3);
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
    grid-template-columns: 80px 1fr 60px;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    border-bottom: 1px solid var(--border);
  }
  .kind {
    color: var(--text-secondary);
  }
  .loc {
    color: var(--text-secondary);
    text-align: right;
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
