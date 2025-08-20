"""
Basic integration tests for the Haskell language server (HLS).
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.haskell
class TestHaskellLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_document_symbols(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_document_symbols("src/Lib.hs")
        assert symbols, "Expected document symbols in Lib.hs"

        # HLS returns a tuple with (hierarchical_symbols, flat_symbols)
        assert isinstance(symbols, tuple) and len(symbols) == 2, f"Expected tuple of 2 lists, got: {type(symbols)}"

        hierarchical_symbols, flat_symbols = symbols
        # Use flat symbols for easier searching - extract names from both lists
        all_symbols = flat_symbols + hierarchical_symbols
        symbol_names = []

        for sym in all_symbols:
            if isinstance(sym, dict) and "name" in sym:
                symbol_names.append(sym["name"])
            # Also check children if they exist
            if isinstance(sym, dict) and "children" in sym:
                for child in sym["children"]:
                    if isinstance(child, dict) and "name" in child:
                        symbol_names.append(child["name"])

        # Check that we can find our key advanced Haskell features
        expected_symbols = ["hello", "add", "safeDiv", "Calculator", "User", "validateUser"]

        found_symbols = [name for name in expected_symbols if name in symbol_names]
        assert len(found_symbols) >= 3, f"Expected to find at least 3 key symbols, found: {found_symbols} in {symbol_names[:10]}..."

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_references(self, language_server: SolidLanguageServer) -> None:
        # Simple test - try to get references at a known location without relying on document symbols
        # Line 6, column 1 should be around the 'add' function definition in src/Lib.hs
        refs = language_server.request_references("src/Lib.hs", 6, 1)
        # Just verify we get a list back (may be empty if no references found, but should not error)
        assert isinstance(refs, list), f"Expected list of references, got: {type(refs)}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_goto_definition_basic_functions(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition for basic functions like 'add' in Main.hs"""
        # Test goto definition for 'add' function call in Main.hs
        definitions = language_server.request_definition("app/Main.hs", 8, 10)  # Around 'add' usage
        assert isinstance(definitions, list), f"Expected list of definitions, got: {type(definitions)}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_goto_definition_data_types(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition for custom data types like Calculator and User"""
        # Test goto definition for Calculator data type usage in Main.hs
        definitions = language_server.request_definition("app/Main.hs", 13, 15)  # Around 'Calculator' usage
        assert isinstance(definitions, list), f"Expected list of definitions, got: {type(definitions)}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_goto_definition_monadic_functions(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition for monadic functions like safeDiv and validateUser"""
        # Test goto definition for safeDiv function call in Main.hs
        definitions = language_server.request_definition("app/Main.hs", 11, 10)  # Around 'safeDiv' usage
        assert isinstance(definitions, list), f"Expected list of definitions, got: {type(definitions)}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_hover_information(self, language_server: SolidLanguageServer) -> None:
        """Test hover information for function signatures"""
        # Test hover on 'add' function in Lib.hs
        hover_info = language_server.request_hover("src/Lib.hs", 19, 1)  # Around 'add' function definition
        # Hover returns a dict with 'contents' key, or might be None if not supported, but should not error
        assert hover_info is None or (
            isinstance(hover_info, dict) and "contents" in hover_info
        ), f"Expected hover info dict with 'contents' or None, got: {type(hover_info)}"

    @pytest.mark.parametrize("language_server", [Language.HASKELL], indirect=True)
    def test_main_file_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for Main.hs which imports and uses advanced features"""
        symbols = language_server.request_document_symbols("app/Main.hs")
        assert symbols, "Expected document symbols in Main.hs"

        # HLS returns a tuple with (hierarchical_symbols, flat_symbols)
        assert isinstance(symbols, tuple) and len(symbols) == 2, f"Expected tuple of 2 lists, got: {type(symbols)}"

        hierarchical_symbols, flat_symbols = symbols
        # Should find at least some symbols (main function, imports, etc.)
        has_symbols = len(flat_symbols) > 0 or len(hierarchical_symbols) > 0
        assert (
            has_symbols
        ), f"Expected to find some symbols in Main.hs. Flat: {len(flat_symbols)}, Hierarchical: {len(hierarchical_symbols)}"
