# Dashboard Review Fixes — Design

**Date:** 2026-05-27
**Branch:** `dashboard_v2`
**Scope:** Address all findings from the dashboard code review (bugs, style-rule
violations, duplication, accessibility, one design improvement) and streamline the
Vitest suite.

## Context

The V2 Svelte 5 (runes) dashboard lives in `dashboard/` and compiles into
`src/serena/resources/dashboard/assets/`. The HTTP API in
`src/serena/dashboard.py` is a **frozen contract** — no endpoint/shape/port changes.
Project rules (`dashboard/CLAUDE.md`): small props-in/events-out components, scoped
CSS, state in `src/lib/stores/*.svelte.ts`, network only through `src/lib/api/`, no
jQuery, **no hardcoded hex** (colors come from `src/styles/tokens.css`), charts go
through `ChartPanel.svelte`. After any change: `npm run build` and commit the
regenerated bundle (CI fails on stale output); `npm run format` and stage all files.

Baseline before this work: 59 tests pass across 28 files; `npm run check` clean
except 4 `state_referenced_locally` warnings; lint + prettier pass.

## Findings being addressed

| # | Sev | Location | Issue |
|---|-----|----------|-------|
| 1 | BUG | `lib/format.ts:26` `highlightTools` | Sequential replacement re-matches injected markup; a tool named `tool`/`name`/`span`/`class` (or a `\b`-bounded substring of an injected wrapper) nests a span into the attribute and garbles the DOM. |
| 2 | BUG | `modals/ShutdownModal.svelte:6` | Ignores `shutdown()` result; unconditionally schedules `window.close()` + `onclose()`. Failure looks like success. |
| 3 | BUG | `modals/EditMemoryModal.svelte:44` | `applyRename` sets no `busy` (double-submit) and the rename input has no submit-on-Enter. |
| 4 | LATENT | `EditMemoryModal.svelte:11,18` + `ModalHost` | `currentName`/`renameValue` capture `name` only at init (`state_referenced_locally`, suppressed). Unreachable today (ModalHost nulls `modal.active` between opens) but masked fragility. |
| 5 | STYLE | `common/Button.svelte:29,43` | `color: #fff` → `var(--text-on-accent)`. |
| 6 | STYLE | `overview/ListPanel.svelte:49` | `color: #fff` → `var(--text-on-accent)` (ProjectsPanel already does this for the identical pattern). |
| 7 | STYLE | `stats/ChartPanel.svelte:63` | 5 hardcoded series hex; only `accent()` reads a token. |
| 8 | DUP | `Card.svelte:12`, `ListPanel.svelte:20`, `ProjectsPanel.svelte:25` | `.card` block byte-identical in 3 files; panels hand-roll `<div class="card">` instead of composing `<Card>`. |
| 9 | DUP | all 8 leaf modals | `.modal-actions` block copy-pasted verbatim; `.modal-textarea`/`.modal-input` duplicated. |
| 10 | DUP | 5 modals | busy/error mutation handler duplicated; `?? 'Failed'` fallbacks are dead code (`runMutation` already defaults the message). |
| 11 | DUP | 3 test files | `exec()` `QueuedExecution` factory duplicated. |
| 12 | A11Y | `shell/Header.svelte` | Menu button lacks `aria-haspopup`/`aria-expanded`; dropdown has no Escape-to-close/focus management. |
| 13 | A11Y | CreateMemory/EditMemory/EditSerenaConfig | Inputs/textareas have no `<label>`/`aria-label`. |
| 14 | A11Y | `common/Modal.svelte` | No focus trap; Tab can leave an `aria-modal="true"` dialog. |
| 15 | DESIGN | `stats/ChartPanel.svelte:53` | Full chart teardown + re-`new Chart()` on every `data` change; root cause of the ResizeObserver `removeChild` race the window-level suppressor papers over. |

## Decisions

- **Finding 15:** Switch to `chart.update(data)`, recreate only on theme change, **and
  remove** the module-level `removeChild` error suppressor + the `try/catch` around
  `destroy()`. This is the riskier option; it requires manual runtime verification
  (the suppressor fixed real console noise in a recent commit). If a race survives,
  reinstate the suppressor.
- **Findings 9/10:** Extract a `runModalAction(fn, {onclose})` helper, move shared modal
  CSS to global, **and** add a `ConfirmModal` wrapper to collapse the four confirm-style
  modals (Remove/Delete/Cancel/Shutdown). Stop short of moving the dirty/busy guard into
  `Modal.svelte` itself.

## Architecture / new units

- **`createModalAction()`** — a new `src/lib/modalAction.svelte.ts` module (must be
  `.svelte.ts` to hold `$state`). Returns `{ get busy(), get error(), run(fn, onSuccess) }`.
  `run` sets `busy = true`, clears `error`, calls `runMutation(fn)`, sets `busy = false`,
  and on `!ok` sets `error = res.message` (no `?? 'Failed'` — `runMutation` already
  defaults) and stays open, on `ok` calls `onSuccess` (typically `onclose`). A factory
  rather than a plain function because the helper must own reactive `busy`/`error` the
  component reads in markup. Eliminates the per-modal 10-line block and the dead
  fallbacks.
- **`ConfirmModal.svelte`** — `src/components/modals/`. Props: `title`, `message`,
  `confirmLabel`, `variant` (`'primary' | 'danger'`), `onconfirm` (async mutation fn),
  `onclose`. Owns its own `createModalAction()` internally (so it renders the inline
  error and `Spinner`-on-busy confirm button). Remove/Delete/Cancel/Shutdown modals
  become thin wrappers passing `onconfirm`.
