"""
Basic integration tests for the HTML language server.

The HTML LSP (vscode-html-language-server) provides in-file document symbols
based on the element tree. Cross-file navigation (definition / references) is
not meaningful for HTML and is therefore not tested here.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from test.solidlsp.conftest import request_all_symbols


@pytest.mark.html
class TestHtmlLanguageServerBasics:
    """Smoke + symbol tests for the HTML language server."""

    @pytest.mark.parametrize("language_server", [Language.HTML], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.HTML], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [Language.HTML], indirect=True)
    def test_index_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """The HTML LSP exposes elements/IDs as document symbols."""
        all_symbols, _ = language_server.request_document_symbols("index.html").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]

        # vscode-html-language-server reports elements by tag name and emits an entry
        # per element with an id attribute. Names contain the id like "header#page-header"
        # or just the tag like "head" for elements without an id; we check both forms.
        joined = " | ".join(names)
        for expected_id in ("page-header", "site-title", "main-nav", "section-features", "feature-list", "page-footer"):
            assert expected_id in joined, f"Expected id '{expected_id}' to appear in HTML symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.HTML], indirect=True)
    def test_about_document_symbols(self, language_server: SolidLanguageServer) -> None:
        all_symbols, _ = language_server.request_document_symbols("about.html").get_all_symbols_and_roots()
        names = [s["name"] for s in all_symbols]
        joined = " | ".join(names)
        for expected_id in ("page-header", "about-title", "main-nav", "about-article"):
            assert expected_id in joined, f"Expected id '{expected_id}' to appear in HTML symbols: {names}"

    @pytest.mark.parametrize("language_server", [Language.HTML], indirect=True)
    def test_full_symbol_tree_includes_both_files(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths = {s.get("location", {}).get("relativePath") for s in all_symbols}
        assert "index.html" in relative_paths
        assert "about.html" in relative_paths
