"""
Basic integration tests for the bash language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the bash test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.bash
class TestBashLanguageServerBasics:
    """Test basic functionality of the bash language server."""

    @pytest.mark.parametrize("language_server", [Language.BASH], indirect=True)
    def test_bash_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that bash language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.BASH

    @pytest.mark.parametrize("language_server", [Language.BASH], indirect=True)
    def test_bash_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for bash files."""
        # Test getting symbols from main.sh
        all_symbols, root_symbols = language_server.request_document_symbols("main.sh", include_body=False)

        # Extract function symbols (LSP Symbol Kind 12)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Should detect all 3 functions from main.sh
        assert "greet_user" in function_names, "Should find greet_user function"
        assert "process_items" in function_names, "Should find process_items function"
        assert "main" in function_names, "Should find main function"
        assert len(function_symbols) >= 3, f"Should find at least 3 functions, found {len(function_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.BASH], indirect=True)
    def test_bash_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        # Test with include_body=True
        all_symbols, root_symbols = language_server.request_document_symbols("main.sh", include_body=True)

        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]

        # Find greet_user function and check it has body
        greet_user_symbol = next((sym for sym in function_symbols if sym["name"] == "greet_user"), None)
        assert greet_user_symbol is not None, "Should find greet_user function"

        if "body" in greet_user_symbol:
            body = greet_user_symbol["body"]
            assert "function greet_user()" in body, "Function body should contain function definition"
            assert "case" in body.lower(), "Function body should contain case statement"

    @pytest.mark.parametrize("language_server", [Language.BASH], indirect=True)
    def test_bash_utils_functions(self, language_server: SolidLanguageServer) -> None:
        """Test function detection in utils.sh file."""
        # Test with utils.sh as well
        utils_all_symbols, utils_root_symbols = language_server.request_document_symbols("utils.sh", include_body=False)

        utils_function_symbols = [symbol for symbol in utils_all_symbols if symbol.get("kind") == 12]
        utils_function_names = [symbol["name"] for symbol in utils_function_symbols]

        # Should detect functions from utils.sh
        expected_utils_functions = [
            "to_uppercase",
            "to_lowercase",
            "trim_whitespace",
            "backup_file",
            "contains_element",
            "log_message",
            "is_valid_email",
            "is_number",
        ]

        for func_name in expected_utils_functions:
            assert func_name in utils_function_names, f"Should find {func_name} function in utils.sh"

        assert len(utils_function_symbols) >= 8, f"Should find at least 8 functions in utils.sh, found {len(utils_function_symbols)}"

    @pytest.mark.parametrize("language_server", [Language.BASH], indirect=True)
    def test_bash_function_syntax_patterns(self, language_server: SolidLanguageServer) -> None:
        """Test that LSP detects different bash function syntax patterns correctly."""
        # Test main.sh (has both 'function' keyword and traditional syntax)
        main_all_symbols, main_root_symbols = language_server.request_document_symbols("main.sh", include_body=False)
        main_functions = [symbol for symbol in main_all_symbols if symbol.get("kind") == 12]
        main_function_names = [func["name"] for func in main_functions]

        # Test utils.sh (all use 'function' keyword)
        utils_all_symbols, utils_root_symbols = language_server.request_document_symbols("utils.sh", include_body=False)
        utils_functions = [symbol for symbol in utils_all_symbols if symbol.get("kind") == 12]
        utils_function_names = [func["name"] for func in utils_functions]

        # Verify LSP detects both syntax patterns
        # main() uses traditional syntax: main() {
        assert "main" in main_function_names, "LSP should detect traditional function syntax"

        # Functions with 'function' keyword: function name() {
        assert "greet_user" in main_function_names, "LSP should detect function keyword syntax"
        assert "process_items" in main_function_names, "LSP should detect function keyword syntax"

        # Verify all expected utils functions are detected by LSP
        expected_utils = [
            "to_uppercase",
            "to_lowercase",
            "trim_whitespace",
            "backup_file",
            "contains_element",
            "log_message",
            "is_valid_email",
            "is_number",
        ]

        for expected_func in expected_utils:
            assert expected_func in utils_function_names, f"LSP should detect {expected_func} function"

        # Verify total counts match expectations
        assert len(main_functions) >= 3, f"Should find at least 3 functions in main.sh, found {len(main_functions)}"
        assert len(utils_functions) >= 8, f"Should find at least 8 functions in utils.sh, found {len(utils_functions)}"
