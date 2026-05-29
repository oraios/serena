# Dashboard Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all 15 dashboard code-review findings (bugs, style-rule violations, duplication, accessibility, one chart-lifecycle design improvement) and streamline the Vitest suite.

**Architecture:** The dashboard is a Svelte 5 (runes) app in `dashboard/`, compiled into `src/serena/resources/dashboard/assets/`. Work proceeds in 6 phases ordered low-risk-first: pure-logic and tests/-only changes land before any component change; a single `npm run build` + manual visual/console verification happens last. Each phase ends green on `npm test`.

**Tech Stack:** Svelte 5 runes, TypeScript, Vite 6, Vitest 2, `@testing-library/svelte`, frappe-charts, ESLint 9 + Prettier.

**Working directory for all commands:** `dashboard/` (i.e. `/home/paul/PycharmProjects/3rd_party/serena/dashboard`). All `npm` commands run there.

**Conventions:**
- TDD: write the failing test, see it fail, implement, see it pass, commit.
- Never hardcode hex in a component — use tokens from `src/styles/tokens.css`.
- Do NOT touch `src/serena/dashboard.py` or any endpoint/shape (frozen contract).
- The committed bundle under `src/serena/resources/dashboard/assets/` is rebuilt ONCE in Phase 6, not per task.
- Commit messages follow the repo's `feat(dashboard):` / `fix(dashboard):` / `refactor(dashboard):` / `test(dashboard):` style.

---

## Phase 1 — Pure-logic fixes (`format.ts`)

### Task 1: Single-pass `highlightTools` + escape single quote

**Files:**
- Modify: `dashboard/src/lib/format.ts:14-34`
- Modify: `dashboard/tests/format.test.ts`

- [ ] **Step 1: Add failing tests for the re-match bug and `'` escaping, and drop the duplicate case**

Replace the body of `dashboard/tests/format.test.ts` with:

```ts
import { describe, it, expect } from 'vitest';
import { detectLevel, escapeHtml, highlightTools } from '../src/lib/format';

describe('format', () => {
  it('detects log level from the line prefix', () => {
    expect(detectLevel('INFO  2026-01-01 something')).toBe('info');
    expect(detectLevel('WARNING 2026-01-01 watch out')).toBe('warning');
    expect(detectLevel('ERROR 2026-01-01 boom')).toBe('error');
    expect(detectLevel('DEBUG 2026-01-01 noise')).toBe('debug');
    expect(detectLevel('no level here')).toBe('info');
  });
  it('does not recolor a line just because a level word appears mid-message', () => {
    expect(detectLevel('INFO  handled an ERROR gracefully')).toBe('info');
  });
  it('highlights tool names case-insensitively', () => {
    const html = highlightTools('called Find_Symbol now', ['find_symbol']);
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
  });
  it('escapes html including single quotes', () => {
    expect(escapeHtml(`<b>&"'`)).toBe('&lt;b&gt;&amp;&quot;&#39;');
  });
  it('escapes HTML in the log text before highlighting', () => {
    const html = highlightTools('<script>alert(1)</script> find_symbol', ['find_symbol']);
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
  });
  it('does not re-match injected markup when a tool is named like a wrapper token', () => {
    // A tool literally named "name"/"span"/"class"/"tool" must not match inside the
    // injected <span class="tool-name"> wrapper of an earlier replacement.
    const html = highlightTools('use find_symbol and name', ['find_symbol', 'name']);
    // Exactly two wrappers, no nested span inside the class attribute.
    expect(html.match(/<span class="tool-name">/g)?.length).toBe(2);
    expect(html).not.toContain('class="tool-<span');
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
    expect(html).toContain('<span class="tool-name">name</span>');
  });
  it('highlights each occurrence of overlapping names in one pass', () => {
    const html = highlightTools('find_symbol find_symbol', ['find_symbol']);
    expect(html.match(/<span class="tool-name">find_symbol<\/span>/g)?.length).toBe(2);
  });
});
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `npm test -- format`
Expected: FAIL — `escapes html including single quotes` (no `&#39;`) and `does not re-match injected markup` (nested span / wrong count).

- [ ] **Step 3: Rewrite `format.ts` to escape `'` and do a single-pass highlight**

Replace `dashboard/src/lib/format.ts` lines 14-34 (the `escapeHtml`, `escapeRegExp`, and `highlightTools` functions) with:

```ts
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Highlight tool names in ONE pass over the escaped text. Building a single combined
// alternation and replacing once means injected <span> markup is never re-scanned, so a
// tool literally named "name"/"span"/"class" can't nest a span into a previous wrapper.
export function highlightTools(text: string, toolNames: string[]): string {
  const escaped = escapeHtml(text);
  if (toolNames.length === 0) return escaped;
  // Longest-first so a longer name wins over a shorter name that is its prefix.
  const sorted = [...toolNames].sort((a, b) => b.length - a.length);
  const re = new RegExp(`\\b(?:${sorted.map(escapeRegExp).join('|')})\\b`, 'gi');
  return escaped.replace(re, (match) => `<span class="tool-name">${escapeHtml(match)}</span>`);
}
```

Note: `detectLevel` (lines 1-12) is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- format`
Expected: PASS (all 6 `format` tests).

- [ ] **Step 5: Run the full suite to confirm no regression in the log viewer test**

Run: `npm test -- log-viewer format`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/format.ts dashboard/tests/format.test.ts
git commit -m "fix(dashboard): single-pass highlightTools; escape single quote in escapeHtml"
```

---

## Phase 2 — Test-suite streamlining (tests/ only)

### Task 2: Create `tests/helpers.ts`

**Files:**
- Create: `dashboard/tests/helpers.ts`

- [ ] **Step 1: Write the helpers**

Create `dashboard/tests/helpers.ts`:

```ts
import { vi } from 'vitest';
import type { QueuedExecution } from '../src/lib/api/types';

/** Stub global fetch to always resolve with one JSON body (HTTP 200 unless overridden). */
export function stubFetchJson(body: unknown, status = 200) {
  const fn = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** Stub fetch with substring URL routing; first matching fragment wins, else `fallback`. */
export function stubFetchRoutes(routes: Record<string, unknown>, fallback: unknown = {}) {
  const fn = vi.fn((url: string) => {
    const hit = Object.entries(routes).find(([frag]) => String(url).includes(frag));
    return Promise.resolve(new Response(JSON.stringify(hit ? hit[1] : fallback), { status: 200 }));
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

/** The backend's soft-failure channel: HTTP 200 with `{status:'error', message}`. */
export const errBody = (message: string) => ({ status: 'error', message });
/** A success mutation body, optionally with extra fields (e.g. was_cancelled). */
export const okBody = (extra: object = {}) => ({ status: 'success', ...extra });

/** Build a QueuedExecution fixture with sensible defaults. */
export function exec(over: Partial<QueuedExecution> = {}): QueuedExecution {
  return {
    task_id: 1,
    is_running: false,
    name: 'task',
    finished_successfully: true,
    logged: true,
    ...over,
  };
}
```

- [ ] **Step 2: Type-check the helper**

Run: `npm run check`
Expected: 0 errors (the 4 pre-existing `state_referenced_locally` warnings may still appear; they are removed in later phases).

- [ ] **Step 3: Commit**

