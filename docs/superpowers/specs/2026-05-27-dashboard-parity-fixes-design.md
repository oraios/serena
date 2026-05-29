# Serena Dashboard — Parity & Bug Fixes — Design Spec

**Date:** 2026-05-27
**Status:** Approved for planning (pending user spec review)
**Author:** Brainstorming session (Pavlo Basanets + Claude)
**Inputs:** `dashboard-parity-review/DISCREPANCIES.md` (the testing findings), live
old-vs-new comparison screenshots in `dashboard-parity-review/shots/`.

## 1. Summary

The Svelte dashboard (branch `dashboard`) replaced the legacy jQuery dashboard and is
close to parity, but live testing surfaced a set of functional regressions and one bug.
This spec defines the fixes. The guiding intent: **fix genuine behavior losses and the
bug, keep the redesign otherwise**, with three explicit legacy restorations the user
requested (config field labels/order, Last Execution card, full execution-cancel UX) and
one explicit removal (the new `Client` config field).

The work is **frontend-only**. `src/serena/dashboard.py` and its endpoints remain a
**frozen contract** — no backend changes. After changes, `npm run build` regenerates the
committed `src/serena/resources/dashboard/` output (CI staleness gate).

The secondary goal is **clean code with minimal repetition**: the fixes that touch many
files (modal error handling, charts) are routed through a few small shared abstractions
rather than copy-paste.

## 2. Scope

### In scope

| # | Fix | Area |
|---|-----|------|
| 1 | Restore **full legacy execution-cancel UX**: cancel ✕ on all queue items (running → confirm modal, queued → direct cancel) **and** the separate "Cancelled Executions" panel | ExecutionsQueue, executions store, CancelExecutionModal, new CancelledExecutions panel |
| 2 | JetBrains-backend mode → show "Using JetBrains backend", hide language badges/Add button | ConfigCard |
| 3 | Surface mutation errors **inline in the modal, keep it open** (stop silent failures) | RemoveLanguage, CreateMemory, DeleteMemory, EditMemory, EditSerenaConfig, CancelExecution (AddLanguage already does this) |
| 4 | Unsaved-changes confirm on close | EditMemory, EditSerenaConfig |
| 5 | Token bar → **two side-by-side single-series bar charts** (Input / Output by tool), each auto-scaled, with on-bar value labels | Stats |
| 6 | Re-add **Total Tokens** summary row | StatsSummary |
| 7 | Fix `removeChild` console errors on chart teardown | ChartPanel |
| 8 | **Restore Last Execution** card: bordered green-tinted success box, status word, monospace `#task_id` | LastExecution |
| 9 | **Restore legacy config labels + order**; **remove `Client`**; restore path tooltips | ConfigCard |
| 10 | Set dynamic `document.title` from active project | App shell |
| 11 | News list explicit newest-first sort | NewsSection |

### Out of scope (keep the redesign)

Stats page left-alignment; `MEMORIES`/`Add Language` button wording; banner per-entry
`border` flag; empty-state text wording; auto-rotating arrow-less banners; boxed
registered-project rows; deletable memories. No backend changes.

## 3. Shared abstractions (the DRY core)

Three small reusable pieces carry the cross-cutting fixes so no pattern is duplicated:

### 3.1 `runMutation(fn)` — `dashboard/src/lib/api/mutation.ts` (new)

The API surfaces failures **two ways**: `client.ts` throws `ApiError` on non-2xx HTTP,
but backend mutation failures come back as **HTTP 200** with a `StatusResponse`
(`{ status: 'success' | 'error'; message? }`). A single helper normalizes both:

```ts
export async function runMutation<T extends { status?: string; message?: string }>(
  fn: () => Promise<T>,
): Promise<{ ok: boolean; message?: string; data?: T }> {
  try {
    const res = await fn();
    if (res && res.status === 'error') return { ok: false, message: res.message, data: res };
    return { ok: true, data: res };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : 'Request failed' };
  }
}
```

