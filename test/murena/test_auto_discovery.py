"""Tests for auto-discovery of Murena projects."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from murena.multi_project.auto_discovery import AutoDiscoveryManager, QuickDiscoveryMode


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with test projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create test projects
        projects = [
            ("project1", ["python", "typescript"]),
            ("project2", ["python"]),
            ("nested/project3", ["go"]),
        ]

        for project_path, languages in projects:
            project_dir = workspace / project_path
            project_dir.mkdir(parents=True, exist_ok=True)

            # Create .murena/project.yml marker file
            murena_dir = project_dir / ".murena"
            murena_dir.mkdir(exist_ok=True)
            project_file = murena_dir / "project.yml"
            project_file.write_text(f"name: {Path(project_path).name}\nlanguages:\n")

        yield workspace


class TestAutoDiscoveryManager:
    """Tests for AutoDiscoveryManager class."""

    def test_initialization(self, temp_workspace):
        """Test AutoDiscoveryManager initialization."""
        manager = AutoDiscoveryManager(workspace_root=temp_workspace)
        assert manager.workspace_root == temp_workspace
        assert manager.discovery is not None

    def test_discover_projects(self, temp_workspace):
        """Test project discovery."""
        manager = AutoDiscoveryManager(workspace_root=temp_workspace)
        projects = manager.discover_projects(max_depth=3)

        assert len(projects) == 3
        project_names = {p["name"] for p in projects}
        assert "project1" in project_names
        assert "project2" in project_names
        assert "project3" in project_names

    def test_discover_projects_depth_limit(self, temp_workspace):
        """Test discovery respects depth limit."""
        manager = AutoDiscoveryManager(workspace_root=temp_workspace)

        # With depth=1, should not find nested/project3
        projects_depth1 = manager.discover_projects(max_depth=1)
        assert len(projects_depth1) == 2

        # With depth=2, should find nested/project3
        projects_depth2 = manager.discover_projects(max_depth=2)
        assert len(projects_depth2) == 3

    def test_discover_projects_excludes_special_dirs(self):
        """Test discovery excludes node_modules, venv, etc."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create project in venv (should be skipped)
            venv_dir = workspace / "venv"
            venv_dir.mkdir()
            project_in_venv = venv_dir / "project"
            project_in_venv.mkdir()
            (project_in_venv / ".murena").mkdir()
            (project_in_venv / ".murena" / "project.yml").write_text("name: project")

            # Create normal project
            normal_project = workspace / "project"
            normal_project.mkdir()
            (normal_project / ".murena").mkdir()
            (normal_project / ".murena" / "project.yml").write_text("name: project")

            manager = AutoDiscoveryManager(workspace_root=workspace)
            projects = manager.discover_projects(max_depth=2)

            # Should only find normal_project
            assert len(projects) == 1
            assert projects[0]["name"] == "project"

    def test_get_mcp_config_path(self):
        """Test MCP config path generation."""
        manager = AutoDiscoveryManager()
        config_path = manager.get_mcp_config_path()

        assert config_path.parent.name == ".claude"
        assert config_path.name == "mcp_servers_murena.json"
        assert config_path.parent.exists()

    def test_load_mcp_config_new(self):
        """Test loading MCP config when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            manager = AutoDiscoveryManager()
            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                config = manager.load_mcp_config()
                assert config == {}

    def test_load_mcp_config_existing(self):
        """Test loading existing MCP config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            test_config = {
                "murena-project1": {
                    "command": "uvx",
                    "args": ["murena", "start-mcp-server"],
                }
            }

            config_path.write_text(json.dumps(test_config))

            manager = AutoDiscoveryManager()
            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                config = manager.load_mcp_config()
                assert config == test_config

    def test_save_mcp_config(self):
        """Test saving MCP config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            test_config = {
                "murena-project1": {
                    "command": "uvx",
                    "args": ["murena", "start-mcp-server"],
                }
            }

            manager = AutoDiscoveryManager()
            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                result = manager.save_mcp_config(test_config)
                assert result is True
                assert config_path.exists()

                saved_config = json.loads(config_path.read_text())
                assert saved_config == test_config

    def test_register_project(self, temp_workspace):
        """Test registering a single project."""
        project1 = temp_workspace / "project1"
        project1_path = str(project1)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            manager = AutoDiscoveryManager()
            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                result = manager.register_project("project1", project1_path)
                assert result is True

                config = manager.load_mcp_config()
                assert "murena-project1" in config
                assert config["murena-project1"]["args"][3] == project1_path

    def test_register_project_already_exists(self, temp_workspace):
        """Test registering a project that already exists."""
        project1 = temp_workspace / "project1"
        project1_path = str(project1)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            manager = AutoDiscoveryManager()
            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                # Register first time
                result1 = manager.register_project("project1", project1_path)
                assert result1 is True

                # Register again (should be idempotent)
                result2 = manager.register_project("project1", project1_path)
                assert result2 is True

                config = manager.load_mcp_config()
                assert "murena-project1" in config

    def test_auto_register_projects(self, temp_workspace):
        """Test batch registration of projects."""
        manager = AutoDiscoveryManager(workspace_root=temp_workspace)
        projects = manager.discover_projects(max_depth=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                results = manager.auto_register_projects(projects)

                assert results["total"] == 3
                assert results["registered"] == 3
                assert results["failed"] == 0

                config = manager.load_mcp_config()
                assert "murena-project1" in config
                assert "murena-project2" in config
                assert "murena-project3" in config

    def test_run_discovery_pipeline(self, temp_workspace):
        """Test complete discovery and registration pipeline."""
        manager = AutoDiscoveryManager(workspace_root=temp_workspace)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            with patch.object(manager, "get_mcp_config_path", return_value=config_path):
                result = manager.run_discovery(workspace_root=temp_workspace, max_depth=3)

                assert result["success"] is True
                assert result["projects_found"] == 3
                assert result["registered"] == 3
                assert result["failed"] == 0

    def test_run_discovery_no_projects(self):
        """Test discovery pipeline with no projects found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            manager = AutoDiscoveryManager(workspace_root=workspace)

            result = manager.run_discovery(workspace_root=workspace)

            assert result["success"] is True
            assert result["projects_found"] == 0
            assert result["projects"] == []