```bash
git add dashboard/tests/helpers.ts
git commit -m "test(dashboard): add shared test helpers (fetch stubs + exec fixture)"
```

### Task 3: Global `afterEach(vi.restoreAllMocks)` in setup.ts

**Files:**
- Modify: `dashboard/tests/setup.ts:1`

- [ ] **Step 1: Add the global afterEach**

In `dashboard/tests/setup.ts`, change the first line from:

```ts
import '@testing-library/jest-dom/vitest';
```

to:

```ts
import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';

// Restore stubs/spies after every test so individual files don't each repeat this.
afterEach(() => vi.restoreAllMocks());
```

- [ ] **Step 2: Run the full suite (it must still pass with the global hook present)**

Run: `npm test`
Expected: PASS (59 tests; the per-file restore calls are still present and harmless).

- [ ] **Step 3: Commit**

```bash
git add dashboard/tests/setup.ts
git commit -m "test(dashboard): restore mocks globally in setup.ts"
```

### Task 4: Drop the trivial smoke test

**Files:**
- Delete: `dashboard/tests/smoke.test.ts`

- [ ] **Step 1: Delete the file**

```bash
git rm dashboard/tests/smoke.test.ts
```

- [ ] **Step 2: Run the suite**

Run: `npm test`
Expected: PASS, one fewer test file.

- [ ] **Step 3: Commit**

```bash
git commit -m "test(dashboard): drop trivial smoke test"
```

### Task 5: Merge `executions.test.ts` into `executions-queue.test.ts`

Both files test `ExecutionsQueue`. Consolidate into one file using the shared `exec()`.

**Files:**
- Modify: `dashboard/tests/executions-queue.test.ts`
- Delete: `dashboard/tests/executions.test.ts`

- [ ] **Step 1: Replace `executions-queue.test.ts` with the merged version**

Overwrite `dashboard/tests/executions-queue.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen, getAllByRole } from '@testing-library/svelte';
import ExecutionsQueue from '../src/components/overview/ExecutionsQueue.svelte';
import { exec } from './helpers';

describe('ExecutionsQueue', () => {
  it('renders a cancel button for a queued (non-running) item and emits the execution', async () => {
    const item = exec({ task_id: 9, is_running: false, name: 'queued-task' });
    const oncancelexecution = vi.fn();
    render(ExecutionsQueue, { props: { items: [item], cancelError: '', oncancelexecution } });
    await fireEvent.click(screen.getByTestId('cancel-btn'));
    expect(oncancelexecution).toHaveBeenCalledWith(item);
  });

  it('shows a cancel button for every logged item', () => {
    const { container } = render(ExecutionsQueue, {
      props: {
        items: [exec({ task_id: 1, is_running: true, name: 'run' }), exec({ task_id: 2, name: 'queued' })],
        oncancelexecution: vi.fn(),
      },
    });
    expect(getAllByRole(container, 'button').length).toBe(2);
  });

  it('hides unlogged background tasks', () => {
    const { container, queryByText } = render(ExecutionsQueue, {
      props: {
        items: [
          exec({ task_id: 1, is_running: true, name: 'logged-task' }),
          exec({ task_id: 2, name: '_get_config_overview', logged: false }),
        ],
        oncancelexecution: vi.fn(),
      },
    });
    expect(container.querySelectorAll('.execution-item').length).toBe(1);
    expect(queryByText('_get_config_overview')).toBeNull();
  });

  it('shows the cancel error when set', () => {
    render(ExecutionsQueue, {
      props: { items: [exec({})], cancelError: 'too late', oncancelexecution: vi.fn() },
    });
    expect(screen.getByText('too late')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Delete the now-redundant file**

```bash
git rm dashboard/tests/executions.test.ts
```

- [ ] **Step 3: Run the suite**

Run: `npm test -- executions-queue`
Expected: PASS (4 tests).

- [ ] **Step 4: Commit**

```bash
git add dashboard/tests/executions-queue.test.ts
git commit -m "test(dashboard): merge executions component tests into one file"
```

### Task 6: Migrate fetch-stub files to the shared helpers

Mechanical migration. For each file: remove the per-file `beforeEach/afterEach(() => vi.restoreAllMocks())` (now global), import from `./helpers`, and replace the inline `vi.stubGlobal('fetch', …)` blocks with `stubFetchJson` / `stubFetchRoutes` / `errBody` / `okBody`. Adjust the `vitest` import to drop now-unused names (`beforeEach`/`afterEach`).

- [ ] **Step 1: `tests/client.test.ts`** — keep the `postJson` test's hand-rolled mock (it asserts on the mock fn). Replace only the other two stubs and drop the `beforeEach`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { getJson, postJson, ApiError } from '../src/lib/api/client';
import { stubFetchJson } from './helpers';

describe('client', () => {
  it('getJson parses JSON on success', async () => {
    stubFetchJson({ a: 1 });
    expect(await getJson<{ a: number }>('/x')).toEqual({ a: 1 });
  });

  it('postJson sends a JSON body', async () => {
    const f = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    await postJson('/y', { name: 'go' });
    expect(f).toHaveBeenCalledWith(
      '/y',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'go' }),
      }),
    );
  });

  it('throws ApiError on non-2xx', async () => {
    stubFetchJson('nope', 500);
    await expect(getJson('/z')).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: `tests/endpoints.test.ts`** — keep its own `fetchMock` (it asserts call args), but drop the now-redundant nothing; this file already uses a shared `fetchMock` and `beforeEach`. Leave the `beforeEach` that builds `fetchMock` (it is not a `restoreAllMocks` call — it constructs the spy). No change required. Verify by reading: if the only `beforeEach` builds `fetchMock`, skip this file.

- [ ] **Step 3: `tests/logs-store.test.ts`** — drop `beforeEach`, keep the sequential mock (routes by call index, not URL), so no helper fits cleanly; just remove the `beforeEach(() => vi.restoreAllMocks())` line and the `beforeEach` import:

```ts
import { describe, it, expect, vi } from 'vitest';
import { createLogsStore } from '../src/lib/stores/logs.svelte';

