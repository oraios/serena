# Scoped Diagnostics for a Selected File/Directory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the dashboard Code tab run LSP diagnostics scoped to a selected file (fresh/pull-based), a selected directory subtree (walked/published), or the whole project (unchanged), triggerable from both the DiagnosticsPanel and the FileTree.

**Architecture:** Extend the existing `GET /code/diagnostics_summary` route with optional `path` + `min_severity` query params (additive — response shape unchanged, frozen-contract safe). A file path uses pull diagnostics; a directory walks its subtree; omitted/`.` keeps today's project walk. The frontend `code` store gains a `diagScope`, the `DiagnosticsPanel` gains a scope selector, and `FileTree` rows gain a hover "Run diagnostics" button.

**Tech Stack:** Backend Flask + Python (`src/serena/dashboard_code.py`), pytest. Frontend Svelte 5 runes + TypeScript + Vite, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-05-29-scoped-diagnostics-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/serena/dashboard_code.py` | Modify | Extract `_collect_candidate_files` + `_diagnostics_for_file` helpers; rewrite `code_diagnostics_summary()` to accept `path`/`min_severity` and dispatch file/dir/project modes |
| `test/serena/test_dashboard_code.py` | Modify | Extend `_FakeLS` with pull-diagnostics; add scoped-diagnostics tests |
| `dashboard/src/lib/api/endpoints.ts` | Modify | `fetchCodeDiagnosticsSummary(file_limit, path?, min_severity?)` |
| `dashboard/src/lib/stores/code.svelte.ts` | Modify | `diagScope`/`diagLastScope` state, `setDiagScope`, `runDiagnosticsForPath`, scope-aware `refreshDiagnostics` |
| `dashboard/src/components/code/DiagnosticsPanel.svelte` | Modify | Scope selector + scope-aware header/empty/truncated text; hide slow-warning in file mode |
| `dashboard/src/components/code/FileTree.svelte` | Modify | Hover-revealed "Run diagnostics" button on file/dir rows |
| `dashboard/tests/code-store.test.ts` | Modify | Store tests for scope + runDiagnosticsForPath |
| `dashboard/tests/diagnostics-panel.test.ts` | Modify | Scope-selector render/disable + scope-aware text tests |
| `dashboard/tests/file-tree.test.ts` | Create | FileTree action-button test |

No `vite.config.ts` change: `/code/diagnostics_summary` is already in `API_ROUTES`; we only add query params.

---

## Task 1: Backend — scope `code_diagnostics_summary` to file/dir/project

**Files:**
- Modify: `src/serena/dashboard_code.py` (helpers near line 196; route at lines 388–491)
- Test: `test/serena/test_dashboard_code.py`

- [ ] **Step 1: Add pull-diagnostics to the test fake**

In `test/serena/test_dashboard_code.py`, the `_FakeLS` class (starts line 173) currently has only `request_published_text_document_diagnostics`. Extend its constructor and add a pull method. Replace the class's `__init__` and add the new method:

```python
class _FakeLS:
    def __init__(
        self,
        doc_symbols=None,
        raise_exc=None,
        ws_symbols=None,
        diagnostics_map=None,
        pull_diagnostics_map=None,
    ):
        self._doc_symbols = doc_symbols
        self._raise = raise_exc
        self._ws_symbols = ws_symbols
        self._diagnostics_map = diagnostics_map or {}
        self._pull_diagnostics_map = pull_diagnostics_map or {}

    def request_document_symbols(self, rel):
        if self._raise:
            raise self._raise
        return self._doc_symbols or []

    def request_workspace_symbol(self, query):
        if self._raise:
            raise self._raise
        return self._ws_symbols

    def request_published_text_document_diagnostics(self, rel, **_kw):
        if self._raise:
            raise self._raise
        return self._diagnostics_map.get(rel)

    def request_text_document_diagnostics(self, rel, **_kw):
        if self._raise:
            raise self._raise
        return self._pull_diagnostics_map.get(rel)
```

- [ ] **Step 2: Write the failing tests**

Append to `test/serena/test_dashboard_code.py` (after the existing diagnostics tests, end of file):

```python
# -----------------------------------------------------------------------------
# Scoped diagnostics — path = file (pull) / directory (subtree) / project
# -----------------------------------------------------------------------------


