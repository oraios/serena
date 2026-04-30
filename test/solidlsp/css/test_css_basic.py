"""
Basic integration tests for the CSS language server.

The CSS LSP (vscode-css-language-server) returns each top-level rule (selector)
as a document symbol. Cross-file ``@import`` navigation is limited and is not
exercised here.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import request_all_symbols


@pytest.mark.css
class TestCssLanguageServerBasics:
    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.CSS], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_main_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("main.css").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        for selector in ("body", "#page-header", "#site-title", ".button", ".button-primary", ".button-secondary"):
            assert selector in joined, f"Expected selector '{selector}' to appear in CSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_theme_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("theme.css").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        assert ":root" in joined, f"Expected ':root' selector to appear in CSS symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.CSS], indirect=True)
    def test_full_symbol_tree_includes_all_files(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        for f in ("main.css", "reset.css", "theme.css"):
            assert f in relative_paths, f"Expected {f} to appear in symbol tree"
