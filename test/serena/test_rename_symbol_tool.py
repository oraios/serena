"""
Tests for the RenameSymbolTool
"""

from unittest.mock import Mock

import pytest

from serena.agent import SerenaAgent
from serena.project import Project
from serena.symbol import LanguageServerSymbol, LanguageServerSymbolLocation, LanguageServerSymbolRetriever
from serena.tools.symbol_tools import RenameSymbolTool
from solidlsp.ls import SolidLanguageServer


class TestRenameSymbolTool:
    def test_rename_symbol_success(self):
        """Test successful symbol renaming"""
        # Mock the agent and project
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_project.project_root = "/test/project"

        # Mock the language server
        mock_language_server = Mock(spec=SolidLanguageServer)

        # Mock the symbol retriever
        mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)
        mock_symbol_retriever.get_language_server.return_value = mock_language_server

        # Mock a symbol location
        mock_location = Mock(spec=LanguageServerSymbolLocation)
        mock_location.has_position_in_file.return_value = True
        mock_location.line = 10
        mock_location.column = 5

        # Mock a symbol
        mock_symbol = Mock(spec=LanguageServerSymbol)
        mock_symbol.location = mock_location

        # Mock the find_by_name result
        mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

        # Mock the rename result
        mock_workspace_edit = Mock()
        mock_workspace_edit.changes = {
            "file:///test/project/file.py": [
                {"range": {"start": {"line": 10, "character": 5}, "end": {"line": 10, "character": 15}}, "newText": "new_name"}
            ]
        }
        mock_language_server.rename_symbol.return_value = mock_workspace_edit

        # Setup agent to return the project
        mock_agent.get_active_project_or_raise.return_value = mock_project

        # Create the tool
        tool = RenameSymbolTool(mock_agent)
        tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

        # Test the rename
        result = tool.apply(name_path="old_name", relative_path="file.py", new_name="new_name")

        # Verify the calls
        mock_symbol_retriever.find_by_name.assert_called_once_with("old_name", within_relative_path="file.py")
        mock_language_server.rename_symbol.assert_called_once_with(relative_file_path="file.py", line=10, column=5, new_name="new_name")
        mock_language_server.apply_workspace_edit.assert_called_once_with(mock_workspace_edit)

        # Check the result
        assert "Successfully renamed 'old_name' to 'new_name'" in result
        assert "1 file(s)" in result

    def test_rename_symbol_not_found(self):
        """Test error when symbol is not found"""
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)

        # Mock empty find result
        mock_symbol_retriever.find_by_name.return_value = []

        # Setup agent to return the project
        mock_agent.get_active_project_or_raise.return_value = mock_project

        tool = RenameSymbolTool(mock_agent)
        tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

        # Test that it raises ValueError
        with pytest.raises(ValueError, match=r"No symbol with name 'nonexistent' found in file 'file\.py'"):
            tool.apply(name_path="nonexistent", relative_path="file.py", new_name="new_name")

    def test_rename_symbol_multiple_matches(self):
        """Test error when multiple symbols match"""
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)

        # Mock multiple symbols found
        mock_symbol1 = Mock(spec=LanguageServerSymbol)
        mock_symbol2 = Mock(spec=LanguageServerSymbol)
        mock_symbol_retriever.find_by_name.return_value = [mock_symbol1, mock_symbol2]

        # Setup agent to return the project
        mock_agent.get_active_project_or_raise.return_value = mock_project

        tool = RenameSymbolTool(mock_agent)
        tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

        # Test that it raises ValueError
        with pytest.raises(ValueError, match=r"Found 2 symbols with name 'ambiguous' in file 'file\.py'"):
            tool.apply(name_path="ambiguous", relative_path="file.py", new_name="new_name")

    def test_rename_symbol_invalid_position(self):
        """Test error when symbol has no valid position"""
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)

        # Mock symbol with invalid location
        mock_location = Mock(spec=LanguageServerSymbolLocation)
        mock_location.has_position_in_file.return_value = False

        mock_symbol = Mock(spec=LanguageServerSymbol)
        mock_symbol.location = mock_location

        mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

        # Setup agent to return the project
        mock_agent.get_active_project_or_raise.return_value = mock_project

        tool = RenameSymbolTool(mock_agent)
        tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

        # Test that it raises ValueError
        with pytest.raises(ValueError, match="Symbol 'test_symbol' does not have a valid position in file for renaming"):
            tool.apply(name_path="test_symbol", relative_path="file.py", new_name="new_name")

    def test_rename_symbol_no_rename_support(self):
        """Test error when language server returns no rename edits"""
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_language_server = Mock(spec=SolidLanguageServer)
        mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)
        mock_symbol_retriever.get_language_server.return_value = mock_language_server

        # Mock valid symbol
        mock_location = Mock(spec=LanguageServerSymbolLocation)
        mock_location.has_position_in_file.return_value = True
        mock_location.line = 10
        mock_location.column = 5

        mock_symbol = Mock(spec=LanguageServerSymbol)
        mock_symbol.location = mock_location

        mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

        # Mock no rename support
        mock_language_server.rename_symbol.return_value = None

        # Setup agent to return the project
        mock_agent.get_active_project_or_raise.return_value = mock_project

        tool = RenameSymbolTool(mock_agent)
        tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

        # Test that it raises ValueError
        with pytest.raises(ValueError, match="Language server returned no rename edits"):
            tool.apply(name_path="test_symbol", relative_path="file.py", new_name="new_name")
