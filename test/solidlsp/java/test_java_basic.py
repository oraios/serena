import os
import platform

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils

# These marks will be applied to all tests in this module.
# We skip the tests if not on Windows (CI hangs on Ubuntu for unknown reasons; testing on Windows is sufficient)
is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
java_tests_enabled = not is_ci or platform.system() == "Windows"
pytestmark = [pytest.mark.java, pytest.mark.skipif(not java_tests_enabled, reason="Java tests are only run on Windows in CI")]


class TestJavaLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils class not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model class not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        # Use correct Maven/Java file paths
        file_path = os.path.join("src", "main", "java", "test_repo", "Utils.java")
        refs = language_server.request_references(file_path, 4, 20)
        assert any("Main.java" in ref.get("relativePath", "") for ref in refs), "Main should reference Utils.printHello"

        # Dynamically determine the correct line/column for the 'Model' class name
        file_path = os.path.join("src", "main", "java", "test_repo", "Model.java")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()
        model_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Model" and sym.get("kind") == 5:  # 5 = Class
                model_symbol = sym
                break
        assert model_symbol is not None, "Could not find 'Model' class symbol in Model.java"
        # Use selectionRange if present, otherwise fall back to range
        if "selectionRange" in model_symbol:
            sel_start = model_symbol["selectionRange"]["start"]
        else:
            sel_start = model_symbol["range"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
        assert any(
            "Main.java" in ref.get("relativePath", "") for ref in refs
        ), "Main should reference Model (tried all positions in selectionRange)"

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_overview_methods(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model missing from overview"
