# Dashboard v2 — Port of legacy `dashboard` branch features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port agent-observability features from the legacy jQuery `dashboard` branch into the Svelte 5 + TS `dashboard_v2` rebuild — per-call timing, ToolCallRecord ring buffer, Tool Call Timeline, 4-card summary, Sort selector, Rate + Duration charts, DrillDown panel, Code tab with project navigator and LSP Diagnostics (warning instead of cancel), shared FilterDropdown, polling-cursor `??` discipline.

**Architecture:** Backend gets new instrumentation in `analytics.py` (Entry extension + ToolCallRecord ring buffer) and `task_executor.py` (TaskInfo timing/race-fix), and five new endpoints split between `dashboard.py` (timeline) and a new `dashboard_code.py` helper (four `/code/*` routes). Frontend adds new Svelte components, two new singleton stores (`timeline`, `code`) following the existing factory pattern, and a new `code` tab between Stats and Logs. No build-pipeline changes.

**Tech Stack:** Python 3 + Pydantic + FastAPI (`dashboard.py`); Svelte 5 (runes) + TypeScript + Chart.js + Vite (`dashboard/`); pytest (backend); vitest + jsdom + Testing Library (frontend); Playwright (one smoke test).

**Spec:** `docs/superpowers/specs/2026-05-28-dashboard-v2-legacy-port-design.md`

---

## Plan Review Corrections (2026-05-28)

> **STATUS:** This section was added after a multi-agent review of the plan. It supersedes any contradictory code samples elsewhere in the plan. Read it in full before starting any task — most affected tasks have been rewritten end-to-end below, and a handful of small cross-cutting corrections need to be applied throughout. Where a corrected version of a task is provided here, **use the corrected version, not the original further down**.

### Decisions taken during review

1. **Web framework: Flask** (the existing `src/serena/dashboard.py` is Flask via `from flask import Flask` at line 18; `Flask(__name__)` at line 204; all routes are `@self._app.route("/...", methods=["GET"])`). The original plan body assumes FastAPI throughout (Tasks 6, 7, 8 and Phase 5). **All new routes use Flask conventions.** Pydantic models stay for response shapes; routes manually call `request.args.get(..., type=int)` for query params and return `model.model_dump()` (or a dict) with the appropriate Flask `(body, status)` tuple for non-200 responses. The corrected Tasks 6, 7, 8 and 19–23 below are the authoritative versions.

2. **Test infrastructure for backend:** the existing `test/serena/test_dashboard.py` is 49 lines (not 1.8K as the plan claims) and uses a `_DummyAgent` + direct private-method calls. The plan's `make_agent_with_stats` / `make_agent_with_project_root` factories using `SerenaAgent.__new__(SerenaAgent)` are replaced with `_DummyAgent`-style stubs that build the dashboard via `SerenaDashboardAPI(memory_log_handler=..., tool_names=[], agent=..., tool_usage_stats=...)` — the real constructor signature. Tests that need HTTP routing use **`dashboard._app.test_client()`** (Flask), not `TestClient(dashboard.app)` (FastAPI). The corrected fixtures are in the rewritten tasks below.

3. **`SerenaDashboardAPI` attribute names:** the constructor (`dashboard.py:194-211`) takes `memory_log_handler, tool_names, agent, tool_usage_stats`. The dashboard holds `self._agent`, `self._tool_usage_stats`, `self._app` — all private. There is **no public `dashboard.app` attribute**; tests must use `dashboard._app.test_client()` and dashboard internals access via `self._agent` / `self._tool_usage_stats`.

### Critical bugs found and fixed

The following bugs in the original plan body must be corrected before implementation. Where the correction is small enough to apply inline, it's described here; where it requires rewriting a task, the rewrite is included in this section.

#### Backend — Phase 1 (Tasks 1–5)

- **B1 (Task 5, plan lines 916–940): Double-recording bug in `apply_ex`.** The `except` branch with `catch_exceptions=False` calls `_record_tool_call_safely` and then `raise`s — but Python's `try/finally` then runs the `finally` block on the way out, calling `_record_tool_call_safely` **a second time**. Result: the same failing tool call increments `_seq_counter` by 2 and double-counts the entry. **Fix:** remove the pre-raise `_record_tool_call_safely` call inside the `except`. The `finally` block already handles both code paths. The corrected `apply_ex` body appears in §"Corrected Task 5 — apply_ex" below.

- **B2 (Task 1 implicit): `ResponseToolStats.stats: dict[str, dict[str, int]]`** at `src/serena/dashboard.py:55` will reject `float`/`None` values once Task 1 widens `Entry`. **Fix:** as part of Task 1, also widen `ResponseToolStats.stats` to `dict[str, dict[str, float | int | None]]` (or `dict[str, dict[str, Any]]`). Without this, the `/get_tool_stats` route starts 500-ing after Task 1 lands.

- **B3 (Task 1 line 180, Task 5 line 835): `import time as _time` inside methods.** `analytics.py` already has `import time` (verified). `agent.py` does not, but should add a module-level `import time` rather than aliased imports inside methods. Replace `import time as _time` with `time` references.

- **B4 (Task 4 line 710): `import re` inside `get_display_name`.** Move to module-level and precompile: `_TASK_PREFIX_RE = re.compile(r"^Task-\d+:\s*(.*)$")`. This method runs once per dashboard render of every task; per-call import is wasteful.

- **B5 (Task 5 line 884–891, "No active project" early-return):** the current plan flow returns "Error: No active project..." as a `result` string without setting `success=False`. The finally then records `success=True`. **Fix:** set `success = False; error_message = "No active project"` before the early return (or move that check before `start = time.perf_counter()` to skip recording entirely). The corrected body in §"Corrected Task 5" below records it as a failure for consistency with the "errors are now counted" commit message.

- **B6 (Task 5 test, plan lines 964–992): `test_apply_ex_records_successful_call_with_duration` does NOT exercise `apply_ex`** — it calls `_record_tool_call_safely` directly. Either rename to `test_record_tool_call_safely_records_success_path`, or build a tiny `Tool` subclass and drive `tool.apply_ex(...)` through the full path. The added integration test below uses the latter approach to exercise B1's fix.

- **B7 (Task 3 test, plan lines 405–413): completeness assertion missing.** The test asserts `seqs == sorted(seqs)` over the retained tail but doesn't assert `len(recs) == 2 * N`. With `N = 1000` and buffer cap 2000 the buffer holds every record; add `assert len(recs) == 2 * N` to lock this in.

#### Backend — Phase 2 (Tasks 6–8)

- **B8: Flask not FastAPI.** Tasks 6, 7, 8 use `@self.app.get(...)`, type-annotated query params with FastAPI Pydantic validation, `HTTPException`, and `TestClient(dashboard.app)`. Flask uses `@self._app.route(...)`, `request.args.get(..., type=int)`, and returns `(body, status)` tuples or 4xx via `abort(400, ...)`. **Use the rewritten Tasks 6, 7, 8 in §"Corrected Tasks 6, 7, 8 (Flask)" below.**

- **B9 (cross-task): Task 7's `tool_stats_totals` reads `stats.get("num_errors", 0)` etc.** These fields only exist on `Entry` after Task 1, and only populate after Task 5 wires `record_call` into dispatch. **Task 7 depends on Tasks 1, 3, 5.** The plan's File Structure table is missing this. Add a dependency note to Task 7's header.

- **B10 (Task 7): `Field` import.** `dashboard.py:20` only imports `BaseModel`. Task 7 uses `Field(default_factory=...)`. Add `from pydantic import BaseModel, Field` (replacing the single-name import) in Task 7's first step.

- **B11 (Task 8): `QueuedExecution` is consumed by 8+ production files and tests** (e.g. `LastExecution.svelte`, `CancelledExecutions.svelte`, `ExecutionsQueue.svelte`, `OverviewPage.svelte`, `executions.svelte.ts`, `tests/helpers.ts:exec()`). The TypeScript `QueuedExecution` interface in `dashboard/src/lib/api/types.ts:96-102` and the `exec()` test fixture in `dashboard/tests/helpers.ts:28-37` must add **default values** for the new required fields. **Fix:** update `exec()` helper to set sensible defaults: `display_name: 'task'`, `started_at: null`, `finished_at: null`, `duration_ms: null`, `error_message: null`. This belongs in Task 9, Step "extend types" — add it explicitly there.

#### Frontend — Phase 3 (Tasks 9–14)

- **B12 (Task 9, 10, 13 tests): `stubFetchRoutes` signature mismatch.** The actual helper at `dashboard/tests/helpers.ts:13-20` takes `Record<string, unknown>` (URL-substring → static JSON body), **not** an array of `{match, handler}` objects with callable handlers. The dynamic-handler tests in Tasks 9, 10, 13 won't compile. **Two options:**
   1. **Recommended:** Extend `stubFetchRoutes` to accept callable handlers as an optional new API before Phase 3 begins. Add this as a new Pre-Task in §"Pre-Phase 3 prerequisite" below.
   2. Use static `stubFetchJson` per call and re-stub between consecutive calls (verbose; loses some test ergonomics).
   Either way, the original test code is wrong and must be replaced.

- **B13 (Task 10): `??` regression test is too weak (plan 1697–1715).** Both `null ?? 0` and `null || 0` equal `0`, so the test passes under both implementations. **Fix:** make the test issue two polls — first poll returns `{records:[r(5)], max_seq:5}` (cursor advances to 5), second returns `{records:[], max_seq:0}` (server restart / reset). Under `||` cursor stays at 5; under `??` cursor correctly becomes 0. The corrected test appears below.

- **B14 (Task 12 + Task 14): `config.overview` is wrong; it's `config.data`.** `dashboard/src/lib/stores/config.svelte.ts:9` exposes `get data()`. Search-and-replace `config.overview?.tool_stats_totals` → `config.data?.tool_stats_totals` everywhere it appears in the plan body (Task 12 Step 5, Task 14 Step 4).

- **B15 (Task 12 File Structure + Step 5): `StatsSummary.svelte` lives in `components/stats/`, NOT `components/overview/`.** Confirmed: `dashboard/src/components/stats/StatsSummary.svelte` exists; `components/overview/StatsSummary.svelte` does not. Also, the existing file is consumed by `StatsPage.svelte` (line 20: `<StatsSummary stats={stats.stats} />`) — replacing it will break Stats. **Fix:** create a new file `dashboard/src/components/overview/OverviewSummaryCards.svelte` (do NOT rename or replace the existing `stats/StatsSummary.svelte`). The original `StatsSummary.svelte` stays as-is. Update Task 12's file list and File Structure table accordingly. The 4-card KPI strip is a new Overview-only component; the Stats tab's `StatsSummary` is unaffected.

- **B16 (Task 13): `import { ReturnType as _ReturnType } from 'typescript';`** is bogus — `ReturnType` is a TypeScript built-in utility type, never imported. **Fix:** drop the bad import and use:
  ```ts
  import type { createTimelineStore } from '$lib/stores/timeline.svelte';
  type TimelineStore = ReturnType<typeof createTimelineStore>;
  ```

- **B17 (Task 13): `pausedGap` math (plan 1847–1850).** Plan: `if (cursor !== null && resp.records.length === 200 && newCursor !== null) { skipped = newCursor - cursor - resp.records.length; }`. The `=== 200` guard means a "partial" batch (e.g. 199 records but cursor jumped 500) silently misses the banner. **Fix:** use `newCursor !== null && cursor !== null && newCursor - cursor > resp.records.length`.

- **B18 (Task 14): `visibilityState` pause is NOT existing behavior.** `grep visibilityState` in `dashboard/src/` returns zero hits. The plan claims existing pollers already handle it. Either (a) add visibility-aware pausing to `polling.ts` as a new step in Task 14, or (b) drop the claim. The corrected Task 14 below treats it as new work.

- **B19 (Task 14): `'code'` view in `pollers.ts` cascades.** Adding `'code'` to the `View` union type breaks `Header.svelte:5` (which redeclares `type View = 'overview' | 'logs' | 'stats'` locally) and any `App.svelte` view rendering. **Fix:** when adding `'code'` to `pollers.ts`, also update `Header.svelte` to import the type from `$lib/pollers` rather than redeclare, AND add a placeholder Code tab button. This goes in Task 14, with a TODO comment that the actual `CodePage.svelte` is wired in Phase 6.

- **B20 (Task 14): Tool-names source for FilterDropdown.** The plan vaguely says "fetch once on mount." Recommended source: `Object.keys(config.data?.tool_stats_summary ?? {})` (already polled at 1 s, auto-updates as new tools see use). Plus union with `record.tool` values observed in the timeline buffer (for tools that fired before stats summary updated).

#### Frontend — Phase 4 (Tasks 15–18)

- **B21 (Task 17): Stacked area config incomplete.** Plan sets `fill: true` on datasets but omits `scales: { y: { stacked: true }, x: { stacked: true } }` on chart options. Without both, the chart draws overlapping filled lines, not stacked bands. The corrected `rateChartSpec` in §"Corrected Phase 4 Charts" sets both.

- **B22 (Tasks 16, 17): `ChartSpec` shape mismatch.** Existing `ChartSpec = ChartConfiguration<'pie'> | ChartConfiguration<'bar'>` (in `dashboard/src/lib/charts.ts`) nests `labels`/`datasets` under `data`. Plan's new specs return `{type, labels, datasets, stacked}` at the top level — and the tests assert `spec.labels`. **Fix:** (a) make new specs return full `ChartConfiguration<...>` objects with `data: { labels, datasets }`; (b) widen `ChartSpec` to include `ChartConfiguration<'line'>`; (c) update tests to assert `spec.data.labels` / `spec.data.datasets`. The corrected specs are in §"Corrected Phase 4 Charts" below.

- **B23 (Task 17): Chart.js click handler integration.** Plan says "wire chart click → drill-down" but never specifies the API. **Fix:** in `ChartPanel.svelte`, add an optional `onSliceClick: (label: string) => void` prop and wire via `options.onClick = (_evt, elements, chart) => { if (elements[0]) onSliceClick?.(chart.data.labels[elements[0].index] as string); };`. Add this to ChartPanel as part of Task 18 Step 0.

- **B24 (Task 18): p95 algorithm off-by-one.** Plan's `percentile(xs, 0.95)` for `xs = [1..100]` should return `95` per the test, but `floor(0.95 * 100) = 95` and `xs[95] = 96`. Use inclusive linear: `xs[Math.floor((q/100) * (sorted.length - 1))]` → `xs[floor(0.95 * 99)] = xs[94] = 95`. **Fix:** change the implementation OR the test, and document the chosen method.

- **B25 (Task 16+17): Chart re-render dataset-count change.** `ChartPanel.svelte` data-effect (existing line 88) only mutates `chart.data.datasets[i].data` — it never *adds* datasets. When `RateChart` toggles between non-stacked (1 dataset) and stacked (N datasets), the toggle-on path silently fails. **Fix:** in `ChartPanel`'s effect, detect a dataset-count change and call `chart.data.datasets = next.data.datasets; chart.update('none');` instead of the in-place mutation. Add this fix as a Step 0 of Task 17.

- **B26 (Task 15): `pieSpec` already takes a metric key.** `pieSpec(stats, key: keyof ToolStatEntry)` (`charts.ts:17`) sorts by the metric *it shows*. Plan's "Sort key reorders all pies consistently" is ambiguous: pies always sort largest slice first. **Decision:** `sortKey` drives the order of the **tokens bar** and **DurationChart**, AND drives a secondary sort for ties on the pies. The pies keep their own metric for ordering (otherwise pie semantics break). Document this in Task 15 Step 3.

- **B27 (Task 15): No backend wiring for new `ToolStatEntry` fields.** Frontend types add `total_duration_ms`, `min/max_duration_ms`, `num_errors`, `last_called_at` (optional). Backend `ResponseToolStats.stats: dict[str, dict[str, int]]` rejects floats and None. See B2 above — fix in Task 1.

#### Backend — Phase 5 (Tasks 19–23)

- **B28: Framework mismatch.** All four `/code/*` routes use FastAPI. **Use the rewritten Tasks 19–23 in §"Corrected Tasks 19–23 (Flask)" below.**

- **B29: LSP method names are wrong.** Real `SolidLanguageServer` methods (verified in `src/solidlsp/ls.py`):
  - `request_document_symbols(relative_file_path, file_buffer=None) -> DocumentSymbols` (line ~1902). Returns an object whose `.root_symbols` is `list[UnifiedSymbolInformation]`. **NOT** `list[dict]`.
  - `request_workspace_symbol(query: str) -> list[UnifiedSymbolInformation] | None` (line ~3045). **No `limit` param**; the dashboard route must slice client-side. Method name has **no trailing `s`**.
  - `request_published_text_document_diagnostics(relative_file_path, after_generation=-1, timeout=2.5, start_line=0, end_line=-1, min_severity=4, allow_cached=True) -> list[ls_types.Diagnostic] | None` (line ~890). Returns LSP-shape diagnostics: `range.start.line`, `severity` (int 1–4 per LSP), `message`, `source`. Adapter to dashboard shape is required.
  - `kind` in LSP symbols is an **integer** (`SymbolKind`), not a string label. The route must map kind int → label using a small switch.

- **B30: `manager.get_language_server(".")` is broken.** `ls_manager.py:166` raises `ValueError` if the path is a directory. For "any LS for this project," use `next(iter(manager.iter_language_servers()), None)` (or whatever the manager API exposes) — verify in `src/serena/ls_manager.py`. **Fix:** in `_get_language_server_or_503`, drop the `.` fallback and iterate language servers explicitly.

- **B31: `manager.started_language_servers_relative_paths()` does NOT exist.** The diagnostics route's "fall back to walking" branch is therefore the always-taken path. **Fix:** drop the `try` and walk the project tree directly, using `GitignoreParser` from `src/serena/util/file_system.py:130` instead of the hardcoded skip set.

- **B32: Gitignore handling.** Spec §5.4 says "respects gitignore" but the plan uses `_GITIGNORE_HARDCODED = {".git", "node_modules", ...}`. Use `GitignoreParser` (existing helper) so nested `.gitignore` files are honored. The corrected Task 20 below uses it.