- **Poller selection map** — extract the start/stop logic from `App.svelte`
  `startPollers` into a pure function `pollersForView(view): PollerName[]` (or a
  `Record<View, PollerName[]>` map) so it is unit-testable without mounting `App`.
- **`tests/helpers.ts`** — `stubFetchJson(body, status?)`, `stubFetchRoutes(routes,
  fallback?)`, `errBody(message)`, `okBody(extra?)`, `exec(overrides?)`.
- **Single-pass `highlightTools`** — build one combined alternation regex from the
  escaped tool names and replace in a single `.replace` callback over the escaped text,
  so injected markup is never re-scanned. `escapeHtml` also escapes `'`.
- **Chart series tokens** — `--chart-2..--chart-6` added to both `:root` and
  `[data-theme='dark']` in `tokens.css`; `ChartPanel` reads them via `getComputedStyle`
  like the existing `accent()` helper. `frappe-charts.d.ts` gains an `update(data)`
  method on the `Chart` type.

## Data flow / behavior changes

- Chart lifecycle: create once when `el` binds (keyed on `type`/`title`); `$effect`
  calls `chart.update(data)` on data change and recreates the chart only when
  `theme.current` changes. Cleanup calls `chart.destroy()` (no try/catch).
- ShutdownModal: `runMutation(() => shutdown())`; on `!ok` show inline error and stay
  open; only on ok schedule `window.close()` + close.
- EditMemoryModal: `applyRename` gated by `busy`, rename input gets `aria-label` and
  Enter-to-submit; ModalHost wraps `<EditMemoryModal>` in `{#key m.name}` (removes the
  two suppressed warnings).

## Phases (execution order)

1. **Pure-logic fixes** (no UI, no rebuild): `highlightTools` single-pass + `escapeHtml`
   `'`. TDD: write the collision/overlap test first.
2. **Test streamlining** (tests/ only): `helpers.ts`; global `afterEach`; drop
   `smoke.test.ts`; merge `executions.test.ts` → `executions-queue.test.ts`; drop
   duplicate `format` case; migrate the 11 fetch-stub files; new coverage for `config`
   store, `stats` store, `client.putJson`, `CreateMemoryModal`, and `pollersForView`
   (extracted from `App.svelte`).
3. **Token/style fixes**: Button + ListPanel `#fff` → token; add `--chart-2..6`;
   ChartPanel reads chart tokens.
4. **Modal dedup + ConfirmModal**: `createModalAction`; shared modal CSS; `ConfirmModal`
   + migrate Remove/Delete/Cancel/Shutdown (folds in finding 2); EditMemoryModal busy +
   Enter (finding 3); `{#key m.name}` (finding 4); delete dead `?? 'Failed'`.
5. **Card dedup + a11y**: ListPanel/ProjectsPanel compose `<Card>` surface; Header menu
   a11y (`aria-haspopup`/`aria-expanded`/Escape); input `aria-label`s (finding 13);
   Modal focus trap (finding 14).
6. **ChartPanel update() + final verify**: `chart.update`, recreate-on-theme, remove
   suppressor + try/catch, extend typings; full `check`/`test`/`lint`, `npm run build`,
   commit regenerated bundle, **manual runtime verification** (charts update with no
   console errors in light+dark; modals; log highlighting).

## Test plan / streamlining detail

- **Drop:** `smoke.test.ts` (asserts framework only).
- **Merge:** `executions.test.ts` into `executions-queue.test.ts` (same component, two
  styles); keep the "hides unlogged tasks" assertion.
- **Dedup:** one of the two near-identical `format` highlight cases.
- **Shared:** `stubFetchJson`/`stubFetchRoutes`/`errBody`/`okBody`/`exec` replace the
  hand-rolled fetch stubs in ~11 files; global `afterEach(vi.restoreAllMocks)` in
  `setup.ts` replaces per-file copies.
- **New coverage:** `config.svelte.ts` (poll dedup: identical body → no reference
  change; new body → updates), `stats.svelte.ts` (`refresh` two fetches, `clear`),
  `client.putJson`, `CreateMemoryModal` (validation gating + mutation error inline),
  `pollersForView` (overview/logs/stats → correct poller sets).
- Each phase ends green on `npm test`. Net test count drops ~3 files of boilerplate
  while adding real coverage.

## Error handling

- Mutation failures continue to surface inline via the existing `error` prop on `Modal`
  / `ConfirmModal`; no new error channels.
- ShutdownModal failure now visible instead of silently closing.
- Chart `destroy()` runs without try/catch; if the runtime check shows a residual race,
  the fallback is to reinstate the suppressor (documented in Phase 6).

## Out of scope

- No changes to `src/serena/dashboard.py` or any endpoint/shape (frozen contract).
- No new dashboard features (the `dashboard-ideas.md` backlog is untouched).
- Not moving the dirty/busy guard into `Modal.svelte` (rejected in favor of
  `ConfirmModal` + per-modal guards).

## Risks

- **Phase 6 suppressor removal** — highest risk; mitigated by manual runtime
  verification and a documented rollback (reinstate suppressor).
- **Visual parity** — Card composition (Phase 5) and modal CSS extraction (Phase 4)
  must not alter rendered spacing/borders; verified side-by-side in light + dark at
  Phase 6.
- **Bundle staleness** — single rebuild at the end; CI enforces freshness.
</content>
</invoke>
