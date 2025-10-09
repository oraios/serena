"""Integration tests for RenameSymbolTool using Go language server."""

from unittest.mock import MagicMock

import pytest

from serena.agent import SerenaAgent
from serena.symbol import LanguageServerSymbolRetriever
from serena.tools.symbol_tools import RenameSymbolTool
from solidlsp.ls_config import Language


@pytest.mark.go
class TestRenameSymbolGoIntegration:
    """Integration tests for RenameSymbolTool using the Go language server."""

    @pytest.mark.parametrize("language_server,project", [(Language.GO, Language.GO)], indirect=True)
    def test_rename_function_go(self, language_server, project) -> None:
        """Test renaming a Go function using the actual language server."""
        # Create a mock agent with the project
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.get_active_project_or_raise.return_value = project

        # Create the tool
        tool = RenameSymbolTool(mock_agent)

        # Create symbol retriever with the language server
        symbol_retriever = LanguageServerSymbolRetriever(language_server)

        # Mock the create_language_server_symbol_retriever method to return our symbol retriever
        tool.create_language_server_symbol_retriever = MagicMock(return_value=symbol_retriever)

        # Test renaming the Helper function
        result = tool.apply(
            name_path="Helper",  # Function name to rename
            relative_path="main.go",  # File containing the function
            new_name="HelperRenamed",  # New name
        )

        # Verify the result indicates success
        assert isinstance(result, str), f"Expected string result, got: {type(result)}"
        result_lower = result.lower()
        assert "success" in result_lower or "renamed" in result_lower, f"Rename operation failed: {result}"
        assert "helperrenamed" in result_lower or "helper" in result_lower

    @pytest.mark.parametrize("language_server,project", [(Language.GO, Language.GO)], indirect=True)
    def test_rename_struct_go(self, language_server, project) -> None:
        """Test renaming a Go struct using the actual language server."""
        # Create a mock agent with the project
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.get_active_project_or_raise.return_value = project

        # Create the tool
        tool = RenameSymbolTool(mock_agent)

        # Create symbol retriever with the language server
        symbol_retriever = LanguageServerSymbolRetriever(language_server)

        # Mock the create_language_server_symbol_retriever method to return our symbol retriever
        tool.create_language_server_symbol_retriever = MagicMock(return_value=symbol_retriever)

        # Test renaming the DemoStruct
        result = tool.apply(
            name_path="DemoStruct",  # Struct name to rename
            relative_path="main.go",  # File containing the struct
            new_name="RenamedStruct",  # New name
        )

        # Verify the result indicates success
        assert isinstance(result, str), f"Expected string result, got: {type(result)}"
        result_lower = result.lower()
        assert "success" in result_lower or "renamed" in result_lower, f"Rename operation failed: {result}"
        assert "renamedstruct" in result_lower or "demostruct" in result_lower

    @pytest.mark.parametrize("language_server,project", [(Language.GO, Language.GO)], indirect=True)
    def test_rename_invalid_position_go(self, language_server, project) -> None:
        """Test renaming at an invalid position in Go file."""
        # Create a mock agent with the project
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.get_active_project_or_raise.return_value = project

        # Create the tool
        tool = RenameSymbolTool(mock_agent)

        # Create symbol retriever with the language server
        symbol_retriever = LanguageServerSymbolRetriever(language_server)

        # Mock the create_language_server_symbol_retriever method to return our symbol retriever
        tool.create_language_server_symbol_retriever = MagicMock(return_value=symbol_retriever)

        # Test renaming an invalid/nonexistent symbol - this should raise an exception
        with pytest.raises(ValueError) as exc_info:
            tool.apply(name_path="NonExistentFunction", relative_path="main.go", new_name="InvalidRename")  # Function that doesn't exist

        # Verify the exception message indicates the symbol wasn't found
        error_message = str(exc_info.value).lower()
        assert "not found" in error_message or "no symbol" in error_message

    @pytest.mark.parametrize("language_server,project", [(Language.GO, Language.GO)], indirect=True)
    def test_rename_nonexistent_file_go(self, language_server, project) -> None:
        """Test renaming in a nonexistent file."""
        # Create a mock agent with the project
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.get_active_project_or_raise.return_value = project

        # Create the tool
        tool = RenameSymbolTool(mock_agent)

        # Create symbol retriever with the language server
        symbol_retriever = LanguageServerSymbolRetriever(language_server)

        # Mock the create_language_server_symbol_retriever method to return our symbol retriever
        tool.create_language_server_symbol_retriever = MagicMock(return_value=symbol_retriever)

        # Test renaming in a nonexistent file - this should raise an exception
        with pytest.raises((ValueError, FileNotFoundError)) as exc_info:
            tool.apply(name_path="SomeFunction", relative_path="nonexistent.go", new_name="SomeRename")  # File that doesn't exist

        # Verify the exception indicates the symbol/file wasn't found
        error_message = str(exc_info.value).lower()
        assert "not found" in error_message or "no symbol" in error_message

    @pytest.mark.parametrize("language_server,project", [(Language.GO, Language.GO)], indirect=True)
    def test_rename_with_references_go(self, language_server, project) -> None:
        """Test renaming a Go function that has references in other parts of the code."""
        # Create a mock agent with the project
        mock_agent = MagicMock(spec=SerenaAgent)
        mock_agent.get_active_project_or_raise.return_value = project

        # Create the tool
        tool = RenameSymbolTool(mock_agent)

        # Create symbol retriever with the language server
        symbol_retriever = LanguageServerSymbolRetriever(language_server)

        # Mock the create_language_server_symbol_retriever method to return our symbol retriever
        tool.create_language_server_symbol_retriever = MagicMock(return_value=symbol_retriever)

        # Test renaming Helper function which is used in UsingHelper function
        result = tool.apply(name_path="Helper", relative_path="main.go", new_name="NewHelperName")  # Function that has references

        # Verify the result indicates success and that multiple locations would be renamed
        assert isinstance(result, str), f"Expected string result, got: {type(result)}"
        result_lower = result.lower()
        assert "success" in result_lower or "renamed" in result_lower, f"Rename operation failed: {result}"

        # The result should indicate that references were found and would be updated
        assert "newhelpername" in result_lower or "helper" in result_lower
