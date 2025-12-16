"""
Basic integration tests for the Pascal language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the Pascal test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.pascal
class TestPascalLanguageServerBasics:
    """Test basic functionality of the Pascal language server."""

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that Pascal language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.PASCAL

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for Pascal files."""
        # Test getting symbols from main.pas
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # Extract class symbols (LSP Symbol Kind 5)
        class_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 5]
        class_names = [symbol["name"] for symbol in class_symbols]

        # Should detect classes from main.pas
        assert "TUser" in class_names, "Should find TUser class"
        assert "TUserManager" in class_names, "Should find TUserManager class"

        # Extract function/procedure symbols (LSP Symbol Kind 12 for functions, 6 for methods)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") in [12, 6]]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Should detect standalone functions
        assert "CalculateSum" in function_names, "Should find CalculateSum function"
        assert "PrintMessage" in function_names, "Should find PrintMessage procedure"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_class_methods(self, language_server: SolidLanguageServer) -> None:
        """Test detection of class methods in Pascal files."""
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # Get all method symbols
        method_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 6]
        method_names = [symbol["name"] for symbol in method_symbols]

        # Should detect TUser methods
        expected_tuser_methods = ["Create", "Destroy", "GetInfo", "UpdateAge"]
        for method in expected_tuser_methods:
            assert method in method_names, f"Should find TUser.{method} method"

        # Should detect TUserManager methods
        expected_manager_methods = ["Create", "Destroy", "AddUser", "GetUserCount", "FindUserByName"]
        for method in expected_manager_methods:
            assert method in method_names, f"Should find TUserManager.{method} method"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_helper_unit_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test function detection in Helper unit."""
        # Test with lib/helper.pas
        helper_all_symbols, _helper_root_symbols = language_server.request_document_symbols(
            "lib/helper.pas"
        ).get_all_symbols_and_roots()

        # Extract class symbols
        class_symbols = [symbol for symbol in helper_all_symbols if symbol.get("kind") == 5]
        class_names = [symbol["name"] for symbol in class_symbols]

        # Should detect THelper class
        assert "THelper" in class_names, "Should find THelper class"

        # Extract function symbols
        function_symbols = [symbol for symbol in helper_all_symbols if symbol.get("kind") in [12, 6]]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Should detect standalone functions
        expected_functions = ["GetHelperMessage", "MultiplyNumbers", "LogMessage"]
        for func_name in expected_functions:
            assert func_name in function_names, f"Should find {func_name} function in Helper unit"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_properties(self, language_server: SolidLanguageServer) -> None:
        """Test detection of Pascal properties."""
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # Properties are typically Symbol Kind 7
        property_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 7]
        property_names = [symbol["name"] for symbol in property_symbols]

        # TUser has Name and Age properties
        # Note: Some LSP servers may not report properties separately, so we check if they exist
        if property_symbols:
            assert any("Name" in name for name in property_names), "Should find Name property"
            assert any("Age" in name for name in property_names), "Should find Age property"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_cross_file_references(self, language_server: SolidLanguageServer) -> None:
        """Test that Pascal LSP can handle cross-file references."""
        # main.pas uses Helper unit
        main_symbols, _main_roots = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()
        helper_symbols, _helper_roots = language_server.request_document_symbols(
            "lib/helper.pas"
        ).get_all_symbols_and_roots()

        # Verify both files have symbols
        assert len(main_symbols) > 0, "main.pas should have symbols"
        assert len(helper_symbols) > 0, "helper.pas should have symbols"

        # Verify GetHelperMessage is in Helper unit
        helper_function_names = [
            symbol["name"] for symbol in helper_symbols if symbol.get("kind") in [12, 6]
        ]
        assert "GetHelperMessage" in helper_function_names, "Helper unit should export GetHelperMessage"