def test_diagnostics_summary_file_scope_uses_pull(make_dashboard_with_project):
    diag = {
        "range": {"start": {"line": 2, "character": 1}, "end": {"line": 2, "character": 4}},
        "severity": 1,
        "message": "pull-only diag",
        "source": "pyright",
    }
    # Published map is empty; only the pull map has the diagnostic. If the file
    # scope returns it, the pull path was used.
    mgr = _FakeManager(ls=_FakeLS(pull_diagnostics_map={"a.py": [diag]}))
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "a.py").write_text("x=1\n")
    r = client.get("/code/diagnostics_summary?path=a.py")
    assert r.status_code == 200
    body = r.get_json()
    files = {f["path"]: f for f in body["files"]}
    assert "a.py" in files
    assert files["a.py"]["diagnostics"][0]["message"] == "pull-only diag"
    assert files["a.py"]["diagnostics"][0]["severity"] == "error"


def test_diagnostics_summary_directory_scope_limits_to_subtree(make_dashboard_with_project):
    diag = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 2,
        "message": "w",
        "source": "x",
    }
    mgr = _FakeManager(
        ls=_FakeLS(diagnostics_map={"pkg/inside.py": [diag], "outside.py": [diag]})
    )
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "pkg").mkdir()
    (root / "pkg" / "inside.py").write_text("x=1\n")
    (root / "outside.py").write_text("x=1\n")
    r = client.get("/code/diagnostics_summary?path=pkg")
    assert r.status_code == 200
    paths = {f["path"] for f in r.get_json()["files"]}
    assert "pkg/inside.py" in paths
    assert "outside.py" not in paths


def test_diagnostics_summary_path_traversal_rejected(make_dashboard_with_project):
    mgr = _FakeManager(ls=_FakeLS())
    _, client, _root = make_dashboard_with_project(ls_manager=mgr)
    r = client.get("/code/diagnostics_summary?path=../etc")
    assert r.status_code == 400


def test_diagnostics_summary_missing_path_404(make_dashboard_with_project):
    mgr = _FakeManager(ls=_FakeLS())
    _, client, _root = make_dashboard_with_project(ls_manager=mgr)
    r = client.get("/code/diagnostics_summary?path=nope.py")
    assert r.status_code == 404


def test_diagnostics_summary_min_severity_filters_published(make_dashboard_with_project):
    warn = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 2,
        "message": "just a warning",
        "source": "x",
    }
    mgr = _FakeManager(ls=_FakeLS(diagnostics_map={"a.py": [warn]}))
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "a.py").write_text("x=1\n")
    # min_severity=1 => errors only => the warning is filtered out => no files.
    r = client.get("/code/diagnostics_summary?min_severity=1")
    assert r.status_code == 200
    assert r.get_json()["files"] == []
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest test/serena/test_dashboard_code.py -k "scope or traversal_rejected or missing_path_404 or min_severity_filters" -v`
Expected: FAILs — `path=a.py` currently returns the whole project (published, empty pull) so `pull-only diag` is absent; directory scope ignores `path`; min_severity unsupported.

- [ ] **Step 4: Extract the collection + per-file helpers**

In `src/serena/dashboard_code.py`, add these two module-level helpers immediately after `_convert_workspace_match` (i.e. before the `# Route registration` banner near line 265):

