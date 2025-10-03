"""
Tests for Agent class polyglot support - Phase 1.3 Step 2/3.

Following TDD approach: Tests written FIRST before implementation.
Following AGENTS.md M4 START TDD CYCLE: RED → GREEN → COMMIT → AI PANEL
Issue: #221 - Enable Multi-Language (Polyglot) Support in Serena
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig
from serena.project import Project
from solidlsp.ls_config import Language


class TestAgentPolyglotIntegration:
    """Test Agent class integration with LSPManager."""

    def setup_method(self):
        """Set up test environment before each test method."""
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

        # Create a polyglot project config
        self.config = ProjectConfig(
            project_name="test_polyglot_agent",
            languages=[Language.PYTHON, Language.RUST, Language.HASKELL],
        )

        # Create project
        self.project = Project(
            project_root=str(self.project_path),
            project_config=self.config,
        )

    def teardown_method(self):
        """Clean up test environment after each test method."""
        shutil.rmtree(self.test_dir)

    def test_agent_has_lsp_manager_attribute(self):
        """Test that Agent class has lsp_manager attribute."""
        agent = SerenaAgent()

        assert hasattr(agent, "lsp_manager")

    def test_agent_has_reset_lsp_manager_method(self):
        """Test that Agent class has reset_lsp_manager method."""
        agent = SerenaAgent()

        assert hasattr(agent, "reset_lsp_manager")
        assert callable(getattr(agent, "reset_lsp_manager"))

    def test_agent_has_get_language_server_for_file_method(self):
        """Test that Agent class has get_language_server_for_file method."""
        agent = SerenaAgent()

        assert hasattr(agent, "get_language_server_for_file")
        assert callable(getattr(agent, "get_language_server_for_file"))

    def test_is_language_server_running_checks_manager(self):
        """Test that is_language_server_running checks LSPManager state."""
        agent = SerenaAgent()

        # Initially no manager
        assert not agent.is_language_server_running()

        # After creating manager (mocked)
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_all_working_language_servers.return_value = [MagicMock()]

        assert agent.is_language_server_running()

    def test_get_language_server_for_file_routes_correctly(self):
        """Test that get_language_server_for_file routes files correctly."""
        agent = SerenaAgent()

        # Mock LSPManager
        agent.lsp_manager = MagicMock()
        mock_lsp = MagicMock()
        agent.lsp_manager.get_language_server_for_file.return_value = mock_lsp

        lsp = agent.get_language_server_for_file("src/main.py")

        assert lsp == mock_lsp
        agent.lsp_manager.get_language_server_for_file.assert_called_once_with("src/main.py")

    def test_backward_compatibility_language_server_property(self):
        """Test that language_server property still works for backward compatibility."""
        agent = SerenaAgent()

        # Mock LSPManager with working LSPs
        agent.lsp_manager = MagicMock()
        mock_python_lsp = MagicMock()
        agent.lsp_manager.get_all_working_language_servers.return_value = [mock_python_lsp]

        # Should return first working LSP for backward compatibility
        assert agent.language_server == mock_python_lsp

    def test_backward_compatibility_language_server_none_when_no_lsps(self):
        """Test that language_server property returns None when no LSPs running."""
        agent = SerenaAgent()

        # Mock LSPManager with no working LSPs
        agent.lsp_manager = MagicMock()
        agent.lsp_manager.get_all_working_language_servers.return_value = []

        # Should return None for backward compatibility
        assert agent.language_server is None