class TestQuickDiscoveryMode:
    """Tests for QuickDiscoveryMode class."""

    def test_quick_scan_success(self, temp_workspace):
        """Test quick scan on startup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            # Patch both the workspace and the config path
            with patch.object(AutoDiscoveryManager, "get_mcp_config_path", return_value=config_path):
                result = QuickDiscoveryMode.quick_scan(workspace_root=temp_workspace)

                assert result is True

    def test_quick_scan_no_projects(self):
        """Test quick scan with no projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_workspace = Path(tmpdir)
            result = QuickDiscoveryMode.quick_scan(workspace_root=empty_workspace)

            assert result is True  # Still succeeds even if no projects found

    def test_is_workspace_root_with_git(self):
        """Test workspace root detection with .git."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / ".git").mkdir()

            result = QuickDiscoveryMode.is_workspace_root(workspace)
            assert result is True

    def test_is_workspace_root_with_vscode(self):
        """Test workspace root detection with .vscode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / ".vscode").mkdir()

            result = QuickDiscoveryMode.is_workspace_root(workspace)
            assert result is True

    def test_is_workspace_root_with_pyproject(self):
        """Test workspace root detection with pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "pyproject.toml").write_text("")

            result = QuickDiscoveryMode.is_workspace_root(workspace)
            assert result is True

    def test_is_workspace_root_not_workspace(self):
        """Test workspace root detection for non-workspace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            result = QuickDiscoveryMode.is_workspace_root(workspace)
            assert result is False


class TestAutoDiscoveryIntegration:
    """Integration tests for auto-discovery."""

    def test_discovery_with_real_project_structure(self):
        """Test discovery with realistic project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create realistic structure
            (workspace / ".git").mkdir()  # Workspace root indicator
            (workspace / "src").mkdir()

            # Create projects
            for i in range(3):
                project_dir = workspace / f"project{i+1}"
                project_dir.mkdir()
                (project_dir / ".murena").mkdir()
                (project_dir / ".murena" / "project.yml").write_text(f"name: project{i+1}")
                (project_dir / "src").mkdir()
                (project_dir / "src" / "main.py").write_text("print('hello')")

            manager = AutoDiscoveryManager(workspace_root=workspace)
            projects = manager.discover_projects(max_depth=2)

            assert len(projects) == 3
            for project in projects:
                assert "name" in project
                assert "path" in project
                assert "marker_file" in project
                assert Path(project["marker_file"]).exists()

    def test_concurrent_discovery(self, temp_workspace):
        """Test multiple concurrent discovery operations."""
        import threading

        results = []
        errors = []

        def discover():
            try:
                manager = AutoDiscoveryManager(workspace_root=temp_workspace)
                projects = manager.discover_projects()
                results.append(len(projects))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=discover) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert all(count == 3 for count in results)
