<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import FileTree from './FileTree.svelte';
  import FileSymbols from './FileSymbols.svelte';
  import WorkspaceSearch from './WorkspaceSearch.svelte';
  import DiagnosticsPanel from './DiagnosticsPanel.svelte';
  import Popover from '../common/Popover.svelte';
  import { CircleHelp } from '@lucide/svelte';

  // Badge shows the number of files with diagnostics (spec §"Diagnostics tab")
  // — not the raw diagnostic count, which can be thousands (LSP noise on
  // lockfiles/markdown) and would clutter the tab.
  const diagFileCount = $derived(code.diag_files.length);
</script>

<div class="code-tab">
  <header class="toolbar">
    <span class="title">Code explorer</span>
    <div class="help-slot">
      <Popover
        label="How the Code explorer works"
        icon={CircleHelp}
        title="How the Code explorer works"
      >
        {#snippet children()}
          <dl class="help">
            <dt>File tree</dt>
            <dd>
              Project files &amp; folders from disk (respects project ignores). Hover a row to run
              diagnostics on that file or folder.
            </dd>
            <dt>Symbols (file)</dt>
            <dd>
              Outline of the open file via the LSP <code>textDocument/documentSymbol</code> request.
              Click a symbol to copy its <code>path:line</code>.
            </dd>
            <dt>Search (workspace)</dt>
            <dd>
              Symbol search across the whole project via the LSP <code>workspace/symbol</code>
              request.
            </dd>
            <dt>Diagnostics</dt>
            <dd>
              Errors &amp; warnings via the LSP <code>textDocument/diagnostic</code> request — a fresh
              pull for a single file, or published/push diagnostics for a directory or project scan. Scope
              it to the project, a file, or a directory. Computing is slow and briefly pauses other LSP
              tools — run it only when needed.
            </dd>
          </dl>
        {/snippet}
      </Popover>
    </div>
  </header>

  <div class="layout">
    <aside class="tree">
      <FileTree />
    </aside>
    <section class="middle">
      <nav class="middle-tabs" aria-label="Code views">
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
        <button
          type="button"
          class:active={code.middle_pane === 'diagnostics'}
          onclick={() => code.setMiddlePane('diagnostics')}
        >
          Diagnostics (project)
          {#if diagFileCount > 0}<span class="badge">· {diagFileCount}</span>{/if}
        </button>
      </nav>
      {#if code.middle_pane === 'symbols'}
        <FileSymbols />
      {:else if code.middle_pane === 'search'}
        <WorkspaceSearch />
      {:else}
        <DiagnosticsPanel />
      {/if}
    </section>
  </div>
</div>

<style>
  .code-tab {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 140px);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: 0 var(--space-1) var(--space-2);
  }
  .toolbar .title {
    font-weight: 600;
    font-size: 0.9em;
    color: var(--text-secondary);
  }
  .help-slot {
    margin-left: auto;
  }
  .help :global(dt) {
    font-weight: 600;
    color: var(--text-primary);
    margin-top: var(--space-2);
  }
  .help :global(dt):first-child {
    margin-top: 0;
  }
  .help :global(dd) {
    margin: 0;
  }
  .help :global(code) {
    font-family: var(--font-mono);
    font-size: 0.95em;
    color: var(--text-primary);
  }
  .layout {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: var(--space-2);
  }
  .tree,
  .middle {
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
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .middle-tabs button.active {
    color: var(--accent);
    border-bottom: 2px solid var(--accent);
  }
  .badge {
    color: var(--text-muted);
    font-size: 0.85em;
  }
  .tree {
    overflow-y: auto;
  }
  @media (max-width: 1000px) {
    .code-tab {
      height: auto;
    }
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto;
    }
  }
</style>
