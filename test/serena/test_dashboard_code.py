"""Tests for src/serena/dashboard_code.py — the /code/* endpoints."""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pytest

from serena.dashboard_code import LSPNotReady, resolve_project_path

# -----------------------------------------------------------------------------
# Task 19 — path resolve + LSPNotReady
# -----------------------------------------------------------------------------


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
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("bad")
    os.symlink(str(outside), str(root / "link.txt"))
    with pytest.raises(ValueError):
        resolve_project_path(str(root), "link.txt")


def test_resolve_project_path_rejects_missing_file(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    with pytest.raises(FileNotFoundError):
        resolve_project_path(str(root), "missing.py")


def test_lsp_not_ready_is_an_exception_type():
    assert issubclass(LSPNotReady, Exception)


# -----------------------------------------------------------------------------
# Shared fixtures / fakes
# -----------------------------------------------------------------------------


class _DummyMemLog:
    def get_log_messages(self, from_idx=0):
        return SimpleNamespace(messages=[], max_idx=-1)

    def clear_log_messages(self):
        pass


class _DummyAgent:
    version = "test-version"

    def __init__(self, root, ls_manager=None):
        self._project = SimpleNamespace(
            project_root=str(root),
            project_name="proj",
            project_config=SimpleNamespace(languages=[], encoding=None),
        )
        self._ls_manager = ls_manager
        self._all_tools: dict = {}
        self.serena_config = SimpleNamespace(projects=[])

    def register_config_changed_callback(self, callback):
        pass

    def get_active_project(self):
        return self._project

    def get_language_server_manager(self):
        return self._ls_manager

    def get_current_tasks(self):
        return []

    def execute_task(self, fn, *, logged=None, name=None):
        return fn()

    def get_context(self):
        return SimpleNamespace(name="test", description="", _yaml_path="/tmp/x")

    def get_active_modes(self):
        return []

    def get_active_tool_names(self):
        return []

    def tool_is_active(self, _name):
        return False

    def get_language_backend(self):
        return SimpleNamespace(is_jetbrains=lambda: False)


@pytest.fixture
def make_dashboard_with_project(tmp_path):
    from serena.dashboard import SerenaDashboardAPI

    def _factory(ls_manager=None):
        root = tmp_path / "proj"
        root.mkdir()
        agent = _DummyAgent(root, ls_manager=ls_manager)
        dashboard = SerenaDashboardAPI(
            memory_log_handler=_DummyMemLog(),
            tool_names=[],
            agent=agent,
            tool_usage_stats=None,
        )
        return dashboard, dashboard._app.test_client(), root

    return _factory


# -----------------------------------------------------------------------------
# Task 20 — /code/list_dir
# -----------------------------------------------------------------------------


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
    _, client, _root = make_dashboard_with_project()
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


# -----------------------------------------------------------------------------
# Task 21 — /code/file_symbols
# -----------------------------------------------------------------------------


class _FakeLS:
    def __init__(
        self,
        doc_symbols=None,
        raise_exc=None,
        ws_symbols=None,
        diagnostics_map=None,
        pull_diagnostics_map=None,
        ignored_paths=None,
    ):
        self._doc_symbols = doc_symbols
        self._raise = raise_exc
        self._ws_symbols = ws_symbols
        self._diagnostics_map = diagnostics_map or {}
        self._pull_diagnostics_map = pull_diagnostics_map or {}
        # Relative paths this server does NOT handle (unsupported file type),
        # mirroring SolidLanguageServer.is_ignored_path(ignore_unsupported_files=True).
        self._ignored_paths = set(ignored_paths or [])

    def is_ignored_path(self, rel, ignore_unsupported_files=True):
        return rel in self._ignored_paths

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


class _FakeManager:
    def __init__(self, ls=None):
        self._ls = ls

    def get_language_server(self, rel):
        if self._ls is None:
            raise ValueError("no LS")
        return self._ls

    def iter_language_servers(self):
        if self._ls:
            yield self._ls


def test_code_file_symbols_returns_document_symbols(make_dashboard_with_project):
    fake_syms = [
        {
            "name": "Foo",
            "kind": 5,
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 5, "character": 0}},
            "children": [
                {
                    "name": "bar",
                    "kind": 6,
                    "range": {"start": {"line": 1, "character": 4}, "end": {"line": 3, "character": 0}},
                    "children": [],
                }
            ],
        }
    ]
    mgr = _FakeManager(ls=_FakeLS(doc_symbols=fake_syms))
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "main.py").write_text("class Foo:\n    def bar(self): pass\n")
    r = client.get("/code/file_symbols?path=main.py")
    assert r.status_code == 200
    body = r.get_json()
    assert body["symbols"][0]["name"] == "Foo"
    assert body["symbols"][0]["kind"] == "Class"
    assert body["symbols"][0]["children"][0]["name"] == "bar"
    assert body["symbols"][0]["children"][0]["kind"] == "Method"


