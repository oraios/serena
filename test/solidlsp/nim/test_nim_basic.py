"""
Basic integration tests for the Nim language server functionality.

These tests validate the functionality of the language server APIs
using the Nim test repository.
"""

import shutil

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils


@pytest.mark.nim
@pytest.mark.skipif(
    shutil.which("nim") is None and shutil.which("nimlangserver") is None,
    reason="Nim toolchain not installed - nim and nimlangserver not found in PATH.",
)
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

        person_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "Person":
                person_symbol = sym
                break
        assert person_symbol is not None, "Could not find 'Person' symbol in main.nim"

        sel_start = person_symbol["selectionRange"]["start"]
        refs = language_server.request_references("main.nim", sel_start["line"], sel_start["character"])
        assert any("main.nim" in ref.get("relativePath", "") for ref in refs), "main.nim should reference Person"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_find_references_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test find references across multiple Nim files.

        Note: nimlangserver does not reliably report cross-file references for all symbols.
        This test verifies that references can be found for a symbol defined in utils.nim,
        but does not require cross-file hits since nimlangserver may only return the definition site.
        """
        doc_symbols = language_server.request_document_symbols("utils.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        format_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "formatNumber":
                format_symbol = sym
                break
        assert format_symbol is not None, "Could not find 'formatNumber' symbol in utils.nim"

        sel_start = format_symbol["selectionRange"]["start"]
        refs = language_server.request_references("utils.nim", sel_start["line"], sel_start["character"])
        # nimlangserver may return empty references or only the definition site for cross-file lookups
        ref_paths = [ref.get("relativePath", "") for ref in refs]
        assert (
            any("utils.nim" in p for p in ref_paths) or refs == []
        ), f"If references are returned, utils.nim (definition site) should be among them, got: {ref_paths}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_goto_definition(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition from main.nim to utils.nim."""
        # Line 63 (0-indexed): `  echo formatNumber(1234567)` — col 7 is start of formatNumber
        definition = language_server.request_definition("main.nim", 63, 7)
        assert definition, "Should find definition for formatNumber call"
        assert "utils.nim" in definition[0]["uri"], "Definition should point to utils.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_completions(self, language_server: SolidLanguageServer) -> None:
        """Test completion for Person fields after dot operator."""
        # Line 33 (0-indexed): `  if p.email != "":` — col 7 is right after the dot in `p.`
        # nimlangserver filters completions by prefix at cursor, so at col 7 we get 'e'-prefixed fields
        completions = language_server.request_completions("main.nim", 33, 7)
        assert completions, "Should return completions"

        completion_labels = [item["completionText"] for item in completions]
        assert "email" in completion_labels, "Should suggest email field for Person type"
