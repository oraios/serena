<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import Icon from '../common/Icon.svelte';
  import { RotateCw, TriangleAlert, CircleAlert, Info, Lightbulb } from '@lucide/svelte';
  import type { DiagnosticSeverity, FileDiagnostics } from '$lib/api/types';

  const counts = $derived(code.diag_counts);
  const selectedFile = $derived(code.selected_path);
  function parentDir(p: string): string {
    const i = p.lastIndexOf('/');
    return i <= 0 ? '.' : p.slice(0, i);
  }
  // A directory scope only makes sense for a real subdirectory. A top-level file
  // has parent '.', which the backend treats as a whole-project scan — so we
  // expose no directory target there (the Directory button stays disabled)
  // rather than silently running the project under a "directory" label.
  const selectedDir = $derived(
    selectedFile && parentDir(selectedFile) !== '.' ? parentDir(selectedFile) : null,
  );
  const scope = $derived(code.diag_scope);

  // Keep an active file/dir scope tracking the current tree selection so the
  // panel target follows what the user clicks in the file tree.
  $effect(() => {
    if (code.diag_scope_pinned) return;
    const sel = code.selected_path;
    const s = code.diag_scope;
    // When the selection is cleared (sel == null) we intentionally keep the
    // last file/dir scope path; the selector buttons become disabled instead.
    if (s.kind === 'file' && sel && sel !== s.path) {
      code.setDiagScope({ kind: 'file', path: sel });
    } else if (s.kind === 'directory' && sel) {
      const d = parentDir(sel);
      // Don't follow into '.' (project root) — keep the last real directory.
      if (d !== '.' && d !== s.path) code.setDiagScope({ kind: 'directory', path: d });
    }
  });

  function scopePathLabel(s: { kind: 'project' | 'file' | 'directory'; path: string | null }) {
    if (s.kind === 'project') return 'the project';
    return `${s.path ?? '.'}${s.kind === 'directory' ? '/' : ''}`;
  }
  const scopeLabel = $derived(
    scope.kind === 'project' ? 'Diagnostics' : `Diagnostics — ${scopePathLabel(scope)}`,
  );

  // The header/selector reflect the *target* scope (what Refresh will run); the
  // results below belong to the *last refreshed* scope. Flag the gap so the
  // header and body never silently disagree.
  function scopeKey(s: { kind: string; path: string | null } | null) {
    return s ? `${s.kind}:${s.path ?? ''}` : null;
  }
  const resultsStale = $derived(
    code.diag_last_scope != null &&
      !code.diag_loading &&
      scopeKey(scope) !== scopeKey(code.diag_last_scope),
  );

  function pickScope(kind: 'project' | 'file' | 'directory') {
    if (kind === 'project') code.setDiagScope({ kind: 'project', path: null });
    else if (kind === 'file' && selectedFile)
      code.setDiagScope({ kind: 'file', path: selectedFile });
    else if (kind === 'directory' && selectedDir)
      code.setDiagScope({ kind: 'directory', path: selectedDir });
  }
  const visibleFiles = $derived<FileDiagnostics[]>(
    code.diag_files
      .map((f) => ({
        ...f,
        diagnostics: f.diagnostics.filter((d) => code.isDiagSeverityShown(d.severity)),
      }))
      .filter((f) => f.diagnostics.length > 0),
  );

  function refresh() {
    if (code.diag_loading) return;
    void code.refreshDiagnostics(1000);
  }

  const SEVERITIES: {
    sev: DiagnosticSeverity;
    label: string;
    icon: typeof CircleAlert;
    color: string;
  }[] = [
    { sev: 'error', label: 'Errors', icon: CircleAlert, color: 'var(--log-error)' },
    { sev: 'warning', label: 'Warnings', icon: TriangleAlert, color: 'var(--log-warning)' },
    { sev: 'info', label: 'Info', icon: Info, color: 'var(--text-secondary)' },
    { sev: 'hint', label: 'Hints', icon: Lightbulb, color: 'var(--text-muted)' },
  ];
</script>

