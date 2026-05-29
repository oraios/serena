# Serena Dashboard — Bug-fix round F1–F4 (Design Spec)

**Date:** 2026-05-28
**Status:** Approved for planning
**Author:** Brainstorming session (Pavlo Basanets + Claude)
**Source:** Findings from the manual Playwright UI test pass — see `dashboard-ui-test-findings.md`.

## 1. Summary

Fix four defects found during live UI testing of the Svelte 5 dashboard. Two are
real bugs (P2): editor modals silently swallow load failures (F1), and the Logs
viewer opens at the oldest line instead of tailing the newest (F2). Two are
polish/a11y items (P3): the view tabs lack an accessible "current view" signal
(F3), and the Create Memory modal has no title heading (F4).

All changes are **frontend-only**. The Flask backend in `src/serena/dashboard.py`
remains a **frozen contract** — no endpoint names, shapes, ports, or host-header
checks change. Each fix is isolated to one or two components plus its existing
test file.

## 2. Goals & Non-Goals

### Goals
- Editor modals (`EditSerenaConfigModal`, `EditMemoryModal`) surface load
  failures and prevent Save until content has actually loaded.
- The Logs viewer tails the newest line on first entry, preserving the existing
  "sticky only when at bottom" behavior for subsequent updates.
- The active view tab is announced to assistive tech.
- The Create Memory modal has a title heading, consistent with the other modals.
- Net-new / extended test coverage for each fix.

### Non-Goals
- No backend changes; no endpoint contract changes.
- No YAML pre-save validation, no log level-filter/search, no hash routing — those
  remain in the improvement-suggestions backlog, out of scope here.
- No change to `runMutation` itself, the `Modal` primitive's API, or theming.

## 3. The Fixes

### F1 — Editor modals surface load (GET) errors; Save blocked until loaded

**Problem.** The load path of `EditSerenaConfigModal.load()` calls
`getSerenaConfig()` directly. `getJson` only throws `ApiError` on non-2xx; a
soft-error (`HTTP 200 {status:'error', message}`) is *not* thrown, so `.content`
is `undefined`, the textarea binds blank, **no error is shown, and Save stays
enabled** — risking an overwrite of the global config with empty content.
`EditMemoryModal` has the same swallow, mitigated only by a `?? ''` fallback (no
error surfaced either).

**Decision (approved).** Apply the fix to **both** editor modals.

**Changes.**

1. **`src/lib/api/types.ts`** — add the optional soft-error fields to the two
   GET-load response types. These GETs legitimately return *either* the success
   shape *or* `{status:'error', message}`; modeling both also satisfies
   `runMutation`'s `T extends { status?: string; message?: string }` generic
   constraint:
   ```ts
   export interface ResponseGetMemory {
     content: string;
     memory_name: string;
     status?: string;
     message?: string;
   }
   export interface ResponseGetSerenaConfig {
     content: string;
     status?: string;
     message?: string;
   }
   ```

2. **`src/components/modals/EditSerenaConfigModal.svelte`** and
   **`src/components/modals/EditMemoryModal.svelte`** — route the load through the
   existing `runMutation` and gate Save on a `loaded` flag:
   ```ts
   let loaded = $state(false);
   let loadError = $state('');
   async function load() {
     // getSerenaConfig() here; getMemory(name) in the memory modal
     const res = await runMutation(() => getSerenaConfig());
     if (!res.ok) {
       loadError = res.message ?? 'Failed to load configuration.';
       return;
     }
     const c = res.data?.content ?? '';
     content = c;
     initialContent = c;
     loaded = true;
   }
   ```
   - `Modal` receives `error={loadError || action.error}` (reuses the existing
     `role="alert"` error slot — no `Modal` API change).
   - Save button: `disabled={!loaded || action.busy}`.
   - The memory modal's `(await getMemory(name)).content ?? ''` swallow and the
     config modal's no-guard `content = loaded` assignment are both replaced by
     the above.

**Acceptance.**
- When the load endpoint returns the soft-error channel, the modal shows the
  backend `message` inline and the **Save button is disabled**.
- When the load succeeds, the textarea is populated and Save is enabled.
- `runMutation` is unchanged; no `fetch` is added to a component.

### F2 — Logs viewer scrolls to bottom on first load (regression vs `main`)

