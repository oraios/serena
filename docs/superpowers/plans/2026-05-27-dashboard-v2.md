# Dashboard v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic jQuery Serena dashboard with a component-based Svelte 5 + TypeScript app (Vite), at full feature parity, while keeping the Flask backend untouched.

**Architecture:** Frontend-only rewrite. The Flask endpoints in `src/serena/dashboard.py` are a frozen contract consumed through a typed API client. Source lives in a new top-level `dashboard/` npm project; Vite builds hashed assets into `src/serena/resources/dashboard/`, which is committed to git and shipped in the wheel by hatchling. Charts use Frappe Charts (bundled). Google Fonts stay on CDN.

**Tech Stack:** Svelte 5 (runes), TypeScript, Vite, Frappe Charts, Vitest + @testing-library/svelte, ESLint + Prettier + svelte-check.

**Reference spec:** `docs/superpowers/specs/2026-05-27-dashboard-v2-design.md`

---

## Conventions for every task

- Work inside `dashboard/` unless a path says otherwise. Run npm commands from `dashboard/`.
- TDD: write the failing test, see it fail, implement, see it pass, commit.
- Commit messages use `feat(dashboard):` / `test(dashboard):` / `chore(dashboard):` prefixes.
- Never hardcode hex colors in components — use `var(--token)` from `tokens.css`.
- All network calls go through `src/lib/api/`. Never call `fetch` from a component.

---

## Phase 0 — Scaffold the frontend project

### Task 0.1: Initialize the Vite + Svelte 5 + TS project

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/svelte.config.js`
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.ts`
- Create: `dashboard/src/App.svelte`
- Create: `dashboard/.gitignore`

- [ ] **Step 1: Create `dashboard/package.json`**

```json
{
  "name": "serena-dashboard",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "check": "svelte-check --tsconfig ./tsconfig.json",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint . && prettier --check .",
    "format": "prettier --write ."
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^5.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/svelte": "^5.2.0",
    "@tsconfig/svelte": "^5.0.0",
    "eslint": "^9.0.0",
    "eslint-plugin-svelte": "^2.46.0",
    "jsdom": "^25.0.0",
    "prettier": "^3.3.0",
    "prettier-plugin-svelte": "^3.3.0",
    "svelte": "^5.0.0",
    "svelte-check": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  },
  "dependencies": {
    "frappe-charts": "^1.6.2"
  }
}
```

- [ ] **Step 2: Create `dashboard/tsconfig.json`**

```json
{
  "extends": "@tsconfig/svelte/tsconfig.json",
  "compilerOptions": {
    "target": "ESNext",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "resolveJsonModule": true,
    "allowJs": true,
    "checkJs": true,
    "isolatedModules": true,
    "moduleResolution": "bundler",
    "strict": true,
    "verbatimModuleSyntax": true,
    "baseUrl": ".",
    "paths": { "$lib/*": ["src/lib/*"] }
  },
  "include": ["src/**/*.ts", "src/**/*.svelte", "tests/**/*.ts"]
}
```

- [ ] **Step 3: Create `dashboard/svelte.config.js`**

```js
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
export default { preprocess: vitePreprocess() };
```

- [ ] **Step 4: Create `dashboard/vite.config.ts`**

The build output goes into the Python package resource dir. `base: './'` makes asset URLs relative so they resolve under `/dashboard/`. Dev proxies the backend routes to a running Serena dashboard (port `0x5EDA` = 24282).

```ts
import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';

const BACKEND = 'http://localhost:24282';
// All non-static backend routes that the app calls (frozen contract).
const API_ROUTES = [
  '/get_log_messages', '/clear_logs', '/get_tool_names', '/get_tool_stats',
  '/clear_tool_stats', '/get_token_count_estimator_name', '/get_config_overview',
  '/shutdown', '/get_available_languages', '/add_language', '/remove_language',
  '/get_memory', '/save_memory', '/delete_memory', '/rename_memory',
  '/get_serena_config', '/save_serena_config', '/queued_task_executions',
  '/cancel_task_execution', '/last_execution', '/fetch_unread_news',
  '/mark_news_snippet_as_read', '/heartbeat',
];

export default defineConfig({
  plugins: [svelte()],
  base: './',
  resolve: { alias: { $lib: fileURLToPath(new URL('./src/lib', import.meta.url)) } },
  build: {
    outDir: fileURLToPath(new URL('../src/serena/resources/dashboard', import.meta.url)),
    emptyOutDir: false, // keep icons/logos/*.png that live in the same dir
    assetsDir: 'assets',
  },
  server: {
    port: 5273,
    proxy: Object.fromEntries(API_ROUTES.map((r) => [r, { target: BACKEND, changeOrigin: true }])),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    globals: true,
  },
});
```

- [ ] **Step 5: Create `dashboard/index.html`** (Google Fonts stay on CDN; favicons resolve from the same output dir)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Serena Dashboard</title>
  <link rel="icon" type="image/png" sizes="16x16" href="./serena-icon-16.png" />
  <link rel="icon" type="image/png" sizes="32x32" href="./serena-icon-32.png" />
  <link rel="icon" type="image/png" sizes="48x48" href="./serena-icon-48.png" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

- [ ] **Step 6: Create `dashboard/src/main.ts`**

```ts
import { mount } from 'svelte';
import './styles/tokens.css';
import './styles/global.css';
import App from './App.svelte';

const app = mount(App, { target: document.getElementById('app')! });
export default app;
```

- [ ] **Step 7: Create placeholder `dashboard/src/App.svelte`** (replaced in Phase 2)

```svelte
<script lang="ts">
</script>

<main>Serena Dashboard v2 — scaffold OK</main>
```

- [ ] **Step 8: Create placeholder style files so `main.ts` imports resolve**

Create `dashboard/src/styles/tokens.css` with `:root {}` and `dashboard/src/styles/global.css` empty. (Filled in Phase 1.)

- [ ] **Step 9: Create `dashboard/.gitignore`**

```
node_modules
dist
.vite
*.local
```

- [ ] **Step 10: Install and verify dev server boots**

Run: `cd dashboard && npm install && npm run check`
Expected: install succeeds; `svelte-check` reports 0 errors.

- [ ] **Step 11: Commit**

```bash
git add dashboard/ && git commit -m "chore(dashboard): scaffold Svelte 5 + Vite + TS project"
```

### Task 0.2: Configure testing, lint, and the subproject CLAUDE.md

**Files:**
- Create: `dashboard/tests/setup.ts`
- Create: `dashboard/eslint.config.js`
- Create: `dashboard/.prettierrc`
- Create: `dashboard/CLAUDE.md`

- [ ] **Step 1: Create `dashboard/tests/setup.ts`**

```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 2: Create `dashboard/eslint.config.js`**

```js
import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
export default [
  js.configs.recommended,
  ...svelte.configs['flat/recommended'],
  { ignores: ['node_modules/', 'dist/'] },
];
```

- [ ] **Step 3: Create `dashboard/.prettierrc`**

```json
{ "singleQuote": true, "printWidth": 100, "plugins": ["prettier-plugin-svelte"] }
```

- [ ] **Step 4: Add a trivial smoke test `dashboard/tests/smoke.test.ts`**

```ts
import { describe, it, expect } from 'vitest';
describe('test harness', () => {
  it('runs', () => { expect(1 + 1).toBe(2); });
});
```

- [ ] **Step 5: Run the test suite**

Run: `cd dashboard && npm test`
Expected: 1 passing test.

- [ ] **Step 6: Create `dashboard/CLAUDE.md`** (full content below)

```markdown
# Serena Dashboard (frontend)

This directory is the **frontend only**. The dashboard's HTTP API lives in
`../src/serena/dashboard.py` and is a **frozen contract** — never change endpoint
names, request/response shapes, ports, or the host-header check from here.

## Commands (run from `dashboard/`)
- `npm install` — install deps
- `npm run dev` — Vite dev server (proxies API to a running Serena dashboard on :24282)
- `npm run build` — build hashed assets into `../src/serena/resources/dashboard/`
- `npm run check` — type-check (`svelte-check`)
- `npm test` — Vitest
- `npm run lint` / `npm run format` — ESLint + Prettier

## Running the backend for `npm run dev`
Start any Serena MCP server with the dashboard enabled, note its port (default 24282),
and set it as the proxy target in `vite.config.ts` if it differs.

## Architecture rules
- Components are small and single-purpose: props in, events out, scoped CSS.
- State lives in runes stores under `src/lib/stores/` (`.svelte.ts`).
- All network access goes through `src/lib/api/`. Never `fetch` from a component.
- Never reintroduce jQuery.
- Colors come from `src/styles/tokens.css`. Never hardcode hex in a component.
- Charts go through `src/components/stats/ChartPanel.svelte` (Frappe Charts wrapper).

## The contract rule (CI enforces this)
After any change, run `npm run build` and commit the regenerated
`../src/serena/resources/dashboard/` output. CI rebuilds and fails the PR if the
committed output is stale.

## Adding a feature that needs a backend route
1. Add the response/request type to `src/lib/api/types.ts`.
2. Add a typed function to `src/lib/api/endpoints.ts`.
3. Add/extend a store in `src/lib/stores/`.
4. Build the component and a Vitest test.

## Visual parity
The app must match the legacy dashboard in both light and dark themes. Compare
side-by-side before merging. The palette is defined once in `tokens.css`.
```

- [ ] **Step 7: Commit**

```bash
git add dashboard/ && git commit -m "chore(dashboard): add test setup, lint config, and CLAUDE.md"
```

---

## Phase 1 — Foundation: design tokens, API layer, stores, utilities

### Task 1.1: Port the design tokens (palette) verbatim

**Files:**
- Modify: `dashboard/src/styles/tokens.css`
- Create: `dashboard/src/styles/global.css` (base element styles)

Source of truth is the legacy `src/serena/resources/dashboard/dashboard.css` `:root` and dark-theme blocks. Reproduce values exactly.

- [ ] **Step 1: Write `dashboard/src/styles/tokens.css`**

```css
:root {
  --bg: #f5f5f5;
  --bg-card: #ffffff;
  --bg-elevated: #ffffff;
  --bg-secondary-btn: #f0f2f5;
  --text-primary: #1f2328;
  --text-secondary: #3f4754;
  --text-muted: #6a737d;
  --border: #e3e6ea;
  --border-strong: #d0d7de;
  --accent: #eaa45d;
  --accent-hover: #dca662;
  --btn-disabled: #adb5bd;
  --tool-highlight: #fff3bf;
  --success: #22c55e;
  --log-debug: #8b95a1;
  --log-info: #1f2328;
  --log-warning: #d97706;
  --log-error: #dc2626;
  --radius: 6px;
  --radius-sm: 4px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px;
  --space-4: 16px; --space-6: 24px; --space-8: 32px;
  --max-width: 1600px;
  --font-sans: 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}

[data-theme='dark'] {
  --bg: #1a1a1a;
  --bg-card: #2d2d2d;
  --bg-elevated: #262b32;
  --bg-secondary-btn: #262b32;
  --text-primary: #e6edf3;
  --text-secondary: #c9d1d9;
  --text-muted: #8b95a1;
  --border: #2d333b;
  --border-strong: #3d444d;
  --tool-highlight: #f6c948;
  --log-info: #e6edf3;
  --log-warning: #f59e0b;
  --log-error: #f87171;
}
```

- [ ] **Step 2: Write `dashboard/src/styles/global.css`** (body, headings, scrollbars, link reset — port the equivalent base rules from legacy `dashboard.css`)

```css
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--font-sans);
  background: var(--bg);
  color: var(--text-primary);
}
h1, h2, h3 { font-weight: 600; }
code, pre, .mono { font-family: var(--font-mono); }
a { color: inherit; }
```

- [ ] **Step 3: Verify build still compiles**

Run: `cd dashboard && npm run check`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/styles && git commit -m "feat(dashboard): port design tokens and base styles"
```

### Task 1.2: Define API types mirroring the Pydantic models

**Files:**
- Create: `dashboard/src/lib/api/types.ts`

These types mirror `src/serena/dashboard.py` and `ToolUsageStats.Entry`. Keep field names identical to the JSON.

- [ ] **Step 1: Write `dashboard/src/lib/api/types.ts`**