def test_code_file_symbols_503_when_no_ls(make_dashboard_with_project):
    _, client, root = make_dashboard_with_project()
    (root / "f.py").write_text("x=1")
    r = client.get("/code/file_symbols?path=f.py")
    assert r.status_code == 503
    assert r.get_json()["code"] == "ls_not_ready"


def test_code_file_symbols_404_for_missing(make_dashboard_with_project):
    _, client, _root = make_dashboard_with_project()
    r = client.get("/code/file_symbols?path=nope.py")
    assert r.status_code == 404


# -----------------------------------------------------------------------------
# Task 22 — /code/workspace_symbol_search
# -----------------------------------------------------------------------------


def test_code_workspace_symbol_search_slices_to_limit(make_dashboard_with_project, tmp_path):
    # Build 5 fake matches, request limit=2, assert 2 returned.
    matches = []
    for i in range(5):
        matches.append(
            {
                "name": f"foo{i}",
                "kind": 12,
                "location": {
                    "uri": "file:///nonexistent/main.py",
                    "range": {"start": {"line": i, "character": 0}, "end": {"line": i, "character": 1}},
                },
            }
        )
    mgr = _FakeManager(ls=_FakeLS(ws_symbols=matches))
    _, client, _root = make_dashboard_with_project(ls_manager=mgr)
    r = client.get("/code/workspace_symbol_search?q=foo&limit=2")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["matches"]) == 2
    assert body["matches"][0]["name"] == "foo0"
    assert body["matches"][0]["kind"] == "Function"


def test_code_workspace_symbol_search_503_when_no_ls(make_dashboard_with_project):
    _, client, _root = make_dashboard_with_project()
    r = client.get("/code/workspace_symbol_search?q=foo")
    assert r.status_code == 503
    assert r.get_json()["code"] == "ls_not_ready"


def test_code_workspace_symbol_search_empty_query_returns_empty(make_dashboard_with_project):
    # Even with no LS, empty query short-circuits to 200/{matches:[]}.
    _, client, _root = make_dashboard_with_project()
    r = client.get("/code/workspace_symbol_search?q=")
    assert r.status_code == 200
    assert r.get_json() == {"matches": []}


# -----------------------------------------------------------------------------
# Task 23 — /code/diagnostics_summary
# -----------------------------------------------------------------------------


def test_code_diagnostics_summary_503_when_no_ls(make_dashboard_with_project):
    _, client, root = make_dashboard_with_project()
    (root / "a.py").write_text("x=1")
    r = client.get("/code/diagnostics_summary")
    assert r.status_code == 503
    assert r.get_json()["code"] == "ls_not_ready"


def test_code_diagnostics_summary_503_when_no_project(tmp_path):
    from serena.dashboard import SerenaDashboardAPI

    class _AgentNoProject:
        version = "v"
        _all_tools: dict = {}
        serena_config = SimpleNamespace(projects=[])

        def register_config_changed_callback(self, callback):
            pass

        def get_active_project(self):
            return None

        def get_language_server_manager(self):
            return None

        def get_current_tasks(self):
            return []

        def execute_task(self, fn, *, logged=None, name=None):
            return fn()

        def get_language_backend(self):
            return SimpleNamespace(is_jetbrains=lambda: False)

    dashboard = SerenaDashboardAPI(memory_log_handler=_DummyMemLog(), tool_names=[], agent=_AgentNoProject(), tool_usage_stats=None)
    client = dashboard._app.test_client()
    r = client.get("/code/diagnostics_summary")
    assert r.status_code == 503
    assert r.get_json()["code"] == "no_project"


def test_code_diagnostics_summary_happy_path(make_dashboard_with_project):
    diag = {
        "range": {"start": {"line": 3, "character": 2}, "end": {"line": 3, "character": 5}},
        "severity": 1,
        "message": "undefined variable",
        "source": "pyright",
    }
    mgr = _FakeManager(ls=_FakeLS(diagnostics_map={"a.py": [diag]}))
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "a.py").write_text("x=1\n")
    r = client.get("/code/diagnostics_summary")
    assert r.status_code == 200
    body = r.get_json()
    assert body["truncated"] is False
    files = {f["path"]: f for f in body["files"]}
    assert "a.py" in files
    assert files["a.py"]["diagnostics"][0]["severity"] == "error"
    assert files["a.py"]["diagnostics"][0]["line"] == 3
    assert files["a.py"]["diagnostics"][0]["column"] == 2
    assert files["a.py"]["diagnostics"][0]["source"] == "pyright"