**Problem.** `LogViewer.svelte`'s `$effect` only scrolls when *already* within
40px of the bottom. On entry, the logs poller's first
`/get_log_messages {start_idx:0}` returns the whole backlog rendered in one pass,
so `scrollTop` is 0 and the check is false — the viewer stays pinned to the
oldest line. The legacy jQuery dashboard scrolled to bottom **unconditionally on
initial load** (`dashboard.js:1277`) and applied the `wasAtBottom`-gated sticky
scroll only to **subsequent** polls (`dashboard.js:1311–1327`); the rewrite
collapsed both into the single gated effect.

**Change — `src/components/logs/LogViewer.svelte`:**
```ts
let didInitialScroll = false;
$effect(() => {
  void lines.length; // re-run when new lines arrive
  if (!el || lines.length === 0) return;
  if (!didInitialScroll) {
    didInitialScroll = true;
    queueMicrotask(() => { if (el) el.scrollTop = el.scrollHeight; });
    return;
  }
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  if (atBottom) queueMicrotask(() => { if (el) el.scrollTop = el.scrollHeight; });
});
```

**Acceptance.**
- On first non-empty render the viewer is scrolled to the bottom (newest line).
- After that, new lines pin to the bottom only when the user is already at the
  bottom; scrolling up is not interrupted (existing behavior preserved).

### F3 — `aria-current="page"` on the active view tab

**Problem.** The Overview / Logs / Stats buttons (in `Header.svelte`, inside a
`<nav>`) convey the active view only visually (underline/accent). No
`role`/`aria-selected`/`aria-current`, so assistive tech gets no active-view
signal.

**Decision (approved).** Use `aria-current="page"` (semantically correct for
nav-style view switches; minimal and non-invasive — no `role=tablist` / panel
wiring).

**Change — `src/components/shell/Header.svelte`:** add
`aria-current={active === '<view>' ? 'page' : undefined}` to each of the three tab
buttons, alongside the existing `class:active`. No structural change.

**Acceptance.** The active tab button exposes `aria-current="page"`; the inactive
ones expose no `aria-current`. Visual styling unchanged.

### F4 — Create Memory modal gets a title heading

**Problem.** `CreateMemoryModal` opens with body paragraphs only; unlike the other
modals it renders no `<h3>` title (the `Modal` primitive renders one when given a
`title` prop).

**Change — `src/components/modals/CreateMemoryModal.svelte`:** add
`title="Create Memory"` to the `<Modal>` invocation.

**Acceptance.** The modal shows a "Create Memory" heading; the dialog gains an
accessible name. No other content changes.

## 4. Testing

Extend the existing Vitest specs (helpers in `tests/helpers.ts`: `errBody` /
`okBody` for the two backend channels, `stubFetchJson` / `stubFetchRoutes`):

- **`tests/edit-serena-config-modal.test.ts`** — load returns `errBody` ⇒ error
  text rendered and Save disabled; load returns `okBody({content})` ⇒ textarea
  populated and Save enabled.
- **`tests/edit-memory-modal.test.ts`** — same two assertions for the memory load
  path (in addition to existing rename/dirty coverage).
- **`tests/log-viewer.test.ts`** — first non-empty render scrolls to bottom
  (assert `scrollTop === scrollHeight`, mocking layout metrics as needed); a
  subsequent update while scrolled up does **not** force-scroll.
- **`tests/title.test.ts`** (or a small header test) — active tab has
  `aria-current="page"`, inactive tabs do not.
- **`tests/create-memory-modal.test.ts`** — the "Create Memory" title is present.

## 5. Build-output contract (CI-enforced)

After the source changes, run in order from `dashboard/`:
`npm run check` → `npm test` → `npm run format` → `npm run build`, then **stage
all changes** including the regenerated `../src/serena/resources/dashboard/`
(`index.html` + hashed `assets/`). A partial stage fails CI's `prettier --check`;
a stale build fails the build-output contract.

## 6. Risk

Low. Each change is local, reuses existing primitives (`runMutation`, `Modal`'s
`error`/`title`, the existing scroll math), and is covered by a unit test. The
only cross-file change is two added optional fields in `types.ts`, which is
purely additive and matches the real backend response union.
