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
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote, urlparse

from flask import request
from pydantic import BaseModel

if TYPE_CHECKING:
    from serena.dashboard import SerenaDashboardAPI

log = logging.getLogger(__name__)

_FILE_LIMIT_CAP = 2000
_WORKSPACE_SYMBOL_LIMIT_CAP = 200
_DIAGNOSTICS_PER_FILE_BYTE_CAP = 1024 * 1024  # 1 MB
_DIAGNOSTICS_PER_MESSAGE_CAP = 4096  # 4 KB per diag message
_DIAGNOSTICS_WALL_CLOCK_BUDGET_S = 30.0  # overall deadline for the per-file LSP loop
_SYMBOL_TREE_MAX_DEPTH = 64  # guard against malformed/circular LSP DocumentSymbol trees


# LSP SymbolKind → human-readable label.
_LSP_SYMBOL_KIND_LABELS: dict[int, str] = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Constructor",
    10: "Enum",
    11: "Interface",
    12: "Function",
    13: "Variable",
    14: "Constant",
    15: "String",
    16: "Number",
    17: "Boolean",
    18: "Array",
    19: "Object",
    20: "Key",
    21: "Null",
    22: "EnumMember",
    23: "Struct",
    24: "Event",
    25: "Operator",
    26: "TypeParameter",
}

# LSP DiagnosticSeverity int → label.
_LSP_SEVERITY: dict[int, str] = {1: "error", 2: "warning", 3: "info", 4: "hint"}


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


def _get_first_language_server(dashboard_api: "SerenaDashboardAPI") -> Any | None:
    """
    Return the first started language server, or None if none.
    Uses ls_manager.iter_language_servers().
    """
    try:
        manager = dashboard_api._agent.get_language_server_manager()
    except Exception as e:
        log.debug("LS manager unavailable: %s", e)
        return None
    if manager is None:
        return None
    try:
        for ls in manager.iter_language_servers():
            return ls
    except Exception as e:
        log.debug("LS iter failed: %s", e)
    return None


def _get_language_server_for_path(dashboard_api: "SerenaDashboardAPI", rel_path: str) -> Any | None:
    """Get the LS responsible for a specific relative path, or None.

    Catches ValueError (raised by ls_manager.get_language_server when the path is
    a directory) and any other Exception as a defensive boundary.
    """
    try:
        manager = dashboard_api._agent.get_language_server_manager()
    except Exception as e:
        log.debug("LS manager unavailable: %s", e)
        return None
    if manager is None:
        return None
    try:
        return manager.get_language_server(rel_path)
    except ValueError:
        # The path looked like a directory or otherwise didn't match an LS.
        return None
    except Exception as e:
        log.debug("get_language_server(%r) failed: %s", rel_path, e)
        return None


def _ls_handles_file(ls: Any, rel_path: str) -> bool:
    """Whether `ls` actually handles this file's language.

    `LanguageServerManager.get_language_server` falls back to the *default*
    server for unsupported file types, so a Markdown/TOML/lockfile would be
    handed to, e.g., the Python server and linted into garbage. This mirrors the
    manager's own suitability test (`is_ignored_path(..., ignore_unsupported_files=True)`):
    a file the server doesn't understand is "ignored". Defensive — any error is
    treated as "not handled" so we never lint a file with the wrong server.
    """
    try:
        return not ls.is_ignored_path(rel_path, ignore_unsupported_files=True)
    except Exception as e:
        log.debug("is_ignored_path(%r) failed: %s", rel_path, e)
        return False


# --------------------------------------------------------------------------- #
# Models                                                                      #
# --------------------------------------------------------------------------- #


class _DirEntry(BaseModel):
    name: str
    kind: str  # "dir" | "file"
    size: int | None = None


class _ResponseListDir(BaseModel):
    entries: list[_DirEntry]


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


class _WorkspaceMatch(BaseModel):
    name: str
    kind: str
    path: str
    range: _Range


