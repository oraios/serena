"""
Basic integration tests for the markdown language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the markdown test repository.
"""

import pytest

from serena.symbol import LanguageServerSymbol
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind


@pytest.mark.markdown
class TestMarkdownLanguageServerBasics:
    """Test basic functionality of the markdown language server."""

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that markdown language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.MARKDOWN

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for markdown files."""
        all_symbols, _root_symbols = language_server.request_document_symbols("README.md").get_all_symbols_and_roots()

        heading_names = [symbol["name"] for symbol in all_symbols]

        # Should detect headings from README.md
        assert "Test Repository" in heading_names or len(all_symbols) > 0, "Should find at least one heading"

        # Verify that markdown headings are remapped from String to Namespace
        for symbol in all_symbols:
            assert (
                symbol["kind"] == SymbolKind.Namespace
            ), f"Heading '{symbol['name']}' should have kind Namespace, got {SymbolKind(symbol['kind']).name}"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_symbols_from_guide(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in guide.md file."""
        all_symbols, _root_symbols = language_server.request_document_symbols("guide.md").get_all_symbols_and_roots()

        # At least some headings should be found
        assert len(all_symbols) > 0, f"Should find headings in guide.md, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_symbols_from_api(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in api.md file."""
        all_symbols, _root_symbols = language_server.request_document_symbols("api.md").get_all_symbols_and_roots()

        # Should detect headings from api.md
        assert len(all_symbols) > 0, f"Should find headings in api.md, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        all_symbols, _root_symbols = language_server.request_document_symbols("README.md").get_all_symbols_and_roots()

        # Should have found some symbols
        assert len(all_symbols) > 0, "Should find symbols in README.md"

        # Note: Not all markdown LSPs provide body information for symbols
        # This test is more lenient and just verifies the API works
        assert all_symbols is not None, "Should return symbols even if body extraction is limited"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_headings_not_low_level(self, language_server: SolidLanguageServer) -> None:
        """Test that markdown headings are not classified as low-level symbols.

        Verifies the fix for the issue where Marksman's SymbolKind.String (15)
        caused all headings to be filtered out of get_symbols_overview.
        """
        all_symbols, _root_symbols = language_server.request_document_symbols("README.md").get_all_symbols_and_roots()
        assert len(all_symbols) > 0, "Should find headings in README.md"

        for symbol in all_symbols:
            ls_symbol = LanguageServerSymbol(symbol)
            assert (
                not ls_symbol.is_low_level()
            ), f"Heading '{symbol['name']}' should not be low-level (kind={SymbolKind(symbol['kind']).name})"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_nested_headings_remapped(self, language_server: SolidLanguageServer) -> None:
        """Test that nested headings (h1-h5) are all remapped from String to Namespace."""
        all_symbols, _root_symbols = language_server.request_document_symbols("api.md").get_all_symbols_and_roots()

        # api.md has deeply nested headings (h1 through h5)
        assert len(all_symbols) > 5, "api.md should have many headings"

        for symbol in all_symbols:
            assert symbol["kind"] == SymbolKind.Namespace, f"Nested heading '{symbol['name']}' should be remapped to Namespace"
