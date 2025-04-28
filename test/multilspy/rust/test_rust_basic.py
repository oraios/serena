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


class TestRustLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_find_references_raw(self, language_server):
        # Directly test the request_references method for the add function
        file_path = os.path.join("src", "lib.rs")
        symbols = language_server.request_document_symbols(file_path)
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in lib.rs"
        sel_start = add_symbol["selectionRange"]["start"]
        sel_end = add_symbol["selectionRange"]["end"]
        found = False
        if sel_start["line"] == sel_end["line"]:
            for col in range(sel_start["character"], sel_end["character"] + 1):
                refs = language_server.request_references(file_path, sel_start["line"], col)
                # f"Raw request_references for add in lib.rs at col {col}: {refs}")
                if any("main.rs" in ref.get("relativePath", "") for ref in refs):
                    found = True
        else:
            refs_start = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
            refs_end = language_server.request_references(file_path, sel_end["line"], sel_end["character"])
            # f"Raw request_references for add in lib.rs at selectionRange start: {refs_start}")
            # f"Raw request_references for add in lib.rs at selectionRange end: {refs_end}")
            if any("main.rs" in ref.get("relativePath", "") for ref in refs_start + refs_end):
                found = True
        assert found, "main.rs should reference add (raw, tried all positions in selectionRange)"

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_find_symbol(self, language_server):
        symbols = language_server.request_full_symbol_tree()
        assert find_symbol_recursive(symbols, "main"), "main function not found in symbol tree"
        assert find_symbol_recursive(symbols, "add"), "add function not found in symbol tree"
        # Add more as needed based on test_repo

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_find_referencing_symbols(self, language_server):
        # Find references to 'add' defined in lib.rs, should be referenced from main.rs
        file_path = os.path.join("src", "lib.rs")
        symbols = language_server.request_document_symbols(file_path)
        add_symbol = None
        for sym in symbols[0]:
            if sym.get("name") == "add":
                add_symbol = sym
                break
        assert add_symbol is not None, "Could not find 'add' function symbol in lib.rs"
        sel_start = add_symbol["selectionRange"]["start"]
        sel_end = add_symbol["selectionRange"]["end"]
        # f"add symbol selectionRange: start={sel_start}, end={sel_end}")
        found = False
        # Try all character positions in the selectionRange (same line, from start to end character)
        if sel_start["line"] == sel_end["line"]:
            for col in range(sel_start["character"], sel_end["character"] + 1):
                refs = language_server.request_references(file_path, sel_start["line"], col)
                # f"References for add in lib.rs at col {col} (selectionRange): {refs}")
                if any("main.rs" in ref.get("relativePath", "") for ref in refs):
                    found = True
        else:
            # If the function name spans multiple lines, try start and end
            refs_start = language_server.request_references(file_path, sel_start["line"], sel_start["character"])
            refs_end = language_server.request_references(file_path, sel_end["line"], sel_end["character"])
            # f"References for add in lib.rs at selectionRange start: {refs_start}")
            # f"References for add in lib.rs at selectionRange end: {refs_end}")
            if any("main.rs" in ref.get("relativePath", "") for ref in refs_start + refs_end):
                found = True
        assert found, "main.rs should reference add (tried all positions in selectionRange)"

    @pytest.mark.parametrize("language_server", [Language.RUST], indirect=True)
    def test_overview_methods(self, language_server):
        symbols = language_server.request_full_symbol_tree()
        assert find_symbol_recursive(symbols, "main"), "main missing from overview"
        assert find_symbol_recursive(symbols, "add"), "add missing from overview"
