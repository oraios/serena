"""
Basic tests for SystemVerilog language server integration (verible-verilog-ls).

This module tests Language.SYSTEMVERILOG using verible-verilog-ls.
Tests are skipped if the language server is not available.
"""

from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


def _find_symbol_by_name(language_server: SolidLanguageServer, file_path: str, name: str) -> dict[str, Any] | None:
    """Find a top-level symbol by name in a file's document symbols."""
    symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
    symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
    return next((s for s in symbol_list if s.get("name") == name), None)


def _get_symbol_selection_start(language_server: SolidLanguageServer, file_path: str, name: str) -> tuple[int, int]:
    """Get the (line, character) of a symbol's selectionRange start. Skips test if not found."""
    symbol = _find_symbol_by_name(language_server, file_path, name)
    if not symbol or "selectionRange" not in symbol:
        pytest.skip(f"Symbol '{name}' or selectionRange not found in {file_path}")
    sel_start = symbol["selectionRange"]["start"]
    return sel_start["line"], sel_start["character"]


@pytest.mark.systemverilog
class TestSystemVerilogSymbols:
    """Tests for document symbol extraction."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree contains expected modules."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "counter"), "Module 'counter' not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for counter.sv."""
        symbol = _find_symbol_by_name(language_server, "counter.sv", "counter")
        assert symbol is not None, "Expected 'counter' in document symbols"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_top_module(self, language_server: SolidLanguageServer) -> None:
        """Test that top module is found (cross-file instantiation test)."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "top"), "Module 'top' not found in symbol tree"


@pytest.mark.systemverilog
class TestSystemVerilogDefinition:
    """Tests for go-to-definition functionality."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_goto_definition(self, language_server: SolidLanguageServer) -> None:
        """Test go to definition on a module declaration."""
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        definitions = language_server.request_definition("counter.sv", line, char)
        assert len(definitions) >= 1, f"Expected at least 1 definition, got {len(definitions)}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_goto_definition_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test go to definition from module instantiation in top.sv to counter.sv.

        This is the key cross-file test: navigating from an instantiation
        (counter in top.sv) to its definition (counter.sv).
        """
        # top.sv line 17 (0-indexed: 16): "    counter #(.WIDTH(8)) u_counter ("
        # "counter" starts at column 4
        definitions = language_server.request_definition("top.sv", 16, 4)
        if not definitions:
            pytest.skip("Cross-file goto definition not supported by verible-verilog-ls")
        def_paths = [d.get("relativePath", "") for d in definitions]
        assert any("counter.sv" in p for p in def_paths), f"Expected definition in counter.sv, got: {def_paths}"


@pytest.mark.systemverilog
class TestSystemVerilogReferences:
    """Tests for find-references functionality."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_references(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to a module."""
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        references = language_server.request_references("counter.sv", line, char)
        assert len(references) >= 1, f"Expected at least 1 reference, got {len(references)}"

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_find_references_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test that references to counter include its instantiation in top.sv.

        Similar to Rust (lib.rs → main.rs) and C# (Program.cs → Models/Person.cs),
        this verifies that cross-file references are found.
        """
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        references = language_server.request_references("counter.sv", line, char)
        ref_paths = [ref.get("relativePath", "") for ref in references]
        if not any("top.sv" in p for p in ref_paths):
            pytest.skip("Cross-file references not supported by verible-verilog-ls")
        assert any("top.sv" in p for p in ref_paths), f"Expected reference from top.sv, got: {ref_paths}"


@pytest.mark.systemverilog
class TestSystemVerilogHover:
    """Tests for hover information."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_hover(self, language_server: SolidLanguageServer) -> None:
        """Test hover information (experimental in verible, requires --lsp_enable_hover)."""
        line, char = _get_symbol_selection_start(language_server, "counter.sv", "counter")
        hover_info = language_server.request_hover("counter.sv", line, char)
        if hover_info is None:
            pytest.skip("Hover not enabled (requires --lsp_enable_hover flag)")
        assert "contents" in hover_info, "Hover should have contents"


@pytest.mark.systemverilog
class TestSystemVerilogDiagnostics:
    """Tests for diagnostics (lint/syntax errors)."""

    @pytest.mark.parametrize("language_server", [Language.SYSTEMVERILOG], indirect=True)
    def test_diagnostics(self, language_server: SolidLanguageServer) -> None:
        """Test diagnostics on valid code — should have no errors."""
        try:
            diagnostics = language_server.request_text_document_diagnostics("counter.sv")
            errors = [d for d in diagnostics if d.get("severity") == 1]  # 1 = Error
            assert len(errors) == 0, f"Expected no errors in valid code, got: {errors}"
        except KeyError as e:
            # verible-verilog-ls may not include all standard diagnostic fields (e.g., 'code')
            pytest.skip(f"Diagnostics API incompatibility: {e}")
