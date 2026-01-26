"""Tests for project discovery functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from murena.config.murena_config import ProjectConfig
from murena.multi_project.project_discovery import ProjectDiscovery


@pytest.fixture
def temp_search_root():
    """Create a temporary directory for test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_project_with_yml(temp_search_root):
    """Create a mock project with .murena/project.yml."""
    project_dir = temp_search_root / "test-project-yml"
    project_dir.mkdir()

    murena_dir = project_dir / ".murena"
    murena_dir.mkdir()

    # Create project.yml
    project_yml = murena_dir / "project.yml"
    project_yml.write_text(
        """
project_name: test-project-yml
languages:
  - python
ignored_paths: []
excluded_tools: []
included_optional_tools: []
"""
    )

    return project_dir


@pytest.fixture
def mock_git_project(temp_search_root):
    """Create a mock git project with code files."""
    project_dir = temp_search_root / "test-git-project"
    project_dir.mkdir()

    # Create .git directory
    git_dir = project_dir / ".git"
    git_dir.mkdir()

    # Create some code files
    (project_dir / "main.py").write_text("print('hello')")
    (project_dir / "utils.py").write_text("def helper(): pass")

    return project_dir


@pytest.fixture
def mock_pyproject_toml(temp_search_root):
    """Create a mock project with pyproject.toml containing murena."""
    project_dir = temp_search_root / "test-pyproject"
    project_dir.mkdir()

    # Create pyproject.toml with murena reference
    pyproject = project_dir / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "test-project"
