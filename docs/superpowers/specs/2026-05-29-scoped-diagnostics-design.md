# Scoped Diagnostics for a Selected File/Directory — Design

**Date:** 2026-05-29
**Branch:** dashboard_v2
**Status:** Approved (pending spec review)

## Problem

The Code tab can currently run diagnostics only over the **whole project**. The
backend route `GET /code/diagnostics_summary` walks every non-ignored file under
the project root and returns published LSP diagnostics; `DiagnosticsPanel.svelte`
renders them behind a single project-wide **Refresh** button plus severity-filter
chips.

There is no way to ask "what are the problems in *this* file?" or "*this*
directory?". For a large project the project-wide walk is slow (30s wall-clock
budget, file-count cap) and overkill when the user only cares about one path.

## Goal

Let the user run diagnostics scoped to:

- a **selected file** — fresh, accurate, pull-based (`textDocument/diagnostic`),
- a **selected directory subtree** — walked like the project scan but rooted at
  that directory, published diagnostics,
- the **whole project** — unchanged from today.

Triggerable from two places: a **scope selector inside DiagnosticsPanel** and a
**"Run diagnostics" action on file/directory rows in the FileTree**.

## Non-Goals (YAGNI)

- Per-symbol diagnostics in the symbol tree (the `GetDiagnosticsForSymbolTool`
  MCP path) — not surfaced in the dashboard here.
- Diagnostic count badges decorating tree nodes.
- Click-a-diagnostic-to-jump — there is no code editor in the dashboard.
- Caching diagnostics results per scope — each Refresh recomputes.
- A right-click context menu in the tree (no context-menu infra exists yet).

## Constraints

- **Frozen HTTP contract** (`dashboard/CLAUDE.md`): never change existing
  endpoint names, request/response shapes, ports, or the host-header check.
  Therefore we **extend** `/code/diagnostics_summary` with an *optional* query
  param and keep its response shape identical — additive only.
- **Build-output contract:** after any source change, `npm run build` and commit
  the regenerated `src/serena/resources/dashboard/` (CI fails if stale).
- **Frontend architecture rules:** no `fetch` in components (go through
  `lib/api/`); `$state` only in `*.svelte.ts` stores exposed via getters +
  action methods; colors from `tokens.css`; compose `common/` primitives.

## Architecture

Three layers, mirroring the existing project-wide path:

```
FileTree row action ─┐
                     ├─> code store (diagScope + refreshDiagnostics) ─> endpoints.fetchCodeDiagnosticsSummary(file_limit, path?)
DiagnosticsPanel ────┘                                                          │
  scope selector + Refresh                                                      v
                                                       GET /code/diagnostics_summary[?path=…]
                                                                                │
                                          ┌─────────────────────────────────────┤
                                  path omitted/"."          path is dir            path is file
                                  project walk (published)  subtree walk (published) single-file (pull)
                                                                                │
                                                       Response { files, truncated }  (shape unchanged)
```

### Component / unit boundaries

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `_collect_candidate_files(root_real, walk_root, ignore, file_limit)` | os.walk rooted at `walk_root`, gitignore + dotfile filtering, cap at `file_limit`; returns `(rel_paths, truncated)` | `GitignoreParser`, `os.walk` |
| `_diagnostics_for_file(ls, rel, use_pull)` | Fetch + convert one file's diagnostics to `_FileDiagnostics`, applying per-message/per-file byte caps; returns `(_FileDiagnostics \| None, truncated)` | `ls.request_*_diagnostics`, `_Diagnostic` |
| `code_diagnostics_summary()` route | Resolve `path`, dispatch to project/dir/file mode, assemble `_ResponseDiagnosticsSummary` under the wall-clock budget | the two helpers above, `resolve_project_path` |
| `endpoints.fetchCodeDiagnosticsSummary` | Build URL with optional `path` | `client.getJson` |
| `code` store diag fields | Hold `diagScope`, `diagLastScope`, drive `refreshDiagnostics`, expose `runDiagnosticsForPath` | endpoints |
| `DiagnosticsPanel.svelte` | Scope selector + scope-aware labels/empty/truncated text + existing chips/refresh | `code` store |
| `FileTree.svelte` row action | Hover-revealed "Run diagnostics" button → `runDiagnosticsForPath` | `code` store |