class _ResponseWorkspaceSymbolSearch(BaseModel):
    matches: list[_WorkspaceMatch]


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
    # Count of in-scope files no started language server handles (e.g. Markdown,
    # JSON, lockfiles in a Python-only project). They are skipped rather than
    # linted by the wrong server; surfacing the count lets the UI distinguish
    # "clean" from "not analyzed". Defaults to 0 so the field is backward-compatible.
    skipped_unsupported: int = 0


_FileSymbol.model_rebuild()


# --------------------------------------------------------------------------- #
# LSP shape adapters                                                          #
# --------------------------------------------------------------------------- #


def _maybe(obj: Any, key: str) -> Any:
    """Read key from dict-or-object. Returns None when missing."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _convert_lsp_symbol(s: Any, _depth: int = 0) -> _FileSymbol:
    """Convert a UnifiedSymbolInformation / LSP DocumentSymbol to dashboard shape.

    Recursion is capped at _SYMBOL_TREE_MAX_DEPTH to guard against malformed or
    circular LSP responses (would otherwise stack-overflow on a bad server).
    """
    name = _maybe(s, "name") or "?"
    kind_int = _maybe(s, "kind")
    try:
        kind_label = _LSP_SYMBOL_KIND_LABELS.get(int(kind_int) if kind_int is not None else 0, str(kind_int))
    except (TypeError, ValueError):
        kind_label = str(kind_int)
    # range may be at top-level (DocumentSymbol) or under .location.range (SymbolInformation).
    rng = _maybe(s, "range")
    if rng is None:
        loc = _maybe(s, "location")
        rng = _maybe(loc, "range") if loc is not None else None
    rng = rng or {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}
    children = _maybe(s, "children") if _depth < _SYMBOL_TREE_MAX_DEPTH else None
    return _FileSymbol(
        name=name,
        kind=kind_label,
        range=cast("_Range", rng),
        children=[_convert_lsp_symbol(c, _depth + 1) for c in children] if children else None,
    )


def _convert_workspace_match(m: Any, project_root_real: Path) -> _WorkspaceMatch:
    name = _maybe(m, "name") or "?"
    kind_int = _maybe(m, "kind")
    try:
        kind_label = _LSP_SYMBOL_KIND_LABELS.get(int(kind_int) if kind_int is not None else 0, str(kind_int))
    except (TypeError, ValueError):
        kind_label = str(kind_int)
    location = _maybe(m, "location")
    uri = _maybe(location, "uri") if location is not None else None
    rng = _maybe(location, "range") if location is not None else None
    file_path = unquote(urlparse(uri).path) if uri else ""
    try:
        rel = str(Path(file_path).relative_to(project_root_real)) if file_path else ""
    except Exception:
        rel = file_path
    return _WorkspaceMatch(
        name=name,
        kind=kind_label,
        path=rel,
        range=cast("_Range", rng or {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}),
    )


def _collect_candidate_files(root_real: str, walk_root: str, ignore: Any, file_limit: int) -> tuple[list[str], bool]:
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
            rel = os.path.relpath(os.path.join(dirpath, fn), root_real).replace(os.sep, "/")
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


def _diagnostics_for_file(ls: Any, rel: str, use_pull: bool, min_severity: int) -> tuple["_FileDiagnostics | None", bool]:
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
    except Exception as e:
        log.debug("Diagnostics failed for %s: %s", rel, e)
        return None, False
    if not raw:
        return None, False

    diags: list[_Diagnostic] = []
    truncated = False
    byte_estimate = 0
    _PER_DIAG_JSON_OVERHEAD = 80  # approx JSON field-name overhead per serialized diag
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


def _group_paths_by_language_server(
    dashboard_api: "SerenaDashboardAPI", candidate_paths: list[str]
) -> tuple[list[tuple[Any, list[str]]], int]:
    """Route each candidate file to the language server that handles its type.

    Returns ``(groups, skipped_unsupported)`` where ``groups`` is a list of
    ``(language_server, paths)`` in first-seen order and ``skipped_unsupported``
    counts files no started server understands (Markdown/JSON/lockfiles/… in a
    Python-only project, or any type with no matching server). Grouping lets the
    scan round-robin across servers so one slow language can't starve the others'
    files of the wall-clock budget.
    """
    groups: dict[int, tuple[Any, list[str]]] = {}
    order: list[int] = []
    skipped_unsupported = 0
    for rel in candidate_paths:
        ls = _get_language_server_for_path(dashboard_api, rel)
        if ls is None or not _ls_handles_file(ls, rel):
            skipped_unsupported += 1
            continue
        key = id(ls)
        if key not in groups:
            groups[key] = (ls, [])
            order.append(key)
        groups[key][1].append(rel)
    return [groups[k] for k in order], skipped_unsupported


def _scan_groups_round_robin(
    groups: list[tuple[Any, list[str]]], use_pull: bool, min_severity: int, deadline: float
) -> tuple[list[_FileDiagnostics], bool]:
    """Scan per-server file groups round-robin until done or the deadline passes.

    Taking one file from each server per round (rather than draining one server
    fully before the next) gives every language a fair share of the shared
    wall-clock budget; if the deadline hits mid-scan, the remaining files in
    every group are dropped and ``truncated`` is True.
    """
    files: list[_FileDiagnostics] = []
    truncated = False
    cursors = [0] * len(groups)
    remaining = sum(len(paths) for _ls, paths in groups)
    while remaining > 0:
        for gi, (ls, paths) in enumerate(groups):
            if cursors[gi] >= len(paths):
                continue
            if time.monotonic() >= deadline:
                return files, True
            rel = paths[cursors[gi]]
            cursors[gi] += 1
            remaining -= 1
            file_diags, trunc = _diagnostics_for_file(ls, rel, use_pull, min_severity)
            if trunc:
                truncated = True
            if file_diags is not None:
                files.append(file_diags)
    return files, truncated


# --------------------------------------------------------------------------- #
# Route registration                                                          #
# --------------------------------------------------------------------------- #


def register_code_routes(dashboard_api: "SerenaDashboardAPI") -> None:
    """Register /code/* routes onto the dashboard's Flask app. Called from _setup_routes."""
    app = dashboard_api._app

    # ----- /code/list_dir -----------------------------------------------------
    @app.route("/code/list_dir", methods=["GET"])
    def code_list_dir() -> tuple[dict[str, Any], int] | dict[str, Any]:
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

        from serena.util.file_system import GitignoreParser

        try:
            ignore: GitignoreParser | None = GitignoreParser(root)
        except Exception:
            ignore = None

        entries: list[_DirEntry] = []
        try:
            with os.scandir(resolved) as it:
                for de in it:
                    if de.name.startswith("."):
                        continue
                    is_dir = de.is_dir(follow_symlinks=False)
                    is_file = de.is_file(follow_symlinks=False)
                    abs_path = de.path
                    rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
                    if ignore is not None:
                        # GitignoreParser.should_ignore handles directory/file disambiguation
                        # internally by appending '/' for directories.
                        if ignore.should_ignore(rel):
                            continue
                    if is_dir:
                        entries.append(_DirEntry(name=de.name, kind="dir"))
                    elif is_file:
                        try:
                            size = de.stat(follow_symlinks=False).st_size
                        except OSError:
                            size = None
                        entries.append(_DirEntry(name=de.name, kind="file", size=size))
        except PermissionError:
            return _err(403, "permission denied")
        entries.sort(key=lambda e: (e.kind == "file", e.name.lower()))
        return _ResponseListDir(entries=entries).model_dump()

    # ----- /code/file_symbols -------------------------------------------------
    @app.route("/code/file_symbols", methods=["GET"])
    def code_file_symbols() -> tuple[dict[str, Any], int] | dict[str, Any]:
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
        rel = os.path.relpath(resolved, str(Path(root).resolve())).replace(os.sep, "/")
        ls = _get_language_server_for_path(dashboard_api, rel)
        if ls is None:
            return _err(503, "Language server not ready", "ls_not_ready")
        try:
            doc_syms = ls.request_document_symbols(rel)
        except TimeoutError as e:
            return _err(504, str(e), "ls_timeout")
        except Exception as e:
            log.error("LSP document symbols failed for %s: %s", rel, e, exc_info=e)
            return _err(502, str(e), "ls_error")
        # doc_syms may be a DocumentSymbols object (.root_symbols) or a raw list.
        roots = getattr(doc_syms, "root_symbols", None)
        if roots is None:
            roots = doc_syms or []
        return _ResponseFileSymbols(symbols=[_convert_lsp_symbol(s) for s in roots]).model_dump()

    # ----- /code/workspace_symbol_search --------------------------------------
    @app.route("/code/workspace_symbol_search", methods=["GET"])
    def code_workspace_symbol_search() -> tuple[dict[str, Any], int] | dict[str, Any]:
        q = request.args.get("q", default="", type=str)
        limit = request.args.get("limit", default=50, type=int)
        q_stripped = q.strip() if q else ""
        if len(q_stripped) < 2:
            return _ResponseWorkspaceSymbolSearch(matches=[]).model_dump()
        limit = max(1, min(limit, _WORKSPACE_SYMBOL_LIMIT_CAP))
        ls = _get_first_language_server(dashboard_api)
        if ls is None:
            return _err(503, "Language server not ready", "ls_not_ready")
        try:
            raw = ls.request_workspace_symbol(q)  # singular — confirmed in solidlsp/ls.py
        except TimeoutError as e:
            return _err(504, str(e), "ls_timeout")
        except Exception as e:
            log.error("LSP workspace symbol failed for %r: %s", q, e, exc_info=e)
            return _err(502, str(e), "ls_error")
        if not raw:
            return _ResponseWorkspaceSymbolSearch(matches=[]).model_dump()
        raw = raw[:limit]
        root = _get_project_root(dashboard_api) or ""
        project_root_real = Path(root).resolve() if root else Path()
        matches = [_convert_workspace_match(m, project_root_real) for m in raw]
        return _ResponseWorkspaceSymbolSearch(matches=matches).model_dump()

    # ----- /code/diagnostics_summary ------------------------------------------
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
        skipped_unsupported = 0
        deadline = time.monotonic() + _DIAGNOSTICS_WALL_CLOCK_BUDGET_S
        if mode == "file":
            rel0 = os.path.relpath(resolved, root_real).replace(os.sep, "/")
            # Diagnose with the server that actually handles THIS file's language
            # (mirrors /code/file_symbols), not the first server. Otherwise a
            # non-Python file (Markdown, JSON, .svelte, .ts in a Python-first
            # project) gets linted by, e.g., Pyright and returns garbage. A file
            # type with no matching server simply has no diagnostics.
            ls = _get_language_server_for_path(dashboard_api, rel0)
            if ls is None or not _ls_handles_file(ls, rel0):
                return _ResponseDiagnosticsSummary(files=[], truncated=False, skipped_unsupported=1).model_dump()
            file_diags, truncated = _diagnostics_for_file(ls, rel0, use_pull=True, min_severity=min_severity)
            result_files = [file_diags] if file_diags is not None else []
        else:  # "dir" or "project"
            candidate_paths, truncated = _collect_candidate_files(root_real, resolved, ignore, file_limit)
            # Route EACH file to the server that handles its type, group by server,
            # then scan round-robin so a multi-language project diagnoses .py with
            # Pyright, .ts with the TS server, etc. — and one slow language can't
            # exhaust the wall-clock budget before the others are reached. Files no
            # started server understands are counted (skipped_unsupported), not
            # linted with the wrong server.
            groups, skipped_unsupported = _group_paths_by_language_server(dashboard_api, candidate_paths)
            result_files, scan_truncated = _scan_groups_round_robin(groups, use_pull=False, min_severity=min_severity, deadline=deadline)
            truncated = truncated or scan_truncated

        return _ResponseDiagnosticsSummary(files=result_files, truncated=truncated, skipped_unsupported=skipped_unsupported).model_dump()
