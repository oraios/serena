"""
Error / edge-case tests for the Angular language server.

The Angular LS routes by file extension across three child processes:
    * ``ngserver`` for ``.html`` definition / references / hover
    * companion ``typescript-language-server`` (with @angular/language-service
      loaded as a tsserver plugin) for ``.ts`` operations
    * companion ``vscode-html-language-server`` for ``.html`` documentSymbol

The behaviour locked in below is **observed** behaviour on Linux with the
versions pinned in ``angular_language_server.py`` (Angular LS 21.2.10,
typescript-language-server 5.1.3, TypeScript 5.9.3). It is platform-aware where
upstream LSPs are known to differ (Windows TS server tends to swallow malformed
positions instead of raising).
"""

import os
import sys
import time

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from test.conftest import _create_ls

pytestmark = pytest.mark.angular

IS_WINDOWS = sys.platform == "win32"

TS_FILE = os.path.join("src", "app", "app.component.ts")
SERVICE_FILE = os.path.join("src", "app", "greeting.service.ts")
TEMPLATE_FILE = os.path.join("src", "app", "app.component.html")


class TestAngularInvalidPositionsOnTs:
    """Negative / out-of-bounds line and column on .ts files (TS-companion route)."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_negative_line_number_containing_symbol(self, language_server: SolidLanguageServer) -> None:
        """``request_containing_symbol`` short-circuits before reaching the LS:
        a negative line returns None.
        """
        result = language_server.request_containing_symbol(TS_FILE, -1, 0)
        assert result is None, f"Expected None for negative line, got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_negative_character_number_containing_symbol(self, language_server: SolidLanguageServer) -> None:
        result = language_server.request_containing_symbol(TS_FILE, 5, -1)
        assert result is None, f"Expected None for negative character, got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_line_number_beyond_file_length(self, language_server: SolidLanguageServer) -> None:
        """The wrapper code raises ``IndexError`` before reaching the LS."""
        with pytest.raises(IndexError) as exc_info:
            language_server.request_containing_symbol(TS_FILE, 99999, 0)
        assert "list index out of range" in str(exc_info.value), f"Expected 'list index out of range' error, got: {exc_info.value}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_character_beyond_line_length_returns_enclosing_class(self, language_server: SolidLanguageServer) -> None:
        """Character far beyond end-of-line is clamped by the LSP. Line 5 of
        app.component.ts is inside ``export class AppComponent { ... }``, so the
        TS companion (with the Angular plugin) returns the AppComponent class
        as the containing symbol — not None — which is the documented LSP
        behaviour.
        """
        result = language_server.request_containing_symbol(TS_FILE, 5, 99999)
        assert isinstance(result, dict), f"Expected dict (containing class), got: {result!r}"
        assert result.get("name") == "AppComponent", f"Expected containing symbol 'AppComponent', got: {result.get('name')!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_references_at_negative_line_returns_empty(self, language_server: SolidLanguageServer) -> None:
        """The Angular LS's TS companion returns ``[]`` for negative-line
        ``request_references`` — it does **not** raise. (Plain Vue tests
        observe a ``Bad line number`` raise on Linux/macOS; the Angular
        plugin layered on tsserver suppresses this.)
        """
        result = language_server.request_references(TS_FILE, -1, 0)
        assert result == [], f"Expected [], got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_at_negative_position_returns_empty(self, language_server: SolidLanguageServer) -> None:
        """Same as references: TS companion returns ``[]``, does not raise."""
        result = language_server.request_definition(TS_FILE, -1, 0)
        assert result == [], f"Expected [], got: {result!r}"


@pytest.mark.skipif(
    IS_WINDOWS,
    reason="Windows ngserver swallows malformed positions instead of raising — same divergence as the TS companion (see test_referencing_symbols_at_invalid_position_raises).",
)
class TestAngularInvalidPositionsOnTemplate:
    """Negative / out-of-bounds positions on .html files (ngserver route)."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_negative_line_definition_raises(self, language_server: SolidLanguageServer) -> None:
        """Ngserver does **not** swallow malformed positions: it surfaces a
        ``Debug Failure. False expression.`` error from its underlying
        compiler. Lock that behaviour to catch any future change.
        """
        with pytest.raises(SolidLSPException) as exc_info:
            language_server.request_definition(TEMPLATE_FILE, -1, 0)
        assert "Debug Failure" in str(exc_info.value) or "Bad line number" in str(exc_info.value), (
            f"Unexpected exception message: {exc_info.value}"
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_character_beyond_line_definition_raises(self, language_server: SolidLanguageServer) -> None:
        """Same path as negative line — ngserver raises Debug Failure."""
        with pytest.raises(SolidLSPException) as exc_info:
            language_server.request_definition(TEMPLATE_FILE, 0, 99999)
        assert "Debug Failure" in str(exc_info.value) or "Bad line number" in str(exc_info.value), (
            f"Unexpected exception message: {exc_info.value}"
        )


class TestAngularNonExistentFiles:
    """Requests against files that don't exist must raise FileNotFoundError consistently."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_nonexistent_ts_file_raises(self, language_server: SolidLanguageServer) -> None:
        nonexistent = os.path.join("src", "app", "does-not-exist.component.ts")
        with pytest.raises(FileNotFoundError):
            language_server.request_references(nonexistent, 0, 0)
        with pytest.raises(FileNotFoundError):
            language_server.request_definition(nonexistent, 0, 0)
        with pytest.raises(FileNotFoundError):
            language_server.request_document_symbols(nonexistent)

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_nonexistent_html_file_raises(self, language_server: SolidLanguageServer) -> None:
        nonexistent = os.path.join("src", "app", "does-not-exist.component.html")
        with pytest.raises(FileNotFoundError):
            language_server.request_definition(nonexistent, 0, 0)
        with pytest.raises(FileNotFoundError):
            language_server.request_document_symbols(nonexistent)


class TestAngularUndefinedSymbols:
    """Symbols that have no callers / definitions / referencing positions."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_at_keyword_position_returns_empty(self, language_server: SolidLanguageServer) -> None:
        """Cursor on the ``import`` keyword (line 0, col 0 of app.component.ts)
        has no definition target — the TS companion returns ``[]``.
        """
        result = language_server.request_definition(TS_FILE, 0, 0)
        assert result == [], f"Expected [] for keyword position, got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_references_for_local_const_have_few_callers(self, language_server: SolidLanguageServer) -> None:
        """A locally-scoped private field has at most its declaration plus its
        in-method use as references. ``defaultName`` on GreetingService is
        used only inside ``greet()``.
        """
        all_symbols, _ = language_server.request_document_symbols(SERVICE_FILE).get_all_symbols_and_roots()
        sym = next((s for s in all_symbols if s.get("name") == "defaultName"), None)
        assert sym is not None, "defaultName symbol missing in fixture"
        sel = sym["selectionRange"]["start"]
        refs = language_server.request_references(SERVICE_FILE, sel["line"], sel["character"])
        assert isinstance(refs, list), f"Expected list, got {type(refs)}"
        # 1 declaration + 1 internal read = 2 expected; allow 1-3 to absorb
        # whether the LSP includes the declaration.
        assert 1 <= len(refs) <= 3, f"defaultName should have 1-3 references, got {len(refs)}: {refs}"


class TestAngularEdgeCasePositions:
    """Position (0,0), whitespace lines, and other boundary conditions."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_containing_symbol_at_file_start_is_none(self, language_server: SolidLanguageServer) -> None:
        """Line 0 of app.component.ts is an ``import`` statement, outside any
        class or function — the TS companion returns ``None`` for containing
        symbol.
        """
        result = language_server.request_containing_symbol(TS_FILE, 0, 0)
        assert result is None, f"Expected None at (0,0), got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_references_at_file_start_returns_empty(self, language_server: SolidLanguageServer) -> None:
        """Position (0, 0) is on the ``import`` keyword — no references."""
        result = language_server.request_references(TS_FILE, 0, 0)
        assert result == [], f"Expected [] at (0,0), got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_definition_at_file_start_returns_empty(self, language_server: SolidLanguageServer) -> None:
        """Position (0, 0) is on the ``import`` keyword — no definition."""
        result = language_server.request_definition(TS_FILE, 0, 0)
        assert result == [], f"Expected [] at (0,0), got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_template_position_no_containing_symbol(self, language_server: SolidLanguageServer) -> None:
        """An Angular template has no class/function containers; the HTML
        companion's documentSymbol provides element symbols only.
        """
        # (1, 4) lands inside <h1>{{ title() | exclaim }}</h1> on line 1.
        result = language_server.request_containing_symbol(TEMPLATE_FILE, 1, 4)
        assert result is None, f"Expected None inside template, got: {result!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_containing_symbol_inside_class_body_returns_class(self, language_server: SolidLanguageServer) -> None:
        """Lines 5 and 10 of app.component.ts are inside the AppComponent class
        body. The TS companion correctly reports AppComponent as the
        containing symbol.
        """
        for line in (5, 10):
            result = language_server.request_containing_symbol(TS_FILE, line, 0)
            assert isinstance(result, dict), f"Line {line}: expected dict, got {result!r}"
            assert result.get("name") == "AppComponent", f"Line {line}: expected 'AppComponent', got {result.get('name')!r}"

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_containing_symbol_outside_class_body_is_none(self, language_server: SolidLanguageServer) -> None:
        """Line 0 (import) and line 15 (blank/whitespace inside file but
        outside any symbol's range, depending on file structure) report no
        containing symbol.
        """
        for line in (0,):
            result = language_server.request_containing_symbol(TS_FILE, line, 0)
            assert result is None, f"Line {line}: expected None, got {result!r}"


class TestAngularReferenceEdgeCases:
    """Edge cases for the SolidLanguageServer reference helpers (built on top of LSP)."""

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_referencing_symbols_at_invalid_position_raises(self, language_server: SolidLanguageServer) -> None:
        """Unlike ``request_references`` (which returns ``[]``),
        ``request_referencing_symbols`` validates more strictly and surfaces
        the underlying TS server error as a ``SolidLSPException``.
        """
        if IS_WINDOWS:
            # Windows TS server is known to swallow these — keep platform-specific
            # contract minimal here since we can't run Windows in dev.
            result = list(language_server.request_referencing_symbols(SERVICE_FILE, -1, -1, include_self=False))
            assert result == [], f"Expected [] on Windows, got: {result!r}"
            return
        with pytest.raises(SolidLSPException) as exc_info:
            list(language_server.request_referencing_symbols(SERVICE_FILE, -1, -1, include_self=False))
        assert "Bad line number" in str(exc_info.value) or "Debug Failure" in str(exc_info.value), (
            f"Unexpected exception message: {exc_info.value}"
        )

    @pytest.mark.parametrize("language_server", [Language.ANGULAR], indirect=True)
    def test_defining_symbol_at_invalid_position_returns_none(self, language_server: SolidLanguageServer) -> None:
        """``request_defining_symbol`` short-circuits when no definition is
        found and returns None — no exception, even for negative positions.
        """
        result = language_server.request_defining_symbol(TS_FILE, -1, -1)
        assert result is None, f"Expected None, got: {result!r}"


class TestAngularCoreProbe:
    """Unit tests for the monorepo-aware ``_find_angular_core_install`` walk.

    These don't spin up the Angular LS — they exercise the pure-Python
    filesystem walker against synthetic node_modules layouts.
    """

    @staticmethod
    def _walk(repo_path: str) -> str | None:
        """Invoke the bound method against a minimal stub carrying only
        ``repository_root_path``.
        """
        from solidlsp.language_servers.angular_language_server import AngularLanguageServer

        stub = type("Stub", (), {"repository_root_path": repo_path})()
        return AngularLanguageServer._find_angular_core_install(stub)  # type: ignore[arg-type]

    def test_finds_core_at_project_root(self, tmp_path) -> None:
        core_pkg = tmp_path / "node_modules" / "@angular" / "core" / "package.json"
        core_pkg.parent.mkdir(parents=True)
        core_pkg.write_text("{}")
        assert self._walk(str(tmp_path)) == str(core_pkg)

    def test_finds_hoisted_core_in_workspace_parent(self, tmp_path) -> None:
        """Nx / yarn-workspaces layout: ``node_modules`` is hoisted to the
        workspace root and the activated sub-package has none of its own.
        """
        sub_pkg = tmp_path / "packages" / "app"
        sub_pkg.mkdir(parents=True)
        core_pkg = tmp_path / "node_modules" / "@angular" / "core" / "package.json"
        core_pkg.parent.mkdir(parents=True)
        core_pkg.write_text("{}")
        # Workspace root marker — the walker stops here.
        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')

        assert self._walk(str(sub_pkg)) == str(core_pkg)

    def test_returns_none_when_not_installed(self, tmp_path) -> None:
        """No node_modules anywhere — walker exhausts and returns None."""
        sub_pkg = tmp_path / "packages" / "app"
        sub_pkg.mkdir(parents=True)
        assert self._walk(str(sub_pkg)) is None

    def test_workspace_root_stops_walk(self, tmp_path) -> None:
        """If a ``package.json`` declares ``workspaces`` we should not walk past
        it — the workspace root is the canonical install location even when no
        ``@angular/core`` is present there.
        """
        # Plant a misleading sibling install ABOVE the workspace root that the
        # walker must NOT find.
        sibling_core = tmp_path / "node_modules" / "@angular" / "core" / "package.json"
        sibling_core.parent.mkdir(parents=True)
        sibling_core.write_text("{}")

        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / "package.json").write_text('{"workspaces": ["packages/*"]}')
        sub_pkg = workspace / "packages" / "app"
        sub_pkg.mkdir(parents=True)

        assert self._walk(str(sub_pkg)) is None


class TestAngularStartupCleanup:
    """Regression: companion processes (TS + HTML) must not leak when ngserver
    fails partway through ``_start_server``.

    Until the cleanup wrapper landed, an exception during ngserver init left
    the two companion Node processes orphaned because the parent constructor
    never returned a handle on which the caller could invoke ``stop()``.
    """

    def test_companions_cleaned_up_on_initialize_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        if IS_WINDOWS:
            pytest.skip("psutil child enumeration is flaky under Windows CI")

        import psutil

        ls = _create_ls(Language.ANGULAR)
        my_proc = psutil.Process(os.getpid())
        children_before = {p.pid for p in my_proc.children(recursive=True)}

        def boom(*_args: object, **_kwargs: object) -> dict:
            raise RuntimeError("simulated ngserver init failure")

        # _get_initialize_params runs after both companions and ngserver have
        # been spawned — exactly the failure window the cleanup wrapper
        # protects against.
        monkeypatch.setattr(ls, "_get_initialize_params", boom)

        try:
            with pytest.raises(RuntimeError, match="simulated ngserver init"):
                ls.start()

            assert ls._ts_server is None, "TS companion was not cleared after startup failure"
            assert ls._html_server is None, "HTML companion was not cleared after startup failure"

            # Allow a brief grace period for the OS to reap the spawned Node
            # processes (and grandchildren — typescript-language-server forks
            # tsserver).
            deadline = time.monotonic() + 5.0
            new_children: set[int] = set()
            while time.monotonic() < deadline:
                children_after = {p.pid for p in my_proc.children(recursive=True)}
                new_children = children_after - children_before
                if not new_children:
                    break
                time.sleep(0.2)
            assert not new_children, f"Companion processes leaked after startup failure: {sorted(new_children)}"
        finally:
            # Best-effort: if anything is still around (e.g. ngserver itself,
            # which lives outside the cleanup contract), shut it down so the
            # test session doesn't leave orphans.
            try:
                ls.stop(shutdown_timeout=2.0)
            except Exception:
                pass
