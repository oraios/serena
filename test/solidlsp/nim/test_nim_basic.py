"""
Basic integration tests for the Nim language server functionality.

These tests validate the functionality of the language server APIs
like request_document_symbols using the Nim test repository.
"""

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.nim
class TestNimLanguageServerBasics:
    """Test basic functionality of the Nim language server."""

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_language_server_initialization(self, language_server: SolidLanguageServer) -> None:
        """Test that Nim language server can be initialized successfully."""
        assert language_server is not None
        assert language_server.language == Language.NIM

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_request_document_symbols(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols for Nim files."""
        # Test getting symbols from main.nim
        all_symbols, root_symbols = language_server.request_document_symbols("main.nim", include_body=False)

        # Extract function symbols (LSP Symbol Kind 12)
        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Should detect procedures from main.nim
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

        # Should detect types from main.nim
        assert "Person" in type_names, "Should find Person type"
        assert "Animal" in type_names, "Should find Animal type"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_request_document_symbols_with_body(self, language_server: SolidLanguageServer) -> None:
        """Test request_document_symbols with body extraction."""
        # Test with include_body=True
        all_symbols, root_symbols = language_server.request_document_symbols("main.nim", include_body=True)

        function_symbols = [symbol for symbol in all_symbols if symbol.get("kind") == 12]

        # Find greet procedure and check it has body
        greet_symbol = next((sym for sym in function_symbols if sym["name"] == "greet"), None)
        assert greet_symbol is not None, "Should find greet procedure"

        if "body" in greet_symbol:
            body = greet_symbol["body"]
            # nimlangserver returns just the signature, not the full proc definition
            assert "greet" in body, "Procedure body should contain function name"
            assert "string" in body, "greet body should contain return type"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_utils_module(self, language_server: SolidLanguageServer) -> None:
        """Test symbol detection in utils.nim module."""
        # Test with utils.nim
        utils_all_symbols, utils_root_symbols = language_server.request_document_symbols("utils.nim", include_body=False)

        utils_function_symbols = [symbol for symbol in utils_all_symbols if symbol.get("kind") == 12]
        utils_function_names = [symbol["name"] for symbol in utils_function_symbols]

        # Should detect procedures from utils.nim
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
            assert func_name in utils_function_names, f"Should find {func_name} procedure in utils.nim"

        # Check for templates (they might be detected as different symbol kinds)
        all_symbol_names = [symbol["name"] for symbol in utils_all_symbols]
        assert "timeIt" in all_symbol_names, "Should find timeIt template"
        # Note: nimlangserver may not detect iterators as symbols
        # This is a known limitation of some language servers

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_types_module(self, language_server: SolidLanguageServer) -> None:
        """Test type detection in types.nim module."""
        # Test with types.nim
        types_all_symbols, types_root_symbols = language_server.request_document_symbols("types.nim", include_body=False)

        # Extract type symbols
        type_symbols = [symbol for symbol in types_all_symbols if symbol.get("kind") in [5, 23, 10]]  # Class, Struct, Enum
        type_names = [symbol["name"] for symbol in type_symbols]

        # Should detect types from types.nim
        expected_types = ["Point", "Rectangle", "Shape", "Circle", "Triangle", "Color", "Status", "Result", "Database"]

        for type_name in expected_types:
            assert type_name in type_names, f"Should find {type_name} type in types.nim"

        # Extract function symbols
        function_symbols = [symbol for symbol in types_all_symbols if symbol.get("kind") == 12]
        function_names = [symbol["name"] for symbol in function_symbols]

        # Should detect procedures from types.nim
        expected_procs = [
            "newPoint",
            "toString",
            "distance",
            "newRectangle",
            "area",
            "perimeter",
            "contains",
            "draw",
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
    def test_nim_goto_definition(self, language_server: SolidLanguageServer) -> None:
        """Test goto definition functionality for Nim."""
        # Test goto definition from main.nim to utils module
        definition = language_server.request_goto_definition("main.nim", 58, 8)  # formatNumber call

        if definition:
            assert isinstance(definition, list), "Definition should be a list"
            assert len(definition) > 0, "Should find at least one definition"

            # Check if the definition points to utils.nim
            first_def = definition[0]
            if "uri" in first_def:
                assert "utils.nim" in first_def["uri"], "Definition should point to utils.nim"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_find_references(self, language_server: SolidLanguageServer) -> None:
        """Test find references functionality for Nim."""
        # Test finding references to the Person type
        references = language_server.request_references("main.nim", 20, 3)  # Person type definition

        if references:
            assert isinstance(references, list), "References should be a list"
            assert len(references) > 0, "Should find at least one reference to Person"

    @pytest.mark.parametrize("language_server", [Language.NIM], indirect=True)
    def test_nim_completions(self, language_server: SolidLanguageServer) -> None:
        """Test completion functionality for Nim."""
        # Test completions after a dot operator
        completions = language_server.request_completions("main.nim", 31, 14)  # After p. in describe proc

        if completions:
            assert "items" in completions, "Completions should have items"
            items = completions["items"]
            assert len(items) > 0, "Should provide at least one completion"

            # Check for Person field completions
            completion_labels = [item["label"] for item in items]
            expected_fields = ["name", "age", "email"]

            for field in expected_fields:
                assert field in completion_labels, f"Should suggest {field} field for Person type"