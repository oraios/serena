import os
import shutil
from typing import cast

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


def _ccls_available() -> bool:
    try:
        import shutil as _sh
        return _sh.which("ccls") is not None
    except Exception:
        return False


@pytest.mark.cpp
@pytest.mark.skipif(not _ccls_available(), reason="ccls not installed; skipping ccls tests")
class TestCclsLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.CPP_CCLS], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "Function 'add' not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "Function 'main' not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.CPP_CCLS], indirect=True)
    def test_get_document_symbols(self, language_server: SolidLanguageServer) -> None:
        file_path = os.path.join("a.cpp")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        # Flatten nested structure if need
        symbol_list = symbols[0] if symbols and isinstance(symbols[0], list) else symbols
        names = [s.get("name") for s in symbol_list]
        assert "main" in names

    @pytest.mark.parametrize("language_server", [Language.CPP_CCLS], indirect=True)
    def test_find_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
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
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)
        ref_files = cast(list[str], [ref.get("relativePath", "") for ref in refs])
        assert any("a.cpp" in ref_file for ref_file in ref_files), "Should find reference in a.cpp"
        # second call stability
        refs2 = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)
        assert refs2 == refs