describe('logs store', () => {
  it('appends only new messages by tracking max_idx', async () => {
    const responses = [
      { messages: ['a', 'b'], max_idx: 2, active_project: 'p' },
      { messages: ['c'], max_idx: 3, active_project: 'p' },
    ];
    let call = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(responses[call++]), { status: 200 }))),
    );
    const store = createLogsStore();
    await store.poll();
    expect(store.lines).toEqual(['a', 'b']);
    await store.poll();
    expect(store.lines).toEqual(['a', 'b', 'c']);
  });
});
```

- [ ] **Step 4: `tests/executions-store.test.ts`** — drop `beforeEach` + its own `exec()`; import `exec`, `okBody`, `errBody`, `stubFetchJson` from `./helpers`. Replace the four stubs:
  - success body → `stubFetchJson(okBody({ was_cancelled: true, message: '' }))`
  - error body → `stubFetchJson(errBody('too late'))`
  - last-execution bodies → `stubFetchJson({ last_execution: <last|null>, status: 'success' })`

New top of file:

```ts
import { describe, it, expect } from 'vitest';
import { createExecutionsStore } from '../src/lib/stores/executions.svelte';
import { exec, okBody, errBody, stubFetchJson } from './helpers';
```

Then in each test replace the `vi.stubGlobal('fetch', …)` block with the matching one-liner above, and delete the local `exec()` definition and the `beforeEach`. Keep all assertions unchanged.

- [ ] **Step 5: `tests/add-language-modal.test.ts`** — replace `mockFetch()` with `stubFetchRoutes`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import AddLanguageModal from '../src/components/modals/AddLanguageModal.svelte';
import { stubFetchRoutes, errBody } from './helpers';

describe('AddLanguageModal error handling', () => {
  it('shows the error inline and stays open when add fails', async () => {
    stubFetchRoutes({ '/get_available_languages': { languages: ['go'] } }, errBody('unknown language'));
    const onclose = vi.fn();
    render(AddLanguageModal, { props: { projectName: 'serena', onclose } });
    const input = screen.getByRole('textbox');
    await fireEvent.focus(input);
    await fireEvent.click(await screen.findByText('go'));
    await fireEvent.click(screen.getByRole('button', { name: 'Add Language' }));
    expect(await screen.findByText('unknown language')).toBeInTheDocument();
    expect(onclose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 6: `tests/delete-memory-modal.test.ts`** — replace the inline stub:

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import DeleteMemoryModal from '../src/components/modals/DeleteMemoryModal.svelte';
import { stubFetchJson, errBody } from './helpers';

describe('DeleteMemoryModal error handling', () => {
  it('shows the error and stays open when delete fails', async () => {
    stubFetchJson(errBody('cannot delete'));
    const onclose = vi.fn();
    render(DeleteMemoryModal, { props: { name: 'core', onclose } });
    await fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(await screen.findByText('cannot delete')).toBeInTheDocument();
    expect(onclose).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 7: `tests/edit-memory-modal.test.ts` and `tests/edit-serena-config-modal.test.ts`** — drop the `afterEach`, switch the load stub to `stubFetchJson`:
  - edit-memory: `stubFetchJson({ content: 'orig', memory_name: 'core' })`
  - edit-serena-config: `stubFetchJson({ content: 'yaml: 1' })`
  Update the `vitest` import to `{ describe, it, expect, vi }` and import `stubFetchJson` from `./helpers`. Keep the `waitFor` blocks and assertions unchanged.

- [ ] **Step 8: Run the full suite**

Run: `npm test`
Expected: PASS, fewer lines, no new failures.

- [ ] **Step 9: Commit**

```bash
git add dashboard/tests/
git commit -m "test(dashboard): migrate fetch stubs to shared helpers"
```

### Task 7: New coverage — config store

**Files:**
- Create: `dashboard/tests/config-store.test.ts`

- [ ] **Step 1: Write the test**

```ts
import { describe, it, expect } from 'vitest';
import { createConfigStore } from '../src/lib/stores/config.svelte';
import { stubFetchJson } from './helpers';

const overview = { serena_version: '1.0', active_project: null, languages: [] };

describe('config store', () => {
  it('keeps the same reference when the polled body is unchanged', async () => {
    stubFetchJson(overview);
    const store = createConfigStore();
    await store.poll();
    const first = store.data;
    await store.poll();
    expect(store.data).toBe(first); // dedup via JSON compare → no reassignment
  });

  it('updates data when the polled body changes', async () => {
    const fetchMock = stubFetchJson(overview);
    const store = createConfigStore();
    await store.poll();
    const first = store.data;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ ...overview, serena_version: '2.0' }), { status: 200 }),
    );
    await store.poll();
    expect(store.data).not.toBe(first);
    expect(store.data?.serena_version).toBe('2.0');
  });
});
```

- [ ] **Step 2: Run it**

Run: `npm test -- config-store`
Expected: PASS (the `createConfigStore` dedup logic already exists at `src/lib/stores/config.svelte.ts:12-19`).

- [ ] **Step 3: Commit**

```bash
git add dashboard/tests/config-store.test.ts
git commit -m "test(dashboard): cover config store poll dedup"
```

### Task 8: New coverage — stats store + client.putJson

**Files:**
- Create: `dashboard/tests/stats-store.test.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write the stats-store test**

```ts
import { describe, it, expect } from 'vitest';
import { createStatsStore } from '../src/lib/stores/stats.svelte';
import { stubFetchRoutes } from './helpers';

describe('stats store', () => {
  it('refresh loads stats and the estimator name', async () => {
    stubFetchRoutes({
      '/get_tool_stats': { stats: { find_symbol: { num_times_called: 3, input_tokens: 1, output_tokens: 2 } } },
      '/get_token_count_estimator_name': { token_count_estimator_name: 'tiktoken' },
    });
    const store = createStatsStore();
    await store.refresh();
    expect(store.stats.find_symbol.num_times_called).toBe(3);
    expect(store.estimator).toBe('tiktoken');
  });

  it('clear resets stats to empty', async () => {
    stubFetchRoutes({ '/clear_tool_stats': { status: 'success' } });
    const store = createStatsStore();
    await store.clear();
    expect(store.stats).toEqual({});
  });
});
```

- [ ] **Step 2: Add a putJson test to client.test.ts**

Append inside the `describe('client', …)` block in `dashboard/tests/client.test.ts`:

```ts
  it('putJson issues a PUT', async () => {
    const f = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    const { putJson } = await import('../src/lib/api/client');
    await putJson('/shutdown');
    expect(f).toHaveBeenCalledWith('/shutdown', expect.objectContaining({ method: 'PUT' }));
  });
```

Also add `putJson` to the static import at the top: `import { getJson, postJson, putJson, ApiError } from '../src/lib/api/client';` and drop the dynamic `await import` in favor of the direct `putJson` reference:

```ts
  it('putJson issues a PUT', async () => {
    const f = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    await putJson('/shutdown');
    expect(f).toHaveBeenCalledWith('/shutdown', expect.objectContaining({ method: 'PUT' }));
  });
```

- [ ] **Step 3: Run both**

Run: `npm test -- stats-store client`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add dashboard/tests/stats-store.test.ts dashboard/tests/client.test.ts
git commit -m "test(dashboard): cover stats store and client.putJson"
```

### Task 9: Extract `pollersForView` from App.svelte + test

**Files:**
- Create: `dashboard/src/lib/pollers.ts`
- Create: `dashboard/tests/pollers.test.ts`
- Modify: `dashboard/src/App.svelte:17,33-46`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/pollers.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { pollersForView } from '../src/lib/pollers';

describe('pollersForView', () => {
  it('overview polls config, queued, and last', () => {
    expect(pollersForView('overview')).toEqual(['config', 'queued', 'last']);
  });
  it('logs polls only logs', () => {
    expect(pollersForView('logs')).toEqual(['logs']);
  });
  it('stats polls nothing', () => {
    expect(pollersForView('stats')).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- pollers`
Expected: FAIL — cannot resolve `../src/lib/pollers`.

- [ ] **Step 3: Create the module**

Create `dashboard/src/lib/pollers.ts`:

```ts
export type View = 'overview' | 'logs' | 'stats';
export type PollerName = 'config' | 'queued' | 'last' | 'logs';

/** Which pollers should be running for a given view. Pure so it is unit-testable. */
export function pollersForView(view: View): PollerName[] {
  switch (view) {
    case 'overview':
      return ['config', 'queued', 'last'];
    case 'logs':
      return ['logs'];
    case 'stats':
      return [];
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- pollers`
Expected: PASS.

