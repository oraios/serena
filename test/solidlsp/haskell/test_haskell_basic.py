"""
Basic tests for Haskell Language Server integration.

Tests cover:
- Symbol discovery (functions, data types, modules)
- Within-file references
- Cross-file references across modules
"""

import pytest

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.haskell
class TestHaskellLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_haskell_symbols(self, language_server: SolidLanguageServer):
        """
        Test if we can find the top-level symbols in Calculator.hs.
        """
        all_symbols, _ = language_server.request_document_symbols("src/Calculator.hs")
        symbol_names = {s["name"] for s in all_symbols}

        # Verify key symbols are found
        assert "add" in symbol_names, f"Expected 'add' function in symbols, got: {symbol_names}"
        assert "subtract" in symbol_names, f"Expected 'subtract' function in symbols, got: {symbol_names}"
        assert "multiply" in symbol_names, f"Expected 'multiply' function in symbols, got: {symbol_names}"
        assert "divide" in symbol_names, f"Expected 'divide' function in symbols, got: {symbol_names}"
        assert "Calculator" in symbol_names, f"Expected 'Calculator' data type in symbols, got: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_haskell_within_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function within the same file.
        """
        # Find references to 'multiply' function in Calculator.hs
        # multiply is defined around line 33 and used in calculate function
        # LSP uses 0-based indexing, so line 33 is index 32
        references = language_server.request_references("src/Calculator.hs", line=32, column=0)

        # Should find at least the definition and usage in calculate
        assert len(references) >= 1, f"Expected at least 1 reference to multiply, got {len(references)}"

        # Verify at least one reference is in Calculator.hs
        reference_paths = [ref["relativePath"] for ref in references]
        assert "src/Calculator.hs" in reference_paths, f"Expected src/Calculator.hs in references, got: {reference_paths}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_haskell_cross_file_references(self, language_server: SolidLanguageServer):
        """
        Test finding references to a function defined in another file.
        """
        # The 'validateNumber' function is defined in Helper.hs (line 8)
        # and used in Calculator.hs (in add and subtract functions)
        # LSP uses 0-based indexing, so line 8 is index 7
        references = language_server.request_references("src/Helper.hs", line=7, column=0)

        # Should find at least the definition and usages
        assert len(references) >= 1, f"Expected at least 1 reference to validateNumber, got {len(references)}"

        # Verify references span multiple files
        reference_paths = [ref["relativePath"] for ref in references]
        # Should have references in both Helper.hs (definition) and Calculator.hs (usage)
        assert any("Helper.hs" in path for path in reference_paths) or any(
            "Calculator.hs" in path for path in reference_paths
        ), f"Expected cross-file references, got: {reference_paths}"
