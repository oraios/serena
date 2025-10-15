"""Tests for the GetDiagnosticsTool."""

import json
from unittest.mock import Mock, patch

import pytest

from src.serena.agent import SerenaAgent
from src.serena.project import Project
from src.serena.tools.symbol_tools import GetDiagnosticsTool


class TestGetDiagnosticsTool:
    """Unit tests for GetDiagnosticsTool."""

    def setup_method(self):
        """Set up test fixtures."""
        # Mock agent
        self.mock_agent = Mock(spec=SerenaAgent)
        self.mock_agent.is_using_language_server.return_value = True

        # Mock language server
        self.mock_language_server = Mock()
        self.mock_agent.language_server = self.mock_language_server

        # Mock project
        self.mock_project = Mock(spec=Project)
        self.mock_project.project_root = "/test/project"
        self.mock_agent.get_active_project_or_raise.return_value = self.mock_project

        # Create tool instance
        self.tool = GetDiagnosticsTool(self.mock_agent)

    def test_get_severity_name(self):
        """Test the _get_severity_name helper method."""
        assert self.tool._get_severity_name(1) == "error"
        assert self.tool._get_severity_name(2) == "warning"
        assert self.tool._get_severity_name(3) == "information"
        assert self.tool._get_severity_name(4) == "hint"
        assert self.tool._get_severity_name(None) == "unknown"
        assert self.tool._get_severity_name(999) == "unknown(999)"

    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_apply_success_with_diagnostics(self, mock_isdir, mock_exists):
        """Test successful diagnostic retrieval with results."""
        # Setup mocks
        mock_exists.return_value = True
        mock_isdir.return_value = False

        # Mock diagnostic data
        mock_diagnostics = [
            {
                "severity": 1,
                "message": "Undefined variable 'foo'",
                "code": "undefined-variable",
                "source": "pylsp",
                "range": {"start": {"line": 10, "character": 5}, "end": {"line": 10, "character": 8}},
            },
            {
                "severity": 2,
                "message": "Line too long",
                "code": "E501",
                "source": "flake8",
                "range": {"start": {"line": 20, "character": 0}, "end": {"line": 20, "character": 100}},
            },
        ]

        self.mock_language_server.request_text_document_diagnostics.return_value = mock_diagnostics

        # Mock the _limit_length method
        with patch.object(self.tool, "_limit_length", side_effect=lambda x, _: x):
            result = self.tool.apply("test_file.py")

        # Verify result
        result_data = json.loads(result)
        assert len(result_data) == 2

        # Check first diagnostic
        diag1 = result_data[0]
        assert diag1["severity"] == 1
        assert diag1["severity_name"] == "error"
        assert diag1["message"] == "Undefined variable 'foo'"
        assert diag1["code"] == "undefined-variable"
        assert diag1["source"] == "pylsp"
        assert diag1["range"]["start"]["line"] == 10
        assert diag1["range"]["start"]["character"] == 5

        # Check second diagnostic
        diag2 = result_data[1]
        assert diag2["severity"] == 2
        assert diag2["severity_name"] == "warning"
        assert diag2["message"] == "Line too long"

        # Verify method calls
        self.mock_language_server.request_text_document_diagnostics.assert_called_once_with("test_file.py")

    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_apply_success_no_diagnostics(self, mock_isdir, mock_exists):
        """Test successful diagnostic retrieval with no results."""
        # Setup mocks
        mock_exists.return_value = True
        mock_isdir.return_value = False

        self.mock_language_server.request_text_document_diagnostics.return_value = []

        # Mock the _limit_length method
        with patch.object(self.tool, "_limit_length", side_effect=lambda x, _: x):
            result = self.tool.apply("clean_file.py")

        # Verify result
        result_data = json.loads(result)
        assert len(result_data) == 0
        assert result_data == []

    def test_apply_no_language_server(self):
        """Test error when language server is not available."""
        self.mock_agent.is_using_language_server.return_value = False

        with pytest.raises(Exception, match="Cannot get diagnostics; agent is not in language server mode"):
            self.tool.apply("test_file.py")

    @patch("os.path.exists")
    def test_apply_file_not_found(self, mock_exists):
        """Test error when file does not exist."""
        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError, match=r"File test_file.py does not exist in the project"):
            self.tool.apply("test_file.py")

    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_apply_is_directory(self, mock_isdir, mock_exists):
        """Test error when path is a directory instead of a file."""
        mock_exists.return_value = True
        mock_isdir.return_value = True

        with pytest.raises(ValueError, match="Expected a file path, but got a directory path: test_dir"):
            self.tool.apply("test_dir")

    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_apply_language_server_error(self, mock_isdir, mock_exists):
        """Test handling of language server errors."""
        mock_exists.return_value = True
        mock_isdir.return_value = False

        # Mock language server to raise an exception
        self.mock_language_server.request_text_document_diagnostics.side_effect = Exception("Language server failed")

        with pytest.raises(RuntimeError, match=r"Failed to retrieve diagnostics for test_file.py: Language server failed"):
            self.tool.apply("test_file.py")

    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_apply_with_missing_fields(self, mock_isdir, mock_exists):
        """Test handling of diagnostics with missing optional fields."""
        # Setup mocks
        mock_exists.return_value = True
        mock_isdir.return_value = False

        # Mock diagnostic with missing optional fields
        mock_diagnostics = [
            {
                "message": "Error without optional fields",
                "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 10}},
                # Missing severity, code, source
            }
        ]

        self.mock_language_server.request_text_document_diagnostics.return_value = mock_diagnostics

        # Mock the _limit_length method
        with patch.object(self.tool, "_limit_length", side_effect=lambda x, _: x):
            result = self.tool.apply("test_file.py")

        # Verify result handles missing fields gracefully
        result_data = json.loads(result)
        assert len(result_data) == 1

        diag = result_data[0]
        assert diag["severity"] == "unknown"
        assert diag["severity_name"] == "unknown"
        assert diag["message"] == "Error without optional fields"
        assert diag["code"] == ""
        assert diag["source"] == ""

    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_apply_with_max_answer_chars(self, mock_isdir, mock_exists):
        """Test limiting output with max_answer_chars parameter."""
        mock_exists.return_value = True
        mock_isdir.return_value = False

        mock_diagnostics = [
            {
                "severity": 1,
                "message": "Test error",
                "code": "test",
                "source": "test",
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}},
            }
        ]

        self.mock_language_server.request_text_document_diagnostics.return_value = mock_diagnostics

        # Mock _limit_length to return truncated result
        with patch.object(self.tool, "_limit_length", return_value="TRUNCATED"):
            result = self.tool.apply("test_file.py", max_answer_chars=100)

        assert result == "TRUNCATED"

    def test_path_construction(self):
        """Test that file paths are constructed correctly."""
        relative_path = "src/module/file.py"

        with (
            patch("os.path.exists", return_value=True),
            patch("os.path.isdir", return_value=False),
            patch.object(self.tool, "_limit_length", side_effect=lambda x, _: x),
        ):

            self.mock_language_server.request_text_document_diagnostics.return_value = []
            self.tool.apply(relative_path)

            # Verify os.path.join was called with correct arguments
            # The actual path checking happens in the method, we verify the LS call
            self.mock_language_server.request_text_document_diagnostics.assert_called_once_with(relative_path)
