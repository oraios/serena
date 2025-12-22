"""
Basic integration tests for the PowerShell language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the PowerShell test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.powershell
class TestPowerShellLanguageServerBasics:
    """Test basic functionality of the PowerShell language server."""

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that PowerShell language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.POWERSHELL

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for PowerShell files."""
        # Test getting symbols from main.ps1
        all_symbols, _root_symbols = language_server.request_document_symbols("main.ps1").get_all_symbols_and_roots()

        # Extract function symbols (LSP Symbol Kind 12)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        # PSES returns function names in format "function FuncName ()" - check for function name substring
        def has_function(name: str) -> bool:
            return any(name in fn for fn in function_names)

        # Should detect the main functions from main.ps1
        assert has_function("Greet-User"), f"Should find Greet-User function in {function_names}"
        assert has_function("Process-Items"), f"Should find Process-Items function in {function_names}"
        assert has_function("Main"), f"Should find Main function in {function_names}"
        assert len(function_symbols) >= 3, f"Should find at least 3 functions, found {len(function_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_utils_functions(self, language_server: SolidLanguageServer) -> None:
        """Test function detection in utils.ps1 file."""
        # Test with utils.ps1
        utils_all_symbols, _utils_root_symbols = language_server.request_document_symbols("utils.ps1").get_all_symbols_and_roots()

        utils_function_symbols = [symbol for symbol in utils_all_symbols if symbol.get("kind") == 12]
        utils_function_names = [symbol["name"] for symbol in utils_function_symbols]

        # PSES returns function names in format "function FuncName ()" - check for function name substring
        def has_function(name: str) -> bool:
            return any(name in fn for fn in utils_function_names)

        # Should detect functions from utils.ps1
        expected_utils_functions = [
            "Convert-ToUpperCase",
            "Convert-ToLowerCase",
            "Remove-Whitespace",
            "Backup-File",
            "Test-ArrayContains",
            "Write-LogMessage",
            "Test-ValidEmail",
            "Test-IsNumber",
        ]

        for func_name in expected_utils_functions:
            assert has_function(func_name), f"Should find {func_name} function in utils.ps1, got {utils_function_names}"

        assert len(utils_function_symbols) >= 8, f"Should find at least 8 functions in utils.ps1, found {len(utils_function_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_function_with_parameters(self, language_server: SolidLanguageServer) -> None:
        """Test that functions with CmdletBinding and parameters are detected correctly."""
        all_symbols, _root_symbols = language_server.request_document_symbols("main.ps1").get_all_symbols_and_roots()

        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]

        # Find Greet-User function which has parameters
        # PSES returns function names in format "function FuncName ()"
        greet_user_symbol = next((sym for sym in function_symbols if "Greet-User" in sym["name"]), None)
        assert greet_user_symbol is not None, f"Should find Greet-User function in {[s['name'] for s in function_symbols]}"

        # Find Process-Items function which has array parameter
        process_items_symbol = next((sym for sym in function_symbols if "Process-Items" in sym["name"]), None)
        assert process_items_symbol is not None, f"Should find Process-Items function in {[s['name'] for s in function_symbols]}"

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_all_function_detection(self, language_server: SolidLanguageServer) -> None:
        """Test that all expected functions are detected across both files."""
        # Get symbols from main.ps1
        main_all_symbols, _main_root_symbols = language_server.request_document_symbols("main.ps1").get_all_symbols_and_roots()
        main_functions = [symbol for symbol in main_all_symbols if symbol.get("kind") == 12]
        main_function_names = [func["name"] for func in main_functions]

        # Get symbols from utils.ps1
        utils_all_symbols, _utils_root_symbols = language_server.request_document_symbols("utils.ps1").get_all_symbols_and_roots()
        utils_functions = [symbol for symbol in utils_all_symbols if symbol.get("kind") == 12]
        utils_function_names = [func["name"] for func in utils_functions]

        # PSES returns function names in format "function FuncName ()" - check for function name substring
        def has_main_function(name: str) -> bool:
            return any(name in fn for fn in main_function_names)

        def has_utils_function(name: str) -> bool:
            return any(name in fn for fn in utils_function_names)

        # Verify main.ps1 functions
        expected_main = ["Greet-User", "Process-Items", "Main"]
        for expected_func in expected_main:
            assert has_main_function(expected_func), f"Should detect {expected_func} function in main.ps1, got {main_function_names}"

        # Verify utils.ps1 functions
        expected_utils = [
            "Convert-ToUpperCase",
            "Convert-ToLowerCase",
            "Remove-Whitespace",
            "Backup-File",
            "Test-ArrayContains",
            "Write-LogMessage",
            "Test-ValidEmail",
            "Test-IsNumber",
        ]
        for expected_func in expected_utils:
            assert has_utils_function(expected_func), f"Should detect {expected_func} function in utils.ps1, got {utils_function_names}"

        # Verify total counts
        assert len(main_functions) >= 3, f"Should find at least 3 functions in main.ps1, found {len(main_functions)}"
        assert len(utils_functions) >= 8, f"Should find at least 8 functions in utils.ps1, found {len(utils_functions)}"

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_find_references_within_file(self, language_server: SolidLanguageServer) -> None:
        """Test finding references to a function within the same file."""
        main_path = "main.ps1"

        # Get symbols to find the Greet-User function which is called from Main
        all_symbols, _root_symbols = language_server.request_document_symbols(main_path).get_all_symbols_and_roots()

        # Find Greet-User function definition
        function_symbols = [s for s in all_symbols if s.get("kind") == 12]
        greet_user_symbol = next((s for s in function_symbols if "Greet-User" in s["name"]), None)
        assert greet_user_symbol is not None, f"Should find Greet-User function in {[s['name'] for s in function_symbols]}"

        # Find references to Greet-User (should be called from Main function at line 91)
        sel_start = greet_user_symbol["selectionRange"]["start"]
        refs = language_server.request_references(main_path, sel_start["line"], sel_start["character"])

        # Should find at least the call site in Main function
        assert refs is not None and len(refs) >= 1, f"Should find references to Greet-User, got {refs}"
        assert any(
            "main.ps1" in ref.get("uri", ref.get("relativePath", "")) for ref in refs
        ), f"Should find reference in main.ps1, got {refs}"

    @pytest.mark.parametrize("language_server", [Language.POWERSHELL], indirect=True)
    def test_powershell_find_definition_across_files(self, language_server: SolidLanguageServer) -> None:
        """Test finding definition of functions across files (main.ps1 -> utils.ps1)."""
        # main.ps1 calls Convert-ToUpperCase from utils.ps1 at line 99 (0-indexed: 98)
        # The call is: $upperName = Convert-ToUpperCase -InputString $User
        # We'll request definition from the call site in main.ps1
        main_path = "main.ps1"

        # Find definition of Convert-ToUpperCase from its usage in main.ps1
        # Line 99 (1-indexed) = line 98 (0-indexed), character position ~16 for "Convert-ToUpperCase"
        definition_locations = language_server.request_definition(main_path, 98, 18)

        # Should find the definition in utils.ps1
        assert (
            definition_locations is not None and len(definition_locations) >= 1
        ), f"Should find definition of Convert-ToUpperCase, got {definition_locations}"
        assert any(
            "utils.ps1" in loc.get("uri", "") for loc in definition_locations
        ), f"Should find definition in utils.ps1, got {definition_locations}"
