<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import FileTree from './FileTree.svelte';
  import FileSymbols from './FileSymbols.svelte';
  import WorkspaceSearch from './WorkspaceSearch.svelte';
  import DiagnosticsPanel from './DiagnosticsPanel.svelte';
</script>

<div class="layout">
  <aside class="tree">
    <FileTree />
  </aside>
  <section class="middle">
    <nav class="middle-tabs">
      <button
        type="button"
        class:active={code.middle_pane === 'symbols'}
        onclick={() => code.setMiddlePane('symbols')}
      >
        Symbols (file)
      </button>
      <button
        type="button"
        class:active={code.middle_pane === 'search'}
        onclick={() => code.setMiddlePane('search')}
      >
        Search (workspace)
      </button>
    </nav>
    {#if code.middle_pane === 'symbols'}
      <FileSymbols />
    {:else}
      <WorkspaceSearch />
    {/if}
  </section>
  <aside class="diagnostics">
    <DiagnosticsPanel />
  </aside>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 260px 1fr 320px;
    gap: var(--space-2);
    height: calc(100vh - 140px);
  }
  .tree,
  .middle,
  .diagnostics {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .middle-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }
  .middle-tabs button {
    background: transparent;
    border: 0;
    padding: var(--space-2);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .middle-tabs button.active {
    color: var(--accent);
    border-bottom: 2px solid var(--accent);
  }
  .tree {
    overflow-y: auto;
  }
  @media (max-width: 1000px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto auto;
      height: auto;
    }
  }
</style>