```ts
// Mirrors src/serena/dashboard.py response/request models. Field names must match JSON.

export interface ToolStatEntry {
  num_times_called: number;
  input_tokens: number;
  output_tokens: number;
}
export type ToolStats = Record<string, ToolStatEntry>;

// NOTE: /get_config_overview's tool_stats_summary is a DIFFERENT, reduced shape —
// the backend renames num_times_called -> num_calls and drops the token fields
// (dashboard.py:564). It is NOT a ToolStats.
export interface ToolSummaryEntry { num_calls: number; }
export type ToolStatsSummary = Record<string, ToolSummaryEntry>;

export interface ResponseLog {
  messages: string[];
  max_idx: number;
  active_project: string | null;
}

export interface ResponseToolNames { tool_names: string[]; }
export interface ResponseToolStats { stats: ToolStats; }

// Precise nested shapes verified against ResponseConfigOverview in dashboard.py.
export interface ActiveProject {
  name: string | null;
  language: string | null; // comma-separated, e.g. "Python, TypeScript"
  path: string | null;
}
export interface ContextInfo { name: string; description: string; path: string; }
export interface ModeInfo { name: string; description?: string; path: string; is_active?: boolean; }
export interface ProjectInfo { name: string; path: string; is_active: boolean; }
export interface ToolInfo { name: string; is_active: boolean; }
export interface ContextOption { name: string; is_active: boolean; path: string; }

export interface ResponseConfigOverview {
  active_project: ActiveProject | null;
  context: ContextInfo;
  modes: ModeInfo[];
  active_tools: string[];
  tool_stats_summary: ToolStatsSummary;
  registered_projects: ProjectInfo[];
  available_tools: ToolInfo[];
  available_modes: ModeInfo[];
  available_contexts: ContextOption[];
  available_memories: string[] | null;
  jetbrains_mode: boolean;
  languages: string[];
  encoding: string | null;
  current_client: string | null;
  serena_version: string;
}

export interface ResponseAvailableLanguages { languages: string[]; }
export interface ResponseGetMemory { content: string; memory_name: string; }
export interface ResponseGetSerenaConfig { content: string; }

export interface QueuedExecution {
  task_id: number;
  is_running: boolean;
  name: string;
  finished_successfully: boolean;
  logged: boolean;
}
export interface ResponseQueuedExecutions { queued_executions: QueuedExecution[]; status: string; }
export interface ResponseLastExecution { last_execution: QueuedExecution | null; status: string; }
export interface ResponseCancelExecution { status: string; was_cancelled: boolean; message?: string; }

// News ids are YYYYMMDD strings; values are HTML snippets.
export interface ResponseNews { news: Record<string, string>; status: string; }

// Generic mutation responses ({status, message}) for add/remove/save/delete/rename.
export interface StatusResponse { status: 'success' | 'error'; message?: string; }
export interface TokenEstimatorResponse { token_count_estimator_name: string; }
```

- [ ] **Step 2: Type-check**

Run: `cd dashboard && npm run check`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/lib/api/types.ts && git commit -m "feat(dashboard): add typed API models"
```

### Task 1.3: Build the typed fetch client (TDD)

**Files:**
- Create: `dashboard/src/lib/api/client.ts`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write the failing test `dashboard/tests/client.test.ts`**

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getJson, postJson, ApiError } from '../src/lib/api/client';

beforeEach(() => { vi.restoreAllMocks(); });

describe('client', () => {
  it('getJson parses JSON on success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ a: 1 }), { status: 200 }),
    ));
    expect(await getJson<{ a: number }>('/x')).toEqual({ a: 1 });
  });

  it('postJson sends a JSON body', async () => {
    const f = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', f);
    await postJson('/y', { name: 'go' });
    expect(f).toHaveBeenCalledWith('/y', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'go' }),
    }));
  });

  it('throws ApiError on non-2xx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 500 })));
    await expect(getJson('/z')).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd dashboard && npm test -- client`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `dashboard/src/lib/api/client.ts`**

```ts
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status} for ${res.url}`);
  return (await res.json()) as T;
}

export async function getJson<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path));
}

export async function postJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return handle<T>(await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }));
}

export async function putJson<T = unknown>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { method: 'PUT' }));
}
```

- [ ] **Step 4: Run the test — expect pass**

Run: `cd dashboard && npm test -- client`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat(dashboard): typed fetch client with ApiError"
```

### Task 1.4: Define the endpoints module

**Files:**
- Create: `dashboard/src/lib/api/endpoints.ts`
- Test: `dashboard/tests/endpoints.test.ts`

- [ ] **Step 1: Write the failing test `dashboard/tests/endpoints.test.ts`** (verifies each function hits the right URL/method)

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as api from '../src/lib/api/endpoints';

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
});

