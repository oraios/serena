# Serena Dashboard v2 — Design Spec

**Date:** 2026-05-27
**Status:** Approved for planning
**Author:** Brainstorming session (Pavlo Basanets + Claude)

## 1. Summary

Replace the current Serena dashboard frontend — a monolithic jQuery application
(`dashboard.js` ~2387 lines, `dashboard.css` ~1682 lines, a single `Dashboard`
class, bundled jQuery) — with a component-based **Svelte 5 + TypeScript** app built
with **Vite**. The replacement reproduces **100% of current features** and preserves
the exact visual identity (palette, fonts, banners, logos, light/dark themes).

This is a **frontend-only** replacement. The Flask backend in
`src/serena/dashboard.py` and its ~25 HTTP endpoints are treated as a **frozen
contract**. The `pywebview` viewer (`SerenaDashboardViewer`) and the system-tray
manager (`SerenaDashboardTrayManager`) are untouched and must continue to load the
new app unchanged.

## 2. Goals & Non-Goals

### Goals
- Lightweight, supportable, maintainable, extendable frontend.
- Component boundaries replacing the single 2387-line class — each component has one
  purpose, props in / events out, scoped CSS, independently testable.
- Net-new test coverage (the current dashboard has none).
- Exact visual parity in both light and dark themes.

### Non-Goals
- No backend rewrite. No changes to endpoint shapes, ports, host-header checks, or
  port discovery.
- No changes to `pywebview` viewer or tray manager.
- No new features beyond current parity.

## 3. Tech Stack

| Concern        | Choice |
|----------------|--------|
| Framework      | Svelte 5 (runes) + TypeScript |
| Bundler        | Vite |
| Charts         | **Frappe Charts** — bundled via npm (replaces Chart.js + datalabels; no CDN) |
| Fonts          | Inter + JetBrains Mono via **Google Fonts CDN** (unchanged from today) |
| HTTP           | Native `fetch` wrapped in a typed API client (jQuery dropped entirely) |
| Tests          | Vitest (unit) + @testing-library/svelte (components); optional Playwright smoke |
| Lint / format  | ESLint + Prettier (svelte plugins); `svelte-check` for types |

Notes:
- **Frappe Charts** (MIT, ~10–25 KB gzipped, zero-dependency SVG) provides the 3 pie
  charts and the grouped bar chart with value labels and animations. It is imported
  and bundled by Vite — the previous Chart.js + `chartjs-plugin-datalabels` CDN
  `<script>` tags are removed.
- **Google Fonts remain on CDN** (Inter + JetBrains Mono), exactly as the current
  dashboard loads them. Fonts are not self-hosted.
- The Vite build bundles only the app's own JS/CSS plus Frappe Charts. No other CDN
  runtime dependencies remain.

### Implementation notes (final)
- **frappe-charts@1.6.2 ships no compiled CSS** — `ChartPanel.svelte` imports only the
  JS (no `frappe-charts/.../*.css` import). The library has no TS types, so types come
  from a local ambient declaration `src/types/frappe-charts.d.ts`. `ChartPanel` destroys
  the chart instance on re-render (effect cleanup) to avoid leaking resize listeners.
- **Memories are deletable**: each memory has a `×` that opens `DeleteMemoryModal`, plus
  an inline "+ Add Memory" action.
- **Executions Queue shows only `logged` tasks** — unlogged internal background tasks
  (e.g. `_get_config_overview`) are hidden, matching the legacy dashboard.
- **Typography copied from legacy verbatim**: 15px / 0.04em uppercase muted section
  labels, 13px config labels, Inter + JetBrains Mono.