```python
def _collect_candidate_files(
    root_real: str, walk_root: str, ignore: Any, file_limit: int
) -> tuple[list[str], bool]:
    """Walk `walk_root`, returning (paths-relative-to-root_real, truncated).

    Skips dotfile dirs/files and gitignored paths; caps the count at file_limit.
    Paths are returned relative to the *project root* (root_real) so they can be
    handed to the language server, even when walking a subdirectory.
    """
    candidate_paths: list[str] = []
    truncated = False
    for dirpath, dirnames, filenames in os.walk(walk_root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if ignore is not None:
            kept_dirs: list[str] = []
            for d in dirnames:
                rel_d = os.path.relpath(os.path.join(dirpath, d), root_real)
                if not ignore.should_ignore(rel_d):
                    kept_dirs.append(d)
            dirnames[:] = kept_dirs
        for fn in filenames:
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root_real)
            if ignore is not None and ignore.should_ignore(rel):
                continue
            if len(candidate_paths) >= file_limit:
                truncated = True
                break
            candidate_paths.append(rel)
        if truncated:
            dirnames[:] = []
            continue
    return candidate_paths, truncated


def _diagnostics_for_file(
    ls: Any, rel: str, use_pull: bool, min_severity: int
) -> tuple["_FileDiagnostics | None", bool]:
    """Fetch + convert one file's diagnostics.

    Returns (file_diagnostics-or-None, truncated). Per-file LSP errors are
    swallowed (logged at debug) and yield (None, False) so one bad file does not
    sink the batch. `use_pull` selects the fresh pull request over published.
    `min_severity` keeps diagnostics whose numeric severity is <= min_severity
    (1=Error … 4=Hint; default 4 = keep all).
    """
    try:
        if use_pull:
            raw = ls.request_text_document_diagnostics(rel, min_severity=min_severity)
        else:
            raw = ls.request_published_text_document_diagnostics(rel)
    except TimeoutError:
        return None, False
    except Exception as e:  # noqa: BLE001
        log.debug("Diagnostics failed for %s: %s", rel, e)
        return None, False
    if not raw:
        return None, False

    diags: list[_Diagnostic] = []
    truncated = False
    byte_estimate = 0
    _PER_DIAG_JSON_OVERHEAD = 80
    for d in raw:
        sev_int = _maybe(d, "severity")
        try:
            sev_num = int(sev_int) if sev_int is not None else 3
        except (TypeError, ValueError):
            sev_num = 3
        if sev_num > min_severity:
            continue  # less severe than the floor — skip
        sev = _LSP_SEVERITY.get(sev_num, "info")
        rng = _maybe(d, "range") or {}
        rng_start = _maybe(rng, "start") or {}
        try:
            line = int(_maybe(rng_start, "line") or 0)
            col = int(_maybe(rng_start, "character") or 0)
        except (TypeError, ValueError):
            line, col = 0, 0
        msg = _maybe(d, "message") or ""
        if not isinstance(msg, str):
            msg = str(msg)
        if len(msg) > _DIAGNOSTICS_PER_MESSAGE_CAP:
            msg = msg[:_DIAGNOSTICS_PER_MESSAGE_CAP]
            truncated = True
        source = _maybe(d, "source")
        if source is not None and not isinstance(source, str):
            source = str(source)
        diag_size = len(msg.encode("utf-8")) + (len(source.encode("utf-8")) if source else 0) + _PER_DIAG_JSON_OVERHEAD
        if byte_estimate + diag_size > _DIAGNOSTICS_PER_FILE_BYTE_CAP:
            truncated = True
            break
        diags.append(_Diagnostic(severity=sev, message=msg, line=line, column=col, source=source))
        byte_estimate += diag_size
    if not diags:
        return None, False
    return _FileDiagnostics(path=rel, diagnostics=diags), truncated
```

- [ ] **Step 5: Rewrite the route to use the helpers + scope params**

In `src/serena/dashboard_code.py`, replace the entire body of `code_diagnostics_summary()` (the `@app.route("/code/diagnostics_summary", ...)` block, currently lines 388–491) with:

