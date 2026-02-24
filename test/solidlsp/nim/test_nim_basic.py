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

        # Verify that symbol body ranges span the full proc/type definition, not just the name.
        # nimlangserver returns SymbolInformation with ranges covering only the symbol name;
        # the range-fix logic should extend them to cover the full body.
        greet_symbol = next(s for s in function_symbols if s["name"] == "greet")
        body = greet_symbol.get("body")
        assert body is not None, "greet should have a body"
        body_text = body.get_text()
        assert "proc greet" in body_text, f"Body should contain the proc signature, got: {body_text!r}"
        assert "result =" in body_text, f"Body should contain the proc body, got: {body_text!r}"
        assert body._end_line > body._start_line, f"greet body should span multiple lines (start={body._start_line}, end={body._end_line})"

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
        """Test cross-file awareness using references and goto-definition.

        formatNumber is defined in utils.nim and called in main.nim.
        nimlangserver's request_references only returns usages within the queried
        file's nimsuggest instance, so we verify cross-file resolution via
        goto-definition (which correctly navigates from main.nim to utils.nim)
        combined with a reference query from the call site.
        """
        # Ensure main.nim is indexed
        language_server.request_document_symbols("main.nim")

        # Find the call to formatNumber in main.nim
        content = language_server.retrieve_full_file_content("main.nim")
        target_line = target_col = None
        for i, line in enumerate(content.split("\n")):
            col = line.find("formatNumber")
            if col >= 0:
                target_line, target_col = i, col
                break
        assert target_line is not None, "Could not find formatNumber call in main.nim"

        # Verify references finds the usage in main.nim
        refs = language_server.request_references("main.nim", target_line, target_col)
        ref_paths = [ref.get("relativePath", "") for ref in refs]
        assert any("main.nim" in p for p in ref_paths), f"Expected main.nim in references, got: {ref_paths}"

        # Verify goto-definition resolves to the definition in utils.nim (cross-file)
        definition = language_server.request_definition("main.nim", target_line, target_col)
        assert definition, "Should find definition for formatNumber"
        assert "utils.nim" in definition[0]["uri"], f"Definition should point to utils.nim, got: {definition[0]['uri']}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_goto_definition(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition from main.nim to utils.nim."""
        content = language_server.retrieve_full_file_content("main.nim")
        target_line = target_col = None
        for i, line in enumerate(content.split("\n")):
            col = line.find("formatNumber")
            if col >= 0:
                target_line, target_col = i, col
                break
        assert target_line is not None, "Could not find formatNumber call in main.nim"

        definition = language_server.request_definition("main.nim", target_line, target_col)
        assert definition, "Should find definition for formatNumber call"
        assert "utils.nim" in definition[0]["uri"], "Definition should point to utils.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_completions(self, language_server: SolidLanguageServer) -> None:
        """Test completion for Person fields after dot operator."""
        content = language_server.retrieve_full_file_content("main.nim")
        target_line = target_col = None
        for i, line in enumerate(content.split("\n")):
            col = line.find("p.email")
            if col >= 0:
                # Position cursor on the 'e' of 'email' (right after the dot)
                target_line, target_col = i, col + 2
                break
        assert target_line is not None, "Could not find p.email in main.nim"

        # nimlangserver filters completions by prefix at cursor, so at col of 'e' we get 'e'-prefixed fields
        completions = language_server.request_completions("main.nim", target_line, target_col)
        assert completions, "Should return completions"

        completion_labels = [item["completionText"] for item in completions]
        assert "email" in completion_labels, "Should suggest email field for Person type"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_hover(self, language_server: SolidLanguageServer) -> None:
        """Test that hover returns type/doc information for a symbol."""
        # Hover over the 'greet' proc definition in main.nim
        doc_symbols = language_server.request_document_symbols("main.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        greet_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "greet":
                greet_symbol = sym
                break
        assert greet_symbol is not None, "Could not find 'greet' symbol in main.nim"

        sel_start = greet_symbol["selectionRange"]["start"]
        hover_info = language_server.request_hover("main.nim", sel_start["line"], sel_start["character"])

        assert hover_info is not None, "Hover should return information for greet proc"
        assert "contents" in hover_info, "Hover should have contents"

        contents = hover_info["contents"]
        if isinstance(contents, str):
            hover_text = contents
        elif isinstance(contents, dict) and "value" in contents:
            hover_text = contents["value"]
        else:
            hover_text = str(contents)

        assert "greet" in hover_text, f"Hover should mention 'greet', got: {hover_text}"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_request_referencing_symbols_cross_file(self, language_server: SolidLanguageServer) -> None:
        """Test request_referencing_symbols finds cross-file usages.

        formatNumber is defined in utils.nim and called in main.nim.
        request_referencing_symbols should find the usage, either via LSP
        references or via the goto-definition fallback.
        """
        # Get the position of formatNumber's definition in utils.nim
        doc_symbols = language_server.request_document_symbols("utils.nim")
        all_symbols, _ = doc_symbols.get_all_symbols_and_roots()

        fmt_symbol = None
        for sym in all_symbols:
            if sym.get("name") == "formatNumber":
                fmt_symbol = sym
                break
        assert fmt_symbol is not None, "Could not find 'formatNumber' in utils.nim"

        sel_start = fmt_symbol["selectionRange"]["start"]
        refs = language_server.request_referencing_symbols(
            "utils.nim", sel_start["line"], sel_start["character"], include_file_symbols=True
        )

        # Should find at least one reference in main.nim
        ref_paths = [r.symbol["location"]["relativePath"] for r in refs]
        assert any("main.nim" in p for p in ref_paths), f"Expected main.nim in referencing symbols for formatNumber, got: {ref_paths}"