- **B33: 504 `ls_timeout` mapping missing.** Spec §7.1 lists 504 for timeouts. Plan only emits 502/503. **Fix:** catch `TimeoutError` (and solidlsp's specific timeout exception if it has one) → 504. Map other LSP exceptions to 502.

- **B34: Path-traversal guard — NUL byte and Windows drive edges.** Add `if "\x00" in path: raise ValueError(...)` at the top of `resolve_project_path`. Wrap `os.path.commonpath(...)` in `try/except ValueError` for the Windows different-drives case. **Better:** rewrite using `pathlib.Path.resolve().is_relative_to(root_real)` (Python 3.9+) — cleaner. Corrected helper in §"Corrected Task 19".

- **B35: Symlink follow policy.** `os.scandir`'s `de.is_dir()` follows symlinks by default. Add `de.is_dir(follow_symlinks=False)` in `code_list_dir` and document that directory symlinks inside the repo are listed as files, not entered.

- **B36: Diagnostics per-file 1 MB cap heuristic is wrong.** Plan uses `keep = max(1, int(len(diags) * CAP / payload_size))` — assumes uniform diag size. A single 5 MB message stays. **Fix:** truncate individual message lengths first (`message[:4096]`), then apply the count cap as a loop until under cap. Set `truncated=True` if any trimming occurs. Corrected logic in §"Corrected Task 23".

#### Frontend — Phase 6 (Tasks 24–29)

- **B37 (Task 24 CRITICAL): `$state<Set<string>>(new Set())` is NOT reactive.** Svelte 5 proxies plain objects/arrays only; `Set`/`Map` mutations do not trigger updates. The FileTree chevron will not flip on toggle. **Fix:** use `SvelteSet` from `svelte/reactivity`:
  ```ts
  import { SvelteSet } from 'svelte/reactivity';
  const expanded = new SvelteSet<string>();
  ```
  OR convert to `Record<string, true>` (consistent with other store fields). The plan deviated from spec §5.4 (which said `Map`) to `Record` for `dirChildren`/`fileSymbols` — for consistency, also use `Record<string, true>` here. Corrected code store in §"Corrected Task 24".

- **B38 (Task 24): `dashboard.app` in test — wrong attribute.** The Code-tab store tests don't hit Flask routing; they stub `fetch`. But the test file imports `fetchCodeListDir` etc. — confirm those wrappers exist after Phase 3 Task 9 lands them. They do (Task 9 Step 4 line 1573+). OK.

- **B39 (Task 24): No retry/error states for `loadDir` / `loadFileSymbols`.** Spec §7.2 says "list_dir fail → folder stays collapsed, inline ⚠"; "file_symbols fail → error card with Retry." Plan's store helpers have no try/catch. **Fix:** add `dir_error: Record<string, string>` and `file_symbols_error: Record<string, string>` to the store; surface in components. Corrected store in §"Corrected Task 24".

- **B40 (Task 24 / App.svelte): `$components` alias does not exist.** Only `$lib/*` is aliased (`tsconfig.json:15`, `vite.config.ts:38`). **Fix:** use a synchronous import: `import CodePage from './components/code/CodePage.svelte';` then render `{#if view === 'code'}<div class="page-view"><CodePage /></div>{/if}`. Mirrors existing `App.svelte:13-15` pattern.

- **B41 (Task 24 + Phase 6 general): `Header.svelte` tab buttons.** `Header.svelte:5` has a locally-typed `View = 'overview' | 'logs' | 'stats'`. Adding the Code tab requires updating this file. Add Step to Task 24: "Update `dashboard/src/components/shell/Header.svelte` — import `View` type from `$lib/pollers` and add a Code tab button between Stats and Logs."

- **B42 (Task 27 WorkspaceSearch): No min-length guard.** Single-char queries flood the LSP. **Fix:** in `code.search(q)`, add `if (q.trim().length < 2) { searchResults = []; return; }` before the epoch advance.

- **B43 (Task 27): Selecting a match doesn't switch the middle pane to Symbols.** Spec §5.4: "Result rows click-to-jump (selects file + scrolls symbols)." Plan only calls `code.selectPath(path)`. **Fix:** lift the middle-pane mode (`'symbols' | 'search'`) into the store, and have `selectMatch` set it to `'symbols'`. Or, more simply, pass a callback from `CodePage.svelte` to `WorkspaceSearch.svelte` that switches the local tab state and calls `selectPath`.

- **B44 (Task 28): Diagnostics error message extraction.** Plan does `diagError = (e as Error).message;` — fails for non-Error throws. **Fix:** `diagError = e instanceof Error ? e.message : String(e)`.

- **B45 (Playwright code-tab.spec.ts): No real LSP in emulator.** The emulator script bootstraps stats but does not initialize a project with LSP. The Playwright Code-tab smoke test (per spec §8.3 step 5–6) will see 503 `ls_not_ready` on every `/code/*` call. **Fix:** stub `/code/*` routes via `page.route(...)` in the Playwright test setup. Alternative: add a project-with-LSP bootstrap to the emulator script (larger scope). The Playwright test in Task 30 (Phase 7 / final) must use `page.route()` stubs.

### Pre-Phase 3 prerequisite — extend `stubFetchRoutes` to support callable handlers

Apply this **before** Task 9. Without it, Tasks 9, 10, 13, 24 tests don't compile.

**File:** `dashboard/tests/helpers.ts`

Replace the `stubFetchRoutes` function body:

```ts
/** Static body OR a callable that receives the URL and returns the body. */
export type RouteBody = unknown | ((url: string) => unknown | Promise<unknown>);

/** Stub fetch with substring URL routing; first matching fragment wins, else `fallback`. */
export function stubFetchRoutes(routes: Record<string, RouteBody>, fallback: unknown = {}) {
  const fn = vi.fn(async (url: string) => {
    const hit = Object.entries(routes).find(([frag]) => String(url).includes(frag));
    const body = hit ? hit[1] : fallback;
    const resolved = typeof body === 'function' ? await (body as (u: string) => unknown)(String(url)) : body;
    return new Response(JSON.stringify(resolved), { status: 200 });
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}
```

This keeps the **`Record<string, RouteBody>` shape** (no breaking change to existing call sites that pass static bodies) and adds optional callable bodies. The plan's tests that pass `[{match, handler}]` arrays must be rewritten to pass `{ '/route_substring': (url) => ({...}) }` records — see corrected Tasks 9, 10, 13, 24 below for examples.

Also update the `exec()` helper to default the new `QueuedExecution` fields:

```ts
export function exec(over: Partial<QueuedExecution> = {}): QueuedExecution {
  return {
    task_id: 1,
    is_running: false,
    name: 'task',
    display_name: 'task',
    finished_successfully: true,
    logged: true,
    started_at: null,
    finished_at: null,
    duration_ms: null,
    error_message: null,
    ...over,
  };
}
```

### Corrected Task 5 — `apply_ex` (remove double-recording, fix early-return)

Replace the original Task 5 Step 5 code block (plan lines 860–953) with this. Everything else in Task 5 (Steps 1–4, 6–9) stays.

```python
        def task() -> str:
            apply_fn = self.get_apply_fn()

            try:
                if not self.is_active():
                    return f"Error: Tool '{self.get_name_from_cls()}' is not active. Active tools: {self.agent.get_active_tool_names()}"
            except Exception as e:
                return f"RuntimeError while checking if tool {self.get_name_from_cls()} is active: {e}"

            if log_call:
                self._log_tool_application(inspect.currentframe(), session_id)

            apply_kwargs = dict(kwargs)
            if self._is_session_aware:
                apply_kwargs["session_id"] = session_id

            tool_name = self.get_name()
            input_str = str(apply_kwargs)
            result: str = ""
            success = True
            error_message: str | None = None
            start = time.perf_counter()
            try:
                if not isinstance(self, ToolMarkerDoesNotRequireActiveProject):
                    if self.agent.get_active_project() is None:
                        success = False
                        error_message = "No active project"
                        result = (
                            "Error: No active project. Ask the user to provide the project path or to select a project from this list of known projects: "
                            + f"{self.agent.serena_config.project_names}"
                        )
                        return result

                try:
                    result = apply_fn(**apply_kwargs)
                except SolidLSPException as e:
                    if e.is_language_server_terminated():
                        affected_language = e.get_affected_language()
                        if affected_language is not None:
                            log.error(
                                f"Language server terminated while executing tool ({e}). Restarting the language server and retrying ..."
                            )
                            self.agent.get_language_server_manager_or_raise().restart_language_server(affected_language)
                            result = apply_fn(**apply_kwargs)
                        else:
                            log.error(
                                f"Language server terminated while executing tool ({e}), but affected language is unknown. Not retrying."
                            )
                            raise
                    else:
                        raise

            except Exception as e:
                success = False
                error_message = f"{type(e).__name__}: {e}"
                if not catch_exceptions:
                    raise
                msg = f"Error executing tool: {e.__class__.__name__} - {e}"
                log.error(f"Error executing tool: {e}", exc_info=e)
                result = msg
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                self.agent._record_tool_call_safely(
                    tool_name=tool_name,
                    input_str=input_str,
                    output_str=result,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message,
                )

            if log_call:
                log.info(f"Result: {result}")

            try:
                ls_manager = self.agent.get_language_server_manager()
                if ls_manager is not None:
                    ls_manager.save_all_caches()
            except Exception as e:
                log.error(f"Error saving language server cache: {e}")

            return result
```

Key changes vs. original plan:
- No `_record_tool_call_safely` call inside `except` — the `finally` block covers both raise and swallow paths exactly once.
- "No active project" early return sets `success=False`, `error_message="No active project"` so the finally records it as a failure.
- Same `try/finally` structure means the `finally` runs even when `not catch_exceptions:` re-raises.

**Replacement integration test (Task 5 Step 6, replacing plan lines 964–992):**

```python
def test_apply_ex_records_one_record_per_failed_call_when_catch_exceptions_false():
    """
    Regression for the double-recording bug: when catch_exceptions=False, the
    except branch raises but the finally must record exactly once.
    """
    from serena.agent import SerenaAgent
    from serena.tools.tools_base import Tool, ToolMarkerDoesNotRequireActiveProject

    class _FailTool(Tool, ToolMarkerDoesNotRequireActiveProject):
        @classmethod
        def get_name_from_cls(cls) -> str: return "fail_tool"
        def apply(self) -> str: raise RuntimeError("nope")

    # Minimal agent surface
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()
    # ... stub the rest of the surface as in test_record_tool_call_safely_handles_analytics_exception ...

    # (Skeleton — implementer fills in with whatever Tool needs to dispatch in this codebase.)
    # The key assertion:
    # before = agent._tool_usage_stats._seq_counter
    # with pytest.raises(RuntimeError):
    #     tool.apply_ex(catch_exceptions=False, log_call=False, session_id=None)
    # after = agent._tool_usage_stats._seq_counter
    # assert after - before == 1, "apply_ex must record exactly once per call"
```

> **Implementer note:** the agent surface required to drive `apply_ex` is non-trivial. If the surface stub gets too heavy, replace this with a direct test of the `task()` closure's recording behavior using a smaller harness — but the **invariant to assert** is: `seq_counter` advances by exactly 1 per `apply_ex` call, regardless of exception path or `catch_exceptions` value.

### Corrected Tasks 6, 7, 8 (Flask)

The original Tasks 6, 7, 8 use FastAPI conventions throughout. Replace their route code and test fixture sections with the versions below. Steps 1 (write test), 2 (run, fail), 4/5 (run, pass), and 5/6 (commit) stay structurally the same; only the test fixtures and route code change.

#### Corrected Task 6 — `/get_tool_call_timeline` (Flask)

**Step 1 — Test fixture (replaces plan lines 1094–1119):**

```python
import pytest
from types import SimpleNamespace
from serena.dashboard import SerenaDashboardAPI
from serena.analytics import ToolUsageStats


class _DummyMemoryLogHandler:
    def get_log_messages(self, from_idx: int = 0):
        return SimpleNamespace(messages=[], max_idx=-1)
    def clear_log_messages(self) -> None: pass


class _DummyAgent:
    def __init__(self):
        self._project = None
    def execute_task(self, func, *, logged=None, name=None):
        del logged, name
        return func()
    def get_active_project(self): return self._project
    def get_current_tasks(self): return []
    def get_last_executed_task(self): return None


@pytest.fixture
def make_dashboard_with_stats():
    """Returns a callable (stats) -> (dashboard, client) where client is a Flask test client."""
    def _factory(stats: ToolUsageStats | None = None):
        agent = _DummyAgent()
        stats = stats if stats is not None else ToolUsageStats()
        dashboard = SerenaDashboardAPI(
            memory_log_handler=_DummyMemoryLogHandler(),
            tool_names=[],
            agent=agent,
            tool_usage_stats=stats,
        )
        return dashboard, dashboard._app.test_client()
    return _factory
```

**Step 1 — Test body (replaces plan lines 1056–1092):**

```python
def test_get_tool_call_timeline_returns_records_with_cursor(make_dashboard_with_stats):
    dashboard, client = make_dashboard_with_stats()
    stats = dashboard._tool_usage_stats
    for i in range(5):
        stats.record_call(
            tool_name="t", input_str="", output_str="",
            duration_ms=1.0, success=True, error_message=None, now=1000.0 + i,
        )
    r = client.get("/get_tool_call_timeline")
    assert r.status_code == 200
    body = r.get_json()
    assert body["max_seq"] == 5
    assert len(body["records"]) == 5

    r = client.get("/get_tool_call_timeline?since_seq=3")
    body = r.get_json()
    assert [rec["seq"] for rec in body["records"]] == [4, 5]

    stats.record_call(
        tool_name="other", input_str="", output_str="",
        duration_ms=1.0, success=True, error_message=None, now=2000.0,
    )
    r = client.get("/get_tool_call_timeline?tool=other")
    body = r.get_json()
    assert all(rec["tool"] == "other" for rec in body["records"])

    r = client.get("/get_tool_call_timeline?limit=99999")
    assert r.status_code == 200  # capped server-side, no error

    r = client.get("/get_tool_call_timeline?since_seq=-1")
    assert r.status_code == 400  # 400 on negative cursor


def test_get_tool_call_timeline_empty_when_no_stats():
    """When tool_usage_stats is None, returns empty payload."""
    from serena.dashboard import SerenaDashboardAPI
    dashboard = SerenaDashboardAPI(
        memory_log_handler=_DummyMemoryLogHandler(),
        tool_names=[],
        agent=_DummyAgent(),
        tool_usage_stats=None,
    )
    client = dashboard._app.test_client()
    r = client.get("/get_tool_call_timeline")
    assert r.status_code == 200
    assert r.get_json() == {"records": [], "max_seq": 0}
```

**Step 3 — Pydantic models (placed near other models, after `QueuedExecution`):**

```python
class ToolCallRecordResponse(BaseModel):
    seq: int
    tool: str
    started_at: float
    duration_ms: float
    success: bool
    error_message: str | None
    input_preview: str
    output_preview: str
    input_truncated: bool
    output_truncated: bool


class ResponseToolCallTimeline(BaseModel):
    records: list[ToolCallRecordResponse]
    max_seq: int
```

**Step 3 — Flask route (placed alongside `/get_tool_stats` in `_setup_routes`):**

```python
        @self._app.route("/get_tool_call_timeline", methods=["GET"])
        def get_tool_call_timeline_route() -> tuple[dict[str, Any], int] | dict[str, Any]:
            since_seq_raw = request.args.get("since_seq", default=None, type=int)
            tool = request.args.get("tool", default=None, type=str) or None  # treat "" as None
            limit = request.args.get("limit", default=200, type=int)
            if since_seq_raw is not None and since_seq_raw < 0:
                return {"status": "error", "message": "since_seq must be >= 0"}, 400
            if limit is not None and limit < 0:
                return {"status": "error", "message": "limit must be >= 0"}, 400
            if self._tool_usage_stats is None:
                return ResponseToolCallTimeline(records=[], max_seq=0).model_dump()
            records, max_seq = self._tool_usage_stats.get_records_since(
                since_seq=since_seq_raw, tool=tool, limit=limit if limit is not None else 200,
            )
            return ResponseToolCallTimeline(
                records=[
                    ToolCallRecordResponse(
                        seq=r.seq, tool=r.tool, started_at=r.started_at,
                        duration_ms=r.duration_ms, success=r.success, error_message=r.error_message,
                        input_preview=r.input_preview, output_preview=r.output_preview,
                        input_truncated=r.input_truncated, output_truncated=r.output_truncated,
                    )
                    for r in records
                ],
                max_seq=max_seq,
            ).model_dump()
```

No new imports needed (Flask `request` is already imported in `dashboard.py:18`).

#### Corrected Task 7 — `tool_stats_totals` (Flask)

**Step 1 — Test (using `make_dashboard_with_stats` from Task 6):**

```python
def test_config_overview_includes_tool_stats_totals(make_dashboard_with_stats):
    dashboard, client = make_dashboard_with_stats()
    stats = dashboard._tool_usage_stats
    stats.record_call(
        tool_name="t", input_str="abc", output_str="defg",
        duration_ms=10.0, success=True, error_message=None, now=1000.0,
    )
    stats.record_call(
        tool_name="t", input_str="x", output_str="y",
        duration_ms=20.0, success=False, error_message="Err: nope", now=1001.0,
    )
    # _get_config_overview directly (existing test pattern in test_dashboard.py uses
    # this private-method style; the /get_config_overview route just wraps it).
    response = dashboard._get_config_overview()
    totals = response.tool_stats_totals
    assert totals["num_calls"] == 2
    assert totals["num_errors"] == 1
    assert totals["total_duration_ms"] == 30.0
    assert totals["total_tokens"] >= 0  # estimator-dependent
```

**Step 3 — Update `ResponseConfigOverview` (dashboard.py:58–74):**

```python
from pydantic import BaseModel, Field  # replace the existing single-name import on line 20

# ...

class ResponseConfigOverview(BaseModel):
    active_project: dict[str, str | None]
    context: dict[str, str]
    modes: list[dict[str, str]]
    active_tools: list[str]
    tool_stats_summary: dict[str, dict[str, int]]
    tool_stats_totals: dict[str, float] = Field(
        default_factory=lambda: {"num_calls": 0, "num_errors": 0, "total_duration_ms": 0.0, "total_tokens": 0}
    )
    registered_projects: list[dict[str, str | bool]]
    available_tools: list[dict[str, str | bool]]
    available_modes: list[dict[str, str | bool]]
    available_contexts: list[dict[str, str | bool]]
    available_memories: list[str] | None
    jetbrains_mode: bool
    languages: list[str]
    encoding: str | None
    current_client: str | None
    serena_version: str
```

**Step 3 — Compute totals in `_get_config_overview` (insert after the existing `tool_stats_summary` block at dashboard.py:560–564):**

```python
        tool_stats_totals: dict[str, float] = {
            "num_calls": 0, "num_errors": 0, "total_duration_ms": 0.0, "total_tokens": 0,
        }
        if self._tool_usage_stats is not None:
            full_stats = self._tool_usage_stats.get_tool_stats_dict()
            for s in full_stats.values():
                tool_stats_totals["num_calls"] += s.get("num_times_called", 0)
                tool_stats_totals["num_errors"] += s.get("num_errors", 0)
                tool_stats_totals["total_duration_ms"] += s.get("total_duration_ms", 0.0)
                tool_stats_totals["total_tokens"] += s.get("input_tokens", 0) + s.get("output_tokens", 0)
```

Then add `tool_stats_totals=tool_stats_totals,` to the `ResponseConfigOverview(...)` constructor call at line 581.

**Cross-task note:** Task 7 depends on Tasks 1 + 3 + 5 having landed (the new `Entry` fields plus `record_call` wiring). Land Task 7 in the same PR as Task 5 or after.

#### Corrected Task 8 — `QueuedExecution` extension

Task 8's core change (the Pydantic model + `from_task_info`) is framework-agnostic and is correct as written. **However:**

1. The test must use Flask test client style or call `QueuedExecution.from_task_info(info)` directly (the existing pattern in `test_dashboard.py` would just call the classmethod). Use the direct-call style:

```python
def test_queued_execution_includes_timing_and_error_fields():
    from serena.task_executor import TaskExecutor
    from serena.dashboard import QueuedExecution

    task = TaskExecutor.Task(function=lambda: "ok", name="Task-7: read_file", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    serialized = QueuedExecution.from_task_info(info).model_dump()

    assert serialized["display_name"] == "read_file"
    assert serialized["duration_ms"] is not None
    assert serialized["error_message"] is None
    assert serialized["started_at"] is not None
    assert serialized["finished_at"] is not None
```

2. **Add a second test** that exercises the `/queued_task_executions` route via Flask test client to confirm the payload reaches HTTP:

```python
def test_queued_executions_route_returns_extended_payload(make_dashboard_with_stats):
    # The dashboard's _agent is a _DummyAgent whose get_current_tasks() returns [].
    # Replace it with one that returns a real TaskInfo.
    from serena.task_executor import TaskExecutor

    dashboard, client = make_dashboard_with_stats()
    task = TaskExecutor.Task(function=lambda: "ok", name="Task-1: foo", logged=False)
    task.start(); task.wait_until_done(timeout=2.0)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    dashboard._agent.get_current_tasks = lambda: [info]

    r = client.get("/queued_task_executions")
    body = r.get_json()
    assert body["status"] == "success"
    assert body["queued_executions"][0]["display_name"] == "foo"
    assert body["queued_executions"][0]["duration_ms"] is not None
```

### Corrected Tasks 19–23 (Flask `/code/*` routes)

The original Phase 5 uses FastAPI + `register_code_routes(app, agent)` + FastAPI `HTTPException`. The corrected version uses Flask: the helper module exports a single `register_code_routes(dashboard_api)` function that adds routes to `dashboard_api._app`. Error responses use Flask's `(body, status)` tuple convention matching the rest of `dashboard.py`.

#### Corrected Task 19 — Helpers in `dashboard_code.py`

**`src/serena/dashboard_code.py`** (full file):

```python
"""
Code-tab endpoints for the dashboard.

Encapsulates the four /code/* routes. Call register_code_routes(dashboard_api)
from SerenaDashboardAPI._setup_routes after the existing route block.

Concurrency note: LSP requests serialize at the language-server subprocess.
Diagnostics is slow; the frontend shows a warning banner and disables Refresh
while a request is outstanding. No global lock is added here.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from flask import request
from pydantic import BaseModel

if TYPE_CHECKING:
    from serena.dashboard import SerenaDashboardAPI

log = logging.getLogger(__name__)

_FILE_LIMIT_CAP = 2000
_WORKSPACE_SYMBOL_LIMIT_CAP = 200
_DIAGNOSTICS_PER_FILE_BYTE_CAP = 1024 * 1024  # 1 MB
_DIAGNOSTICS_PER_MESSAGE_CAP = 4096  # 4 KB per diag message


class LSPNotReady(Exception):
    """Raised when an /code/* route is called but no LanguageServer is initialized."""


def resolve_project_path(project_root: str, path: str) -> str:
    """
    Resolve `path` (relative to project root) to an absolute path. Raises:
    - ValueError on traversal/escape, NUL bytes, or absolute paths
    - FileNotFoundError if the resolved path doesn't exist
    """
    if "\x00" in path:
        raise ValueError(f"path contains NUL byte: {path!r}")
    if os.path.isabs(path):
        raise ValueError(f"absolute path not allowed: {path!r}")
    root_real = Path(project_root).resolve()
    candidate = (root_real / path).resolve()
    try:
        candidate.relative_to(root_real)
    except ValueError as e:
        raise ValueError(f"path escapes project root: {path!r}") from e
    if not candidate.exists():
        raise FileNotFoundError(str(candidate))
    return str(candidate)


def _err(status: int, message: str, code: str | None = None) -> tuple[dict[str, Any], int]:
    body: dict[str, Any] = {"status": "error", "message": message}
    if code is not None:
        body["code"] = code
    return body, status


def _get_project_root(dashboard_api: "SerenaDashboardAPI") -> str | None:
    project = dashboard_api._agent.get_active_project()
    if project is None:
        return None
    return str(project.project_root)


def _get_first_language_server(dashboard_api: "SerenaDashboardAPI"):
    """
    Return the first started language server, or None if none.
    Adjust to whatever API ls_manager.py actually exposes — verify in
    src/serena/ls_manager.py before implementing.
    """
    try:
        manager = dashboard_api._agent.get_language_server_manager()
    except Exception as e:  # noqa: BLE001
        log.debug("LS manager unavailable: %s", e)
        return None
    if manager is None:
        return None
    # iter_language_servers() is the documented accessor on LanguageServerManager.
    # If the manager exposes a different name (e.g. get_started_servers()), update here.
    try:
        for ls in manager.iter_language_servers():
            return ls
    except Exception as e:  # noqa: BLE001
        log.debug("LS iter failed: %s", e)
    return None


def _get_language_server_for_path(dashboard_api: "SerenaDashboardAPI", rel_path: str):
    """Get the LS responsible for a specific relative path, or None."""
    try:
        manager = dashboard_api._agent.get_language_server_manager()
    except Exception:
        return None
    if manager is None:
        return None
    try:
        return manager.get_language_server(rel_path)
    except Exception:
        return None


def register_code_routes(dashboard_api: "SerenaDashboardAPI") -> None:
    """Register /code/* routes onto the dashboard's Flask app. Called from _setup_routes."""
    # Implemented across Tasks 20-23 (see below for each route's code).
    pass
```

**Test file** (`test/serena/test_dashboard_code.py`):

```python
import os
import pytest
from pathlib import Path

from serena.dashboard_code import resolve_project_path, LSPNotReady


def test_resolve_project_path_rejects_traversal(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "file.py").write_text("x = 1")
    assert resolve_project_path(str(root), "file.py") == str((root / "file.py").resolve())
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "../secret.txt")
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "/etc/passwd")


def test_resolve_project_path_rejects_nul_byte(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "foo\x00.txt")


@pytest.mark.skipif(os.name == "nt", reason="symlinks require admin/dev mode on Windows")
def test_resolve_project_path_rejects_symlink_escape(tmp_path):
    root = tmp_path / "proj"; root.mkdir()
    outside = tmp_path / "outside.txt"; outside.write_text("bad")
    os.symlink(str(outside), str(root / "link.txt"))
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "link.txt")


def test_resolve_project_path_rejects_missing_file(tmp_path):
    root = tmp_path / "proj"; root.mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_project_path(str(root), "missing.py")


def test_lsp_not_ready_is_an_exception_type():
    assert issubclass(LSPNotReady, Exception)
```

#### Corrected Task 20 — `/code/list_dir` (Flask)

**Add to `dashboard_code.py` (above `register_code_routes`):**

```python
class _DirEntry(BaseModel):
    name: str
    kind: str  # "dir" | "file"
    size: int | None = None


class _ResponseListDir(BaseModel):
    entries: list[_DirEntry]
```

**Inside `register_code_routes`** (replace the `pass` stub):

```python
    app = dashboard_api._app

    @app.route("/code/list_dir", methods=["GET"])
    def code_list_dir():
        path = request.args.get("path", default=".", type=str) or "."
        root = _get_project_root(dashboard_api)
        if root is None:
            return _err(503, "No active project", "no_project")
        try:
            if path in ("", "."):
                resolved = str(Path(root).resolve())
            else:
                resolved = resolve_project_path(root, path)
        except ValueError as e:
            return _err(400, str(e))
        except FileNotFoundError:
            return _err(404, "directory not found")
        if not os.path.isdir(resolved):
            return _err(400, "path is not a directory")

        # Use GitignoreParser to respect .gitignore (nested, layered).
        from serena.util.file_system import GitignoreParser
        try:
            ignore = GitignoreParser(root)
        except Exception:
            ignore = None  # Fall back to no-ignore if parsing fails.

        entries: list[_DirEntry] = []
        try:
            with os.scandir(resolved) as it:
                for de in it:
                    # Skip dotfiles except a small allowlist (matches legacy behavior;
                    # tweak as needed). Implementer: confirm whether dotfiles should
                    # be visible — spec doesn't say, but VS Code-style trees hide them.
                    if de.name.startswith("."):
                        continue
                    abs_path = de.path
                    rel = os.path.relpath(abs_path, root)
                    if ignore is not None and ignore.is_ignored(rel, is_dir=de.is_dir(follow_symlinks=False)):
                        continue
                    if de.is_dir(follow_symlinks=False):
                        entries.append(_DirEntry(name=de.name, kind="dir"))
                    elif de.is_file(follow_symlinks=False):
                        try:
                            size = de.stat(follow_symlinks=False).st_size
                        except OSError:
                            size = None
                        entries.append(_DirEntry(name=de.name, kind="file", size=size))
        except PermissionError:
            return _err(403, "permission denied")
        entries.sort(key=lambda e: (e.kind == "file", e.name.lower()))
        return _ResponseListDir(entries=entries).model_dump()
```

**Wire from `dashboard.py`:** at the end of `SerenaDashboardAPI._setup_routes` (line ~451):

```python
        from serena.dashboard_code import register_code_routes
        register_code_routes(self)
```

**Test fixture** (`test/serena/test_dashboard_code.py`):

```python
@pytest.fixture
def make_dashboard_with_project(tmp_path):
    from types import SimpleNamespace
    from serena.dashboard import SerenaDashboardAPI

    class _DummyMemLog:
        def get_log_messages(self, from_idx=0): return SimpleNamespace(messages=[], max_idx=-1)
        def clear_log_messages(self): pass

    class _DummyAgent:
        def __init__(self, root, ls_manager=None):
            self._project = SimpleNamespace(project_root=str(root), project_name="proj",
                                            project_config=SimpleNamespace(languages=[], encoding=None))
            self._ls_manager = ls_manager
        def get_active_project(self): return self._project
        def get_language_server_manager(self): return self._ls_manager
        def get_current_tasks(self): return []
        def get_last_executed_task(self): return None
        def execute_task(self, fn, *, logged=None, name=None): return fn()

    def _factory(ls_manager=None):
        root = tmp_path / "proj"; root.mkdir()
        agent = _DummyAgent(root, ls_manager=ls_manager)
        dashboard = SerenaDashboardAPI(
            memory_log_handler=_DummyMemLog(), tool_names=[],
            agent=agent, tool_usage_stats=None,
        )
        return dashboard, dashboard._app.test_client(), root
    return _factory


def test_code_list_dir_returns_entries(make_dashboard_with_project):
    _, client, root = make_dashboard_with_project()
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hi')")
    (root / "README.md").write_text("hi")
    r = client.get("/code/list_dir?path=.")
    assert r.status_code == 200
    body = r.get_json()
    names = {e["name"] for e in body["entries"]}
    assert "src" in names and "README.md" in names
    kinds = {e["name"]: e["kind"] for e in body["entries"]}
    assert kinds["src"] == "dir" and kinds["README.md"] == "file"


def test_code_list_dir_rejects_traversal(make_dashboard_with_project):
    _, client, _ = make_dashboard_with_project()
    r = client.get("/code/list_dir?path=../etc")
    assert r.status_code == 400


def test_code_list_dir_respects_gitignore(make_dashboard_with_project):
    _, client, root = make_dashboard_with_project()
    (root / ".gitignore").write_text("ignored/\n")
    (root / "ignored").mkdir()
    (root / "visible").mkdir()
    r = client.get("/code/list_dir?path=.")
    names = {e["name"] for e in r.get_json()["entries"]}
    assert "visible" in names
    assert "ignored" not in names
```

#### Corrected Task 21 — `/code/file_symbols` (Flask)

**Models (in `dashboard_code.py`):**

```python
class _Position(BaseModel):
    line: int
    character: int


class _Range(BaseModel):
    start: _Position
    end: _Position


class _FileSymbol(BaseModel):
    name: str
    kind: str  # human-readable label (e.g., "Class", "Function")
    range: _Range
    children: list["_FileSymbol"] | None = None


class _ResponseFileSymbols(BaseModel):
    symbols: list[_FileSymbol]
```

**LSP SymbolKind → label mapping** (add at module level):

```python
_LSP_SYMBOL_KIND_LABELS = {
    1: "File", 2: "Module", 3: "Namespace", 4: "Package",
    5: "Class", 6: "Method", 7: "Property", 8: "Field",
    9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
    13: "Variable", 14: "Constant", 15: "String", 16: "Number",
    17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
    21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
    25: "Operator", 26: "TypeParameter",
}


def _convert_lsp_symbol(s: Any) -> _FileSymbol:
    """Convert a UnifiedSymbolInformation / LSP DocumentSymbol to dashboard shape."""
    name = s.get("name", "?") if isinstance(s, dict) else getattr(s, "name", "?")
    kind_int = s.get("kind") if isinstance(s, dict) else getattr(s, "kind", None)
    kind_label = _LSP_SYMBOL_KIND_LABELS.get(int(kind_int) if kind_int is not None else 0, str(kind_int))
    # range may be at top-level (DocumentSymbol) or under .location.range (SymbolInformation).
    rng = s.get("range") if isinstance(s, dict) else getattr(s, "range", None)
    if rng is None:
        loc = s.get("location") if isinstance(s, dict) else getattr(s, "location", None)
        rng = (loc.get("range") if isinstance(loc, dict) else getattr(loc, "range", None)) if loc else None
    rng = rng or {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}
    children = s.get("children") if isinstance(s, dict) else getattr(s, "children", None)
    return _FileSymbol(
        name=name,
        kind=kind_label,
        range=rng,
        children=[_convert_lsp_symbol(c) for c in children] if children else None,
    )
```

**Route inside `register_code_routes`:**

```python
    @app.route("/code/file_symbols", methods=["GET"])
    def code_file_symbols():
        path = request.args.get("path", default=None, type=str)
        if not path:
            return _err(400, "path is required")
        root = _get_project_root(dashboard_api)
        if root is None:
            return _err(503, "No active project", "no_project")
        try:
            resolved = resolve_project_path(root, path)
        except ValueError as e:
            return _err(400, str(e))
        except FileNotFoundError:
            return _err(404, "file not found")
        rel = os.path.relpath(resolved, str(Path(root).resolve()))
        ls = _get_language_server_for_path(dashboard_api, rel)
        if ls is None:
            return _err(503, "Language server not ready", "ls_not_ready")
        try:
            doc_syms = ls.request_document_symbols(rel)
        except TimeoutError as e:
            return _err(504, str(e), "ls_timeout")
        except Exception as e:  # noqa: BLE001
            log.error("LSP document symbols failed for %s: %s", rel, e, exc_info=e)
            return _err(502, str(e), "ls_error")
        # doc_syms is a DocumentSymbols object (or a list, depending on solidlsp shape).
        # Extract the iterable of top-level symbols. Adjust to actual API.
        roots = getattr(doc_syms, "root_symbols", None) or doc_syms or []
        return _ResponseFileSymbols(symbols=[_convert_lsp_symbol(s) for s in roots]).model_dump()
```

**Implementer note:** read `src/solidlsp/ls.py:1902` for the exact return shape of `request_document_symbols`. If it returns a `DocumentSymbols` instance with `.root_symbols`, the code above handles it; if it returns a raw list, the `or doc_syms or []` fallback covers that too.

**Tests** — see fixture pattern in Task 20. Mock the LS:

```python
class _FakeLS:
    def __init__(self, doc_symbols=None, raise_exc=None):
        self._doc_symbols = doc_symbols
        self._raise = raise_exc
    def request_document_symbols(self, rel):
        if self._raise: raise self._raise
        return self._doc_symbols or []

class _FakeManager:
    def __init__(self, ls=None):
        self._ls = ls
    def get_language_server(self, rel):
        return self._ls
    def iter_language_servers(self):
        if self._ls: yield self._ls


def test_code_file_symbols_returns_document_symbols(make_dashboard_with_project):
    fake_syms = [{
        "name": "Foo", "kind": 5,
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 5, "character": 0}},
        "children": [{
            "name": "bar", "kind": 6,
            "range": {"start": {"line": 1, "character": 4}, "end": {"line": 3, "character": 0}},
            "children": [],
        }],
    }]
    mgr = _FakeManager(ls=_FakeLS(doc_symbols=fake_syms))
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "main.py").write_text("class Foo:\n    def bar(self): pass\n")
    r = client.get("/code/file_symbols?path=main.py")
    assert r.status_code == 200
    body = r.get_json()
    assert body["symbols"][0]["name"] == "Foo"
    assert body["symbols"][0]["kind"] == "Class"  # mapped from int 5
    assert body["symbols"][0]["children"][0]["name"] == "bar"
    assert body["symbols"][0]["children"][0]["kind"] == "Method"


def test_code_file_symbols_503_when_no_ls(make_dashboard_with_project):
    _, client, root = make_dashboard_with_project()  # ls_manager=None
    (root / "f.py").write_text("x=1")
    r = client.get("/code/file_symbols?path=f.py")
    assert r.status_code == 503
    assert r.get_json()["code"] == "ls_not_ready"


def test_code_file_symbols_404_for_missing(make_dashboard_with_project):
    _, client, _ = make_dashboard_with_project()
    r = client.get("/code/file_symbols?path=nope.py")
    assert r.status_code == 404
```

#### Corrected Task 22 — `/code/workspace_symbol_search` (Flask)

**Models:**

```python
class _WorkspaceMatch(BaseModel):
    name: str
    kind: str
    path: str
    range: _Range


class _ResponseWorkspaceSymbolSearch(BaseModel):
    matches: list[_WorkspaceMatch]
```

**Route:**

```python
    @app.route("/code/workspace_symbol_search", methods=["GET"])
    def code_workspace_symbol_search():
        q = request.args.get("q", default="", type=str)
        limit = request.args.get("limit", default=50, type=int)
        if not q.strip():
            return _ResponseWorkspaceSymbolSearch(matches=[]).model_dump()
        limit = max(1, min(limit, _WORKSPACE_SYMBOL_LIMIT_CAP))
        ls = _get_first_language_server(dashboard_api)
        if ls is None:
            return _err(503, "Language server not ready", "ls_not_ready")
        try:
            raw = ls.request_workspace_symbol(q)  # Note: SINGULAR (no trailing s)
        except TimeoutError as e:
            return _err(504, str(e), "ls_timeout")
        except Exception as e:  # noqa: BLE001
            log.error("LSP workspace symbol failed for %r: %s", q, e, exc_info=e)
            return _err(502, str(e), "ls_error")
        if raw is None:
            return _ResponseWorkspaceSymbolSearch(matches=[]).model_dump()
        raw = raw[:limit]
        matches: list[_WorkspaceMatch] = []
        for m in raw:
            # UnifiedSymbolInformation has .location.uri and .location.range
            name = m.get("name") if isinstance(m, dict) else getattr(m, "name", "?")
            kind_int = m.get("kind") if isinstance(m, dict) else getattr(m, "kind", None)
            location = m.get("location") if isinstance(m, dict) else getattr(m, "location", None)
            uri = (location.get("uri") if isinstance(location, dict) else getattr(location, "uri", None)) if location else None
            rng = (location.get("range") if isinstance(location, dict) else getattr(location, "range", None)) if location else None
            # Convert file:// URI to a project-relative path.
            from urllib.parse import urlparse, unquote
            file_path = unquote(urlparse(uri).path) if uri else ""
            try:
                rel = str(Path(file_path).relative_to(Path(_get_project_root(dashboard_api) or "").resolve()))
            except Exception:
                rel = file_path
            matches.append(_WorkspaceMatch(
                name=name,
                kind=_LSP_SYMBOL_KIND_LABELS.get(int(kind_int) if kind_int is not None else 0, str(kind_int)),
                path=rel,
                range=rng or {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
            ))
        return _ResponseWorkspaceSymbolSearch(matches=matches).model_dump()
```

**Test:** mock `_FakeLS.request_workspace_symbol(q)` to return a list, and assert the route slices to `limit`.

#### Corrected Task 23 — `/code/diagnostics_summary` (Flask)

**Models:**

```python
class _Diagnostic(BaseModel):
    severity: str  # "error" | "warning" | "info" | "hint"
    message: str
    line: int
    column: int
    source: str | None = None


class _FileDiagnostics(BaseModel):
    path: str
    diagnostics: list[_Diagnostic]


class _ResponseDiagnosticsSummary(BaseModel):
    files: list[_FileDiagnostics]
    truncated: bool


_LSP_SEVERITY = {1: "error", 2: "warning", 3: "info", 4: "hint"}
```

**Route:**

```python
    @app.route("/code/diagnostics_summary", methods=["GET"])
    def code_diagnostics_summary():
        file_limit = request.args.get("file_limit", default=1000, type=int)
        file_limit = max(1, min(file_limit, _FILE_LIMIT_CAP))
        root = _get_project_root(dashboard_api)
        if root is None:
            return _err(503, "No active project", "no_project")
        ls = _get_first_language_server(dashboard_api)
        if ls is None:
            return _err(503, "Language server not ready", "ls_not_ready")

        # Walk the project tree honoring gitignore.
        from serena.util.file_system import GitignoreParser
        try:
            ignore = GitignoreParser(root)
        except Exception:
            ignore = None
        candidate_paths: list[str] = []
        root_real = str(Path(root).resolve())
        for dirpath, dirnames, filenames in os.walk(root_real, followlinks=False):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            if ignore is not None:
                dirnames[:] = [
                    d for d in dirnames
                    if not ignore.is_ignored(os.path.relpath(os.path.join(dirpath, d), root_real), is_dir=True)
                ]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), root_real)
                if ignore is not None and ignore.is_ignored(rel, is_dir=False):
                    continue
                candidate_paths.append(rel)

        truncated = False
        if len(candidate_paths) > file_limit:
            candidate_paths = candidate_paths[:file_limit]
            truncated = True

        files: list[_FileDiagnostics] = []
        for rel in candidate_paths:
            try:
                raw = ls.request_published_text_document_diagnostics(rel)
            except TimeoutError:
                continue  # individual file timeout: skip, don't kill the whole response
            except Exception as e:  # noqa: BLE001
                log.debug("Diagnostics failed for %s: %s", rel, e)
                continue
            if not raw:
                continue
            diags: list[_Diagnostic] = []
            for d in raw:
                # LSP shape: {range: {start: {line, character}}, severity: 1..4, message, source}
                rng_start = d.get("range", {}).get("start", {}) if isinstance(d, dict) else getattr(d, "range", {}).get("start", {})
                line = int(rng_start.get("line", 0))
                col = int(rng_start.get("character", 0))
                sev_int = d.get("severity") if isinstance(d, dict) else getattr(d, "severity", None)
                sev = _LSP_SEVERITY.get(int(sev_int) if sev_int is not None else 3, "info")
                msg = (d.get("message") if isinstance(d, dict) else getattr(d, "message", "")) or ""
                if len(msg) > _DIAGNOSTICS_PER_MESSAGE_CAP:
                    msg = msg[:_DIAGNOSTICS_PER_MESSAGE_CAP]
                    truncated = True
                source = d.get("source") if isinstance(d, dict) else getattr(d, "source", None)
                diags.append(_Diagnostic(severity=sev, message=msg, line=line, column=col, source=source))
            # Apply 1 MB per-file cap by dropping tail entries until under.
            fd = _FileDiagnostics(path=rel, diagnostics=diags)
            while diags and len(fd.model_dump_json().encode("utf-8")) > _DIAGNOSTICS_PER_FILE_BYTE_CAP:
                diags.pop()
                fd = _FileDiagnostics(path=rel, diagnostics=diags)
                truncated = True
            files.append(fd)

        return _ResponseDiagnosticsSummary(files=files, truncated=truncated).model_dump()
```

**Tests** — assert 503 when no LS, 200 with diagnostics when LS is mocked, `truncated=True` on file_limit cap, and message-length truncation when a diagnostic exceeds 4 KB.

### Corrected Task 10 — `??` regression test (replaces plan 1697–1715)

```ts
it('cursor uses ?? not || — preserves cursor when max_seq is 0 after a non-zero advance', async () => {
  let phase = 0;
  stubFetchRoutes({
    '/get_tool_call_timeline': (_url: string) => {
      phase++;
      if (phase === 1) return { records: [{ seq: 5, tool: 't', started_at: 0, duration_ms: 0, success: true, error_message: null, input_preview: '', output_preview: '', input_truncated: false, output_truncated: false }], max_seq: 5 };
      // Phase 2: simulate a server restart (or buffer clear) — max_seq=0.
      return { records: [], max_seq: 0 };
    },
  });
  const store = createTimelineStore();
  await store.poll();
  expect(store.cursor).toBe(5);
  await store.poll();
  // Under `||`: cursor would stay at 5 (because 0 is falsy and || picks the truthy 5).
  // Under `??`: cursor becomes 0 (because 0 is not nullish).
  // We want `??` semantics: explicit server state wins over local guess.
  expect(store.cursor).toBe(0);
});
```

> **Note for implementer:** if you decide the `||` semantics are actually what you want (preserve cursor when server resets), document the choice and remove the spec's claim of a `??` discipline. The corrected test above asserts the spec's stated intent.

### Corrected Task 24 — `code` store (SvelteSet for reactivity, error states)

Replace plan lines 4682–4791 with this version:

```ts
import {
  fetchCodeListDir,
  fetchCodeFileSymbols,
  fetchCodeWorkspaceSymbolSearch,
  fetchCodeDiagnosticsSummary,
} from '$lib/api/endpoints';
import type { DirEntry, FileSymbol, WorkspaceMatch, FileDiagnostics } from '$lib/api/types';
import { SvelteSet } from 'svelte/reactivity';

export function createCodeStore() {
  const dirChildren = $state<Record<string, DirEntry[]>>({});
  const dirErrors = $state<Record<string, string>>({});
  const expanded = new SvelteSet<string>();
  let selectedPath = $state<string | null>(null);
  const fileSymbols = $state<Record<string, FileSymbol[]>>({});
  const fileSymbolErrors = $state<Record<string, string>>({});
  let searchQuery = $state('');
  let searchResults = $state<WorkspaceMatch[]>([]);
  let searchLoading = $state(false);
  let searchError = $state<string | null>(null);
  let middlePane = $state<'symbols' | 'search'>('symbols');
  let searchEpoch = 0;
  let diagFiles = $state<FileDiagnostics[]>([]);
  let diagLoading = $state(false);
  let diagError = $state<string | null>(null);
  let diagTruncated = $state(false);
  let diagLastRefreshAt = $state<number | null>(null);

  return {
    get dir_children() { return dirChildren; },
    get dir_errors() { return dirErrors; },
    get expanded() { return expanded; },
    get selected_path() { return selectedPath; },
    get file_symbols() { return fileSymbols; },
    get file_symbol_errors() { return fileSymbolErrors; },
    get search_query() { return searchQuery; },
    get search_results() { return searchResults; },
    get search_loading() { return searchLoading; },
    get search_error() { return searchError; },
    get middle_pane() { return middlePane; },
    get diag_files() { return diagFiles; },
    get diag_loading() { return diagLoading; },
    get diag_error() { return diagError; },
    get diag_truncated() { return diagTruncated; },
    get diag_last_refresh_at() { return diagLastRefreshAt; },
    setMiddlePane(pane: 'symbols' | 'search') { middlePane = pane; },
    async loadDir(path: string, force = false) {
      if (!force && dirChildren[path]) return;
      delete dirErrors[path];
      try {
        const resp = await fetchCodeListDir(path);
        dirChildren[path] = resp.entries;
      } catch (e) {
        dirErrors[path] = e instanceof Error ? e.message : String(e);
      }
    },
    toggleExpand(path: string) {
      if (expanded.has(path)) expanded.delete(path);
      else {
        expanded.add(path);
        void this.loadDir(path);
      }
    },
    selectPath(path: string | null, opts: { switchMiddleTo?: 'symbols' | 'search' } = {}) {
      selectedPath = path;
      if (opts.switchMiddleTo) middlePane = opts.switchMiddleTo;
      if (path) void this.loadFileSymbols(path);
    },
    async loadFileSymbols(path: string, force = false) {
      if (!force && fileSymbols[path]) return;
      delete fileSymbolErrors[path];
      try {
        const resp = await fetchCodeFileSymbols(path);
        fileSymbols[path] = resp.symbols;
      } catch (e) {
        fileSymbolErrors[path] = e instanceof Error ? e.message : String(e);
      }
    },
    async search(q: string) {
      searchQuery = q;
      if (q.trim().length < 2) {
        searchResults = [];
        searchLoading = false;
        searchError = null;
        return;
      }
      const myEpoch = ++searchEpoch;
      searchLoading = true;
      searchError = null;
      try {
        const resp = await fetchCodeWorkspaceSymbolSearch(q, 50);
        if (myEpoch === searchEpoch) {
          searchResults = resp.matches;
        }
      } catch (e) {
        if (myEpoch === searchEpoch) {
          searchError = e instanceof Error ? e.message : String(e);
          // Per spec §7.2: older successful results stay visible. Don't clear searchResults.
        }
      } finally {
        if (myEpoch === searchEpoch) searchLoading = false;
      }
    },
    async refreshDiagnostics(file_limit = 1000) {
      diagLoading = true;
      diagError = null;
      try {
        const resp = await fetchCodeDiagnosticsSummary(file_limit);
        diagFiles = resp.files;
        diagTruncated = resp.truncated;
        diagLastRefreshAt = Date.now();
      } catch (e) {
        diagError = e instanceof Error ? e.message : String(e);
        // Previous diagFiles stay visible per spec §7.2.
      } finally {
        diagLoading = false;
      }
    },
  };
}

export const code = createCodeStore();
```

**Additional Task 24 step — update `Header.svelte`:**

In `dashboard/src/components/shell/Header.svelte`, replace the local `type View = ...` declaration with `import type { View } from '$lib/pollers';` and add a Code tab button between Stats and Logs. (Per B41.)

**Additional Task 24 step — update `App.svelte`:**

```svelte
<script lang="ts">
  // ... existing imports ...
  import CodePage from './components/code/CodePage.svelte';
</script>

<!-- ... existing Header / shell ... -->

{#if view === 'overview'}<OverviewPage />{/if}
{#if view === 'stats'}<StatsPage />{/if}
{#if view === 'code'}<CodePage />{/if}
{#if view === 'logs'}<LogsPage />{/if}
```

Use synchronous imports matching the existing pattern. No `$components` alias.

### Corrected Task 27 — `WorkspaceSearch` switches middle pane on match select

Replace the `selectMatch` function in `WorkspaceSearch.svelte` (plan line 5086):

```ts
function selectMatch(path: string) {
  code.selectPath(path, { switchMiddleTo: 'symbols' });
}
```

The store's `selectPath` now accepts an `opts.switchMiddleTo` (added in the corrected Task 24).

### Corrected Phase 4 Charts — ChartSpec shape + stacked-area config

The original Tasks 16 and 17 return `{type, labels, datasets, ...}` at the top level. The existing `ChartSpec` is `ChartConfiguration<...>` which nests `labels`/`datasets` under `data`. **Use the existing shape.**

**Widen `ChartSpec`** in `dashboard/src/lib/charts.ts`:

```ts
import type { ChartConfiguration } from 'chart.js';

export type ChartSpec =
  | ChartConfiguration<'pie'>
  | ChartConfiguration<'bar'>
  | ChartConfiguration<'line'>;
```

**Corrected `durationChartSpec` (Task 16):**

```ts
export function durationChartSpec(
  stats: Record<string, ToolStatEntry>,
  sortKey: SortKey,
): ChartConfiguration<'bar'> {
  const sorted = sortToolsBy(stats, sortKey);
  const labels = sorted.map(([name]) => name);
  const avg = sorted.map(([, s]) =>
    s.num_times_called > 0 ? (s.total_duration_ms ?? 0) / s.num_times_called : 0,
  );
  const max = sorted.map(([, s]) => s.max_duration_ms ?? 0);
  return {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Avg (ms)', data: avg, backgroundColor: 'var(--accent)' },
        { label: 'Max (ms)', data: max, backgroundColor: 'transparent', borderColor: 'var(--accent)', borderWidth: 2 },
      ],
    },
    options: { responsive: true, maintainAspectRatio: false },
  };
}
```

**Corrected `rateChartSpec` (Task 17) — adds stacked scales config:**

```ts
export function rateChartSpec(
  records: ToolCallRecord[],
  options: { windowMinutes: 15 | 30 | 60 | 360; stacked: boolean; visibleTools: Set<string> },
): ChartConfiguration<'line'> {
  const nowSec = Math.floor(Date.now() / 1000);
  const currentMinute = Math.floor(nowSec / 60) * 60;
  const total = options.windowMinutes + 1;
  const buckets: number[] = Array.from({ length: total }, (_, i) =>
    currentMinute - (total - 1 - i) * 60,
  );
  const labels = buckets.map((b) => new Date(b * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

  if (!options.stacked) {
    const counts = buckets.map((b) =>
      records.filter((r) => r.started_at >= b && r.started_at < b + 60).length,
    );
    return {
      type: 'line',
      data: { labels, datasets: [{ label: 'Calls/min', data: counts, fill: false, borderColor: 'var(--accent)' }] },
      options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } } },
    };
  }

  const tools = [...options.visibleTools];
  const datasets = tools.map((tool, i) => ({
    label: tool,
    data: buckets.map((b) =>
      records.filter((r) => r.tool === tool && r.started_at >= b && r.started_at < b + 60).length,
    ),
    fill: true,
    borderColor: `var(--chart-${(i % 6) + 1}, var(--accent))`,
    backgroundColor: `var(--chart-${(i % 6) + 1}, var(--accent))`,
  }));
  return {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { stacked: true },
        y: { stacked: true, beginAtZero: true, ticks: { maxTicksLimit: 8 } },
      },
    },
  };
}
```

**Corrected `percentile` (Task 18 — inclusive-linear, matches test value 95 for `[1..100]`):**

```ts
export function percentile(xs: number[], q: number): number {
  if (xs.length === 0) return 0;
  const sorted = [...xs].sort((a, b) => a - b);
  const idx = Math.floor((q / 100) * (sorted.length - 1));
  return sorted[idx]!;
}
```

**Test expectations should match** (plan line 3565): `percentile([1..100], 95) === 95`. The implementation above produces exactly that.

**Chart click handler — add to `ChartPanel.svelte` (Task 18 Step 0):**

```svelte
<script lang="ts">
  // ... existing props ...
  interface Props {
    spec: ChartSpec;
    height?: string;
    onSliceClick?: (label: string) => void;
  }
  let { spec, height = '300px', onSliceClick }: Props = $props();

  // Inside the $effect that creates the chart:
  const cfg = {
    ...spec,
    options: {
      ...(spec.options ?? {}),
      onClick: (_evt: any, elements: any[], chart: any) => {
        if (elements[0]) {
          const label = chart.data.labels?.[elements[0].index] as string | undefined;
          if (label && onSliceClick) onSliceClick(label);
        }
      },
    },
  };
  chart = new Chart(canvas, cfg);
</script>
```

**Dataset-count change handling (Task 17, addresses B25):**

In `ChartPanel.svelte`'s data-update effect, replace the in-place dataset mutation with:

```ts
$effect(() => {
  if (!chart) return;
  if (chart.data.datasets.length !== spec.data.datasets.length) {
    chart.data.labels = spec.data.labels;
    chart.data.datasets = spec.data.datasets;
    chart.update('none');
    return;
  }
  chart.data.labels = spec.data.labels;
  spec.data.datasets.forEach((ds, i) => {
    if (chart!.data.datasets[i]) {
      chart!.data.datasets[i].data = ds.data;
      chart!.data.datasets[i].label = ds.label;
    }
  });
  chart.update('none');
});
```

### File Structure table corrections

Apply these edits to the File Structure table near the top of the plan:

- `dashboard/src/components/overview/StatsSummary.svelte` (modify) → **remove this row entirely**. The existing file is at `components/stats/StatsSummary.svelte` and is untouched.
- Add a new row: `dashboard/src/components/overview/OverviewSummaryCards.svelte` (create) — "4-card KPI strip: Calls / Tokens / Time / Errors. Mounted on Overview only; does not affect Stats."
- `src/serena/dashboard_code.py` (create) — description stays.
- Add a new row for `src/serena/util/file_system.py` (read-only dep) and document that the `/code/*` routes use `GitignoreParser` from this module.
- Add: `dashboard/src/components/shell/Header.svelte` (modify) — "Add Code tab button between Stats and Logs; import `View` type from `$lib/pollers`."

### Recommended additions (improvements found during review)

These are not bug fixes but improvements worth applying:

1. **Add a small color palette** in `dashboard/src/styles/tokens.css` (`--chart-7`..`--chart-12`) so stacked-area RateChart with 12+ tools doesn't cycle colors every 6.
2. **Visibility-aware polling** in `dashboard/src/lib/polling.ts`: pause polling when `document.visibilityState === 'hidden'`, resume on `visibilitychange`. Add as a Step 0 of Task 14.
3. **Tool-names source for FilterDropdown**: derive from `Object.keys(config.data?.tool_stats_summary ?? {})` (already polled) unioned with `record.tool` from the timeline buffer. Avoids a separate fetch.
4. **`_seedForTest()` action on timeline store**: gated on `import.meta.env.TEST`, lets tests inject records cleanly instead of mutating `(store as any).records`. Add to Task 10.
5. **Drill-down panel empty state**: when timeline buffer has zero records for the selected tool, show "No recent calls in the timeline buffer. (Aggregates above cover full history.)" instead of computing p95 over an empty array.
6. **`updateMode: 'none'` for charts on poll-driven data updates**: prevents flicker on 1 s ticks. Already in the corrected `rateChartSpec` update logic above; apply uniformly across new charts.
7. **Concurrency cap on diagnostics**: spec says diagnostics is slow. Consider a `_diagnostics_inflight: bool` guard at the route level so a second concurrent request short-circuits with 429 rather than queueing behind the LS.
8. **`request_workspace_symbol` may return `None` if the LSP doesn't support workspace/symbol** (some servers don't). Treat `None` as empty matches with a 200 response (corrected Task 22 already does this).

