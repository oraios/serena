"""
Basic tests for C/C++ language server integration (clangd and ccls).

This module tests both Language.CPP (clangd) and Language.CPP_CCLS (ccls)
using the same test repository. Tests are skipped if the respective language
server is not available.
"""

import os
import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


def _ccls_available() -> bool:
    return shutil.which("ccls") is not None


_cpp_servers: list[Language] = [Language.CPP]
if _ccls_available():
    _cpp_servers.append(Language.CPP_CCLS)


@pytest.mark.cpp
@pytest.mark.skipif(not _cpp_servers, reason="No C++ language server (clangd or ccls) available")
class TestCppLanguageServer:
    """Tests for C/C++ language servers (clangd and ccls)."""

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that symbol tree contains expected functions."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "Function 'add' not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "Function 'main' not found in symbol tree"

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test document symbols for a.cpp."""
        file_path = os.path.join("a.cpp")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        # Flatten nested structure if needed
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        names = [s.get("name") for s in symbol_list]
        assert "main" in names, f"Expected 'main' in document symbols, got: {names}"

    @pytest.mark.parametrize("language_server", _cpp_servers, indirect=True)
    def test_find_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to 'add' function across files."""
        # Locate 'add' in b.cpp
        file_path = os.path.join("b.cpp")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        add_symbol = None
        for sym in symbol_list:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in b.cpp"

        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        ref_files = [ref.get("relativePath", "") for ref in refs]
        assert any("a.cpp" in ref_file for ref_file in ref_files), f"Should find reference in a.cpp, {refs=}"

        # Verify second call returns same results (stability check)
        def _ref_key(ref: dict) -> tuple:
            rp = ref.get("relativePath", "")
            rng = ref.get("range") or {}
            s = rng.get("start") or {}
            e = rng.get("end") or {}
            return (
                rp,
                s.get("line", -1),
                s.get("character", -1),
                e.get("line", -1),
                e.get("character", -1),
            )

        refs2 = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert sorted(map(_ref_key, refs2)) == sorted(map(_ref_key, refs)), "Reference results should be stable across calls"