<section class="root">
  <header>
    <h3>{scopeLabel}</h3>
    <button type="button" class="refresh" onclick={refresh} disabled={code.diag_loading}>
      <span class="spin" class:on={code.diag_loading}>
        <Icon icon={RotateCw} size={14} />
      </span>
      <span>{code.diag_loading ? 'Computing…' : 'Refresh'}</span>
    </button>
  </header>

  <nav class="scope" aria-label="Diagnostics scope">
    <button
      type="button"
      class="scope-btn"
      class:active={scope.kind === 'project'}
      onclick={() => pickScope('project')}>Project</button
    >
    <button
      type="button"
      class="scope-btn"
      class:active={scope.kind === 'file'}
      disabled={!selectedFile && scope.kind !== 'file'}
      title={selectedFile
        ? `Diagnose ${selectedFile}`
        : scope.kind === 'file'
          ? `Diagnose ${scope.path ?? ''}`
          : 'Select a file first'}
      onclick={() => pickScope('file')}>File</button
    >
    <button
      type="button"
      class="scope-btn"
      class:active={scope.kind === 'directory'}
      disabled={!selectedDir && scope.kind !== 'directory'}
      title={selectedDir
        ? `Diagnose ${selectedDir}/`
        : scope.kind === 'directory'
          ? `Diagnose ${scope.path ?? '.'}/`
          : 'Select a file in a subdirectory first'}
      onclick={() => pickScope('directory')}>Directory</button
    >
  </nav>

  {#if resultsStale && code.diag_last_scope}
    <div class="stale" role="status">
      Showing results for {scopePathLabel(code.diag_last_scope)}. Click Refresh to update.
    </div>
  {/if}

  {#if scope.kind !== 'file'}
    <aside class="slow-warning" role="note">
      <Icon icon={TriangleAlert} size={14} label="Slow" />
      <span>
        Computing diagnostics is slow and temporarily delays other LSP tools. Use only when needed.
      </span>
    </aside>
  {/if}

  <nav class="chips" aria-label="Severity filter">
    {#each SEVERITIES as s (s.sev)}
      <button
        type="button"
        class="chip"
        class:active={code.diag_severity_filter.has(s.sev)}
        style:--chip-color={s.color}
        onclick={() => code.toggleDiagSeverity(s.sev)}
      >
        <Icon icon={s.icon} size={12} />
        <span>{s.label} ({counts[s.sev] ?? 0})</span>
      </button>
    {/each}
  </nav>

  {#if code.diag_error}
    <div class="error-card">
      <strong>Diagnostics failed.</strong>
      <div class="msg">{code.diag_error}</div>
    </div>
  {/if}

  {#if code.diag_truncated && !code.diag_loading}
    <div class="warn">
      Showing first {code.diag_files.length} files;
      {code.diag_last_scope?.kind === 'directory'
        ? 'directory'
        : code.diag_last_scope?.kind === 'file'
          ? 'this file'
          : 'project'} has more.
    </div>
  {/if}

  {#if code.diag_files.length === 0 && !code.diag_loading && !code.diag_error}
    {#if code.diag_last_scope}
      <p class="empty">
        No diagnostics in {code.diag_last_scope.kind === 'project'
          ? 'this project'
          : (code.diag_last_scope.path ?? 'this project')}.
      </p>
    {:else}
      <p class="empty">Click Refresh to compute diagnostics.</p>
    {/if}
  {/if}

  {#each visibleFiles as f (f.path)}
    <details class="file" open>
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
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
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
  .spin.on {
    animation: spin 1.2s linear infinite;
    display: inline-flex;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .slow-warning {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    background: var(--bg);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
    font-size: 0.85em;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px var(--space-2);
    color: var(--chip-color, var(--text-secondary));
    font-size: 0.8em;
    cursor: pointer;
  }
  .chip.active {
    background: color-mix(in srgb, var(--chip-color) 12%, transparent);
    border-color: var(--chip-color, var(--border));
  }
  .scope {
    display: flex;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .scope-btn {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    color: var(--text-secondary);
    font-size: 0.8em;
    cursor: pointer;
  }
  .scope-btn.active {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-color: var(--accent);
    color: var(--text-primary);
  }
  .scope-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .stale {
    background: color-mix(in srgb, var(--accent) 8%, transparent);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    margin-bottom: var(--space-2);
    color: var(--text-secondary);
    font-size: 0.85em;
  }
  .warn,
  .error-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-2);
    margin-bottom: var(--space-2);
  }
  .error-card {
    border-color: var(--log-error);
    color: var(--log-error);
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
