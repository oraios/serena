import {
  fetchCodeListDir,
  fetchCodeFileSymbols,
  fetchCodeWorkspaceSymbolSearch,
  fetchCodeDiagnosticsSummary,
} from '$lib/api/endpoints';
import type { DirEntry, FileSymbol, WorkspaceMatch, FileDiagnostics } from '$lib/api/types';
import { SvelteSet } from 'svelte/reactivity';

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
  let middlePane = $state<'symbols' | 'search'>('symbols');
  let searchEpoch = 0;
  let diagFiles = $state<FileDiagnostics[]>([]);
  let diagLoading = $state(false);
  let diagError = $state<string | null>(null);
  let diagTruncated = $state(false);
  let diagLastRefreshAt = $state<number | null>(null);

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
    get diag_last_refresh_at() {
      return diagLastRefreshAt;
    },
    setMiddlePane(pane: 'symbols' | 'search') {
      middlePane = pane;
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
    selectPath(path: string | null, opts: { switchMiddleTo?: 'symbols' | 'search' } = {}) {
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
      } catch (e) {
        fileSymbolErrors[path] = e instanceof Error ? e.message : String(e);
      }
    },
    async search(q: string) {
      searchQuery = q;
      if (q.trim().length < 2) {
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
      diagLoading = true;
      diagError = null;
      try {
        const resp = await fetchCodeDiagnosticsSummary(file_limit);
        diagFiles = resp.files;
        diagTruncated = resp.truncated;
        diagLastRefreshAt = Date.now();
      } catch (e) {
        diagError = e instanceof Error ? e.message : String(e);
        // Previous diagFiles stay visible per spec §7.2.
      } finally {
        diagLoading = false;
      }
    },
  };
}

export const code = createCodeStore();
