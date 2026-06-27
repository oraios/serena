import {
  fetchCodeListDir,
  fetchCodeFileSymbols,
  fetchCodeWorkspaceSymbolSearch,
  fetchCodeDiagnosticsSummary,
} from '$lib/api/endpoints';
import type {
  DirEntry,
  FileSymbol,
  WorkspaceMatch,
  FileDiagnostics,
  DiagnosticSeverity,
} from '$lib/api/types';
import { SvelteSet } from 'svelte/reactivity';

export type DiagScope = { kind: 'project' | 'file' | 'directory'; path: string | null };

const EMPTY_SET: ReadonlySet<string> = new Set();

export function createCodeStore() {
  const dirChildren = $state<Record<string, DirEntry[]>>({});
  const dirErrors = $state<Record<string, string>>({});
  const expanded = new SvelteSet<string>();
  let selectedPath = $state<string | null>(null);
  const fileSymbols = $state<Record<string, FileSymbol[]>>({});
  const fileSymbolErrors = $state<Record<string, string>>({});
  let searchQuery = $state('');
  let searchResults = $state<WorkspaceMatch[]>([]);
  let searchLoading = $state(false);
  let searchError = $state<string | null>(null);
  let middlePane = $state<'symbols' | 'search' | 'diagnostics'>('symbols');
  let searchEpoch = 0;
  let diagEpoch = 0;
  let diagFiles = $state<FileDiagnostics[]>([]);
  let diagLoading = $state(false);
  let diagError = $state<string | null>(null);
  let diagTruncated = $state(false);
  let diagSkippedUnsupported = $state(0);
  let diagLastRefreshAt = $state<number | null>(null);
  let diagScope = $state<DiagScope>({ kind: 'project', path: null });
  let diagScopePinned = $state(false);
  let diagLastScope = $state<DiagScope | null>(null);
  const diagSeverityFilter = new SvelteSet<DiagnosticSeverity>();
  const symbolExpanded = $state<Record<string, SvelteSet<string>>>({});
  const symbolFilters = $state<Record<string, string>>({});

  function getOrCreateExpanded(path: string): SvelteSet<string> {
    let set = symbolExpanded[path];
    if (!set) {
      set = new SvelteSet<string>();
      symbolExpanded[path] = set;
    }
    return set;
  }

  // Expand only the depth-0 parents (classes/functions show their members,
  // nested members stay collapsed). Used as the on-load default.
  function expandTopLevelInto(path: string) {
    const set = getOrCreateExpanded(path);
    for (const s of fileSymbols[path] ?? []) {
      if (s.children && s.children.length > 0) set.add(`${s.name}:${s.range.start.line}`);
    }
  }

  return {
    get dir_children() {
      return dirChildren;
    },
    get dir_errors() {
      return dirErrors;
    },
    get expanded() {
      return expanded;
    },
    get selected_path() {
      return selectedPath;
    },
    get file_symbols() {
      return fileSymbols;
    },
    get file_symbol_errors() {
      return fileSymbolErrors;
    },
    get search_query() {
      return searchQuery;
    },
    get search_results() {
      return searchResults;
    },
    get search_loading() {
      return searchLoading;
    },
    get search_error() {
      return searchError;
    },
    get middle_pane() {
      return middlePane;
    },
    get diag_files() {
      return diagFiles;
    },
    get diag_loading() {
      return diagLoading;
    },
    get diag_error() {
      return diagError;
    },
    get diag_truncated() {
      return diagTruncated;
    },
    get diag_skipped_unsupported() {
      return diagSkippedUnsupported;
    },
    get diag_last_refresh_at() {
      return diagLastRefreshAt;
    },
    get diag_scope() {
      return diagScope;
    },
    get diag_scope_pinned() {
      return diagScopePinned;
    },
    get diag_last_scope() {
      return diagLastScope;
    },
    get diag_severity_filter() {
      return diagSeverityFilter;
    },
    get diag_counts() {
      const counts = { error: 0, warning: 0, info: 0, hint: 0 } as Record<string, number>;
      for (const f of diagFiles) {
        for (const d of f.diagnostics) counts[d.severity]++;
      }
      return counts;
    },
    setMiddlePane(pane: 'symbols' | 'search' | 'diagnostics') {
      middlePane = pane;
    },
    setDiagScope(scope: DiagScope) {
      diagScope = scope;
    },
    toggleDiagSeverity(sev: DiagnosticSeverity) {
      if (diagSeverityFilter.has(sev)) diagSeverityFilter.delete(sev);
      else diagSeverityFilter.add(sev);
    },
    isDiagSeverityShown(sev: DiagnosticSeverity): boolean {
      return diagSeverityFilter.size === 0 || diagSeverityFilter.has(sev);
    },
    _setDiagFilesForTest(files: FileDiagnostics[]) {
      diagFiles = files;
    },
    async loadDir(path: string, force = false) {
      if (!force && dirChildren[path]) return;
      delete dirErrors[path];
      try {
        const resp = await fetchCodeListDir(path);
        dirChildren[path] = resp.entries;
      } catch (e) {
        dirErrors[path] = e instanceof Error ? e.message : String(e);
      }
    },
    toggleExpand(path: string) {
      if (expanded.has(path)) expanded.delete(path);
      else {
        expanded.add(path);
        void this.loadDir(path);
      }
    },
    // Expand-only (never collapses) — used by breadcrumb navigation so a second
    // click on an already-open segment doesn't surprise the user by collapsing it.
    expandPath(path: string) {
      if (!expanded.has(path)) {
        expanded.add(path);
        void this.loadDir(path);
      }
    },
    selectPath(
      path: string | null,
      opts: { switchMiddleTo?: 'symbols' | 'search' | 'diagnostics' } = {},
    ) {
      // A genuine tree selection (or deselection) resumes selection-driven scope
      // following, releasing any pin set by an explicit per-row diagnostics action.
      diagScopePinned = false;
      selectedPath = path;
      if (opts.switchMiddleTo) middlePane = opts.switchMiddleTo;
      if (path) void this.loadFileSymbols(path);
    },
    async loadFileSymbols(path: string, force = false) {
      if (!force && fileSymbols[path]) return;
      delete fileSymbolErrors[path];
      try {
        const resp = await fetchCodeFileSymbols(path);
        fileSymbols[path] = resp.symbols;
        // Default view: top-level symbols expanded (matches the old flat list's
        // "you see the structure" feel without dumping every nested member).
        // Only on first load — don't clobber expand state the user has touched.
        if (symbolExpanded[path] === undefined) expandTopLevelInto(path);
      } catch (e) {
        fileSymbolErrors[path] = e instanceof Error ? e.message : String(e);
      }
    },
    getExpandedSymbols(path: string): ReadonlySet<string> {
      // Read-only: does NOT lazily create. Safe to call inside $derived.
      return symbolExpanded[path] ?? EMPTY_SET;
    },
    toggleSymbolExpand(path: string, key: string) {
      const set = getOrCreateExpanded(path);
      if (set.has(key)) set.delete(key);
      else set.add(key);
    },
    expandAllSymbols(path: string) {
      const set = getOrCreateExpanded(path);
      const symbols = fileSymbols[path] ?? [];
      const walk = (list: typeof symbols) => {
        for (const s of list) {
          if (s.children && s.children.length > 0) {
            set.add(`${s.name}:${s.range.start.line}`);
            walk(s.children);
          }
        }
      };
      walk(symbols);
    },
    expandTopLevelSymbols(path: string) {
      expandTopLevelInto(path);
    },
    collapseAllSymbols(path: string) {
      symbolExpanded[path] = new SvelteSet<string>();
    },
    getSymbolFilter(path: string): string {
      return symbolFilters[path] ?? '';
    },
    setSymbolFilter(path: string, q: string) {
      symbolFilters[path] = q;
    },
    async search(q: string) {
      searchQuery = q;
      if (q.trim().length < 2) {
        // Bump the epoch so any request still in flight from a prior keystroke
        // can't resolve and repopulate the results we're clearing here.
        ++searchEpoch;
        searchResults = [];
        searchLoading = false;
        searchError = null;
        return;
      }
      const myEpoch = ++searchEpoch;
      searchLoading = true;
      searchError = null;
      try {
        const resp = await fetchCodeWorkspaceSymbolSearch(q, 50);
        if (myEpoch === searchEpoch) {
          searchResults = resp.matches;
        }
      } catch (e) {
        if (myEpoch === searchEpoch) {
          searchError = e instanceof Error ? e.message : String(e);
          // Per spec §7.2: older successful results stay visible. Don't clear searchResults.
        }
      } finally {
        if (myEpoch === searchEpoch) searchLoading = false;
      }
    },
    async refreshDiagnostics(file_limit = 1000) {
      const scope = diagScope;
      // Guard against overlapping refreshes (e.g. two quick per-row runs, or a
      // selection-sync refresh racing a manual one): only the latest request is
      // allowed to write results, so a slow earlier call can't land its data
      // under a newer scope.
      const myEpoch = ++diagEpoch;
      diagLoading = true;
      diagError = null;
      try {
        const resp = await fetchCodeDiagnosticsSummary(
          file_limit,
          scope.kind === 'project' ? undefined : (scope.path ?? undefined),
        );
        if (myEpoch !== diagEpoch) return;
        diagFiles = resp.files;
        diagTruncated = resp.truncated;
        diagSkippedUnsupported = resp.skipped_unsupported ?? 0;
        diagLastRefreshAt = Date.now();
        diagLastScope = scope;
      } catch (e) {
        if (myEpoch === diagEpoch) diagError = e instanceof Error ? e.message : String(e);
        // Previous diagFiles stay visible per spec §7.2.
      } finally {
        if (myEpoch === diagEpoch) diagLoading = false;
      }
    },
    async runDiagnosticsForPath(path: string, kind: 'file' | 'directory') {
      diagScope = { kind, path };
      diagScopePinned = true;
      middlePane = 'diagnostics';
      await this.refreshDiagnostics();
    },
  };
}

export const code = createCodeStore();
