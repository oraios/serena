"""
Basic integration tests for the Nim language server functionality.

These tests validate the functionality of the language server APIs
using the Nim test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.nim
class TestNimLanguageServerBasics:
    """Test basic functionality of the Nim language server."""

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that Nim language server can find symbols across the project."""
        symbols = language_server.request_full_symbol_tree()
        assert SymbolUtils.symbol_tree_contains_name(symbols, "greet"), "greet procedure not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "calculate"), "calculate procedure not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "processData"), "processData procedure not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "newPerson"), "newPerson procedure not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Person"), "Person type not found"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Animal"), "Animal type not found"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for Nim files."""
        doc_symbols = language_server.request_document_symbols("main.nim")
        all_symbols, root_symbols = doc_symbols.get_all_symbols_and_roots()

        # Extract function symbols (LSP Symbol Kind 12)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        assert "greet" in function_names, "Should find greet procedure"
        assert "calculate" in function_names, "Should find calculate procedure"
        assert "processData" in function_names, "Should find processData procedure"
        assert "newPerson" in function_names, "Should find newPerson procedure"
        assert "describe" in function_names, "Should find describe procedure"
        assert "newAnimal" in function_names, "Should find newAnimal procedure"
        assert "speak" in function_names, "Should find speak procedure"

        # Extract type symbols (LSP Symbol Kind 5 for Class, 23 for Struct)
        type_symbols = [symbol for symbol in all_symbols if symbol.get("kind") in [5, 23]]
        type_names = [symbol["name"] for symbol in type_symbols]

        assert "Person" in type_names, "Should find Person type"
        assert "Animal" in type_names, "Should find Animal type"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_utils_module(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in utils.nim module."""
        doc_symbols = language_server.request_document_symbols("utils.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        expected_utils_functions = [
            "formatNumber",
            "reverseString",
            "isPalindrome",
            "fibonacci",
            "factorial",
            "gcd",
            "lcm",
            "mapSeq",
        ]

        for func_name in expected_utils_functions:
            assert func_name in function_names, f"Should find {func_name} procedure in utils.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_types_module(self, language_server: SolidLanguageServer) -> None:
        """Test type detection in types.nim module."""
        doc_symbols = language_server.request_document_symbols("types.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        type_symbols = [symbol for symbol in all_symbols if symbol.get("kind") in [5, 23, 10]]
        type_names = [symbol["name"] for symbol in type_symbols]

        expected_types = ["Point", "Rectangle", "Shape", "Circle", "Triangle", "Color", "Status", "Result", "Database"]
        for type_name in expected_types:
            assert type_name in type_names, f"Should find {type_name} type in types.nim"

        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Note: 'draw' is defined as 'method', not 'proc' — nimlangserver does NOT report methods
        expected_procs = [
            "newPoint",
            "toString",
            "distance",
            "newRectangle",
            "area",
            "perimeter",
            "contains",
            "ok",
            "err",
            "isOk",
            "isErr",
            "newDatabase",
            "set",
            "get",
            "delete",
        ]

        for proc_name in expected_procs:
            assert proc_name in function_names, f"Should find {proc_name} procedure in types.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test find references functionality for Nim within a single file."""
        doc_symbols = language_server.request_document_symbols("main.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        # Find the Person type symbol
        person_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "Person":
                person_symbol = sym
                break

        if person_symbol is not None:
            sel_start = person_symbol["selectionRange"]["start"]
            refs = language_server.request_references("main.nim", sel_start["line"], sel_start["character"])
            assert refs, "Should find at least one reference to Person"
            assert any("main.nim" in ref.get("relativePath", "") for ref in refs), "main.nim should reference Person"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test find references across multiple Nim files."""
        # Find formatNumber in utils.nim and check if it's referenced in main.nim
        doc_symbols = language_server.request_document_symbols("utils.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        format_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "formatNumber":
                format_symbol = sym
                break

        if format_symbol is not None:
            sel_start = format_symbol["selectionRange"]["start"]
            refs = language_server.request_references("utils.nim", sel_start["line"], sel_start["character"])
            if refs:
                ref_files = [ref.get("relativePath", "") for ref in refs]
                assert any("main.nim" in f for f in ref_files), "Expected to find usage of formatNumber in main.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_goto_definition(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition functionality for Nim."""
        definition = language_server.request_definition("main.nim", 58, 8)

        if definition:
            assert isinstance(definition, list), "Definition should be a list"
            assert len(definition) > 0, "Should find at least one definition"
            first_def = definition[0]
            if "uri" in first_def:
                assert "utils.nim" in first_def["uri"], "Definition should point to utils.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_completions(self, language_server: SolidLanguageServer) -> None:
        """Test completion functionality for Nim."""
        completions = language_server.request_completions("main.nim", 31, 14)

        if completions:
            assert "items" in completions, "Completions should have items"
            items = completions["items"]
            assert len(items) > 0, "Should provide at least one completion"

            completion_labels = [item["label"] for item in items]
            expected_fields = ["name", "age", "email"]
            for field_name in expected_fields:
                assert field_name in completion_labels, f"Should suggest {field_name} field for Person type"
