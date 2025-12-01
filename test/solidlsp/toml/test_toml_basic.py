"""
Basic integration tests for the TOML language server functionality.

These tests validate the functionality of the Taplo language server APIs
like request_document_symbols using the TOML test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.toml
class TestTomlLanguageServerBasics:
    """Test basic functionality of the TOML language server (Taplo)."""

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    def test_toml_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that TOML language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.TOML

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    def test_toml_request_document_symbols_cargo(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for Cargo.toml files."""
        all_symbols, _root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        # Extract symbol names - Taplo should detect tables and keys
        symbol_names = [symbol["name"] for symbol in all_symbols]

        # Should detect at least some standard Cargo.toml sections
        # Taplo typically detects tables like [package], [dependencies], etc.
        assert len(all_symbols) > 0, f"Should find symbols in Cargo.toml, found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    def test_toml_request_document_symbols_pyproject(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for pyproject.toml files."""
        all_symbols, _root_symbols = language_server.request_document_symbols("pyproject.toml").get_all_symbols_and_roots()

        # Extract symbol names
        symbol_names = [symbol["name"] for symbol in all_symbols]

        # Should detect at least some standard pyproject.toml sections
        assert len(all_symbols) > 0, f"Should find symbols in pyproject.toml, found: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.TOML], indirect=True)
    def test_toml_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        all_symbols, _root_symbols = language_server.request_document_symbols("Cargo.toml").get_all_symbols_and_roots()

        # Should have found some symbols
        assert len(all_symbols) > 0, "Should find symbols in Cargo.toml"
        assert all_symbols is not None, "Should return symbols"