def test_code_diagnostics_summary_truncates_long_message(make_dashboard_with_project):
    long_msg = "X" * 10_000
    diag = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 2,
        "message": long_msg,
        "source": "x",
    }
    mgr = _FakeManager(ls=_FakeLS(diagnostics_map={"a.py": [diag]}))
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "a.py").write_text("x=1\n")
    r = client.get("/code/diagnostics_summary")
    assert r.status_code == 200
    body = r.get_json()
    assert body["truncated"] is True
    files = {f["path"]: f for f in body["files"]}
    msg = files["a.py"]["diagnostics"][0]["message"]
    assert len(msg) <= 4096


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
    mgr = _FakeManager(ls=_FakeLS(diagnostics_map={"pkg/inside.py": [diag], "outside.py": [diag]}))
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


def test_diagnostics_summary_file_scope_skips_unsupported_file(make_dashboard_with_project):
    diag = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 1,
        "message": "should not surface",
        "source": "pyright",
    }
    # The manager hands back its default server for any path, but that server does
    # not handle Markdown (is_ignored_path -> True). File scope must NOT lint the
    # file with the wrong server; it returns no diagnostics. (Were the diagnostic
    # to surface, it would prove the wrong-server linting bug.)
    ls = _FakeLS(pull_diagnostics_map={"notes.md": [diag]}, ignored_paths={"notes.md"})
    _, client, root = make_dashboard_with_project(ls_manager=_FakeManager(ls=ls))
    (root / "notes.md").write_text("# hi\n")
    r = client.get("/code/diagnostics_summary?path=notes.md")
    assert r.status_code == 200
    body = r.get_json()
    assert body["files"] == []
    assert body["skipped_unsupported"] == 1


# -----------------------------------------------------------------------------
# Per-file LSP routing in dir/project scope (multi-language correctness)
# -----------------------------------------------------------------------------


class _FakeRoutingManager:
    """Routes each path to a per-extension language server, mirroring
    LanguageServerManager.get_language_server in a multi-language project.

    Falls back to a default server for unknown extensions, exactly like the real
    manager — the dashboard's _ls_handles_file guard is what then filters files
    that no server actually understands.
    """

    def __init__(self, by_ext, default=None):
        self._by_ext = by_ext  # {".py": ls_py, ".ts": ls_ts}
        self._default = default if default is not None else next(iter(by_ext.values()))

    def get_language_server(self, rel):
        if os.path.isdir(rel):
            raise ValueError(f"directory: {rel}")
        ext = os.path.splitext(rel)[1]
        return self._by_ext.get(ext, self._default)

    def iter_language_servers(self):
        seen: set[int] = set()
        for ls in self._by_ext.values():
            if id(ls) not in seen:
                seen.add(id(ls))
                yield ls


def test_diagnostics_summary_project_scope_routes_each_file_to_correct_server(make_dashboard_with_project):
    """In a multi-language project each file must be diagnosed by the server that
    handles its type: .py by the Python server, .ts by the TypeScript server.
    """
    diag_py = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 1,
        "message": "python diag",
        "source": "pyright",
    }
    diag_ts = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 1,
        "message": "typescript diag",
        "source": "tsserver",
    }
    # Trap: the Python server *also* has a (wrong) diagnostic keyed under b.ts.
    # If routing were broken and b.ts were sent to the Python server, this trap
    # message would surface instead of "typescript diag".
    trap = {
        "range": {"start": {"line": 9, "character": 0}, "end": {"line": 9, "character": 1}},
        "severity": 1,
        "message": "WRONG SERVER",
        "source": "pyright",
    }
    ls_py = _FakeLS(
        diagnostics_map={"a.py": [diag_py], "b.ts": [trap]},
        ignored_paths={"b.ts"},  # Python server does not handle .ts
    )
    ls_ts = _FakeLS(
        diagnostics_map={"b.ts": [diag_ts]},
        ignored_paths={"a.py"},  # TS server does not handle .py
    )
    mgr = _FakeRoutingManager({".py": ls_py, ".ts": ls_ts})
    _, client, root = make_dashboard_with_project(ls_manager=mgr)
    (root / "a.py").write_text("x=1\n")
    (root / "b.ts").write_text("const x = 1\n")
    r = client.get("/code/diagnostics_summary")
    assert r.status_code == 200
    files = {f["path"]: f for f in r.get_json()["files"]}
    assert set(files) == {"a.py", "b.ts"}
    assert files["a.py"]["diagnostics"][0]["message"] == "python diag"
    # Correct routing => the TS server's diag, never the Python server's trap.
    assert files["b.ts"]["diagnostics"][0]["message"] == "typescript diag"