describe('endpoints', () => {
  it('fetchConfigOverview GETs /get_config_overview', async () => {
    await api.fetchConfigOverview();
    expect(fetchMock).toHaveBeenCalledWith('/get_config_overview');
  });
  it('fetchLogMessages POSTs /get_log_messages with start_idx', async () => {
    await api.fetchLogMessages(5);
    expect(fetchMock).toHaveBeenCalledWith('/get_log_messages', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ start_idx: 5 }),
    }));
  });
  it('shutdown PUTs /shutdown', async () => {
    await api.shutdown();
    expect(fetchMock).toHaveBeenCalledWith('/shutdown', expect.objectContaining({ method: 'PUT' }));
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- endpoints` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/api/endpoints.ts`**

```ts
import { getJson, postJson, putJson } from './client';
import type {
  ResponseLog, ResponseToolNames, ResponseToolStats, ResponseConfigOverview,
  ResponseAvailableLanguages, ResponseGetMemory, ResponseGetSerenaConfig,
  ResponseQueuedExecutions, ResponseLastExecution, ResponseCancelExecution,
  ResponseNews, StatusResponse, TokenEstimatorResponse,
} from './types';

export const fetchConfigOverview = () => getJson<ResponseConfigOverview>('/get_config_overview');
export const fetchLogMessages = (startIdx: number) => postJson<ResponseLog>('/get_log_messages', { start_idx: startIdx });
export const clearLogs = () => postJson<StatusResponse>('/clear_logs');
export const fetchToolNames = () => getJson<ResponseToolNames>('/get_tool_names');
export const fetchToolStats = () => getJson<ResponseToolStats>('/get_tool_stats');
export const clearToolStats = () => postJson<StatusResponse>('/clear_tool_stats');
export const fetchEstimatorName = () => getJson<TokenEstimatorResponse>('/get_token_count_estimator_name');
export const shutdown = () => putJson<StatusResponse>('/shutdown');
export const fetchAvailableLanguages = () => getJson<ResponseAvailableLanguages>('/get_available_languages');
export const addLanguage = (language: string) => postJson<StatusResponse>('/add_language', { language });
export const removeLanguage = (language: string) => postJson<StatusResponse>('/remove_language', { language });
export const getMemory = (memory_name: string) => postJson<ResponseGetMemory>('/get_memory', { memory_name });
export const saveMemory = (memory_name: string, content: string) => postJson<StatusResponse>('/save_memory', { memory_name, content });
export const deleteMemory = (memory_name: string) => postJson<StatusResponse>('/delete_memory', { memory_name });
export const renameMemory = (old_name: string, new_name: string) => postJson<StatusResponse>('/rename_memory', { old_name, new_name });
export const getSerenaConfig = () => getJson<ResponseGetSerenaConfig>('/get_serena_config');
export const saveSerenaConfig = (content: string) => postJson<StatusResponse>('/save_serena_config', { content });
export const fetchQueuedExecutions = () => getJson<ResponseQueuedExecutions>('/queued_task_executions');
export const cancelExecution = (task_id: number) => postJson<ResponseCancelExecution>('/cancel_task_execution', { task_id });
export const fetchLastExecution = () => getJson<ResponseLastExecution>('/last_execution');
export const fetchUnreadNews = () => getJson<ResponseNews>('/fetch_unread_news');
export const markNewsRead = (news_snippet_id: string) => postJson<StatusResponse>('/mark_news_snippet_as_read', { news_snippet_id });
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- endpoints` → PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/api/endpoints.ts dashboard/tests/endpoints.test.ts
git commit -m "feat(dashboard): typed endpoints module for all backend routes"
```

### Task 1.5: Polling utility (TDD)

**Files:**
- Create: `dashboard/src/lib/polling.ts`
- Test: `dashboard/tests/polling.test.ts`

Replaces scattered `setInterval`s. Calls `fn` immediately, then on an interval; `stop()` cancels; overlapping runs are prevented (skip a tick if the previous call is still in flight).

- [ ] **Step 1: Write the failing test `dashboard/tests/polling.test.ts`**

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPoller } from '../src/lib/polling';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('createPoller', () => {
  it('runs immediately and on each interval, and stops', async () => {
    const fn = vi.fn().mockResolvedValue(undefined);
    const poller = createPoller(fn, 1000);
    poller.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(fn).toHaveBeenCalledTimes(2);
    poller.stop();
    await vi.advanceTimersByTimeAsync(2000);
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- polling` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/polling.ts`**

```ts
export interface Poller { start(): void; stop(): void; }

export function createPoller(fn: () => Promise<void> | void, intervalMs: number): Poller {
  let timer: ReturnType<typeof setInterval> | null = null;
  let inFlight = false;

  const tick = async () => {
    if (inFlight) return;
    inFlight = true;
    try { await fn(); } finally { inFlight = false; }
  };

  return {
    start() {
      if (timer) return;
      void tick();
      timer = setInterval(() => void tick(), intervalMs);
    },
    stop() {
      if (timer) { clearInterval(timer); timer = null; }
    },
  };
}
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- polling` → PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/polling.ts dashboard/tests/polling.test.ts
git commit -m "feat(dashboard): reusable poller utility"
```

### Task 1.6: Log formatting utility (TDD)

**Files:**
- Create: `dashboard/src/lib/format.ts`
- Test: `dashboard/tests/format.test.ts`

Ports the legacy `LogMessage` behavior: HTML-escape text, detect level (DEBUG/INFO/WARNING/ERROR), and wrap known tool names in `<span class="tool-name">`.

- [ ] **Step 1: Write the failing test `dashboard/tests/format.test.ts`**

```ts
import { describe, it, expect } from 'vitest';
import { detectLevel, escapeHtml, highlightTools } from '../src/lib/format';

describe('format', () => {
  it('detects log level', () => {
    expect(detectLevel('2026-01-01 INFO something')).toBe('info');
    expect(detectLevel('WARNING watch out')).toBe('warning');
    expect(detectLevel('no level here')).toBe('info');
  });
  it('escapes html', () => {
    expect(escapeHtml('<b>&"')).toBe('&lt;b&gt;&amp;&quot;');
  });
  it('highlights known tool names', () => {
    const html = highlightTools('called find_symbol now', ['find_symbol']);
    expect(html).toContain('<span class="tool-name">find_symbol</span>');
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- format` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/format.ts`**

```ts
export type LogLevel = 'debug' | 'info' | 'warning' | 'error';

export function detectLevel(line: string): LogLevel {
  if (/\bERROR\b/.test(line)) return 'error';
  if (/\bWARNING\b/.test(line)) return 'warning';
  if (/\bDEBUG\b/.test(line)) return 'debug';
  return 'info';
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function highlightTools(text: string, toolNames: string[]): string {
  let html = escapeHtml(text);
  for (const name of toolNames) {
    const re = new RegExp(`\\b${name.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')}\\b`, 'g');
    html = html.replace(re, `<span class="tool-name">${name}</span>`);
  }
  return html;
}
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- format` → PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/format.ts dashboard/tests/format.test.ts
git commit -m "feat(dashboard): log formatting and tool-name highlighting"
```

### Task 1.7: Theme store (TDD)

**Files:**
- Create: `dashboard/src/lib/stores/theme.svelte.ts`
- Test: `dashboard/tests/theme.test.ts`

Reads localStorage (`serena-dashboard-theme`), falls back to `prefers-color-scheme`, writes `data-theme` on `<html>`, persists on toggle.

- [ ] **Step 1: Write the failing test `dashboard/tests/theme.test.ts`**

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { createThemeStore } from '../src/lib/stores/theme.svelte';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('theme store', () => {
  it('persists and applies the theme on toggle', () => {
    const t = createThemeStore();
    t.init();
    const first = t.current;
    t.toggle();
    expect(t.current).not.toBe(first);
    expect(document.documentElement.getAttribute('data-theme')).toBe(t.current);
    expect(localStorage.getItem('serena-dashboard-theme')).toBe(t.current);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- theme` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/stores/theme.svelte.ts`**

```ts
export type Theme = 'light' | 'dark';
const KEY = 'serena-dashboard-theme';

export function createThemeStore() {
  let current = $state<Theme>('light');

  function apply(t: Theme) {
    current = t;
    document.documentElement.setAttribute('data-theme', t);
  }

  return {
    get current() { return current; },
    init() {
      const stored = localStorage.getItem(KEY) as Theme | null;
      const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
      apply(stored ?? (prefersDark ? 'dark' : 'light'));
    },
    toggle() {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      apply(next);
      localStorage.setItem(KEY, next);
    },
  };
}

export const theme = createThemeStore();
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- theme` → PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/stores/theme.svelte.ts dashboard/tests/theme.test.ts
git commit -m "feat(dashboard): theme store with persistence and system fallback"
```

### Task 1.8: Config, logs, executions, stats stores

**Files:**
- Create: `dashboard/src/lib/stores/config.svelte.ts`
- Create: `dashboard/src/lib/stores/logs.svelte.ts`
- Create: `dashboard/src/lib/stores/executions.svelte.ts`
- Create: `dashboard/src/lib/stores/stats.svelte.ts`
- Test: `dashboard/tests/logs-store.test.ts`

The logs store holds the incremental-append + "skip if unchanged" logic, which is the most error-prone, so it gets a test.

- [ ] **Step 1: Write the failing test `dashboard/tests/logs-store.test.ts`**

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createLogsStore } from '../src/lib/stores/logs.svelte';

beforeEach(() => vi.restoreAllMocks());

describe('logs store', () => {
  it('appends only new messages by tracking max_idx', async () => {
    const responses = [
      { messages: ['a', 'b'], max_idx: 2, active_project: 'p' },
      { messages: ['c'], max_idx: 3, active_project: 'p' },
    ];
    let call = 0;
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(responses[call++]), { status: 200 }))));
    const store = createLogsStore();
    await store.poll();
    expect(store.lines).toEqual(['a', 'b']);
    await store.poll();
    expect(store.lines).toEqual(['a', 'b', 'c']);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- logs-store` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/stores/logs.svelte.ts`**

```ts
import { fetchLogMessages, clearLogs as apiClearLogs } from '$lib/api/endpoints';

export function createLogsStore() {
  let lines = $state<string[]>([]);
  let nextIdx = $state(0);
  let activeProject = $state<string | null>(null);

  return {
    get lines() { return lines; },
    get activeProject() { return activeProject; },
    async poll() {
      const res = await fetchLogMessages(nextIdx);
      if (res.messages.length) lines = [...lines, ...res.messages];
      nextIdx = res.max_idx;
      activeProject = res.active_project;
    },
    async clear() {
      await apiClearLogs();
      lines = [];
      nextIdx = 0;
    },
  };
}

export const logs = createLogsStore();
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- logs-store` → PASS.

- [ ] **Step 5: Implement `dashboard/src/lib/stores/config.svelte.ts`** (skip re-render via JSON hash compare)

```ts
import { fetchConfigOverview } from '$lib/api/endpoints';
import type { ResponseConfigOverview } from '$lib/api/types';

export function createConfigStore() {
  let data = $state<ResponseConfigOverview | null>(null);
  let lastJson = '';

  return {
    get data() { return data; },
    async poll() {
      const next = await fetchConfigOverview();
      const json = JSON.stringify(next);
      if (json !== lastJson) { data = next; lastJson = json; }
    },
  };
}

export const config = createConfigStore();
```

- [ ] **Step 6: Implement `dashboard/src/lib/stores/executions.svelte.ts`**

```ts
import { fetchQueuedExecutions, fetchLastExecution, cancelExecution } from '$lib/api/endpoints';
import type { QueuedExecution } from '$lib/api/types';

export function createExecutionsStore() {
  let queued = $state<QueuedExecution[]>([]);
  let last = $state<QueuedExecution | null>(null);

  return {
    get queued() { return queued; },
    get last() { return last; },
    async pollQueued() { queued = (await fetchQueuedExecutions()).queued_executions; },
    async pollLast() { last = (await fetchLastExecution()).last_execution; },
    async cancel(taskId: number) { return cancelExecution(taskId); },
  };
}

export const executions = createExecutionsStore();
```

- [ ] **Step 7: Implement `dashboard/src/lib/stores/stats.svelte.ts`**

```ts
import { fetchToolStats, clearToolStats, fetchEstimatorName } from '$lib/api/endpoints';
import type { ToolStats } from '$lib/api/types';

export function createStatsStore() {
  let stats = $state<ToolStats>({});
  let estimator = $state('unknown');

  return {
    get stats() { return stats; },
    get estimator() { return estimator; },
    async refresh() {
      stats = (await fetchToolStats()).stats;
      estimator = (await fetchEstimatorName()).token_count_estimator_name;
    },
    async clear() { await clearToolStats(); stats = {}; },
  };
}

export const stats = createStatsStore();
```

- [ ] **Step 8: Type-check + test.** Run: `cd dashboard && npm run check && npm test` → 0 errors, all pass.

- [ ] **Step 9: Commit**

```bash
git add dashboard/src/lib/stores dashboard/tests/logs-store.test.ts
git commit -m "feat(dashboard): config, logs, executions, and stats stores"
```

---

## Phase 2 — App shell and common components

### Task 2.1: Common UI primitives

**Files:**
- Create: `dashboard/src/components/common/Spinner.svelte`
- Create: `dashboard/src/components/common/Modal.svelte`
- Create: `dashboard/src/components/common/Collapsible.svelte`
- Create: `dashboard/src/components/common/Combobox.svelte`
- Test: `dashboard/tests/combobox.test.ts`

- [ ] **Step 1: Implement `Spinner.svelte`** (port the 16px rotating spinner; orange top border)

```svelte
<div class="spinner" aria-label="Loading"></div>
<style>
  .spinner {
    width: 16px; height: 16px; border: 2px solid var(--border-strong);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.7s linear infinite; display: inline-block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
```

- [ ] **Step 2: Implement `Modal.svelte`** (backdrop with blur, close on ✕/backdrop/Escape, slot for content). Uses Svelte 5 snippets.

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  let { open = false, title = '', onclose, children }:
    { open?: boolean; title?: string; onclose: () => void; children: Snippet } = $props();

  function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onclose(); }
</script>

<svelte:window on:keydown={onKey} />
{#if open}
  <div class="backdrop" role="presentation" onclick={onclose}>
    <div class="modal-content" role="dialog" aria-modal="true" onclick={(e) => e.stopPropagation()}>
      <span class="modal-close" role="button" tabindex="0" onclick={onclose}>&times;</span>
      {#if title}<h3>{title}</h3>{/if}
      {@render children()}
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(2px); display: flex; align-items: center;
    justify-content: center; z-index: 1000;
  }
  .modal-content {
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: var(--space-6);
    max-width: 600px; width: 90%; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    position: relative;
  }
  .modal-close { position: absolute; top: var(--space-3); right: var(--space-4); cursor: pointer; font-size: 22px; color: var(--text-muted); }
</style>
```

- [ ] **Step 3: Implement `Collapsible.svelte`** (header with rotating ▼ chevron; content toggles).

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  let { title, open = false, children }:
    { title: string; open?: boolean; children: Snippet } = $props();
  let expanded = $state(open);
</script>

<section class="collapsible">
  <h2 class="collapsible-header" role="button" tabindex="0"
      onclick={() => (expanded = !expanded)}>
    <span>{title}</span>
    <span class="toggle-icon" class:open={expanded}>▼</span>
  </h2>
  {#if expanded}<div class="collapsible-content">{@render children()}</div>{/if}
</section>

<style>
  .collapsible-header { display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
  .toggle-icon { transition: transform 0.2s; }
  .toggle-icon.open { transform: rotate(180deg); }
</style>
```

- [ ] **Step 4: Write the failing test `dashboard/tests/combobox.test.ts`** for the combobox filtering behavior

```ts
import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import Combobox from '../src/components/common/Combobox.svelte';

describe('Combobox', () => {
  it('filters options by typed text', async () => {
    const { getByRole, queryByText, getByText } = render(Combobox, {
      props: { options: ['python', 'typescript', 'rust'], value: '', onselect: () => {} },
    });
    await fireEvent.input(getByRole('textbox'), { target: { value: 'ty' } });
    expect(getByText('typescript')).toBeInTheDocument();
    expect(queryByText('rust')).toBeNull();
  });
});
```

- [ ] **Step 5: Run it — expect failure.** Run: `cd dashboard && npm test -- combobox` → FAIL.

- [ ] **Step 6: Implement `Combobox.svelte`**

```svelte
<script lang="ts">
  let { options, value = '', placeholder = 'Type to filter…', onselect }:
    { options: string[]; value?: string; placeholder?: string; onselect: (v: string) => void } = $props();
  let query = $state(value);
  let openList = $state(false);
  const filtered = $derived(options.filter((o) => o.toLowerCase().includes(query.toLowerCase())));

  function choose(o: string) { query = o; openList = false; onselect(o); }
</script>

<div class="combobox">
  <input type="text" role="textbox" {placeholder} bind:value={query}
         onfocus={() => (openList = true)} autocomplete="off" spellcheck="false" />
  <span class="combobox-caret" aria-hidden="true">▾</span>
  {#if openList}
    {#if filtered.length}
      <ul class="combobox-options" role="listbox">
        {#each filtered as o (o)}
          <li role="option" aria-selected={o === query} onclick={() => choose(o)}>{o}</li>
        {/each}
      </ul>
    {:else}
      <div class="combobox-empty">No options available</div>
    {/if}
  {/if}
</div>

<style>
  .combobox { position: relative; }
  input { width: 100%; padding: var(--space-2); border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm); background: var(--bg-card); color: var(--text-primary); font-family: var(--font-sans); }
  .combobox-caret { position: absolute; right: var(--space-2); top: var(--space-2); pointer-events: none; }
  .combobox-options { list-style: none; margin: 0; padding: 0; position: absolute; z-index: 5;
    width: 100%; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); max-height: 200px; overflow: auto; }
  .combobox-options li { padding: var(--space-2); cursor: pointer; }
  .combobox-options li:hover { background: var(--bg-secondary-btn); }
  .combobox-empty { padding: var(--space-2); color: var(--text-muted); }
</style>
```

- [ ] **Step 7: Run the test — expect pass.** Run: `cd dashboard && npm test -- combobox` → PASS.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/components/common dashboard/tests/combobox.test.ts
git commit -m "feat(dashboard): common UI primitives (spinner, modal, collapsible, combobox)"
```

### Task 2.2: Reusable button styles + the app shell

**Files:**
- Create: `dashboard/src/components/common/Button.svelte`
- Create: `dashboard/src/components/shell/Header.svelte`
- Create: `dashboard/src/components/shell/ThemeToggle.svelte`
- Modify: `dashboard/src/App.svelte`

- [ ] **Step 1: Implement `Button.svelte`** (primary orange / secondary gray / disabled, matching legacy `.btn`)

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  let { variant = 'primary', disabled = false, onclick, children }:
    { variant?: 'primary' | 'secondary' | 'danger'; disabled?: boolean; onclick?: () => void; children: Snippet } = $props();
</script>

<button class="btn {variant}" {disabled} onclick={onclick}>{@render children()}</button>

<style>
  .btn { font-family: var(--font-sans); font-weight: 500; border: none; border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-4); cursor: pointer; }
  .primary { background: var(--accent); color: #fff; }
  .primary:hover { background: var(--accent-hover); }
  .secondary { background: var(--bg-secondary-btn); color: var(--text-primary); }
  .danger { background: var(--log-error); color: #fff; }
  .btn:disabled { background: var(--btn-disabled); cursor: not-allowed; }
</style>
```

- [ ] **Step 2: Implement `ThemeToggle.svelte`** (uses the theme store; shows 🌙/☀ + label)

```svelte
<script lang="ts">
  import { theme } from '$lib/stores/theme.svelte';
</script>

<button class="theme-toggle" onclick={() => theme.toggle()}>
  <span style="height:21px">{theme.current === 'dark' ? '☀' : '🌙'}</span>
  <span>{theme.current === 'dark' ? 'Light' : 'Dark'}</span>
</button>

<style>
  .theme-toggle { display: inline-flex; gap: var(--space-2); align-items: center;
    background: var(--bg-secondary-btn); border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: var(--space-2) var(--space-3); cursor: pointer; color: var(--text-primary); }
</style>
```

- [ ] **Step 3: Implement `Header.svelte`** — theme-aware logo (swap `serena-logo.svg`/`serena-logo-dark-mode.svg` based on `theme.current`), platinum banner slot, tab nav (`overview` / `logs`), menu dropdown (`Advanced Stats`, `Shutdown Server`). Props: `active: View`, `onnavigate: (v) => void`, `onshutdown: () => void`; a `BannerCarousel` for platinum banners is wired in Phase 7 (leave a placeholder `<div id="platinum-banners">` for now).

```svelte
<script lang="ts">
  import { theme } from '$lib/stores/theme.svelte';
  import ThemeToggle from './ThemeToggle.svelte';
  type View = 'overview' | 'logs' | 'stats';
  let { active, onnavigate, onshutdown }:
    { active: View; onnavigate: (v: View) => void; onshutdown: () => void } = $props();
  let menuOpen = $state(false);
  const logoSrc = $derived(theme.current === 'dark' ? 'serena-logo-dark-mode.svg' : 'serena-logo.svg');
</script>

<header class="header">
  <div class="header-left">
    <div class="logo-container"><img id="serena-logo" src={logoSrc} alt="Serena" /></div>
    <div id="platinum-banners" class="header-banner"><!-- BannerCarousel mounts here (Phase 7) --></div>
  </div>
  <nav class="header-nav">
    <div class="header-actions">
      <ThemeToggle />
      <button class="menu-button" onclick={() => (menuOpen = !menuOpen)}><span>☰</span><span>Menu</span></button>
      {#if menuOpen}
        <div class="menu-dropdown">
          <a href="#" onclick={() => { onnavigate('stats'); menuOpen = false; }}>Advanced Stats</a>
          <hr />
          <a href="#" onclick={() => { onshutdown(); menuOpen = false; }}>Shutdown Server</a>
        </div>
      {/if}
    </div>
    <div class="header-tabs">
      <a href="#" class="header-tab" class:active={active === 'overview'} onclick={() => onnavigate('overview')}>Overview</a>
      <a href="#" class="header-tab" class:active={active === 'logs'} onclick={() => onnavigate('logs')}>Logs</a>
    </div>
  </nav>
</header>

<style>
  /* Port spacing/borders from legacy .header; full visual match tuned in Phase 8 parity pass. */
  .header { display: flex; justify-content: space-between; align-items: center;
    padding: var(--space-4) var(--space-6); border-bottom: 1px solid var(--border); min-height: 150px; }
  .header-left { display: flex; align-items: center; gap: var(--space-6); }
  #serena-logo { height: 48px; }
  .header-nav { display: flex; flex-direction: column; align-items: flex-end; gap: var(--space-3); }
  .header-actions { position: relative; display: flex; gap: var(--space-2); }
  .menu-button { background: var(--bg-secondary-btn); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: var(--space-2) var(--space-3); cursor: pointer; color: var(--text-primary); }
  .menu-dropdown { position: absolute; right: 0; top: 100%; background: var(--bg-card);
    border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--space-2); min-width: 180px; z-index: 50; }
  .menu-dropdown a { display: block; padding: var(--space-2); text-decoration: none; }
  .header-tabs { display: flex; gap: var(--space-4); }
  .header-tab { text-decoration: none; padding-bottom: var(--space-1); }
  .header-tab.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
</style>
```

- [ ] **Step 4: Rewrite `App.svelte`** — mount header, switch views, run config/executions/logs pollers per active view, own the shutdown confirm modal.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Header from './components/shell/Header.svelte';
  import { theme } from '$lib/stores/theme.svelte';
  import { createPoller } from '$lib/polling';
  import { config } from '$lib/stores/config.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import { logs } from '$lib/stores/logs.svelte';
  // View components are added in Phases 3–6; import them as they land.

  type View = 'overview' | 'logs' | 'stats';
  let view = $state<View>('overview');

  const configPoller = createPoller(() => config.poll(), 1000);
  const queuedPoller = createPoller(() => executions.pollQueued(), 1000);
  const lastPoller = createPoller(() => executions.pollLast(), 1000);
  const logsPoller = createPoller(() => logs.poll(), 1000);

  function startPollers(v: View) {
    configPoller.stop(); queuedPoller.stop(); lastPoller.stop(); logsPoller.stop();
    if (v === 'overview') { configPoller.start(); queuedPoller.start(); lastPoller.start(); }
    if (v === 'logs') { logsPoller.start(); }
  }

  function navigate(v: View) { view = v; startPollers(v); }

  onMount(() => { theme.init(); startPollers('overview'); });
</script>

<div id="frame">
  <Header active={view} onnavigate={navigate} onshutdown={() => { /* ShutdownModal wired in Phase 6 */ }} />
  <div class="main">
    {#if view === 'overview'}<div class="page-view"><!-- OverviewPage (Phase 3) --></div>{/if}
    {#if view === 'logs'}<div class="page-view"><!-- LogsPage (Phase 4) --></div>{/if}
    {#if view === 'stats'}<div class="page-view"><!-- StatsPage (Phase 5) --></div>{/if}
  </div>
</div>

<style>
  .main { max-width: var(--max-width); margin: 0 auto; padding: var(--space-6); }
</style>
```

- [ ] **Step 5: Type-check + dev smoke.** Run: `cd dashboard && npm run check` (0 errors). Then `npm run dev`, open the printed URL, confirm header + theme toggle render and toggling swaps the logo.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src && git commit -m "feat(dashboard): app shell, header, theme toggle, view switching"
```

---

## Phase 3 — Overview page

### Task 3.1: Config card + side panels

**Files:**
- Create: `dashboard/src/components/overview/OverviewPage.svelte`
- Create: `dashboard/src/components/overview/ConfigCard.svelte`
- Create: `dashboard/src/components/overview/ToolUsageBars.svelte`
- Create: `dashboard/src/components/overview/ListPanel.svelte`
- Test: `dashboard/tests/tool-usage-bars.test.ts`

`ListPanel` is a single reusable `Collapsible`-wrapped list used for Registered Projects, Disabled Tools, Available Modes, and Available Contexts (DRY — one component, four usages).

- [ ] **Step 1: Implement `ListPanel.svelte`**

```svelte
<script lang="ts">
  import Collapsible from '../common/Collapsible.svelte';
  let { title, items }: { title: string; items: string[] } = $props();
</script>

<Collapsible {title}>
  {#if items.length}
    <ul class="list-panel">{#each items as item (item)}<li>{item}</li>{/each}</ul>
  {:else}
    <div class="no-stats-message">None.</div>
  {/if}
</Collapsible>

<style>
  .list-panel { list-style: none; margin: 0; padding: 0; }
  .list-panel li { padding: var(--space-1) 0; font-family: var(--font-mono); font-size: 13px; }
  .no-stats-message { color: var(--text-muted); }
</style>
```

- [ ] **Step 2: Write the failing test `dashboard/tests/tool-usage-bars.test.ts`** (bars sorted by call count, descending, with percentages)

```ts
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import ToolUsageBars from '../src/components/overview/ToolUsageBars.svelte';

describe('ToolUsageBars', () => {
  it('renders tools sorted by call count descending', () => {
    const { getAllByTestId } = render(ToolUsageBars, {
      props: { stats: { a: { num_calls: 1 }, b: { num_calls: 5 } } },
    });
    const names = getAllByTestId('tool-bar-name').map((n) => n.textContent);
    expect(names).toEqual(['b', 'a']);
  });
});
```

- [ ] **Step 3: Run it — expect failure.** Run: `cd dashboard && npm test -- tool-usage-bars` → FAIL.

- [ ] **Step 4: Implement `ToolUsageBars.svelte`**

```svelte
<script lang="ts">
  import type { ToolStatsSummary } from '$lib/api/types';
  let { stats }: { stats: ToolStatsSummary } = $props();
  const sorted = $derived(
    Object.entries(stats).sort((a, b) => b[1].num_calls - a[1].num_calls));
  const max = $derived(Math.max(1, ...sorted.map(([, s]) => s.num_calls)));
</script>

{#if sorted.length}
  <div class="bars">
    {#each sorted as [name, s] (name)}
      <div class="bar-row">
        <span class="bar-name" data-testid="tool-bar-name">{name}</span>
        <div class="bar-track"><div class="bar-fill" style="width:{(s.num_calls / max) * 100}%"></div></div>
        <span class="bar-count">{s.num_calls}</span>
      </div>
    {/each}
  </div>
{:else}
  <div class="no-stats-message">No tool usage yet.</div>
{/if}

<style>
  .bar-row { display: grid; grid-template-columns: 1fr 3fr auto; gap: var(--space-2); align-items: center; margin: var(--space-1) 0; }
  .bar-name { font-family: var(--font-mono); font-size: 12px; }
  .bar-track { background: var(--bg-secondary-btn); border-radius: var(--radius-sm); height: 14px; }
  .bar-fill { background: var(--accent); height: 100%; border-radius: var(--radius-sm); }
  .bar-count { font-size: 12px; color: var(--text-muted); }
  .no-stats-message { color: var(--text-muted); }
</style>
```

- [ ] **Step 5: Run the test — expect pass.** Run: `cd dashboard && npm test -- tool-usage-bars` → PASS.

- [ ] **Step 6: Implement `ConfigCard.svelte`** — renders from `ResponseConfigOverview`: project name + language(s), context, active modes, encoding, current client, serena version, language badges with remove buttons (emits `onremovelanguage`), an "Add Language" button (emits `onaddlanguage`), an "Edit Global Serena Config" button (emits `oneditconfig`), and the active-tools + memories collapsible lists. Memory entries emit `onopenmemory(name)`; a "Create Memory" button emits `oncreatememory`. Props are the config object plus those callbacks.

```svelte
<script lang="ts">
  import type { ResponseConfigOverview } from '$lib/api/types';
  import Collapsible from '../common/Collapsible.svelte';
  import Button from '../common/Button.svelte';
  let { data, onaddlanguage, onremovelanguage, oneditconfig, onopenmemory, oncreatememory }: {
    data: ResponseConfigOverview;
    onaddlanguage: () => void;
    onremovelanguage: (lang: string) => void;
    oneditconfig: () => void;
    onopenmemory: (name: string) => void;
    oncreatememory: () => void;
  } = $props();
</script>

<div class="config-display">
  <div class="config-row"><strong>Project:</strong> {data.active_project?.name ?? '—'}</div>
  <div class="config-row"><strong>Context:</strong> {data.context.name ?? '—'}</div>
  <div class="config-row"><strong>Modes:</strong> {data.modes.map((m) => m.name).join(', ') || '—'}</div>
  <div class="config-row"><strong>Encoding:</strong> {data.encoding ?? '—'}</div>
  <div class="config-row"><strong>Client:</strong> {data.current_client ?? '—'}</div>
  <div class="config-row"><strong>Version:</strong> {data.serena_version}</div>

  <div class="config-row">
    <strong>Languages:</strong>
    {#each data.languages as lang (lang)}
      <span class="lang-badge">{lang}
        <button class="lang-remove" aria-label="Remove {lang}" onclick={() => onremovelanguage(lang)}>×</button>
      </span>
    {/each}
    <Button variant="secondary" onclick={onaddlanguage}>Add Language</Button>
  </div>

  <Collapsible title="Active Tools ({data.active_tools.length})">
    <div class="tools-grid">{#each data.active_tools as t (t)}<span class="tool-chip">{t}</span>{/each}</div>
  </Collapsible>

  {#if data.available_memories}
    <Collapsible title="Memories ({data.available_memories.length})">
      <div class="memories-container">
        {#each data.available_memories as m (m)}
          <button class="memory-link" onclick={() => onopenmemory(m)}>{m}</button>
        {/each}
      </div>
      <Button variant="secondary" onclick={oncreatememory}>Create Memory</Button>
    </Collapsible>
  {/if}

  <Button variant="secondary" onclick={oneditconfig}>Edit Global Serena Config</Button>
</div>

<style>
  .config-row { margin: var(--space-2) 0; display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; }
  .lang-badge { background: var(--bg-secondary-btn); border-radius: var(--radius-sm); padding: 2px var(--space-2);
    font-family: var(--font-mono); font-size: 12px; display: inline-flex; align-items: center; gap: 4px; }
  .lang-remove { border: none; background: none; cursor: pointer; color: var(--text-muted); }
  .tools-grid { display: flex; flex-wrap: wrap; gap: var(--space-1); }
  .tool-chip, .memory-link { background: var(--bg-secondary-btn); border-radius: var(--radius-sm);
    padding: 2px var(--space-2); font-family: var(--font-mono); font-size: 12px; border: none; cursor: pointer; }
  .memories-container { display: flex; flex-direction: column; gap: var(--space-1); align-items: flex-start; }
</style>
```

- [ ] **Step 7: Implement `OverviewPage.svelte`** — two-column layout reading `config.data`, `stats`, `executions`; left column = ConfigCard + ToolUsageBars + ExecutionsQueue + LastExecution + NewsSection (Phase 7); right column = the four ListPanels + GoldBanners (Phase 7). Wire modal-open callbacks up to App (Phase 6). Executions sub-components are Task 3.2.

```svelte
<script lang="ts">
  import { config } from '$lib/stores/config.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  import ConfigCard from './ConfigCard.svelte';
  import ToolUsageBars from './ToolUsageBars.svelte';
  import ListPanel from './ListPanel.svelte';
  import ExecutionsQueue from './ExecutionsQueue.svelte';
  import LastExecution from './LastExecution.svelte';
  import Spinner from '../common/Spinner.svelte';
  let { onaddlanguage, onremovelanguage, oneditconfig, onopenmemory, oncreatememory, oncancelexecution }: {
    onaddlanguage: () => void; onremovelanguage: (l: string) => void; oneditconfig: () => void;
    onopenmemory: (n: string) => void; oncreatememory: () => void; oncancelexecution: (id: number) => void;
  } = $props();
  const d = $derived(config.data);
</script>

{#if !d}
  <Spinner />
{:else}
  <div class="overview-container">
    <div class="overview-left">
      <section class="config-section"><h2>Current Configuration</h2>
        <ConfigCard data={d} {onaddlanguage} {onremovelanguage} {oneditconfig} {onopenmemory} {oncreatememory} />
      </section>
      <section><h2>Tool Usage</h2><ToolUsageBars stats={d.tool_stats_summary} /></section>
      <section><h2>Executions Queue</h2><ExecutionsQueue items={executions.queued} {oncancelexecution} /></section>
      <section><h2>Last Execution</h2><LastExecution execution={executions.last} /></section>
    </div>
    <div class="overview-right">
      <ListPanel title="Registered Projects" items={d.registered_projects.map((p) => p.name)} />
      <ListPanel title="Available Tools (Disabled)" items={d.available_tools.map((t) => t.name)} />
      <ListPanel title="Available Modes" items={d.available_modes.map((m) => m.name)} />
      <ListPanel title="Available Contexts" items={d.available_contexts.map((c) => c.name)} />
    </div>
  </div>
{/if}

<style>
  .overview-container { display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-6); }
  @media (max-width: 1000px) { .overview-container { grid-template-columns: 1fr; } }
  section { margin-bottom: var(--space-6); }
</style>
```

- [ ] **Step 8: Wire `OverviewPage` into `App.svelte`** (replace the overview placeholder; pass modal callbacks that get filled in Phase 6 — temporary no-ops for now). Type-check + dev smoke against a running backend: confirm config, languages, tool bars, and lists render.

Run: `cd dashboard && npm run check` → 0 errors.

- [ ] **Step 9: Commit**

```bash
git add dashboard/src && git commit -m "feat(dashboard): overview page — config card, tool bars, list panels"
```

### Task 3.2: Executions queue + last execution

**Files:**
- Create: `dashboard/src/components/overview/ExecutionsQueue.svelte`
- Create: `dashboard/src/components/overview/LastExecution.svelte`
- Test: `dashboard/tests/executions.test.ts`

- [ ] **Step 1: Write the failing test `dashboard/tests/executions.test.ts`**

```ts
import { describe, it, expect, vi } from 'vitest';
import { render, getAllByRole } from '@testing-library/svelte';
import ExecutionsQueue from '../src/components/overview/ExecutionsQueue.svelte';

describe('ExecutionsQueue', () => {
  it('shows a cancel button only for running items', () => {
    const { container } = render(ExecutionsQueue, {
      props: {
        items: [
          { task_id: 1, is_running: true, name: 'run', finished_successfully: false, logged: false },
          { task_id: 2, is_running: false, name: 'queued', finished_successfully: false, logged: false },
        ],
        oncancelexecution: vi.fn(),
      },
    });
    expect(getAllByRole(container, 'button').length).toBe(1);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- executions` → FAIL.

- [ ] **Step 3: Implement `ExecutionsQueue.svelte`** (pills; running ones get a spinner + cancel button)

```svelte
<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  import Spinner from '../common/Spinner.svelte';
  let { items, oncancelexecution }:
    { items: QueuedExecution[]; oncancelexecution: (id: number) => void } = $props();
</script>

{#if items.length}
  <div class="executions">
    {#each items as ex (ex.task_id)}
      <div class="execution-item" class:running={ex.is_running}>
        {#if ex.is_running}<Spinner />{/if}
        <span class="execution-name">{ex.name}</span>
        {#if ex.is_running}
          <button class="cancel-btn" aria-label="Cancel" onclick={() => oncancelexecution(ex.task_id)}>×</button>
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <div class="no-stats-message">No queued executions.</div>
{/if}

<style>
  .execution-item { display: inline-flex; align-items: center; gap: var(--space-2);
    border: 1px solid var(--border); border-radius: 999px; padding: var(--space-1) var(--space-3); margin: 2px; }
  .execution-item.running { border-color: var(--accent); }
  .execution-name { font-family: var(--font-mono); font-size: 12px; }
  .cancel-btn { border: none; background: none; cursor: pointer; color: var(--text-muted); }
  .no-stats-message { color: var(--text-muted); }
</style>
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- executions` → PASS.

- [ ] **Step 5: Implement `LastExecution.svelte`** (success/failure status; "None yet." when null)

```svelte
<script lang="ts">
  import type { QueuedExecution } from '$lib/api/types';
  let { execution }: { execution: QueuedExecution | null } = $props();
</script>

{#if execution}
  <div class="last-exec" class:ok={execution.finished_successfully} class:fail={!execution.finished_successfully && !execution.is_running}>
    <span class="execution-name">{execution.name}</span>
    <span class="status">{execution.is_running ? 'running' : execution.finished_successfully ? '✓ success' : '✗ failed'}</span>
  </div>
{:else}
  <div class="no-stats-message">None yet.</div>
{/if}

<style>
  .last-exec { display: flex; gap: var(--space-3); align-items: center; }
  .ok .status { color: var(--success); }
  .fail .status { color: var(--log-error); }
  .execution-name { font-family: var(--font-mono); font-size: 12px; }
  .no-stats-message { color: var(--text-muted); }
</style>
```

- [ ] **Step 6: Type-check.** Run: `cd dashboard && npm run check` → 0 errors.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src dashboard/tests/executions.test.ts
git commit -m "feat(dashboard): executions queue and last-execution panels"
```

---

## Phase 4 — Logs page

### Task 4.1: Log viewer + toolbar

**Files:**
- Create: `dashboard/src/components/logs/LogsPage.svelte`
- Create: `dashboard/src/components/logs/LogViewer.svelte`
- Create: `dashboard/src/components/logs/LogToolbar.svelte`
- Test: `dashboard/tests/log-viewer.test.ts`

- [ ] **Step 1: Write the failing test `dashboard/tests/log-viewer.test.ts`** (renders one styled line per message, level class applied)

```ts
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import LogViewer from '../src/components/logs/LogViewer.svelte';

describe('LogViewer', () => {
  it('renders a line per message with a level class', () => {
    const { container } = render(LogViewer, {
      props: { lines: ['INFO hello', 'ERROR boom'], toolNames: [] },
    });
    const rows = container.querySelectorAll('.log-line');
    expect(rows.length).toBe(2);
    expect(rows[1].classList.contains('error')).toBe(true);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- log-viewer` → FAIL.

- [ ] **Step 3: Implement `LogViewer.svelte`** (auto-scroll to bottom if user was already at bottom; uses `format.ts`)

```svelte
<script lang="ts">
  import { detectLevel, highlightTools } from '$lib/format';
  let { lines, toolNames }: { lines: string[]; toolNames: string[] } = $props();
  let el = $state<HTMLDivElement | null>(null);

  $effect(() => {
    void lines.length; // re-run when new lines arrive
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom) queueMicrotask(() => { if (el) el.scrollTop = el.scrollHeight; });
  });
</script>

<div bind:this={el} class="log-container">
  {#each lines as line, i (i)}
    <div class="log-line {detectLevel(line)}">{@html highlightTools(line, toolNames)}</div>
  {/each}
</div>

<style>
  .log-container { height: calc(100vh - 220px); overflow: auto; font-family: var(--font-mono);
    font-size: 12px; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--space-3); }
  .log-line { white-space: pre-wrap; }
  .debug { color: var(--log-debug); }
  .info { color: var(--log-info); }
  .warning { color: var(--log-warning); }
  .error { color: var(--log-error); }
  :global(.log-line .tool-name) { color: var(--accent); font-weight: 500; }
</style>
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- log-viewer` → PASS.

- [ ] **Step 5: Implement `LogToolbar.svelte`** — copy / save / clear buttons (the legacy SVG icons), disabled when there are no lines. Copy uses `navigator.clipboard.writeText`; save triggers a Blob download (`serena-logs.txt`); clear calls `logs.clear()`. Each action shows a transient ✓ for ~1s. Props: `lines: string[]`, `onclear: () => void`.

```svelte
<script lang="ts">
  let { lines, onclear }: { lines: string[]; onclear: () => void } = $props();
  let copied = $state(false);
  const disabled = $derived(lines.length === 0);

  async function copy() {
    await navigator.clipboard.writeText(lines.join('\n'));
    copied = true; setTimeout(() => (copied = false), 1000);
  }
  function save() {
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'serena-logs.txt'; a.click();
    URL.revokeObjectURL(a.href);
  }
</script>

<div class="log-action-buttons">
  <button class="log-action-btn" {disabled} onclick={copy} title="Copy logs">{copied ? '✓ copied' : 'copy logs'}</button>
  <button class="log-action-btn" {disabled} onclick={save} title="Save logs to file">save logs</button>
  <button class="log-action-btn danger" {disabled} onclick={onclear} title="Clear logs">clear logs</button>
</div>

<style>
  .log-action-buttons { display: flex; gap: var(--space-2); justify-content: flex-end; margin-bottom: var(--space-2); }
  .log-action-btn { background: var(--bg-secondary-btn); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: var(--space-1) var(--space-3); cursor: pointer; color: var(--text-primary); }
  .log-action-btn:disabled { color: var(--btn-disabled); cursor: not-allowed; }
  .danger:not(:disabled) { color: var(--log-error); }
</style>
```

- [ ] **Step 6: Implement `LogsPage.svelte`** — loads tool names once on mount (for highlighting), renders `LogToolbar` + `LogViewer` from the `logs` store.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { logs } from '$lib/stores/logs.svelte';
  import { fetchToolNames } from '$lib/api/endpoints';
  import LogToolbar from './LogToolbar.svelte';
  import LogViewer from './LogViewer.svelte';
  let toolNames = $state<string[]>([]);
  onMount(async () => { toolNames = (await fetchToolNames()).tool_names; });
</script>

<LogToolbar lines={logs.lines} onclear={() => logs.clear()} />
<LogViewer lines={logs.lines} {toolNames} />
```

- [ ] **Step 7: Wire `LogsPage` into `App.svelte`** (replace the logs placeholder). Type-check + dev smoke: switch to Logs tab, confirm live log streaming, copy/save/clear.

Run: `cd dashboard && npm run check` → 0 errors.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src dashboard/tests/log-viewer.test.ts
git commit -m "feat(dashboard): logs page with live viewer and toolbar"
```

---

## Phase 5 — Advanced stats page (Frappe Charts)

### Task 5.1: Chart wrapper + stats page

**Files:**
- Create: `dashboard/src/components/stats/ChartPanel.svelte`
- Create: `dashboard/src/components/stats/StatsPage.svelte`
- Create: `dashboard/src/components/stats/StatsSummary.svelte`
- Create: `dashboard/src/lib/charts.ts`
- Test: `dashboard/tests/charts.test.ts`

`charts.ts` transforms `ToolStats` into Frappe Charts data structures (pure functions → unit-testable). `ChartPanel.svelte` is the only place that imports `frappe-charts`.

- [ ] **Step 1: Write the failing test `dashboard/tests/charts.test.ts`**

```ts
import { describe, it, expect } from 'vitest';
import { toPieData, toGroupedBarData } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  a: { num_times_called: 2, input_tokens: 10, output_tokens: 5 },
  b: { num_times_called: 8, input_tokens: 40, output_tokens: 20 },
};

describe('charts data', () => {
  it('builds pie data for a chosen metric, sorted descending', () => {
    const pie = toPieData(stats, 'num_times_called');
    expect(pie.labels).toEqual(['b', 'a']);
    expect(pie.datasets[0].values).toEqual([8, 2]);
  });
  it('builds grouped bar data with input and output series', () => {
    const bar = toGroupedBarData(stats);
    expect(bar.labels).toEqual(['b', 'a']);
    expect(bar.datasets.map((d) => d.name)).toEqual(['Input Tokens', 'Output Tokens']);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- charts` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/charts.ts`**

```ts
import type { ToolStats, ToolStatEntry } from './api/types';

export interface FrappeData {
  labels: string[];
  datasets: Array<{ name?: string; values: number[] }>;
}

function sortedEntries(stats: ToolStats, key: keyof ToolStatEntry): Array<[string, ToolStatEntry]> {
  return Object.entries(stats).sort((a, b) => b[1][key] - a[1][key]);
}

export function toPieData(stats: ToolStats, key: keyof ToolStatEntry): FrappeData {
  const entries = sortedEntries(stats, key);
  return { labels: entries.map(([n]) => n), datasets: [{ values: entries.map(([, s]) => s[key]) }] };
}

export function toGroupedBarData(stats: ToolStats): FrappeData {
  const entries = sortedEntries(stats, 'input_tokens');
  return {
    labels: entries.map(([n]) => n),
    datasets: [
      { name: 'Input Tokens', values: entries.map(([, s]) => s.input_tokens) },
      { name: 'Output Tokens', values: entries.map(([, s]) => s.output_tokens) },
    ],
  };
}
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- charts` → PASS.

- [ ] **Step 5: Implement `ChartPanel.svelte`** — wraps Frappe Charts; re-creates the chart when `data`, `type`, or theme changes; pulls colors from CSS variables so charts re-theme on toggle.

```svelte
<script lang="ts">
  import { onDestroy } from 'svelte';
  import { Chart } from 'frappe-charts';
  import 'frappe-charts/dist/frappe-charts.min.css';
  import type { FrappeData } from '$lib/charts';
  import { theme } from '$lib/stores/theme.svelte';

  let { title, data, type }:
    { title: string; data: FrappeData; type: 'pie' | 'percentage' | 'bar' } = $props();
  let el = $state<HTMLDivElement | null>(null);
  let chart: Chart | null = null;

  function accent(): string {
    return getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#eaa45d';
  }

  $effect(() => {
    void theme.current; void data; // re-render on theme or data change
    if (!el) return;
    el.innerHTML = '';
    chart = new Chart(el, {
      title, data, type,
      height: type === 'bar' ? 240 : 220,
      colors: [accent(), '#6aa3d8', '#7fb77e', '#d88c8c', '#b39ddb', '#e0a458'],
    });
  });

  onDestroy(() => { chart = null; });
</script>

<div class="chart-group"><h3>{title}</h3><div bind:this={el}></div></div>

<style>
  .chart-group { background: var(--bg-card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: var(--space-4); }
</style>
```

- [ ] **Step 6: Implement `StatsSummary.svelte`** — totals table (sum of calls, input tokens, output tokens across tools) from `ToolStats`.

```svelte
<script lang="ts">
  import type { ToolStats } from '$lib/api/types';
  let { stats }: { stats: ToolStats } = $props();
  const totals = $derived(Object.values(stats).reduce(
    (acc, s) => ({
      calls: acc.calls + s.num_times_called,
      input: acc.input + s.input_tokens,
      output: acc.output + s.output_tokens,
    }), { calls: 0, input: 0, output: 0 }));
</script>

<table class="stats-summary-block">
  <tbody>
    <tr><td>Total calls</td><td>{totals.calls}</td></tr>
    <tr><td>Total input tokens</td><td>{totals.input}</td></tr>
    <tr><td>Total output tokens</td><td>{totals.output}</td></tr>
  </tbody>
</table>

<style>
  table { width: 100%; border-collapse: collapse; }
  td { padding: var(--space-2); border-bottom: 1px solid var(--border); font-family: var(--font-mono); }
</style>
```

- [ ] **Step 7: Implement `StatsPage.svelte`** — Refresh/Clear buttons, summary, estimator name, "No stats" message, and the four charts (3 pie + 1 grouped bar) driven by the `stats` store + `charts.ts`. Loads on mount.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { stats } from '$lib/stores/stats.svelte';
  import { toPieData, toGroupedBarData } from '$lib/charts';
  import ChartPanel from './ChartPanel.svelte';
  import StatsSummary from './StatsSummary.svelte';
  import Button from '../common/Button.svelte';
  const hasStats = $derived(Object.keys(stats.stats).length > 0);
  onMount(() => stats.refresh());
</script>

<div class="controls">
  <Button onclick={() => stats.refresh()}>Refresh Stats</Button>
  <Button onclick={() => stats.clear()}>Clear Stats</Button>
</div>

{#if hasStats}
  <StatsSummary stats={stats.stats} />
  <div class="estimator-name">Token estimator: {stats.estimator}</div>
  <div class="charts-container">
    <ChartPanel title="Tool Calls" type="pie" data={toPieData(stats.stats, 'num_times_called')} />
    <ChartPanel title="Input Tokens" type="pie" data={toPieData(stats.stats, 'input_tokens')} />
    <ChartPanel title="Output Tokens" type="pie" data={toPieData(stats.stats, 'output_tokens')} />
    <ChartPanel title="Input vs Output Tokens" type="bar" data={toGroupedBarData(stats.stats)} />
  </div>
{:else}
  <div class="no-stats-message">No tool stats collected yet.</div>
{/if}

<style>
  .controls { display: flex; gap: var(--space-3); margin-bottom: var(--space-4); }
  .charts-container { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-4); margin-top: var(--space-4); }
  .charts-container :global(.chart-group:last-child) { grid-column: 1 / -1; }
  .estimator-name { color: var(--text-muted); margin: var(--space-2) 0; }
  .no-stats-message { color: var(--text-muted); }
</style>
```

- [ ] **Step 8: Wire `StatsPage` into `App.svelte`** (replace the stats placeholder). Type-check; dev smoke: open Advanced Stats from the menu, confirm charts render in both themes after triggering some tool usage.

Run: `cd dashboard && npm run check` → 0 errors.

- [ ] **Step 9: Commit**

```bash
git add dashboard/src dashboard/tests/charts.test.ts
git commit -m "feat(dashboard): advanced stats page with Frappe Charts"
```

---

## Phase 6 — Modals and mutations

### Task 6.1: Modal store + shutdown + cancel-execution modals

**Files:**
- Create: `dashboard/src/lib/stores/modal.svelte.ts`
- Create: `dashboard/src/components/modals/ShutdownModal.svelte`
- Create: `dashboard/src/components/modals/CancelExecutionModal.svelte`
- Test: `dashboard/tests/modal-store.test.ts`

The modal store holds a single discriminated-union "active modal" value, so only one modal renders at a time.

- [ ] **Step 1: Write the failing test `dashboard/tests/modal-store.test.ts`**

```ts
import { describe, it, expect } from 'vitest';
import { createModalStore } from '../src/lib/stores/modal.svelte';

describe('modal store', () => {
  it('opens and closes a single active modal', () => {
    const m = createModalStore();
    expect(m.active).toBeNull();
    m.open({ kind: 'shutdown' });
    expect(m.active?.kind).toBe('shutdown');
    m.close();
    expect(m.active).toBeNull();
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- modal-store` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/stores/modal.svelte.ts`**

```ts
export type ModalState =
  | { kind: 'shutdown' }
  | { kind: 'cancelExecution'; taskId: number }
  | { kind: 'addLanguage' }
  | { kind: 'removeLanguage'; language: string }
  | { kind: 'editMemory'; name: string }
  | { kind: 'deleteMemory'; name: string }
  | { kind: 'createMemory' }
  | { kind: 'editSerenaConfig' };

export function createModalStore() {
  let active = $state<ModalState | null>(null);
  return {
    get active() { return active; },
    open(s: ModalState) { active = s; },
    close() { active = null; },
  };
}

export const modal = createModalStore();
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- modal-store` → PASS.

- [ ] **Step 5: Implement `ShutdownModal.svelte`** (confirm → `shutdown()` → close window after 1s)

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { shutdown } from '$lib/api/endpoints';
  let { onclose }: { onclose: () => void } = $props();
  async function confirm() {
    await shutdown();
    setTimeout(() => window.close(), 1000);
    onclose();
  }
</script>

<Modal open={true} title="Shutdown Server" {onclose}>
  <p class="modal-prompt">Shut down the Serena server?</p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button variant="danger" onclick={confirm}>Shutdown</Button>
  </div>
</Modal>

<style>
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 6: Implement `CancelExecutionModal.svelte`** (the legacy warning text; confirm → `executions.cancel(taskId)`)

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { executions } from '$lib/stores/executions.svelte';
  let { taskId, onclose }: { taskId: number; onclose: () => void } = $props();
  async function confirm() { await executions.cancel(taskId); onclose(); }
</script>

<Modal open={true} {onclose}>
  <p class="modal-prompt">Are you sure? The execution will continue running until timeout, it will simply no
    longer be in the queue. Abandoning a running execution is only advised as a measure for unblocking Serena.</p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button onclick={confirm}>OK</Button>
  </div>
</Modal>

<style>
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 7: Commit**

```bash
git add dashboard/src dashboard/tests/modal-store.test.ts
git commit -m "feat(dashboard): modal store, shutdown and cancel-execution modals"
```

### Task 6.2: Language modals

**Files:**
- Create: `dashboard/src/components/modals/AddLanguageModal.svelte`
- Create: `dashboard/src/components/modals/RemoveLanguageModal.svelte`

- [ ] **Step 1: Implement `AddLanguageModal.svelte`** — loads `fetchAvailableLanguages()` on mount into a `Combobox`; on Add, shows a `Spinner`, calls `addLanguage(selected)`, then closes and lets the config poller refresh. Shows the legacy hint about language-server download time and the project name.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Combobox from '../common/Combobox.svelte';
  import Button from '../common/Button.svelte';
  import Spinner from '../common/Spinner.svelte';
  import { fetchAvailableLanguages, addLanguage } from '$lib/api/endpoints';
  let { projectName, onclose }: { projectName: string; onclose: () => void } = $props();
  let options = $state<string[]>([]);
  let selected = $state('');
  let busy = $state(false);
  let error = $state('');
  onMount(async () => { options = (await fetchAvailableLanguages()).languages; });
  async function add() {
    if (!selected) return;
    busy = true; error = '';
    const res = await addLanguage(selected);
    busy = false;
    if (res.status === 'error') { error = res.message ?? 'Failed'; return; }
    onclose();
  }
</script>

<Modal open={true} title="Add Language" {onclose}>
  <p class="modal-info">Adding a language to serena config of project <strong>{projectName}</strong>.</p>
  <p class="modal-hint">Note that this may download dependencies for the language server and then start it;
    it may take a few seconds before the LS is responsive.</p>
  <Combobox {options} value={selected} onselect={(v) => (selected = v)} />
  {#if error}<p class="error">{error}</p>{/if}
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={busy || !selected} onclick={add}>{#if busy}<Spinner />{:else}Add Language{/if}</Button>
  </div>
</Modal>

<style>
  .modal-info { color: var(--text-secondary); }
  .modal-hint { color: var(--text-muted); font-size: 13px; }
  .error { color: var(--log-error); }
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 2: Implement `RemoveLanguageModal.svelte`** — confirm dialog; calls `removeLanguage(language)`.

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { removeLanguage } from '$lib/api/endpoints';
  let { language, onclose }: { language: string; onclose: () => void } = $props();
  async function confirm() { await removeLanguage(language); onclose(); }
</script>

<Modal open={true} {onclose}>
  <p class="modal-prompt">Remove language <strong>{language}</strong> from configuration?</p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button onclick={confirm}>OK</Button>
  </div>
</Modal>

<style>
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 3: Type-check + commit**

Run: `cd dashboard && npm run check` → 0 errors.
```bash
git add dashboard/src && git commit -m "feat(dashboard): add/remove language modals"
```

### Task 6.3: Memory modals + name validation (TDD)

**Files:**
- Create: `dashboard/src/lib/validation.ts`
- Create: `dashboard/src/components/modals/EditMemoryModal.svelte`
- Create: `dashboard/src/components/modals/CreateMemoryModal.svelte`
- Create: `dashboard/src/components/modals/DeleteMemoryModal.svelte`
- Test: `dashboard/tests/validation.test.ts`

- [ ] **Step 1: Write the failing test `dashboard/tests/validation.test.ts`** (legacy rule: alphanumeric, underscores, slashes for paths)

```ts
import { describe, it, expect } from 'vitest';
import { isValidMemoryName } from '../src/lib/validation';

describe('memory name validation', () => {
  it('accepts names with letters, digits, underscores, and slashes', () => {
    expect(isValidMemoryName('architecture/api_design')).toBe(true);
    expect(isValidMemoryName('global/java/style_guide')).toBe(true);
  });
  it('rejects spaces and other punctuation', () => {
    expect(isValidMemoryName('bad name')).toBe(false);
    expect(isValidMemoryName('weird!')).toBe(false);
    expect(isValidMemoryName('')).toBe(false);
  });
});
```

- [ ] **Step 2: Run it — expect failure.** Run: `cd dashboard && npm test -- validation` → FAIL.

- [ ] **Step 3: Implement `dashboard/src/lib/validation.ts`**

```ts
export function isValidMemoryName(name: string): boolean {
  return /^[A-Za-z0-9_]+(\/[A-Za-z0-9_]+)*$/.test(name);
}
```

- [ ] **Step 4: Run the test — expect pass.** Run: `cd dashboard && npm test -- validation` → PASS.

- [ ] **Step 5: Implement `EditMemoryModal.svelte`** — loads `getMemory(name)`, large textarea, dirty tracking, inline rename (✎ → input; on save uses `renameMemory(old, new)`), Save uses `saveMemory(name, content)`. Closes on save.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getMemory, saveMemory, renameMemory } from '$lib/api/endpoints';
  import { isValidMemoryName } from '$lib/validation';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
  let currentName = $state(name);
  let content = $state('');
  let renaming = $state(false);
  let renameValue = $state(name);
  onMount(async () => { content = (await getMemory(name)).content; });

  async function save() { await saveMemory(currentName, content); onclose(); }
  async function applyRename() {
    if (!isValidMemoryName(renameValue) || renameValue === currentName) { renaming = false; return; }
    await renameMemory(currentName, renameValue);
    currentName = renameValue; renaming = false;
  }
</script>

<Modal open={true} {onclose}>
  <h3 class="modal-title-with-meta">Memory:
    {#if renaming}
      <input class="memory-rename-input" bind:value={renameValue} />
      <button onclick={applyRename}>✓</button>
    {:else}
      <span class="memory-name-display">{currentName}</span>
      <span role="button" tabindex="0" title="Rename memory" onclick={() => { renaming = true; renameValue = currentName; }}>✎</span>
    {/if}
  </h3>
  <textarea class="memory-editor modal-textarea" rows="20" bind:value={content}></textarea>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button onclick={save}>Save</Button>
  </div>
</Modal>

<style>
  .modal-textarea { width: 100%; font-family: var(--font-mono); font-size: 13px;
    background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: var(--space-3); }
  .memory-name-display { font-family: var(--font-mono); }
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 6: Implement `CreateMemoryModal.svelte`** — name input with the legacy hint; validates with `isValidMemoryName`; on Create calls `saveMemory(name, '')` then transitions to editing (emits `oncreated(name)` so App opens the edit modal).

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { saveMemory } from '$lib/api/endpoints';
  import { isValidMemoryName } from '$lib/validation';
  let { projectName, onclose, oncreated }:
    { projectName: string; onclose: () => void; oncreated: (name: string) => void } = $props();
  let name = $state('');
  const valid = $derived(isValidMemoryName(name));
  async function create() { if (!valid) return; await saveMemory(name, ''); oncreated(name); }
</script>

<Modal open={true} {onclose}>
  <p class="modal-info">Create a new memory for project <strong>{projectName}</strong>.</p>
  <p class="modal-hint">Use underscores instead of spaces (e.g. "api_architecture"). Use "/" for
    subdirectories (e.g. "architecture/api_design"); use the "global/" prefix for cross-project memories.</p>
  <input class="modal-input" placeholder="e.g., project_overview or topic/memory_name" bind:value={name} />
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button disabled={!valid} onclick={create}>Create</Button>
  </div>
</Modal>

<style>
  .modal-info { color: var(--text-secondary); }
  .modal-hint { color: var(--text-muted); font-size: 13px; }
  .modal-input { width: 100%; padding: var(--space-2); border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm); background: var(--bg-card); color: var(--text-primary); }
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 7: Implement `DeleteMemoryModal.svelte`** — confirm; calls `deleteMemory(name)`.

```svelte
<script lang="ts">
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { deleteMemory } from '$lib/api/endpoints';
  let { name, onclose }: { name: string; onclose: () => void } = $props();
  async function confirm() { await deleteMemory(name); onclose(); }
</script>

<Modal open={true} {onclose}>
  <p class="modal-prompt">Delete memory <strong>{name}</strong>?</p>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button variant="danger" onclick={confirm}>OK</Button>
  </div>
</Modal>

<style>
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 8: Type-check + commit**

Run: `cd dashboard && npm run check` → 0 errors.
```bash
git add dashboard/src dashboard/tests/validation.test.ts
git commit -m "feat(dashboard): memory edit/create/delete modals with name validation"
```

### Task 6.4: Serena config modal + wire all modals into App

**Files:**
- Create: `dashboard/src/components/modals/EditSerenaConfigModal.svelte`
- Create: `dashboard/src/components/modals/ModalHost.svelte`
- Modify: `dashboard/src/App.svelte`

- [ ] **Step 1: Implement `EditSerenaConfigModal.svelte`** — loads `getSerenaConfig()`, textarea, the legacy "changes take effect after restart" hint, Save → `saveSerenaConfig(content)`.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import Modal from '../common/Modal.svelte';
  import Button from '../common/Button.svelte';
  import { getSerenaConfig, saveSerenaConfig } from '$lib/api/endpoints';
  let { onclose }: { onclose: () => void } = $props();
  let content = $state('');
  onMount(async () => { content = (await getSerenaConfig()).content; });
  async function save() { await saveSerenaConfig(content); onclose(); }
</script>

<Modal open={true} title="Global Serena Configuration" {onclose}>
  <p class="modal-hint">Note: Changes to the configuration only take effect after Serena is restarted.</p>
  <textarea class="modal-textarea" rows="20" bind:value={content}></textarea>
  <div class="modal-actions">
    <Button variant="secondary" onclick={onclose}>Cancel</Button>
    <Button onclick={save}>Save</Button>
  </div>
</Modal>

<style>
  .modal-hint { color: var(--text-muted); font-size: 13px; }
  .modal-textarea { width: 100%; font-family: var(--font-mono); font-size: 13px;
    background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: var(--space-3); }
  .modal-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-4); }
</style>
```

- [ ] **Step 2: Implement `ModalHost.svelte`** — renders the active modal based on `modal.active.kind`, passing the right props and `onclose={() => modal.close()}`. Reads `config.data` for the active project name where needed. For `createMemory`, on `oncreated(name)` it switches the modal to `editMemory`.

```svelte
<script lang="ts">
  import { modal } from '$lib/stores/modal.svelte';
  import { config } from '$lib/stores/config.svelte';
  import ShutdownModal from './ShutdownModal.svelte';
  import CancelExecutionModal from './CancelExecutionModal.svelte';
  import AddLanguageModal from './AddLanguageModal.svelte';
  import RemoveLanguageModal from './RemoveLanguageModal.svelte';
  import EditMemoryModal from './EditMemoryModal.svelte';
  import CreateMemoryModal from './CreateMemoryModal.svelte';
  import DeleteMemoryModal from './DeleteMemoryModal.svelte';
  import EditSerenaConfigModal from './EditSerenaConfigModal.svelte';
  const projectName = $derived(String(config.data?.active_project.name ?? ''));
  const close = () => modal.close();
</script>

{#if modal.active}
  {#if modal.active.kind === 'shutdown'}<ShutdownModal onclose={close} />
  {:else if modal.active.kind === 'cancelExecution'}<CancelExecutionModal taskId={modal.active.taskId} onclose={close} />
  {:else if modal.active.kind === 'addLanguage'}<AddLanguageModal {projectName} onclose={close} />
  {:else if modal.active.kind === 'removeLanguage'}<RemoveLanguageModal language={modal.active.language} onclose={close} />
  {:else if modal.active.kind === 'editMemory'}<EditMemoryModal name={modal.active.name} onclose={close} />
  {:else if modal.active.kind === 'createMemory'}
    <CreateMemoryModal {projectName} onclose={close} oncreated={(name) => modal.open({ kind: 'editMemory', name })} />
  {:else if modal.active.kind === 'deleteMemory'}<DeleteMemoryModal name={modal.active.name} onclose={close} />
  {:else if modal.active.kind === 'editSerenaConfig'}<EditSerenaConfigModal onclose={close} />
  {/if}
{/if}
```

- [ ] **Step 3: Modify `App.svelte`** — mount `<ModalHost />`; replace the temporary no-op callbacks so `Header` shutdown → `modal.open({ kind: 'shutdown' })`, and `OverviewPage` callbacks open the matching modals (`addLanguage`, `removeLanguage`, `editSerenaConfig`, `editMemory`, `createMemory`, `cancelExecution`). Remove the placeholder onshutdown comment.

```svelte
<!-- inside <script>: -->
<!-- import ModalHost from './components/modals/ModalHost.svelte'; -->
<!-- import { modal } from '$lib/stores/modal.svelte'; -->
<!-- Header: onshutdown={() => modal.open({ kind: 'shutdown' })} -->
<!-- OverviewPage props:
  onaddlanguage={() => modal.open({ kind: 'addLanguage' })}
  onremovelanguage={(language) => modal.open({ kind: 'removeLanguage', language })}
  oneditconfig={() => modal.open({ kind: 'editSerenaConfig' })}
  onopenmemory={(name) => modal.open({ kind: 'editMemory', name })}
  oncreatememory={() => modal.open({ kind: 'createMemory' })}
  oncancelexecution={(taskId) => modal.open({ kind: 'cancelExecution', taskId })}
-->
<!-- after </div> of #frame: <ModalHost /> -->
```

- [ ] **Step 4: Type-check + dev smoke.** Run: `cd dashboard && npm run check` (0 errors). In `npm run dev`: open each modal, exercise add/remove language, create/edit/delete/rename memory, edit serena config, cancel execution, shutdown confirm.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src && git commit -m "feat(dashboard): serena-config modal and full modal wiring"
```

---

## Phase 7 — Banners and news

### Task 7.1: Banner carousel

**Files:**
- Create: `dashboard/src/components/banners/BannerCarousel.svelte`
- Create: `dashboard/src/lib/banners.ts`
- Test: `dashboard/tests/banners.test.ts`

`banners.ts` parses the remote manifest and picks the light/dark variant; it is pure and testable. `BannerCarousel` renders the image + prev/next arrows, random initial index, auto-rotation disabled by default — matching the legacy `BannerRotation`.

- [ ] **Step 1: Inspect the legacy manifest handling** in the old `src/serena/resources/dashboard/dashboard.js` (`BannerRotation`, lines ~62–240) to copy the exact manifest URL (`https://oraios-software.de/serena-banners/manifest.php`), the JSON shape (entries with light/dark image URLs + link), and the "platinum" vs "gold" target filtering. Record the field names you find before writing `banners.ts`.

- [ ] **Step 2: Write the failing test `dashboard/tests/banners.test.ts`** (uses the field names confirmed in Step 1; example assumes `{ images: [{ target, light, dark, url }] }`)

```ts
import { describe, it, expect } from 'vitest';
import { selectBanners, pickVariant } from '../src/lib/banners';

const manifest = { images: [
  { target: 'platinum', light: 'p-l.png', dark: 'p-d.png', url: 'https://a' },
  { target: 'gold', light: 'g-l.png', dark: 'g-d.png', url: 'https://b' },
] };

describe('banners', () => {
  it('filters by target', () => {
    expect(selectBanners(manifest, 'gold')).toHaveLength(1);
    expect(selectBanners(manifest, 'platinum')[0].url).toBe('https://a');
  });
  it('picks the variant for the theme', () => {
    const b = selectBanners(manifest, 'platinum')[0];
    expect(pickVariant(b, 'dark')).toBe('p-d.png');
    expect(pickVariant(b, 'light')).toBe('p-l.png');
  });
});
```

- [ ] **Step 3: Run it — expect failure.** Run: `cd dashboard && npm test -- banners` → FAIL.

- [ ] **Step 4: Implement `dashboard/src/lib/banners.ts`** (adjust field names to match Step 1 findings)

```ts
import type { Theme } from './stores/theme.svelte';

export interface BannerEntry { target: string; light: string; dark: string; url: string; }
export interface BannerManifest { images: BannerEntry[]; }
export const BANNER_MANIFEST_URL = 'https://oraios-software.de/serena-banners/manifest.php';

export function selectBanners(manifest: BannerManifest, target: 'platinum' | 'gold'): BannerEntry[] {
  return manifest.images.filter((b) => b.target === target);
}
export function pickVariant(entry: BannerEntry, theme: Theme): string {
  return theme === 'dark' ? entry.dark : entry.light;
}
export async function loadManifest(): Promise<BannerManifest> {
  const res = await fetch(BANNER_MANIFEST_URL);
  if (!res.ok) return { images: [] };
  return (await res.json()) as BannerManifest;
}
```

- [ ] **Step 5: Run the test — expect pass.** Run: `cd dashboard && npm test -- banners` → PASS.

- [ ] **Step 6: Implement `BannerCarousel.svelte`** — props `target: 'platinum' | 'gold'`; loads manifest on mount, random initial index, prev/next arrows, theme-aware variant, clicking the image opens `entry.url`. If no banners, render nothing.

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { theme } from '$lib/stores/theme.svelte';
  import { loadManifest, selectBanners, pickVariant, type BannerEntry } from '$lib/banners';
  let { target }: { target: 'platinum' | 'gold' } = $props();
  let banners = $state<BannerEntry[]>([]);
  let idx = $state(0);
  onMount(async () => {
    banners = selectBanners(await loadManifest(), target);
    if (banners.length) idx = Math.floor(Math.random() * banners.length);
  });
  const current = $derived(banners[idx]);
  function prev() { idx = (idx - 1 + banners.length) % banners.length; }
  function next() { idx = (idx + 1) % banners.length; }
</script>

{#if current}
  <div class="banner">
    {#if banners.length > 1}<button class="banner-arrow left" aria-label="Previous banner" onclick={prev}>‹</button>{/if}
    <a href={current.url} target="_blank" rel="noopener"><img src={pickVariant(current, theme.current)} alt="" /></a>
    {#if banners.length > 1}<button class="banner-arrow right" aria-label="Next banner" onclick={next}>›</button>{/if}
  </div>
{/if}

<style>
  .banner { position: relative; display: inline-flex; align-items: center; }
  .banner img { max-height: 90px; display: block; }
  .banner-arrow { position: absolute; background: rgba(0,0,0,0.3); color: #fff; border: none;
    cursor: pointer; height: 100%; padding: 0 var(--space-2); }
  .banner-arrow.left { left: 0; } .banner-arrow.right { right: 0; }
</style>
```

- [ ] **Step 7: Wire `BannerCarousel`** into `Header.svelte` (`target="platinum"` inside `#platinum-banners`) and into `OverviewPage.svelte` right column (`target="gold"`). Type-check.

Run: `cd dashboard && npm run check` → 0 errors.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src dashboard/tests/banners.test.ts
git commit -m "feat(dashboard): platinum and gold banner carousels"
```

### Task 7.2: News section

**Files:**
- Create: `dashboard/src/components/overview/NewsSection.svelte`

- [ ] **Step 1: Implement `NewsSection.svelte`** — on mount calls `fetchUnreadNews()`; renders each entry's HTML snippet with a "Mark as read" button that calls `markNewsRead(id)` and removes the item locally. Hidden when there is no unread news. News ids are the object keys; values are HTML strings, rendered with `{@html}` (server-trusted content, same as legacy).

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchUnreadNews, markNewsRead } from '$lib/api/endpoints';
  let items = $state<Array<[string, string]>>([]);
  onMount(async () => { items = Object.entries((await fetchUnreadNews()).news); });
  async function dismiss(id: string) {
    await markNewsRead(id);
    items = items.filter(([k]) => k !== id);
  }
</script>

{#if items.length}
  <section class="news-section">
    <h2>What's New</h2>
    {#each items as [id, html] (id)}
      <div class="news-item">
        <div class="news-body">{@html html}</div>
        <button class="news-dismiss" onclick={() => dismiss(id)}>Mark as read</button>
      </div>
    {/each}
  </section>
{/if}

<style>
  .news-item { border: 1px solid var(--border); border-radius: var(--radius);
    padding: var(--space-3); margin-bottom: var(--space-3); background: var(--bg-card); }
  .news-dismiss { margin-top: var(--space-2); background: var(--bg-secondary-btn);
    border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--space-1) var(--space-3); cursor: pointer; color: var(--text-primary); }
</style>
```

- [ ] **Step 2: Wire `NewsSection`** at the top of the `OverviewPage` left column. Type-check.

Run: `cd dashboard && npm run check` → 0 errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src && git commit -m "feat(dashboard): What's New news section"
```

---

## Phase 8 — Build integration, parity pass, cutover

### Task 8.1: Produce the build and confirm Flask serves it

**Files:**
- Modify: committed output under `src/serena/resources/dashboard/` (generated)
- Verify: `src/serena/dashboard.py:223-229` (static serving — read only, no change expected)

- [ ] **Step 1: Build**

Run: `cd dashboard && npm run build`
Expected: Vite writes `index.html` + `assets/…` into `src/serena/resources/dashboard/` without deleting the existing icon/logo/png files (`emptyOutDir: false`).

- [ ] **Step 2: Confirm asset paths are relative.** Open the generated `src/serena/resources/dashboard/index.html` and verify script/style hrefs start with `./assets/` (so they resolve under `/dashboard/`). If they are absolute (`/assets/…`), confirm `base: './'` in `vite.config.ts`.

- [ ] **Step 3: Run the real backend and load the app.** Start a Serena MCP server with the dashboard enabled (per repo `suggested_commands` memory / README), open `http://localhost:24282/dashboard/`, and verify: overview loads, logs stream, stats charts render, all modals work, banners + news load, theme toggle works in both directions.

- [ ] **Step 4: Commit the built assets**

```bash
git add src/serena/resources/dashboard
git commit -m "build(dashboard): commit Svelte build output"
```

### Task 8.2: Visual parity pass (both themes)

**Files:**
- Modify: `dashboard/src/styles/*` and component `<style>` blocks as needed

- [ ] **Step 1: Side-by-side compare.** Keep the legacy dashboard (still in git history / a stashed copy) open next to the new app. Walk every view in light then dark theme. List each visual discrepancy (spacing, font size, border, color, header height, card shadows).

- [ ] **Step 2: Fix discrepancies** by adjusting tokens/component styles. Re-run `npm run build` after CSS changes and re-check in the browser. Iterate until the app is pixel-comparable in both themes.

- [ ] **Step 3: Rebuild + commit**

```bash
cd dashboard && npm run build
git add dashboard/src src/serena/resources/dashboard
git commit -m "style(dashboard): visual parity pass for both themes"
```

### Task 8.3: Delete legacy frontend

**Files:**
- Delete: `src/serena/resources/dashboard/dashboard.js`
- Delete: `src/serena/resources/dashboard/dashboard.css`
- Delete: `src/serena/resources/dashboard/jquery.min.js`
- (The old `index.html` is already overwritten by the Vite build output.)

- [ ] **Step 1: Confirm nothing in Python references the deleted files.** Run: `grep -rn "dashboard.js\|dashboard.css\|jquery.min.js" src/serena` → expect no matches (the legacy `index.html` referenced them; the new built `index.html` references hashed assets instead).

- [ ] **Step 2: Delete the files**

```bash
git rm src/serena/resources/dashboard/dashboard.js \
       src/serena/resources/dashboard/dashboard.css \
       src/serena/resources/dashboard/jquery.min.js
```

- [ ] **Step 3: Re-run the backend smoke test** (Task 8.1 Step 3) to confirm the dashboard still fully works with the legacy files gone.

- [ ] **Step 4: Verify pywebview + tray still load the app.** On macOS, launch the dashboard via the `SerenaDashboardViewer`/tray path (per repo docs) and confirm the native window renders the new app. (No code change expected — it loads the same `/dashboard/` URL.)

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(dashboard): remove legacy jQuery dashboard"
```

### Task 8.4: CI job + poe task

**Files:**
- Modify: `pyproject.toml` (add a poe task)
- Create/Modify: GitHub Actions workflow (find existing under `.github/workflows/`; add a job, or create `.github/workflows/dashboard.yml` if none fits)

- [ ] **Step 1: Add a poe task to `pyproject.toml`** under `[tool.poe.tasks]`:

```toml
build-dashboard = { cmd = "npm --prefix dashboard ci && npm --prefix dashboard run build" }
```

- [ ] **Step 2: Inspect existing workflows.** Run: `ls .github/workflows && grep -l "uv\|pytest\|poe" .github/workflows/*` to find the main CI workflow and match its style (runner, setup-node usage).

- [ ] **Step 3: Add the dashboard CI job** (new file `.github/workflows/dashboard.yml` if no JS job exists). The staleness check rebuilds and fails if committed output differs.

```yaml
name: dashboard
on:
  pull_request:
    paths: ['dashboard/**', 'src/serena/resources/dashboard/**']
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: dashboard } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: dashboard/package-lock.json }
      - run: npm ci
      - run: npm run check
      - run: npm test
      - run: npm run lint
      - run: npm run build
      - name: Fail if committed build output is stale
        run: git diff --exit-code -- ../src/serena/resources/dashboard
        working-directory: dashboard
```

- [ ] **Step 4: Validate the workflow locally** by running the same commands: `cd dashboard && npm ci && npm run check && npm test && npm run lint && npm run build && git diff --exit-code -- ../src/serena/resources/dashboard`. Expected: all pass, no diff.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .github/workflows/dashboard.yml
git commit -m "ci(dashboard): build, type-check, test, and staleness gate"
```

### Task 8.5: Final verification

- [ ] **Step 1: Full frontend gate.** Run: `cd dashboard && npm run check && npm test && npm run lint && npm run build`. Expected: 0 type errors, all tests pass, lint clean, build succeeds.

- [ ] **Step 2: Python packaging sanity.** Run: `uv build` (or the repo's build command from the `suggested_commands` memory) and confirm the wheel contains `serena/resources/dashboard/index.html` and `serena/resources/dashboard/assets/…`:

```bash
python -m zipfile -l dist/*.whl | grep "resources/dashboard"
```

Expected: built `index.html` + `assets/*` present; no `dashboard.js`/`dashboard.css`/`jquery.min.js`.

- [ ] **Step 3: End-to-end backend run** of every feature in both themes one final time (overview, logs, stats, all modals, banners, news, shutdown).

- [ ] **Step 4: Commit any final fixes**, then proceed to branch finishing (PR) per the team's flow.

---

## Self-Review (completed during authoring)

- **Spec coverage:** Tech stack (§3 → Task 0.1, 5.1, 8.4), repo layout (§4 → Task 0.1), components (§5 → Phases 2–7), state/polling/API (§6 → Phase 1), styling/tokens (§7 → Task 1.1, 8.2), banners/news (§7 → Phase 7), build/CI/poe (§8 → Task 8.1, 8.4), CLAUDE.md (§9 → Task 0.2), testing (§10 → tests throughout), cutover/hard-replace (§11 → Phase 8), Frappe Charts fallback risk (§12 → noted in Task 5.1 scope). All spec sections map to tasks.
- **Placeholder scan:** No "TBD"/"add error handling"-style gaps; every code step shows real code. Two tasks (7.1, 8.x) require reading existing legacy/CI files first and adapting field names/workflow style — these are explicit inspection steps with concrete fallbacks, not placeholders.
- **Type consistency:** `ResponseConfigOverview`, `ToolStats`/`ToolStatEntry` (`num_times_called`/`input_tokens`/`output_tokens`), `QueuedExecution`, and the `endpoints.ts` function names are used consistently across stores, components, and charts. Modal `kind`s in the store match the `ModalHost` switch and the `App` callbacks.

---

## Post-execution deviations

Notable changes made during/after execution versus this plan:

- The three right-column lists were unified into a single reusable `ListPanel.svelte` (instead of separate `DisabledToolsPanel` / `ModesPanel` / `ContextsPanel`).
- Added a reusable `Card.svelte` (common) wrapping each overview section, plus a separate `ProjectsPanel.svelte` (boxed rows: name + monospace path, active project highlighted).
- frappe-charts@1.6.2 ships no compiled CSS, so the planned `frappe-charts/.../*.css` import was dropped; types come from a local ambient `src/types/frappe-charts.d.ts`, and the chart instance is destroyed on re-render.
- `npm run build` runs a `prebuild` (`scripts/clean-assets.mjs`) that clears the `assets/` subdir, since `emptyOutDir: false` is required and would otherwise leave stale hashed bundles.
- Banners auto-rotate (~6 s); the manual prev/next arrows were removed.
- Memories are deletable (× → `DeleteMemoryModal`) with an inline "+ Add Memory".
- The Executions Queue filters to `logged` tasks only (hides unlogged internal tasks like `_get_config_overview`), matching legacy.
- The dashboard is opened/served at `/dashboard/`.
- A card-based visual-parity pass plus legacy typography (15px/0.04em uppercase muted section labels, 13px config labels, Inter + JetBrains Mono); the "📖 View Configuration Guide" link was restored.
```
