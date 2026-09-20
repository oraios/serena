"""
Basic integration tests for the Astro language server.
"""

import os
from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from test.solidlsp.conftest import document_symbol_names, request_all_symbols

pytestmark = pytest.mark.astro


class TestAstroLanguageServerBasics:
    """Smoke and symbol retrieval tests for the Astro language server."""

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    @pytest.mark.parametrize("repo_path", [LanguageServerId.ASTRO], indirect=True)
    def test_ls_is_running(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        assert language_server.is_running()
        assert Path(language_server.language_server.repository_root_path).resolve() == repo_path.resolve()

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_card_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "components", "Card.astro")
        names = document_symbol_names(language_server, file_path)

        # Frontmatter symbols
        assert "Props" in names
        assert "formatTitle" in names

        # Template elements
        assert any(n in names for n in ("li", "a", "h2", "p"))

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_index_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("src", "pages", "index.astro")
        names = document_symbol_names(language_server, file_path)

        assert "pageTitle" in names
        assert any(n in names for n in ("main", "h1", "Card"))

    @pytest.mark.parametrize("language_server", [LanguageServerId.ASTRO], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        all_symbols = request_all_symbols(language_server)
        relative_paths: set[str] = set()
        for s in all_symbols:
            loc = s.get("location")
            if isinstance(loc, dict):
                rel = loc.get("relativePath")
                if isinstance(rel, str):
                    relative_paths.add(rel.replace("\\", "/"))
        assert any("Card.astro" in p for p in relative_paths)
        assert any("index.astro" in p for p in relative_paths)
