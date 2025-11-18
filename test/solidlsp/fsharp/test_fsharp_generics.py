"""
Tests for F# generic types, constraints, and advanced features with strict navigation checks.
"""

from pathlib import Path

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language


@pytest.mark.fsharp
class TestFSharpGenerics:
    """Test F# generic types and functions."""

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_generic_function_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from generic function usage to its definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 76, 7)

        assert definition_location_list, "Expected definition location for generic function 'first'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_type_abbreviation_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from type abbreviation usage to its definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 18, 20)

        assert definition_location_list, "Expected definition location for type abbreviation 'Vector'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_active_pattern_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from active pattern usage to its case definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 30, 6)

        assert definition_location_list, "Expected definition location for active pattern case 'Even'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_recursive_function_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from recursive call site back to definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 36, 13)

        assert definition_location_list, "Expected definition location for recursive function 'factorial'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_higher_order_function_references(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Resolve references for higher-order helper."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        references = language_server.request_references(advanced_fs_path, 39, 4)

        assert references, "Expected references for higher-order function 'apply'"
        assert any(loc["uri"].endswith("Advanced.fs") for loc in references)

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_curried_function_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from partial application site to curried function definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 45, 14)

        assert definition_location_list, "Expected definition location for curried function 'addThree'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_async_workflow_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Ensure async workflow definitions are discoverable."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 60, 4)

        assert definition_location_list, "Expected definition location for async workflow"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_result_type_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from Result-returning function to its definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 67, 4)

        assert definition_location_list, "Expected definition location for result-returning function 'divide'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_discriminated_union_with_fields(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Resolve DU case definitions with named fields."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 93, 6)

        assert definition_location_list, "Expected definition location for DU case 'Email'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_record_with_mutable_field_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate to record definition with mutable field."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 105, 5)

        assert definition_location_list, "Expected definition location for record 'Counter'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_interface_definition_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate to interface definition and implementation."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 143, 14)

        assert definition_location_list, "Expected definition location for interface 'IShape'"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_nested_module_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate to Nested module definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 151, 7)

        assert definition_location_list, "Expected definition location for nested module"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_pipeline_operator_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from pipeline-based function to its definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 48, 4)

        assert definition_location_list, "Expected definition location for pipeline-based function"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_composition_operator_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate from composition operator usage to definition."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 57, 4)

        assert definition_location_list, "Expected definition location for composed function"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_units_of_measure_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate to values using units of measure."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 119, 4)

        assert definition_location_list, "Expected definition location for value with units of measure"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")

    @pytest.mark.parametrize("language_server", [Language.FSHARP], indirect=True)
    @pytest.mark.parametrize("repo_path", [Language.FSHARP], indirect=True)
    def test_sequence_expression_navigation(self, language_server: SolidLanguageServer, repo_path: Path) -> None:
        """Navigate to sequence and list expressions."""
        advanced_fs_path = str(repo_path / "src" / "Advanced.fs")

        definition_location_list = language_server.request_definition(advanced_fs_path, 124, 4)

        assert definition_location_list, "Expected definition location for sequence expression"
        assert definition_location_list[0]["uri"].endswith("Advanced.fs")