```python
    @app.route("/code/diagnostics_summary", methods=["GET"])
    def code_diagnostics_summary() -> tuple[dict[str, Any], int] | dict[str, Any]:
        file_limit = request.args.get("file_limit", default=1000, type=int)
        file_limit = max(1, min(file_limit, _FILE_LIMIT_CAP))
        min_severity = request.args.get("min_severity", default=4, type=int)
        min_severity = max(1, min(min_severity, 4))
        path = request.args.get("path", default=None, type=str)

        root = _get_project_root(dashboard_api)
        if root is None:
            return _err(503, "No active project", "no_project")
        ls = _get_first_language_server(dashboard_api)
        if ls is None:
            return _err(503, "Language server not ready", "ls_not_ready")

        root_real = str(Path(root).resolve())

        # Resolve the requested scope.
        if path and path not in ("", "."):
            try:
                resolved = resolve_project_path(root, path)
            except ValueError as e:
                return _err(400, str(e))
            except FileNotFoundError:
                return _err(404, "path not found")
            if os.path.isfile(resolved):
                mode = "file"
            elif os.path.isdir(resolved):
                mode = "dir"
            else:
                return _err(400, "path is neither a file nor a directory")
        else:
            resolved, mode = root_real, "project"

        from serena.util.file_system import GitignoreParser

        try:
            ignore: GitignoreParser | None = GitignoreParser(root)
        except Exception:
            ignore = None

        truncated = False
        if mode == "file":
            candidate_paths = [os.path.relpath(resolved, root_real)]
            use_pull = True
        else:  # "dir" or "project"
            candidate_paths, truncated = _collect_candidate_files(root_real, resolved, ignore, file_limit)
            use_pull = False

        files: list[_FileDiagnostics] = []
        deadline = time.monotonic() + _DIAGNOSTICS_WALL_CLOCK_BUDGET_S
        for rel in candidate_paths:
            if mode != "file" and time.monotonic() >= deadline:
                truncated = True
                break
            file_diags, trunc = _diagnostics_for_file(ls, rel, use_pull, min_severity)
            if trunc:
                truncated = True
            if file_diags is not None:
                files.append(file_diags)

        return _ResponseDiagnosticsSummary(files=files, truncated=truncated).model_dump()
```

- [ ] **Step 6: Run the full dashboard_code test module**

Run: `uv run pytest test/serena/test_dashboard_code.py -v`
Expected: PASS — the new scoped tests pass AND the pre-existing `test_code_diagnostics_summary_happy_path` / `_truncates_long_message` / `_503_*` still pass (project mode unchanged; default `min_severity=4` keeps all severities).

- [ ] **Step 7: Commit**

