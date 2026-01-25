"""Tests for Claude Code MCP configuration management."""

import json
import tempfile
from pathlib import Path

import pytest

from murena.config.claude_code_integration import ClaudeCodeConfigManager
from murena.config.murena_config import ProjectConfig, RegisteredProject


@pytest.fixture
def temp_config_dir():
    """Create a temporary .claude directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config_manager(temp_config_dir):
    """Create a ClaudeCodeConfigManager with temp directory."""
    return ClaudeCodeConfigManager(config_path=temp_config_dir)


@pytest.fixture
def mock_registered_project(tmp_path):
    """Create a mock RegisteredProject."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    murena_dir = project_dir / ".murena"
    murena_dir.mkdir()

    project_yml = murena_dir / "project.yml"
    project_yml.write_text(
        """
project_name: test-project
languages:
  - python
ignored_paths: []
excluded_tools: []
included_optional_tools: []
"""
    )

    project_config = ProjectConfig.load(project_dir)
    return RegisteredProject(
        project_root=str(project_dir),
        project_config=project_config,
    )


class TestClaudeCodeConfigManager:
    """Tests for ClaudeCodeConfigManager."""

    def test_init_creates_config_path(self, temp_config_dir):
        """Test that initialization sets up paths correctly."""
        manager = ClaudeCodeConfigManager(config_path=temp_config_dir)

        assert manager.config_dir == temp_config_dir
        assert manager.mcp_config_path == temp_config_dir / "mcp_servers_murena.json"

    def test_add_project_server(self, config_manager, mock_registered_project):
        """Test adding a project server configuration."""
        server_name = config_manager.add_project_server(mock_registered_project)

        # Server name should be correct
        expected_name = "murena-test-project"
        assert server_name == expected_name

        # Config file should exist
        assert config_manager.mcp_config_path.exists()

        # Config should contain the server
        configs = json.loads(config_manager.mcp_config_path.read_text())
        assert expected_name in configs

        # Config should have correct structure
        server_config = configs[expected_name]
        assert server_config["command"] == "uv"
        assert server_config["args"][0] == "run"
        assert server_config["args"][1] == "--project"
        # args[2] should be the murena installation path
        assert "murena" in server_config["args"]
        assert "start-mcp-server" in server_config["args"]
        assert str(mock_registered_project.project_root) in server_config["args"]
        assert "--context" in server_config["args"]
        assert "claude-code" in server_config["args"]

    def test_add_multiple_projects(self, config_manager, mock_registered_project, tmp_path):
        """Test adding multiple projects."""
        # Add first project
        config_manager.add_project_server(mock_registered_project)

        # Create and add second project
        project_dir2 = tmp_path / "another-project"
        project_dir2.mkdir()
        (project_dir2 / ".murena").mkdir()
        (project_dir2 / ".murena" / "project.yml").write_text(
            """
project_name: another-project
languages:
  - python
"""
        )

        project_config2 = ProjectConfig.load(project_dir2)
        registered_project2 = RegisteredProject(
            project_root=str(project_dir2),
            project_config=project_config2,
        )

        config_manager.add_project_server(registered_project2)

        # Both should be in config
        configs = json.loads(config_manager.mcp_config_path.read_text())
        assert "murena-test-project" in configs
        assert "murena-another-project" in configs

    def test_remove_project_server(self, config_manager, mock_registered_project):
        """Test removing a project server."""
        # Add project
        config_manager.add_project_server(mock_registered_project)

        # Remove it
        result = config_manager.remove_project_server("test-project")
        assert result is True

        # Should not be in config anymore
        configs = json.loads(config_manager.mcp_config_path.read_text())
        assert "murena-test-project" not in configs

    def test_remove_nonexistent_project(self, config_manager):
        """Test removing a project that doesn't exist."""
        result = config_manager.remove_project_server("nonexistent")
        assert result is False

    def test_list_configured_projects_empty(self, config_manager):
        """Test listing projects when none are configured."""
        projects = config_manager.list_configured_projects()
        assert projects == []

    def test_list_configured_projects(self, config_manager, mock_registered_project):
        """Test listing configured projects."""
        # Add project
        config_manager.add_project_server(mock_registered_project)

        projects = config_manager.list_configured_projects()
        assert "murena-test-project" in projects

    def test_list_configured_projects_filters_non_murena(self, config_manager, mock_registered_project):
        """Test that listing filters out non-murena servers."""
        # Add murena project
        config_manager.add_project_server(mock_registered_project)

        # Manually add a non-murena server
        configs = config_manager._load_configs()
        configs["other-server"] = {"command": "test", "args": []}
        config_manager._save_configs(configs)

        # Should only list murena servers
        projects = config_manager.list_configured_projects()
        assert "murena-test-project" in projects
        assert "other-server" not in projects

    def test_get_project_config(self, config_manager, mock_registered_project):
        """Test getting configuration for a specific project."""
        # Add project
        config_manager.add_project_server(mock_registered_project)

        # Get config
        config = config_manager.get_project_config("test-project")

        assert config is not None
        assert config["command"] == "uv"
        assert config["args"][0] == "run"
        assert config["args"][1] == "--project"
        assert "murena" in config["args"]
        assert "start-mcp-server" in config["args"]
        assert "--context" in config["args"]
        assert "claude-code" in config["args"]

    def test_get_project_config_nonexistent(self, config_manager):
        """Test getting config for non-existent project."""
        config = config_manager.get_project_config("nonexistent")
        assert config is None

    def test_sync_with_discovered_projects_add_new(self, config_manager, mock_registered_project, tmp_path):
        """Test syncing adds new projects."""
        # Create second project
        project_dir2 = tmp_path / "new-project"
        project_dir2.mkdir()
        (project_dir2 / ".murena").mkdir()
        (project_dir2 / ".murena" / "project.yml").write_text(
            """
project_name: new-project
languages:
  - python
"""
        )

        project_config2 = ProjectConfig.load(project_dir2)
        registered_project2 = RegisteredProject(
            project_root=str(project_dir2),
            project_config=project_config2,
        )

        # Sync with both projects
        added, updated, removed = config_manager.sync_with_discovered_projects(
            [mock_registered_project, registered_project2], remove_stale=False
        )

        assert len(added) == 2
        assert len(updated) == 0
        assert len(removed) == 0

        # Both should be in config
        configs = json.loads(config_manager.mcp_config_path.read_text())
        assert "murena-test-project" in configs
        assert "murena-new-project" in configs

    def test_sync_with_discovered_projects_remove_stale(self, config_manager, mock_registered_project):
        """Test syncing removes stale projects when enabled."""
        # Add initial project
        config_manager.add_project_server(mock_registered_project)

        # Manually add a stale project
        configs = config_manager._load_configs()
        configs["murena-stale-project"] = {"command": "uvx", "args": []}
        config_manager._save_configs(configs)

        # Sync with only the mock project (should remove stale)
        added, updated, removed = config_manager.sync_with_discovered_projects([mock_registered_project], remove_stale=True)

        assert len(added) == 0
        assert len(updated) == 0
        assert len(removed) == 1
        assert "murena-stale-project" in removed

        # Stale project should be gone
        configs = json.loads(config_manager.mcp_config_path.read_text())
        assert "murena-stale-project" not in configs

    def test_sync_with_discovered_projects_no_remove_stale(self, config_manager, mock_registered_project):
        """Test syncing preserves stale projects when not enabled."""
        # Add initial project
        config_manager.add_project_server(mock_registered_project)

        # Manually add a stale project
        configs = config_manager._load_configs()
        configs["murena-stale-project"] = {"command": "uvx", "args": []}
        config_manager._save_configs(configs)

        # Sync without removing stale
        added, updated, removed = config_manager.sync_with_discovered_projects([mock_registered_project], remove_stale=False)

        assert len(removed) == 0

        # Stale project should still be there
        configs = json.loads(config_manager.mcp_config_path.read_text())
        assert "murena-stale-project" in configs

    def test_merge_with_existing(self, config_manager, mock_registered_project):
        """Test merging new configs with existing ones."""
        # Create initial config
        initial_config = {"existing-server": {"command": "test", "args": []}}
        config_manager._save_configs(initial_config)

        # Merge new configs
        new_configs = {"murena-test-project": {"command": "uvx", "args": ["murena"]}}
        merged = config_manager.merge_with_existing(new_configs)

        # Should have both
        assert "existing-server" in merged
        assert "murena-test-project" in merged

    def test_config_file_creation(self, config_manager, mock_registered_project):
        """Test that config file is created with correct permissions."""
        config_manager.add_project_server(mock_registered_project)

        # File should exist and be readable
        assert config_manager.mcp_config_path.exists()
        assert config_manager.mcp_config_path.is_file()

        # Should be valid JSON
        content = json.loads(config_manager.mcp_config_path.read_text())
        assert isinstance(content, dict)