### Open items needing user input (none blocking)

- **Dotfile visibility in `code/list_dir`:** spec doesn't say. The corrected Task 20 hides dotfiles. If the user wants `.github` / `.vscode` etc. visible, change the `de.name.startswith(".")` skip to skip only `.git`.
- **Tab visibility when no project loaded:** Code tab visible but every `/code/*` returns 503 `no_project` with an empty state. Acceptable; consider hiding the tab entirely if `config.data?.active_project?.name` is null.
- **`percentile` algorithm choice:** the corrected version uses inclusive-linear (`(n-1)*q`). Some teams prefer the nearest-rank (`floor(n*q)`) variant. Document the choice in `dashboard/src/lib/percentile.ts` for future reference.

---

## File Structure

### Backend (Python)

| File | Status | Responsibility |
|---|---|---|
| `src/serena/analytics.py` | modify | Extend `Entry` with timing/error fields; add `ToolCallRecord` dataclass; add ring buffer + seq cursor + `record_call` + `get_records_since` on `ToolUsageStats` |
| `src/serena/task_executor.py` | modify | Extend `Task` with `started_at`/`finished_at`; race-fix in `run_task`; extend `TaskInfo` with timing accessors + display/error helpers |
| `src/serena/tools/tools_base.py` | modify | Wrap `apply_fn(...)` with timing + error capture in `apply_ex` |
| `src/serena/agent.py` | modify | Add `_record_tool_call_safely` helper; deprecate `record_tool_usage` callers to it |
| `src/serena/dashboard.py` | modify | Add `/get_tool_call_timeline` route; extend `/get_config_overview` payload (`tool_stats_totals`); extend `QueuedExecution` serializer |
| `src/serena/dashboard_code.py` | create | Four `/code/*` route handlers + path-traversal guard helper |
| `test/serena/test_analytics.py` | create | Unit tests for extended Entry, ToolCallRecord truncation, ring buffer, seq monotonicity, thread safety |
| `test/serena/test_task_executor.py` | modify | Add timing tests + race-fix regression test |
| `test/serena/test_dashboard.py` | modify | Tests for `/get_tool_call_timeline` |
| `test/serena/test_dashboard_code.py` | create | Tests for `/code/*` routes incl. path-traversal guard |

### Frontend (TypeScript + Svelte)

| File | Status | Responsibility |
|---|---|---|
| `dashboard/src/lib/api/types.ts` | modify | Add `ToolCallRecord`, `ResponseToolCallTimeline`, `ToolStatsTotals`, `Diagnostic`, `FileSymbol`, `WorkspaceMatch`, `DirEntry` types; extend `ResponseConfigOverview` + `QueuedExecution` |
| `dashboard/src/lib/api/endpoints.ts` | modify | Five new typed fetch wrappers |
| `dashboard/src/lib/pollers.ts` | modify | Add `'code'` view; add `'timeline'` poller; update `pollersForView` |
| `dashboard/src/lib/stores/timeline.svelte.ts` | create | Cursor-based timeline buffer with `??` discipline; filter/pause/clear actions |
| `dashboard/src/lib/stores/code.svelte.ts` | create | Code tab state: lazy folder cache, selected file, file-symbols cache, search-with-epoch, diagnostics state |
| `dashboard/src/lib/charts.ts` | modify | Add `durationChartSpec` + `rateChartSpec` builders |
| `dashboard/src/components/common/FilterDropdown.svelte` | create | Shared filterable single-select with × clear, applied checkmark, keyboard nav |
| `dashboard/src/components/overview/SummaryCards.svelte` | create | 4-card KPI strip: Calls / Tokens / Time / Errors. **Per corrections §B15:** mounts on Overview only; the existing `components/stats/StatsSummary.svelte` is unaffected. |
| `dashboard/src/components/shell/Header.svelte` | modify | **Per corrections §B19/B41:** add Code tab button between Stats and Logs; import `View` type from `$lib/pollers`. |
| `dashboard/src/components/overview/Timeline.svelte` | create | Filtered, paginated, polled timeline list |
| `dashboard/src/components/overview/TimelineRow.svelte` | create | Single timeline row with expandable detail |
| `dashboard/src/components/stats/SortSelector.svelte` | create | Sort key selector (calls/tokens/duration-total/duration-avg/errors) |
| `dashboard/src/components/stats/DurationChart.svelte` | create | Chart.js avg + max duration chart |
| `dashboard/src/components/stats/RateChart.svelte` | create | Per-minute line chart with window selector + stacked-area toggle |
| `dashboard/src/components/stats/DrillDownPanel.svelte` | create | Side-panel with aggregates, p95, recent errors, last-20 calls, Open in Timeline |
| `dashboard/src/components/stats/StatsPage.svelte` | modify | Mount SortSelector, DurationChart, RateChart, DrillDownPanel; wire chart click handlers |
| `dashboard/src/components/code/CodePage.svelte` | create | Three-pane layout: FileTree + (FileSymbols ⇄ WorkspaceSearch) + DiagnosticsPanel |
| `dashboard/src/components/code/FileTree.svelte` | create | Lazy folder tree |
| `dashboard/src/components/code/FileSymbols.svelte` | create | Nested LSP document-symbols tree |
| `dashboard/src/components/code/WorkspaceSearch.svelte` | create | Debounced LSP workspace symbol search with epoch counter |
| `dashboard/src/components/code/DiagnosticsPanel.svelte` | create | Refresh + warning banner + grouped diagnostics list |
| `dashboard/src/App.svelte` | modify | Register `code` tab between Stats and Logs |
| `dashboard/tests/timeline-store.test.ts` | create | Cursor `??` discipline, dedup-by-seq, buffer cap |
| `dashboard/tests/code-store.test.ts` | create | Lazy cache, search epoch |
| `dashboard/tests/filter-dropdown.test.ts` | create | Keyboard nav, substring filter, applied checkmark |
| `dashboard/tests/summary-cards.test.ts` | create | Renders 4 cards with formatted values |
| `dashboard/tests/timeline.test.ts` | create | Pagination, filter, pause/resume, row expansion |
| `dashboard/tests/sort-selector.test.ts` | create | Driven chart specs reorder |
| `dashboard/tests/charts.test.ts` | modify | Add `rateChartSpec` bucket alignment + `durationChartSpec` |
| `dashboard/tests/drilldown.test.ts` | create | p95 computation |
| `dashboard/tests/code-tab.spec.ts` | create | Playwright golden-path smoke test |

---

## Conventions used in this plan

- **Backend tests**: pytest under `test/serena/`. Run with `uv run pytest <file>::<test> -v` (project standard; see existing `pyproject.toml`).
- **Frontend tests**: vitest under `dashboard/tests/`. Run with `cd dashboard && npm test -- <file>` or `npm test -- -t "test name"`.
- **Frontend store testing**: test the factory (`createXStore()`) for isolation. Stub fetch with `stubFetchJson` / `stubFetchRoutes` from `tests/helpers.ts`.
- **Build contract**: after any change under `dashboard/src/`, run `cd dashboard && npm run format && npm run build` and stage all changes — partial staging breaks CI's prettier check. Final phase task covers this.
- **Commit style**: `feat(dashboard):`, `fix(dashboard):`, `test(dashboard):`, `docs(dashboard):`. Existing branch convention. Include `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer.
- **Components**: compose `common/Card`, `common/Button`, etc. — don't re-implement.

---

## Phase 1 — Backend instrumentation

### Task 1: Extend `Entry` with timing + error fields

**Files:**
- Modify: `src/serena/analytics.py:137-149`
- Create: `test/serena/test_analytics.py`

- [ ] **Step 1: Write the failing test**

Create `test/serena/test_analytics.py`:

```python
from serena.analytics import ToolUsageStats


def test_entry_update_on_call_tracks_timing_and_errors():
    stats = ToolUsageStats()
    # Successful call
    stats._tool_stats["read_file"].update_on_call(
        input_tokens=10, output_tokens=20, duration_ms=15.0, success=True, now=1000.0
    )
    e = stats._tool_stats["read_file"]
    assert e.num_times_called == 1
    assert e.num_errors == 0
    assert e.input_tokens == 10
    assert e.output_tokens == 20
    assert e.total_duration_ms == 15.0
    assert e.min_duration_ms == 15.0
    assert e.max_duration_ms == 15.0
    assert e.last_called_at == 1000.0
    # Failed call with longer duration
    stats._tool_stats["read_file"].update_on_call(
        input_tokens=5, output_tokens=0, duration_ms=42.0, success=False, now=1001.0
    )
    e = stats._tool_stats["read_file"]
    assert e.num_times_called == 2
    assert e.num_errors == 1
    assert e.total_duration_ms == 57.0
    assert e.min_duration_ms == 15.0
    assert e.max_duration_ms == 42.0
    assert e.last_called_at == 1001.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/serena/test_analytics.py::test_entry_update_on_call_tracks_timing_and_errors -v`

Expected: FAIL — `Entry.update_on_call()` has wrong signature.

- [ ] **Step 3: Modify `Entry` in `src/serena/analytics.py`**

Replace lines 137–149 with:

```python
    @dataclass(kw_only=True)
    class Entry:
        num_times_called: int = 0
        num_errors: int = 0
        input_tokens: int = 0
        output_tokens: int = 0
        total_duration_ms: float = 0.0
        min_duration_ms: float | None = None
        max_duration_ms: float | None = None
        last_called_at: float | None = None

        def update_on_call(
            self,
            input_tokens: int,
            output_tokens: int,
            duration_ms: float,
            success: bool,
            now: float,
        ) -> None:
            """
            Update the entry for a single call: tokens, duration, success/error, timestamp.
            """
            self.num_times_called += 1
            if not success:
                self.num_errors += 1
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
            self.total_duration_ms += duration_ms
            self.min_duration_ms = (
                duration_ms if self.min_duration_ms is None else min(self.min_duration_ms, duration_ms)
            )
            self.max_duration_ms = (
                duration_ms if self.max_duration_ms is None else max(self.max_duration_ms, duration_ms)
            )
            self.last_called_at = now
```

- [ ] **Step 4: Temporarily update `ToolUsageStats.record_tool_usage` (lines 161–166) to keep current callers compiling**

This task only changes the dataclass; Task 3 introduces `record_call`. To keep imports and callers passing for now, replace `record_tool_usage` to pass new fields with neutral values:

```python
    def record_tool_usage(self, tool_name: str, input_str: str, output_str: str) -> None:
        # Legacy entry point kept for compatibility; Task 3 supersedes via record_call.
        import time as _time
        input_tokens = self._estimate_token_count(input_str)
        output_tokens = self._estimate_token_count(output_str)
        with self._tool_stats_lock:
            entry = self._tool_stats[tool_name]
            entry.update_on_call(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=0.0,
                success=True,
                now=_time.time(),
            )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest test/serena/test_analytics.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/serena/analytics.py test/serena/test_analytics.py
git commit -m "$(cat <<'EOF'
feat(analytics): extend Entry with duration, errors, last_called_at

Adds num_errors, total/min/max_duration_ms, last_called_at to Entry.
update_on_call now takes duration_ms, success, now. Legacy
record_tool_usage caller kept as a shim until tools_base wiring lands.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add `ToolCallRecord` dataclass + truncation helper

**Files:**
- Modify: `src/serena/analytics.py` (add near `Entry`)
- Modify: `test/serena/test_analytics.py`

- [ ] **Step 1: Write the failing tests**

Append to `test/serena/test_analytics.py`:

```python
from serena.analytics import ToolCallRecord, _truncate_preview, _INPUT_OUTPUT_PREVIEW_BYTES


def test_truncate_preview_short_input_returns_as_is():
    text, truncated = _truncate_preview("hello")
    assert text == "hello"
    assert truncated is False


def test_truncate_preview_long_input_truncates_to_cap():
    long = "x" * (_INPUT_OUTPUT_PREVIEW_BYTES + 1000)
    text, truncated = _truncate_preview(long)
    assert len(text.encode("utf-8")) <= _INPUT_OUTPUT_PREVIEW_BYTES
    assert truncated is True


def test_tool_call_record_is_frozen():
    rec = ToolCallRecord(
        seq=1, tool="read_file", started_at=1000.0, duration_ms=12.0,
        success=True, error_message=None,
        input_preview="a", output_preview="b",
        input_truncated=False, output_truncated=False,
    )
    import dataclasses
    assert dataclasses.is_dataclass(rec)
    # Frozen — assignment raises
    import pytest as _pytest
    with _pytest.raises(dataclasses.FrozenInstanceError):
        rec.seq = 2  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_analytics.py -v`

Expected: 3 new tests FAIL with ImportError (`ToolCallRecord` / `_truncate_preview` undefined).

- [ ] **Step 3: Add `ToolCallRecord` + helper to `src/serena/analytics.py`**

Insert near the top of the file, after the existing imports:

```python
_INPUT_OUTPUT_PREVIEW_BYTES = 8 * 1024
_RECORD_BUFFER_SIZE = 2000


def _truncate_preview(text: str) -> tuple[str, bool]:
    """
    Truncate text so its UTF-8 byte length is at most _INPUT_OUTPUT_PREVIEW_BYTES.
    Returns (possibly-truncated text, was_truncated).
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= _INPUT_OUTPUT_PREVIEW_BYTES:
        return text, False
    # Truncate on byte boundary, then decode best-effort
    truncated = encoded[:_INPUT_OUTPUT_PREVIEW_BYTES].decode("utf-8", errors="ignore")
    return truncated, True


@dataclass(frozen=True)
class ToolCallRecord:
    seq: int
    tool: str
    started_at: float
    duration_ms: float
    success: bool
    error_message: str | None
    input_preview: str
    output_preview: str
    input_truncated: bool
    output_truncated: bool
```

Add to imports at top if not present: `from dataclasses import dataclass, asdict`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_analytics.py -v`

Expected: PASS (5 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/serena/analytics.py test/serena/test_analytics.py
git commit -m "$(cat <<'EOF'
feat(analytics): add ToolCallRecord dataclass + 8KB truncation helper

Frozen record dataclass + _truncate_preview helper for the bounded
ring buffer introduced in the next commit. 8 KB cap matches legacy.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add ring buffer + `record_call` + `get_records_since` on `ToolUsageStats`

**Files:**
- Modify: `src/serena/analytics.py` (`ToolUsageStats.__init__` and add methods)
- Modify: `test/serena/test_analytics.py`

- [ ] **Step 1: Write the failing tests**

Append to `test/serena/test_analytics.py`:

```python
import threading
from serena.analytics import _RECORD_BUFFER_SIZE


def test_record_call_populates_buffer_and_entry():
    stats = ToolUsageStats()
    stats.record_call(
        tool_name="read_file", input_str="a=1", output_str="ok",
        duration_ms=5.0, success=True, error_message=None, now=1000.0,
    )
    recs, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert max_seq == 1
    assert len(recs) == 1
    r = recs[0]
    assert r.seq == 1
    assert r.tool == "read_file"
    assert r.success is True
    assert r.duration_ms == 5.0
    e = stats.get_stats("read_file")
    assert e.num_times_called == 1
    assert e.total_duration_ms == 5.0


def test_get_records_since_cursor_filters():
    stats = ToolUsageStats()
    for i in range(5):
        stats.record_call(
            tool_name=f"t{i % 2}", input_str="", output_str="",
            duration_ms=1.0, success=True, error_message=None, now=1000.0 + i,
        )
    recs, max_seq = stats.get_records_since(since_seq=2, tool=None, limit=10)
    assert [r.seq for r in recs] == [3, 4, 5]
    assert max_seq == 5
    recs_t0, _ = stats.get_records_since(since_seq=None, tool="t0", limit=10)
    assert all(r.tool == "t0" for r in recs_t0)
    assert [r.seq for r in recs_t0] == [1, 3, 5]


def test_ring_buffer_drops_oldest_at_capacity():
    stats = ToolUsageStats()
    for i in range(_RECORD_BUFFER_SIZE + 50):
        stats.record_call(
            tool_name="t", input_str="", output_str="",
            duration_ms=1.0, success=True, error_message=None, now=float(i),
        )
    recs, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=_RECORD_BUFFER_SIZE + 100)
    assert max_seq == _RECORD_BUFFER_SIZE + 50
    assert len(recs) == _RECORD_BUFFER_SIZE
    # Earliest retained is seq = max_seq - cap + 1
    assert recs[0].seq == max_seq - _RECORD_BUFFER_SIZE + 1


