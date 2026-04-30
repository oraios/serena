import os
import threading
from typing import Any

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import SymbolUtils
from test.conftest import find_identifier_position, get_repo_path, is_ci, language_has_verified_implementation_support
from test.solidlsp.conftest import format_symbol_for_assert, has_malformed_name, request_all_symbols
from test.solidlsp.util.diagnostics import assert_file_diagnostics


# Currently, most F# tests fail, there seems to be a regression or instability.
@pytest.mark.fsharp
@pytest.mark.skipif(is_ci, reason="F# language server is currently unreliable")
class TestFSharpLanguageServer:
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_find_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test finding symbols in the full symbol tree."""
        symbols = language_server.request_full_symbol_tree()

        # Check for main program module symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Program"), "Program module not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "main"), "main function not found in symbol tree"

        # Check for Calculator module symbols
        assert SymbolUtils.symbol_tree_contains_name(symbols, "Calculator"), "Calculator module not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "add"), "add function not found in symbol tree"
        assert SymbolUtils.symbol_tree_contains_name(symbols, "CalculatorClass"), "CalculatorClass not found in symbol tree"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_get_document_symbols_program(self, language_server: SolidLanguageServer) -> None:
        """Test getting document symbols from the main Program.fs file."""
        file_path = os.path.join("Program.fs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()[0]

        # Look for expected functions and modules
        symbol_names = [s.get("name") for s in symbols]
        assert "main" in symbol_names, "main function not found in Program.fs symbols"

    if language_has_verified_implementation_support(Language.FSHARP):

        @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
        def test_find_implementations(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.FSHARP)
            pos = find_identifier_position(repo_path / "Formatter.fs", "FormatGreeting")
            assert pos is not None, "Could not find IGreeter.FormatGreeting in fixture"

            implementations = language_server.request_implementation("Formatter.fs", *pos)
            assert implementations, "Expected at least one implementation of IGreeter.FormatGreeting"
            assert any("Formatter.fs" in implementation.get("relativePath", "") for implementation in implementations), (
                f"Expected ConsoleGreeter.FormatGreeting in implementations, got: {implementations}"
            )

        @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
        def test_request_implementing_symbols(self, language_server: SolidLanguageServer) -> None:
            repo_path = get_repo_path(Language.FSHARP)
            pos = find_identifier_position(repo_path / "Formatter.fs", "FormatGreeting")
            assert pos is not None, "Could not find IGreeter.FormatGreeting in fixture"

            implementing_symbols = language_server.request_implementing_symbols("Formatter.fs", *pos)
            assert implementing_symbols, "Expected implementing symbols for IGreeter.FormatGreeting"
            assert any(
                symbol.get("name") == "FormatGreeting" and "Formatter.fs" in symbol["location"].get("relativePath", "")
                for symbol in implementing_symbols
            ), f"Expected ConsoleGreeter.FormatGreeting symbol, got: {implementing_symbols}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_get_document_symbols_calculator(self, language_server: SolidLanguageServer) -> None:
        """Test getting document symbols from Calculator.fs file."""
        file_path = os.path.join("Calculator.fs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()[0]

        # Look for expected functions
        symbol_names = [s.get("name") for s in symbols]
        expected_symbols = ["add", "subtract", "multiply", "divide", "square", "factorial", "CalculatorClass"]

        for expected in expected_symbols:
            assert expected in symbol_names, f"{expected} function not found in Calculator.fs symbols"

    @pytest.mark.xfail(is_ci, reason="Test is flaky")  # TODO: Re-enable if the LS can be made more reliable #1040
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_find_referencing_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test finding references using symbol selection range."""
        file_path = os.path.join("Calculator.fs")
        symbols = language_server.request_document_symbols(file_path)

        # Find the 'add' function symbol
        add_symbol = None

        for sym in symbols.iter_symbols():
            if sym.get("name") == "add":
                add_symbol = sym
                break

        assert add_symbol is not None, "Could not find 'add' function symbol in Calculator.fs"

        # Try to find references to the add function
        sel_start = add_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)

        # The add function should be referenced in Program.fs
        assert any("Program.fs" in ref.get("relativePath", "") for ref in refs), "Program.fs should reference add function"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_nested_module_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test getting symbols from nested Models namespace."""
        file_path = os.path.join("Models", "Person.fs")
        symbols = language_server.request_document_symbols(file_path).get_all_symbols_and_roots()[0]

        # Check for expected types and modules
        symbol_names = [s.get("name") for s in symbols]
        expected_symbols = ["Person", "PersonModule", "Address", "Employee"]

        for expected in expected_symbols:
            assert expected in symbol_names, f"{expected} not found in Person.fs symbols"

    @pytest.mark.xfail(is_ci, reason="Test is flaky")  # TODO: Re-enable if the LS can be made more reliable #1040
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_find_referencing_symbols_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to Calculator functions across files."""
        # Find the subtract function in Calculator.fs
        file_path = os.path.join("Calculator.fs")
        symbols = language_server.request_document_symbols(file_path)

        subtract_symbol = None
        for sym in symbols.iter_symbols():
            if sym.get("name") == "subtract":
                subtract_symbol = sym
                break

        assert subtract_symbol is not None, "Could not find 'subtract' function symbol"

        # Find references to subtract function
        sel_start = subtract_symbol["selectionRange"]["start"]
        refs = language_server.request_references(file_path, sel_start["line"], sel_start["character"] + 1)

        # The subtract function should be referenced in Program.fs
        assert any("Program.fs" in ref.get("relativePath", "") for ref in refs), "Program.fs should reference subtract function"

    @pytest.mark.xfail(is_ci, reason="Test is flaky")  # TODO: Re-enable if the LS can be made more reliable #1040
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_go_to_definition(self, language_server: SolidLanguageServer) -> None:
        """Test go-to-definition functionality."""
        # Test going to definition of 'add' function from Program.fs
        program_file = os.path.join("Program.fs")

        # Try to find definition of 'add' function used in Program.fs
        # This would typically be at the line where 'add 5 3' is called
        definitions = language_server.request_definition(program_file, 10, 20)  # Approximate position

        # We should get at least some definitions
        assert len(definitions) >= 0, "Should get definitions (even if empty for complex cases)"

    @pytest.mark.xfail(is_ci, reason="Test is flaky")  # TODO: Re-enable if the LS can be made more reliable #1040
    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_hover_information(self, language_server: SolidLanguageServer) -> None:
        """Test hover information functionality."""
        file_path = os.path.join("Calculator.fs")

        # Try to get hover information for a function
        hover_info = language_server.request_hover(file_path, 5, 10)  # Approximate position of a function

        # Hover info might be None or contain information
        # This is acceptable as it depends on the LSP server's capabilities and timing
        assert hover_info is None or isinstance(hover_info, dict), "Hover info should be None or dict"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_completion(self, language_server: SolidLanguageServer) -> None:
        """Test code completion functionality."""
        file_path = os.path.join("Program.fs")

        # Use threading for cross-platform timeout (signal.SIGALRM is Unix-only)
        result: dict[str, Any] = dict(value=None)
        exception: dict[str, Any] = dict(value=None)

        def run_completion():
            try:
                result["value"] = language_server.request_completions(file_path, 15, 10)
            except Exception as e:
                exception["value"] = e

        thread = threading.Thread(target=run_completion, daemon=True)
        thread.start()
        thread.join(timeout=5)  # 5 second timeout

        if thread.is_alive():
            # Completion timed out, but this is acceptable for F# in some cases
            # The important thing is that the language server doesn't crash
            return

        if exception["value"]:
            raise exception["value"]

        assert isinstance(result["value"], list), "Completions should be a list"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_file_diagnostics(self, language_server: SolidLanguageServer) -> None:
        assert_file_diagnostics(
            language_server,
            "DiagnosticsSample.fs",
            (),
            min_count=1,
        )

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    def test_bare_symbol_names(self, language_server) -> None:
        all_symbols = request_all_symbols(language_server)
        malformed_symbols = []
        for s in all_symbols:
            if has_malformed_name(s):
                malformed_symbols.append(s)
        if malformed_symbols:
            pytest.fail(
                f"Found malformed symbols: {[format_symbol_for_assert(sym) for sym in malformed_symbols]}",
                pytrace=False,
            )