- [ ] **Step 5: Wire App.svelte to use it**

In `dashboard/src/App.svelte`:

Replace the local `type View` declaration (line 17) and add the import. After the existing imports, add:

```ts
  import { pollersForView, type View, type PollerName } from '$lib/pollers';
  import type { Poller } from '$lib/polling';
```

Delete the line `type View = 'overview' | 'logs' | 'stats';` (now imported).

Replace `startPollers` (lines 33-46) with:

```ts
  const pollers: Record<PollerName, Poller> = {
    config: configPoller,
    queued: queuedPoller,
    last: lastPoller,
    logs: logsPoller,
  };

  function startPollers(v: View) {
    for (const p of Object.values(pollers)) p.stop();
    for (const name of pollersForView(v)) pollers[name].start();
  }
```

- [ ] **Step 6: Type-check and run the suite**

Run: `npm run check && npm test`
Expected: 0 type errors related to App/pollers; all tests pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/pollers.ts dashboard/tests/pollers.test.ts dashboard/src/App.svelte
git commit -m "refactor(dashboard): extract testable pollersForView; cover it"
```

### Task 10: New coverage — CreateMemoryModal (validation + mutation error)

**Files:**
- Create: `dashboard/tests/create-memory-modal.test.ts`

- [ ] **Step 1: Write the test**

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, screen } from '@testing-library/svelte';
import CreateMemoryModal from '../src/components/modals/CreateMemoryModal.svelte';
import { stubFetchJson, errBody } from './helpers';

describe('CreateMemoryModal', () => {
  it('disables Create until the name is valid', async () => {
    stubFetchJson(errBody('nope'));
    render(CreateMemoryModal, { props: { projectName: 'serena', onclose: vi.fn(), oncreated: vi.fn() } });
    const create = screen.getByRole('button', { name: 'Create' });
    expect(create).toBeDisabled();
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'valid_name' } });
    expect(create).not.toBeDisabled();
  });

  it('shows the error inline and does not signal creation when save fails', async () => {
    stubFetchJson(errBody('already exists'));
    const oncreated = vi.fn();
    render(CreateMemoryModal, { props: { projectName: 'serena', onclose: vi.fn(), oncreated } });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'dup' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('already exists')).toBeInTheDocument();
    expect(oncreated).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run it**

Run: `npm test -- create-memory-modal`
Expected: PASS against the current `CreateMemoryModal` (it will still pass after the Phase 4 refactor — the refactor preserves the `Create` label, `disabled` gating, and inline error).

- [ ] **Step 3: Commit**

```bash
git add dashboard/tests/create-memory-modal.test.ts
git commit -m "test(dashboard): cover CreateMemoryModal validation and error"
```

---

## Phase 3 — Token / style-violation fixes

### Task 11: Replace hardcoded `#fff` with `var(--text-on-accent)`

**Files:**
- Modify: `dashboard/src/components/common/Button.svelte:29,43`
- Modify: `dashboard/src/components/overview/ListPanel.svelte:49`

- [ ] **Step 1: Button.svelte**

In `dashboard/src/components/common/Button.svelte`, change `.primary` `color: #fff;` (line 29) and `.danger` `color: #fff;` (line 43) both to `color: var(--text-on-accent);`.

- [ ] **Step 2: ListPanel.svelte**

In `dashboard/src/components/overview/ListPanel.svelte`, change `.list-panel li.active` `color: #fff;` (line 49) to `color: var(--text-on-accent);` (matches `ProjectsPanel.svelte:49`).

- [ ] **Step 3: Verify no remaining hardcoded white in components**

Run: `grep -rn "#fff" dashboard/src/components dashboard/src/styles`
Expected: matches only in `tokens.css` (`--text-on-accent: #ffffff` and other token definitions), none in component `<style>` blocks. (Chart series hex in `ChartPanel.svelte:63` is handled in Task 12.)

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/common/Button.svelte dashboard/src/components/overview/ListPanel.svelte
git commit -m "style(dashboard): use --text-on-accent token instead of hardcoded #fff"
```

### Task 12: Chart series color tokens; ChartPanel reads them

**Files:**
- Modify: `dashboard/src/styles/tokens.css`
- Modify: `dashboard/src/components/stats/ChartPanel.svelte:47-63`

- [ ] **Step 1: Add chart tokens to tokens.css**

In `dashboard/src/styles/tokens.css`, inside `:root` (after `--accent-hover: #dca662;`, line 12), add:

```css
  --chart-2: #6aa3d8;
  --chart-3: #7fb77e;
  --chart-4: #d88c8c;
  --chart-5: #b39ddb;
  --chart-6: #e0a458;
```

These are theme-neutral series colors; no dark-theme override is needed (the legacy chart palette did not vary by theme). The first series stays `--accent`, which already differs per theme.

- [ ] **Step 2: ChartPanel reads tokens via getComputedStyle**

In `dashboard/src/components/stats/ChartPanel.svelte`, replace the `accent()` helper (lines 47-51) with a generic token reader, and use it for the whole `colors` array:

```ts
  function cssVar(name: string, fallback: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }
  function seriesColors(): string[] {
    return [
      cssVar('--accent', '#eaa45d'),
      cssVar('--chart-2', '#6aa3d8'),
      cssVar('--chart-3', '#7fb77e'),
      cssVar('--chart-4', '#d88c8c'),
      cssVar('--chart-5', '#b39ddb'),
      cssVar('--chart-6', '#e0a458'),
    ];
  }
```

Then in the `$effect`, change the `colors:` line (line 63) from the hardcoded array to:

```ts
      colors: seriesColors(),
```

- [ ] **Step 3: Run charts test + type-check**

Run: `npm test -- charts && npm run check`
Expected: PASS; 0 new type errors. (`charts.test.ts` covers `toPieData`/`toSingleSeriesBar`, not ChartPanel rendering, so it is unaffected.)

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/styles/tokens.css dashboard/src/components/stats/ChartPanel.svelte
git commit -m "style(dashboard): move chart series colors into tokens"
```

---

## Phase 4 — Modal dedup + ConfirmModal

### Task 13: `createModalAction` helper + test

**Files:**
- Create: `dashboard/src/lib/modalAction.svelte.ts`
- Create: `dashboard/tests/modal-action.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/modal-action.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { createModalAction } from '../src/lib/modalAction.svelte';

