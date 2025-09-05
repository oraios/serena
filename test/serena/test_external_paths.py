"""
Tests for external path access functionality.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from serena.agent import SerenaAgent
from serena.config.serena_config import SERENA_MANAGED_DIR_NAME, ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language


class TestExternalPaths:
    """Test external path access functionality."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as project_dir:
            with tempfile.TemporaryDirectory() as external_dir1:
                with tempfile.TemporaryDirectory() as external_dir2:
                    # Create some test files
                    project_path = Path(project_dir)
                    ext1_path = Path(external_dir1)
                    ext2_path = Path(external_dir2)

                    # Create project structure
                    (project_path / "main.py").write_text("# Main project file")
                    (project_path / SERENA_MANAGED_DIR_NAME).mkdir(parents=True)

                    # Create external files
                    (ext1_path / "shared.py").write_text("# Shared library")
                    (ext2_path / "config.yaml").write_text("key: value")

                    yield {"project": project_path, "external1": ext1_path, "external2": ext2_path}

    def test_project_config_with_external_paths(self, temp_dirs):
        """Test that ProjectConfig correctly loads allowed_external_paths."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create project.yml with external paths
        config_data = {
            "project_name": "test_project",
            "language": "python",
            "allowed_external_paths": [str(ext1), "../external2"],  # Absolute path  # Relative path
        }

        config_path = project_path / SERENA_MANAGED_DIR_NAME / "project.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Load the config
        config = ProjectConfig.load(project_path)

        assert config.project_name == "test_project"
        assert config.language == Language.PYTHON
        assert len(config.allowed_external_paths) == 2
        assert str(ext1) in config.allowed_external_paths
        assert "../external2" in config.allowed_external_paths

    def test_path_is_in_allowed_external_absolute(self, temp_dirs):
        """Test path_is_in_allowed_external with absolute paths."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create project config with external path
        project_config = ProjectConfig(project_name="test", language=Language.PYTHON, allowed_external_paths=[str(ext1)])

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Create agent
        agent = SerenaAgent(project="test", serena_config=serena_config)

        # Test paths
        assert agent.path_is_in_allowed_external(str(ext1))
        assert agent.path_is_in_allowed_external(str(ext1 / "shared.py"))
        assert agent.path_is_in_allowed_external(ext1 / "subdir" / "file.py")

        # Path not in allowed external
        assert not agent.path_is_in_allowed_external("/tmp/other/path")
        assert not agent.path_is_in_allowed_external(project_path / "main.py")

    def test_path_is_in_allowed_external_relative(self, temp_dirs):
        """Test path_is_in_allowed_external with relative paths."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Calculate relative path from project to external
        rel_path = os.path.relpath(ext1, project_path)

        # Create project config with relative external path
        project_config = ProjectConfig(project_name="test", language=Language.PYTHON, allowed_external_paths=[rel_path])

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Create agent
        agent = SerenaAgent(project="test", serena_config=serena_config)

        # Test that external path is allowed
        assert agent.path_is_in_allowed_external(str(ext1))
        assert agent.path_is_in_allowed_external(str(ext1 / "shared.py"))

    def test_validate_relative_path_with_external(self, temp_dirs):
        """Test validate_relative_path allows external paths."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create project config with external path
        project_config = ProjectConfig(project_name="test", language=Language.PYTHON, allowed_external_paths=[str(ext1)])

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Create agent
        agent = SerenaAgent(project="test", serena_config=serena_config)

        # Should not raise for allowed external path
        agent.validate_relative_path(str(ext1 / "shared.py"))

        # Should raise for non-allowed external path
        with pytest.raises(ValueError, match="outside of the repository root"):
            agent.validate_relative_path("/tmp/not/allowed/path.py")

    def test_symlink_handling(self, temp_dirs):
        """Test that symlinks are properly resolved."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create a symlink
        symlink_path = project_path / "symlink_to_external"
        symlink_path.symlink_to(ext1)

        # Create project config with the symlink path
        project_config = ProjectConfig(project_name="test", language=Language.PYTHON, allowed_external_paths=[str(symlink_path)])

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Create agent
        agent = SerenaAgent(project="test", serena_config=serena_config)

        # The symlink should resolve to the actual external directory
        assert agent.path_is_in_allowed_external(str(ext1))
        assert agent.path_is_in_allowed_external(str(ext1 / "shared.py"))

    def test_path_traversal_prevention(self, temp_dirs):
        """Test that path traversal attacks are prevented."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create project config with a specific subdirectory
        allowed_subdir = ext1 / "allowed"
        allowed_subdir.mkdir()

        project_config = ProjectConfig(project_name="test", language=Language.PYTHON, allowed_external_paths=[str(allowed_subdir)])

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Create agent
        agent = SerenaAgent(project="test", serena_config=serena_config)

        # Should allow the specific subdirectory
        assert agent.path_is_in_allowed_external(str(allowed_subdir))

        # Should not allow parent directory via traversal
        traversal_path = str(allowed_subdir / ".." / "shared.py")
        assert not agent.path_is_in_allowed_external(traversal_path)

    def test_startup_warnings(self, temp_dirs, caplog):
        """Test that warnings are logged when external paths are configured."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create project config with external paths
        project_config = ProjectConfig(
            project_name="test_warnings",
            language=Language.PYTHON,
            allowed_external_paths=[str(ext1), "../relative/path", "/invalid/\\x00/path"],  # Invalid path to test error handling
        )

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Set log level to capture warnings
        import logging

        caplog.set_level(logging.WARNING)

        # Create agent - this should trigger warnings
        SerenaAgent(project="test_warnings", serena_config=serena_config)

        # Check that warnings were logged
        warning_records = [record for record in caplog.records if record.levelname == "WARNING"]
        warning_messages = [record.message for record in warning_records]

        # Should have main warning + one for each path
        assert any("SECURITY: Project test_warnings has allowed external paths:" in msg for msg in warning_messages)
        assert any(str(ext1) in msg for msg in warning_messages)
        assert any("../relative/path" in msg for msg in warning_messages)

        # For the invalid path, it might log the path itself or an error
        # Check if either the path with null byte or an error message is present
        has_invalid_path = any("/invalid/" in msg and "/path" in msg for msg in warning_messages)
        has_error = any("ERROR:" in msg for msg in warning_messages)
        assert has_invalid_path or has_error, f"Expected either invalid path or ERROR in warnings, got: {warning_messages}"

    def test_empty_allowed_paths_default(self, temp_dirs):
        """Test that allowed_external_paths defaults to empty list."""
        project_path = temp_dirs["project"]

        # Create minimal project.yml
        config_data = {
            "project_name": "test_project",
            "language": "python",
            # No allowed_external_paths specified
        }

        config_path = project_path / SERENA_MANAGED_DIR_NAME / "project.yml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Load the config
        config = ProjectConfig.load(project_path)

        assert config.allowed_external_paths == []

    def test_gitignore_patterns_apply_to_external(self, temp_dirs):
        """Test that common gitignore patterns apply to external paths."""
        project_path = temp_dirs["project"]
        ext1 = temp_dirs["external1"]

        # Create a .gitignore file in the project with patterns
        gitignore_content = """