```bash
git add src/serena/dashboard_code.py test/serena/test_dashboard_code.py
git commit -m "feat(dashboard): scope /code/diagnostics_summary to file/dir via optional path

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Frontend store — diagScope + runDiagnosticsForPath

**Files:**
- Modify: `dashboard/src/lib/api/endpoints.ts:82-83`
- Modify: `dashboard/src/lib/stores/code.svelte.ts`
- Test: `dashboard/tests/code-store.test.ts`

- [ ] **Step 1: Write the failing store tests**

Append to `dashboard/tests/code-store.test.ts` (after the last `describe` block, before EOF):

```ts
describe('code store — diagnostics scope', () => {
  it('refreshDiagnostics omits path for project scope', async () => {
    const urls: string[] = [];
    stubFetchRoutes({
      '/code/diagnostics_summary': (url: string) => {
        urls.push(url);
        return { files: [], truncated: false };
      },
    });
    const store = createCodeStore();
    await store.refreshDiagnostics(1000);
    expect(urls[0]).not.toContain('path=');
    expect(store.diag_last_scope?.kind).toBe('project');
  });

  it('refreshDiagnostics sends path for a file scope', async () => {
    const urls: string[] = [];
    stubFetchRoutes({
      '/code/diagnostics_summary': (url: string) => {
        urls.push(url);
        return { files: [], truncated: false };
      },
    });
    const store = createCodeStore();
    store.setDiagScope({ kind: 'file', path: 'src/a.py' });
    await store.refreshDiagnostics(1000);
    expect(urls[0]).toContain('path=src%2Fa.py');
    expect(store.diag_last_scope?.kind).toBe('file');
  });

  it('runDiagnosticsForPath sets scope, switches to the diagnostics pane, and fetches', async () => {
    const urls: string[] = [];
    stubFetchRoutes({
      '/code/diagnostics_summary': (url: string) => {
        urls.push(url);
        return { files: [], truncated: false };
      },
    });
    const store = createCodeStore();
    await store.runDiagnosticsForPath('src', 'directory');
    expect(store.middle_pane).toBe('diagnostics');
    expect(store.diag_scope).toEqual({ kind: 'directory', path: 'src' });
    expect(urls[0]).toContain('path=src');
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd dashboard && npx vitest run tests/code-store.test.ts -t "diagnostics scope"`
Expected: FAIL — `setDiagScope`, `diag_scope`, `diag_last_scope`, `runDiagnosticsForPath` do not exist.

- [ ] **Step 3: Update the endpoint signature**

In `dashboard/src/lib/api/endpoints.ts`, replace the `fetchCodeDiagnosticsSummary` definition (lines 82–83):

```ts
export const fetchCodeDiagnosticsSummary = (file_limit = 1000, path?: string, min_severity?: number) => {
  const qs = new URLSearchParams({ file_limit: String(file_limit) });
  if (path) qs.set('path', path);
  if (min_severity !== undefined) qs.set('min_severity', String(min_severity));
  return getJson<ResponseDiagnosticsSummary>(`/code/diagnostics_summary?${qs}`);
};
```

- [ ] **Step 4: Add scope state + actions to the store**

In `dashboard/src/lib/stores/code.svelte.ts`:

(a) Add the type just below the imports (after line 14, the `SvelteSet` import):

```ts
export type DiagScope = { kind: 'project' | 'file' | 'directory'; path: string | null };
```

(b) Add state next to the other `diag*` declarations (after line 35, `diagLastRefreshAt`):

```ts
  let diagScope = $state<DiagScope>({ kind: 'project', path: null });
  let diagLastScope = $state<DiagScope | null>(null);
```

(c) Add getters next to the other `diag_*` getters (after the `diag_last_refresh_at` getter, around line 106):

```ts
    get diag_scope() {
      return diagScope;
    },
    get diag_last_scope() {
      return diagLastScope;
    },
```

(d) Add `setDiagScope` next to `setMiddlePane` (after line 119):

```ts
    setDiagScope(scope: DiagScope) {
      diagScope = scope;
    },
```

(e) Replace the existing `refreshDiagnostics` method (lines 236–250) with the scope-aware version, and add `runDiagnosticsForPath` right after it:

```ts
    async refreshDiagnostics(file_limit = 1000) {
      const scope = diagScope;
      diagLoading = true;
      diagError = null;
      try {
        const resp = await fetchCodeDiagnosticsSummary(
          file_limit,
          scope.kind === 'project' ? undefined : (scope.path ?? undefined),
        );
        diagFiles = resp.files;
        diagTruncated = resp.truncated;
        diagLastRefreshAt = Date.now();
        diagLastScope = scope;
      } catch (e) {
        diagError = e instanceof Error ? e.message : String(e);
        // Previous diagFiles stay visible per spec §7.2.
      } finally {
        diagLoading = false;
      }
    },
    async runDiagnosticsForPath(path: string, kind: 'file' | 'directory') {
      diagScope = { kind, path };
      middlePane = 'diagnostics';
      await this.refreshDiagnostics();
    },
```

- [ ] **Step 5: Run the store tests**

Run: `cd dashboard && npx vitest run tests/code-store.test.ts`
Expected: PASS (new scope tests + all pre-existing code-store tests).

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/lib/api/endpoints.ts dashboard/src/lib/stores/code.svelte.ts dashboard/tests/code-store.test.ts
git commit -m "feat(dashboard): code store diagnostics scope + runDiagnosticsForPath

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Frontend — DiagnosticsPanel scope selector

**Files:**
- Modify: `dashboard/src/components/code/DiagnosticsPanel.svelte`
- Test: `dashboard/tests/diagnostics-panel.test.ts`

- [ ] **Step 1: Write the failing panel tests**

Append to `dashboard/tests/diagnostics-panel.test.ts` (inside the file, after the existing `describe` block):

```ts
describe('DiagnosticsPanel — scope selector', () => {
  beforeEach(() => {
    code.setDiagScope({ kind: 'project', path: null });
    code.selectPath(null);
  });

  it('disables File/Directory scope when nothing is selected', () => {
    const { getByRole } = render(DiagnosticsPanel);
    expect((getByRole('button', { name: /^File$/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((getByRole('button', { name: /^Directory$/i }) as HTMLButtonElement).disabled).toBe(true);
    expect((getByRole('button', { name: /^Project$/i }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('enables File/Directory once a file is selected and sets scope on click', async () => {
    code.file_symbols['src/a.py'] = [] as never; // avoid a symbols fetch on selectPath
    code.selectPath('src/a.py');
    const { getByRole } = render(DiagnosticsPanel);
    const fileBtn = getByRole('button', { name: /^File$/i }) as HTMLButtonElement;
    expect(fileBtn.disabled).toBe(false);
    await fireEvent.click(fileBtn);
    expect(code.diag_scope).toEqual({ kind: 'file', path: 'src/a.py' });
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd dashboard && npx vitest run tests/diagnostics-panel.test.ts -t "scope selector"`
Expected: FAIL — no Project/File/Directory buttons exist yet.

- [ ] **Step 3: Add the scope selector to the panel**

In `dashboard/src/components/code/DiagnosticsPanel.svelte`:

(a) Extend the `<script>` block. After the existing `const counts = $derived(code.diag_counts);` line, add scope derivations and a sync effect:

```ts
  const selectedFile = $derived(code.selected_path);
  function parentDir(p: string): string {
    const i = p.lastIndexOf('/');
    return i === -1 ? '.' : p.slice(0, i);
  }
  const selectedDir = $derived(selectedFile ? parentDir(selectedFile) : null);
  const scope = $derived(code.diag_scope);

  // Keep an active file/dir scope tracking the current tree selection so the
  // panel target follows what the user clicks in the file tree.
  $effect(() => {
    const sel = code.selected_path;
    const s = code.diag_scope;
    if (s.kind === 'file' && sel && sel !== s.path) {
      code.setDiagScope({ kind: 'file', path: sel });
    } else if (s.kind === 'directory' && sel) {
      const d = parentDir(sel);
      if (d !== s.path) code.setDiagScope({ kind: 'directory', path: d });
    }
  });

  const scopeLabel = $derived(
    scope.kind === 'project'
      ? 'Diagnostics'
      : `Diagnostics — ${scope.path ?? '.'}${scope.kind === 'directory' ? '/' : ''}`,
  );

  function pickScope(kind: 'project' | 'file' | 'directory') {
    if (kind === 'project') code.setDiagScope({ kind: 'project', path: null });
    else if (kind === 'file' && selectedFile) code.setDiagScope({ kind: 'file', path: selectedFile });
    else if (kind === 'directory' && selectedDir)
      code.setDiagScope({ kind: 'directory', path: selectedDir });
  }
```

(b) Replace the `<h3>Diagnostics</h3>` in the header with the scope-aware label:

```svelte
    <h3>{scopeLabel}</h3>
```

(c) Add a scope-selector `<nav>` immediately after the closing `</header>` tag (before the `<aside class="slow-warning">`):

```svelte
  <nav class="scope" aria-label="Diagnostics scope">
    <button
      type="button"
      class="scope-btn"
      class:active={scope.kind === 'project'}
      onclick={() => pickScope('project')}>Project</button>
    <button
      type="button"
      class="scope-btn"
      class:active={scope.kind === 'file'}
      disabled={!selectedFile}
      title={selectedFile ? `Diagnose ${selectedFile}` : 'Select a file first'}
      onclick={() => pickScope('file')}>File</button>
    <button
      type="button"
      class="scope-btn"
      class:active={scope.kind === 'directory'}
      disabled={!selectedDir}
      title={selectedDir ? `Diagnose ${selectedDir}/` : 'Select a file first'}
      onclick={() => pickScope('directory')}>Directory</button>
  </nav>
```

(d) Wrap the existing slow-warning `<aside>` so it hides in file mode. Change the line `<aside class="slow-warning" role="note">…</aside>` block to:

```svelte
  {#if scope.kind !== 'file'}
    <aside class="slow-warning" role="note">
      <Icon icon={TriangleAlert} size={14} label="Slow" />
      <span>
        Computing diagnostics is slow and temporarily delays other LSP tools. Use only when needed.
      </span>
    </aside>
  {/if}
```

(e) Make the truncated + empty messages scope-aware. Replace the truncated block:

```svelte
  {#if code.diag_truncated && !code.diag_loading}
    <div class="warn">
      Showing first {code.diag_files.length} files;
      {code.diag_last_scope?.kind === 'directory' ? 'directory' : 'project'} has more.
    </div>
  {/if}
```

and replace the empty-state block:

```svelte
  {#if code.diag_files.length === 0 && !code.diag_loading && !code.diag_error}
    {#if code.diag_last_scope}
      <p class="empty">
        No diagnostics in {code.diag_last_scope.kind === 'project'
          ? 'this project'
          : (code.diag_last_scope.path ?? 'this project')}.
      </p>
    {:else}
      <p class="empty">Click Refresh to compute diagnostics.</p>
    {/if}
  {/if}
```

(f) Add CSS for the scope buttons inside the `<style>` block (after the `.chip.active` rule):

```css
  .scope {
    display: flex;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .scope-btn {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: var(--space-1) var(--space-2);
    color: var(--text-secondary);
    font-size: 0.8em;
    cursor: pointer;
  }
  .scope-btn.active {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-color: var(--accent);
    color: var(--text-primary);
  }
  .scope-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
```

- [ ] **Step 4: Run the panel tests**

Run: `cd dashboard && npx vitest run tests/diagnostics-panel.test.ts`
Expected: PASS (new scope-selector tests + the 2 pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/code/DiagnosticsPanel.svelte dashboard/tests/diagnostics-panel.test.ts
git commit -m "feat(dashboard): scope selector + scope-aware text in DiagnosticsPanel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Frontend — FileTree "Run diagnostics" action

**Files:**
- Modify: `dashboard/src/components/code/FileTree.svelte`
- Test: `dashboard/tests/file-tree.test.ts` (create)

- [ ] **Step 1: Write the failing FileTree test**

Create `dashboard/tests/file-tree.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/svelte';
import { stubFetchRoutes } from './helpers';
import FileTree from '../src/components/code/FileTree.svelte';
import { code } from '../src/lib/stores/code.svelte';

beforeEach(() => {
  code.setDiagScope({ kind: 'project', path: null });
  code.setMiddlePane('symbols');
});

describe('FileTree — run diagnostics action', () => {
  it('runs file-scoped diagnostics from a file row without selecting it', async () => {
    stubFetchRoutes({
      '/code/list_dir': () => ({ entries: [{ name: 'a.py', kind: 'file' }] }),
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    const btn = await findByLabelText(/Run diagnostics on a\.py/i);
    await fireEvent.click(btn);
    await waitFor(() => expect(code.diag_scope).toEqual({ kind: 'file', path: 'a.py' }));
    expect(code.middle_pane).toBe('diagnostics');
    // Clicking the action must NOT select the file row.
    expect(code.selected_path).toBeNull();
  });

  it('runs directory-scoped diagnostics from a dir row', async () => {
    stubFetchRoutes({
      '/code/list_dir': () => ({ entries: [{ name: 'src', kind: 'dir' }] }),
      '/code/diagnostics_summary': () => ({ files: [], truncated: false }),
    });
    const { findByLabelText } = render(FileTree, { rootPath: '.' });
    const btn = await findByLabelText(/Run diagnostics on src/i);
    await fireEvent.click(btn);
    await waitFor(() => expect(code.diag_scope).toEqual({ kind: 'directory', path: 'src' }));
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd dashboard && npx vitest run tests/file-tree.test.ts`
Expected: FAIL — no "Run diagnostics on …" button exists.

- [ ] **Step 3: Add the action button to the tree**

In `dashboard/src/components/code/FileTree.svelte`:

(a) Add `Stethoscope` to the lucide import (line 4):

```ts
  import { ChevronRight, ChevronDown, TriangleAlert, Stethoscope } from '@lucide/svelte';
```

(b) Replace the body of the `{#each children as entry …}` loop (the `<li>…</li>`, lines 37–69) with a version that wraps the row + action button and moves the dir-children render out of the row:

```svelte
      {#each children as entry (entry.name)}
        {@const fullPath = joinPath(path, entry.name)}
        <li>
          <div class="row-wrap">
            {#if entry.kind === 'dir'}
              <button
                type="button"
                class="row dir"
                onclick={() => code.toggleExpand(fullPath)}
                aria-expanded={code.expanded.has(fullPath)}
              >
                <span class="chev">
                  <Icon icon={code.expanded.has(fullPath) ? ChevronDown : ChevronRight} size={14} />
                </span>
                <span class="name">{entry.name}</span>
                {#if code.dir_errors[fullPath] !== undefined}
                  <span class="warn" title={code.dir_errors[fullPath]}>
                    <Icon icon={TriangleAlert} size={14} label="Error" />
                  </span>
                {/if}
              </button>
            {:else}
              <button
                type="button"
                class="row file"
                class:selected={code.selected_path === fullPath}
                onclick={() => code.selectPath(fullPath)}
              >
                <span class="chev" aria-hidden="true"></span>
                <span class="name">{entry.name}</span>
              </button>
            {/if}
            <button
              type="button"
              class="diag-action"
              aria-label={`Run diagnostics on ${entry.name}`}
              title={`Run diagnostics on ${entry.name}`}
              onclick={(e) => {
                e.stopPropagation();
                code.runDiagnosticsForPath(fullPath, entry.kind === 'dir' ? 'directory' : 'file');
              }}
            >
              <Icon icon={Stethoscope} size={13} />
            </button>
          </div>
          {#if entry.kind === 'dir' && code.expanded.has(fullPath)}
            {@render treeNode(fullPath, depth + 1)}
          {/if}
        </li>
      {/each}
```

(c) Add CSS to the `<style>` block (after the `.row.selected` rule):

```css
  .row-wrap {
    display: flex;
    align-items: center;
  }
  .row {
    flex: 1 1 auto;
    min-width: 0;
  }
  .diag-action {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    cursor: pointer;
    padding: var(--space-1);
    opacity: 0;
  }
  .row-wrap:hover .diag-action,
  .diag-action:focus-visible,
  .diag-action:focus {
    opacity: 1;
  }
  .diag-action:hover {
    color: var(--accent);
  }
```

- [ ] **Step 4: Run the FileTree tests**

Run: `cd dashboard && npx vitest run tests/file-tree.test.ts`
Expected: PASS — both file and directory actions set the scope/pane and the file action does not select the row.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/code/FileTree.svelte dashboard/tests/file-tree.test.ts
git commit -m "feat(dashboard): per-row Run diagnostics action in FileTree

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Verify, build the bundle, and commit the build output

**Files:**
- Modify: `src/serena/resources/dashboard/` (generated; CI-enforced)

- [ ] **Step 1: Frontend gates**

Run: `cd dashboard && npm run format && npm run check && npm test`
Expected: prettier writes/no-ops, `svelte-check` reports 0 errors, all Vitest suites pass.

- [ ] **Step 2: Backend gate**

Run: `uv run pytest test/serena/test_dashboard_code.py -q`
Expected: all pass.

- [ ] **Step 3: Build the bundle**

Run: `cd dashboard && npm run build`
Expected: regenerates `../src/serena/resources/dashboard/index.html` + `assets/` (hashed JS/CSS).

- [ ] **Step 4: Stage everything and commit the build output**

Per `dashboard/CLAUDE.md`, stage **all** changes (a partial stage can leave files prettier-dirty and fail CI):

```bash
git add -A
git commit -m "build(dashboard): regenerate bundle for scoped diagnostics

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Final sanity check**

Run: `git status`
Expected: clean working tree (nothing uncommitted), confirming the bundle is in sync.

---

## Self-Review Notes

- **Spec coverage:** backend file(pull)/dir(subtree)/project dispatch + caps (Task 1); optional `min_severity` threading, improvement #1 (Task 1, Steps 4–5 + test); endpoint param (Task 2); store scope + `runDiagnosticsForPath` (Task 2); panel scope selector + scope-aware header/empty (improvement #2)/truncated text + file-mode warning hide (Task 3); FileTree per-row action (Task 4); build-output contract (Task 5). All spec sections map to a task.
- **Type consistency:** `DiagScope` (`{kind, path}`) defined in Task 2 Step 4a and used identically in Tasks 2–4; `runDiagnosticsForPath(path, kind)`, `setDiagScope(scope)`, `diag_scope`, `diag_last_scope` names match across store/panel/tree/tests. Backend helpers `_collect_candidate_files(root_real, walk_root, ignore, file_limit)` and `_diagnostics_for_file(ls, rel, use_pull, min_severity)` are defined once (Task 1 Step 4) and called once (Step 5).
- **No placeholders:** every step shows full code and an exact command with expected output.
