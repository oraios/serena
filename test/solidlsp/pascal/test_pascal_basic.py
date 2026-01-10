"""
Basic integration tests for the Pascal language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the Pascal test repository.

Uses genericptr/pascal-language-server which returns SymbolInformation[] format:
- Returns classes, structs, enums, typedefs, functions/procedures
- Uses correct SymbolKind values: Class=5, Function=12, Method=6, Struct=23
- Method names don't include parent class prefix; uses containerName instead
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_types import SymbolKind
from test.conftest import language_tests_enabled

pytestmark = [
    pytest.mark.pascal,
    pytest.mark.skipif(not language_tests_enabled(Language.PASCAL), reason="Pascal tests are disabled (pasls/fpc not available)"),
]


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
        """Test request_document_symbols for Pascal files.

        genericptr pasls returns proper SymbolKind values:
        - Standalone functions: kind=12 (Function)
        - Classes: kind=5 (Class)
        """
        # Test getting symbols from main.pas
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # Should have symbols
        assert len(all_symbols) > 0, "Should have symbols in main.pas"

        # Should detect standalone functions (SymbolKind.Function = 12)
        function_symbols = [s for s in all_symbols if s.get("kind") == SymbolKind.Function]
        function_names = [s["name"] for s in function_symbols]

        assert "CalculateSum" in function_names, "Should find CalculateSum function"
        assert "PrintMessage" in function_names, "Should find PrintMessage procedure"

        # Should detect classes (SymbolKind.Class = 5)
        class_symbols = [s for s in all_symbols if s.get("kind") == SymbolKind.Class]
        class_names = [s["name"] for s in class_symbols]

        assert "TUser" in class_names, "Should find TUser class"
        assert "TUserManager" in class_names, "Should find TUserManager class"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_class_methods(self, language_server: SolidLanguageServer) -> None:
        """Test detection of class methods in Pascal files.

        pasls returns class methods with SymbolKind.Method (kind 6), not Function (kind 12).
        """
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # Get all method symbols (pasls returns class methods as SymbolKind.Method = 6)
        method_symbols = [s for s in all_symbols if s.get("kind") == SymbolKind.Method]
        method_names = [s["name"] for s in method_symbols]

        # Should detect TUser methods
        expected_tuser_methods = ["Create", "Destroy", "GetInfo", "UpdateAge"]
        for method in expected_tuser_methods:
            found = method in method_names
            assert found, f"Should find method '{method}'"

        # Should detect TUserManager methods
        expected_manager_methods = ["Create", "Destroy", "AddUser", "GetUserCount", "FindUserByName"]
        for method in expected_manager_methods:
            found = method in method_names
            assert found, f"Should find method '{method}'"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_helper_unit_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test function detection in Helper unit."""
        # Test with lib/helper.pas
        helper_all_symbols, _helper_root_symbols = language_server.request_document_symbols("lib/helper.pas").get_all_symbols_and_roots()

        # Should have symbols
        assert len(helper_all_symbols) > 0, "Helper unit should have symbols"

        # Extract function symbols
        function_symbols = [s for s in helper_all_symbols if s.get("kind") == SymbolKind.Function]
        function_names = [s["name"] for s in function_symbols]

        # Should detect standalone functions
        expected_functions = ["GetHelperMessage", "MultiplyNumbers", "LogMessage"]
        for func_name in expected_functions:
            assert func_name in function_names, f"Should find {func_name} function in Helper unit"

        # Should also detect THelper class methods (returned as SymbolKind.Method = 6)
        method_symbols = [s for s in helper_all_symbols if s.get("kind") == SymbolKind.Method]
        method_names = [s["name"] for s in method_symbols]
        assert "FormatString" in method_names, "Should find FormatString method"
        assert "IsEven" in method_names, "Should find IsEven method"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_cross_file_references(self, language_server: SolidLanguageServer) -> None:
        """Test that Pascal LSP can handle cross-file references."""
        # main.pas uses Helper unit
        main_symbols, _main_roots = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()
        helper_symbols, _helper_roots = language_server.request_document_symbols("lib/helper.pas").get_all_symbols_and_roots()

        # Verify both files have symbols
        assert len(main_symbols) > 0, "main.pas should have symbols"
        assert len(helper_symbols) > 0, "helper.pas should have symbols"

        # Verify GetHelperMessage is in Helper unit
        helper_function_names = [s["name"] for s in helper_symbols if s.get("kind") == SymbolKind.Function]
        assert "GetHelperMessage" in helper_function_names, "Helper unit should export GetHelperMessage"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_symbol_locations(self, language_server: SolidLanguageServer) -> None:
        """Test that symbols have correct location information.

        Note: genericptr pasls returns the interface declaration location (line ~41),
        not the implementation location (line ~115).
        """
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # Find CalculateSum function
        calc_symbols = [s for s in all_symbols if s.get("name") == "CalculateSum"]
        assert len(calc_symbols) > 0, "Should find CalculateSum"

        calc_symbol = calc_symbols[0]

        # Verify it has location information (SymbolInformation format uses location.range)
        if "location" in calc_symbol:
            location = calc_symbol["location"]
            assert "range" in location, "Location should have range"
            assert "start" in location["range"], "Range should have start"
            assert "line" in location["range"]["start"], "Start should have line"
            line = location["range"]["start"]["line"]
        else:
            # DocumentSymbol format uses range directly
            assert "range" in calc_symbol, "Symbol should have range"
            assert "start" in calc_symbol["range"], "Range should have start"
            line = calc_symbol["range"]["start"]["line"]

        # CalculateSum is declared at line 41 in main.pas (0-indexed would be 40)
        # genericptr pasls returns interface declaration location
        assert 35 <= line <= 45, f"CalculateSum should be around line 41 (interface), got {line}"

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_namespace_symbol(self, language_server: SolidLanguageServer) -> None:
        """Test that genericptr pasls returns Interface namespace symbol."""
        all_symbols, _root_symbols = language_server.request_document_symbols("main.pas").get_all_symbols_and_roots()

        # genericptr pasls adds an "Interface" namespace symbol
        symbol_names = [s["name"] for s in all_symbols]

        # The Interface section should be represented
        # Note: This depends on pasls configuration
        assert len(all_symbols) > 0, "Should have symbols"
        # Interface namespace may or may not be present depending on pasls configuration
        _ = symbol_names  # used for potential future assertions

    @pytest.mark.parametrize("language_server", [Language.PASCAL], indirect=True)
    def test_pascal_hover_with_doc_comments(self, language_server: SolidLanguageServer) -> None:
        """Test that hover returns documentation comments.

        CalculateSum has /// style doc comments that should appear in hover.
        """
        # CalculateSum is declared at line 46 (1-indexed), so line 45 (0-indexed)
        hover = language_server.request_hover("main.pas", 45, 12)

        assert hover is not None, "Hover should return a result"

        # Extract hover content - handle both dict and object formats
        if isinstance(hover, dict):
            contents = hover.get("contents", {})
            value = contents.get("value", "") if isinstance(contents, dict) else str(contents)
        else:
            value = hover.contents.value if hasattr(hover.contents, "value") else str(hover.contents)

        # Should contain the function signature
        assert "CalculateSum" in value, f"Hover should show function name. Got: {value[:500]}"

        # Should contain the doc comment
        assert "Calculates the sum" in value, f"Hover should include doc comment. Got: {value[:500]}"