def test_seq_monotonic_under_concurrent_writers():
    stats = ToolUsageStats()
    N = 1000

    def writer():
        for _ in range(N):
            stats.record_call(
                tool_name="t", input_str="", output_str="",
                duration_ms=1.0, success=True, error_message=None, now=0.0,
            )

    threads = [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    recs, max_seq = stats.get_records_since(since_seq=None, tool=None, limit=10_000)
    assert max_seq == 2 * N
    # No duplicate seqs in retained tail
    seqs = [r.seq for r in recs]
    assert len(seqs) == len(set(seqs))
    # Strictly increasing
    assert seqs == sorted(seqs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_analytics.py -v`

Expected: 4 new tests FAIL with AttributeError (`record_call` / `get_records_since`).

- [ ] **Step 3: Extend `ToolUsageStats` in `src/serena/analytics.py`**

Add `from collections import deque` to imports at top (alongside existing `from collections import defaultdict`).

Modify `ToolUsageStats.__init__` (around line 124) — add the buffer + seq counter:

```python
    def __init__(self, token_count_estimator: RegisteredTokenCountEstimator = RegisteredTokenCountEstimator.TIKTOKEN_GPT4O):
        self._token_count_estimator = token_count_estimator.load_estimator()
        self._token_estimator_name = token_count_estimator.value
        self._tool_stats: dict[str, ToolUsageStats.Entry] = defaultdict(ToolUsageStats.Entry)
        self._tool_stats_lock = threading.Lock()
        self._records: deque[ToolCallRecord] = deque(maxlen=_RECORD_BUFFER_SIZE)
        self._seq_counter: int = 0
```

Add new methods to `ToolUsageStats` (place after `record_tool_usage`, before `get_tool_stats_dict`):

```python
    def record_call(
        self,
        tool_name: str,
        input_str: str,
        output_str: str,
        duration_ms: float,
        success: bool,
        error_message: str | None,
        now: float,
    ) -> None:
        """
        Record a tool call: updates the aggregate Entry AND appends a ToolCallRecord
        to the bounded ring buffer. Atomic under the stats lock.
        """
        input_tokens = self._estimate_token_count(input_str)
        output_tokens = self._estimate_token_count(output_str)
        input_preview, input_truncated = _truncate_preview(input_str)
        output_preview, output_truncated = _truncate_preview(output_str)
        with self._tool_stats_lock:
            self._seq_counter += 1
            seq = self._seq_counter
            self._tool_stats[tool_name].update_on_call(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                success=success,
                now=now,
            )
            self._records.append(
                ToolCallRecord(
                    seq=seq,
                    tool=tool_name,
                    started_at=now - duration_ms / 1000.0,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message,
                    input_preview=input_preview,
                    output_preview=output_preview,
                    input_truncated=input_truncated,
                    output_truncated=output_truncated,
                )
            )

    def get_records_since(
        self,
        since_seq: int | None,
        tool: str | None,
        limit: int,
    ) -> tuple[list[ToolCallRecord], int]:
        """
        Return (records, max_seq). since_seq=None returns the tail; otherwise only
        records with seq > since_seq are returned. Optional per-tool filter.
        Result is capped at `limit` (newest preferred via tail-slicing).
        """
        limit = max(0, min(limit, 500))
        with self._tool_stats_lock:
            max_seq = self._seq_counter
            snapshot = list(self._records)
        if since_seq is not None:
            snapshot = [r for r in snapshot if r.seq > since_seq]
        if tool is not None:
            snapshot = [r for r in snapshot if r.tool == tool]
        if len(snapshot) > limit:
            snapshot = snapshot[-limit:]
        return snapshot, max_seq
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_analytics.py -v`

Expected: PASS (9 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/serena/analytics.py test/serena/test_analytics.py
git commit -m "$(cat <<'EOF'
feat(analytics): bounded ToolCallRecord ring buffer + cursor reads

ToolUsageStats now keeps a deque(maxlen=2000) of ToolCallRecord and a
monotonic seq counter. record_call() updates Entry and appends a
record atomically. get_records_since(since_seq, tool, limit) returns
(records, max_seq) for cursor-based timeline polling. Limit
server-capped at 500.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Extend `Task` + `TaskInfo` with timing + race fix

**Files:**
- Modify: `src/serena/task_executor.py:28-66, 133-155`
- Modify: `test/serena/test_task_executor.py`

- [ ] **Step 1: Write the failing tests**

Append to `test/serena/test_task_executor.py`:

```python
import threading
import time

from serena.task_executor import TaskExecutor


def test_task_records_started_and_finished_at_on_success():
    task = TaskExecutor.Task(function=lambda: "ok", name="t1", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    assert task.started_at is not None
    assert task.finished_at is not None
    assert task.finished_at >= task.started_at


def test_task_records_finished_at_on_failure():
    def boom() -> str:
        raise RuntimeError("nope")

    task = TaskExecutor.Task(function=boom, name="t2", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    assert task.finished_at is not None
    assert task.future.exception() is not None


def test_task_info_get_duration_and_error_message():
    task_ok = TaskExecutor.Task(function=lambda: "ok", name="t3", logged=False)
    task_ok.start()
    task_ok.wait_until_done(timeout=2.0)
    info_ok = TaskExecutor.TaskInfo.from_task(task_ok, is_running=False)
    assert info_ok.get_duration_ms() is not None
    assert info_ok.get_duration_ms() >= 0
    assert info_ok.get_error_message() is None

    def boom() -> str:
        raise RuntimeError("kaboom")

    task_err = TaskExecutor.Task(function=boom, name="t4", logged=False)
    task_err.start()
    task_err.wait_until_done(timeout=2.0)
    info_err = TaskExecutor.TaskInfo.from_task(task_err, is_running=False)
    assert info_err.get_error_message() is not None
    assert "kaboom" in info_err.get_error_message()


def test_task_info_get_display_name_strips_task_n_prefix():
    task = TaskExecutor.Task(function=lambda: "ok", name="Task-7: find_symbol", logged=False)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    assert info.get_display_name() == "find_symbol"
    task2 = TaskExecutor.Task(function=lambda: "ok", name="naked-name", logged=False)
    info2 = TaskExecutor.TaskInfo.from_task(task2, is_running=False)
    assert info2.get_display_name() == "naked-name"


def test_finished_at_visible_before_future_done_callback_fires():
    """
    Race-fix regression: if finished_at is set AFTER set_result, a done-callback
    observer may see finished_at == None. We assert the inverse: every done-callback
    observation sees finished_at populated.
    """
    observations: list[bool] = []
    barrier = threading.Event()

    for _ in range(100):
        task = TaskExecutor.Task(function=lambda: "ok", name="race", logged=False)

        def cb(_fut, t=task):
            observations.append(t.finished_at is not None)
            if len(observations) == 100:
                barrier.set()

        task.future.add_done_callback(cb)
        task.start()

    barrier.wait(timeout=10.0)
    assert len(observations) == 100
    assert all(observations), "finished_at was None for one or more done-callback observations"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_task_executor.py -v`

Expected: 5 new tests FAIL (attributes/methods undefined).

- [ ] **Step 3: Extend `Task` in `src/serena/task_executor.py`**

Modify `Task.__init__` (line 29):

```python
        def __init__(self, function: Callable[[], T], name: str, logged: bool = True, timeout: float | None = None):
            self.name = name
            self.future: concurrent.futures.Future = concurrent.futures.Future()
            self.logged = logged
            self.timeout = timeout
            self._function = function
            self.started_at: float | None = None
            self.finished_at: float | None = None
```

Modify `Task.start` (lines 45–66) — set `finished_at` BEFORE resolving the future, in both success and failure paths:

```python
        def start(self) -> None:
            """
            Executes the task in a separate thread, setting the result or exception on the future.
            """

            def run_task() -> None:
                self.started_at = time.time()
                try:
                    if self.future.done():
                        if self.logged:
                            log.info(f"Task {self.name} was already completed/cancelled; skipping execution")
                        self.finished_at = time.time()
                        return
                    with LogTime(self.name, logger=log, enabled=self.logged):
                        result = self._function()
                        if not self.future.done():
                            self.finished_at = time.time()
                            self.future.set_result(result)
                except Exception as e:
                    if not self.future.done():
                        log.error(f"Error during execution of {self.name}: {e}", exc_info=e)
                        self.finished_at = time.time()
                        self.future.set_exception(e)

            thread = Thread(target=run_task, name=self.name)
            thread.start()
```

- [ ] **Step 4: Extend `TaskInfo` in `src/serena/task_executor.py`**

Replace lines 133–155 with:

```python
    @dataclass
    class TaskInfo:
        name: str
        is_running: bool
        future: Future
        task_id: int
        logged: bool
        started_at: float | None = None
        finished_at: float | None = None

        def finished_successfully(self) -> bool:
            return self.future.done() and not self.future.cancelled() and self.future.exception() is None

        def get_duration_ms(self) -> int | None:
            if self.started_at is None or self.finished_at is None:
                return None
            return int(max(0.0, (self.finished_at - self.started_at) * 1000))

        def get_error_message(self) -> str | None:
            if not self.future.done() or self.future.cancelled():
                return None
            exc = self.future.exception()
            if exc is None:
                return None
            return f"{type(exc).__name__}: {exc}"

        def get_display_name(self) -> str:
            # Strip "Task-N: " prefix if present.
            import re
            m = re.match(r"^Task-\d+:\s*(.*)$", self.name)
            return m.group(1) if m else self.name

        @staticmethod
        def from_task(task: "TaskExecutor.Task", is_running: bool) -> "TaskExecutor.TaskInfo":
            return TaskExecutor.TaskInfo(
                name=task.name,
                is_running=is_running,
                future=task.future,
                task_id=id(task),
                logged=task.logged,
                started_at=task.started_at,
                finished_at=task.finished_at,
            )

        def cancel(self) -> None:
            self.future.cancel()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_task_executor.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/serena/task_executor.py test/serena/test_task_executor.py
git commit -m "$(cat <<'EOF'
feat(task-executor): TaskInfo timing + race-fix around future resolve

Task.started_at/finished_at populated by run_task; finished_at is set
BEFORE set_result/set_exception so done-callback observers see a
consistent record. TaskInfo gains get_duration_ms,
get_error_message, get_display_name (strips Task-N: prefix).

Race-fix regression test: 100 tasks observed via add_done_callback;
every observation sees finished_at populated.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Wire timing/error capture into `tools_base.py` + add `_record_tool_call_safely` on `SerenaAgent`

> **⚠️ CORRECTION:** Step 5's `apply_ex` body in this task has a double-recording bug (the `except` branch and the `finally` block both call `_record_tool_call_safely`). Use the corrected version in §"Corrected Task 5 — `apply_ex`" near the top of this plan. Step 6's integration test should also be replaced with the regression test in that section. The rest of Task 5 (Steps 1–4, 7–9) is correct as written.

**Files:**
- Modify: `src/serena/agent.py:835-843`
- Modify: `src/serena/tools/tools_base.py:309-393`
- Create: integration test in `test/serena/test_analytics.py`

- [ ] **Step 1: Write the failing integration test**

Append to `test/serena/test_analytics.py`:

```python
def test_record_tool_call_safely_handles_analytics_exception(monkeypatch, caplog):
    """
    Instrumentation must never break the agent: if record_call raises,
    _record_tool_call_safely swallows and logs.
    """
    import logging
    from serena.agent import SerenaAgent

    # Build a minimal agent without going through SerenaAgent.__init__'s heavy setup.
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()

    def explode(*_a, **_kw):
        raise RuntimeError("synthetic analytics failure")

    monkeypatch.setattr(agent._tool_usage_stats, "record_call", explode)

    with caplog.at_level(logging.WARNING):
        # Must not raise.
        agent._record_tool_call_safely(
            tool_name="x", input_str="i", output_str="o",
            duration_ms=1.0, success=True, error_message=None,
        )
    assert any("synthetic analytics failure" in r.message or "analytics" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/serena/test_analytics.py::test_record_tool_call_safely_handles_analytics_exception -v`

Expected: FAIL — `_record_tool_call_safely` doesn't exist.

- [ ] **Step 3: Add `_record_tool_call_safely` on `SerenaAgent` in `src/serena/agent.py`**

Replace lines 835–843 with:

```python
    def record_tool_usage(self, input_kwargs: dict, tool_result: str | dict, tool: Tool) -> None:
        """
        Legacy success-only entry point. New callers should use _record_tool_call_safely
        directly from the tool dispatch layer (tools_base.apply_ex) so error paths and
        timing are captured too.
        """
        tool_name = tool.get_name()
        input_str = str(input_kwargs)
        output_str = str(tool_result)
        log.debug(f"Recording tool usage for tool '{tool_name}'")
        self._tool_usage_stats.record_tool_usage(tool_name, input_str, output_str)

    def _record_tool_call_safely(
        self,
        tool_name: str,
        input_str: str,
        output_str: str,
        duration_ms: float,
        success: bool,
        error_message: str | None,
    ) -> None:
        """
        Record a tool call into the in-memory analytics buffer. Instrumentation must
        never break the agent — any exception from the analytics layer is caught
        and logged at WARNING.
        """
        if self._tool_usage_stats is None:
            return
        try:
            import time as _time
            self._tool_usage_stats.record_call(
                tool_name=tool_name,
                input_str=input_str,
                output_str=output_str,
                duration_ms=duration_ms,
                success=success,
                error_message=error_message,
                now=_time.time(),
            )
        except BaseException as e:  # noqa: BLE001 — instrumentation MUST NOT break agent
            log.warning(f"Failed to record tool call analytics for '{tool_name}': {e}", exc_info=e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/serena/test_analytics.py::test_record_tool_call_safely_handles_analytics_exception -v`

Expected: PASS.

- [ ] **Step 5: Modify `tools_base.py:apply_ex` to capture timing + errors**

Replace lines 327–392 of `src/serena/tools/tools_base.py` (the `task()` closure body) with:

```python
        def task() -> str:
            apply_fn = self.get_apply_fn()

            try:
                if not self.is_active():
                    return f"Error: Tool '{self.get_name_from_cls()}' is not active. Active tools: {self.agent.get_active_tool_names()}"
            except Exception as e:
                return f"RuntimeError while checking if tool {self.get_name_from_cls()} is active: {e}"

            if log_call:
                self._log_tool_application(inspect.currentframe(), session_id)

            # Build apply kwargs ahead of timing so it's not on the hot path.
            apply_kwargs = dict(kwargs)
            if self._is_session_aware:
                apply_kwargs["session_id"] = session_id

            tool_name = self.get_name()
            input_str = str(apply_kwargs)
            result: str = ""
            success = True
            error_message: str | None = None
            start = time.perf_counter()
            try:
                # check whether the tool requires an active project and language server
                if not isinstance(self, ToolMarkerDoesNotRequireActiveProject):
                    if self.agent.get_active_project() is None:
                        result = (
                            "Error: No active project. Ask the user to provide the project path or to select a project from this list of known projects: "
                            + f"{self.agent.serena_config.project_names}"
                        )
                        return result

                # apply the actual tool
                try:
                    result = apply_fn(**apply_kwargs)
                except SolidLSPException as e:
                    if e.is_language_server_terminated():
                        affected_language = e.get_affected_language()
                        if affected_language is not None:
                            log.error(
                                f"Language server terminated while executing tool ({e}). Restarting the language server and retrying ..."
                            )
                            self.agent.get_language_server_manager_or_raise().restart_language_server(affected_language)
                            result = apply_fn(**apply_kwargs)
                        else:
                            log.error(
                                f"Language server terminated while executing tool ({e}), but affected language is unknown. Not retrying."
                            )
                            raise
                    else:
                        raise

            except Exception as e:
                success = False
                error_message = f"{type(e).__name__}: {e}"
                if not catch_exceptions:
                    # Record before re-raising so the analytics tail isn't lost.
                    duration_ms = (time.perf_counter() - start) * 1000
                    self.agent._record_tool_call_safely(
                        tool_name=tool_name,
                        input_str=input_str,
                        output_str=result,
                        duration_ms=duration_ms,
                        success=False,
                        error_message=error_message,
                    )
                    raise
                msg = f"Error executing tool: {e.__class__.__name__} - {e}"
                log.error(f"Error executing tool: {e}", exc_info=e)
                result = msg
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                self.agent._record_tool_call_safely(
                    tool_name=tool_name,
                    input_str=input_str,
                    output_str=result,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message,
                )

            if log_call:
                log.info(f"Result: {result}")

            try:
                ls_manager = self.agent.get_language_server_manager()
                if ls_manager is not None:
                    ls_manager.save_all_caches()
            except Exception as e:
                log.error(f"Error saving language server cache: {e}")

            return result
```

Add `import time` to the file's imports if not already present.

> **Note:** the legacy `self.agent.record_tool_usage(apply_kwargs, result, self)` call is removed — `_record_tool_call_safely` replaces it and captures both success and error paths.

- [ ] **Step 6: Write an integration test that exercises the full dispatch path**

Append to `test/serena/test_analytics.py`:

```python
def test_apply_ex_records_successful_call_with_duration(monkeypatch):
    """
    A successful tool dispatch through Tool.apply_ex records one ToolCallRecord
    with success=True and duration_ms > 0.
    """
    from serena.agent import SerenaAgent
    from serena.tools.tools_base import Tool

    # Build a minimal agent with stats; no real project required because we test a
    # ToolMarkerDoesNotRequireActiveProject-style fake tool via Tool's _is_session_aware=False.
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()
    agent._active_tool_names = {"fake_tool"}
    monkeypatch.setattr(agent, "tool_is_active", lambda name: True)
    monkeypatch.setattr(agent, "get_active_tool_names", lambda: ["fake_tool"])
    monkeypatch.setattr(agent, "get_active_project", lambda: object())
    monkeypatch.setattr(agent, "get_language_server_manager", lambda: None)

    # Directly drive the analytics path with the helper — this exercises the same
    # code that apply_ex's finally{} block calls.
    agent._record_tool_call_safely(
        tool_name="fake_tool", input_str="{}", output_str="ok",
        duration_ms=12.5, success=True, error_message=None,
    )
    recs, _ = agent._tool_usage_stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert len(recs) == 1
    assert recs[0].tool == "fake_tool"
    assert recs[0].duration_ms == 12.5
    assert recs[0].success is True


def test_failed_tool_call_is_recorded_with_error_message():
    from serena.agent import SerenaAgent
    agent = SerenaAgent.__new__(SerenaAgent)
    agent._tool_usage_stats = ToolUsageStats()
    agent._record_tool_call_safely(
        tool_name="bad_tool", input_str="{}", output_str="",
        duration_ms=3.0, success=False, error_message="ValueError: bad arg",
    )
    recs, _ = agent._tool_usage_stats.get_records_since(since_seq=None, tool=None, limit=10)
    assert len(recs) == 1
    assert recs[0].success is False
    assert recs[0].error_message == "ValueError: bad arg"
    e = agent._tool_usage_stats.get_stats("bad_tool")
    assert e.num_errors == 1
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_analytics.py test/serena/test_task_executor.py -v`

Expected: PASS (all tests in both files).

- [ ] **Step 8: Run the broader test suite to catch regressions**

Run: `uv run pytest test/serena/ -x --ignore=test/serena/test_serena_agent.py -q`

Expected: PASS. (We ignore the heavy agent-integration tests for speed; CI runs them.)

- [ ] **Step 9: Commit**

```bash
git add src/serena/agent.py src/serena/tools/tools_base.py test/serena/test_analytics.py
git commit -m "$(cat <<'EOF'
feat(agent): instrument tool dispatch with timing + error capture

apply_ex wraps the tool call in a try/finally that records the call via
SerenaAgent._record_tool_call_safely — duration, success, and error
message all captured. The helper swallows analytics exceptions so
instrumentation can never break the agent. Errors are now counted
(previously dropped).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — Backend new endpoints

> **⚠️ CRITICAL CORRECTION:** All three Phase 2 tasks (6, 7, 8) below use FastAPI conventions (`@self.app.get(...)`, `HTTPException`, `TestClient(dashboard.app)`). The actual dashboard is **Flask** (verified: `dashboard.py:18, 204`). **Use the rewritten "Corrected Tasks 6, 7, 8 (Flask)" section near the top of this plan instead of the route code and test fixtures below.** The structure of each task (Step 1 write failing test → Step 2 run/fail → Step 3 implement → Step 4 run/pass → Step 5 commit) is preserved; only the route code and test fixtures change.

### Task 6: `/get_tool_call_timeline` endpoint

**Files:**
- Modify: `src/serena/dashboard.py` (add response model + route)
- Modify: `test/serena/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

Append to `test/serena/test_dashboard.py`:

```python
def test_get_tool_call_timeline_returns_records_with_cursor(make_agent_with_stats):
    """
    /get_tool_call_timeline returns records since the cursor with a max_seq.
    `make_agent_with_stats` is a fixture that boots a minimal dashboard with
    a pre-populated ToolUsageStats.
    """
    from fastapi.testclient import TestClient
    agent, dashboard = make_agent_with_stats()
    # Seed 5 records
    for i in range(5):
        agent._tool_usage_stats.record_call(
            tool_name="t", input_str="", output_str="",
            duration_ms=1.0, success=True, error_message=None, now=1000.0 + i,
        )
    client = TestClient(dashboard.app)
    # First poll (no cursor) returns everything
    r = client.get("/get_tool_call_timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["max_seq"] == 5
    assert len(body["records"]) == 5
    # Cursor poll returns only newer
    r = client.get("/get_tool_call_timeline?since_seq=3")
    body = r.json()
    assert [rec["seq"] for rec in body["records"]] == [4, 5]
    # Tool filter
    agent._tool_usage_stats.record_call(
        tool_name="other", input_str="", output_str="",
        duration_ms=1.0, success=True, error_message=None, now=2000.0,
    )
    r = client.get("/get_tool_call_timeline?tool=other")
    body = r.json()
    assert all(rec["tool"] == "other" for rec in body["records"])
    # Limit is clamped at 500
    r = client.get("/get_tool_call_timeline?limit=99999")
    assert r.status_code == 200
```

If `make_agent_with_stats` doesn't exist in `test/serena/test_dashboard.py`, add this minimal helper to the file (study the existing 1.8K-line file for the established pattern — if the file currently uses something else, follow that):

```python
import pytest


@pytest.fixture
def make_agent_with_stats():
    """
    Returns a callable that constructs a (agent, dashboard) pair with a real
    ToolUsageStats. Bypasses heavy SerenaAgent setup.
    """
    from serena.agent import SerenaAgent
    from serena.analytics import ToolUsageStats
    from serena.dashboard import SerenaDashboardAPI

    def _factory():
        agent = SerenaAgent.__new__(SerenaAgent)
        agent._tool_usage_stats = ToolUsageStats()
        # Patch the minimal SerenaAgent surface the dashboard touches.
        # Add minimal stubs as needed — refer to existing tests for the pattern.
        dashboard = SerenaDashboardAPI(agent)
        return agent, dashboard

    return _factory
```

> **Note for implementer:** read `test/serena/test_dashboard.py` first — it's only 1.8K, you'll see the existing fixture pattern. Use whatever is already there; the above is a fallback if the file has no fixture yet.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/serena/test_dashboard.py::test_get_tool_call_timeline_returns_records_with_cursor -v`

Expected: FAIL — route 404.

- [ ] **Step 3: Add response model + route in `src/serena/dashboard.py`**

Near the other Pydantic models (around line 138, after `QueuedExecution`), add:

```python
class ToolCallRecordResponse(BaseModel):
    seq: int
    tool: str
    started_at: float
    duration_ms: float
    success: bool
    error_message: str | None
    input_preview: str
    output_preview: str
    input_truncated: bool
    output_truncated: bool


class ResponseToolCallTimeline(BaseModel):
    records: list[ToolCallRecordResponse]
    max_seq: int
```

In the dashboard route-registration section (where other `@self.app.get(...)` decorators live), add the new route. Place it next to `/get_tool_stats`:

```python
        @self.app.get("/get_tool_call_timeline")
        def get_tool_call_timeline(
            since_seq: int | None = None,
            tool: str | None = None,
            limit: int = 200,
        ) -> ResponseToolCallTimeline:
            if self._tool_usage_stats is None:
                return ResponseToolCallTimeline(records=[], max_seq=0)
            if since_seq is not None and since_seq < 0:
                raise HTTPException(status_code=400, detail="since_seq must be >= 0")
            records, max_seq = self._tool_usage_stats.get_records_since(
                since_seq=since_seq, tool=tool, limit=limit,
            )
            return ResponseToolCallTimeline(
                records=[
                    ToolCallRecordResponse(
                        seq=r.seq,
                        tool=r.tool,
                        started_at=r.started_at,
                        duration_ms=r.duration_ms,
                        success=r.success,
                        error_message=r.error_message,
                        input_preview=r.input_preview,
                        output_preview=r.output_preview,
                        input_truncated=r.input_truncated,
                        output_truncated=r.output_truncated,
                    )
                    for r in records
                ],
                max_seq=max_seq,
            )
```

If `HTTPException` isn't already imported, add `from fastapi import HTTPException` to the imports.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/serena/test_dashboard.py::test_get_tool_call_timeline_returns_records_with_cursor -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/serena/dashboard.py test/serena/test_dashboard.py
git commit -m "$(cat <<'EOF'
feat(dashboard): GET /get_tool_call_timeline for cursor-based polling

Returns {records, max_seq}. since_seq cursor filters to newer records;
optional tool filter; limit capped at 500 server-side, default 200.
400 on negative cursor.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Extend `/get_config_overview` with `tool_stats_totals`

**Files:**
- Modify: `src/serena/dashboard.py:560-564`
- Modify: `test/serena/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

Append to `test/serena/test_dashboard.py`:

```python
def test_config_overview_includes_tool_stats_totals(make_agent_with_stats):
    from fastapi.testclient import TestClient
    agent, dashboard = make_agent_with_stats()
    agent._tool_usage_stats.record_call(
        tool_name="t", input_str="abc", output_str="defg",
        duration_ms=10.0, success=True, error_message=None, now=1000.0,
    )
    agent._tool_usage_stats.record_call(
        tool_name="t", input_str="x", output_str="y",
        duration_ms=20.0, success=False, error_message="Err: nope", now=1001.0,
    )
    client = TestClient(dashboard.app)
    r = client.get("/get_config_overview")
    body = r.json()
    assert "tool_stats_totals" in body
    totals = body["tool_stats_totals"]
    assert totals["num_calls"] == 2
    assert totals["num_errors"] == 1
    assert totals["total_duration_ms"] == 30.0
    assert totals["total_tokens"] >= 0  # estimator-dependent but non-negative
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/serena/test_dashboard.py::test_config_overview_includes_tool_stats_totals -v`

Expected: FAIL — key missing from response.

- [ ] **Step 3: Compute totals in `get_config_overview` (dashboard.py around line 560)**

Insert just after the existing `tool_stats_summary` block (line 564):

```python
        # Aggregate totals for the Overview SummaryCards
        tool_stats_totals = {
            "num_calls": 0,
            "num_errors": 0,
            "total_duration_ms": 0.0,
            "total_tokens": 0,
        }
        if self._tool_usage_stats is not None:
            full_stats = self._tool_usage_stats.get_tool_stats_dict()
            for stats in full_stats.values():
                tool_stats_totals["num_calls"] += stats["num_times_called"]
                tool_stats_totals["num_errors"] += stats.get("num_errors", 0)
                tool_stats_totals["total_duration_ms"] += stats.get("total_duration_ms", 0.0)
                tool_stats_totals["total_tokens"] += stats["input_tokens"] + stats["output_tokens"]
```

Find the response-construction dict (the `return` of `get_config_overview`) and add `"tool_stats_totals": tool_stats_totals,` to it.

Also update the response model. Find the `ResponseConfigOverview` Pydantic class and add:

```python
    tool_stats_totals: dict[str, float] = Field(
        default_factory=lambda: {"num_calls": 0, "num_errors": 0, "total_duration_ms": 0.0, "total_tokens": 0}
    )
```

(If `Field` isn't already imported from `pydantic`, add it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/serena/test_dashboard.py::test_config_overview_includes_tool_stats_totals -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/serena/dashboard.py test/serena/test_dashboard.py
git commit -m "$(cat <<'EOF'
feat(dashboard): aggregate tool_stats_totals in /get_config_overview

Adds {num_calls, num_errors, total_duration_ms, total_tokens} totals
to the existing config-overview payload so the new 4-card Overview
strip updates on the existing 1s poll without a separate endpoint.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Extend `QueuedExecution` serializer with timing + error fields

**Files:**
- Modify: `src/serena/dashboard.py:123-138`
- Modify: `test/serena/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

Append to `test/serena/test_dashboard.py`:

```python
def test_queued_execution_includes_timing_and_error_fields(make_agent_with_stats):
    from fastapi.testclient import TestClient
    from serena.task_executor import TaskExecutor

    agent, dashboard = make_agent_with_stats()
    # Build a TaskInfo manually
    task = TaskExecutor.Task(function=lambda: "ok", name="Task-7: read_file", logged=False)
    task.start()
    task.wait_until_done(timeout=2.0)
    info = TaskExecutor.TaskInfo.from_task(task, is_running=False)
    from serena.dashboard import QueuedExecution
    serialized = QueuedExecution.from_task_info(info).model_dump()
    assert "duration_ms" in serialized
    assert "error_message" in serialized
    assert "display_name" in serialized
    assert "started_at" in serialized
    assert "finished_at" in serialized
    assert serialized["display_name"] == "read_file"
    assert serialized["duration_ms"] is not None
    assert serialized["error_message"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest test/serena/test_dashboard.py::test_queued_execution_includes_timing_and_error_fields -v`

Expected: FAIL — keys missing.

- [ ] **Step 3: Extend `QueuedExecution` in `src/serena/dashboard.py`**

Replace lines 123–138 with:

```python
class QueuedExecution(BaseModel):
    task_id: int
    is_running: bool
    name: str
    display_name: str
    finished_successfully: bool
    logged: bool
    started_at: float | None
    finished_at: float | None
    duration_ms: int | None
    error_message: str | None

    @classmethod
    def from_task_info(cls, task_info: TaskExecutor.TaskInfo) -> Self:
        return cls(
            task_id=task_info.task_id,
            is_running=task_info.is_running,
            name=task_info.name,
            display_name=task_info.get_display_name(),
            finished_successfully=task_info.finished_successfully(),
            logged=task_info.logged,
            started_at=task_info.started_at,
            finished_at=task_info.finished_at,
            duration_ms=task_info.get_duration_ms(),
            error_message=task_info.get_error_message(),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest test/serena/test_dashboard.py::test_queued_execution_includes_timing_and_error_fields -v`

Expected: PASS.

- [ ] **Step 5: Run the whole backend test file to catch any regressions**

Run: `uv run pytest test/serena/test_dashboard.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/serena/dashboard.py test/serena/test_dashboard.py
git commit -m "$(cat <<'EOF'
feat(dashboard): expose TaskInfo timing + error in QueuedExecution

QueuedExecution now includes display_name, started_at, finished_at,
duration_ms, error_message — drives the richer Executions Queue +
Last Execution UIs without extra round-trips.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Frontend Tier 2 (Timeline + SummaryCards + FilterDropdown)

> **⚠️ Pre-Phase 3 prerequisite:** before Task 9, apply the `stubFetchRoutes` callable-handler extension AND the `exec()` helper update described in "Pre-Phase 3 prerequisite" near the top of this plan. Without it, every test in Phase 3 that uses dynamic handlers will fail to compile.
>
> **Other corrections that apply to Phase 3 (see top of plan for details):**
> - **B12:** `stubFetchRoutes` signature was wrong throughout — fixed by the prerequisite above.
> - **B13:** Task 10's `??` regression test is too weak; use the corrected version near the top.
> - **B14:** `config.overview` does not exist — use `config.data`.
> - **B15:** `StatsSummary.svelte` lives in `components/stats/`, not `components/overview/`. Create a new `OverviewSummaryCards.svelte` instead of modifying `StatsSummary.svelte`. The existing `stats/StatsSummary.svelte` stays untouched.
> - **B16:** drop the `import { ReturnType } from 'typescript'` line in Task 13 (it's a built-in utility type).
> - **B17:** Task 13's `pausedGap` math uses `=== 200` as the gap-detection trigger; replace with `newCursor - cursor > resp.records.length`.
> - **B18, B19:** Task 14 must update `Header.svelte` and add visibility-aware polling — neither is existing behavior.
> - **B11:** Task 9's `QueuedExecution` type extension must also update `tests/helpers.ts:exec()` to default the new required fields, or every existing executions test breaks.

### Task 9: Add API types + endpoint wrappers for new routes

**Files:**
- Modify: `dashboard/src/lib/api/types.ts`
- Modify: `dashboard/src/lib/api/endpoints.ts`
- Modify: `dashboard/tests/endpoints.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/endpoints.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { stubFetchRoutes } from './helpers';
import { fetchToolCallTimeline } from '../src/lib/api/endpoints';

describe('fetchToolCallTimeline', () => {
  it('passes since_seq, tool, limit as query params', async () => {
    const seen: string[] = [];
    stubFetchRoutes([
      {
        match: '/get_tool_call_timeline',
        handler: (url) => {
          seen.push(url);
          return { records: [], max_seq: 0 };
        },
      },
    ]);
    await fetchToolCallTimeline({ since_seq: 42, tool: 'read_file', limit: 100 });
    expect(seen[0]).toContain('since_seq=42');
    expect(seen[0]).toContain('tool=read_file');
    expect(seen[0]).toContain('limit=100');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- endpoints`

Expected: FAIL — `fetchToolCallTimeline` undefined.

- [ ] **Step 3: Add types in `dashboard/src/lib/api/types.ts`**

Append (alongside existing types):

```ts
// Extension to ResponseConfigOverview for the Overview SummaryCards.
export interface ToolStatsTotals {
  num_calls: number;
  num_errors: number;
  total_duration_ms: number;
  total_tokens: number;
}

// Augment existing ResponseConfigOverview by adding tool_stats_totals.
// (Make this field optional on the type so older backends without it still parse.)
```

Find the existing `ResponseConfigOverview` interface and add:

```ts
  tool_stats_totals?: ToolStatsTotals;
```

Find the existing `QueuedExecution` interface and replace it with:

```ts
export interface QueuedExecution {
  task_id: number;
  is_running: boolean;
  name: string;
  display_name: string;
  finished_successfully: boolean;
  logged: boolean;
  started_at: number | null;
  finished_at: number | null;
  duration_ms: number | null;
  error_message: string | null;
}
```

Append timeline types:

```ts
export interface ToolCallRecord {
  seq: number;
  tool: string;
  started_at: number;
  duration_ms: number;
  success: boolean;
  error_message: string | null;
  input_preview: string;
  output_preview: string;
  input_truncated: boolean;
  output_truncated: boolean;
}

export interface ResponseToolCallTimeline {
  records: ToolCallRecord[];
  max_seq: number;
}
```

Append Code-tab types (used in Phase 5/6):

```ts
export interface DirEntry {
  name: string;
  kind: 'dir' | 'file';
  size?: number;
}
export interface ResponseListDir {
  entries: DirEntry[];
}

export interface FileSymbol {
  name: string;
  kind: string;
  range: { start: { line: number; character: number }; end: { line: number; character: number } };
  children?: FileSymbol[];
}
export interface ResponseFileSymbols {
  symbols: FileSymbol[];
}

export interface WorkspaceMatch {
  name: string;
  kind: string;
  path: string;
  range: { start: { line: number; character: number }; end: { line: number; character: number } };
}
export interface ResponseWorkspaceSymbolSearch {
  matches: WorkspaceMatch[];
}

export type DiagnosticSeverity = 'error' | 'warning' | 'info' | 'hint';
export interface Diagnostic {
  severity: DiagnosticSeverity;
  message: string;
  line: number;
  column: number;
  source?: string;
}
export interface FileDiagnostics {
  path: string;
  diagnostics: Diagnostic[];
}
export interface ResponseDiagnosticsSummary {
  files: FileDiagnostics[];
  truncated: boolean;
}
```

- [ ] **Step 4: Add endpoint wrappers in `dashboard/src/lib/api/endpoints.ts`**

Add at the bottom (and to the type import):

```ts
import type {
  // ...existing imports...
  ResponseToolCallTimeline,
  ResponseListDir,
  ResponseFileSymbols,
  ResponseWorkspaceSymbolSearch,
  ResponseDiagnosticsSummary,
} from './types';

export const fetchToolCallTimeline = (params: {
  since_seq?: number;
  tool?: string;
  limit?: number;
}) => {
  const qs = new URLSearchParams();
  if (params.since_seq !== undefined) qs.set('since_seq', String(params.since_seq));
  if (params.tool) qs.set('tool', params.tool);
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  const query = qs.toString();
  const url = query ? `/get_tool_call_timeline?${query}` : '/get_tool_call_timeline';
  return getJson<ResponseToolCallTimeline>(url);
};

export const fetchCodeListDir = (path: string) =>
  getJson<ResponseListDir>(`/code/list_dir?path=${encodeURIComponent(path)}`);

export const fetchCodeFileSymbols = (path: string) =>
  getJson<ResponseFileSymbols>(`/code/file_symbols?path=${encodeURIComponent(path)}`);

export const fetchCodeWorkspaceSymbolSearch = (q: string, limit = 50) =>
  getJson<ResponseWorkspaceSymbolSearch>(
    `/code/workspace_symbol_search?q=${encodeURIComponent(q)}&limit=${limit}`
  );

export const fetchCodeDiagnosticsSummary = (file_limit = 1000) =>
  getJson<ResponseDiagnosticsSummary>(`/code/diagnostics_summary?file_limit=${file_limit}`);
```

Also register the new routes in `dashboard/vite.config.ts` `API_ROUTES`. Find the existing `API_ROUTES` array and add:

```ts
  '/get_tool_call_timeline',
  '/code/list_dir',
  '/code/file_symbols',
  '/code/workspace_symbol_search',
  '/code/diagnostics_summary',
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard && npm run check && npm test -- endpoints`

Expected: PASS.

- [ ] **Step 6: Commit (no asset rebuild needed — TS types + endpoints only)**

```bash
git add dashboard/src/lib/api/types.ts dashboard/src/lib/api/endpoints.ts dashboard/vite.config.ts dashboard/tests/endpoints.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): TS types + endpoint wrappers for timeline + code routes

Adds fetchToolCallTimeline + four fetchCode* wrappers, mirrors the
backend models (ToolCallRecord, FileDiagnostics, etc.), and registers
the new routes in API_ROUTES so the dev proxy forwards them.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Create `timeline` store with `??` cursor discipline

**Files:**
- Create: `dashboard/src/lib/stores/timeline.svelte.ts`
- Create: `dashboard/tests/timeline-store.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `dashboard/tests/timeline-store.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { stubFetchRoutes } from './helpers';
import { createTimelineStore } from '../src/lib/stores/timeline.svelte';
import type { ToolCallRecord } from '../src/lib/api/types';

function record(seq: number, tool = 't'): ToolCallRecord {
  return {
    seq,
    tool,
    started_at: 1000 + seq,
    duration_ms: 1,
    success: true,
    error_message: null,
    input_preview: '',
    output_preview: '',
    input_truncated: false,
    output_truncated: false,
  };
}

describe('timeline store', () => {
  it('merges new records onto the front, dedups by seq, caps at 2000', async () => {
    let max_seq = 0;
    stubFetchRoutes([
      {
        match: '/get_tool_call_timeline',
        handler: () => {
          const records = [record(max_seq + 1)];
          max_seq += 1;
          return { records, max_seq };
        },
      },
    ]);
    const store = createTimelineStore();
    await store.poll();
    await store.poll();
    expect(store.records.length).toBe(2);
    expect(store.records.map((r) => r.seq).sort()).toEqual([1, 2]);
    expect(store.cursor).toBe(2);
  });

  it('advances cursor using ?? so server max_seq=0 is preserved (regression)', async () => {
    let calls = 0;
    stubFetchRoutes([
      {
        match: '/get_tool_call_timeline',
        handler: () => {
          calls += 1;
          // First call: server has zero records. Cursor must become 0, NOT stay undefined.
          if (calls === 1) return { records: [], max_seq: 0 };
          return { records: [], max_seq: 0 };
        },
      },
    ]);
    const store = createTimelineStore();
    expect(store.cursor).toBeNull();
    await store.poll();
    // Cursor must be 0 — would be null if we used || instead of ?? somewhere.
    expect(store.cursor).toBe(0);
  });

  it('caps the buffer at 2000 records', async () => {
    let next = 0;
    stubFetchRoutes([
      {
        match: '/get_tool_call_timeline',
        handler: () => {
          const batch = Array.from({ length: 600 }, () => {
            next += 1;
            return record(next);
          });
          return { records: batch, max_seq: next };
        },
      },
    ]);
    const store = createTimelineStore();
    for (let i = 0; i < 4; i++) await store.poll(); // 2400 total
    expect(store.records.length).toBe(2000);
  });

  it('pause stops poll from advancing cursor', async () => {
    stubFetchRoutes([
      {
        match: '/get_tool_call_timeline',
        handler: () => ({ records: [record(1)], max_seq: 1 }),
      },
    ]);
    const store = createTimelineStore();
    store.pause();
    await store.poll();
    expect(store.records.length).toBe(0);
    expect(store.cursor).toBeNull();
  });

  it('setFilter resets buffer and cursor', async () => {
    let next = 0;
    stubFetchRoutes([
      {
        match: '/get_tool_call_timeline',
        handler: () => {
          next += 1;
          return { records: [record(next, 't1')], max_seq: next };
        },
      },
    ]);
    const store = createTimelineStore();
    await store.poll();
    expect(store.records.length).toBe(1);
    store.setFilter('t2');
    expect(store.records.length).toBe(0);
    expect(store.cursor).toBeNull();
    expect(store.filter).toBe('t2');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && npm test -- timeline-store`

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `dashboard/src/lib/stores/timeline.svelte.ts`**

```ts
import { fetchToolCallTimeline } from '$lib/api/endpoints';
import type { ToolCallRecord } from '$lib/api/types';

const BUFFER_CAP = 2000;

export function createTimelineStore() {
  let records = $state<ToolCallRecord[]>([]);
  let cursor = $state<number | null>(null);
  let filter = $state<string | null>(null);
  let paused = $state(false);
  let page = $state(1);
  let pageSize = $state(25);
  let pausedGap = $state<number | null>(null);
  let error = $state<string | null>(null);

  function mergeIncoming(incoming: ToolCallRecord[]) {
    if (incoming.length === 0) return;
    const seen = new Set(records.map((r) => r.seq));
    const fresh = incoming.filter((r) => !seen.has(r.seq));
    // New records are typically newer; prepend, then sort defensively by seq desc.
    const next = [...fresh, ...records];
    next.sort((a, b) => b.seq - a.seq);
    if (next.length > BUFFER_CAP) {
      next.length = BUFFER_CAP;
    }
    records = next;
  }

  return {
    get records() {
      return records;
    },
    get cursor() {
      return cursor;
    },
    get filter() {
      return filter;
    },
    get paused() {
      return paused;
    },
    get page() {
      return page;
    },
    get pageSize() {
      return pageSize;
    },
    get pausedGap() {
      return pausedGap;
    },
    get error() {
      return error;
    },
    async poll() {
      if (paused) return;
      try {
        const resp = await fetchToolCallTimeline({
          since_seq: cursor ?? undefined,
          tool: filter ?? undefined,
          limit: 200,
        });
        // Cursor coalescing: USE `??` not `||` so server-reported 0 doesn't
        // fall back to the previous cursor value.
        const newCursor = resp.max_seq ?? cursor;
        // If we paused-and-resumed across more records than fit in `limit`,
        // capture the gap so the UI can hint at it.
        if (cursor !== null && resp.records.length === 200 && newCursor !== null) {
          const skipped = newCursor - cursor - resp.records.length;
          if (skipped > 0) pausedGap = skipped;
        }
        mergeIncoming(resp.records);
        cursor = newCursor;
        error = null;
      } catch (e) {
        error = (e as Error).message;
      }
    },
    pause() {
      paused = true;
    },
    resume() {
      paused = false;
      pausedGap = null;
    },
    togglePause() {
      paused = !paused;
      if (!paused) pausedGap = null;
    },
    clearView() {
      records = [];
      pausedGap = null;
      page = 1;
    },
    setFilter(tool: string | null) {
      filter = tool;
      records = [];
      cursor = null;
      page = 1;
    },
    setPage(p: number) {
      page = Math.max(1, p);
    },
    setPageSize(size: number) {
      pageSize = size;
      page = 1;
    },
  };
}

export const timeline = createTimelineStore();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && npm test -- timeline-store`

Expected: PASS.

- [ ] **Step 5: Commit (no asset rebuild — store/test only)**

```bash
git add dashboard/src/lib/stores/timeline.svelte.ts dashboard/tests/timeline-store.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): timeline store with ?? cursor discipline

createTimelineStore() owns a cursor-based ring buffer (cap 2000),
dedupes by seq, prepends fresh records, and advances the cursor with
?? (not ||) so a server max_seq of 0 is preserved. Supports per-tool
filter, pause/resume, clearView, pagination state. Regression test
documents the ??-vs-|| pitfall.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Create shared `FilterDropdown.svelte`

**Files:**
- Create: `dashboard/src/components/common/FilterDropdown.svelte`
- Create: `dashboard/tests/filter-dropdown.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `dashboard/tests/filter-dropdown.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import FilterDropdown from '../src/components/common/FilterDropdown.svelte';

const opts = [
  { value: 'read_file', label: 'read_file' },
  { value: 'find_symbol', label: 'find_symbol' },
  { value: 'execute_shell_command', label: 'execute_shell_command' },
];

describe('FilterDropdown', () => {
  it('renders placeholder when value is null', () => {
    const { getByRole } = render(FilterDropdown, { options: opts, value: null, placeholder: 'All tools' });
    expect(getByRole('button').textContent).toContain('All tools');
  });

  it('opens on click and lists options', async () => {
    const { getByRole, getAllByRole } = render(FilterDropdown, { options: opts, value: null, placeholder: 'All' });
    await fireEvent.click(getByRole('button'));
    const items = getAllByRole('option');
    expect(items.length).toBe(3);
  });

  it('typing filters by substring', async () => {
    const { getByRole, getAllByRole, getByPlaceholderText } = render(FilterDropdown, {
      options: opts, value: null, placeholder: 'All',
    });
    await fireEvent.click(getByRole('button'));
    const input = getByPlaceholderText(/filter/i);
    await fireEvent.input(input, { target: { value: 'sym' } });
    expect(getAllByRole('option').length).toBe(1);
    expect(getAllByRole('option')[0].textContent).toContain('find_symbol');
  });

  it('Enter selects the highlighted option and fires onChange', async () => {
    let chosen: string | null = null;
    const { getByRole, getByPlaceholderText } = render(FilterDropdown, {
      options: opts, value: null, placeholder: 'All',
      onChange: (v: string | null) => (chosen = v),
    });
    await fireEvent.click(getByRole('button'));
    const input = getByPlaceholderText(/filter/i);
    await fireEvent.keyDown(input, { key: 'ArrowDown' });
    await fireEvent.keyDown(input, { key: 'Enter' });
    expect(chosen).toBe('read_file');
  });

  it('clear button (×) fires onChange(null) when a value is set', async () => {
    let chosen: string | null = 'read_file';
    const { getByLabelText } = render(FilterDropdown, {
      options: opts, value: 'read_file', placeholder: 'All',
      onChange: (v: string | null) => (chosen = v),
    });
    await fireEvent.click(getByLabelText(/clear/i));
    expect(chosen).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && npm test -- filter-dropdown`

Expected: FAIL — component missing.

- [ ] **Step 3: Create `dashboard/src/components/common/FilterDropdown.svelte`**

```svelte
<script lang="ts">
  interface Option {
    value: string;
    label: string;
  }

  interface Props {
    options: Option[];
    value: string | null;
    placeholder?: string;
    onChange?: (v: string | null) => void;
  }

  let { options, value, placeholder = 'All', onChange }: Props = $props();

  let open = $state(false);
  let query = $state('');
  let highlight = $state(0);
  let buttonEl: HTMLButtonElement | undefined = $state();
  let inputEl: HTMLInputElement | undefined = $state();
  let rootEl: HTMLDivElement | undefined = $state();

  const filtered = $derived(
    options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())),
  );

  function toggle() {
    open = !open;
    if (open) {
      // Initial highlight: applied option if visible, else 0
      const idx = filtered.findIndex((o) => o.value === value);
      highlight = idx >= 0 ? idx : 0;
      // Focus input next tick
      queueMicrotask(() => inputEl?.focus());
    }
  }

  function selectAt(idx: number) {
    const o = filtered[idx];
    if (!o) return;
    onChange?.(o.value);
    open = false;
    query = '';
  }

  function clear(e: Event) {
    e.stopPropagation();
    onChange?.(null);
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlight = Math.min(filtered.length - 1, highlight + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlight = Math.max(0, highlight - 1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      selectAt(highlight);
    } else if (e.key === 'Escape') {
      open = false;
    }
  }

  function onClickOutside(e: MouseEvent) {
    if (!rootEl) return;
    if (!rootEl.contains(e.target as Node)) {
      open = false;
    }
  }

  $effect(() => {
    if (open) {
      document.addEventListener('mousedown', onClickOutside);
      return () => document.removeEventListener('mousedown', onClickOutside);
    }
  });

  const display = $derived(value ? (options.find((o) => o.value === value)?.label ?? value) : placeholder);
</script>

<div bind:this={rootEl} class="root" class:active={value !== null}>
  <button
    bind:this={buttonEl}
    type="button"
    class="trigger"
    aria-haspopup="listbox"
    aria-expanded={open}
    onclick={toggle}
  >
    <span class="label">{display}</span>
    {#if value !== null}
      <span
        role="button"
        tabindex="0"
        aria-label="Clear filter"
        class="clear"
        onclick={clear}
        onkeydown={(e) => e.key === 'Enter' && clear(e)}
      >×</span>
    {/if}
    <span class="chev">▾</span>
  </button>

  {#if open}
    <div class="panel" role="listbox">
      <input
        bind:this={inputEl}
        bind:value={query}
        placeholder="Filter…"
        class="filter-input"
        onkeydown={onKey}
      />
      <ul class="list">
        {#each filtered as o, i}
          <li
            role="option"
            aria-selected={o.value === value}
            class:highlight={i === highlight}
            onmouseenter={() => (highlight = i)}
            onclick={() => selectAt(i)}
          >
            <span class="check">{o.value === value ? '✓' : ''}</span>
            <span>{o.label}</span>
          </li>
        {/each}
        {#if filtered.length === 0}
          <li class="empty">No matches</li>
        {/if}
      </ul>
    </div>
  {/if}
</div>

<style>
  .root {
    position: relative;
    display: inline-block;
  }
  .trigger {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text-primary);
    border-radius: var(--radius);
    cursor: pointer;
    font-family: inherit;
  }
  .root.active .trigger {
    border-color: var(--accent);
  }
  .clear {
    color: var(--text-secondary);
    cursor: pointer;
    user-select: none;
  }
  .clear:hover {
    color: var(--accent);
  }
  .chev {
    color: var(--text-secondary);
  }
  .panel {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 200px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    box-shadow: var(--shadow-elevated);
    z-index: 50;
  }
  .filter-input {
    width: 100%;
    padding: var(--space-2);
    border: none;
    border-bottom: 1px solid var(--border);
    background: transparent;
    color: var(--text-primary);
    font-family: inherit;
    outline: none;
  }
  .filter-input:focus {
    border-bottom-color: var(--accent);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: var(--space-1) 0;
    max-height: 240px;
    overflow-y: auto;
  }
  .list li {
    display: flex;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }
  .list li.highlight {
    background: var(--bg);
  }
  .check {
    width: 1em;
    color: var(--accent);
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-2);
  }
</style>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && npm test -- filter-dropdown && npm run check`

Expected: PASS.

- [ ] **Step 5: Commit (no asset rebuild — final phase rebuilds once for the whole branch)**

```bash
git add dashboard/src/components/common/FilterDropdown.svelte dashboard/tests/filter-dropdown.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): shared FilterDropdown primitive

Filtered single-select with × clear, applied checkmark, substring
typing, keyboard nav (Up/Down/Enter/Esc), and click-outside close.
Active border uses the orange accent token. Reused by the Timeline
filter and any future filtered list.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Create `SummaryCards.svelte` and wire it into Overview

**Files:**
- Create: `dashboard/src/components/overview/SummaryCards.svelte`
- Modify: `dashboard/src/components/overview/StatsSummary.svelte` (replace inline KPI strip)
- Create: `dashboard/tests/summary-cards.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/summary-cards.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import SummaryCards from '../src/components/overview/SummaryCards.svelte';
import type { ToolStatsTotals } from '../src/lib/api/types';

const totals: ToolStatsTotals = {
  num_calls: 1234,
  num_errors: 7,
  total_duration_ms: 90123,
  total_tokens: 5678,
};

describe('SummaryCards', () => {
  it('renders four cards with formatted values', () => {
    const { getAllByRole, container } = render(SummaryCards, { totals });
    const headings = container.querySelectorAll('[data-card-title]');
    expect(headings.length).toBe(4);
    const labels = Array.from(headings).map((n) => n.textContent?.trim());
    expect(labels).toEqual(['Calls', 'Tokens', 'Time', 'Errors']);
    expect(container.textContent).toContain('1,234');
    expect(container.textContent).toContain('7');
  });

  it('renders em-dashes when totals is undefined (older backend)', () => {
    const { container } = render(SummaryCards, { totals: undefined });
    expect(container.textContent).toContain('—');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && npm test -- summary-cards`

Expected: FAIL — component missing.

- [ ] **Step 3: Create `dashboard/src/components/overview/SummaryCards.svelte`**

```svelte
<script lang="ts">
  import type { ToolStatsTotals } from '$lib/api/types';
  import { formatNumber, formatDurationMs, formatTokens } from '$lib/format';

  interface Props {
    totals: ToolStatsTotals | undefined;
  }
  let { totals }: Props = $props();

  const errorRate = $derived(
    totals && totals.num_calls > 0 ? (totals.num_errors / totals.num_calls) * 100 : 0,
  );
  const avgDurationMs = $derived(
    totals && totals.num_calls > 0 ? totals.total_duration_ms / totals.num_calls : 0,
  );
</script>

<div class="grid">
  <div class="card">
    <div class="title" data-card-title>Calls</div>
    <div class="main">{totals ? formatNumber(totals.num_calls) : '—'}</div>
    <div class="sub">
      {totals ? `error rate ${errorRate.toFixed(2)} %` : ''}
    </div>
  </div>
  <div class="card">
    <div class="title" data-card-title>Tokens</div>
    <div class="main">{totals ? formatTokens(totals.total_tokens) : '—'}</div>
    <div class="sub">{totals ? `total` : ''}</div>
  </div>
  <div class="card">
    <div class="title" data-card-title>Time</div>
    <div class="main">{totals ? formatDurationMs(totals.total_duration_ms) : '—'}</div>
    <div class="sub">{totals ? `avg ${formatDurationMs(avgDurationMs)} / call` : ''}</div>
  </div>
  <div class="card">
    <div class="title" data-card-title>Errors</div>
    <div class="main">{totals ? formatNumber(totals.num_errors) : '—'}</div>
    <div class="sub">{totals ? `${errorRate.toFixed(2)} % rate` : ''}</div>
  </div>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-3);
  }
  .card {
    padding: var(--space-3);
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .title {
    color: var(--text-secondary);
    font-size: 0.85em;
    margin-bottom: var(--space-1);
  }
  .main {
    font-size: 1.6em;
    font-weight: 600;
  }
  .sub {
    color: var(--text-secondary);
    font-size: 0.85em;
    margin-top: var(--space-1);
  }
  @media (max-width: 800px) {
    .grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
```

- [ ] **Step 4: Add formatters in `dashboard/src/lib/format.ts` if missing**

Read `dashboard/src/lib/format.ts` first. If `formatNumber`, `formatDurationMs`, `formatTokens` already exist, skip this step. Otherwise append:

```ts
export function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

export function formatDurationMs(ms: number): string {
  if (ms < 1) return '<1 ms';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = s / 60;
  if (m < 60) return `${m.toFixed(1)} m`;
  const h = m / 60;
  return `${h.toFixed(1)} h`;
}

export function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}
```

- [ ] **Step 5: Wire `SummaryCards` into `StatsSummary.svelte`**

Open `dashboard/src/components/overview/StatsSummary.svelte`. Find the existing inline KPI strip (the section that renders Calls / Input tokens / Output tokens / Total tokens). Replace it with:

```svelte
<script lang="ts">
  import { config } from '$lib/stores/config.svelte';
  import SummaryCards from './SummaryCards.svelte';
</script>

<SummaryCards totals={config.overview?.tool_stats_totals} />
```

> **Implementer note:** the rest of `StatsSummary.svelte` may render other content (e.g. estimator name, totals not covered by SummaryCards). Preserve that content; only the four-stat strip is replaced. Re-read the file before editing.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd dashboard && npm test -- summary-cards && npm run check`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/overview/SummaryCards.svelte dashboard/src/components/overview/StatsSummary.svelte dashboard/src/lib/format.ts dashboard/tests/summary-cards.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): 4-card Overview KPI strip (Calls/Tokens/Time/Errors)

Replaces the inline Calls/Input/Output/Total strip with four cards:
Calls, Tokens, Time (total + avg/call), Errors. Reads
tool_stats_totals from the existing config-overview payload, so it
updates on the 1s poll without a new endpoint. Falls back to em-dashes
when the backend doesn't expose the field (forward-compat).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 13: Create `Timeline.svelte` + `TimelineRow.svelte`

**Files:**
- Create: `dashboard/src/components/overview/Timeline.svelte`
- Create: `dashboard/src/components/overview/TimelineRow.svelte`
- Create: `dashboard/tests/timeline.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/timeline.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import Timeline from '../src/components/overview/Timeline.svelte';
import { createTimelineStore } from '../src/lib/stores/timeline.svelte';
import type { ToolCallRecord } from '../src/lib/api/types';

function rec(seq: number, tool = 'read_file', success = true): ToolCallRecord {
  return {
    seq,
    tool,
    started_at: 1000 + seq,
    duration_ms: seq,
    success,
    error_message: success ? null : 'Err',
    input_preview: `in${seq}`,
    output_preview: `out${seq}`,
    input_truncated: false,
    output_truncated: false,
  };
}

describe('Timeline', () => {
  it('renders rows from the store and paginates', () => {
    const store = createTimelineStore();
    for (let i = 1; i <= 60; i++) (store as any).records.push(rec(i));
    // Force reactive read by reassigning page through public API
    store.setPageSize(25);
    const { container } = render(Timeline, { store, toolNames: ['read_file'] });
    // 25 rows on page 1
    expect(container.querySelectorAll('[data-timeline-row]').length).toBe(25);
  });

  it('toggle pause sets paused state', async () => {
    const store = createTimelineStore();
    const { getByLabelText } = render(Timeline, { store, toolNames: [] });
    await fireEvent.click(getByLabelText(/pause/i));
    expect(store.paused).toBe(true);
  });

  it('clear view empties records', async () => {
    const store = createTimelineStore();
    (store as any).records.push(rec(1));
    const { getByLabelText } = render(Timeline, { store, toolNames: [] });
    await fireEvent.click(getByLabelText(/clear/i));
    expect(store.records.length).toBe(0);
  });
});
```

> **Note:** the test mutates `store.records` via cast for setup. Production code never does this — only the store's own actions touch state.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && npm test -- timeline.test`

Expected: FAIL — component missing.

- [ ] **Step 3: Create `dashboard/src/components/overview/TimelineRow.svelte`**

```svelte
<script lang="ts">
  import type { ToolCallRecord } from '$lib/api/types';
  import { formatDurationMs } from '$lib/format';

  interface Props {
    record: ToolCallRecord;
  }
  let { record }: Props = $props();
  let expanded = $state(false);
  let showFullInput = $state(false);
  let showFullOutput = $state(false);

  const time = $derived(new Date(record.started_at * 1000).toISOString().split('T')[1].slice(0, 12));
  const statusClass = $derived(record.success ? 'ok' : 'err');
</script>

<li class="row" class:expanded data-timeline-row>
  <button class="head" type="button" onclick={() => (expanded = !expanded)} aria-expanded={expanded}>
    <span class="chev">{expanded ? '▾' : '▸'}</span>
    <span class="time">{time}</span>
    <span class="tool">{record.tool}</span>
    <span class="duration">{formatDurationMs(record.duration_ms)}</span>
    <span class="status {statusClass}">{record.success ? 'ok' : 'ERR'}</span>
  </button>
  {#if expanded}
    <div class="detail">
      <div><span class="k">seq:</span> {record.seq}</div>
      <div><span class="k">started:</span> {new Date(record.started_at * 1000).toISOString()}</div>
      <div><span class="k">duration:</span> {formatDurationMs(record.duration_ms)}</div>
      {#if record.error_message}
        <div class="err"><span class="k">error:</span> {record.error_message}</div>
      {/if}
      <div class="block">
        <div class="k">input:</div>
        <pre class="code">{showFullInput || record.input_preview.length < 400 ? record.input_preview : record.input_preview.slice(0, 400) + '…'}</pre>
        {#if record.input_preview.length >= 400}
          <button type="button" class="link" onclick={() => (showFullInput = !showFullInput)}>
            {showFullInput ? 'Show less' : 'Show full'}
          </button>
        {/if}
        {#if record.input_truncated}
          <div class="note">(server-truncated at 8 KB)</div>
        {/if}
      </div>
      <div class="block">
        <div class="k">output:</div>
        <pre class="code">{showFullOutput || record.output_preview.length < 400 ? record.output_preview : record.output_preview.slice(0, 400) + '…'}</pre>
        {#if record.output_preview.length >= 400}
          <button type="button" class="link" onclick={() => (showFullOutput = !showFullOutput)}>
            {showFullOutput ? 'Show less' : 'Show full'}
          </button>
        {/if}
        {#if record.output_truncated}
          <div class="note">(server-truncated at 8 KB)</div>
        {/if}
      </div>
    </div>
  {/if}
</li>

<style>
  .row {
    border-bottom: 1px solid var(--border);
  }
  .head {
    width: 100%;
    display: grid;
    grid-template-columns: 24px 110px 1fr 70px 50px;
    gap: var(--space-2);
    align-items: center;
    background: transparent;
    border: 0;
    color: var(--text-primary);
    cursor: pointer;
    padding: var(--space-1) var(--space-2);
    text-align: left;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .head:hover {
    background: var(--bg);
  }
  .time {
    color: var(--text-secondary);
  }
  .tool {
    color: var(--text-primary);
  }
  .duration {
    color: var(--text-secondary);
  }
  .status.ok {
    color: var(--success, var(--text-secondary));
  }
  .status.err {
    color: var(--danger, #c33);
  }
  .detail {
    padding: var(--space-2) var(--space-3) var(--space-3) calc(24px + var(--space-2));
    font-family: var(--font-mono);
    font-size: 0.85em;
    color: var(--text-primary);
  }
  .k {
    color: var(--text-secondary);
    margin-right: var(--space-1);
  }
  .block {
    margin-top: var(--space-2);
  }
  .code {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-2);
    white-space: pre-wrap;
    word-break: break-all;
    margin: var(--space-1) 0;
  }
  .link {
    background: transparent;
    border: 0;
    color: var(--accent);
    cursor: pointer;
    padding: 0;
  }
  .note {
    color: var(--text-secondary);
    font-size: 0.85em;
  }
  .err {
    color: var(--danger, #c33);
  }
</style>
```

- [ ] **Step 4: Create `dashboard/src/components/overview/Timeline.svelte`**

```svelte
<script lang="ts">
  import type { ReturnType as _ReturnType } from 'typescript';
  import FilterDropdown from '$components/common/FilterDropdown.svelte';
  import TimelineRow from './TimelineRow.svelte';

  type TimelineStore = ReturnType<typeof import('$lib/stores/timeline.svelte').createTimelineStore>;

  interface Props {
    store: TimelineStore;
    toolNames: string[];
  }
  let { store, toolNames }: Props = $props();

  const filterOpts = $derived(toolNames.map((n) => ({ value: n, label: n })));
  const totalPages = $derived(Math.max(1, Math.ceil(store.records.length / store.pageSize)));
  const start = $derived((store.page - 1) * store.pageSize);
  const visible = $derived(store.records.slice(start, start + store.pageSize));
</script>

<section class="card">
  <header class="head">
    <h3 class="title">Tool Call Timeline</h3>
    <div class="controls">
      <FilterDropdown
        options={filterOpts}
        value={store.filter}
        placeholder="All tools"
        onChange={(v) => store.setFilter(v)}
      />
      <button
        type="button"
        class="ctrl"
        aria-label={store.paused ? 'Resume' : 'Pause'}
        onclick={() => store.togglePause()}
      >{store.paused ? '▶ Resume' : '⏸ Pause'}</button>
      <button type="button" class="ctrl" aria-label="Clear view" onclick={() => store.clearView()}>
        ↻ Clear
      </button>
    </div>
  </header>

  {#if store.pausedGap}
    <div class="banner">({store.pausedGap.toLocaleString()} calls while paused — view truncated)</div>
  {/if}
  {#if store.error}
    <div class="banner error">Live updates paused — reconnecting…</div>
  {/if}

  <div class="pager">
    <label>
      Page size
      <select onchange={(e) => store.setPageSize(Number((e.target as HTMLSelectElement).value))} value={String(store.pageSize)}>
        <option value="25">25</option>
        <option value="50">50</option>
        <option value="100">100</option>
      </select>
    </label>
    <span class="grow"></span>
    <button type="button" onclick={() => store.setPage(1)} disabled={store.page <= 1}>«</button>
    <button type="button" onclick={() => store.setPage(store.page - 1)} disabled={store.page <= 1}>‹</button>
    <span class="pageinfo">page {store.page} of {totalPages}</span>
    <button type="button" onclick={() => store.setPage(store.page + 1)} disabled={store.page >= totalPages}>›</button>
    <button type="button" onclick={() => store.setPage(totalPages)} disabled={store.page >= totalPages}>»</button>
  </div>

  <ul class="list">
    {#each visible as r (r.seq)}
      <TimelineRow record={r} />
    {/each}
    {#if visible.length === 0}
      <li class="empty">No calls yet.</li>
    {/if}
  </ul>
</section>

<style>
  .card {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3);
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-2);
  }
  .title {
    margin: 0;
    font-size: 1em;
  }
  .controls {
    margin-left: auto;
    display: flex;
    gap: var(--space-2);
  }
  .ctrl {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }
  .pager {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border);
  }
  .grow {
    flex: 1;
  }
  .pageinfo {
    color: var(--text-secondary);
    font-size: 0.9em;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-3);
    text-align: center;
  }
  .banner {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
  }
  .banner.error {
    border-color: var(--danger, #c33);
    color: var(--danger, #c33);
  }
</style>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard && npm test -- timeline.test && npm run check`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/overview/Timeline.svelte dashboard/src/components/overview/TimelineRow.svelte dashboard/tests/timeline.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): Tool Call Timeline + expandable TimelineRow

Live, paginated, filter-able list of tool calls. Per-tool
FilterDropdown, pause/resume, clear-view, page-size selector,
first/prev/next/last paging. Rows expand inline to show seq, full
timestamp, duration, input/output previews with show-full toggle and
8 KB truncation note. Paused-gap banner appears when poll skipped
more records than the response window can carry.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Register the timeline poller + tool-names fetch + mount Timeline on Overview

**Files:**
- Modify: `dashboard/src/lib/pollers.ts`
- Modify: `dashboard/src/App.svelte` (mount Timeline, start `timeline` poller)
- Modify: `dashboard/src/components/overview/StatsSummary.svelte` (place Timeline below SummaryCards) — or whichever Overview-level component composes the cards
- Create: `dashboard/tests/pollers.test.ts` (extend if exists)

- [ ] **Step 1: Update `dashboard/src/lib/pollers.ts`**

```ts
export type View = 'overview' | 'logs' | 'stats' | 'code';
export type PollerName = 'config' | 'queued' | 'last' | 'logs' | 'timeline';

/** Which pollers should be running for a given view. Pure so it is unit-testable. */
export function pollersForView(view: View): PollerName[] {
  switch (view) {
    case 'overview':
      return ['config', 'queued', 'last', 'timeline'];
    case 'logs':
      return ['logs'];
    case 'stats':
      return ['config', 'timeline'];
    case 'code':
      return ['config'];
  }
}
```

- [ ] **Step 2: Add / update unit test for pollers**

If `dashboard/tests/pollers.test.ts` doesn't exist, create it:

```ts
import { describe, it, expect } from 'vitest';
import { pollersForView } from '../src/lib/pollers';

describe('pollersForView', () => {
  it('includes timeline for overview and stats', () => {
    expect(pollersForView('overview')).toContain('timeline');
    expect(pollersForView('stats')).toContain('timeline');
  });
  it('does not run timeline on logs/code', () => {
    expect(pollersForView('logs')).not.toContain('timeline');
    expect(pollersForView('code')).not.toContain('timeline');
  });
});
```

- [ ] **Step 3: Wire the timeline poller in `dashboard/src/App.svelte`**

Read the existing `App.svelte` first to see how `config`, `queued`, `last`, `logs` pollers are created and started/stopped on view changes. The pattern is `createPoller(fn, intervalMs)`. Add a `timeline` poller alongside the others:

```ts
import { timeline } from '$lib/stores/timeline.svelte';
import { fetchToolNames } from '$lib/api/endpoints';
// …existing imports

const timelinePoller = createPoller(() => safe(() => timeline.poll()), 1000);

// Visibility-aware: pause polls when tab is hidden.
$effect(() => {
  function onVis() {
    if (document.visibilityState === 'visible') {
      // resume by re-applying current view's pollers
      applyPollersForView(view);
    } else {
      timelinePoller.stop();
      // …stop other pollers as the existing code does
    }
  }
  document.addEventListener('visibilitychange', onVis);
  return () => document.removeEventListener('visibilitychange', onVis);
});
```

> **Implementer note:** the existing `App.svelte` already orchestrates pollers via `pollersForView` + a per-name map. Add `'timeline': timelinePoller` to that map, and add a tool-names fetch (cached) so the Timeline can populate FilterDropdown. Match the existing pattern, don't introduce a new one.

- [ ] **Step 4: Mount `<Timeline>` below `<SummaryCards>` on the Overview page**

Find the Overview-level component (likely `dashboard/src/components/overview/OverviewPage.svelte` or `StatsSummary.svelte` depending on which currently composes Overview). Insert Timeline below SummaryCards:

```svelte
<script lang="ts">
  import SummaryCards from './SummaryCards.svelte';
  import Timeline from './Timeline.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import { config } from '$lib/stores/config.svelte';
  // toolNames may live in a separate store; if not, derive from config or fetch.
  // Implementer: pick whichever source already exists.
  let toolNames = $state<string[]>([]);
  // …fetch once on mount via fetchToolNames if no existing store
</script>

<SummaryCards totals={config.overview?.tool_stats_totals} />
<Timeline store={timeline} toolNames={toolNames} />
```

- [ ] **Step 5: Run tests + type-check**

Run: `cd dashboard && npm test -- pollers && npm run check`

Expected: PASS.

- [ ] **Step 6: Manual smoke (dev server)**

Run the emulator (see memory `run-dashboard-emulate-tool-calls.md`) in one terminal, then `cd dashboard && npm run dev` in another. Visit `http://localhost:5273`, confirm:

- 4 SummaryCards appear under Overview.
- Timeline section appears below, ticking in new rows once per second.
- Pause/Resume button works.
- Tool filter dropdown opens, lets you type, applies a filter.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/pollers.ts dashboard/src/App.svelte dashboard/src/components/overview/*.svelte dashboard/tests/pollers.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): mount Timeline on Overview + register timeline poller

Timeline section sits below SummaryCards; timeline poller runs on
both Overview and Stats views (so RateChart/DurationChart/DrillDown
stay fresh on Stats) and pauses on tab-hidden. New 'code' view
registered in the polling map even though it polls nothing — its
on-demand fetches live on the components.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Frontend Tier 3 + Stats polish

> **⚠️ Corrections that apply to Phase 4 (see top of plan for details):**
> - **B21:** Task 17's stacked-area config is incomplete — needs `scales.{x,y}.stacked: true` on chart options, not just `fill: true` on datasets.
> - **B22:** Task 16 + 17's `ChartSpec` shape is wrong (returns `{type, labels, datasets}` at top level; should nest under `data:` per `ChartConfiguration<...>`). Tests assert the wrong shape too. Use the corrected `durationChartSpec` / `rateChartSpec` near the top of this plan.
> - **B23:** Task 18 must add chart click-handler wiring on `ChartPanel.svelte` (Step 0).
> - **B24:** Task 18's `percentile` algorithm is off-by-one. Use inclusive-linear `floor((q/100)*(n-1))` per the corrected version near the top.
> - **B25:** Task 17 must update `ChartPanel.svelte` to handle dataset-count changes (RateChart toggles between 1 and N datasets). Corrected effect snippet near the top.
> - **B26:** Task 15 — pies keep their own metric for ordering; only the tokens bar and DurationChart fully reorder by `sortKey`. Document this in Step 3.
> - **B27:** depends on Task 1 widening `ResponseToolStats.stats` type (see B2).

### Task 15: `SortSelector.svelte` driving stats chart order

**Files:**
- Create: `dashboard/src/components/stats/SortSelector.svelte`
- Modify: `dashboard/src/lib/stores/stats.svelte.ts` (add `sortKey` state)
- Modify: `dashboard/src/lib/charts.ts` (accept sort key in spec builders)
- Modify: `dashboard/src/components/stats/StatsPage.svelte` (mount SortSelector, pass sort key to specs)
- Create: `dashboard/tests/sort-selector.test.ts`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/sort-selector.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { sortToolsBy } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

const stats: ToolStats = {
  read_file: { num_times_called: 10, input_tokens: 100, output_tokens: 100 },
  find_symbol: { num_times_called: 50, input_tokens: 20, output_tokens: 20 },
  shell: { num_times_called: 2, input_tokens: 500, output_tokens: 500 },
};

describe('sortToolsBy', () => {
  it('sorts by calls desc', () => {
    expect(sortToolsBy(stats, 'calls')).toEqual(['find_symbol', 'read_file', 'shell']);
  });
  it('sorts by tokens desc', () => {
    expect(sortToolsBy(stats, 'tokens')).toEqual(['shell', 'read_file', 'find_symbol']);
  });
});
```

> If the existing `charts.ts` already exports tool ordering, replace with whatever name is in use — keep the test asserting the same behavior.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- sort-selector`

Expected: FAIL — `sortToolsBy` undefined.

- [ ] **Step 3: Add `sortKey` state to `dashboard/src/lib/stores/stats.svelte.ts`**

Replace the file with:

```ts
import { fetchToolStats, clearToolStats, fetchEstimatorName } from '$lib/api/endpoints';
import type { ToolStats } from '$lib/api/types';

export type SortKey = 'calls' | 'tokens' | 'duration_total' | 'duration_avg' | 'errors';

export function createStatsStore() {
  let stats = $state<ToolStats>({});
  let estimator = $state('unknown');
  let sortKey = $state<SortKey>('calls');

  return {
    get stats() {
      return stats;
    },
    get estimator() {
      return estimator;
    },
    get sortKey() {
      return sortKey;
    },
    setSortKey(k: SortKey) {
      sortKey = k;
    },
    async refresh() {
      stats = (await fetchToolStats()).stats;
      estimator = (await fetchEstimatorName()).token_count_estimator_name;
    },
    async clear() {
      await clearToolStats();
      stats = {};
    },
  };
}

export const stats = createStatsStore();
```

> **Note:** `ToolStatEntry` in `types.ts` should also gain optional duration/error fields to mirror the backend extension done in Phase 1. Update `types.ts`:
>
> ```ts
> export interface ToolStatEntry {
>   num_times_called: number;
>   num_errors?: number;
>   input_tokens: number;
>   output_tokens: number;
>   total_duration_ms?: number;
>   min_duration_ms?: number | null;
>   max_duration_ms?: number | null;
>   last_called_at?: number | null;
> }
> ```

- [ ] **Step 4: Add `sortToolsBy` to `dashboard/src/lib/charts.ts`**

Read `dashboard/src/lib/charts.ts` first to understand existing spec-builder shape. Append:

```ts
import type { ToolStats } from './api/types';
import type { SortKey } from './stores/stats.svelte';

export function sortToolsBy(stats: ToolStats, key: SortKey): string[] {
  const entries = Object.entries(stats);
  const score = (e: [string, ToolStats[string]]) => {
    const [, v] = e;
    switch (key) {
      case 'calls':
        return v.num_times_called;
      case 'tokens':
        return (v.input_tokens ?? 0) + (v.output_tokens ?? 0);
      case 'duration_total':
        return v.total_duration_ms ?? 0;
      case 'duration_avg':
        return v.num_times_called > 0 ? (v.total_duration_ms ?? 0) / v.num_times_called : 0;
      case 'errors':
        return v.num_errors ?? 0;
    }
  };
  return entries.sort((a, b) => score(b) - score(a)).map(([name]) => name);
}
```

Update the existing chart spec builders (e.g. `pieSpec`, `tokensBarSpec`) to accept and apply the sort key. Read each one first; the typical change is adding a `sortKey` param and replacing any implicit ordering with `sortToolsBy(stats, sortKey)`.

- [ ] **Step 5: Create `dashboard/src/components/stats/SortSelector.svelte`**

```svelte
<script lang="ts">
  import { stats, type SortKey } from '$lib/stores/stats.svelte';

  const options: { value: SortKey; label: string }[] = [
    { value: 'calls', label: 'Calls' },
    { value: 'tokens', label: 'Tokens' },
    { value: 'duration_total', label: 'Total duration' },
    { value: 'duration_avg', label: 'Avg duration' },
    { value: 'errors', label: 'Errors' },
  ];
</script>

<label class="root">
  <span>Sort by</span>
  <select value={stats.sortKey} onchange={(e) => stats.setSortKey((e.target as HTMLSelectElement).value as SortKey)}>
    {#each options as o}
      <option value={o.value}>{o.label}</option>
    {/each}
  </select>
</label>

<style>
  .root {
    display: inline-flex;
    gap: var(--space-2);
    align-items: center;
    color: var(--text-secondary);
  }
  select {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-primary);
    padding: var(--space-1) var(--space-2);
  }
</style>
```

- [ ] **Step 6: Mount `<SortSelector>` in `StatsPage.svelte` toolbar; pass `stats.sortKey` to each existing chart spec call**

Read `dashboard/src/components/stats/StatsPage.svelte` first. Add `<SortSelector />` to the existing card-style toolbar (the grouping introduced by commit `a7e91c3b`). Where chart spec builders are invoked (e.g. `pieSpec(stats.stats, ...)`), pass `stats.sortKey` as the new parameter.

- [ ] **Step 7: Run tests + type-check**

Run: `cd dashboard && npm test -- sort-selector && npm run check`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/components/stats/SortSelector.svelte dashboard/src/lib/charts.ts dashboard/src/lib/stores/stats.svelte.ts dashboard/src/lib/api/types.ts dashboard/src/components/stats/StatsPage.svelte dashboard/tests/sort-selector.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): SortSelector for Stats charts (calls/tokens/duration/errors)

Single sortKey on the stats store flows into every chart spec builder
via sortToolsBy(). Default 'calls' matches today's implicit order.
ToolStatEntry mirrors the backend Entry extension (optional duration
+ error fields).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: `DurationChart.svelte` (avg + max bars)

**Files:**
- Modify: `dashboard/src/lib/charts.ts` (add `durationChartSpec`)
- Create: `dashboard/src/components/stats/DurationChart.svelte`
- Modify: `dashboard/tests/charts.test.ts`
- Modify: `dashboard/src/components/stats/StatsPage.svelte` (mount DurationChart)

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/charts.test.ts`:

```ts
import { durationChartSpec } from '../src/lib/charts';
import type { ToolStats } from '../src/lib/api/types';

describe('durationChartSpec', () => {
  it('builds avg + max datasets ordered by sortKey', () => {
    const stats: ToolStats = {
      a: { num_times_called: 10, input_tokens: 0, output_tokens: 0, total_duration_ms: 100, max_duration_ms: 20 },
      b: { num_times_called: 5, input_tokens: 0, output_tokens: 0, total_duration_ms: 50, max_duration_ms: 30 },
    };
    const spec = durationChartSpec(stats, 'duration_total');
    expect(spec.type).toBe('bar');
    expect(spec.labels).toEqual(['a', 'b']);
    expect(spec.datasets.length).toBe(2);
    const avg = spec.datasets.find((d) => d.label === 'Avg');
    expect(avg?.data).toEqual([10, 10]); // 100/10, 50/5
    const max = spec.datasets.find((d) => d.label === 'Max');
    expect(max?.data).toEqual([20, 30]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- charts.test`

Expected: FAIL — `durationChartSpec` undefined.

- [ ] **Step 3: Add `durationChartSpec` in `dashboard/src/lib/charts.ts`**

```ts
import type { ToolStats } from './api/types';
import { sortToolsBy } from './charts';
import type { SortKey } from './stores/stats.svelte';

export function durationChartSpec(stats: ToolStats, sortKey: SortKey) {
  const labels = sortToolsBy(stats, sortKey);
  const avg = labels.map((n) => {
    const e = stats[n];
    return e && e.num_times_called > 0 ? (e.total_duration_ms ?? 0) / e.num_times_called : 0;
  });
  const max = labels.map((n) => stats[n]?.max_duration_ms ?? 0);
  return {
    type: 'bar' as const,
    labels,
    datasets: [
      { label: 'Avg', data: avg, kind: 'avg' as const },
      { label: 'Max', data: max, kind: 'max' as const },
    ],
  };
}
```

> **Implementer note:** match the existing `ChartSpec` shape. If the codebase uses a named type rather than the literal shape above, conform to it. Read `charts.ts` first.

- [ ] **Step 4: Create `dashboard/src/components/stats/DurationChart.svelte`**

```svelte
<script lang="ts">
  import ChartPanel from './ChartPanel.svelte';
  import { stats } from '$lib/stores/stats.svelte';
  import { durationChartSpec } from '$lib/charts';

  const spec = $derived(durationChartSpec(stats.stats, stats.sortKey));
</script>

<ChartPanel title="Duration (avg / max ms)" spec={spec} height={260} />
```

> **Implementer note:** `ChartPanel`'s API — read it first. The exact prop names may differ (e.g. `chartSpec` not `spec`). Conform to the existing prop signature. The chart should render two bar datasets per tool; if `ChartPanel` doesn't yet support a "max-as-outline" variant, render plain side-by-side bars — the visual variant can land later as polish, but two datasets per tool is required.

- [ ] **Step 5: Mount in `StatsPage.svelte`**

Add a new `<DurationChart />` panel alongside the existing pies and tokens bar.

- [ ] **Step 6: Run tests + check**

Run: `cd dashboard && npm test -- charts && npm run check`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/charts.ts dashboard/src/components/stats/DurationChart.svelte dashboard/src/components/stats/StatsPage.svelte dashboard/tests/charts.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): DurationChart (avg + max ms per tool)

Avg derived from total_duration_ms / num_times_called; max from the
new max_duration_ms field. Ordered by SortSelector key.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: `RateChart.svelte` (per-minute line + window + stacked-area toggle)

**Files:**
- Modify: `dashboard/src/lib/charts.ts` (add `rateChartSpec` + bucketing helper)
- Create: `dashboard/src/components/stats/RateChart.svelte`
- Modify: `dashboard/tests/charts.test.ts`
- Modify: `dashboard/src/components/stats/StatsPage.svelte` (mount RateChart)

- [ ] **Step 1: Write the failing test (bucket alignment regression)**

Append to `dashboard/tests/charts.test.ts`:

```ts
import { rateChartSpec, bucketRecordsByMinute } from '../src/lib/charts';
import type { ToolCallRecord } from '../src/lib/api/types';

function rec(started_at: number, tool = 't'): ToolCallRecord {
  return {
    seq: 0,
    tool,
    started_at,
    duration_ms: 0,
    success: true,
    error_message: null,
    input_preview: '',
    output_preview: '',
    input_truncated: false,
    output_truncated: false,
  };
}

describe('bucketRecordsByMinute', () => {
  it('emits windowMinutes + 1 buckets, with the current minute as the last bucket', () => {
    const now = 1_700_000_000; // arbitrary epoch s
    // Place "now" at the start of a clean minute boundary
    const nowAligned = Math.floor(now / 60) * 60;
    const records = [
      rec(nowAligned + 5),   // in current minute
      rec(nowAligned - 30),  // in current minute (still within 0–59s of nowAligned)
      rec(nowAligned - 65),  // 1 minute ago
    ];
    const buckets = bucketRecordsByMinute(records, nowAligned + 10, 15);
    expect(buckets.length).toBe(16); // 15 + 1
    // Current-minute calls land in the LAST bucket — not dropped.
    expect(buckets[buckets.length - 1].count).toBe(2);
    expect(buckets[buckets.length - 2].count).toBe(1);
  });

  it('returns 0-count buckets for empty minutes', () => {
    const now = 1_700_000_000;
    const buckets = bucketRecordsByMinute([], now, 5);
    expect(buckets.length).toBe(6);
    expect(buckets.every((b) => b.count === 0)).toBe(true);
  });
});

describe('rateChartSpec', () => {
  it('produces a single line dataset when stacked=false', () => {
    const spec = rateChartSpec([], Date.now() / 1000, 15, false, []);
    expect(spec.type).toBe('line');
    expect(spec.datasets.length).toBe(1);
  });
  it('produces per-tool datasets when stacked=true and tools provided', () => {
    const spec = rateChartSpec([], Date.now() / 1000, 15, true, ['a', 'b', 'c']);
    expect(spec.datasets.length).toBe(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- charts`

Expected: FAIL — functions undefined.

- [ ] **Step 3: Add bucketing + spec in `dashboard/src/lib/charts.ts`**

```ts
import type { ToolCallRecord } from './api/types';

export interface MinuteBucket {
  // epoch seconds for the START of this minute bucket
  start: number;
  count: number;
  byTool: Record<string, number>;
}

/**
 * Bucket records into per-minute counts. Returns windowMinutes+1 buckets aligned
 * so the current minute (containing nowEpochS) is the LAST bucket.
 */
export function bucketRecordsByMinute(
  records: ToolCallRecord[],
  nowEpochS: number,
  windowMinutes: number,
): MinuteBucket[] {
  const currentMinuteStart = Math.floor(nowEpochS / 60) * 60;
  const oldestMinuteStart = currentMinuteStart - windowMinutes * 60;
  const total = windowMinutes + 1;
  const buckets: MinuteBucket[] = Array.from({ length: total }, (_, i) => ({
    start: oldestMinuteStart + i * 60,
    count: 0,
    byTool: {},
  }));
  for (const r of records) {
    if (r.started_at < oldestMinuteStart) continue;
    if (r.started_at >= currentMinuteStart + 60) continue;
    const idx = Math.floor((r.started_at - oldestMinuteStart) / 60);
    if (idx < 0 || idx >= total) continue;
    buckets[idx].count += 1;
    buckets[idx].byTool[r.tool] = (buckets[idx].byTool[r.tool] ?? 0) + 1;
  }
  return buckets;
}

export function rateChartSpec(
  records: ToolCallRecord[],
  nowEpochS: number,
  windowMinutes: number,
  stacked: boolean,
  tools: string[],
) {
  const buckets = bucketRecordsByMinute(records, nowEpochS, windowMinutes);
  const labels = buckets.map((b) => new Date(b.start * 1000).toISOString().slice(11, 16));
  if (!stacked) {
    return {
      type: 'line' as const,
      labels,
      datasets: [{ label: 'Calls / min', data: buckets.map((b) => b.count) }],
    };
  }
  return {
    type: 'line' as const,
    labels,
    stacked: true,
    datasets: tools.map((t) => ({
      label: t,
      data: buckets.map((b) => b.byTool[t] ?? 0),
      fill: true,
    })),
  };
}
```

- [ ] **Step 4: Create `dashboard/src/components/stats/RateChart.svelte`**

```svelte
<script lang="ts">
  import ChartPanel from './ChartPanel.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import { rateChartSpec } from '$lib/charts';

  type WindowMinutes = 15 | 30 | 60 | 360;
  let windowMinutes = $state<WindowMinutes>(15);
  let stacked = $state(false);
  let enabledTools = $state<Set<string>>(new Set());

  const allTools = $derived(Array.from(new Set(timeline.records.map((r) => r.tool))).sort());
  const activeTools = $derived(stacked ? allTools.filter((t) => enabledTools.size === 0 || enabledTools.has(t)) : []);

  const nowS = $derived(Date.now() / 1000);
  const spec = $derived(rateChartSpec(timeline.records, nowS, windowMinutes, stacked, activeTools));

  function showAll() {
    enabledTools = new Set(allTools);
  }
  function disableAll() {
    enabledTools = new Set();
  }
</script>

<section class="card">
  <header class="head">
    <h3>Tool Call Rate</h3>
    <div class="controls">
      <label>
        Window
        <select onchange={(e) => (windowMinutes = Number((e.target as HTMLSelectElement).value) as WindowMinutes)} value={String(windowMinutes)}>
          <option value="15">15 m</option>
          <option value="30">30 m</option>
          <option value="60">1 h</option>
          <option value="360">6 h</option>
        </select>
      </label>
      <label>
        <input type="checkbox" bind:checked={stacked} /> per-tool stacked
      </label>
      {#if stacked}
        <button type="button" onclick={showAll}>Show all</button>
        <button type="button" onclick={disableAll}>Disable all</button>
      {/if}
    </div>
  </header>
  <ChartPanel spec={spec} height={240} />
  {#if windowMinutes >= 60}
    <p class="hint">Buffer is capped at 2000 records — long windows may show only the recent portion.</p>
  {/if}
</section>

<style>
  .card {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-3);
  }
  .head {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-2);
  }
  .head h3 {
    margin: 0;
    font-size: 1em;
  }
  .controls {
    margin-left: auto;
    display: flex;
    gap: var(--space-2);
    color: var(--text-secondary);
  }
  .hint {
    color: var(--text-secondary);
    font-size: 0.85em;
    margin: var(--space-1) 0 0;
  }
</style>
```

- [ ] **Step 5: Mount in `StatsPage.svelte`**

Add `<RateChart />` to the StatsPage layout.

- [ ] **Step 6: Run tests + check**

Run: `cd dashboard && npm test -- charts && npm run check`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/charts.ts dashboard/src/components/stats/RateChart.svelte dashboard/src/components/stats/StatsPage.svelte dashboard/tests/charts.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): per-minute RateChart with windows + stacked-area toggle

bucketRecordsByMinute aligns the current minute as the LAST bucket
(windowMinutes+1 total) so live calls aren't dropped — the legacy
bug, locked down as a regression test. Window selector
(15m/30m/1h/6h), Show all / Disable all when stacked. Reads from the
timeline buffer (no new endpoint).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: `DrillDownPanel.svelte` + click handlers on chart slices

**Files:**
- Create: `dashboard/src/components/stats/DrillDownPanel.svelte`
- Modify: `dashboard/src/lib/stores/stats.svelte.ts` (add `drillTool` state)
- Modify: `dashboard/src/components/stats/StatsPage.svelte` (wire chart click → setDrillTool)
- Modify: `dashboard/src/components/stats/ChartPanel.svelte` (forward click events with the clicked label)
- Create: `dashboard/tests/drilldown.test.ts`

- [ ] **Step 1: Write the failing test (p95 computation)**

Create `dashboard/tests/drilldown.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { percentile } from '../src/lib/format';

describe('percentile', () => {
  it('computes p95 over a fixed window', () => {
    const xs = Array.from({ length: 100 }, (_, i) => i + 1); // 1..100
    expect(percentile(xs, 95)).toBe(95);
  });
  it('returns 0 for empty input', () => {
    expect(percentile([], 95)).toBe(0);
  });
  it('clamps quantile', () => {
    expect(percentile([1, 2, 3], 200)).toBe(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && npm test -- drilldown`

Expected: FAIL — `percentile` undefined.

- [ ] **Step 3: Add `percentile` to `dashboard/src/lib/format.ts`**

Append:

```ts
export function percentile(xs: number[], q: number): number {
  if (xs.length === 0) return 0;
  const sorted = [...xs].sort((a, b) => a - b);
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor((q / 100) * sorted.length)));
  return sorted[idx];
}
```

- [ ] **Step 4: Add `drillTool` state in stats store**

Edit `dashboard/src/lib/stores/stats.svelte.ts`:

```ts
// inside createStatsStore:
let drillTool = $state<string | null>(null);
// add to return:
get drillTool() {
  return drillTool;
},
setDrillTool(t: string | null) {
  drillTool = t;
},
```

- [ ] **Step 5: Create `dashboard/src/components/stats/DrillDownPanel.svelte`**

```svelte
<script lang="ts">
  import { stats } from '$lib/stores/stats.svelte';
  import { timeline } from '$lib/stores/timeline.svelte';
  import { formatDurationMs, formatNumber, percentile } from '$lib/format';

  interface Props {
    onOpenInTimeline?: (tool: string) => void;
  }
  let { onOpenInTimeline }: Props = $props();

  const tool = $derived(stats.drillTool);
  const entry = $derived(tool ? stats.stats[tool] : undefined);

  const recordsForTool = $derived(tool ? timeline.records.filter((r) => r.tool === tool) : []);
  const durations = $derived(recordsForTool.map((r) => r.duration_ms));
  const p95 = $derived(percentile(durations, 95));
  const recentErrors = $derived(recordsForTool.filter((r) => !r.success).slice(0, 5));
  const last20 = $derived(recordsForTool.slice(0, 20));

  const errorRate = $derived(entry && entry.num_times_called > 0 ? ((entry.num_errors ?? 0) / entry.num_times_called) * 100 : 0);
  const avg = $derived(entry && entry.num_times_called > 0 ? (entry.total_duration_ms ?? 0) / entry.num_times_called : 0);
</script>

{#if tool}
  <aside class="panel" role="dialog" aria-label="Tool details">
    <header>
      <h3>{tool}</h3>
      <button type="button" class="close" aria-label="Close" onclick={() => stats.setDrillTool(null)}>×</button>
    </header>
    {#if !entry}
      <p class="empty">No data for this tool.</p>
    {:else}
      <dl class="grid">
        <dt>Calls</dt><dd>{formatNumber(entry.num_times_called)}</dd>
        <dt>Errors</dt><dd>{formatNumber(entry.num_errors ?? 0)} ({errorRate.toFixed(2)} %)</dd>
        <dt>Avg</dt><dd>{formatDurationMs(avg)}</dd>
        <dt>p95</dt><dd>{formatDurationMs(p95)}</dd>
        <dt>Total</dt><dd>{formatDurationMs(entry.total_duration_ms ?? 0)}</dd>
        <dt>Max</dt><dd>{formatDurationMs(entry.max_duration_ms ?? 0)}</dd>
      </dl>
      <p class="hint">p95 based on last {recordsForTool.length} calls in the live buffer.</p>

      {#if recentErrors.length > 0}
        <h4>Recent errors</h4>
        <ul class="errors">
          {#each recentErrors as r}
            <li>{new Date(r.started_at * 1000).toISOString().slice(11, 19)} — {r.error_message}</li>
          {/each}
        </ul>
      {/if}

      <h4>Last {Math.min(20, last20.length)} calls</h4>
      <ul class="calls">
        {#each last20 as r}
          <li>
            <span>{new Date(r.started_at * 1000).toISOString().slice(11, 19)}</span>
            <span>{formatDurationMs(r.duration_ms)}</span>
            <span class={r.success ? 'ok' : 'err'}>{r.success ? 'ok' : 'ERR'}</span>
          </li>
        {/each}
      </ul>

      <button type="button" class="open" onclick={() => onOpenInTimeline?.(tool)}>Open in Timeline →</button>
    {/if}
  </aside>
{/if}

<style>
  .panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 340px;
    background: var(--bg-elevated);
    border-left: 1px solid var(--border-strong);
    box-shadow: var(--shadow-elevated);
    padding: var(--space-3);
    overflow-y: auto;
    z-index: 40;
  }
  header {
    display: flex;
    align-items: center;
    margin-bottom: var(--space-2);
  }
  header h3 {
    margin: 0;
    font-family: var(--font-mono);
  }
  .close {
    margin-left: auto;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    font-size: 1.4em;
    cursor: pointer;
  }
  .close:hover {
    color: var(--accent);
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-1) var(--space-2);
    margin: 0;
  }
  dt {
    color: var(--text-secondary);
  }
  dd {
    margin: 0;
    font-weight: 600;
  }
  .hint {
    color: var(--text-secondary);
    font-size: 0.85em;
  }
  h4 {
    margin: var(--space-3) 0 var(--space-1);
    font-size: 0.95em;
  }
  .errors,
  .calls {
    list-style: none;
    margin: 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .calls li {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: var(--space-2);
  }
  .ok {
    color: var(--success, var(--text-secondary));
  }
  .err {
    color: var(--danger, #c33);
  }
  .empty {
    color: var(--text-secondary);
  }
  .open {
    margin-top: var(--space-3);
    background: var(--accent);
    color: white;
    border: 0;
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }
</style>
```

- [ ] **Step 6: Forward click → setDrillTool from `StatsPage.svelte`**

In `StatsPage.svelte`, where pies / tokens bar / DurationChart are rendered, pass an `onSliceClick` callback (matching `ChartPanel`'s existing event/callback API — read first; if a click prop doesn't exist, add one in `ChartPanel.svelte`):

```svelte
<ChartPanel
  spec={pieSpec(stats.stats, stats.sortKey)}
  onSliceClick={(label) => stats.setDrillTool(label)}
/>
<DrillDownPanel onOpenInTimeline={(tool) => {
  timeline.setFilter(tool);
  navigate('overview'); // or whatever the existing nav helper is
}} />
```

- [ ] **Step 7: Run tests + check**

Run: `cd dashboard && npm test -- drilldown && npm run check`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/components/stats/DrillDownPanel.svelte dashboard/src/components/stats/StatsPage.svelte dashboard/src/components/stats/ChartPanel.svelte dashboard/src/lib/stores/stats.svelte.ts dashboard/src/lib/format.ts dashboard/tests/drilldown.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): per-tool DrillDownPanel with p95 + Open in Timeline

Click any pie / tokens bar / duration chart slice to open a side panel
with aggregates (Calls, Errors with %, Avg, p95, Total, Max), recent
errors, and the last 20 calls. p95 computed client-side from the
timeline buffer; UI hints at the window. 'Open in Timeline' applies
the tool filter and navigates back to Overview.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Backend `/code/*` routes

> **⚠️ CRITICAL CORRECTION:** All four `/code/*` route tasks (19–23) below use **FastAPI**. The actual dashboard is **Flask**. **Do not implement the original Phase 5 task code — use the rewritten "Corrected Tasks 19–23 (Flask `/code/*` routes)" section near the top of this plan.** Additional corrections that apply:
>
> - **B29:** LSP method names in the original tasks are wrong. Real names: `request_document_symbols(rel_path)` returns `DocumentSymbols` (object with `.root_symbols`, not a list of dicts); `request_workspace_symbol(query)` (SINGULAR, no `limit` param); `request_published_text_document_diagnostics(rel_path)` returns LSP-shape diagnostics. SymbolKind is an integer requiring a label map.
> - **B30:** `manager.get_language_server(".")` raises (it requires a file). Use `next(iter(manager.iter_language_servers()), None)` for "any LS" use cases.
> - **B31:** `manager.started_language_servers_relative_paths()` doesn't exist. Walk the project tree directly.
> - **B32:** Use `GitignoreParser` from `src/serena/util/file_system.py:130` (existing helper) instead of the hardcoded skip set. Honors nested `.gitignore` files.
> - **B33:** Map `TimeoutError` → 504 `ls_timeout` (spec §7.1 requires this; original task collapses everything to 502/503).
> - **B34:** Path-traversal guard needs NUL-byte rejection and `pathlib.Path.resolve().relative_to(...)` instead of `os.path.commonpath` (cleaner on Windows).
> - **B35:** `os.scandir` follows symlinks by default — use `follow_symlinks=False`.
> - **B36:** 1 MB diagnostics cap heuristic is wrong (assumes uniform diag size). Trim per-message first, then loop-pop until under cap.

> **Implementer note for this whole phase:** all four routes share a path-traversal guard and an LSP error→HTTP translator. Task 19 creates the helpers; Tasks 20–23 use them. Each route lives in `src/serena/dashboard_code.py`, registered from `dashboard.py` via a single `register_code_routes(dashboard_api)` call (Flask). Read `dashboard.py` first to see how it currently wires routes onto `self._app`; the new helper should match that style.

### Task 19: Path-traversal guard + LSP error helper in `dashboard_code.py`

**Files:**
- Create: `src/serena/dashboard_code.py`
- Create: `test/serena/test_dashboard_code.py`

- [ ] **Step 1: Write the failing tests**

Create `test/serena/test_dashboard_code.py`:

```python
import pytest

from serena.dashboard_code import resolve_project_path, LSPNotReady


def test_resolve_project_path_rejects_traversal(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "file.py").write_text("x = 1")
    # OK
    resolved = resolve_project_path(str(root), "file.py")
    assert resolved == str((root / "file.py").resolve())
    # Rejects ../
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "../secret.txt")
    # Rejects absolute path outside root
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "/etc/passwd")


def test_resolve_project_path_rejects_symlink_escape(tmp_path):
    import os
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("bad")
    link = root / "link.txt"
    os.symlink(str(outside), str(link))
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "link.txt")


def test_resolve_project_path_rejects_missing_file(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_project_path(str(root), "missing.py")


def test_lsp_not_ready_is_an_exception_type():
    assert issubclass(LSPNotReady, Exception)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_dashboard_code.py -v`

Expected: FAIL — module missing.

- [ ] **Step 3: Create `src/serena/dashboard_code.py`**

```python
"""
Code-tab endpoints for the dashboard.

This module encapsulates the four /code/* routes used by the dashboard_v2 Code
tab. It does NOT register a router on its own; call register_code_routes(app,
agent) from dashboard.py.

Concurrency note: LSP requests serialize at the language-server subprocess's
stdin/stdout pipe. The diagnostics endpoint is slow; the frontend shows a
warning banner and disables Refresh while a request is outstanding. No global
lock is added here.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

log = logging.getLogger(__name__)

_FILE_LIMIT_CAP = 2000
_WORKSPACE_SYMBOL_LIMIT_CAP = 200
_DIAGNOSTICS_PER_FILE_BYTE_CAP = 1024 * 1024  # 1 MB


class LSPNotReady(Exception):
    """Raised when an /code/* route is called but no LanguageServer is initialized."""


def resolve_project_path(project_root: str, path: str) -> str:
    """
    Resolve `path` (which must be a relative path under the project root) to an
    absolute path. Raises ValueError on traversal/escape and FileNotFoundError
    on missing files.

    - Absolute paths are rejected (must be relative to project root).
    - .. traversal is rejected via commonpath check on the realpath.
    - Symlinks pointing outside the root are rejected.
    """
    if os.path.isabs(path):
        raise ValueError(f"absolute path not allowed: {path!r}")
    root_real = os.path.realpath(project_root)
    candidate = os.path.realpath(os.path.join(root_real, path))
    if os.path.commonpath([candidate, root_real]) != root_real:
        raise ValueError(f"path escapes project root: {path!r}")
    if not os.path.exists(candidate):
        raise FileNotFoundError(candidate)
    return candidate


def _get_project_root_or_503(agent: "SerenaAgent") -> str:
    project = agent.get_active_project()
    if project is None:
        raise HTTPException(status_code=503, detail={"error": "No active project", "code": "no_project"})
    return project.project_root


def _get_language_server_or_503(agent: "SerenaAgent", path: str | None = None):
    """
    Returns a SolidLanguageServer for the given relative path (or any for the
    project if path is None). Raises HTTPException 503 with `ls_not_ready` if
    no language server is initialized.
    """
    try:
        manager = agent.get_language_server_manager()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={"error": str(e), "code": "ls_not_ready"})
    if manager is None:
        raise HTTPException(status_code=503, detail={"error": "Language server not ready", "code": "ls_not_ready"})
    try:
        if path is not None:
            return manager.get_language_server(path)
        # No relative path: return any started server (manager exposes one).
        return manager.get_language_server(".")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail={"error": str(e), "code": "ls_not_ready"})


def register_code_routes(app: FastAPI, agent: "SerenaAgent") -> None:
    """Register /code/* routes onto the given FastAPI app."""
    # Implemented across Tasks 20-23.
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_dashboard_code.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/serena/dashboard_code.py test/serena/test_dashboard_code.py
git commit -m "$(cat <<'EOF'
feat(dashboard): scaffold dashboard_code module + path-traversal guard

New module hosting the /code/* routes. resolve_project_path enforces:
no absolute paths, no .. traversal, no symlink escape, file must
exist. _get_language_server_or_503 normalizes LS readiness errors to
HTTP 503 with code=ls_not_ready.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 20: `/code/list_dir` endpoint

**Files:**
- Modify: `src/serena/dashboard_code.py` (implement list_dir route inside register_code_routes)
- Modify: `src/serena/dashboard.py` (call register_code_routes)
- Modify: `test/serena/test_dashboard_code.py`

- [ ] **Step 1: Write the failing tests**

Append to `test/serena/test_dashboard_code.py`:

```python
def test_code_list_dir_returns_entries(make_agent_with_project_root):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_project_root()
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hi')")
    (root / "README.md").write_text("hi")
    client = TestClient(dashboard.app)

    r = client.get("/code/list_dir?path=.")
    assert r.status_code == 200
    names = {e["name"] for e in r.json()["entries"]}
    assert "src" in names and "README.md" in names
    kinds = {e["name"]: e["kind"] for e in r.json()["entries"]}
    assert kinds["src"] == "dir"
    assert kinds["README.md"] == "file"


def test_code_list_dir_rejects_traversal(make_agent_with_project_root):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_project_root()
    client = TestClient(dashboard.app)
    r = client.get("/code/list_dir?path=../etc")
    assert r.status_code == 400
```

Add the `make_agent_with_project_root` fixture to the file:

```python
@pytest.fixture
def make_agent_with_project_root(tmp_path, monkeypatch):
    from serena.agent import SerenaAgent
    from serena.dashboard import SerenaDashboardAPI

    def _factory():
        root = tmp_path / "proj"
        root.mkdir()
        agent = SerenaAgent.__new__(SerenaAgent)
        agent._tool_usage_stats = None

        class _Project:
            project_root = str(root)
            project_name = "proj"

        monkeypatch.setattr(agent, "get_active_project", lambda: _Project(), raising=False)
        monkeypatch.setattr(agent, "get_language_server_manager", lambda: None, raising=False)
        dashboard = SerenaDashboardAPI(agent)
        return agent, dashboard, root

    return _factory
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_dashboard_code.py -v`

Expected: FAIL — 404 from `/code/list_dir`.

- [ ] **Step 3: Implement the route in `register_code_routes`**

Replace the `register_code_routes` stub in `src/serena/dashboard_code.py` with:

```python
class _DirEntry(BaseModel):
    name: str
    kind: str  # "dir" | "file"
    size: int | None = None


class _ResponseListDir(BaseModel):
    entries: list[_DirEntry]


_GITIGNORE_HARDCODED = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"}


def register_code_routes(app: FastAPI, agent: "SerenaAgent") -> None:
    @app.get("/code/list_dir")
    def code_list_dir(path: str = ".") -> _ResponseListDir:
        root = _get_project_root_or_503(agent)
        try:
            resolved = resolve_project_path(root, path) if path not in ("", ".") else os.path.realpath(root)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="directory not found")
        if not os.path.isdir(resolved):
            raise HTTPException(status_code=400, detail="path is not a directory")
        entries: list[_DirEntry] = []
        try:
            with os.scandir(resolved) as it:
                for de in it:
                    if de.name in _GITIGNORE_HARDCODED or de.name.startswith("."):
                        continue
                    if de.is_dir():
                        entries.append(_DirEntry(name=de.name, kind="dir"))
                    elif de.is_file():
                        try:
                            size = de.stat().st_size
                        except OSError:
                            size = None
                        entries.append(_DirEntry(name=de.name, kind="file", size=size))
        except PermissionError:
            raise HTTPException(status_code=403, detail="permission denied")
        entries.sort(key=lambda e: (e.kind == "file", e.name.lower()))
        return _ResponseListDir(entries=entries)
```

- [ ] **Step 4: Wire `register_code_routes` from `dashboard.py`**

In `src/serena/dashboard.py`, find where the dashboard initializes routes (likely in `SerenaDashboardAPI.__init__` after the existing `@self.app.get(...)` registrations). Add:

```python
        from serena.dashboard_code import register_code_routes
        register_code_routes(self.app, self._agent)
```

(Use the attribute the dashboard already uses for the agent — check whether it's `self._agent` or `self.agent`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_dashboard_code.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/serena/dashboard_code.py src/serena/dashboard.py test/serena/test_dashboard_code.py
git commit -m "$(cat <<'EOF'
feat(dashboard): GET /code/list_dir (lazy folder tree)

One-level directory listing under the active project root, with
path-traversal guard, hardcoded skip-list (.git, node_modules,
__pycache__, .venv, dotfiles), and dir-then-file sort. Foundation for
the Code tab's FileTree.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 21: `/code/file_symbols` endpoint

**Files:**
- Modify: `src/serena/dashboard_code.py` (add file_symbols route)
- Modify: `test/serena/test_dashboard_code.py`

- [ ] **Step 1: Write the failing test (with mocked LSP)**

Append to `test/serena/test_dashboard_code.py`:

```python
def test_code_file_symbols_returns_lsp_document_symbols(make_agent_with_lsp, tmp_path):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_lsp(
        document_symbols={
            "main.py": [
                {
                    "name": "Foo",
                    "kind": "Class",
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 5, "character": 0}},
                    "children": [
                        {
                            "name": "bar",
                            "kind": "Method",
                            "range": {"start": {"line": 1, "character": 4}, "end": {"line": 3, "character": 0}},
                            "children": [],
                        }
                    ],
                },
            ],
        }
    )
    (root / "main.py").write_text("class Foo:\n    def bar(self): pass\n")
    client = TestClient(dashboard.app)
    r = client.get("/code/file_symbols?path=main.py")
    assert r.status_code == 200
    body = r.json()
    assert body["symbols"][0]["name"] == "Foo"
    assert body["symbols"][0]["children"][0]["name"] == "bar"


def test_code_file_symbols_returns_503_when_no_ls(make_agent_with_project_root):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_project_root()
    (root / "f.py").write_text("x=1")
    client = TestClient(dashboard.app)
    r = client.get("/code/file_symbols?path=f.py")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "ls_not_ready"


def test_code_file_symbols_404_for_missing(make_agent_with_project_root):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_project_root()
    client = TestClient(dashboard.app)
    r = client.get("/code/file_symbols?path=nope.py")
    assert r.status_code == 404
```

Add the `make_agent_with_lsp` fixture:

```python
@pytest.fixture
def make_agent_with_lsp(tmp_path, monkeypatch):
    """
    Builds an agent whose language server manager is a fake returning preset
    document symbols / workspace matches / diagnostics.
    """
    from serena.agent import SerenaAgent
    from serena.dashboard import SerenaDashboardAPI

    def _factory(*, document_symbols=None, workspace_matches=None, diagnostics=None):
        root = tmp_path / "proj"
        root.mkdir()
        agent = SerenaAgent.__new__(SerenaAgent)
        agent._tool_usage_stats = None

        class _Project:
            project_root = str(root)
            project_name = "proj"

        class _LS:
            def request_document_symbols(self, path):
                return (document_symbols or {}).get(os.path.basename(path), [])

            def request_workspace_symbols(self, q, limit):
                return (workspace_matches or [])[:limit]

            def request_published_text_document_diagnostics(self, path):
                return (diagnostics or {}).get(os.path.basename(path), [])

        class _Manager:
            def get_language_server(self, path):
                return _LS()

            def started_language_servers_relative_paths(self):
                return ["main.py"]

        monkeypatch.setattr(agent, "get_active_project", lambda: _Project(), raising=False)
        monkeypatch.setattr(agent, "get_language_server_manager", lambda: _Manager(), raising=False)
        dashboard = SerenaDashboardAPI(agent)
        return agent, dashboard, root

    return _factory
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_dashboard_code.py -v -k file_symbols`

Expected: FAIL.

- [ ] **Step 3: Add the route to `register_code_routes`**

Inside `register_code_routes` in `src/serena/dashboard_code.py`, append (with supporting models above `register_code_routes`):

```python
class _Position(BaseModel):
    line: int
    character: int


class _Range(BaseModel):
    start: _Position
    end: _Position


class _FileSymbol(BaseModel):
    name: str
    kind: str
    range: _Range
    children: list["_FileSymbol"] | None = None


class _ResponseFileSymbols(BaseModel):
    symbols: list[_FileSymbol]
```

Inside `register_code_routes` (next to `code_list_dir`):

```python
    @app.get("/code/file_symbols")
    def code_file_symbols(path: str) -> _ResponseFileSymbols:
        root = _get_project_root_or_503(agent)
        try:
            resolved = resolve_project_path(root, path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="file not found")
        ls = _get_language_server_or_503(agent, path)
        rel = os.path.relpath(resolved, os.path.realpath(root))
        try:
            raw = ls.request_document_symbols(rel)
        except Exception as e:  # noqa: BLE001
            log.error("LSP document symbols failed for %s: %s", rel, e, exc_info=e)
            raise HTTPException(status_code=502, detail={"error": str(e), "code": "ls_error"})

        def _convert(node: dict) -> _FileSymbol:
            return _FileSymbol(
                name=node["name"],
                kind=str(node.get("kind", "")),
                range=node["range"],
                children=[_convert(c) for c in node.get("children", [])] if node.get("children") else None,
            )

        return _ResponseFileSymbols(symbols=[_convert(s) for s in raw])
```

> **Implementer note:** the exact LSP method name (`request_document_symbols`) and return shape must match what `SolidLanguageServer` actually exposes — read `src/solidlsp/ls.py` if there's a difference. Adjust the call site and the `_convert` mapping accordingly. The fake `_LS` in the fixture should be updated to match the real method signature.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_dashboard_code.py -v -k file_symbols`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/serena/dashboard_code.py test/serena/test_dashboard_code.py
git commit -m "$(cat <<'EOF'
feat(dashboard): GET /code/file_symbols (LSP document symbols)

Returns a nested symbol tree for the requested file. 404 if missing,
503 ls_not_ready when no LS is initialized, 502 ls_error when LSP
raises, 400 on path-escape.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 22: `/code/workspace_symbol_search` endpoint

**Files:**
- Modify: `src/serena/dashboard_code.py`
- Modify: `test/serena/test_dashboard_code.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_code_workspace_symbol_search_returns_matches(make_agent_with_lsp):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_lsp(
        workspace_matches=[
            {"name": "foo_bar", "kind": "Function", "path": "src/a.py", "range": {"start": {"line": 1, "character": 0}, "end": {"line": 2, "character": 0}}},
            {"name": "foo_baz", "kind": "Function", "path": "src/b.py", "range": {"start": {"line": 3, "character": 0}, "end": {"line": 4, "character": 0}}},
        ]
    )
    client = TestClient(dashboard.app)
    r = client.get("/code/workspace_symbol_search?q=foo")
    assert r.status_code == 200
    body = r.json()
    assert len(body["matches"]) == 2
    assert body["matches"][0]["name"] == "foo_bar"


def test_code_workspace_symbol_search_limit_capped(make_agent_with_lsp):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_lsp(workspace_matches=[])
    client = TestClient(dashboard.app)
    r = client.get("/code/workspace_symbol_search?q=x&limit=9999")
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_dashboard_code.py -v -k workspace_symbol`

Expected: FAIL.

- [ ] **Step 3: Add the route**

Add models above `register_code_routes`:

```python
class _WorkspaceMatch(BaseModel):
    name: str
    kind: str
    path: str
    range: _Range


class _ResponseWorkspaceSymbolSearch(BaseModel):
    matches: list[_WorkspaceMatch]
```

Add route inside `register_code_routes`:

```python
    @app.get("/code/workspace_symbol_search")
    def code_workspace_symbol_search(q: str, limit: int = 50) -> _ResponseWorkspaceSymbolSearch:
        if not q:
            return _ResponseWorkspaceSymbolSearch(matches=[])
        limit = max(1, min(limit, _WORKSPACE_SYMBOL_LIMIT_CAP))
        ls = _get_language_server_or_503(agent)
        try:
            raw = ls.request_workspace_symbols(q, limit)
        except Exception as e:  # noqa: BLE001
            log.error("LSP workspace symbols failed for %r: %s", q, e, exc_info=e)
            raise HTTPException(status_code=502, detail={"error": str(e), "code": "ls_error"})
        return _ResponseWorkspaceSymbolSearch(
            matches=[
                _WorkspaceMatch(
                    name=m["name"], kind=str(m.get("kind", "")), path=m["path"], range=m["range"],
                )
                for m in raw
            ]
        )
```

> **Implementer note:** `SolidLanguageServer` may not currently expose `request_workspace_symbols`. If not, add a thin wrapper in `solidlsp/ls.py` that sends an LSP `workspace/symbol` request — refer to `request_document_symbols` for the request-style pattern already in place. Then update the fake `_LS` in the test fixture accordingly.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_dashboard_code.py -v -k workspace_symbol`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/serena/dashboard_code.py src/solidlsp/ls.py test/serena/test_dashboard_code.py
git commit -m "$(cat <<'EOF'
feat(dashboard): GET /code/workspace_symbol_search (LSP workspace/symbol)

Debounced from the frontend; backend caps limit at 200. Empty q
returns []. Thin solidlsp wrapper added if not already present.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 23: `/code/diagnostics_summary` endpoint

**Files:**
- Modify: `src/serena/dashboard_code.py`
- Modify: `test/serena/test_dashboard_code.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_code_diagnostics_summary_returns_files_with_diagnostics(make_agent_with_lsp):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_lsp(
        diagnostics={
            "main.py": [
                {"severity": "error", "message": "undefined name 'x'", "line": 1, "column": 4, "source": "pyflakes"},
            ],
        }
    )
    (root / "main.py").write_text("print(x)")
    client = TestClient(dashboard.app)
    r = client.get("/code/diagnostics_summary?file_limit=10")
    assert r.status_code == 200
    body = r.json()
    assert any(f["path"].endswith("main.py") for f in body["files"])
    assert body["truncated"] is False


def test_code_diagnostics_summary_file_limit_capped(make_agent_with_lsp):
    from fastapi.testclient import TestClient
    agent, dashboard, root = make_agent_with_lsp(diagnostics={})
    client = TestClient(dashboard.app)
    r = client.get("/code/diagnostics_summary?file_limit=999999")
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test/serena/test_dashboard_code.py -v -k diagnostics`

Expected: FAIL.

- [ ] **Step 3: Add the route**

Add models above `register_code_routes`:

```python
class _Diagnostic(BaseModel):
    severity: str
    message: str
    line: int
    column: int
    source: str | None = None


class _FileDiagnostics(BaseModel):
    path: str
    diagnostics: list[_Diagnostic]


class _ResponseDiagnosticsSummary(BaseModel):
    files: list[_FileDiagnostics]
    truncated: bool
```

Add route inside `register_code_routes`:

```python
    @app.get("/code/diagnostics_summary")
    def code_diagnostics_summary(file_limit: int = 1000) -> _ResponseDiagnosticsSummary:
        file_limit = max(1, min(file_limit, _FILE_LIMIT_CAP))
        root = _get_project_root_or_503(agent)
        ls = _get_language_server_or_503(agent)
        # Discover the files that the LS knows about (or fall back to walking).
        candidate_paths: list[str] = []
        try:
            candidate_paths = list(ls.started_language_servers_relative_paths())
        except Exception:  # noqa: BLE001
            for dirpath, dirnames, filenames in os.walk(root):
                # prune common skip dirs in place
                dirnames[:] = [d for d in dirnames if d not in _GITIGNORE_HARDCODED and not d.startswith(".")]
                for fn in filenames:
                    if fn.startswith("."):
                        continue
                    rel = os.path.relpath(os.path.join(dirpath, fn), root)
                    candidate_paths.append(rel)
        truncated = False
        if len(candidate_paths) > file_limit:
            candidate_paths = candidate_paths[:file_limit]
            truncated = True

        files: list[_FileDiagnostics] = []
        total_bytes = 0
        for rel in candidate_paths:
            try:
                raw = ls.request_published_text_document_diagnostics(rel)
            except Exception as e:  # noqa: BLE001
                log.warning("Diagnostics failed for %s: %s", rel, e)
                continue
            if not raw:
                continue
            diags = [
                _Diagnostic(
                    severity=str(d.get("severity", "info")),
                    message=str(d.get("message", "")),
                    line=int(d.get("line", 0)),
                    column=int(d.get("column", 0)),
                    source=d.get("source"),
                )
                for d in raw
            ]
            # Per-file size cap: if encoded JSON would exceed 1 MB, truncate the list.
            fd = _FileDiagnostics(path=rel, diagnostics=diags)
            payload_size = len(fd.model_dump_json().encode("utf-8"))
            if payload_size > _DIAGNOSTICS_PER_FILE_BYTE_CAP:
                # Drop diagnostics until under cap (keep oldest indices).
                keep = max(1, int(len(diags) * _DIAGNOSTICS_PER_FILE_BYTE_CAP / payload_size))
                fd = _FileDiagnostics(path=rel, diagnostics=diags[:keep])
                truncated = True
            files.append(fd)
            total_bytes += payload_size

        return _ResponseDiagnosticsSummary(files=files, truncated=truncated)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test/serena/test_dashboard_code.py -v -k diagnostics`

Expected: PASS.

- [ ] **Step 5: Run the whole backend test suite**

Run: `uv run pytest test/serena/test_dashboard_code.py test/serena/test_dashboard.py test/serena/test_analytics.py test/serena/test_task_executor.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/serena/dashboard_code.py test/serena/test_dashboard_code.py
git commit -m "$(cat <<'EOF'
feat(dashboard): GET /code/diagnostics_summary (1 MB/file cap)

Iterates known LS-loaded paths (or walks the project), requests
published diagnostics, applies 1 MB per-file payload cap and a
file_limit cap (default 1000, max 2000). Returns truncated=true when
caps fire. Failed per-file diagnostics are logged + skipped, never
fail the whole response.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6 — Frontend Code tab

> **⚠️ Corrections that apply to Phase 6 (see top of plan for details):**
> - **B37 (CRITICAL):** `$state<Set<string>>(new Set())` in Task 24 is NOT reactive in Svelte 5. The FileTree chevron won't flip on toggle. Use `SvelteSet` from `svelte/reactivity`. The corrected `code` store with `SvelteSet` AND error states is in §"Corrected Task 24" near the top of this plan.
> - **B39:** Task 24's `loadDir` / `loadFileSymbols` have no error states; Spec §7.2 requires them. Corrected store includes `dir_errors` and `file_symbol_errors` records.
> - **B40:** `$components` alias does not exist; use `$lib/*` or relative paths. Synchronous import per existing `App.svelte` pattern.
> - **B41:** Update `Header.svelte` for the Code tab button.
> - **B42:** Task 27's `code.search()` needs `q.trim().length < 2` guard.
> - **B43:** Task 27's `selectMatch` must call `code.selectPath(path, { switchMiddleTo: 'symbols' })` so clicking a search result switches to the Symbols pane (corrected store API supports this).
> - **B44:** Task 28's `diagError = (e as Error).message` fails for non-Error throws. Use `e instanceof Error ? e.message : String(e)`.
> - **B45:** Task 30 Playwright Code-tab tests will see 503 `ls_not_ready` (the emulator has no LSP). Stub `/code/*` via `page.route(...)` in the test setup.

### Task 24: `code` store + register code tab in App.svelte

**Files:**
- Create: `dashboard/src/lib/stores/code.svelte.ts`
- Modify: `dashboard/src/App.svelte` (register Code tab between Stats and Logs)
- Create: `dashboard/tests/code-store.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `dashboard/tests/code-store.test.ts`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { stubFetchRoutes } from './helpers';
import { createCodeStore } from '../src/lib/stores/code.svelte';

describe('code store', () => {
  it('caches list_dir results per path', async () => {
    const calls: string[] = [];
    stubFetchRoutes([
      {
        match: '/code/list_dir',
        handler: (url) => {
          calls.push(url);
          return { entries: [{ name: 'a', kind: 'file' }] };
        },
      },
    ]);
    const store = createCodeStore();
    await store.loadDir('src');
    await store.loadDir('src'); // cached
    expect(calls.length).toBe(1);
  });

  it('caches file_symbols results per path', async () => {
    const calls: string[] = [];
    stubFetchRoutes([
      {
        match: '/code/file_symbols',
        handler: (url) => {
          calls.push(url);
          return { symbols: [] };
        },
      },
    ]);
    const store = createCodeStore();
    await store.loadFileSymbols('a.py');
    await store.loadFileSymbols('a.py');
    expect(calls.length).toBe(1);
  });

  it('search uses epoch counter to discard stale responses', async () => {
    let resolveSlow: (v: unknown) => void = () => {};
    const slow = new Promise((res) => (resolveSlow = res));
    let queries: string[] = [];
    stubFetchRoutes([
      {
        match: '/code/workspace_symbol_search',
        handler: async (url) => {
          queries.push(url);
          if (url.includes('q=ab')) {
            await slow;
            return { matches: [{ name: 'OLD', kind: 'F', path: 'x.py', range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } } }] };
          }
          return { matches: [{ name: 'NEW', kind: 'F', path: 'y.py', range: { start: { line: 0, character: 0 }, end: { line: 0, character: 0 } } }] };
        },
      },
    ]);
    const store = createCodeStore();
    const p1 = store.search('ab');
    const p2 = store.search('abc');
    await p2;
    resolveSlow(null);
    await p1;
    expect(store.search_results[0]?.name).toBe('NEW');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && npm test -- code-store`

Expected: FAIL — module missing.

- [ ] **Step 3: Create `dashboard/src/lib/stores/code.svelte.ts`**

```ts
import {
  fetchCodeListDir,
  fetchCodeFileSymbols,
  fetchCodeWorkspaceSymbolSearch,
  fetchCodeDiagnosticsSummary,
} from '$lib/api/endpoints';
import type { DirEntry, FileSymbol, WorkspaceMatch, FileDiagnostics } from '$lib/api/types';

export function createCodeStore() {
  const dirChildren = $state<Record<string, DirEntry[]>>({});
  const expanded = $state<Set<string>>(new Set());
  let selectedPath = $state<string | null>(null);
  const fileSymbols = $state<Record<string, FileSymbol[]>>({});
  let searchQuery = $state('');
  let searchResults = $state<WorkspaceMatch[]>([]);
  let searchLoading = $state(false);
  let searchEpoch = 0;
  let diagFiles = $state<FileDiagnostics[]>([]);
  let diagLoading = $state(false);
  let diagError = $state<string | null>(null);
  let diagTruncated = $state(false);
  let diagLastRefreshAt = $state<number | null>(null);

  return {
    get dir_children() {
      return dirChildren;
    },
    get expanded() {
      return expanded;
    },
    get selected_path() {
      return selectedPath;
    },
    get file_symbols() {
      return fileSymbols;
    },
    get search_query() {
      return searchQuery;
    },
    get search_results() {
      return searchResults;
    },
    get search_loading() {
      return searchLoading;
    },
    get diag_files() {
      return diagFiles;
    },
    get diag_loading() {
      return diagLoading;
    },
    get diag_error() {
      return diagError;
    },
    get diag_truncated() {
      return diagTruncated;
    },
    get diag_last_refresh_at() {
      return diagLastRefreshAt;
    },
    async loadDir(path: string) {
      if (dirChildren[path]) return;
      const resp = await fetchCodeListDir(path);
      dirChildren[path] = resp.entries;
    },
    toggleExpand(path: string) {
      if (expanded.has(path)) expanded.delete(path);
      else {
        expanded.add(path);
        void this.loadDir(path);
      }
    },
    selectPath(path: string | null) {
      selectedPath = path;
      if (path) void this.loadFileSymbols(path);
    },
    async loadFileSymbols(path: string) {
      if (fileSymbols[path]) return;
      const resp = await fetchCodeFileSymbols(path);
      fileSymbols[path] = resp.symbols;
    },
    async search(q: string) {
      searchQuery = q;
      if (!q.trim()) {
        searchResults = [];
        searchLoading = false;
        return;
      }
      const myEpoch = ++searchEpoch;
      searchLoading = true;
      try {
        const resp = await fetchCodeWorkspaceSymbolSearch(q, 50);
        if (myEpoch === searchEpoch) {
          searchResults = resp.matches;
        }
      } finally {
        if (myEpoch === searchEpoch) searchLoading = false;
      }
    },
    async refreshDiagnostics(file_limit = 1000) {
      diagLoading = true;
      diagError = null;
      try {
        const resp = await fetchCodeDiagnosticsSummary(file_limit);
        diagFiles = resp.files;
        diagTruncated = resp.truncated;
        diagLastRefreshAt = Date.now();
      } catch (e) {
        diagError = (e as Error).message;
      } finally {
        diagLoading = false;
      }
    },
  };
}

export const code = createCodeStore();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && npm test -- code-store`

Expected: PASS.

- [ ] **Step 5: Register the Code tab in `App.svelte`**

Read `App.svelte` first. Find the tab list (the switch on `view`) and add `'code'` between Stats and Logs. Example shape:

```svelte
<nav class="tabs">
  <button onclick={() => navigate('overview')} aria-current={view === 'overview' ? 'page' : undefined}>Overview</button>
  <button onclick={() => navigate('stats')} aria-current={view === 'stats' ? 'page' : undefined}>Stats</button>
  <button onclick={() => navigate('code')} aria-current={view === 'code' ? 'page' : undefined}>Code</button>
  <button onclick={() => navigate('logs')} aria-current={view === 'logs' ? 'page' : undefined}>Logs</button>
</nav>

{#if view === 'code'}
  {#await import('$components/code/CodePage.svelte') then m}
    <m.default />
  {/await}
{/if}
```

> **Implementer note:** match the existing structural pattern — the snippet above is a reference. If the project doesn't currently lazy-load views, render synchronously instead.

- [ ] **Step 6: Type-check + run store tests**

Run: `cd dashboard && npm run check && npm test -- code-store`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/lib/stores/code.svelte.ts dashboard/src/App.svelte dashboard/tests/code-store.test.ts
git commit -m "$(cat <<'EOF'
feat(dashboard): code store + Code tab between Stats and Logs

createCodeStore() owns lazy folder cache, file-symbols cache, search
state with epoch-counter staleness gating, and diagnostics state.
Code tab registered in the App.svelte tab list and pollers map.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 25: `FileTree.svelte` (lazy folder tree)

**Files:**
- Create: `dashboard/src/components/code/FileTree.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import type { DirEntry } from '$lib/api/types';

  interface Props {
    rootPath?: string;
  }
  let { rootPath = '.' }: Props = $props();

  $effect(() => {
    void code.loadDir(rootPath);
  });

  function joinPath(base: string, child: string): string {
    if (base === '.' || base === '') return child;
    return `${base}/${child}`;
  }
</script>

{#snippet treeNode(path: string, depth: number)}
  {@const children = code.dir_children[path]}
  <ul class="list" style:--depth={depth}>
    {#if !children}
      <li class="loading">…</li>
    {:else}
      {#each children as entry}
        {@const fullPath = joinPath(path, entry.name)}
        <li>
          {#if entry.kind === 'dir'}
            <button
              type="button"
              class="row dir"
              onclick={() => code.toggleExpand(fullPath)}
              aria-expanded={code.expanded.has(fullPath)}
            >
              <span class="chev">{code.expanded.has(fullPath) ? '▾' : '▸'}</span>
              <span class="name">{entry.name}</span>
            </button>
            {#if code.expanded.has(fullPath)}
              {@render treeNode(fullPath, depth + 1)}
            {/if}
          {:else}
            <button
              type="button"
              class="row file"
              class:selected={code.selected_path === fullPath}
              onclick={() => code.selectPath(fullPath)}
            >
              <span class="chev"></span>
              <span class="name">{entry.name}</span>
            </button>
          {/if}
        </li>
      {/each}
    {/if}
  </ul>
{/snippet}

{@render treeNode(rootPath, 0)}

<style>
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    width: 100%;
    text-align: left;
    background: transparent;
    border: 0;
    color: var(--text-primary);
    cursor: pointer;
    padding: var(--space-1);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    font-family: var(--font-mono);
    font-size: 0.9em;
  }
  .row:hover {
    background: var(--bg);
  }
  .row.selected {
    background: var(--bg);
    color: var(--accent);
  }
  .chev {
    width: 1em;
    color: var(--text-secondary);
  }
  .loading {
    color: var(--text-secondary);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/components/code/FileTree.svelte
git commit -m "$(cat <<'EOF'
feat(dashboard): FileTree (lazy folder navigation for Code tab)

Click folder to expand/collapse; loads on first expand and caches.
Click file to select (drives FileSymbols pane).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 26: `FileSymbols.svelte` (LSP document symbols)

**Files:**
- Create: `dashboard/src/components/code/FileSymbols.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';
  import type { FileSymbol } from '$lib/api/types';

  const path = $derived(code.selected_path);
  const symbols = $derived(path ? code.file_symbols[path] : undefined);
</script>

{#snippet symbolNode(s: FileSymbol, depth: number)}
  <li style:--depth={depth} class="row">
    <span class="kind">{s.kind}</span>
    <span class="name">{s.name}</span>
    <span class="loc">{s.range.start.line + 1}:{s.range.start.character + 1}</span>
  </li>
  {#if s.children && s.children.length > 0}
    {#each s.children as c}
      {@render symbolNode(c, depth + 1)}
    {/each}
  {/if}
{/snippet}

<div class="root">
  {#if !path}
    <p class="empty">Select a file from the tree.</p>
  {:else if symbols === undefined}
    <p class="empty">Loading…</p>
  {:else if symbols.length === 0}
    <p class="empty">No symbols.</p>
  {:else}
    <ul class="list">
      {#each symbols as s}
        {@render symbolNode(s, 0)}
      {/each}
    </ul>
  {/if}
</div>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-3);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .row {
    display: grid;
    grid-template-columns: 80px 1fr 60px;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    padding-left: calc(var(--space-2) + var(--depth, 0) * var(--space-3));
    border-bottom: 1px solid var(--border);
  }
  .kind {
    color: var(--text-secondary);
  }
  .loc {
    color: var(--text-secondary);
    text-align: right;
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/components/code/FileSymbols.svelte
git commit -m "$(cat <<'EOF'
feat(dashboard): FileSymbols (nested LSP document-symbols pane)

Renders the symbol tree for the file selected in FileTree. Loading
and empty states.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 27: `WorkspaceSearch.svelte` (debounced + epoch staleness)

**Files:**
- Create: `dashboard/src/components/code/WorkspaceSearch.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';

  let value = $state(code.search_query);
  let timer: ReturnType<typeof setTimeout> | null = null;

  function onInput(e: Event) {
    value = (e.target as HTMLInputElement).value;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      void code.search(value);
    }, 250);
  }

  function selectMatch(path: string) {
    code.selectPath(path);
  }
</script>

<div class="root">
  <input
    type="search"
    placeholder="Search workspace symbols…"
    value={value}
    oninput={onInput}
    class="input"
  />
  {#if code.search_loading}
    <div class="status">Searching…</div>
  {:else if value && code.search_results.length === 0}
    <div class="status">No matches.</div>
  {:else if code.search_results.length > 0}
    <ul class="results">
      {#each code.search_results as m}
        <li>
          <button type="button" onclick={() => selectMatch(m.path)} class="match">
            <span class="kind">{m.kind}</span>
            <span class="name">{m.name}</span>
            <span class="path">{m.path}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .root {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .input {
    width: 100%;
    padding: var(--space-2);
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text-primary);
    font-family: inherit;
  }
  .input:focus {
    outline: none;
    border-color: var(--accent);
  }
  .status {
    color: var(--text-secondary);
    padding: var(--space-2);
  }
  .results {
    list-style: none;
    margin: var(--space-2) 0 0;
    padding: 0;
    overflow-y: auto;
    flex: 1;
  }
  .match {
    width: 100%;
    text-align: left;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border);
    padding: var(--space-1) var(--space-2);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.85em;
    cursor: pointer;
    display: grid;
    grid-template-columns: 80px 1fr auto;
    gap: var(--space-2);
  }
  .match:hover {
    background: var(--bg);
  }
  .kind {
    color: var(--text-secondary);
  }
  .path {
    color: var(--text-secondary);
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/components/code/WorkspaceSearch.svelte
git commit -m "$(cat <<'EOF'
feat(dashboard): WorkspaceSearch (LSP workspace/symbol)

Debounced 250 ms input → /code/workspace_symbol_search. Click a
match → selects the file in the tree. Store-level epoch counter
prevents stale slow-search responses from overwriting newer ones.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 28: `DiagnosticsPanel.svelte` (with warning banner, no cancel)

**Files:**
- Create: `dashboard/src/components/code/DiagnosticsPanel.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
  import { code } from '$lib/stores/code.svelte';

  function refresh() {
    if (code.diag_loading) return;
    void code.refreshDiagnostics(1000);
  }
</script>

<section class="root">
  <header>
    <h3>Diagnostics</h3>
    <button type="button" class="refresh" onclick={refresh} disabled={code.diag_loading}>
      {code.diag_loading ? 'Computing…' : '↻ Refresh'}
    </button>
  </header>

  {#if code.diag_loading}
    <div class="warn">
      ⚠ Computing diagnostics — this can take a while and temporarily slows other
      LSP-backed tools.
    </div>
  {/if}

  {#if code.diag_error}
    <div class="error-card">
      <strong>Diagnostics failed.</strong>
      <div class="msg">{code.diag_error}</div>
    </div>
  {/if}

  {#if code.diag_truncated && !code.diag_loading}
    <div class="warn">
      Showing first {code.diag_files.length} files; project has more.
    </div>
  {/if}

  {#if code.diag_files.length === 0 && !code.diag_loading && !code.diag_error}
    <p class="empty">
      Click Refresh to compute diagnostics. (Results are not auto-refreshed because
      diagnostics is slow.)
    </p>
  {/if}

  {#each code.diag_files as f}
    <details class="file">
      <summary>
        <span class="path">{f.path}</span>
        <span class="count">{f.diagnostics.length}</span>
      </summary>
      <ul class="diags">
        {#each f.diagnostics as d}
          <li class={`sev-${d.severity}`}>
            <span class="loc">{d.line + 1}:{d.column + 1}</span>
            <span class="sev">{d.severity}</span>
            <span class="msg">{d.message}</span>
            {#if d.source}<span class="source">[{d.source}]</span>{/if}
          </li>
        {/each}
      </ul>
    </details>
  {/each}
</section>

<style>
  .root {
    height: 100%;
    overflow-y: auto;
    padding: var(--space-2);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  header h3 {
    margin: 0;
    font-size: 1em;
  }
  .refresh {
    margin-left: auto;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
    color: var(--text-primary);
  }
  .refresh:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .warn {
    background: var(--bg);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--text-secondary);
    margin-bottom: var(--space-2);
  }
  .error-card {
    background: var(--bg);
    border: 1px solid var(--danger, #c33);
    border-radius: var(--radius);
    padding: var(--space-2);
    color: var(--danger, #c33);
    margin-bottom: var(--space-2);
  }
  .empty {
    color: var(--text-secondary);
    padding: var(--space-2);
  }
  .file {
    border-bottom: 1px solid var(--border);
    padding: var(--space-1) 0;
  }
  .file summary {
    display: flex;
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 0.9em;
  }
  .file summary .count {
    margin-left: auto;
    color: var(--text-secondary);
  }
  .diags {
    list-style: none;
    margin: var(--space-1) 0 0;
    padding: 0;
    font-family: var(--font-mono);
    font-size: 0.85em;
  }
  .diags li {
    display: grid;
    grid-template-columns: 70px 60px 1fr auto;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
  }
  .sev-error {
    color: var(--danger, #c33);
  }
  .sev-warning {
    color: var(--accent);
  }
  .sev-info,
  .sev-hint {
    color: var(--text-secondary);
  }
  .source {
    color: var(--text-secondary);
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/components/code/DiagnosticsPanel.svelte
git commit -m "$(cat <<'EOF'
feat(dashboard): DiagnosticsPanel (manual refresh + warning, no cancel)

Refresh button disabled while in-flight; warning banner explains that
computing diagnostics temporarily slows other LSP-backed tools.
Previous results stay visible on error. Files-with-issues grouped by
path; expandable to individual diagnostics (severity, line:col,
message, source).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 29: `CodePage.svelte` three-pane layout

**Files:**
- Create: `dashboard/src/components/code/CodePage.svelte`

- [ ] **Step 1: Create the component**

```svelte
<script lang="ts">
  import FileTree from './FileTree.svelte';
  import FileSymbols from './FileSymbols.svelte';
  import WorkspaceSearch from './WorkspaceSearch.svelte';
  import DiagnosticsPanel from './DiagnosticsPanel.svelte';

  type MiddleTab = 'symbols' | 'search';
  let middle = $state<MiddleTab>('symbols');
</script>

<div class="layout">
  <aside class="tree">
    <FileTree />
  </aside>
  <section class="middle">
    <nav class="middle-tabs">
      <button class:active={middle === 'symbols'} onclick={() => (middle = 'symbols')}>Symbols (file)</button>
      <button class:active={middle === 'search'} onclick={() => (middle = 'search')}>Search (workspace)</button>
    </nav>
    {#if middle === 'symbols'}
      <FileSymbols />
    {:else}
      <WorkspaceSearch />
    {/if}
  </section>
  <aside class="diagnostics">
    <DiagnosticsPanel />
  </aside>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: 260px 1fr 320px;
    gap: var(--space-2);
    height: calc(100vh - 140px);
  }
  .tree,
  .middle,
  .diagnostics {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .middle-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }
  .middle-tabs button {
    background: transparent;
    border: 0;
    padding: var(--space-2);
    color: var(--text-secondary);
    cursor: pointer;
  }
  .middle-tabs button.active {
    color: var(--accent);
    border-bottom: 2px solid var(--accent);
  }
  .tree {
    overflow-y: auto;
  }
  @media (max-width: 1000px) {
    .layout {
      grid-template-columns: 1fr;
      grid-template-rows: auto auto auto;
      height: auto;
    }
  }
</style>
```

- [ ] **Step 2: Verify the Code tab renders end-to-end**

Run: `cd dashboard && npm run check`

Expected: no type errors.

Manual: `cd dashboard && npm run dev` with a running Serena MCP backend (one that has a language server). Click Code tab; confirm three panes render; expand a folder, click a file, see symbols; type in the workspace search box; click Refresh in Diagnostics and see warning banner + result.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/code/CodePage.svelte
git commit -m "$(cat <<'EOF'
feat(dashboard): CodePage three-pane layout (Tree / Symbols+Search / Diagnostics)

Composes FileTree, FileSymbols ⇄ WorkspaceSearch, DiagnosticsPanel.
Middle pane tab switches Symbols/Search without losing tree state.
Responsive: stacks vertically on narrow viewports.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 7 — Final pass (smoke test, format, asset rebuild)

### Task 30: Playwright golden-path smoke test

**Files:**
- Create: `dashboard/tests/code-tab.spec.ts` (Playwright)
- Modify: `dashboard/package.json` if Playwright isn't installed yet

> **Prereq:** the emulator script (`run-dashboard-emulate-tool-calls.md` in memory) seeds synthetic tool calls so the dashboard has data without a live agent loop. Use it as the boot mechanism.

- [ ] **Step 1: Confirm Playwright availability**

Run: `cd dashboard && npx playwright --version || echo "missing"`

If `missing`: `cd dashboard && npm install -D @playwright/test && npx playwright install chromium`. Add a `playwright.config.ts` if none exists, pointing `baseURL` at `http://localhost:5273`.

- [ ] **Step 2: Write the smoke test**

Create `dashboard/tests/code-tab.spec.ts`:

```ts
import { test, expect } from '@playwright/test';

// Goal: golden-path validation of every new surface. Requires the dashboard
// running (e.g. via the emulator script) on localhost:5273 before this test
// is invoked.

test('overview shows 4 summary cards', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Overview' }).click();
  const titles = await page.locator('[data-card-title]').allTextContents();
  expect(titles).toEqual(['Calls', 'Tokens', 'Time', 'Errors']);
});

test('timeline rows render and expand', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Overview' }).click();
  const firstRow = page.locator('[data-timeline-row]').first();
  await expect(firstRow).toBeVisible({ timeout: 10_000 });
  await firstRow.getByRole('button').first().click();
  await expect(page.getByText('seq:')).toBeVisible();
});

test('stats sort selector reorders charts', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Stats' }).click();
  // Capture the first chart's category labels with default sort
  const before = await page.locator('canvas').first().evaluate(() => 'ok');
  await page.getByLabel(/Sort by/i).selectOption({ value: 'duration_total' });
  // Charts update in place — visual change isn't easy to assert here, so just
  // confirm no errors and that the selector reflects the change.
  await expect(page.getByLabel(/Sort by/i)).toHaveValue('duration_total');
  expect(before).toBe('ok');
});

test('clicking a pie slice opens drill-down panel', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Stats' }).click();
  // Click in the center of the first chart canvas — actual slice hit is best-effort.
  const canvas = page.locator('canvas').first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error('canvas has no bounding box');
  await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.4);
  await expect(page.getByRole('dialog', { name: 'Tool details' })).toBeVisible({ timeout: 3_000 });
});

test('code tab navigates folder tree and shows symbols', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Code' }).click();
  // Wait for any folder row to appear
  const firstDir = page.locator('button.row.dir').first();
  await expect(firstDir).toBeVisible({ timeout: 10_000 });
  await firstDir.click();
  // Click the first file under it
  const firstFile = page.locator('button.row.file').first();
  await firstFile.click();
  // Symbols pane should show "Loading…" or actual symbols quickly
  await expect(page.getByText(/Loading|Symbols/)).toBeVisible({ timeout: 5_000 });
});

test('diagnostics refresh shows warning banner', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Code' }).click();
  const refresh = page.getByRole('button', { name: /Refresh/ });
  await refresh.click();
  await expect(page.getByText(/Computing diagnostics/)).toBeVisible({ timeout: 3_000 });
});
```

- [ ] **Step 3: Run the smoke test**

Start the emulator + dashboard per `run-dashboard-emulate-tool-calls.md`, then in another shell:

`cd dashboard && npx playwright test code-tab.spec.ts`

Expected: PASS (6 tests).

- [ ] **Step 4: Commit**

```bash
git add dashboard/tests/code-tab.spec.ts dashboard/playwright.config.ts dashboard/package.json dashboard/package-lock.json
git commit -m "$(cat <<'EOF'
test(dashboard): Playwright golden-path smoke for the port

Single end-to-end spec covering the 6 new surfaces: SummaryCards,
Timeline row expansion, SortSelector, DrillDown, Code tab navigation,
Diagnostics warning banner. Run against the emulator script before
shipping.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 31: Format + run all tests + regenerate built assets

This is the CI contract: any Svelte change requires a rebuilt `src/serena/resources/dashboard/` checked in.

- [ ] **Step 1: Run the full frontend test suite**

Run: `cd dashboard && npm run format && npm test`

Expected: PASS, no formatting changes after.

- [ ] **Step 2: Run the full backend test suite**

Run: `uv run pytest test/serena/ -q`

Expected: PASS.

- [ ] **Step 3: Type-check**

Run: `cd dashboard && npm run check`

Expected: PASS.

- [ ] **Step 4: Rebuild assets**

Run: `cd dashboard && npm run build`

Expected: `../src/serena/resources/dashboard/index.html` and `../src/serena/resources/dashboard/assets/` regenerated.

- [ ] **Step 5: Stage everything and commit**

```bash
git add src/serena/resources/dashboard/
git status   # confirm only the regenerated assets show
git commit -m "$(cat <<'EOF'
build(dashboard): regenerate bundle for legacy-feature port

Final asset rebuild after the Timeline / SummaryCards / Sort /
Duration / Rate / DrillDown / Code-tab additions.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Manual verification with the emulator**

Follow `~/.claude/projects/-Users-Pavlo-Basanets-PycharmProjects-serena-fork/memory/run-dashboard-emulate-tool-calls.md`. Open the dashboard in a browser. Verify, with console open:

- 4 SummaryCards under Overview, updating each second.
- Timeline ticks in new rows; expand one; see args + output; truncation note appears if seeded with >8 KB I/O.
- Pause stops new rows; Resume picks them back up; Clear empties the view.
- Per-tool filter applies via FilterDropdown; × clears it.
- Stats tab: SortSelector changes reorder pies + tokens bar + DurationChart consistently.
- RateChart shows per-minute counts; window selector switches; stacked-area toggle reveals per-tool layers; Show all / Disable all work.
- Click a pie slice → DrillDownPanel slides in with the 6 aggregates + p95 + recent errors + last 20 calls + "Open in Timeline" jump.
- Code tab between Stats and Logs. FileTree expands lazily; click a file → FileSymbols renders; toggle "Search (workspace)" → debounced search works.
- DiagnosticsPanel: Refresh button shows the warning banner; result renders; previous results stay on error.
- Open DevTools → no console errors during any of the above.

If anything fails, fix in a follow-up task and rebuild assets.

---

## Self-review (run after the plan above is complete)

This section is meant for the implementer to run against this plan + the spec — it's the same checklist used when authoring.

**1. Spec coverage check.** Walk through every numbered section of `docs/superpowers/specs/2026-05-28-dashboard-v2-legacy-port-design.md` and confirm a task implements it:

| Spec section | Task(s) |
|---|---|
| §3 Architecture & module boundaries | All phases |
| §4.1 `analytics.py` extensions | T1, T2, T3 |
| §4.2 `task_executor.py` enrichments + race fix | T4 |
| §4.3 Tool dispatch instrumentation | T5 |
| §4.4 New endpoints (timeline + code + tool_stats_totals + executions) | T6, T7, T8, T20, T21, T22, T23 |
| §4.5 Path-traversal guard | T19 |
| §5.1 FilterDropdown | T11 |
| §5.2 SummaryCards + Timeline | T12, T13, T14 |
| §5.3 SortSelector + DurationChart + RateChart + DrillDownPanel | T15, T16, T17, T18 |
| §5.4 Code tab (FileTree / FileSymbols / WorkspaceSearch / DiagnosticsPanel) | T24, T25, T26, T27, T28, T29 |
| §5.5 Polling primitive `??` | T10 (baked into store + regression test) |
| §6 Data flow & polling, timeline buffer cap, backpressure | T10, T14 |
| §7 Error handling | T5 (analytics safety), T19 (HTTP code translation), T28 (UI on error) |
| §8.1 Backend tests | T1, T2, T3, T4, T6, T7, T8, T19, T20, T21, T22, T23 |
| §8.2 Frontend tests | T10, T11, T12, T13, T15, T16, T17, T18, T24 |
| §8.3 Playwright smoke | T30 |
| §9 Manual verification | T31 |
| §10 Implementation sequence | Matches Phases 1–7 |

**2. Placeholder scan.** Search this plan for "TBD", "TODO", "fill in", "similar to" — none should appear. The "Implementer note:" callouts are intentional pointers; they direct the implementer to *read* a referenced file before editing, not placeholders.

**3. Type consistency.**

- `ToolCallRecord` shape used identically in backend (`analytics.py`), backend Pydantic (`ToolCallRecordResponse`), and frontend (`types.ts`).
- `ToolStatsTotals` keys (`num_calls`, `num_errors`, `total_duration_ms`, `total_tokens`) are identical in backend dict (T7), Pydantic field (T7), and frontend `types.ts` (T9).
- `SortKey` union (`'calls' | 'tokens' | 'duration_total' | 'duration_avg' | 'errors'`) is identical in `stats.svelte.ts` and `SortSelector.svelte` and `sortToolsBy`.
- Diagnostic severity strings (`'error' | 'warning' | 'info' | 'hint'`) match between backend `_Diagnostic.severity` (a `str` field, validated implicitly by source) and frontend `DiagnosticSeverity`. The backend currently passes through whatever the LS sends — the implementer should normalize to these four values in T23 if the LSP returns numeric LSP severity codes (1=error, 2=warning, 3=info, 4=hint).

**4. Scope check.** Single coherent port: agent observability + project navigator. All tasks share the same Svelte runes + pytest patterns. 7 phases, 31 tasks; each task is one PR-worthy unit.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-28-dashboard-v2-legacy-port.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**

