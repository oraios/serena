import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import (
    find_identifier_position,
    get_repo_path,
    language_has_verified_implementation_support,
    language_tests_enabled,
)

pytestmark = [pytest.mark.java, pytest.mark.skipif(not language_tests_enabled(Language.JAVA), reason="Java tests disabled")]


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
        assert any("Main.java" in ref.get("relativePath", "") for ref in refs), (
            "Main should reference Model (tried all positions in selectionRange)"
        )

    @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
    def test_overview_methods(self, language_server: SolidLanguageServer) -> None:
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Main"), "Main missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Utils"), "Utils missing from overview"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Model"), "Model missing from overview"

    if language_has_verified_implementation_support(Language.JAVA):

        @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.JAVA)
            pos = find_identifier_position(repo_path / "src/main/java/test_repo/Greeter.java", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementations = language_server.request_implementation("src/main/java/test_repo/Greeter.java", *pos)
            assert implementations, "Expected at least one implementation of Greeter.formatGreeting"
            assert any("ConsoleGreeter.java" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.formatGreeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.JAVA], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.JAVA)
            pos = find_identifier_position(repo_path / "src/main/java/test_repo/Greeter.java", "formatGreeting")
            assert pos is not None, "Could not find Greeter.formatGreeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols("src/main/java/test_repo/Greeter.java", *pos)
            assert implementing_symbols, "Expected implementing symbols for Greeter.formatGreeting"
            assert any(
                symbol.get("name") == "formatGreeting" and "ConsoleGreeter.java" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.formatGreeting symbol, got: {implementing_symbols}"
