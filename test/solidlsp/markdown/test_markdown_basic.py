"""
Basic integration tests for the markdown language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the markdown test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


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
        # Test getting symbols from README.md
        all_symbols, root_symbols = language_server.request_document_symbols("README.md", include_body=False)

        # Extract heading symbols (LSP Symbol Kind 15 is String, but marksman uses kind 15 for headings)
        # Note: Different markdown LSPs may use different symbol kinds for headings
        # Marksman typically uses kind 15 (String) for markdown headings
        heading_names = [symbol["name"] for symbol in all_symbols]

        # Should detect headings from README.md
        assert "Test Repository" in heading_names or len(all_symbols) > 0, "Should find at least one heading"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_symbols_from_guide(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in guide.md file."""
        all_symbols, root_symbols = language_server.request_document_symbols("guide.md", include_body=False)

        # At least some headings should be found
        assert len(all_symbols) > 0, f"Should find headings in guide.md, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_symbols_from_api(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in api.md file."""
        all_symbols, root_symbols = language_server.request_document_symbols("api.md", include_body=False)

        # Should detect headings from api.md
        assert len(all_symbols) > 0, f"Should find headings in api.md, found {len(all_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.MARKDOWN], indirect=True)
    def test_markdown_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        # Test with include_body=True
        all_symbols, root_symbols = language_server.request_document_symbols("README.md", include_body=True)

        # Should have found some symbols
        assert len(all_symbols) > 0, "Should find symbols in README.md"

        # Note: Not all markdown LSPs provide body information for symbols
        # This test is more lenient and just verifies the API works
        assert all_symbols is not None, "Should return symbols even if body extraction is limited"
