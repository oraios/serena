"""
Tests for the Lua language server implementation.

These tests validate symbol finding and cross-file reference capabilities
for Lua modules and functions.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.conftest import find_identifier_position, get_repo_path, language_has_verified_implementation_support
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols


@pytest.mark.lua
class TestLuaLanguageServer:
    """Test Lua language server symbol finding and cross-file references."""

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_find_symbols_in_calculator(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific functions in calculator.lua."""
        symbols = language_server.request_document_symbols("src/calculator.lua").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        # Extract function names from the returned structure
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        function_names = set()
        for symbol in symbol_list:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                # Handle both plain names and module-prefixed names
                if "." in name:
                    name = name.split(".")[-1]
                if symbol.get("kind") == SymbolKind.Function:
                    function_names.add(name)

        # Verify exact calculator functions exist
        expected_functions = {"add", "subtract", "multiply", "divide", "factorial"}
        found_functions = function_names & expected_functions
        assert found_functions == expected_functions, f"Expected exactly {expected_functions}, found {found_functions}"

        # Verify specific functions
        assert "add" in function_names, "add function not found"
        assert "multiply" in function_names, "multiply function not found"
        assert "factorial" in function_names, "factorial function not found"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_find_symbols_in_utils(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific functions in utils.lua."""
        symbols = language_server.request_document_symbols("src/utils.lua").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        function_names = set()
        all_symbols = set()

        for symbol in symbol_list:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                all_symbols.add(name)
                # Handle both plain names and module-prefixed names
                if "." in name:
                    name = name.split(".")[-1]
                if symbol.get("kind") == SymbolKind.Function:
                    function_names.add(name)

        # Verify exact string utility functions
        expected_utils = {"trim", "split", "starts_with", "ends_with"}
        found_utils = function_names & expected_utils
        assert found_utils == expected_utils, f"Expected exactly {expected_utils}, found {found_utils}"

        # Verify exact table utility functions
        table_utils = {"deep_copy", "table_contains", "table_merge"}
        found_table_utils = function_names & table_utils
        assert found_table_utils == table_utils, f"Expected exactly {table_utils}, found {found_table_utils}"

        # Check for Logger class/table
        assert "Logger" in all_symbols or any("Logger" in s for s in all_symbols), "Logger not found in symbols"

    if language_has_verified_implementation_support(Language.LUA):

        @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.LUA)
            pos = find_identifier_position(repo_path / "src" / "animals.lua", "speak")
            assert pos is not None, "Could not find Animal:speak in fixture"

            implementations = language_server.request_implementation("src/animals.lua", *pos)
            assert implementations, "Expected at least one implementation of Animal:speak"
            assert any("animals.lua" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected Dog:speak in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.LUA)
            pos = find_identifier_position(repo_path / "src" / "animals.lua", "speak")
            assert pos is not None, "Could not find Animal:speak in fixture"

            implementing_symbols = language_server.request_implementing_symbols("src/animals.lua", *pos)
            assert implementing_symbols, "Expected implementing symbols for Animal:speak"
            assert any(
                symbol.get("name") == "speak" and "animals.lua" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected Dog:speak symbol, got: {implementing_symbols}"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_find_symbols_in_main(self, language_server: SolidLanguageServer) -> None:
        """Test finding functions in main.lua."""
        symbols = language_server.request_document_symbols("main.lua").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        function_names = set()

        for symbol in symbol_list:
            if isinstance(symbol, dict) and symbol.get("kind") == SymbolKind.Function:
                function_names.add(symbol.get("name", ""))

        # Verify exact main functions exist
        expected_funcs = {"print_banner", "test_calculator", "test_utils"}
        found_funcs = function_names & expected_funcs
        assert found_funcs == expected_funcs, f"Expected exactly {expected_funcs}, found {found_funcs}"

        assert "test_calculator" in function_names, "test_calculator function not found"
        assert "test_utils" in function_names, "test_utils function not found"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_cross_file_references_calculator_add(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to calculator.add function."""
        symbols = language_server.request_document_symbols("src/calculator.lua").get_all_symbols_and_roots()

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the add function
        add_symbol = None
        for sym in symbol_list:
            if isinstance(sym, dict):
                name = sym.get("name", "")
                if "add" in name or name == "add":
                    add_symbol = sym
                    break

        assert add_symbol is not None, "add function not found in calculator.lua"

        # Get references to the add function
        range_info = add_symbol.get("selectionRange", add_symbol.get("range"))
        assert range_info is not None, "add function has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/calculator.lua", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        # add function appears in: main.lua (lines 17, 78), test_calculator.lua (lines 22, 23, 24)
        # Note: The declaration itself may or may not be included as a reference
        assert len(refs) >= 5, f"Should find at least 5 references to calculator.add, found {len(refs)}"

        # Verify exact reference locations
        ref_files: dict[str, list[int]] = {}
        for ref in refs:
            filename = ref.get("uri", "").split("/")[-1]
            if filename not in ref_files:
                ref_files[filename] = []
            ref_files[filename].append(ref["range"]["start"]["line"])

        # The declaration may or may not be included
        if "calculator.lua" in ref_files:
            assert 5 in ref_files["calculator.lua"], (
                f"If declaration is included, it should be at line 6 (0-indexed: 5), found at {ref_files['calculator.lua']}"
            )

        # Check main.lua has usages
        assert "main.lua" in ref_files, "Should find add usages in main.lua"
        assert 16 in ref_files["main.lua"] or 77 in ref_files["main.lua"], (
            f"Should find add usage in main.lua, found at lines {ref_files.get('main.lua', [])}"
        )

        # Check for cross-file references from main.lua
        main_refs = [ref for ref in refs if "main.lua" in ref.get("uri", "")]
        assert len(main_refs) > 0, "calculator.add should be called in main.lua"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_cross_file_references_utils_trim(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to utils.trim function."""
        symbols = language_server.request_document_symbols("src/utils.lua").get_all_symbols_and_roots()

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the trim function
        trim_symbol = None
        for sym in symbol_list:
            if isinstance(sym, dict):
                name = sym.get("name", "")
                if "trim" in name or name == "trim":
                    trim_symbol = sym
                    break

        assert trim_symbol is not None, "trim function not found in utils.lua"

        # Get references to the trim function
        range_info = trim_symbol.get("selectionRange", trim_symbol.get("range"))
        assert range_info is not None, "trim function has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/utils.lua", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        # trim function appears in: usage (line 33 in main.lua)
        # Note: The declaration itself may or may not be included as a reference
        assert len(refs) >= 1, f"Should find at least 1 reference to utils.trim, found {len(refs)}"

        # Verify exact reference locations
        ref_files: dict[str, list[int]] = {}
        for ref in refs:
            filename = ref.get("uri", "").split("/")[-1]
            if filename not in ref_files:
                ref_files[filename] = []
            ref_files[filename].append(ref["range"]["start"]["line"])

        # The declaration may or may not be included
        if "utils.lua" in ref_files:
            assert 5 in ref_files["utils.lua"], (
                f"If declaration is included, it should be at line 6 (0-indexed: 5), found at {ref_files['utils.lua']}"
            )

        # Check main.lua has usage
        assert "main.lua" in ref_files, "Should find trim usage in main.lua"
        assert 32 in ref_files["main.lua"], (
            f"Should find trim usage at line 33 (0-indexed: 32) in main.lua, found at lines {ref_files.get('main.lua', [])}"
        )

        # Check for cross-file references from main.lua
        main_refs = [ref for ref in refs if "main.lua" in ref.get("uri", "")]
        assert len(main_refs) > 0, "utils.trim should be called in main.lua"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_hover_information(self, language_server: SolidLanguageServer) -> None:
        """Test hover information for symbols."""
        # Get hover info for a function
        hover_info = language_server.request_hover("src/calculator.lua", 5, 10)  # Position near add function

        assert hover_info is not None, "Should provide hover information"

        # Hover info could be a dict with 'contents' or a string
        if isinstance(hover_info, dict):
            assert "contents" in hover_info or "value" in hover_info, "Hover should have contents"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_full_symbol_tree(self, language_server: SolidLanguageServer) -> None:
        """Test that full symbol tree is not empty."""
        symbols = language_server.request_full_symbol_tree()

        assert symbols is not None
        assert len(symbols) > 0, "Symbol tree should not be empty"

        # The tree should have at least one root node
        root = symbols[0]
        assert isinstance(root, dict), "Root should be a dict"
        assert "name" in root, "Root should have a name"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_references_between_test_and_source(self, language_server: SolidLanguageServer) -> None:
        """Test finding references from test files to source files."""
        # Check if test_calculator.lua references calculator module
        test_symbols = language_server.request_document_symbols("tests/test_calculator.lua").get_all_symbols_and_roots()

        assert test_symbols is not None
        assert len(test_symbols) > 0

        # The test file should have some content that references calculator
        symbol_list = test_symbols[0] if isinstance(test_symbols, tuple) else test_symbols
        assert len(symbol_list) > 0, "test_calculator.lua should have symbols"

    @pytest.mark.parametrize("language_server", [Language.LUA], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(
                s,
                whitespace_allowed=s["name"] == " ",
                period_allowed="." in s["name"],
                colon_allowed=":" in s["name"],
            ):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