dependencies = ["murena"]
"""
    )

    return project_dir


@pytest.fixture
def mock_non_project(temp_search_root):
    """Create a directory that is not a Murena project."""
    project_dir = temp_search_root / "not-a-project"
    project_dir.mkdir()
    (project_dir / "readme.txt").write_text("Just a text file")
    return project_dir


class TestProjectDiscovery:
    """Tests for ProjectDiscovery class."""

    def test_is_murena_project_with_yml(self, mock_project_with_yml):
        """Test that projects with .murena/project.yml are detected."""
        discovery = ProjectDiscovery()
        assert discovery.is_murena_project(mock_project_with_yml)

    def test_is_murena_project_with_git(self, mock_git_project):
        """Test that git repos with code files are detected."""
        discovery = ProjectDiscovery()
        assert discovery.is_murena_project(mock_git_project)

    def test_is_murena_project_with_pyproject(self, mock_pyproject_toml):
        """Test that projects with pyproject.toml containing murena are detected."""
        discovery = ProjectDiscovery()
        assert discovery.is_murena_project(mock_pyproject_toml)

    def test_is_not_murena_project(self, mock_non_project):
        """Test that non-projects are not detected."""
        discovery = ProjectDiscovery()
        assert not discovery.is_murena_project(mock_non_project)

    def test_is_murena_project_file_path(self, temp_search_root):
        """Test that file paths (not directories) return False."""
        test_file = temp_search_root / "test.txt"
        test_file.write_text("test")
        discovery = ProjectDiscovery()
        assert not discovery.is_murena_project(test_file)

    def test_find_murena_projects_discovers_multiple(self, temp_search_root, mock_project_with_yml, mock_git_project):
        """Test that discovery finds multiple projects."""
        discovery = ProjectDiscovery(search_root=temp_search_root)
        projects = discovery.find_murena_projects()

        # Should find at least 2 projects
        assert len(projects) >= 2

        project_names = {p.project_name for p in projects}
        # The yml project should be found with its configured name
        assert "test-project-yml" in project_names

    def test_find_murena_projects_ignores_hidden(self, temp_search_root):
        """Test that hidden directories are ignored."""
        hidden_dir = temp_search_root / ".hidden-project"
        hidden_dir.mkdir()
        (hidden_dir / ".murena" / "project.yml").parent.mkdir(parents=True)
        (hidden_dir / ".murena" / "project.yml").write_text("project_name: hidden\nlanguages:\n  - python\n")

        discovery = ProjectDiscovery(search_root=temp_search_root)
        projects = discovery.find_murena_projects()

        project_names = {p.project_name for p in projects}
        assert "hidden" not in project_names

    def test_find_murena_projects_empty_directory(self, temp_search_root):
        """Test discovery in empty directory."""
        empty_dir = temp_search_root / "empty"
        empty_dir.mkdir()

        discovery = ProjectDiscovery(search_root=empty_dir)
        projects = discovery.find_murena_projects()

        assert len(projects) == 0

    def test_find_murena_projects_nonexistent_root(self):
        """Test discovery with non-existent search root."""
        nonexistent = Path("/nonexistent/path/to/projects")
        discovery = ProjectDiscovery(search_root=nonexistent)
        projects = discovery.find_murena_projects()

        assert len(projects) == 0

    def test_generate_mcp_config_auto_naming(self, mock_project_with_yml):
        """Test MCP config generation with auto-naming."""
        from murena.config.murena_config import RegisteredProject

        project_config = ProjectConfig.load(mock_project_with_yml)
        registered_project = RegisteredProject(
            project_root=str(mock_project_with_yml),
            project_config=project_config,
        )

        discovery = ProjectDiscovery()
        server_name, mcp_config = discovery.generate_mcp_config(registered_project, auto_name=True)

        # Server name should be murena-{directory_name}
        expected_name = f"murena-{mock_project_with_yml.name}"
        assert server_name == expected_name

        # Config should have correct structure
        assert mcp_config.command == "uvx"
        assert "murena" in mcp_config.args
        assert "start-mcp-server" in mcp_config.args
        # Use resolve() to handle /var vs /private/var on macOS
        assert str(mock_project_with_yml.resolve()) in mcp_config.args or str(mock_project_with_yml) in mcp_config.args
        assert "--auto-name" in mcp_config.args

    def test_generate_mcp_config_no_auto_naming(self, mock_project_with_yml):
        """Test MCP config generation without auto-naming."""
        from murena.config.murena_config import RegisteredProject

        project_config = ProjectConfig.load(mock_project_with_yml)
        registered_project = RegisteredProject(
            project_root=str(mock_project_with_yml),
            project_config=project_config,
        )

        discovery = ProjectDiscovery()
        server_name, mcp_config = discovery.generate_mcp_config(registered_project, auto_name=False)

        # Server name should be just "murena"
        assert server_name == "murena"

    def test_generate_mcp_configs_for_multiple_projects(self, temp_search_root, mock_project_with_yml, mock_git_project):
        """Test generating configs for multiple projects."""
        discovery = ProjectDiscovery(search_root=temp_search_root)
        configs = discovery.generate_mcp_configs()

        # Should generate configs for discovered projects
        assert len(configs) >= 2

        # All config keys should start with "murena-"
        for key in configs.keys():
            assert key.startswith("murena-")

        # Each config should have required fields
        for config in configs.values():
            assert "command" in config
            assert "args" in config
            assert "env" in config

    def test_save_mcp_configs(self, temp_search_root, mock_project_with_yml):
        """Test saving MCP configs to file."""
        output_file = temp_search_root / "mcp_config.json"

        discovery = ProjectDiscovery(search_root=temp_search_root)
        saved_path = discovery.save_mcp_configs(output_path=output_file, merge=False)

        # File should be created
        assert saved_path.exists()
        assert saved_path == output_file

        # Content should be valid JSON
        content = json.loads(output_file.read_text())
        assert isinstance(content, dict)
        assert len(content) > 0

    def test_save_mcp_configs_merge(self, temp_search_root, mock_project_with_yml):
        """Test merging with existing configs."""
        output_file = temp_search_root / "mcp_config.json"

        # Create initial config
        initial_config = {"existing-server": {"command": "test", "args": [], "env": {}}}
        output_file.write_text(json.dumps(initial_config))

        # Save with merge
        discovery = ProjectDiscovery(search_root=temp_search_root)
        discovery.save_mcp_configs(output_path=output_file, merge=True)

        # Should preserve existing config
        content = json.loads(output_file.read_text())
        assert "existing-server" in content

        # Should also have new configs
        assert any(key.startswith("murena-") for key in content.keys())
