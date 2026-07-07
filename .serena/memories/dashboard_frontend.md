# Dashboard Frontend

Svelte 5 (runes) + TS + Vite SPA in `dashboard/`. Built into
`src/serena/resources/dashboard/` and served by Flask in `src/serena/dashboard.py`
at `/dashboard/`. **`dashboard/CLAUDE.md` is the authoritative ruleset** — read it
before editing anything under `dashboard/`; this memory only records the
hard invariants.

## Hard invariants

- **Backend is a frozen contract.** `dashboard.py` endpoint names, request/response
  shapes, ports, and the host-header check must not change from the frontend.
  Canonical route list = `API_ROUTES` in `dashboard/vite.config.ts`.
- **Build output is committed & CI-enforced.** After any `dashboard/src` change:
  `npm run build` (writes hashed assets to `src/serena/resources/dashboard/`) and
  commit the regenerated `index.html` + `assets/`. Stale output fails CI
  (`.github/workflows/dashboard.yml`; poe task `poe build-dashboard`).
- Before committing dashboard work: `npm run format` and **stage all changes** — a
  partial stage leaves files prettier-dirty and CI's `prettier --check` fails.
- `prebuild` (`scripts/clean-assets.mjs`) clears `assets/` because
  `emptyOutDir: false` (the dir also holds icon/logo PNGs).

## Commands (run from `dashboard/`)

`npm run dev` (Vite :5273, proxies API to a Serena server on :24282) ·
`npm run build` · `npm run check` (svelte-check) · `npm test` (Vitest) ·
`npm run lint` / `npm run format`. Dev needs a running Serena MCP server with the
dashboard enabled; logos/icons 404 under dev (backend-served).

## Architecture invariants

- Layered: `lib/api/` (`types.ts` → `endpoints.ts` → `client.ts`, the only `fetch`)
  → `lib/stores/*.svelte.ts` (runes singletons, getter-only) → components. Never
  `fetch` from a component.
- Two backend failure channels (non-2xx `ApiError` AND HTTP-200
  `{status:'error'}`); normalize every mutation through `runMutation()`.
- `$derived` for computed values; `$effect` only for true side effects (never to
  sync state). Reactive collections use `SvelteSet`/`SvelteMap`. Colors via
  `var(--token)` from `styles/tokens.css`, never hardcoded. Charts only through
  `ChartPanel.svelte`. Snippets, not `<slot>`. No jQuery.
- Each store/lib gets a unit test; each component a render+interaction test.
  Vitest + jsdom; chart-mounting tests must mock `chart.js/auto`.
