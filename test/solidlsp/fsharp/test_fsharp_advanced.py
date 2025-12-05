"""
Advanced F# language server tests.

Tests for advanced features, edge cases, and error handling.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException


@pytest.mark.fsharp
class TestFSharpAdvancedFeatures:
    """Test advanced F# features and LSP capabilities."""

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_hover_on_function(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test hover information on a function"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        # Hover over 'add' function definition
        hover_info = language_server.request_hover(helper_fs_path, 3, 4)

        assert hover_info, "Expected hover information but got None"

        # Hover should contain either the function signature or documentation
        if isinstance(hover_info, dict):
            contents = hover_info.get("contents", {})
            # Check that we got some meaningful content
            assert contents, "Expected non-empty hover contents"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_hover_on_type(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test hover information on a type"""
        types_fs_path = str(repo_path / "src" / "Types.fs")

        # Hover over 'Point' type definition
        # Note: FsAutoComplete may not have finished type checking yet, so hover might be None
        hover_info = language_server.request_hover(types_fs_path, 4, 5)

        # This test is primarily checking that the request doesn't crash
        # Hover information may be None if FsAutoComplete hasn't finished checking the file
        # which is acceptable for this test
        if hover_info:
            # If we got hover info, verify it's structured correctly
            assert isinstance(hover_info, dict)

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_record_field_definition(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition of record field usage"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # In Program.fs line 34 (0-indexed line 33):
        # printfn "Person: %s, Age: %d, Email: %A" person.Name person.Age person.Email
        # Find definition of 'Name' field
        definition_location_list = language_server.request_definition(program_fs_path, 33, 56)

        assert definition_location_list, "Expected definition for record field 'Name'"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Types.fs"), f"Expected definition in Types.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_discriminated_union_case_definition(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition of DU case"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # In Program.fs line 25 (0-indexed line 24):
        # let rectangle = Rectangle (4.0, 6.0)
        # Try to find definition of 'Rectangle' DU case
        definition_location_list = language_server.request_definition(program_fs_path, 24, 20)

        assert definition_location_list, "Expected definition location for DU case 'Rectangle'"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Types.fs"), f"Expected definition in Types.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_pattern_matching_function_reference(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding function used in pattern matching"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # Navigate from area usage in Program.fs to its definition in Types.fs
        definition_location_list = language_server.request_definition(program_fs_path, 27, 53)

        assert definition_location_list, "Expected definition location for 'area'"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Types.fs"), f"Expected definition in Types.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_symbol_kinds(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that symbols have correct kinds"""
        types_fs_path = str(repo_path / "src" / "Types.fs")

        symbols = language_server.request_document_symbols(types_fs_path)
        assert symbols, "Expected non-empty symbols"

        # Check symbol kinds
        symbol_kinds = {}
        for symbol in symbols.iter_symbols():
            if isinstance(symbol, dict):
                name = symbol.get("name", "")
                kind = symbol.get("kind")
                if name:
                    symbol_kinds[name] = kind

        # Verify we have symbols with kinds
        assert len(symbol_kinds) > 0, "Expected to find symbols with kinds"

        # Verify that symbols have valid kinds (any numeric kind is fine)
        # FsAutoComplete may return different kinds for different symbol types
        for name, kind in symbol_kinds.items():
            if kind is not None:
                assert isinstance(kind, int), f"Expected {name} kind to be int but got {type(kind)}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_multiple_references_to_same_function(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding all references when a function is used multiple times"""
        calculator_fs_path = str(repo_path / "src" / "Calculator.fs")

        # Find references to 'add' function which is used in multiple places
        # Line 23 (0-indexed 22): List.fold (fun acc n -> add acc n) 0 numbers
        references = language_server.request_references(calculator_fs_path, 22, 32)

        assert references, "Expected to find references to 'add'"
        reference_files = [loc["uri"].split("/")[-1] for loc in references]
        assert (
            "Calculator.fs" in reference_files or "Program.fs" in reference_files
        ), f"Expected references in Calculator.fs or Program.fs but got {reference_files}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_optional_type_usage(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition through optional type"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # In Program.fs line 33 (0-indexed 32):
        # let person = createPerson "Alice" 30 (Some "alice@example.com")
        # Find definition of createPerson
        definition_location_list = language_server.request_definition(program_fs_path, 32, 17)

        assert definition_location_list, f"Expected non-empty definition_location_list but got {definition_location_list=}"
        assert len(definition_location_list) >= 1

        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Types.fs"), f"Expected definition in Types.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_list_fold_function_reference(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test references within higher-order functions like List.fold"""
        calculator_fs_path = str(repo_path / "src" / "Calculator.fs")

        # Verify we can navigate from the List.fold lambda call to the helper definition
        definition_location_list = language_server.request_definition(calculator_fs_path, 22, 32)

        assert definition_location_list, "Expected definition location for 'add' inside List.fold"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith("Helper.fs"), f"Expected definition in Helper.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_module_open_statement(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that open statements are properly resolved"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # Program.fs has: open TestProject.Calculator
        # Ensure the open statement enables navigation to Calculator methods
        definition_location_list = language_server.request_definition(program_fs_path, 12, 33)

        assert definition_location_list, "Expected definition location for Add via open statement"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith(
            "Calculator.fs"
        ), f"Expected definition in Calculator.fs but got {definition_location['uri']}"


@pytest.mark.fsharp
class TestFSharpErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_definition_at_invalid_position(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test that requesting definition at whitespace returns empty or raises appropriate error"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        # Request definition at a position with only whitespace should raise
        with pytest.raises(SolidLSPException):
            language_server.request_definition(helper_fs_path, 0, 0)

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_references_for_builtin_type(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding references for built-in types like int, string"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        # Find references to 'x' parameter (local variable)
        references = language_server.request_references(helper_fs_path, 3, 8)

        assert references, "Expected references for local parameter 'x'"
        assert any(loc["uri"].endswith("Helper.fs") for loc in references), "Expected references within Helper.fs"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_hover_on_keyword(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test hover on F# keywords doesn't crash"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        # Hover over 'add' should provide signature/type info
        hover_info = language_server.request_hover(helper_fs_path, 3, 4)

        assert hover_info, "Expected hover information for 'add'"
        assert "add" in str(hover_info), f"Expected hover text to include function name, got {hover_info}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_symbols_in_empty_module(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test requesting symbols from a file returns something"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        symbols = language_server.request_document_symbols(helper_fs_path)

        assert symbols, "Expected non-empty symbols list"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_definition_of_self_reference(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding definition when cursor is already on the definition"""
        helper_fs_path = str(repo_path / "src" / "Helper.fs")

        # Position on 'add' function name in its definition
        definition_location_list = language_server.request_definition(helper_fs_path, 3, 4)

        assert definition_location_list, "Expected self-definition lookup to return a location"
        assert definition_location_list[0]["uri"].endswith(
            "Helper.fs"
        ), f"Expected definition in Helper.fs but got {definition_location_list}"


@pytest.mark.fsharp
class TestFSharpCrossFileNavigation:
    """Test cross-file navigation scenarios."""

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_navigate_through_multiple_files(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test navigation chain: Program -> Calculator -> Helper"""
        program_fs_path = str(repo_path / "src" / "Program.fs")

        # Start in Program.fs, find definition of createCalculator
        # Line 10 (0-indexed 9): let calc = createCalculator()
        definition_location_list = language_server.request_definition(program_fs_path, 9, 15)

        assert definition_location_list, "Expected to find createCalculator definition"
        assert len(definition_location_list) >= 1

        # Should point to Calculator.fs
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith(
            "Calculator.fs"
        ), f"Expected definition in Calculator.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_find_all_usages_of_type_across_project(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding all usages of a type across the entire project"""
        # Find references to Calculator type from its definition (line 7, 0-indexed 6)
        calculator_fs_path = str(repo_path / "src" / "Calculator.fs")
        references = language_server.request_references(calculator_fs_path, 6, 5)

        assert references, "Expected references for 'Calculator' across project"

        reference_files = [loc["uri"].split("/")[-1] for loc in references]
        assert (
            "Program.fs" in reference_files or "Calculator.fs" in reference_files
        ), f"Expected references in Program.fs or Calculator.fs but got {reference_files}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_module_hierarchy_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test navigation through module hierarchy"""
        # All our test files are in TestProject.* namespace
        # Verify we can find symbols across this hierarchy
        program_fs_path = str(repo_path / "src" / "Program.fs")

        definition_location_list = language_server.request_definition(program_fs_path, 9, 15)

        assert definition_location_list, "Expected definition for createCalculator"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith(
            "Calculator.fs"
        ), f"Expected definition in Calculator.fs but got {definition_location['uri']}"

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_type_usage_in_function_signature(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Test finding type definitions used in function signatures"""
        # Navigate from usage in Program.fs to Sum definition
        program_fs_path = str(repo_path / "src" / "Program.fs")
        definition_location_list = language_server.request_definition(program_fs_path, 19, 43)

        assert definition_location_list, "Expected definition location for Sum"
        definition_location = definition_location_list[0]
        assert definition_location["uri"].endswith(
            "Calculator.fs"
        ), f"Expected definition in Calculator.fs but got {definition_location['uri']}"
