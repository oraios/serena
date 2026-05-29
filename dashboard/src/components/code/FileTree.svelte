<script lang="ts">
  import { code } from '$lib/stores/code.svelte';

  interface Props {
    rootPath?: string;
  }
  let { rootPath = '.' }: Props = $props();

  $effect(() => {
    void code.loadDir(rootPath);
  });

  function joinPath(base: string, child: string): string {
    if (base === '.' || base === '') return child;
    return `${base}/${child}`;
  }
</script>

{#snippet treeNode(path: string, depth: number)}
  {@const children = code.dir_children[path]}
  {@const error = code.dir_errors[path]}
  <ul class="list" style:--depth={depth}>
    {#if error !== undefined}
      <li class="error-row">
        <span class="warn" title={error}>⚠</span>
        <span class="err-msg">{error}</span>
      </li>
    {:else if !children}
      <li class="loading">…</li>
    {:else}
      {#each children as entry (entry.name)}
        {@const fullPath = joinPath(path, entry.name)}
        <li>
          {#if entry.kind === 'dir'}
            <button
              type="button"
              class="row dir"
              onclick={() => code.toggleExpand(fullPath)}
              aria-expanded={code.expanded.has(fullPath)}
            >
              <span class="chev">{code.expanded.has(fullPath) ? '▾' : '▸'}</span>
              <span class="name">{entry.name}</span>
              {#if code.dir_errors[fullPath] !== undefined}
                <span class="warn" title={code.dir_errors[fullPath]}>⚠</span>
              {/if}
            </button>
            {#if code.expanded.has(fullPath)}
              {@render treeNode(fullPath, depth + 1)}
            {/if}
          {:else}
            <button
              type="button"
              class="row file"
              class:selected={code.selected_path === fullPath}
              onclick={() => code.selectPath(fullPath)}
            >
              <span class="chev"></span>
              <span class="name">{entry.name}</span>
            </button>
          {/if}
        </li>
      {/each}
    {/if}
  </ul>
{/snippet}

{@render treeNode(rootPath, 0)}

<style>
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    text-align: left;
    background: transparent;
    border: 0;
    color: var(--text-primary);
    cursor: pointer;
    padding: var(--space-1);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    font-family: var(--font-mono);
    font-size: 0.9em;
  }
  .row:hover {
    background: var(--bg);
  }
  .row.selected {
    background: var(--bg);
    color: var(--accent);
  }
  .chev {
    width: 1em;
    color: var(--text-secondary);
  }
  .loading {
    color: var(--text-secondary);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
  }
  .error-row {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    color: var(--log-error);
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .err-msg {
    color: var(--log-error);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .warn {
    color: var(--log-error);
    margin-left: var(--space-1);
  }
</style>