describe('createModalAction', () => {
  it('calls onSuccess and never sets error when the action succeeds', async () => {
    const action = createModalAction();
    const onSuccess = vi.fn();
    await action.run(async () => ({ ok: true }), onSuccess);
    expect(onSuccess).toHaveBeenCalledOnce();
    expect(action.error).toBe('');
    expect(action.busy).toBe(false);
  });

  it('sets error and skips onSuccess when the action fails', async () => {
    const action = createModalAction();
    const onSuccess = vi.fn();
    await action.run(async () => ({ ok: false, message: 'boom' }), onSuccess);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(action.error).toBe('boom');
    expect(action.busy).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm test -- modal-action`
Expected: FAIL — cannot resolve `../src/lib/modalAction.svelte`.

- [ ] **Step 3: Create the helper**

Create `dashboard/src/lib/modalAction.svelte.ts`:

```ts
import type { MutationResult } from './api/mutation';

/**
 * Owns the busy/error lifecycle shared by every mutating modal. Callers pass a function
 * returning a normalized MutationResult (wrap raw endpoints with `runMutation`), plus an
 * onSuccess callback (typically `onclose`). Must be a `.svelte.ts` module so it can hold $state.
 */
export function createModalAction() {
  let busy = $state(false);
  let error = $state('');
  return {
    get busy() {
      return busy;
    },
    get error() {
      return error;
    },
    clearError() {
      error = '';
    },
    async run(
      fn: () => Promise<MutationResult<unknown>>,
      onSuccess: () => void,
    ): Promise<MutationResult<unknown>> {
      busy = true;
      error = '';
      const res = await fn();
      busy = false;
      if (!res.ok) {
        error = res.message ?? '';
        return res;
      }
      onSuccess();
      return res;
    },
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- modal-action`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/modalAction.svelte.ts dashboard/tests/modal-action.test.ts
git commit -m "feat(dashboard): createModalAction helper for modal busy/error"
```

### Task 14: Shared modal CSS in global.css

**Files:**
- Modify: `dashboard/src/styles/global.css`

- [ ] **Step 1: Append shared modal classes to global.css**

Add to the end of `dashboard/src/styles/global.css`:

```css
.modal-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
  margin-top: var(--space-4);
}

.modal-info {
  color: var(--text-secondary);
}

.modal-hint {
  color: var(--text-muted);
  font-size: 13px;
}

.modal-input {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
}

.modal-textarea {
  width: 100%;
  font-family: var(--font-mono);
  font-size: 13px;
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: var(--space-3);
}
```

(`.modal-prompt` has no rules in any current modal — it is an unstyled paragraph — so it is intentionally not added.)

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/styles/global.css
git commit -m "style(dashboard): hoist shared modal CSS to global"
```

### Task 15: ConfirmModal component

**Files:**
- Create: `dashboard/src/components/modals/ConfirmModal.svelte`

- [ ] **Step 1: Create ConfirmModal**

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { MutationResult } from '$lib/api/mutation';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { createModalAction } from '$lib/modalAction.svelte';
  let {
    title = '',
    confirmLabel = 'OK',
    variant = 'primary',
    onconfirm,
    onclose,
    children,
  }: {
    title?: string;
    confirmLabel?: string;
    variant?: 'primary' | 'danger';
    onconfirm: () => Promise<MutationResult<unknown>>;
    onclose: () => void;
    children: Snippet;
  } = $props();
  const action = createModalAction();
</script>

<Modal open={true} {title} error={action.error} {onclose}>
  <p class="modal-prompt">{@render children()}</p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button {variant} disabled={action.busy} onclick={() => action.run(onconfirm, onclose)}>
      {#if action.busy}<Spinner />{:else}{confirmLabel}{/if}
    </Button>
  </div>
</Modal>
```

- [ ] **Step 2: Type-check**

Run: `npm run check`
Expected: 0 errors in ConfirmModal.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/modals/ConfirmModal.svelte
git commit -m "feat(dashboard): ConfirmModal wrapper for confirm-style modals"
```

### Task 16: Migrate the four confirm modals onto ConfirmModal

**Files:**
- Modify: `dashboard/src/components/modals/RemoveLanguageModal.svelte`
- Modify: `dashboard/src/components/modals/DeleteMemoryModal.svelte`
- Modify: `dashboard/src/components/modals/CancelExecutionModal.svelte`
- Modify: `dashboard/src/components/modals/ShutdownModal.svelte`

- [ ] **Step 1: RemoveLanguageModal**

Overwrite `dashboard/src/components/modals/RemoveLanguageModal.svelte`:

```svelte
<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { removeLanguage } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { language, onclose }: { language: string; onclose: () => void } = $props();
</script>

<ConfirmModal onconfirm={() => runMutation(() => removeLanguage(language))} {onclose}>
  Remove language <strong>{language}</strong> from configuration?
</ConfirmModal>
```

- [ ] **Step 2: DeleteMemoryModal**

Overwrite `dashboard/src/components/modals/DeleteMemoryModal.svelte`:

```svelte
<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { deleteMemory } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
</script>

<ConfirmModal variant="danger" onconfirm={() => runMutation(() => deleteMemory(name))} {onclose}>
  Delete memory <strong>{name}</strong>?
</ConfirmModal>
```

- [ ] **Step 3: CancelExecutionModal** (uses the store's `cancel`, which already returns a MutationResult; clears the store error on close)

Overwrite `dashboard/src/components/modals/CancelExecutionModal.svelte`:

```svelte
<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import type { QueuedExecution } from '$lib/api/types';
  let { execution, onclose }: { execution: QueuedExecution; onclose: () => void } = $props();
  // Clear the store-level cancel error on dismiss so a failed cancel here doesn't leave a
  // stale message under the (now uncovered) Executions Queue.
  function handleClose() {
    executions.clearCancelError();
    onclose();
  }
</script>

<ConfirmModal onconfirm={() => executions.cancel(execution)} onclose={handleClose}>
  Are you sure? The execution will continue running until timeout, it will simply no longer be in
  the queue. Abandoning a running execution is only advised as a measure for unblocking Serena.
</ConfirmModal>
```

- [ ] **Step 4: ShutdownModal** (fixes finding 2 — only close on success)

Overwrite `dashboard/src/components/modals/ShutdownModal.svelte`:

```svelte
<script lang="ts">
  import ConfirmModal from './ConfirmModal.svelte';
  import { shutdown } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  let { onclose }: { onclose: () => void } = $props();
  async function confirm() {
    const res = await runMutation(() => shutdown());
    // Only schedule the tab close if the server actually accepted the shutdown.
    if (res.ok) setTimeout(() => window.close(), 1000);
    return res;
  }
</script>

<ConfirmModal
  title="Shutdown Server"
  confirmLabel="Shutdown"
  variant="danger"
  onconfirm={confirm}
  {onclose}
>
  Shut down the Serena server?
</ConfirmModal>
```

- [ ] **Step 5: Type-check and run the relevant tests**

Run: `npm run check && npm test -- delete-memory-modal executions`
Expected: 0 type errors; `delete-memory-modal` still passes (button label `OK`, inline error). The merged `executions-queue` test is unaffected (it renders `ExecutionsQueue`, not the modal).

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/modals/RemoveLanguageModal.svelte dashboard/src/components/modals/DeleteMemoryModal.svelte dashboard/src/components/modals/CancelExecutionModal.svelte dashboard/src/components/modals/ShutdownModal.svelte
git commit -m "refactor(dashboard): confirm modals use ConfirmModal; fix shutdown error handling"
```

### Task 17: Refactor input/editor modals onto createModalAction + shared CSS

**Files:**
- Modify: `dashboard/src/components/modals/AddLanguageModal.svelte`
- Modify: `dashboard/src/components/modals/CreateMemoryModal.svelte`
- Modify: `dashboard/src/components/modals/EditSerenaConfigModal.svelte`

- [ ] **Step 1: AddLanguageModal** — use `createModalAction`, drop local busy/error and the inline `.modal-info`/`.modal-hint`/`.modal-actions` styles (now global). Add an `aria-label` to the combobox via existing markup (the Combobox input gets a label in Task 20; here only the action refactor):

Overwrite `dashboard/src/components/modals/AddLanguageModal.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Combobox from '../common/Combobox.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { fetchAvailableLanguages, addLanguage } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  let { projectName, onclose }: { projectName: string; onclose: () => void } = $props();
  let options = $state<string[]>([]);
  let selected = $state('');
  const action = createModalAction();
  onMount(() => {
    void (async () => {
      options = (await fetchAvailableLanguages()).languages;
    })();
  });
  function add() {
    if (!selected) return;
    void action.run(() => runMutation(() => addLanguage(selected)), onclose);
  }
</script>

<Modal open={true} title="Add Language" error={action.error} {onclose}>
  <p class="modal-info">
    Adding a language to serena config of project <strong>{projectName}</strong>.
  </p>
  <p class="modal-hint">
    Note that this may download dependencies for the language server and then start it; it may take
    a few seconds before the LS is responsive.
  </p>
  <Combobox {options} value={selected} onselect={(v) => (selected = v)} />
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={action.busy || !selected} onclick={add}
      >{#if action.busy}<Spinner />{:else}Add Language{/if}</Button
    >
  </div>
</Modal>
```

(No `<style>` block — all classes are global now.)

- [ ] **Step 2: CreateMemoryModal** — same treatment; preserve the `Create` label and `disabled={!valid || busy}` gating that Task 10's test asserts:

Overwrite `dashboard/src/components/modals/CreateMemoryModal.svelte`:

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { saveMemory } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  import { isValidMemoryName } from '$lib/validation';
  let {
    projectName,
    onclose,
    oncreated,
  }: { projectName: string; onclose: () => void; oncreated: (_name: string) => void } = $props();
  let name = $state('');
  const valid = $derived(isValidMemoryName(name));
  const action = createModalAction();
  function create() {
    if (!valid) return;
    void action.run(() => runMutation(() => saveMemory(name, '')), () => oncreated(name));
  }
</script>

<Modal open={true} error={action.error} {onclose}>
  <p class="modal-info">Create a new memory for project <strong>{projectName}</strong>.</p>
  <p class="modal-hint">
    Use underscores instead of spaces (e.g. "api_architecture"). Use "/" for subdirectories (e.g.
    "architecture/api_design"); use the "global/" prefix for cross-project memories.
  </p>
  <input
    class="modal-input"
    aria-label="Memory name"
    placeholder="e.g., project_overview or topic/memory_name"
    bind:value={name}
  />
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={!valid || action.busy} onclick={create}
      >{#if action.busy}<Spinner />{:else}Create{/if}</Button
    >
  </div>
</Modal>
```

- [ ] **Step 3: EditSerenaConfigModal** — use createModalAction, keep the dirty guard, drop the local `.modal-textarea`/`.modal-hint`/`.modal-actions` styles, add `aria-label` to the textarea:

Overwrite `dashboard/src/components/modals/EditSerenaConfigModal.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getSerenaConfig, saveSerenaConfig } from '$lib/api/endpoints';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  import { confirmDiscard } from '$lib/confirmDiscard';
  let { onclose }: { onclose: () => void } = $props();
  let content = $state('');
  let initialContent = $state('');
  const dirty = $derived(content !== initialContent);
  const action = createModalAction();
  async function load() {
    const loaded = (await getSerenaConfig()).content;
    content = loaded;
    initialContent = loaded;
  }
  onMount(() => {
    void load();
  });
  function requestClose() {
    if (confirmDiscard(dirty)) onclose();
  }
  function save() {
    void action.run(() => runMutation(() => saveSerenaConfig(content)), onclose);
  }
</script>

<Modal open={true} title="Global Serena Configuration" error={action.error} onclose={requestClose}>
  <p class="modal-hint">
    Note: Changes to the configuration only take effect after Serena is restarted.
  </p>
  <textarea class="modal-textarea" aria-label="Configuration" rows="20" bind:value={content}
  ></textarea>
  <div class="modal-actions">
    <Button variant="secondary" onclick={requestClose}>Cancel</Button>
    <Button disabled={action.busy} onclick={save}>Save</Button>
  </div>
</Modal>
```

- [ ] **Step 4: Type-check and run modal tests**

Run: `npm run check && npm test -- add-language-modal create-memory-modal edit-serena-config-modal`
Expected: 0 type errors; all three pass (labels, gating, inline error, dirty guard preserved).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/modals/AddLanguageModal.svelte dashboard/src/components/modals/CreateMemoryModal.svelte dashboard/src/components/modals/EditSerenaConfigModal.svelte
git commit -m "refactor(dashboard): input/editor modals use createModalAction + shared CSS"
```

### Task 18: EditMemoryModal — createModalAction, rename busy+Enter, `{#key}` remount

**Files:**
- Modify: `dashboard/src/components/modals/EditMemoryModal.svelte`
- Modify: `dashboard/src/components/modals/ModalHost.svelte:28`

- [ ] **Step 1: Wrap EditMemoryModal in `{#key m.name}` in ModalHost**

In `dashboard/src/components/modals/ModalHost.svelte`, change the `editMemory` branch (line 28) from:

```svelte
  {:else if m.kind === 'editMemory'}<EditMemoryModal name={m.name} onclose={close} />
```

to:

```svelte
  {:else if m.kind === 'editMemory'}{#key m.name}<EditMemoryModal name={m.name} onclose={close} />{/key}
```

- [ ] **Step 2: Rewrite EditMemoryModal**

Overwrite `dashboard/src/components/modals/EditMemoryModal.svelte`:

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getMemory, saveMemory, renameMemory } from '$lib/api/endpoints';
  import { isValidMemoryName } from '$lib/validation';
  import { runMutation } from '$lib/api/mutation';
  import { createModalAction } from '$lib/modalAction.svelte';
  import { confirmDiscard } from '$lib/confirmDiscard';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
  // `{#key m.name}` in ModalHost remounts this component per memory, so initializing from
  // the prop here is correct: a different memory mounts a fresh instance.
  let currentName = $state(name);
  let content = $state('');
  let initialContent = $state('');
  let renaming = $state(false);
  let renameValue = $state(name);
  const dirty = $derived(content !== initialContent);
  const action = createModalAction();
  const renameAction = createModalAction();
  onMount(() => {
    void (async () => {
      // On failure the backend returns {status:'error', message} (HTTP 200) with no `content`;
      // fall back to an empty string so the textarea never binds to `undefined`.
      const loaded = (await getMemory(name)).content ?? '';
      content = loaded;
      initialContent = loaded;
    })();
  });
  function requestClose() {
    if (confirmDiscard(dirty)) onclose();
  }
  function save() {
    void action.run(() => runMutation(() => saveMemory(currentName, content)), onclose);
  }
  function applyRename() {
    if (!isValidMemoryName(renameValue) || renameValue === currentName) {
      renaming = false;
      return;
    }
    void renameAction.run(
      () => runMutation(() => renameMemory(currentName, renameValue)),
      () => {
        currentName = renameValue;
        renaming = false;
      },
    );
  }
</script>

<Modal open={true} error={action.error || renameAction.error} onclose={requestClose}>
  <h3 class="modal-title-with-meta">
    Memory:
    {#if renaming}
      <input
        class="memory-rename-input"
        aria-label="New memory name"
        bind:value={renameValue}
        onkeydown={(e) => e.key === 'Enter' && applyRename()}
      />
      <button
        class="rename-confirm"
        type="button"
        title="Confirm rename"
        aria-label="Confirm rename"
        disabled={renameAction.busy}
        onclick={applyRename}>✓</button
      >
    {:else}
      <span class="memory-name-display">{currentName}</span>
      <button
        class="rename-trigger"
        type="button"
        title="Rename memory"
        aria-label="Rename memory"
        onclick={() => {
          renaming = true;
          renameValue = currentName;
        }}>✎</button
      >
    {/if}
  </h3>
  <textarea
    class="memory-editor modal-textarea"
    aria-label="Memory content"
    rows="20"
    bind:value={content}
  ></textarea>
  <div class="modal-actions">
    <Button variant="secondary" onclick={requestClose}>Cancel</Button>
    <Button disabled={action.busy} onclick={save}>Save</Button>
  </div>
</Modal>

<style>
  .memory-rename-input {
    font-family: var(--font-mono);
    font-size: 14px;
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--bg-card);
    color: var(--text-primary);
  }
  .memory-name-display {
    font-family: var(--font-mono);
  }
  .rename-trigger {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
  }
</style>
```

(The local `.modal-textarea` and `.modal-actions` blocks are removed — they are global now. `.rename-confirm` had no rules previously; keep it unstyled.)

- [ ] **Step 3: Type-check, run the edit-memory test and confirm warnings are gone**

Run: `npm run check`
Expected: 0 errors AND the two `state_referenced_locally` warnings for `EditMemoryModal.svelte:11,18` are gone (the eslint-disable comments and the suppressed pattern were removed by the rewrite).

Run: `npm test -- edit-memory-modal`
Expected: PASS (dirty-guard behavior preserved).

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/modals/EditMemoryModal.svelte dashboard/src/components/modals/ModalHost.svelte
git commit -m "refactor(dashboard): EditMemoryModal createModalAction, rename busy/Enter, key remount"
```

---

## Phase 5 — Card dedup + accessibility

### Task 19: Compose `<Card>` in ListPanel and ProjectsPanel

`Card.svelte` renders `<section class="card">{children}</section>` with the exact `.card` style these panels duplicate. Compose it instead.

**Files:**
- Modify: `dashboard/src/components/overview/ListPanel.svelte`
- Modify: `dashboard/src/components/overview/ProjectsPanel.svelte`

- [ ] **Step 1: ListPanel** — wrap in `<Card>`, drop the duplicated `.card` style block:

Overwrite `dashboard/src/components/overview/ListPanel.svelte`:

```svelte
<script lang="ts">
  import Card from '../common/Card.svelte';
  import Collapsible from '../common/Collapsible.svelte';
  let { title, items }: { title: string; items: Array<{ name: string; active?: boolean }> } =
    $props();
</script>

<Card>
  <Collapsible {title}>
    {#if items.length}
      <ul class="list-panel">
        {#each items as item (item.name)}<li class:active={item.active}>{item.name}</li>{/each}
      </ul>
    {:else}
      <div class="no-stats-message">None.</div>
    {/if}
  </Collapsible>
</Card>

<style>
  .list-panel {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 340px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .list-panel li {
    padding: var(--space-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-elevated);
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-primary);
  }
  .list-panel li.active {
    background: var(--accent);
    color: var(--text-on-accent);
    border-color: var(--accent);
  }
  .no-stats-message {
    color: var(--text-muted);
  }
</style>
```

- [ ] **Step 2: ProjectsPanel** — same; drop the `.card` block, keep everything else:

In `dashboard/src/components/overview/ProjectsPanel.svelte`:
- Add `import Card from '../common/Card.svelte';` after the `ProjectInfo` import.
- Replace the wrapping `<div class="card"> … </div>` (lines 7-22) with `<Card> … </Card>` (same inner content).
- Delete the `.card { … }` rule (lines 25-32) from the `<style>` block.

- [ ] **Step 3: Type-check**

Run: `npm run check`
Expected: 0 errors. (Visual parity is verified in Phase 6 — `<Card>` renders a `<section class="card">` with identical styling, replacing the panels' `<div class="card">`.)

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/overview/ListPanel.svelte dashboard/src/components/overview/ProjectsPanel.svelte
git commit -m "refactor(dashboard): ListPanel/ProjectsPanel compose Card (drop duplicated .card)"
```

### Task 20: Header menu accessibility

**Files:**
- Modify: `dashboard/src/components/shell/Header.svelte:16-36`

- [ ] **Step 1: Add ARIA + Escape-to-close to the menu button**

In `dashboard/src/components/shell/Header.svelte`, update `handleWindowClick` to also handle Escape via a key handler, and annotate the button.

Change the `<svelte:window>` line (line 24) to add a keydown handler:

```svelte
<svelte:window onclick={handleWindowClick} onkeydown={handleWindowKey} />
```

Add this function after `handleWindowClick` (after line 21):

```ts
  function handleWindowKey(event: KeyboardEvent) {
    if (event.key === 'Escape') menuOpen = false;
  }
```

Change the menu button (lines 34-36) from:

```svelte
      <button class="menu-button" onclick={() => (menuOpen = !menuOpen)}>
        <span>☰</span><span>Menu</span>
      </button>
```

to:

```svelte
      <button
        class="menu-button"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        onclick={() => (menuOpen = !menuOpen)}
      >
        <span aria-hidden="true">☰</span><span>Menu</span>
      </button>
```

- [ ] **Step 2: Type-check**

Run: `npm run check`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/shell/Header.svelte
git commit -m "a11y(dashboard): header menu aria-haspopup/expanded + Escape to close"
```

### Task 21: Focus trap in Modal

**Files:**
- Modify: `dashboard/src/components/common/Modal.svelte:31-56`

- [ ] **Step 1: Trap Tab within the dialog**

In `dashboard/src/components/common/Modal.svelte`, extend `onKey` (lines 31-33) to trap Tab when the dialog is open:

```ts
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      onclose();
      return;
    }
    if (e.key !== 'Tab' || !open || !contentEl) return;
    const focusable = contentEl.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input, textarea, select, [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const activeEl = document.activeElement;
    if (e.shiftKey && activeEl === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && activeEl === last) {
      e.preventDefault();
      first.focus();
    }
  }
```

The existing `onkeydown={(e) => e.stopPropagation()}` on `.modal-content` (line 47) prevents the window handler from firing twice; keep it. Since `onKey` is bound to `svelte:window` (line 36), it still receives Tab while focus is inside the dialog (focus is on a child, the window listener is at the top). Verify in Phase 6 runtime check.

- [ ] **Step 2: Type-check + run the modal tests**

Run: `npm run check && npm test -- edit-memory-modal edit-serena-config-modal delete-memory-modal add-language-modal`
Expected: 0 errors; all pass (focus trap does not change tested behavior).

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/common/Modal.svelte
git commit -m "a11y(dashboard): trap Tab focus within open modal"
```

---

## Phase 6 — ChartPanel update() refactor + final verification

### Task 22: Add `update()` to frappe-charts typings

**Files:**
- Modify: `dashboard/src/types/frappe-charts.d.ts`

- [ ] **Step 1: Extend the Chart type**

Overwrite `dashboard/src/types/frappe-charts.d.ts`:

```ts
declare module 'frappe-charts' {
  export class Chart {
    constructor(parent: HTMLElement | string, options: Record<string, unknown>);
    update(data: { labels: string[]; datasets: Array<{ name?: string; values: number[] }> }): void;
    destroy(): void;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/types/frappe-charts.d.ts
git commit -m "build(dashboard): type Chart.update for frappe-charts"
```

### Task 23: ChartPanel — update() on data change, recreate on theme, remove suppressor

**Files:**
- Modify: `dashboard/src/components/stats/ChartPanel.svelte`

- [ ] **Step 1: Rewrite ChartPanel**

Overwrite `dashboard/src/components/stats/ChartPanel.svelte` (this removes the module-level suppressor block and the destroy() try/catch, and switches to create-once + update):

```svelte
<script lang="ts">
  import { untrack } from 'svelte';
  import { Chart } from 'frappe-charts';
  import type { FrappeData } from '$lib/charts';
  import { theme } from '$lib/stores/theme.svelte';

  let {
    title,
    data,
    type,
    valuesOverPoints = false,
  }: {
    title: string;
    data: FrappeData;
    type: 'pie' | 'percentage' | 'bar';
    valuesOverPoints?: boolean;
  } = $props();
  let el = $state<HTMLDivElement | null>(null);

  function cssVar(name: string, fallback: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  }
  function seriesColors(): string[] {
    return [
      cssVar('--accent', '#eaa45d'),
      cssVar('--chart-2', '#6aa3d8'),
      cssVar('--chart-3', '#7fb77e'),
      cssVar('--chart-4', '#d88c8c'),
      cssVar('--chart-5', '#b39ddb'),
      cssVar('--chart-6', '#e0a458'),
    ];
  }

  let chartRef: Chart | null = null;

  // Recreate the chart only when the theme changes (colors are baked in at construction) or
  // when `el` (re)binds. `data`/`title`/`type` are read via untrack() so a data change does
  // NOT re-run this effect — the separate update-effect below handles data in place, avoiding
  // the full DOM teardown that previously triggered the ResizeObserver removeChild race.
  $effect(() => {
    void theme.current; // re-run on theme change
    if (!el) return; // reading `el` makes (re)bind a dependency, which we want
    const node = el;
    const chart = untrack(() => {
      node.innerHTML = '';
      return new Chart(node, {
        title,
        data,
        type,
        height: type === 'bar' ? 240 : 220,
        colors: seriesColors(),
        valuesOverPoints: valuesOverPoints ? 1 : 0,
      });
    });
    chartRef = chart;
    return () => {
      chartRef = null;
      chart.destroy();
    };
  });

  // Data-only updates: read `data` (registers the dependency) and diff in place. Skips when
  // the chart hasn't been built yet — the create-effect renders the first frame.
  $effect(() => {
    const next = data;
    if (chartRef) chartRef.update(next);
  });
</script>

<div class="chart-group">
  <h3>{title}</h3>
  <div bind:this={el}></div>
</div>

<style>
  .chart-group {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-4);
    box-shadow: var(--shadow);
  }
</style>
```

Note on effect ordering: the create-effect reads only `theme.current` and `el`, so a data change does NOT re-run it; the second effect reads `data` and calls `update()`. On first mount both run — create builds the chart and sets `chartRef`; the update-effect then calls `update(data)` once with the same data (idempotent, cheap). On theme change the create-effect tears down and rebuilds with fresh colors.

- [ ] **Step 2: Type-check**

Run: `npm run check`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/stats/ChartPanel.svelte
git commit -m "perf(dashboard): ChartPanel update() in place; remove removeChild suppressor"
```

### Task 24: Full verification, build, and bundle commit

**Files:**
- Modify (generated): `dashboard/../src/serena/resources/dashboard/assets/*`

- [ ] **Step 1: Format, lint, type-check, test**

Run: `npm run format && npm run lint && npm run check && npm test`
Expected: prettier writes nothing new (or stage what it changes), eslint clean, 0 type errors, 0 `state_referenced_locally` warnings remaining (Collapsible/Combobox still have theirs — see Step 2), all tests pass.

- [ ] **Step 2: Confirm warning state**

Run: `npm run check 2>&1 | grep -i "state_referenced_locally" || echo "none"`
Expected: Only `Collapsible.svelte` and `Combobox.svelte` may remain (their `open`/`value` initial-capture is out of scope for this plan and documented as initial-only). `EditMemoryModal` warnings must be GONE. If `EditMemoryModal` still appears, the Task 18 rewrite is incomplete.

- [ ] **Step 3: Build the bundle**

Run: `npm run build`
Expected: succeeds; regenerates `../src/serena/resources/dashboard/assets/index-*.js` and `index-*.css` (the `prebuild` clean removes stale hashed files).

- [ ] **Step 4: Manual runtime verification (REQUIRED — the suppressor was removed)**

Start a Serena MCP server with the dashboard enabled (default port 24282), open the dashboard, and in the browser devtools console confirm:
- Stats page: click Refresh Stats — all 5 charts render; click Refresh again (data update path) — charts update with **no `removeChild`/`NotFoundError` console errors**.
- Toggle theme on the Stats page — charts recreate and recolor with no console errors.
- Light AND dark: Overview cards (Registered Projects / list panels) match the previous look (Card composition).
- Open each modal (Add Language, Create/Edit/Delete Memory, Edit Config, Cancel Execution, Shutdown — do NOT confirm Shutdown): inline errors and busy spinners work; Tab stays within the dialog; Escape closes.
- Logs page: tool names still highlight correctly.

If any `removeChild` console error appears on the chart paths, reinstate the suppressor: restore the `<script module>` block and the `try/catch` around `destroy()` from git history (`git show HEAD~1:dashboard/src/components/stats/ChartPanel.svelte`) while keeping the `update()` logic, then rebuild.

- [ ] **Step 5: Commit the regenerated bundle**

```bash
git add -A src/serena/resources/dashboard/ dashboard/
git commit -m "build(dashboard): rebuild bundle after review fixes"
```

---

## Self-review notes (coverage map)

- Findings 1 (highlightTools) → Task 1. Single-quote escape → Task 1.
- Finding 2 (ShutdownModal) → Task 16 Step 4.
- Finding 3 (applyRename busy + Enter) → Task 18.
- Finding 4 (EditMemoryModal init-capture / `{#key}`) → Task 18.
- Findings 5, 6 (`#fff`) → Task 11.
- Finding 7 (chart hex) → Task 12 + Task 23.
- Finding 8 (`.card` triple-dup) → Task 19.
- Finding 9 (`.modal-actions`/textarea dup) → Tasks 14, 16, 17, 18.
- Finding 10 (busy/error dup + dead `?? 'Failed'`) → Tasks 13, 16, 17, 18.
- Finding 11 (`exec()` test dup) → Tasks 2, 5, 6.
- Finding 12 (Header a11y) → Task 20.
- Finding 13 (input labels) → Tasks 17, 18.
- Finding 14 (Modal focus trap) → Task 21.
- Finding 15 (ChartPanel lifecycle + suppressor removal) → Tasks 22, 23, 24.
- Test streamlining (drop/merge/dedup/helpers/coverage gaps) → Tasks 2–10.
```
