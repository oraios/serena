"""
Basic tests for SystemVerilog language server integration (verible-verilog-ls).

This module tests Language.SYSTEMVERILOG using verible-verilog-ls.
Tests are skipped if the language server is not available.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.systemverilog
class TestSystemVerilogLanguageServer:
    """Tests for SystemVerilog language server (verible-verilog-ls)."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree contains expected modules."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "counter"), "Module 'counter' not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for counter.sv."""
        file_path = "counter.sv"
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        names = [s.get("name") for s in symbol_list]
        assert "counter" in names, f"Expected 'counter' in document symbols, got: {names}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_alu_module(self, language_server: SolidLanguageServer) -> None:
        """Test that ALU module is found."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "alu"), "Module 'alu' not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_get_alu_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for alu.sv."""
        file_path = "alu.sv"
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        names = [s.get("name") for s in symbol_list]
        assert "alu" in names, f"Expected 'alu' in document symbols, got: {names}"
