import os

import pytest

from multilspy.multilspy_config import Language


def find_symbol_recursive(symbols, name):
    for symbol in symbols:
        if symbol.get("name") == name:
            return True
        if symbol.get("children"):
            if find_symbol_recursive(symbol["children"], name):
                return True
    return False


class TestJavaLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_find_symbol(self, language_server):
        symbols = language_server.request_full_symbol_tree()
        assert find_symbol_recursive(symbols, "Main"), "Main class not found in symbol tree"
        assert find_symbol_recursive(symbols, "Utils"), "Utils class not found in symbol tree"
        assert find_symbol_recursive(symbols, "Model"), "Model class not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_find_referencing_symbols(self, language_server):
        # Use correct Maven/Java file paths
        file_path = os.path.join("src", "main", "java", "test_repo", "Utils.java")
        refs = language_server.request_references(file_path, 4, 20)
        assert any("Main.java" in ref.get("relativePath", "") for ref in refs), "Main should reference Utils.printHello"

        # Dynamically determine the correct line/column for the 'Model' class name
        file_path = os.path.join("src", "main", "java", "test_repo", "Model.java")
        symbols = language_server.request_document_symbols(file_path)
        model_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "Model" and sym.get("kind") == 5:  # 5 = Class
                model_symbol = sym
                break
        assert model_symbol is not None, "Could not find 'Model' class symbol in Model.java"
        # Use selectionRange if present, otherwise fall back to range
        if "selectionRange" in model_symbol:
            sel_start = model_symbol["selectionRange"]["start"]
            sel_end = model_symbol["selectionRange"]["end"]
        else:
            sel_start = model_symbol["range"]["start"]
            sel_end = model_symbol["range"]["end"]
        found = False
        if sel_start["line"] == sel_end["line"]:
            for col in range(sel_start["character"], sel_end["character"] + 1):
                refs = language_server.request_references(file_path, sel_start["line"], col)
                if any("Main.java" in ref.get("relativePath", "") for ref in refs):
                    found = True
        else:
            refs_start = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
            refs_end = language_server.request_references(file_path, sel_end["line"], sel_end["character"])
            if any("Main.java" in ref.get("relativePath", "") for ref in refs_start + refs_end):
                found = True
        assert found, "Main should reference Model (tried all positions in selectionRange)"

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_overview_methods(self, language_server):
        symbols = language_server.request_full_symbol_tree()
        assert find_symbol_recursive(symbols, "Main"), "Main missing from overview"
        assert find_symbol_recursive(symbols, "Utils"), "Utils missing from overview"
        assert find_symbol_recursive(symbols, "Model"), "Model missing from overview"
