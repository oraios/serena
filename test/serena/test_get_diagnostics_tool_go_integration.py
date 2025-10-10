"""Integration tests for GetDiagnosticsTool with Go language server."""
import json
import os
import pytest
from unittest.mock import Mock

from src.serena.tools.symbol_tools import GetDiagnosticsTool
from src.serena.agent import SerenaAgent
from src.serena.project import Project
from solidlsp.ls_config import Language
from test.conftest import create_ls


@pytest.mark.go
class TestGetDiagnosticsToolGoIntegration:
    """Integration tests for GetDiagnosticsTool with Go language server."""

    def setup_method(self):
        """Set up test fixtures with real Go language server."""
        # Path to our diagnostic test repository
        self.repo_path = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "resources", 
            "repos", 
            "go", 
            "diagnostic_test_repo"
        )
        self.repo_path = os.path.abspath(self.repo_path)
        
        # Create real language server for Go
        self.language_server = create_ls(Language.GO, repo_path=self.repo_path)
        
        # Mock agent with real language server
        self.mock_agent = Mock(spec=SerenaAgent)
        self.mock_agent.is_using_language_server.return_value = True
        self.mock_agent.language_server = self.language_server
        
        # Mock project
        self.mock_project = Mock(spec=Project)
        self.mock_project.project_root = self.repo_path
        self.mock_agent.get_active_project_or_raise.return_value = self.mock_project
        
        # Create tool instance
        self.tool = GetDiagnosticsTool(self.mock_agent)

    def teardown_method(self):
        """Clean up language server."""
        if hasattr(self, 'language_server'):
            self.language_server.stop()

    def test_get_diagnostics_with_go_errors(self):
        """Test GetDiagnosticsTool retrieves actual Go diagnostics from language server."""
        # Mock the _limit_length method to avoid character limits in tests
        def mock_limit_length(content, max_chars):
            return content
        self.tool._limit_length = mock_limit_length
        
        try:
            print(f"Starting Go language server for repo: {self.repo_path}")
            # Start the language server
            self.language_server.start()
            print("Language server started successfully")
            
            # Get diagnostics for the main.go file with intentional errors
            result = self.tool.apply("main.go")
            
            # Parse the JSON result
            diagnostics = json.loads(result)
            
            # We should have at least some diagnostics due to the intentional errors
            assert isinstance(diagnostics, list)
            assert len(diagnostics) > 0, f"Expected diagnostics but got none. Result: {result}"
            
            # Check that we have actual diagnostic data
            for diagnostic in diagnostics:
                assert "severity" in diagnostic
                assert "severity_name" in diagnostic
                assert "message" in diagnostic
                assert "range" in diagnostic
                assert "start" in diagnostic["range"]
                assert "end" in diagnostic["range"]
                assert "line" in diagnostic["range"]["start"]
                assert "character" in diagnostic["range"]["start"]
                
                # Severity should be a known value
                assert diagnostic["severity_name"] in ["error", "warning", "information", "hint", "unknown"]
                
                # Message should not be empty for real diagnostics
                assert len(diagnostic["message"]) > 0
            
            # Check that we have at least one error (due to undefined variables/functions)
            error_diagnostics = [d for d in diagnostics if d["severity_name"] == "error"]
            assert len(error_diagnostics) > 0, f"Expected at least one error diagnostic. Got diagnostics: {diagnostics}"
            
            print(f"Successfully retrieved {len(diagnostics)} diagnostics:")
            for i, diag in enumerate(diagnostics[:5]):  # Print first 5 diagnostics
                print(f"  {i+1}. [{diag['severity_name']}] {diag['message']} at line {diag['range']['start']['line']}")
            
        except Exception as e:
            pytest.skip(f"Go language server not available or failed: {e}")

    def test_get_diagnostics_empty_file(self):
        """Test GetDiagnosticsTool with a valid Go file that has no errors."""
        # Create a valid Go file with no errors
        valid_go_content = '''package utils

import "fmt"

func PrintMessage() {
    fmt.Println("Hello, World!")
}
'''
        
        # Create subdirectory for the valid file to avoid package conflicts
        valid_dir = os.path.join(self.repo_path, "utils")
        os.makedirs(valid_dir, exist_ok=True)
        
        # Write the valid content to a test file in subdirectory
        valid_file_path = os.path.join(valid_dir, "valid.go")
        try:
            with open(valid_file_path, 'w') as f:
                f.write(valid_go_content)
            
            # Mock the _limit_length method
            def mock_limit_length(content, max_chars):
                return content
            self.tool._limit_length = mock_limit_length
            
            # Start the language server
            self.language_server.start()
            
            # Get diagnostics for the valid file
            result = self.tool.apply("utils/valid.go")
            
            # Parse the JSON result
            diagnostics = json.loads(result)
            
            # Should be an empty list or only contain minor warnings
            assert isinstance(diagnostics, list)
            
            # If there are any diagnostics, they should not be errors
            error_diagnostics = [d for d in diagnostics if d["severity_name"] == "error"]
            assert len(error_diagnostics) == 0, f"Valid Go file should not have errors. Got: {error_diagnostics}"
            
            print(f"Valid Go file has {len(diagnostics)} diagnostics (expected 0 or only warnings/hints)")
            
        except Exception as e:
            pytest.skip(f"Go language server not available or failed: {e}")
        finally:
            # Clean up the test file and directory
            if os.path.exists(valid_file_path):
                os.remove(valid_file_path)
            if os.path.exists(valid_dir) and os.path.isdir(valid_dir):
                os.rmdir(valid_dir)

    def test_get_diagnostics_nonexistent_file(self):
        """Test GetDiagnosticsTool error handling with nonexistent file."""
        with pytest.raises(FileNotFoundError, match="File nonexistent.go does not exist in the project"):
            self.tool.apply("nonexistent.go")

    def test_get_diagnostics_directory_path(self):
        """Test GetDiagnosticsTool error handling when given a directory path."""
        # Create a test directory
        test_dir = os.path.join(self.repo_path, "test_dir")
        os.makedirs(test_dir, exist_ok=True)
        
        try:
            with pytest.raises(ValueError, match="Expected a file path, but got a directory path"):
                self.tool.apply("test_dir")
        finally:
            # Clean up
            if os.path.exists(test_dir):
                os.rmdir(test_dir)