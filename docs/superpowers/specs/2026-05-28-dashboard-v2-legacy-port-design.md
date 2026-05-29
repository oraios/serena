# Dashboard v2 — Port of legacy `dashboard` branch features

**Date:** 2026-05-28
**Branch:** `dashboard_v2`
**Scope:** Tiers 1, 2, 4, 5 from the feature audit, plus Tier 3 #9 (Rate chart) and #11 (Avg/Max duration chart). LSP Diagnostics gets a warning banner instead of a cancel button.

---

## 1. Goal

Port the agent-observability features from the legacy jQuery `dashboard` branch into the Svelte 5 + TypeScript `dashboard_v2` rebuild. The legacy branch added per-call timing, an in-memory record buffer, a live tool-call Timeline, a Code tab with project navigator and LSP diagnostics, and several UX refinements. None of these exist in `dashboard_v2` today.

This spec defines a single coherent port, scoped to one implementation plan. It is **not** a full re-implementation of the legacy branch: we deliberately omit co-occurrence (Tier 3 #10), the dev-only injection endpoint, the editor-URL template, and an LSP cancel mechanism.

## 2. Non-goals

- Implementing LSP `$/cancelRequest` in `solidlsp`. Out of scope; we surface a warning instead.
- Tool sequences / co-occurrence chart (Tier 3 #10).
- "Open in external editor" URL template (Tier 5 polish).
- Restoring `/_dev_inject_tool_call`. The local emulator script covers this.
- Any global LSP serialization lock. Behavior matches today; we only make existing serialization visible to the user.

## 3. Architecture & module boundaries

### 3.1 Backend (Python)

Three existing modules touched, one new helper:

- `src/serena/analytics.py` — extend `ToolUsageStats.Entry`; add `ToolCallRecord` and a bounded ring buffer with a monotonic seq cursor on `ToolUsageStats`.
- `src/serena/task_executor.py` — extend `TaskInfo`; race-fix the ordering around `Future` resolution.
- `src/serena/agent.py` — wrap tool dispatch with timing + error capture via a `_record_tool_call_safely` helper.
- `src/serena/dashboard.py` — five new routes; one extended payload (`/get_config_overview`).
- `src/serena/dashboard_code.py` — **new** helper module encapsulating the four `/code/*` endpoints, so `dashboard.py` stays a thin router.

### 3.2 Frontend (Svelte 5 + TS)

Layout under `dashboard/src/`:

- **Stores** (new): `lib/stores/timeline.svelte.ts`, `lib/stores/code.svelte.ts`.
- **API client / types** (extend): `lib/api/endpoints.ts`, `lib/api/types.ts`.
- **Polling registration** (extend): `lib/pollers.ts` — add `'code'` view, register `timeline` poller on both `'overview'` and `'stats'`.
- **Polling primitive fix**: switch cursor coalescing from `||` to `??` in the shared poller helper.
- **Components** (new):
  - `components/overview/SummaryCards.svelte` (replaces the inline KPI strip in `StatsSummary.svelte`).
  - `components/overview/Timeline.svelte` + `TimelineRow.svelte`.
  - `components/stats/SortSelector.svelte`.
  - `components/stats/DurationChart.svelte`.
  - `components/stats/RateChart.svelte`.
  - `components/stats/DrillDownPanel.svelte`.
  - `components/code/CodePage.svelte` + `FileTree.svelte` + `FileSymbols.svelte` + `WorkspaceSearch.svelte` + `DiagnosticsPanel.svelte`.
  - `components/common/FilterDropdown.svelte` — shared filter primitive.

### 3.3 Tab order

`Overview / Stats / Code / Logs`. Code goes between Stats and Logs.

### 3.4 Build contract

Existing: any Svelte change requires `npm run build` and committing the regenerated assets under `src/serena/resources/dashboard/`.

## 4. Backend changes

### 4.1 `analytics.py`

**Extended `Entry`:**

```python
@dataclass(kw_only=True)
class Entry:
    num_times_called: int = 0
    num_errors: int = 0                      # new
    input_tokens: int = 0
    output_tokens: int = 0
    total_duration_ms: float = 0.0           # new
    min_duration_ms: float | None = None     # new
    max_duration_ms: float | None = None     # new
    last_called_at: float | None = None      # new (epoch s)

    def update_on_call(
        self, input_tokens: int, output_tokens: int,
        duration_ms: float, success: bool, now: float,
    ) -> None: ...
```

**New `ToolCallRecord`:**

```python
@dataclass(frozen=True)
class ToolCallRecord:
    seq: int
    tool: str
    started_at: float
    duration_ms: float
    success: bool
    error_message: str | None
    input_preview: str          # truncated to 8 KB
    output_preview: str         # truncated to 8 KB
    input_truncated: bool
    output_truncated: bool
```

**`ToolUsageStats` additions:**

- `_records: collections.deque[ToolCallRecord]` with `maxlen=2000`.
- `_seq_counter: int` (monotonic, never reused).
- One `threading.Lock` guarding `_entries`, `_records`, `_seq_counter` together.
- `record_call(tool, input_str, output_str, duration_ms, success, error)` — updates `Entry` and appends a `ToolCallRecord` atomically.
- `get_records_since(since_seq: int | None, tool: str | None, limit: int) -> tuple[list[ToolCallRecord], int]` — returns records and current `max_seq`. `since_seq=None` returns the tail up to `limit`.

**Constants:** `_INPUT_OUTPUT_PREVIEW_BYTES = 8 * 1024`, `_RECORD_BUFFER_SIZE = 2000`.

### 4.2 `task_executor.py`

**Extended `TaskInfo`:**

```python
@dataclass
class TaskInfo:
    name: str
    is_running: bool
    future: Future
    task_id: int
    logged: bool
    started_at: float | None = None       # new
    finished_at: float | None = None      # new

    def get_duration_ms(self) -> int | None: ...
    def get_error_message(self) -> str | None: ...
    def get_display_name(self) -> str:                 # strips "Task-N: " prefix
```

**Race fix** in `Task.start()`'s `run_task` closure — `finished_at` is set **before** the future is resolved:

```python
self.task_info.started_at = time.time()
try:
    result = fn(*args, **kwargs)
    self.task_info.finished_at = time.time()
    self.future.set_result(result)
except BaseException as e:
    self.task_info.finished_at = time.time()
    self.future.set_exception(e)
```

`get_error_message()` reads from `future.exception()` only after `finished_at` is set. Never raises.

### 4.3 Tool dispatch instrumentation (`agent.py`)

Wrap `tool.apply()` in `agent.py` (the layer that knows the tool name and input/output reprs). A `try/finally` block calls `_record_tool_call_safely`, which catches `BaseException` from the analytics call and logs at WARNING. Instrumentation must never break the agent.

```python
start = time.perf_counter()
success = True
error_message = None
result = ""
try:
    result = tool.apply(...)
    return result
except BaseException as e:
    success = False
    error_message = type(e).__name__ + ": " + str(e)
    raise
finally:
    duration_ms = (time.perf_counter() - start) * 1000
    self._record_tool_call_safely(
        tool_name, input_repr, result, duration_ms, success, error_message,
    )
```

### 4.4 New / extended endpoints

| Route | Purpose | Notes |
|---|---|---|
| `GET /get_tool_call_timeline?since_seq=&tool=&limit=` | Tier 2 timeline | `limit` capped at 500 |
| `GET /code/list_dir?path=` | Lazy folder tree | One level only; respects gitignore |
| `GET /code/file_symbols?path=` | LSP document symbols | Nested tree |
| `GET /code/workspace_symbol_search?q=&limit=` | LSP workspace/symbol | `limit` capped at 200, default 50 |
| `GET /code/diagnostics_summary?file_limit=` | Project-wide diagnostics | 1 MB/file cap, `file_limit` default 1000 capped at 2000, returns `truncated` flag |

**`/get_config_overview` extended:** adds `tool_stats_totals = {num_calls, num_errors, total_duration_ms, total_tokens}` to drive the 4-card summary on the existing 1 s poll.

**`/queued_task_executions` and `/last_execution` extended:** include `duration_ms`, `error_message`, `display_name`, `started_at`, `finished_at`.

**Diagnostics warning behavior.** No cancel button. The Diagnostics panel surfaces a banner when a refresh is in flight: *"Computing diagnostics — this can take a while and temporarily slows other LSP-backed tools."* Refresh button disabled while a request is outstanding.

### 4.5 Path-traversal guard

`/code/list_dir` and `/code/file_symbols` resolve `path` via `os.path.realpath` and assert `os.path.commonpath([resolved, project_root]) == project_root`. Any escape (relative `..`, absolute path, symlink to outside) → 400.

## 5. Frontend changes

### 5.1 Shared primitive: `FilterDropdown.svelte`

Reusable filtered single-select. Props: `options: {value, label}[]`, `value: string | null`, `placeholder`, `onChange`. Behavior:

- Clear (×) button when a value is set.
- Active-state border in the existing orange accent token.
- Checkmark beside the applied option when the dropdown reopens.
- Keyboard nav: opening focuses the applied option; ↑/↓ moves; Enter selects; Esc closes.
- Substring filter typed while focused.
- Click-outside closes.

Used by Timeline's per-tool filter and any future filtered list.

### 5.2 Overview tab

**`SummaryCards.svelte`** — four cards driven by extended `/get_config_overview`:

| Card | Main | Subtext |
|---|---|---|
| Calls | `num_calls` (thousands-separated) | error rate `%` |
| Tokens | `total` (k/M formatted) | `in / out` split |
| Time | `total_duration_ms` formatted (`1.2 s`, `45 m`) | `avg per call` |
| Errors | `num_errors` | last error tool name (if any) |

`StatsSummary.svelte` is kept but trimmed — the inline strip extracts to `SummaryCards`; other Overview-summary content stays.

**`Timeline.svelte` + `TimelineRow.svelte`** — sits below `SummaryCards`.

Layout: header with per-tool filter (FilterDropdown), pause/resume, clear-view; page-size selector and pagination (first / prev / next / last). Rows expand inline to: `seq`, full ISO timestamp, `duration_ms`, input/output token counts, full input args and output. Long values get a "Show full" toggle; truncation notice when `input_truncated`/`output_truncated` is true.

### 5.3 Stats tab

**`SortSelector.svelte`** at the top of the Stats toolbar. Options: Calls (default), Tokens (total), Total duration, Avg duration, Errors. Single store key drives all chart specs — pies, tokens bar, and the new duration chart reorder consistently.

**`DurationChart.svelte`** — Chart.js chart, two datasets per tool: avg (solid) and max (overlay outline). Reuses the existing spec-builder pattern.

**`RateChart.svelte`** — line chart on a per-minute time axis. Controls: window selector (15 m / 30 m / 1 h / 6 h) and a per-tool stacked-area toggle with Show all / Disable all buttons. Data is computed client-side from the timeline buffer (no new endpoint). Bucket alignment: current minute is bucket N; render N+1 buckets so the live minute isn't dropped.

> **Constraint:** with a 2000-record buffer, the 6 h window only shows whatever fraction of those 6 h is present in the buffer (high-rate sessions will see less than the full window). Matches legacy behavior; we don't add a server endpoint to backfill. Acceptable for an in-memory observability view.

**`DrillDownPanel.svelte`** — right-slide overlay (300–360 px wide), opens on click of any pie slice / tokens bar / duration chart bar. Content: aggregates (Calls, Errors with %, Avg, p95, Total, Max), Recent errors, Last 20 calls, "Open in Timeline" button. p95 computed client-side from the timeline buffer for that tool, with a "based on last 2000 calls" hint shown near p95.

### 5.4 Code tab

Three-pane layout: FileTree | (FileSymbols ⇄ WorkspaceSearch) | DiagnosticsPanel.

- **`FileTree.svelte`** — lazy folder tree. Click folder → `/code/list_dir`. Click file → updates `code` store's `selectedPath`.
- **`FileSymbols.svelte`** — shows `/code/file_symbols` for the selected file. Nested LSP symbol tree with kind icons.
- **`WorkspaceSearch.svelte`** — search box at the top of the middle pane. Debounced 250 ms. Hits `/code/workspace_symbol_search`. Result rows click-to-jump (selects file + scrolls symbols). Toggle in middle-pane header switches between "Symbols (file)" and "Search (workspace)".
- **`DiagnosticsPanel.svelte`** — independent of selection. Refresh button + warning banner. Files-with-issues grouped by path; expandable to individual diagnostics (severity, message, line:col). Refresh disabled while in flight; previous results stay visible on error.

**Store** `lib/stores/code.svelte.ts`:

```ts
{
  expanded: Set<string>,
  children: Map<string, Entry[]>,
  selectedPath: string | null,
  fileSymbols: Map<string, Symbol[]>,
  search: { q: string, results: Match[], loading: boolean, epoch: number },
  diagnostics: { files: …, loading: boolean, error: string | null, lastRefreshAt: number | null },
}
```

**No polling on the Code tab** — everything is on-demand. Older in-flight searches are discarded via a `searchEpoch` compare-and-set.

### 5.5 Polling primitive change

In the shared poller helper: `since = response.max_seq ?? since` (was `||`). One-line change, one unit test.

## 6. Data flow & polling

### 6.1 Polling topology

| Poll loop | View(s) | Cadence | Cursor | Pauses when |
|---|---|---|---|---|
| `config` (existing) | Overview, Stats, Code | 1 s | none | tab hidden |
| `executions` (existing) | Overview | 1 s | none | tab hidden |
| `logs` (existing) | Logs | 1 s | byte offset | tab hidden |
| `timeline` (new) | Overview, Stats | 1 s | `since_seq` | tab hidden OR user paused OR view ≠ Overview/Stats |
| `code` (new) | — | none | — | always (on-demand only) |

Timeline polls on Stats too so RateChart, DurationChart, and DrillDown stay current.

### 6.2 Timeline buffer is the frontend source of truth

`lib/stores/timeline.svelte.ts` owns a single in-memory list capped at 2000 records (mirroring backend). Consumers: `Timeline`, `RateChart`, `DurationChart`, `DrillDownPanel`. For tools whose history has scrolled out of the 2000-record window, aggregated `/get_tool_stats` continues to drive the pies/bars.

### 6.3 Request lifecycles

**Tool call → record.** Synchronous, on the agent thread. Lock held for microseconds. Errors in `_record_tool_call_safely` are caught, logged, and dropped.

**Timeline poll.** `GET /get_tool_call_timeline?since_seq=N&tool=T&limit=200`. Server: lock-protected scan, filter, slice. Client: merge into buffer, cap at 2000, advance cursor with `??`. On long pause / resume, the next response returns the tail and we accept the gap — a "(N calls while paused — view truncated)" hint appears in the Timeline header.

**Code tab.** Every action user-triggered. Cached in store on success; search uses an epoch counter to discard stale responses.

### 6.4 Backend concurrency

We add **no global LSP lock**. LSP requests already serialize at the language-server subprocess's stdin/stdout. Two consequences worth naming:

- Diagnostics blocks navigator + search while running. Hence the warning banner.
- Each `/code/*` route issues one LSP request and returns — no nested LSP calls, no new deadlock risk.

`ToolUsageStats`'s lock is independent of everything else, held only for record-buffer mutations.

### 6.5 Backpressure & sanity caps

- `_RECORD_BUFFER_SIZE = 2000` (ring) — bounded memory.
- `_INPUT_OUTPUT_PREVIEW_BYTES = 8 * 1024` per record. Worst-case buffer ≈ 32 MB.
- `/get_tool_call_timeline?limit=` capped server-side at 500.
- `/code/diagnostics_summary` per-file payload capped at 1 MB; `file_limit` capped at 2000.
- `/code/workspace_symbol_search?limit=` capped at 200.
- Frontend timeline buffer capped at 2000.

### 6.6 Visibility-aware polling

Single `document.visibilityState === 'visible'` gate in the shared poller. When hidden, `timeline` and `config` pause; on resume, they fire immediately, get the gap, and resume cadence.

## 7. Error handling

### 7.1 Backend

| Failure | HTTP | Notes |
|---|---|---|
| LS not initialized | 503 `{"error": "...", "code": "ls_not_ready"}` | Frontend retries on next tick |
| LS timeout | 504 `{"code": "ls_timeout"}` | Existing solidlsp timeout |
| LS responded with error | 502 `{"code": "ls_error"}` | Surface message to user |
| Path traversal / invalid | 400 | |
| Missing / unreadable file | 404 | |
| Unexpected | 500 `{"code": "internal"}` | No stack traces in body; log at ERROR |

`_record_tool_call_safely` is the one place that wraps `BaseException` and swallows — analytics must never break the agent. `TaskInfo.get_error_message()` returns `None` until `future.done()`; never raises.

### 7.2 Frontend

**Polling errors.**

- 503 `ls_not_ready` → inline "Language server starting…", retries on next tick, no toast.
- Network / 5xx → set `error`, retry with backoff 1 s → 2 s → 5 s (capped). Inline error in affected panel, tab stays up.
- 4xx → set `error`, stop polling for that resource.

**Timeline poll failure.** Buffer left intact; small banner *"Live updates paused — reconnecting…"* at the top of `Timeline.svelte`. Pause/resume still allows manual retry.

**Code tab.**

- `list_dir` fail → folder stays collapsed, inline `⚠ <message>`.
- `file_symbols` fail → middle pane error card with Retry.
- `workspace_symbol_search` fail → older successful results stay visible.
- `diagnostics_summary` fail → error card; previous results preserved below.

**Drill-down panel.** If `tool` no longer in `/get_tool_stats`, panel shows "No data for this tool" and a Close button.

**SummaryCards.** If `tool_stats_totals` is missing from `/get_config_overview` (older backend), cards render with em-dashes.

## 8. Testing

### 8.1 Backend (pytest)

**`tests/serena/test_analytics.py`** (new):

- `Entry.update_on_call` updates duration/error/last_called fields.
- `ToolCallRecord` truncation honors 8 KB cap; `*_truncated` flags set.
- Ring buffer drops oldest at capacity; `_seq` is monotonic, never reused.
- `get_records_since(since_seq=N)` returns only `seq > N`.
- `get_records_since(tool="X")` filters correctly.
- Two threads × 1000 calls each → contiguous seq, correct totals.

**`tests/serena/test_task_executor.py`** (extend):

- `started_at`/`finished_at` set in the right order around `set_result`.
- `get_duration_ms` to within tolerance.
- `get_error_message` returns exception string for failed; `None` for successful.
- **Race-fix regression test:** spawn 100 tasks, observe each via `add_done_callback`, assert `finished_at is not None` in every observation. This is the test that would have failed before the fix.

**`tests/serena/test_dashboard.py`** (extend):

- `/get_tool_call_timeline` shape; cursor; limit; tool filter.
- `/code/list_dir` path-traversal guard rejects `../`, absolute paths, symlinks outside root.
- `/code/file_symbols` 404 for missing file.
- `/code/workspace_symbol_search` shape; limit cap.
- `/code/diagnostics_summary` truncates large responses; `truncated` flag.
- All `/code/*` return 503 `ls_not_ready` when no LSP is initialized (mocked).

**Instrumentation integration test:** drive a fake successful tool through the agent → one `ToolCallRecord` with `duration_ms > 0`, `success: true`. Drive a failing tool → `success: false`, `error_message` populated.

### 8.2 Frontend (vitest)

- `lib/stores/timeline.svelte.ts`: poll merges, dedups on `seq`, respects buffer cap, advances cursor with `??`.
- `lib/stores/code.svelte.ts`: lazy-load cache; refresh invalidates only the requested key.
- `RateChart` spec builder: bucket alignment puts the current minute as bucket N, with N+1 total buckets (legacy bug regression).
- `DurationChart` spec builder: avg vs max datasets correctly mapped.
- `DrillDownPanel`: p95 against a fixed fixture of 100 records.
- `FilterDropdown`: kbd nav opens on applied value; Esc closes; Enter selects; substring filter applies.
- `SortSelector`-driven specs: changing sort key reorders all three pie specs and the duration chart consistently.

### 8.3 Playwright smoke test (one, end-to-end)

Using the emulated-tool-calls dashboard (per memory `run-dashboard-emulate-tool-calls.md`):

1. 4 SummaryCards render with non-empty values.
2. Timeline shows rows; expand one; see args/output.
3. Switch to Stats; change SortSelector; charts reorder.
4. Click a pie slice; DrillDownPanel opens with stats.
5. Switch to Code tab; expand a folder; click a file; see symbols.
6. Click Refresh in DiagnosticsPanel; warning banner appears; eventual result renders.

### 8.4 Out of scope for testing

- Build pipeline (existing CI contract handles asset regeneration).
- Actual LSP server correctness — mocked via a small fake `LanguageServerManager` in dashboard tests.

## 9. Manual verification before "done"

Run the emulator script, exercise every new control in the browser, watch for console errors. Type-check + tests pass + assets regenerated before claiming complete.

## 10. Implementation sequence

The plan should land in this order so each step is independently verifiable:

1. **Backend instrumentation** — `Entry` extension, `ToolCallRecord`, `ToolUsageStats` ring buffer, `_record_tool_call_safely` wrap, `TaskInfo` enrichments, race fix. Unblocks all UI.
2. **Backend Tier 2 routes** — `/get_tool_call_timeline`, `/get_config_overview` extension.
3. **Frontend Tier 2** — `SummaryCards`, `FilterDropdown`, `Timeline` + `TimelineRow`, `timeline` store, polling-primitive `??` fix.
4. **Frontend Tier 3 + Stats** — `SortSelector`, `DurationChart`, `RateChart`, `DrillDownPanel`.
5. **Backend Tier 4 routes** — `/code/list_dir`, `/code/file_symbols`, `/code/workspace_symbol_search`, `/code/diagnostics_summary` + `dashboard_code.py`.
6. **Frontend Tier 4** — Code tab, `code` store, all four Code components.
7. **Final pass** — Playwright smoke, asset regeneration, manual emulator verification.