## Backend Detail (`src/serena/dashboard_code.py`)

`code_diagnostics_summary()` gains an optional `path` arg:

```python
path = request.args.get("path", default=None, type=str)
file_limit = max(1, min(request.args.get("file_limit", default=1000, type=int), _FILE_LIMIT_CAP))
root = _get_project_root(dashboard_api)            # 503 no_project if None
ls = _get_first_language_server(dashboard_api)     # 503 ls_not_ready if None

if path and path != ".":
    try:
        resolved = resolve_project_path(root, path)    # ValueError->400, FileNotFoundError->404
    except ValueError as e:
        return _err(400, str(e))
    except FileNotFoundError:
        return _err(404, "path not found")
    if os.path.isfile(resolved):
        mode = "file"
    elif os.path.isdir(resolved):
        mode = "dir"
    else:
        return _err(400, "path is neither file nor directory")
else:
    resolved, mode = root_real, "project"
```

- **file mode:** `candidate_paths = [rel_of(resolved)]`; `use_pull = True`
  (`ls.request_text_document_diagnostics(rel)` — opens the file, falls back to
  published internally if the server lacks pull support). Skip the wall-clock
  budget (single file).
- **dir mode:** `candidate_paths, truncated = _collect_candidate_files(root_real,
  walk_root=resolved, ignore, file_limit)`; `use_pull = False` (published).
- **project mode:** same collection with `walk_root = root_real`; `use_pull =
  False`. Byte-for-byte the current behavior.

The per-file loop, wall-clock deadline (`_DIAGNOSTICS_WALL_CLOCK_BUDGET_S`),
per-message cap (`_DIAGNOSTICS_PER_MESSAGE_CAP`), and per-file byte cap
(`_DIAGNOSTICS_PER_FILE_BYTE_CAP`) are preserved, moved into / shared via the two
helpers. Response remains `_ResponseDiagnosticsSummary(files=…, truncated=…)`.

