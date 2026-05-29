import { describe, it, expect } from 'vitest';
import { stubFetchRoutes } from './helpers';
import { createCodeStore } from '../src/lib/stores/code.svelte';
import type { DiagnosticSeverity, FileDiagnostics } from '../src/lib/api/types';

describe('code store', () => {
  it('caches list_dir results per path', async () => {
    const calls: string[] = [];
    stubFetchRoutes({
      '/code/list_dir': (url: string) => {
        calls.push(url);
        return { entries: [{ name: 'a', kind: 'file' }] };
      },
    });
    const store = createCodeStore();
    await store.loadDir('src');
    await store.loadDir('src'); // cached
    expect(calls.length).toBe(1);
  });

  it('caches file_symbols results per path', async () => {
    const calls: string[] = [];
    stubFetchRoutes({
      '/code/file_symbols': (url: string) => {
        calls.push(url);
        return { symbols: [] };
      },
    });
    const store = createCodeStore();
    await store.loadFileSymbols('a.py');
    await store.loadFileSymbols('a.py');
    expect(calls.length).toBe(1);
  });

  it('expandPath is add-only (never collapses an already-open dir)', () => {
    stubFetchRoutes({ '/code/list_dir': () => ({ entries: [] }) });
    const store = createCodeStore();
    store.expandPath('src');
    expect(store.expanded.has('src')).toBe(true);
    store.expandPath('src'); // second call must NOT toggle it closed
    expect(store.expanded.has('src')).toBe(true);
  });

  it('search uses epoch counter to discard stale responses', async () => {
    let resolveSlow: (v: unknown) => void = () => {};
    const slow = new Promise((res) => (resolveSlow = res));
    const queries: string[] = [];
    stubFetchRoutes({
      '/code/workspace_symbol_search': async (url: string) => {
        queries.push(url);
        if (url.includes('q=ab&')) {
          await slow;
          return {
            matches: [
              {
                name: 'OLD',
                kind: 'F',
                path: 'x.py',
                range: {
                  start: { line: 0, character: 0 },
                  end: { line: 0, character: 0 },
                },
              },
            ],
          };
        }
        return {
          matches: [
            {
              name: 'NEW',
              kind: 'F',
              path: 'y.py',
              range: {
                start: { line: 0, character: 0 },
                end: { line: 0, character: 0 },
              },
            },
          ],
        };
      },
    });
    const store = createCodeStore();
    const p1 = store.search('ab');
    const p2 = store.search('abc');
    await p2;
    resolveSlow(null);
    await p1;
    expect(store.search_results[0]?.name).toBe('NEW');
  });

  it('clearing the query (<2 chars) discards a still-in-flight response', async () => {
    let resolveSlow: (v: unknown) => void = () => {};
    const slow = new Promise((res) => (resolveSlow = res));
    stubFetchRoutes({
      '/code/workspace_symbol_search': async () => {
        await slow;
        return {
          matches: [
            {
              name: 'STALE',
              kind: 'F',
              path: 'x.py',
              range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } },
            },
          ],
        };
      },
    });
    const store = createCodeStore();
    const p1 = store.search('ab'); // fires a slow request
    await store.search('a'); // clears + must invalidate the in-flight request
    expect(store.search_results).toEqual([]);
    resolveSlow(null);
    await p1;
    // Pre-fix: the 'ab' response repopulated results under an empty query box.
    expect(store.search_results).toEqual([]);
  });

  it('search with <2 chars returns empty without firing a fetch', async () => {
    const calls: string[] = [];
    stubFetchRoutes({
      '/code/workspace_symbol_search': (url: string) => {
        calls.push(url);
        return { matches: [] };
      },
    });
    const store = createCodeStore();
    await store.search('a');
    expect(calls.length).toBe(0);
    expect(store.search_results).toEqual([]);
    expect(store.search_loading).toBe(false);
    // search_query is still updated for the input binding
    expect(store.search_query).toBe('a');
  });
});

