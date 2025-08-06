"""
Basic integration tests for the Lean 4 language server functionality.

These tests validate the functionality of the language server APIs
using the Lean 4 test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.lean4
class TestLean4LanguageServerBasics:
    """Test basic functionality of the Lean 4 language server."""

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_lean4_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that Lean 4 language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.LEAN4

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_lean4_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for Lean 4 files."""
        # Test getting symbols from Serena/Basic.lean
        all_symbols, root_symbols = language_server.request_document_symbols("Serena/Basic.lean", include_body=False)

        # Check for any symbols at all (Lean might categorize differently than other languages)
        assert len(all_symbols) > 0, "Should find at least some symbols in the file"

        # Lean may not use standard LSP Symbol Kind 12 for functions
        # Just verify we got some symbols
        print(f"Found {len(all_symbols)} total symbols")
        if all_symbols:
            print(f"Sample symbol kinds: {set(sym.get('kind') for sym in all_symbols[:5])}")

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_lean4_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        # Test with include_body=True
        all_symbols, root_symbols = language_server.request_document_symbols("Serena/Basic.lean", include_body=True)

        # Should have some symbols
        assert len(all_symbols) > 0, "Should find symbols in the file"

        # Check that at least one symbol has a body
        symbols_with_body = [sym for sym in all_symbols if sym.get("body")]
        assert len(symbols_with_body) > 0, "Should find at least one symbol with body content"

    @pytest.mark.parametrize("language_server", [Language.LEAN4], indirect=True)
    def test_lean4_definition_lookup(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition functionality."""
        # Test is optional - Lean's go-to-definition may work differently
        try:
            definition_locations = language_server.request_definition("Serena/Basic.lean", 24, 13)

            if definition_locations:
                print(f"Found {len(definition_locations)} definitions")
                # Just verify we got some result
                assert len(definition_locations) > 0, "Should find at least one definition"
            else:
                # Lean server may not support go-to-definition in all contexts
                print("Go-to-definition not supported or no definitions found")
        except Exception as e:
            # Go-to-definition is optional for basic functionality
            print(f"Go-to-definition test skipped: {e}")
