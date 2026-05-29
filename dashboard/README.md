# Serena Dashboard (frontend)

Svelte 5 (runes) + TypeScript + Vite single-page app. It is built into
`../src/serena/resources/dashboard/` and served by the Flask backend in
`../src/serena/dashboard.py` at `/dashboard/`. The backend is a **frozen
contract** — don't change endpoint names, shapes, or ports from here.

> `CLAUDE.md` in this folder has the architecture rules for AI agents; this
> README is the human quick-start.

## Quick start

```bash
cd dashboard
npm install
npm run dev      # Vite dev server on :5273, proxies API routes to a backend on :24282
```

`npm run dev` only serves the frontend — start a Serena MCP server (dashboard
enabled, default port **24282**) first so the API calls resolve. Note: the
logo/icon files are served by the backend, so they 404 under `npm run dev`. For
full fidelity (logos, real data, correct routing) build and open the app the way
it ships:

```bash
npm run build    # writes hashed assets into ../src/serena/resources/dashboard/
# then open http://localhost:24282/dashboard/ with a Serena server running
```

## Commands

| Command                           | What                                          |
| --------------------------------- | --------------------------------------------- |
| `npm run check`                   | Type-check (`svelte-check`)                   |
| `npm test` / `npm run test:watch` | Vitest                                        |
| `npm run lint` / `npm run format` | ESLint + Prettier (check / write)             |
| `npm run build`                   | Production build into the Python resource dir |

## The build-output contract (important)

The build output under `../src/serena/resources/dashboard/` (`index.html` +
`assets/`) is **committed to git** and shipped in the wheel. After any source
change: **`npm run build` and commit the regenerated output.** CI
(`.github/workflows/dashboard.yml`) rebuilds and fails the PR if the committed
output is stale. There is also a poe task: `poe build-dashboard`.

`npm run build` auto-runs a `prebuild` step (`scripts/clean-assets.mjs`) that
clears `assets/` first. This prevents stale hashed bundles from piling up:
`emptyOutDir: false` is required because the same output dir holds the icon/logo
files, so Vite can't clean it on its own.

**Before committing:** run `npm run format` and **stage all changes**. Committing
only task-scoped files can leave other files prettier-dirty and fail CI's
`prettier --check`.

## Layout

- `src/lib/api/` — `types.ts` (mirrors backend JSON), `endpoints.ts` (one typed
  fn per route), `client.ts` (the only place that calls `fetch` for the API).
- `src/lib/stores/` — runes stores (`*.svelte.ts`): config, logs, executions,
  stats, theme, modal.
- `src/lib/` — `polling.ts`, `format.ts`, `charts.ts`, `validation.ts`, `banners.ts`.
- `src/components/` — `common/`, `shell/`, `overview/`, `logs/`, `stats/`,
  `modals/`, `banners/`.
- `src/styles/tokens.css` — the palette (light + `[data-theme='dark']`). Never
  hardcode hex in a component; use `var(--token)`.
- `tests/` — Vitest specs.

## Adding a feature that needs a backend route

1. Add the request/response type to `src/lib/api/types.ts`.
2. Add a typed function to `src/lib/api/endpoints.ts`.
3. Add/extend a store under `src/lib/stores/`.
4. Build the component + a Vitest test, then rebuild and commit the output.

## Gotchas

- **Charts use Chart.js** (`chart.js/auto`) + `chartjs-plugin-datalabels`, wrapped
  by `src/components/stats/ChartPanel.svelte` (the only file importing them).
  Series colours come from CSS vars, not hardcoded hex.
- **Node 26 + Vitest:** Node's experimental `localStorage` global shadows
  jsdom's, so `tests/setup.ts` reinstalls jsdom's Storage. Tests that touch
  `localStorage` must `clear()` it in `beforeEach`.
- **`$state(someProp)`** (capturing a prop as initial state) emits a
  `state_referenced_locally` svelte-check warning; it's suppressed where
  intentional. These are warnings, not errors.