*.log
__pycache__/
*.pyc
*.pyo
*.pyd
"""
        (project_path / ".gitignore").write_text(gitignore_content)

        # Create files that match common gitignore patterns
        (ext1 / "test.log").write_text("log content")
        (ext1 / "__pycache__").mkdir()
        (ext1 / "__pycache__" / "module.pyc").write_text("bytecode")

        # Create project config with external path
        project_config = ProjectConfig(
            project_name="test", language=Language.PYTHON, allowed_external_paths=[str(ext1)], ignore_all_files_in_gitignore=True
        )

        project = Project(project_root=str(project_path), project_config=project_config)

        # Create a mock SerenaConfig
        serena_config = SerenaConfig(gui_log_window_enabled=False, web_dashboard=False)
        serena_config.projects = [RegisteredProject.from_project_instance(project)]

        # Create agent
        agent = SerenaAgent(project="test", serena_config=serena_config)

        # The paths are in allowed external
        assert agent.path_is_in_allowed_external(str(ext1 / "test.log"))
        assert agent.path_is_in_allowed_external(str(ext1 / "__pycache__" / "module.pyc"))

        # But validation should fail due to gitignore patterns
        with pytest.raises(ValueError, match="gitignored"):
            agent.validate_relative_path(str(ext1 / "test.log"))

        with pytest.raises(ValueError, match="gitignored"):
            agent.validate_relative_path(str(ext1 / "__pycache__" / "module.pyc"))
