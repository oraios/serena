<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import Icon from '../common/Icon.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { getFileIconMeta } from '$lib/fileIcons';
  import { ChevronRight, ChevronDown, TriangleAlert, Stethoscope } from '@lucide/svelte';

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
        <span class="warn" title={error}>
          <Icon icon={TriangleAlert} size={14} label="Error" />
        </span>
        <span class="err-msg">{error}</span>
      </li>
    {:else if !children}
      <li class="loading"><Spinner /><span>Loading…</span></li>
    {:else}
      {#each children as entry (entry.name)}
        {@const fullPath = joinPath(path, entry.name)}
        {@const meta = getFileIconMeta(
          entry.name,
          entry.kind,
          entry.kind === 'dir' && code.expanded.has(fullPath),
        )}
        <li>
          <div class="row-wrap">
            {#if entry.kind === 'dir'}
              <button
                type="button"
                class="row dir"
                class:depth-0={depth === 0}
                onclick={() => code.toggleExpand(fullPath)}
                aria-expanded={code.expanded.has(fullPath)}
              >
                <span class="chev">
                  <Icon icon={code.expanded.has(fullPath) ? ChevronDown : ChevronRight} size={14} />
                </span>
                <span class="ficon" style:--icon-color="var({meta.colorVar})">
                  <Icon icon={meta.icon} size={14} label={meta.label} />
                </span>
                <span class="name">{entry.name}</span>
                {#if code.dir_errors[fullPath] !== undefined}
                  <span class="warn" title={code.dir_errors[fullPath]}>
                    <Icon icon={TriangleAlert} size={14} label="Error" />
                  </span>
                {/if}
              </button>
            {:else}
              <button
                type="button"
                class="row file"
                class:depth-0={depth === 0}
                class:selected={code.selected_path === fullPath}
                onclick={() => code.selectPath(fullPath)}
              >
                <span class="chev" aria-hidden="true"></span>
                <span class="ficon" style:--icon-color="var({meta.colorVar})">
                  <Icon icon={meta.icon} size={14} label={meta.label} />
                </span>
                <span class="name">{entry.name}</span>
              </button>
            {/if}
            <button
              type="button"
              class="diag-action"
              aria-label={`Run diagnostics on ${entry.name}`}
              title={`Run diagnostics on ${entry.name}`}
              onclick={(e) => {
                e.stopPropagation();
                code.runDiagnosticsForPath(fullPath, entry.kind === 'dir' ? 'directory' : 'file');
              }}
            >
              <Icon icon={Stethoscope} size={13} />
            </button>
          </div>
          {#if entry.kind === 'dir' && code.expanded.has(fullPath)}
            {@render treeNode(fullPath, depth + 1)}
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
    flex: 1 1 auto;
    min-width: 0;
    text-align: left;
    background: transparent;
    border: 0;
    color: var(--text-primary);
    cursor: pointer;
    padding: var(--space-1);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    font-family: var(--font-mono);
    font-size: 0.9em;
    position: relative;
  }
  .row:hover {
    background: var(--bg);
  }
  .row.selected {
    background: var(--bg);
    color: var(--accent);
  }
  .row-wrap {
    display: flex;
    align-items: center;
  }
  .diag-action {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    cursor: pointer;
    padding: var(--space-1);
    opacity: 0;
  }
  .row-wrap:hover .diag-action,
  .diag-action:focus-visible,
  .diag-action:focus {
    opacity: 1;
  }
  .diag-action:hover {
    color: var(--accent);
  }
  .chev {
    width: 1em;
    color: var(--text-secondary);
  }
  .loading {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--text-secondary);
    padding: var(--space-1);
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
  .ficon {
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
    color: var(--icon-color, var(--text-secondary));
  }
  /* 1px indent guide per nesting level; depth-0 has no parent to draw under. */
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
</style>