- The "📖 View Configuration Guide" link is restored (→
  https://oraios.github.io/serena/02-usage/050_configuration.html).

## 4. Repository Layout

Frontend source lives **outside** the Python package in a top-level `dashboard/`
directory with its own npm world. Vite builds **into** the package resource dir so
the wheel picks the output up automatically.

```
serena_fork/
├─ dashboard/                       # NEW frontend source (its own npm world)
│  ├─ CLAUDE.md                     # subproject instructions (section 9)
│  ├─ package.json  package-lock.json
│  ├─ vite.config.ts  tsconfig.json
│  ├─ index.html                    # Vite entry (Google Fonts <link> kept here)
│  ├─ src/
│  │  ├─ main.ts                     # mounts App.svelte
│  │  ├─ App.svelte                  # shell: header, tabs, view switch
│  │  ├─ lib/
│  │  │  ├─ api/
│  │  │  │  ├─ client.ts             # fetch wrapper, JSON, error handling, base URL
│  │  │  │  ├─ types.ts              # request/response types mirroring Pydantic models
│  │  │  │  └─ endpoints.ts          # config, logs, stats, memory, language, config, news, executions
│  │  │  ├─ stores/                  # runes-based state (.svelte.ts)
│  │  │  ├─ polling.ts               # createPoller(fn, intervalMs) util
│  │  │  └─ format.ts                # log formatting + tool-name highlighting
│  │  ├─ components/
│  │  │  ├─ overview/  logs/  stats/  modals/  banners/  common/
│  │  └─ styles/
│  │     ├─ tokens.css               # CSS custom properties = the palette (section 7)
│  │     └─ global.css
│  └─ tests/
└─ src/serena/resources/dashboard/   # build output committed here (shipped in wheel)
   ├─ index.html  assets/…           # Vite output (hashed)
   └─ (icons + logos + serena-logs*.png kept as static assets)
```

The legacy `dashboard.js`, `dashboard.css`, `jquery.min.js`, and old `index.html`
are **deleted** in the cutover PR. Icons (`serena-icon-*.png`, `serena.ico`), logos
(`serena-logo.svg`, `serena-logo-dark-mode.svg`), and `serena-logs*.png` are kept and
referenced as static assets by the new app.

## 5. Component Architecture

`App.svelte` is the shell: header (theme-aware logo, platinum banner carousel, theme
toggle, menu dropdown, tab nav) plus a tiny client-side view switch across
**Overview / Logs / Stats** (no router library needed).

- **Overview**: `ConfigCard`, `ToolUsageBars`, `ExecutionsQueue`, `LastExecution`,
  `ProjectsPanel` (registered projects as boxed rows with name + monospace path,
  active project highlighted in accent), a single reusable `ListPanel` used for the
  three right-column lists ("Available Tools (Disabled)", "Available Modes",
  "Available Contexts" — bordered scrollable rows, active items highlighted),
  `GoldBanners`, `NewsSection`.
- **Logs**: `LogToolbar` (copy / save / clear), `LogViewer` (incremental append +
  auto-scroll-if-at-bottom).
- **Stats**: `StatsSummary`, four `ChartPanel` instances wrapping Frappe Charts (3
  pie, 1 grouped bar with dual reading of input vs output).
- **Modals** (one component each, driven by a single modal store): `AddLanguage`
  (combobox), `RemoveLanguage`, `EditMemory` (+ inline rename), `DeleteMemory`,
  `CreateMemory`, `CancelExecution`, `EditSerenaConfig`.
- **common**: `Card` (titled bordered/shadowed wrapper for each overview section),
  `Modal`, `Collapsible`, `Combobox`, `Spinner`, `BannerCarousel`, `ThemeToggle`.

Each component is small, single-purpose, with scoped CSS and independently testable.
This is the core maintainability win over the single jQuery class.

## 6. State & Data Flow

- **Runes-based stores** (`$state` / `$derived` in `.svelte.ts` modules): `theme`,
  `configOverview`, `logs`, `executions`, `toolStats`, `modal`.
- **Polling util**: a single `createPoller(fn, intervalMs)` replaces the scattered
  `setInterval`s. Preserves current cadences (config 1 s, executions 1 s, logs
  incremental 1 s) and the "skip re-render if unchanged" optimization (hash compare in
  the store). Pollers start/stop on view change exactly as today.
- **Typed API client**: `client.ts` centralizes base URL, JSON handling, and errors.
  `types.ts` mirrors the Pydantic response/request models (`ResponseConfigOverview`,
  `QueuedExecution`, `ResponseToolStats`, etc.) so endpoint-shape drift is caught at
  compile time. `endpoints.ts` exposes one typed function per backend route.

### Endpoint inventory (frozen contract)
The app consumes the existing routes, unchanged:
`/get_log_messages`, `/clear_logs`, `/get_tool_names`, `/get_tool_stats`,
`/clear_tool_stats`, `/get_token_count_estimator_name`, `/get_config_overview`,
`/shutdown`, `/get_available_languages`, `/add_language`, `/remove_language`,
`/get_memory`, `/save_memory`, `/delete_memory`, `/rename_memory`,
`/get_serena_config`, `/save_serena_config`, `/queued_task_executions`,
`/cancel_task_execution`, `/last_execution`, `/fetch_unread_news`,
`/mark_news_snippet_as_read`, plus static serving via `/dashboard/<path:filename>`
and `/dashboard/`.

## 7. Styling — Preserving the Exact Palette

`tokens.css` captures the current values verbatim as CSS custom properties, themed via
`[data-theme]`:

- Accent `--accent: #eaa45d` (hover `#dca662`, disabled `#adb5bd`).
- Light: bg `#f5f5f5`, cards `#ffffff`, text `#1f2328` / `#3f4754` / muted `#6a737d`,
  borders `#e3e6ea` / `#d0d7de`, tool highlight `#fff3bf`.
- Dark: bg `#1a1a1a`, cards `#2d2d2d`, elevated `#262b32`, text `#e6edf3` / `#c9d1d9`
  / muted `#8b95a1`, borders `#2d333b` / `#3d444d`, tool highlight `#f6c948`.
- Log levels: debug `#8b95a1`, info `#1f2328`/`#e6edf3`, warning `#d97706`/`#f59e0b`,
  error `#dc2626`/`#f87171`. Success accent `#22c55e`.
- Fonts: Inter (400/500/600/700) + JetBrains Mono (400/500), via Google Fonts CDN.
- Spacing scale 4/8/12/16/24/32, radius 6/4 px, max content width 1600 px, 2-col → 1-col
  responsive breakpoint preserved.
- Theme toggle writes `data-theme` + localStorage and swaps theme-aware logo/images —
  same behavior as today, including system-preference detection fallback.
- Frappe Charts colors are driven from these tokens so charts re-theme on toggle.

**Acceptance bar:** the new app is pixel-comparable to the old one in both themes.

### Banners
Platinum (header) and gold (sidebar) banner carousels are reproduced by a
`BannerCarousel` component hitting the same remote manifest
(`https://oraios-software.de/serena-banners/manifest.php`), preserving light/dark
image variants and a random initial banner. The carousel **auto-rotates** (~6 s
interval) with **no manual prev/next arrows** (this supersedes the original
manual-arrows / auto-rotation-disabled design). The news system likewise hits the
existing backend endpoints; banner/news content remains remotely served (not
bundled).

## 8. Build Process & Distribution

- **Dev**: `npm run dev` → Vite dev server with HMR; `vite.config.ts` proxies the
  backend routes (e.g. `/get_config_overview`, `/get_log_messages`, …) to a locally
  running Serena dashboard at `http://localhost:24282`
  (`SerenaPorts.DASHBOARD_API_BASE_PORT = 0x5EDA`). Fast inner loop, no Python rebuild.
- **Build**: `npm run build` → Vite emits hashed `assets/` + `index.html` into
  `src/serena/resources/dashboard/`. A `prebuild` step (`scripts/clean-assets.mjs`)
  deletes the `assets/` subdir first: `emptyOutDir: false` is required (the output dir
  also holds icon/logo files), so without the clean, stale hashed bundles would
  accumulate in git and the wheel.
- **Serving**: the dashboard is opened/served at `/dashboard/` (not
  `/dashboard/index.html`).
- **Distribution**: built output is **committed to git** and ships in the wheel
  automatically — hatchling packages `src/serena/**`
  (`[tool.hatch.build.targets.wheel] packages = ["src/serena", …]`). End users and
  Python-only contributors need **no Node**; only frontend contributors run npm.
- **CI gate** (GitHub Actions): job runs `npm ci && npm run build && npm run check &&
  npm test`, then fails the PR if committed output is stale
  (`git diff --exit-code` over `src/serena/resources/dashboard/`). Guarantees committed
  assets always match source.
- **Flask serving**: minimal change. The existing `/dashboard/<path:filename>` route
  already serves arbitrary files from `SERENA_DASHBOARD_DIR`; the index route serves
  the built `index.html`. Verify hashed-asset subpaths (`assets/…`) resolve correctly.
- **poe task**: add `poe build-dashboard` wrapping the npm build for discoverability
  alongside existing poe tasks.

## 9. Subproject `dashboard/CLAUDE.md`

A focused instruction file for anyone (human or agent) working in `dashboard/`:

- **Scope & boundary**: this dir is frontend only; the Flask API in
  `../src/serena/dashboard.py` is a frozen contract — never change endpoint shapes
  from here.
- **Commands**: `npm install`, `npm run dev` (with proxy target), `npm run build`,
  `npm run check`, `npm test`, `npm run lint`.
- **Architecture rules**: components small & single-purpose; state in runes stores;
  all network calls through `lib/api/`; never reintroduce jQuery; scoped CSS only;
  colors come from `tokens.css` (never hardcode hex); charts go through the
  `ChartPanel` wrapper around Frappe Charts.
- **The contract rule**: after editing, run `npm run build` and commit
  `src/serena/resources/dashboard/` output, or CI fails.
- **Adding a feature / endpoint** (recipe): add type to `types.ts` → function to
  `endpoints.ts` → component + store → test.
- **Palette / visual parity**: must match the old dashboard in both themes; how to
  compare side-by-side.
- **Testing expectations**: Vitest for logic/components before merge.

## 10. Testing Strategy

- **Unit (Vitest)**: log formatting / tool-name highlighting, poller start/stop &
  unchanged-skip, API client error handling, combobox filtering, memory-name
  validation.
- **Component (@testing-library/svelte)**: modals open/submit/cancel, collapsibles,
  theme toggle, log auto-scroll behavior.
- **Smoke (optional Playwright)**: app boots against a mocked API and renders all
  three views.

## 11. Cutover Plan (Hard Replace, One PR)

1. Scaffold `dashboard/` (Vite + Svelte 5 + TS, tooling, `CLAUDE.md`).
2. Build the typed API client + runes stores against the existing endpoints.
3. Implement components view-by-view to parity: Overview → Logs → Stats → Modals →
   Banners/News.
4. Wire build output into `src/serena/resources/dashboard/`; add CI job + poe task.
5. Delete legacy `dashboard.js`, `dashboard.css`, `jquery.min.js`, old `index.html`.
6. Verify parity in both themes; verify `pywebview` window + tray still load the new
   app.
7. Single PR.

## 12. Risks / Open Questions

- **Visual parity effort** — matching ~1682 lines of CSS exactly is the bulk of the
  work; mitigated by porting tokens verbatim and comparing side-by-side.
- **Frappe Charts feature gaps** — must confirm it covers the grouped/dual bar chart
  and per-slice value labels equivalent to the old datalabels plugin; if a specific
  chart can't be matched, fall back to a hand-rolled SVG component for that one chart.
- **Banner/news behavior** — remote manifest format must be reproduced precisely
  (light/dark variants, random initial, arrows); port existing logic faithfully.
- **Large logo SVGs (~212 KB each)** — kept as-is for parity; optional later
  optimization, out of scope.
- **No backend change** means any backend quirk (host-header check, port discovery)
  stays — acceptable for a frontend swap.