describe('code store — symbol view state', () => {
  it('exposes per-path expand state via getExpandedSymbols', () => {
    const store = createCodeStore();
    const set = store.getExpandedSymbols('a.py');
    expect(set instanceof Set).toBe(true);
    expect(set.size).toBe(0);
  });

  it('toggleSymbolExpand flips a key on a given path', () => {
    const store = createCodeStore();
    store.toggleSymbolExpand('a.py', 'foo:1');
    expect(store.getExpandedSymbols('a.py').has('foo:1')).toBe(true);
    store.toggleSymbolExpand('a.py', 'foo:1');
    expect(store.getExpandedSymbols('a.py').has('foo:1')).toBe(false);
  });

  it('expandAllSymbols adds keys for every parent (with children) and collapseAllSymbols clears them', () => {
    const store = createCodeStore();
    const symbols = [
      {
        name: 'Alpha',
        kind: 'Class',
        range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } },
        children: [
          {
            name: 'foo',
            kind: 'Method',
            range: { start: { line: 1, character: 0 }, end: { line: 1, character: 0 } },
          },
        ],
      },
      {
        name: 'leaf',
        kind: 'Function',
        range: { start: { line: 2, character: 0 }, end: { line: 2, character: 0 } },
      },
    ];
    // seed cache directly via the public loader API
    store.file_symbols['a.py'] = symbols as never;
    store.expandAllSymbols('a.py');
    expect(store.getExpandedSymbols('a.py').has('Alpha:0')).toBe(true);
    expect(store.getExpandedSymbols('a.py').has('leaf:2')).toBe(false);
    store.collapseAllSymbols('a.py');
    expect(store.getExpandedSymbols('a.py').size).toBe(0);
  });

  it('symbol filter is per-path and defaults to ""', () => {
    const store = createCodeStore();
    expect(store.getSymbolFilter('a.py')).toBe('');
    store.setSymbolFilter('a.py', 'foo');
    expect(store.getSymbolFilter('a.py')).toBe('foo');
    expect(store.getSymbolFilter('b.py')).toBe('');
  });

  const nested = [
    {
      name: 'Alpha',
      kind: 'Class',
      range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } },
      children: [
        {
          name: 'foo',
          kind: 'Method',
          range: { start: { line: 1, character: 0 }, end: { line: 1, character: 0 } },
          children: [
            {
              name: 'v',
              kind: 'Variable',
              range: { start: { line: 2, character: 0 }, end: { line: 2, character: 0 } },
            },
          ],
        },
      ],
    },
    {
      name: 'leaf',
      kind: 'Function',
      range: { start: { line: 5, character: 0 }, end: { line: 5, character: 0 } },
    },
  ];

  it('expandTopLevelSymbols expands only depth-0 parents, not nested ones', () => {
    const store = createCodeStore();
    store.file_symbols['a.py'] = nested as never;
    store.expandTopLevelSymbols('a.py');
    const set = store.getExpandedSymbols('a.py');
    expect(set.has('Alpha:0')).toBe(true); // depth-0 parent
    expect(set.has('foo:1')).toBe(false); // nested parent stays collapsed
    expect(set.has('leaf:5')).toBe(false); // no children
  });

  it('loadFileSymbols auto-expands top level on first load (and leaves nested collapsed)', async () => {
    stubFetchRoutes({ '/code/file_symbols': () => ({ symbols: nested }) });
    const store = createCodeStore();
    await store.loadFileSymbols('a.py');
    const set = store.getExpandedSymbols('a.py');
    expect(set.has('Alpha:0')).toBe(true);
    expect(set.has('foo:1')).toBe(false);
  });

  it('loadFileSymbols does not clobber expand state the user already touched', async () => {
    stubFetchRoutes({ '/code/file_symbols': () => ({ symbols: nested }) });
    const store = createCodeStore();
    store.collapseAllSymbols('a.py'); // creates an (empty) expand set first
    await store.loadFileSymbols('a.py');
    // first-load auto-expand is skipped because the set already exists
    expect(store.getExpandedSymbols('a.py').has('Alpha:0')).toBe(false);
  });
});

describe('code store — diagnostics filter + counts', () => {
  it('middle_pane widens to support "diagnostics"', () => {
    const store = createCodeStore();
    store.setMiddlePane('diagnostics');
    expect(store.middle_pane).toBe('diagnostics');
  });

  it('diag_counts aggregates by severity across files', () => {
    const store = createCodeStore();
    const files: FileDiagnostics[] = [
      {
        path: 'a.py',
        diagnostics: [
          { severity: 'error', message: 'x', line: 0, column: 0 },
          { severity: 'warning', message: 'y', line: 0, column: 0 },
        ],
      },
      {
        path: 'b.py',
        diagnostics: [
          { severity: 'error', message: 'z', line: 0, column: 0 },
          { severity: 'info', message: 'i', line: 0, column: 0 },
        ],
      },
    ];
    store._setDiagFilesForTest(files);
    expect(store.diag_counts).toEqual({ error: 2, warning: 1, info: 1, hint: 0 });
  });

  it('toggleDiagSeverity flips a severity in the filter set', () => {
    const store = createCodeStore();
    expect(store.diag_severity_filter.has('error')).toBe(false);
    store.toggleDiagSeverity('error');
    expect(store.diag_severity_filter.has('error')).toBe(true);
    store.toggleDiagSeverity('error');
    expect(store.diag_severity_filter.has('error')).toBe(false);
  });

  it('isDiagSeverityShown returns true when filter set is empty (show-all default)', () => {
    const store = createCodeStore();
    const all: DiagnosticSeverity[] = ['error', 'warning', 'info', 'hint'];
    for (const sev of all) {
      expect(store.isDiagSeverityShown(sev)).toBe(true);
    }
    store.toggleDiagSeverity('error');
    expect(store.isDiagSeverityShown('error')).toBe(true);
    expect(store.isDiagSeverityShown('warning')).toBe(false);
  });
});

describe('code store — diagnostics scope', () => {
  it('refreshDiagnostics omits path for project scope', async () => {
    const urls: string[] = [];
    stubFetchRoutes({
      '/code/diagnostics_summary': (url: string) => {
        urls.push(url);
        return { files: [], truncated: false };
      },
    });
    const store = createCodeStore();
    await store.refreshDiagnostics(1000);
    expect(urls[0]).not.toContain('path=');
    expect(store.diag_last_scope?.kind).toBe('project');
  });

  it('refreshDiagnostics sends path for a file scope', async () => {
    const urls: string[] = [];
    stubFetchRoutes({
      '/code/diagnostics_summary': (url: string) => {
        urls.push(url);
        return { files: [], truncated: false };
      },
    });
    const store = createCodeStore();
    store.setDiagScope({ kind: 'file', path: 'src/a.py' });
    await store.refreshDiagnostics(1000);
    expect(urls[0]).toContain('path=src%2Fa.py');
    expect(store.diag_last_scope?.kind).toBe('file');
  });

  it('runDiagnosticsForPath sets scope, switches to the diagnostics pane, and fetches', async () => {
    const urls: string[] = [];
    stubFetchRoutes({
      '/code/diagnostics_summary': (url: string) => {
        urls.push(url);
        return { files: [], truncated: false };
      },
    });
    const store = createCodeStore();
    await store.runDiagnosticsForPath('src', 'directory');
    expect(store.middle_pane).toBe('diagnostics');
    expect(store.diag_scope).toEqual({ kind: 'directory', path: 'src' });
    expect(urls[0]).toContain('path=src');
  });
});
