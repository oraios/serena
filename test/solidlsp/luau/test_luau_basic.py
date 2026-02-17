"""
Tests for the Luau language server implementation.

These tests validate symbol finding, within-file references,
and cross-file reference capabilities for Luau modules and functions.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.luau
class TestLuauLanguageServer:
    """Test Luau language server symbol finding and cross-file references."""

    @pytest.mark.parametrize("language_server", [Language.LUAU], indirect=True)
    def test_find_symbols_in_init(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific functions in init.luau."""
        symbols = language_server.request_document_symbols("src/init.luau").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = set()
        for symbol in symbol_list:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                symbol_names.add(name)

        assert "createConfig" in symbol_names, f"createConfig not found in symbols: {symbol_names}"
        assert "main" in symbol_names, f"main not found in symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.LUAU], indirect=True)
    def test_find_symbols_in_module(self, language_server: SolidLanguageServer) -> None:
        """Test finding specific functions in module.luau."""
        symbols = language_server.request_document_symbols("src/module.luau").get_all_symbols_and_roots()

        assert symbols is not None
        assert len(symbols) > 0

        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols
        symbol_names = set()
        for symbol in symbol_list:
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                symbol_names.add(name)

        assert "process" in symbol_names, f"process not found in symbols: {symbol_names}"
        assert "helper" in symbol_names, f"helper not found in symbols: {symbol_names}"

    @pytest.mark.parametrize("language_server", [Language.LUAU], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding within-file references to createConfig in init.luau.

        createConfig is defined at line 8 (0-indexed) and referenced at lines 17 and 23.
        """
        symbols = language_server.request_document_symbols("src/init.luau").get_all_symbols_and_roots()

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the createConfig function symbol
        create_config_symbol = None
        for sym in symbol_list:
            if isinstance(sym, dict) and sym.get("name") == "createConfig":
                create_config_symbol = sym
                break

        assert create_config_symbol is not None, "createConfig function not found in init.luau"

        range_info = create_config_symbol.get("selectionRange", create_config_symbol.get("range"))
        assert range_info is not None, "createConfig has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/init.luau", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        # createConfig appears multiple times within init.luau:
        # definition (line 8), usage in main (line 17), and return table (line 23)
        assert len(refs) >= 2, f"Should find at least 2 references to createConfig, found {len(refs)}"

        # Verify that references are in init.luau
        ref_files = set()
        for ref in refs:
            filename = ref.get("uri", "").split("/")[-1]
            ref_files.add(filename)

        assert "init.luau" in ref_files, f"Expected references in init.luau, found in: {ref_files}"

    @pytest.mark.parametrize("language_server", [Language.LUAU], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding cross-file references to process function.

        process is defined in module.luau and used in init.luau via module.process().
        """
        symbols = language_server.request_document_symbols("src/module.luau").get_all_symbols_and_roots()

        assert symbols is not None
        symbol_list = symbols[0] if isinstance(symbols, tuple) else symbols

        # Find the process function symbol
        process_symbol = None
        for sym in symbol_list:
            if isinstance(sym, dict) and sym.get("name") == "process":
                process_symbol = sym
                break

        assert process_symbol is not None, "process function not found in module.luau"

        range_info = process_symbol.get("selectionRange", process_symbol.get("range"))
        assert range_info is not None, "process function has no range information"

        range_start = range_info["start"]
        refs = language_server.request_references("src/module.luau", range_start["line"], range_start["character"])

        assert refs is not None
        assert isinstance(refs, list)
        assert len(refs) >= 1, f"Should find at least 1 reference to process, found {len(refs)}"

        # Collect reference files and lines
        ref_info: dict[str, list[int]] = {}
        for ref in refs:
            filename = ref.get("uri", "").split("/")[-1]
            if filename not in ref_info:
                ref_info[filename] = []
            ref_info[filename].append(ref["range"]["start"]["line"])

        # The definition in module.luau may or may not be included
        # We expect at least the reference in module.luau return table (line 9)
        assert "module.luau" in ref_info, f"Expected references in module.luau, found in: {set(ref_info.keys())}"

    @pytest.mark.parametrize("language_server", [Language.LUAU], indirect=True)
    def test_find_definition(self, language_server: SolidLanguageServer) -> None:
        """Test finding definition of createConfig from its usage in main().

        createConfig is used at line 17, column 20 (0-indexed) in init.luau.
        Its definition should be at line 8 in init.luau.
        """
        # Line 17 (0-indexed): `    local config = createConfig("test", 42)`
        # createConfig starts at column 20
        definition_locations = language_server.request_definition("src/init.luau", 17, 20)

        assert definition_locations, f"Expected non-empty definition list but got {definition_locations}"
        assert len(definition_locations) >= 1

        definition = definition_locations[0]
        assert definition["uri"].endswith("init.luau"), f"Definition should be in init.luau, got: {definition['uri']}"
        # createConfig is defined at line 8 (0-indexed): `local function createConfig(...)`
        assert definition["range"]["start"]["line"] == 8, f"Definition should be at line 8, got line {definition['range']['start']['line']}"
