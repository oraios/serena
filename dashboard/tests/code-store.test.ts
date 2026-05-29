import { describe, it, expect } from 'vitest';
import { stubFetchRoutes } from './helpers';
import { createCodeStore } from '../src/lib/stores/code.svelte';

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