Every mutating modal calls `runMutation(() => endpointFn(...))` instead of hand-rolling
error checks. The resolved body is returned as `data`, so callers that need extra fields
(e.g. cancel's `was_cancelled`) read it from the same helper — no second code path.

### 3.2 `Modal.svelte` gains an optional `error?: string` prop

`Modal` renders a single red error block (`<p class="error">{error}</p>`, styled with
`var(--log-error)`) when `error` is set — centralizing the markup/styling that today
lives bespoke only in `AddLanguageModal`. Each modal keeps local `let busy = $state(false)`
and `let error = $state('')`, runs the mutation via `runMutation`, and on `!ok` sets
`error` (modal stays open) or on `ok` calls `onclose()`. `AddLanguageModal` is refactored
onto this shared prop too (removing its private error markup).

### 3.3 `confirmDiscard(isDirty)` — `dashboard/src/lib/confirmDiscard.ts` (new)

```ts
export const confirmDiscard = (isDirty: boolean): boolean =>
  !isDirty || window.confirm('You have unsaved changes. Discard them?');
```

`EditMemoryModal` and `EditSerenaConfigModal` track a `dirty` derived from
current-vs-initial textarea content and gate every close path (×, backdrop, Esc, Cancel)
through `confirmDiscard(dirty)`.

## 4. Stats (`charts.ts`, `ChartPanel.svelte`, `StatsPage.svelte`, `StatsSummary.svelte`)

- **Two single-series bar charts.** Replace `toGroupedBarData` with a generic
  `toSingleSeriesBar(stats, key: 'input_tokens' | 'output_tokens', label)`. `StatsPage`
  renders two `ChartPanel type="bar"` instances — "Input Tokens (by tool)" and
  "Output Tokens (by tool)" — each auto-scaling its own y-axis. (Frappe 1.6.2 has no
  dual-axis or log scale; this is the native way to make both series readable.)
- **On-bar value labels.** `ChartPanel` gains an optional `valuesOverPoints?: boolean`
  prop passed through to the Frappe `Chart` config (`valuesOverPoints: 1`), restoring the
  old datalabels behavior on bars. (Pie slice values remain in the legend — Frappe pies
  have no on-slice label option; documented constraint.)
- **`removeChild` fix.** Wrap the `$effect` teardown's `chart.destroy()` in
  `try { … } catch { /* frappe removeChild race */ }`.
- **Total Tokens row.** `StatsSummary` adds a fourth row, `input_tokens + output_tokens`.
  Existing redesigned row labels are kept; only the row is added.

## 5. Overview components

### 5.1 ConfigCard

- **Restore legacy fields, order, labels:** Version → Active Project → Languages (inline in
  the grid) → Context → Active Modes → File Encoding. Restore the legacy labels
  ("Active Project", "Active Modes", "File Encoding").
- **Remove the `Client` field** entirely.
- **Restore path tooltips** (`title=`) on Active Project (project.yml path), Context, and
  each Active Mode.
- **JetBrains mode:** when `jetbrains_mode` is true, render "Using JetBrains backend" in
  place of the language badges and suppress the Add Language button.
- Active Tools / Memories collapsibles and the footer (Config Guide link + Edit Global
  Serena Config) are unchanged.

### 5.2 LastExecution

Restore the bordered, green-tinted success box: status word (from
`ResponseLastExecution.status`, e.g. "Succeeded"), the task `name`, and the monospace
`#${task_id}` on the right. Theme-aware via existing tokens (success accent
`--success`/green tint). Non-success states reuse the legacy styling for failed/abandoned.

### 5.3 ExecutionsQueue + Cancelled Executions (full legacy restore)

- **Cancel control on all items.** Render the cancel ✕ for every queue row.
- **Mechanics (legacy):** clicking ✕ on a **running** item opens `CancelExecutionModal`
  (confirm); on a **queued** (non-running) item cancels **directly** (no modal).
- **executions store** gains `cancelled: QueuedExecution[]` (client-side list, as in
  legacy) and a `cancelError: string`. `cancel(execution)` calls
  `runMutation(() => cancelExecution(task_id))` and reads `data.was_cancelled` from the
  returned body to distinguish a true cancel from "already finished". On a true cancel the
  execution is pushed to `cancelled` (flagged abandoned if it was running); on `!ok` the
  running path shows the message inline in `CancelExecutionModal` (shared `error` prop) and
  the direct queued path sets `cancelError`, rendered as one inline line under the queue.
- **CancelledExecutions panel** (new component): a separate overview panel listing
  cancelled/abandoned tasks with `#task_id`, matching the legacy section. Hidden when
  empty.

## 6. App shell & News

- **`App.svelte`:** an `$effect` sets
  `document.title = project ? \`${project} – Serena Dashboard\` : 'Serena Dashboard'`,
  reading the active project name already available from the config store (single source;
  no new endpoint).
- **`NewsSection`:** sort the `news` entries by id (YYYYMMDD) **descending** before
  rendering, matching the legacy newest-first order.

## 7. Data flow & error handling

- No new endpoints; all calls go through existing `endpoints.ts`. `runMutation` is the one
  place that interprets the dual success/error contract.
- Modal failure → inline error, modal stays open, user retries or cancels. Success →
  modal closes (and, for cancels, the item moves to the Cancelled panel).
- Polling cadences, in-flight guards, and the unchanged-skip optimization are untouched.

## 8. Testing

**Vitest (logic):**
- `runMutation`: thrown `ApiError` → `{ok:false}`; `{status:'error',message}` →
  `{ok:false,message}`; success → `{ok:true}`.
- `confirmDiscard`: not-dirty → true without prompt; dirty → defers to `window.confirm`.
- `toSingleSeriesBar`: correct per-tool series for input vs output keys.
- StatsSummary Total Tokens = input + output.
- ConfigCard mapping: JetBrains mode hides languages; `Client` absent; field order/labels.

**Component (@testing-library/svelte):**
- A representative modal shows the inline error and stays open when the mutation fails.
- ExecutionsQueue renders a cancel ✕ for a queued (non-running) item and calls direct
  cancel; running item opens the modal.
- CancelledExecutions renders after a cancel and is hidden when empty.

**Build gate:** `npm run lint && npm run check && npm test`, then `npm run build` and
commit regenerated `src/serena/resources/dashboard/` (CI fails on stale output).

## 9. Risks / notes

- **Pie on-slice labels** can't be restored in Frappe 1.6.2 (no option); values stay in
  the legend. Accepted.
- **Two bar charts** change the Stats layout from 4 to 5 chart panels; acceptable and
  more readable.
- **Cancelled list is client-side only** (as in legacy) — it resets on reload; there is no
  backend endpoint for it. Matches old behavior.
- Keep components small and single-purpose; the new `CancelledExecutions` panel and the
  shared helpers are independently testable.
</content>
