"""
Simple integration test for rename functionality (without actual language server)
"""

import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from src.serena.tools.symbol_tools import RenameSymbolTool
from src.serena.symbol import LanguageServerSymbolRetriever, LanguageServerSymbol, LanguageServerSymbolLocation
from src.serena.agent import SerenaAgent
from src.serena.project import Project
from solidlsp import SolidLanguageServer
from solidlsp import ls_types


class TestRenameSymbolSimple:
    """Simple tests without real language servers - focused on tool logic"""

    def test_rename_tool_workflow_mocked(self):
        """Test the rename tool workflow with mocked language server"""
        # Create temporary test files
        temp_dir = Path(tempfile.mkdtemp())
        test_file = temp_dir / "test.py"
        test_file.write_text("def old_function():\n    pass\n\nold_function()\n")

        try:
            # Setup mocks
            mock_agent = Mock(spec=SerenaAgent)
            mock_project = Mock(spec=Project)
            mock_project.project_root = str(temp_dir)

            mock_language_server = Mock(spec=SolidLanguageServer)
            mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)
            mock_symbol_retriever.get_language_server.return_value = mock_language_server

            # Mock symbol location
            mock_location = Mock(spec=LanguageServerSymbolLocation)
            mock_location.has_position_in_file.return_value = True
            mock_location.line = 0
            mock_location.column = 4

            # Mock symbol
            mock_symbol = Mock(spec=LanguageServerSymbol)
            mock_symbol.location = mock_location
            mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

            # Mock workspace edit result
            mock_workspace_edit = Mock()
            mock_workspace_edit.changes = {
                f"file://{test_file}": [
                    {"range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 16}}, "newText": "new_function"},
                    {"range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 12}}, "newText": "new_function"},
                ]
            }
            mock_language_server.rename_symbol.return_value = mock_workspace_edit
            mock_language_server.apply_workspace_edit = Mock()

            # Setup agent to return the project
            mock_agent.get_active_project_or_raise.return_value = mock_project

            # Create and test tool
            tool = RenameSymbolTool(mock_agent)
            tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

            # Perform rename
            result = tool.apply(name_path="old_function", relative_path="test.py", new_name="new_function")

            # Verify calls were made correctly
            mock_symbol_retriever.find_by_name.assert_called_once_with("old_function", within_relative_path="test.py")
            mock_language_server.rename_symbol.assert_called_once_with(
                relative_file_path="test.py", line=0, column=4, new_name="new_function"
            )
            mock_language_server.apply_workspace_edit.assert_called_once_with(mock_workspace_edit)

            # Verify result
            assert "Successfully renamed 'old_function' to 'new_function'" in result
            assert "1 file(s)" in result

        finally:
            shutil.rmtree(temp_dir)

    def test_rename_tool_error_cases(self):
        """Test various error conditions"""
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_project.project_root = "/test"
        mock_agent.get_active_project_or_raise.return_value = mock_project

        tool = RenameSymbolTool(mock_agent)  # Test: No symbol found
        mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)
        mock_symbol_retriever.find_by_name.return_value = []
        tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

        with pytest.raises(ValueError, match="No symbol with name 'missing' found"):
            tool.apply(name_path="missing", relative_path="test.py", new_name="new_name")

        # Test: Multiple symbols found
        mock_symbol1 = Mock(spec=LanguageServerSymbol)
        mock_symbol2 = Mock(spec=LanguageServerSymbol)
        mock_symbol_retriever.find_by_name.return_value = [mock_symbol1, mock_symbol2]

        with pytest.raises(ValueError, match="Found 2 symbols with name 'ambiguous'"):
            tool.apply(name_path="ambiguous", relative_path="test.py", new_name="new_name")

        # Test: Symbol with invalid location
        mock_location = Mock(spec=LanguageServerSymbolLocation)
        mock_location.has_position_in_file.return_value = False
        mock_symbol = Mock(spec=LanguageServerSymbol)
        mock_symbol.location = mock_location
        mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

        with pytest.raises(ValueError, match="does not have a valid position in file for renaming"):
            tool.apply(name_path="test_symbol", relative_path="test.py", new_name="new_name")

        # Test: Language server returns None (rename not supported)
        mock_location = Mock(spec=LanguageServerSymbolLocation)
        mock_location.has_position_in_file.return_value = True
        mock_location.line = 0
        mock_location.column = 0
        mock_symbol = Mock(spec=LanguageServerSymbol)
        mock_symbol.location = mock_location
        mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

        mock_language_server = Mock(spec=SolidLanguageServer)
        mock_language_server.rename_symbol.return_value = None
        mock_symbol_retriever.get_language_server.return_value = mock_language_server

        with pytest.raises(ValueError, match="Language server returned no rename edits"):
            tool.apply(name_path="test_symbol", relative_path="test.py", new_name="new_name")

    def test_workspace_edit_documentchanges_format(self):
        """Test handling of documentChanges format in workspace edits"""
        temp_dir = Path(tempfile.mkdtemp())
        mock_agent = Mock(spec=SerenaAgent)
        mock_project = Mock(spec=Project)
        mock_project.project_root = str(temp_dir)

        try:
            # Setup tool with mocks
            mock_language_server = Mock(spec=SolidLanguageServer)
            mock_symbol_retriever = Mock(spec=LanguageServerSymbolRetriever)
            mock_symbol_retriever.get_language_server.return_value = mock_language_server

            # Mock valid symbol
            mock_location = Mock(spec=LanguageServerSymbolLocation)
            mock_location.has_position_in_file.return_value = True
            mock_location.line = 0
            mock_location.column = 0
            mock_symbol = Mock(spec=LanguageServerSymbol)
            mock_symbol.location = mock_location
            mock_symbol_retriever.find_by_name.return_value = [mock_symbol]

            # Mock workspace edit with documentChanges format
            mock_text_document = Mock()
            mock_text_document.uri = f"file://{temp_dir}/test.py"

            mock_edit = Mock()
            mock_edit.range = Mock()
            mock_edit.range.start = Mock()
            mock_edit.range.start.line = 0
            mock_edit.range.start.character = 0
            mock_edit.range.end = Mock()
            mock_edit.range.end.line = 0
            mock_edit.range.end.character = 5
            mock_edit.newText = "new_name"

            mock_document_change = Mock()
            mock_document_change.textDocument = mock_text_document
            mock_document_change.edits = [mock_edit]

            mock_workspace_edit = Mock()
            mock_workspace_edit.changes = None
            mock_workspace_edit.documentChanges = [mock_document_change]

            mock_language_server.rename_symbol.return_value = mock_workspace_edit
            mock_language_server.apply_workspace_edit = Mock()

            # Setup agent to return the project
            mock_agent.get_active_project_or_raise.return_value = mock_project

            # Create tool and test
            tool = RenameSymbolTool(mock_agent)
            tool.create_language_server_symbol_retriever = Mock(return_value=mock_symbol_retriever)

            result = tool.apply(name_path="old_name", relative_path="test.py", new_name="new_name")

            # Verify it handled documentChanges format
            assert "Successfully renamed 'old_name' to 'new_name'" in result
            assert "1 file(s)" in result

        finally:
            shutil.rmtree(temp_dir)
