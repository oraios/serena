import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import is_ci


# Kotlin LSP (IntelliJ-based, pre-alpha v261) crashes on JVM restart under CI resource constraints
# (2 CPUs, 7GB RAM). First start succeeds but subsequent starts fail with cancelled (-32800).
# Tests pass reliably on developer machines. See PR #1061 for investigation details.
@pytest.mark.skipif(is_ci, reason="Kotlin LSP JVM restart is unstable on CI runners")
@pytest.mark.kotlin
class TestKotlinLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.KOTLIN], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model class not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.KOTLIN], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        # Use correct Kotlin file paths
        file_path = os.path.join("src", "main", "kotlin", "test_repo", "Utils.kt")
        refs = language_server.request_references(file_path, 3, 12)
        assert any("Main.kt" in ref.get("relativePath", "") for ref in refs), "Main should reference Utils.printHello"

        # Dynamically determine the correct line/column for the 'Model' class name
        file_path = os.path.join("src", "main", "kotlin", "test_repo", "Model.kt")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        model_symbol = None
        for sym in symbols[0]:
            print(sym)
            print("\n")
            if sym.get("name") == "Model" and sym.get("kind") == 23:  # 23 = Class
                model_symbol = sym
                break
        assert model_symbol is not None, "Could not find 'Model' class symbol in Model.kt"
        # Use selectionRange if present, otherwise fall back to range
        if "selectionRange" in model_symbol:
            sel_start = model_symbol["selectionRange"]["start"]
        else:
            sel_start = model_symbol["range"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any(
            "Main.kt" in ref.get("relativePath", "") for ref in refs
        ), "Main should reference Model (tried all positions in selectionRange)"

    @pytest.mark.parametrize("language_server", [Language.KOTLIN], indirect=True)
    def test_overview_methods(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model missing from overview"

    @pytest.mark.parametrize("language_server", [Language.KOTLIN], indirect=True)
    def test_hover(self, language_server: SolidLanguageServer) -> None:
        """Test that hover (include_info) returns information for Kotlin symbols.

        Verifies the _request_hover retry logic that handles the Kotlin LSP's
        lazy-loading behaviour (hover may return None on the first request
        after didOpen).
        """
        file_path = os.path.join("src", "main", "kotlin", "test_repo", "Utils.kt")
        doc_symbols = language_server.request_document_symbols(file_path)
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        # Find the Utils object symbol
        utils_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "Utils":
                utils_symbol = sym
                break
        assert utils_symbol is not None, "Utils symbol not found in Utils.kt"

        # Use selectionRange (identifier position) for hover
        sel_start = utils_symbol.get("selectionRange", utils_symbol.get("range", {}))["start"]
        line = sel_start["line"]
        col = sel_start["character"]

        hover = language_server.request_hover(file_path, line, col)
        if hover is None:
            # Kotlin LSP (IntelliJ-based, early versions like v261) may return null for hover
            # even after our retry loop. This is a known limitation; the retry logic in
            # KotlinLanguageServer._request_hover handles future versions that improve hover support.
            pytest.skip("Kotlin LSP hover returned None - hover not yet supported in this LSP version")

        contents = hover.get("contents")
        assert contents, "Hover contents are empty"

        # Extract text regardless of format (MarkupContent dict, MarkedString list, or plain string)
        if isinstance(contents, dict):
            text = contents.get("value", "")
        elif isinstance(contents, list):
            text = " ".join(p if isinstance(p, str) else p.get("value", "") for p in contents)
        else:
            text = str(contents)
        assert text.strip(), "Hover text is empty"

    @pytest.mark.parametrize("language_server", [Language.KOTLIN], indirect=True)
    def test_dir_overview(self, language_server: SolidLanguageServer) -> None:
        result = language_server.request_dir_overview("src/main/kotlin/test_repo")
        print(f"dir_overview keys: {list(result.keys())}")
        for k, v in result.items():
            print(f"  {k}: {[s.get('name') for s in v]}")
        assert len(result) > 0, "Directory overview should return symbols for at least one file"
        # Should find symbols from all 4 .kt files
        all_symbol_names = set()
        for symbols in result.values():
            for s in symbols:
                all_symbol_names.add(s.get("name"))
        assert "Main" in all_symbol_names, "Main should be in directory overview"
        assert "Utils" in all_symbol_names, "Utils should be in directory overview"
        assert "Model" in all_symbol_names, "Model should be in directory overview"