def test_diagnostics_summary_project_scope_skips_unsupported_file(make_dashboard_with_project):
    """A file whose type no started server handles (e.g. Markdown in a Python-only
    project) must be skipped, not linted by the default server.
    """
    diag = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 1,
        "message": "real python diag",
        "source": "pyright",
    }
    trap = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 1,
        "message": "WRONG SERVER",
        "source": "pyright",
    }
    # Single Python server: handles a.py, but notes.md is unsupported. The manager
    # would still hand back this server for notes.md (fallback), so the guard must
    # drop it.
    ls = _FakeLS(diagnostics_map={"a.py": [diag], "notes.md": [trap]}, ignored_paths={"notes.md"})
    _, client, root = make_dashboard_with_project(ls_manager=_FakeManager(ls=ls))
    (root / "a.py").write_text("x=1\n")
    (root / "notes.md").write_text("# hi\n")
    r = client.get("/code/diagnostics_summary")
    assert r.status_code == 200
    body = r.get_json()
    paths = {f["path"] for f in body["files"]}
    assert paths == {"a.py"}
    assert body["skipped_unsupported"] == 1


# -----------------------------------------------------------------------------
# Per-server grouping + round-robin scan (fair wall-clock budgeting)
# -----------------------------------------------------------------------------


def test_group_paths_by_language_server_groups_and_counts_skipped():
    from serena.dashboard_code import _group_paths_by_language_server

    ls_py = _FakeLS(ignored_paths={"b.ts", "notes.md"})
    ls_ts = _FakeLS(ignored_paths={"a.py", "c.py", "notes.md"})
    mgr = _FakeRoutingManager({".py": ls_py, ".ts": ls_ts})
    dashboard_api = SimpleNamespace(_agent=SimpleNamespace(get_language_server_manager=lambda: mgr))

    groups, skipped = _group_paths_by_language_server(dashboard_api, ["a.py", "b.ts", "c.py", "notes.md"])

    # Two groups (Python, TypeScript) in first-seen order; .md routed nowhere.
    assert skipped == 1
    assert [ls for ls, _paths in groups] == [ls_py, ls_ts]
    by_ls = {id(ls): paths for ls, paths in groups}
    assert by_ls[id(ls_py)] == ["a.py", "c.py"]
    assert by_ls[id(ls_ts)] == ["b.ts"]


def test_scan_groups_round_robin_interleaves_servers():
    from serena.dashboard_code import _scan_groups_round_robin

    def _diag(msg):
        return {
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
            "severity": 1,
            "message": msg,
            "source": "x",
        }

    # Each server returns one diagnostic per file (keyed by path) so we can read
    # back the scan order from the result list.
    ls_a = _FakeLS(diagnostics_map={"a1.py": [_diag("a1")], "a2.py": [_diag("a2")]})
    ls_b = _FakeLS(diagnostics_map={"b1.ts": [_diag("b1")]})
    groups = [(ls_a, ["a1.py", "a2.py"]), (ls_b, ["b1.ts"])]

    files, truncated = _scan_groups_round_robin(groups, use_pull=False, min_severity=4, deadline=time.monotonic() + 30)

    assert truncated is False
    order = [f.path for f in files]
    # Round 1 takes one from each server (a1, b1) before round 2 drains a2 — so
    # the second server is reached before the first server's queue is exhausted.
    assert order == ["a1.py", "b1.ts", "a2.py"]


def test_scan_groups_round_robin_truncates_at_deadline():
    from serena.dashboard_code import _scan_groups_round_robin

    diag = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "severity": 1,
        "message": "m",
        "source": "x",
    }
    ls = _FakeLS(diagnostics_map={"a.py": [diag], "b.py": [diag]})
    groups = [(ls, ["a.py", "b.py"])]
    # Deadline already in the past => nothing scanned, truncated True.
    files, truncated = _scan_groups_round_robin(groups, use_pull=False, min_severity=4, deadline=time.monotonic() - 1)
    assert files == []
    assert truncated is True
