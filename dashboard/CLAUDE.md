# Serena Dashboard (frontend)

Svelte 5 (runes) + TS + Vite SPA. **Frontend only** — the HTTP API lives in
`../src/serena/dashboard.py` and is a **frozen contract**: never change endpoint
names, request/response shapes, ports, or the host-header check from here. The
canonical list of routes the app calls is `API_ROUTES` in `vite.config.ts`.

## Commands (run from `dashboard/`)

- `npm run dev` — Vite on :5273, proxies API routes to a backend on :24282
- `npm run build` — hashed assets into `../src/serena/resources/dashboard/`
- `npm run check` — `svelte-check` · `npm test` — Vitest · `npm run lint` / `format`

For `npm run dev` start any Serena MCP server with the dashboard enabled first
(logos/icons 404 under dev — they're served by the backend). See `README.md` for
the human quick-start.

## The build-output contract (CI enforces)

After **any** source change run `npm run build` and commit the regenerated
`../src/serena/resources/dashboard/` (`index.html` + `assets/`) — it ships in the
wheel and CI fails the PR if it's stale. Before committing run `npm run format`
and **stage all changes** (a partial stage can leave other files prettier-dirty
and fail CI's `prettier --check`). `prebuild` (`scripts/clean-assets.mjs`) clears
`assets/` first because `emptyOutDir: false` (the dir also holds icon/logo PNGs).

## Architecture rules

- Components are small, single-purpose: props in, events out (`on*` callback
  props, not `createEventDispatcher`), scoped CSS. Compose `common/` primitives
  (`Card`, `Button`, `Modal`, `Spinner`, `Combobox`, `Collapsible`) — don't
  re-implement their markup.
- Colors come from `src/styles/tokens.css` (light + `[data-theme='dark']`).
  Never hardcode hex; use `var(--token)`.
- Charts go **only** through `src/components/stats/ChartPanel.svelte`.
- Never `fetch` from a component — all network goes through `src/lib/api/`.
- Never reintroduce jQuery.

## State: runes stores (`src/lib/stores/*.svelte.ts`)

`$state` only lives in `.svelte.ts` modules. Each store is a factory returning
**getter-only** accessors plus action methods, exported as a singleton:

```ts
export function createXStore() {
  let data = $state<T | null>(null);
  return {
    get data() {
      return data;
    },
    async poll() {
      data = await fetchX();
    },
  };
}
export const x = createXStore(); // import the singleton; factory exists for tests
```

Never expose the `$state` variable directly — only getters, so reads stay
reactive and writes funnel through methods.

## API layer (`src/lib/api/`)

- `types.ts` — TS mirrors of backend JSON. `endpoints.ts` — one typed fn per
  route. `client.ts` — the **only** place that calls `fetch` (`getJson` /
  `postJson` / `putJson`, throws `ApiError` on non-2xx).
- **Two failure channels.** The backend signals failure either as a non-2xx
  (thrown `ApiError`) _or_ as HTTP 200 with `{ status: 'error', message }`. Wrap
  every mutating call in `runMutation(fn)` (`mutation.ts`) — it normalizes both
  into `{ ok, message?, data? }`. Don't hand-roll try/catch around endpoints.

## Modals

- One discriminated union `ModalState` in `stores/modal.svelte.ts`; the global
  `modal` store has `open(state)` / `close()`. `App.svelte` opens modals;
  `ModalHost.svelte` is the single switch that renders the active one. To add a
  modal: extend the union, add a case in `ModalHost`, build the component.
- Mutating modals use `createModalAction()` (`modalAction.svelte.ts`) for the
  shared busy/error lifecycle: `action.run(() => runMutation(...), onclose)` —
  on success it calls `onclose`, on failure it sets `action.error` and stays
  open. Confirm-style modals just wrap `ConfirmModal`.
- Editor modals guard unsaved work with `confirmDiscard(isDirty)` before closing.
- `Modal.svelte` owns a11y: focus trap, focus restore on destroy, Escape/backdrop
  close. Don't re-implement dialog behavior per modal.

## Polling

- `createPoller(fn, intervalMs)` (`polling.ts`) self-guards against overlapping
  ticks (`inFlight`). `pollersForView(view)` (`pollers.ts`) is a **pure** map of
  view → which pollers run, so it's unit-tested independently. `App.svelte` stops
  all pollers and starts the view's set on every `navigate`. Poll calls are
  wrapped in `safe()` so a transient backend error logs instead of throwing an
  unhandled rejection; the next tick retries.

## Charts (`ChartPanel.svelte`)

Chart.js wrapper (`chart.js/auto`). `charts.ts` builds pure, colourless
`ChartSpec`s (`pieSpec`, `tokensBarSpec`); `ChartPanel` is the **only** importer
of `chart.js`/`chartjs-plugin-datalabels`. It resolves the palette
(`--accent`, `--chart-2…6`) and theme colours (`--text-primary`, `--chart-grid`)
from CSS vars and writes them onto the live chart. A **create-effect** builds the
chart once per canvas bind (reads `spec` via `untrack`); a **data-effect** copies
labels/data in place on `spec` change; a **theme-effect** re-applies colours on
`theme.current`. All three end in `chart.update()` — no teardown, so there is no
frappe-style `removeChild` race to suppress. `chartjs-plugin-datalabels` is
registered **per-instance** (`plugins: [ChartDataLabels]`), enabled on the pies
and disabled on the dual-axis bar.

## Testing (Vitest + jsdom + Testing Library)

- Helpers in `tests/helpers.ts`: `stubFetchJson` / `stubFetchRoutes` (substring
  URL routing), `errBody` / `okBody` (the two backend channels), `exec()`
  fixtures. `tests/setup.ts` restores mocks after each test.
- Test the singleton store via its factory (`createXStore()`) for isolation.
- A store/lib gets a unit test; a component gets a render + interaction test
  (assert error-stays-open / success-closes for modals).

## Gotchas

- **Charts use `chart.js/auto`** (auto-registers all controllers/scales — simpler
  than manual tree-shaking). `chartjs-plugin-datalabels` is registered per-chart,
  not globally. Its Chart.js type augmentation is loaded via the type-only
  `src/types/chartjs-datalabels.d.ts`.
- **jsdom has no canvas backend** — component tests that mount a chart must
  `vi.mock('chart.js/auto', ...)` and `vi.mock('chartjs-plugin-datalabels', ...)`
  (see `tests/chart-panel.test.ts`).
- **Node 26 + Vitest:** Node's experimental `localStorage` shadows jsdom's, so
  `tests/setup.ts` reinstalls it; localStorage tests must `clear()` in `beforeEach`.
- `$state(someProp)` (prop as initial state) emits a `state_referenced_locally`
  svelte-check **warning**, not an error — suppressed where intentional.