**Improvement folded in (#1):** `code_diagnostics_summary()` also reads an
optional `min_severity` query param (int, default 4 = include all). It is passed
through to both `request_text_document_diagnostics(..., min_severity=…)` and the
published-diagnostics filter, so a future "errors+warnings only" toggle needs no
backend change. Default behavior is unchanged.

## Frontend Detail

### `lib/api/endpoints.ts`

```ts
export const fetchCodeDiagnosticsSummary = (
  file_limit = 1000,
  path?: string,
  min_severity?: number,
) => {
  const qs = new URLSearchParams({ file_limit: String(file_limit) });
  if (path) qs.set('path', path);
  if (min_severity !== undefined) qs.set('min_severity', String(min_severity));
  return getJson<ResponseDiagnosticsSummary>(`/code/diagnostics_summary?${qs}`);
};
```

Response shape (`ResponseDiagnosticsSummary` in `types.ts`) is unchanged.

### `lib/stores/code.svelte.ts`

New FE-only type and state:

```ts
type DiagScope = { kind: 'project' | 'file' | 'directory'; path: string | null };

let diagScope = $state<DiagScope>({ kind: 'project', path: null });
let diagLastScope = $state<DiagScope | null>(null);   // scope the visible results belong to
```

Getters `diag_scope`, `diag_last_scope`; actions:

- `setDiagScope(scope: DiagScope)` — updates target only (does not fetch).
- `refreshDiagnostics(file_limit = 1000)` — reads `diagScope`, passes
  `scope.path` when `kind !== 'project'`, sets `diagLastScope = diagScope` on
  success. Existing §7.2 behavior preserved: on error, old results stay visible.
- `runDiagnosticsForPath(path: string, kind: 'file' | 'directory')` — sets
  `diagScope`, `middlePane = 'diagnostics'`, then `void refreshDiagnostics()`
  (explicit "do it now" verb).

### `components/code/DiagnosticsPanel.svelte`

- A scope-selector row above the severity chips: segmented control with
  **Project · File · Directory**. File and Directory options derive their target
  from `code.selected_path` / its parent directory and are **disabled** (greyed,
  with explanatory `title`) when no applicable selection exists. Choosing an
  option calls `code.setDiagScope(...)`.
- Header shows the active scope path, e.g. `Diagnostics — src/serena/dashboard_code.py`.
- The existing **Refresh** button runs the currently selected scope.
- **Slow warning** is hidden in `file` mode (single file is cheap), shown for
  `directory`/`project`.
- **Truncated banner** wording keys off `diag_last_scope`: "directory has more"
  vs "project has more".
- **Improvement folded in (#2):** scope-aware empty state — when a refresh
  returns zero files, show `No diagnostics in <scope path>.` (or `…in this
  project.`) instead of the generic "Click Refresh to compute diagnostics."
  The pre-first-refresh prompt remains "Click Refresh…".

### `components/code/FileTree.svelte`

- Add a hover-revealed **"Run diagnostics"** icon button (lucide `Stethoscope`)
  to both `dir` and `file` rows, right-aligned in the slot currently used by
  `.warn`. It is a separate `<button>` (the existing row is itself a button, so
  the action button is a sibling within the `<li>`, not nested inside the row
  button — avoids invalid nested-button HTML).
- Click handler calls
  `code.runDiagnosticsForPath(fullPath, entry.kind === 'dir' ? 'directory' : 'file')`
  and `stopPropagation()` so it does not also select/expand the row.
- Accessible: `aria-label="Run diagnostics on <name>"`, visible on row hover and
  on keyboard focus.

## Data Flow Example (file-tree action on a file)

1. User hovers `src/foo.py`, clicks the stethoscope button.
2. `runDiagnosticsForPath('src/foo.py', 'file')` → sets
   `diagScope = {kind:'file', path:'src/foo.py'}`, `middlePane='diagnostics'`,
   calls `refreshDiagnostics()`.
3. `fetchCodeDiagnosticsSummary(1000, 'src/foo.py')` → `GET
   /code/diagnostics_summary?file_limit=1000&path=src%2Ffoo.py`.
4. Backend resolves to a file → pull diagnostics for that one file → `{files,
   truncated}`.
5. Store sets `diagFiles`, `diagLastScope`; panel re-renders, header reads
   `Diagnostics — src/foo.py`.

## Error Handling

Reuses the established two-channel pattern. Non-2xx (`no_project` 503,
`ls_not_ready` 503, bad path 400, missing 404) throws `ApiError`, caught in
`refreshDiagnostics`, surfaced via `diag_error` and the panel's existing error
card. Per-file LSP failures are swallowed server-side (logged at debug) so one
broken file doesn't sink the batch — unchanged from today.

## Testing

**Backend (pytest):**
- `path` omitted ⇒ identical to current project-wide behavior.
- file `path` ⇒ result contains only that file; pull path exercised.
- directory `path` ⇒ only files under that subtree; a diagnostic in a sibling
  directory is excluded.
- traversal (`../`), absolute path, NUL ⇒ 400; nonexistent ⇒ 404.
- no active project ⇒ 503 `no_project`; no LS ⇒ 503 `ls_not_ready`.
- `min_severity` filters as expected.

**Frontend (Vitest):**
- store: `refreshDiagnostics` sends `path` for file/dir scopes, omits it for
  project; `runDiagnosticsForPath` sets scope + pane + triggers fetch;
  `diagLastScope` tracks the resolved scope.
- endpoint: URL building with/without `path`/`min_severity`.
- `DiagnosticsPanel`: renders scope selector; file/dir options disabled with no
  selection; scope-aware empty + truncated text.
- `FileTree`: action button calls `runDiagnosticsForPath` with correct kind and
  does **not** trigger select/expand (stopPropagation).

**Build/CI:** `npm run format`, `npm run check`, `npm test`, `npm run build`,
stage **all** changes incl. regenerated bundle.

## Rollout / Risk

- Purely additive backend param + new FE affordances; no existing call site
  changes. Low risk to current behavior.
- Largest unknown: pull diagnostics latency for a single large file on slow
  servers — mitigated because it's one file and the existing per-request
  handling already tolerates timeouts/fallbacks.
