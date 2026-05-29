<script lang="ts">
  import { code } from '$lib/stores/code.svelte';

  function refresh() {
    if (code.diag_loading) return;
    void code.refreshDiagnostics(1000);
  }
</script>

<section class="root">
  <header>
    <h3>Diagnostics</h3>
    <button type="button" class="refresh" onclick={refresh} disabled={code.diag_loading}>
      {code.diag_loading ? 'Computing…' : '↻ Refresh'}
    </button>
  </header>

  {#if code.diag_loading}
    <div class="warn">
      ⚠ Computing diagnostics — this can take a while and temporarily slows other LSP-backed tools.
    </div>
  {/if}

  {#if code.diag_error}
    <div class="error-card">
      <strong>Diagnostics failed.</strong>
      <div class="msg">{code.diag_error}</div>
    </div>
  {/if}

  {#if code.diag_truncated && !code.diag_loading}
    <div class="warn">
      Showing first {code.diag_files.length} files; project has more.
    </div>
  {/if}

  {#if code.diag_files.length === 0 && !code.diag_loading && !code.diag_error}
    <p class="empty">
      Click Refresh to compute diagnostics. (Results are not auto-refreshed because diagnostics is
      slow.)
    </p>
  {/if}

  {#each code.diag_files as f (f.path)}
    <details class="file">
      <summary>
        <span class="path">{f.path}</span>
        <span class="count">{f.diagnostics.length}</span>
      </summary>
      <ul class="diags">
        {#each f.diagnostics as d, i (i)}
          <li class={`sev-${d.severity}`}>
            <span class="loc">{d.line + 1}:{d.column + 1}</span>
            <span class="sev">{d.severity}</span>
            <span class="msg">{d.message}</span>
            {#if d.source}<span class="source">[{d.source}]</span>{/if}
          </li>
        {/each}
      </ul>
    </details>
  {/each}
</section>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
    padding: var(--space-2);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  header h3 {
    margin: 0;
    font-size: 1em;
  }
  .refresh {
    margin-left: auto;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
    color: var(--text-primary);
  }
  .refresh:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .warn {
    background: var(--bg);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
  }
  .error-card {
    background: var(--bg);
    border: 1px solid var(--log-error);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--log-error);
    margin-bottom: var(--space-2);
  }
  .error-card .msg {
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-2);
  }
  .file {
    border-bottom: 1px solid var(--border);
    padding: var(--space-1) 0;
  }
  .file summary {
    display: flex;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.9em;
  }
  .file summary .count {
    margin-left: auto;
    color: var(--text-secondary);
  }
  .diags {
    list-style: none;
    margin: var(--space-1) 0 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .diags li {
    display: grid;
    grid-template-columns: 70px 60px 1fr auto;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
  }
  .sev-error {
    color: var(--log-error);
  }
  .sev-warning {
    color: var(--log-warning);
  }
  .sev-info,
  .sev-hint {
    color: var(--text-secondary);
  }
  .source {
    color: var(--text-secondary);
  }
</style>
