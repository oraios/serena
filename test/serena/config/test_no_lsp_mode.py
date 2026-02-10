"""
Tests for the allow_no_language_servers configuration option.

This test suite verifies that projects can be created and activated without any language servers
when the allow_no_language_servers option is enabled.
"""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from serena.config.serena_config import ProjectConfig, SerenaConfig
from serena.project import Project


class TestNoLSPMode:
    """Test suite for projects without language servers."""

    def setup_method(self):
        """Set up a temporary directory for each test."""
        self.temp_dir = TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up the temporary directory."""
        self.temp_dir.cleanup()

    def test_autogenerate_empty_directory_without_option(self):
        """Test that autogenerate raises ValueError for empty directory when option is disabled."""
        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.autogenerate(self.project_path, save_to_disk=False, allow_no_language_servers=False)

        error_message = str(exc_info.value)
        assert "No source files found" in error_message
        assert "allow_no_language_servers" in error_message

    def test_autogenerate_empty_directory_with_option(self):
        """Test that autogenerate succeeds for empty directory when option is enabled."""
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=False, allow_no_language_servers=True)

        assert config.project_name == self.project_path.name
        assert config.languages == []

    def test_autogenerate_saves_empty_languages_to_disk(self):
        """Test that autogenerate can save empty languages list to disk."""
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)

        # Verify the configuration file was created
        config_path = self.project_path / ".serena" / "project.yml"
        assert config_path.exists()

        # Verify the content
        assert config.languages == []

        # Reload and verify
        reloaded_config = ProjectConfig.load(self.project_path)
        assert reloaded_config.languages == []

    def test_project_load_with_empty_languages(self):
        """Test that Project.load works with empty languages list."""
        # Create a project with empty languages
        ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)

        # Load the project
        project = Project.load(self.project_path, autogenerate=False)

        assert project.project_config.languages == []
        assert project.language_server_manager is None

    def test_create_language_server_manager_with_empty_languages_and_option(self):
        """Test that create_language_server_manager returns None when languages is empty and option is enabled."""
        # Create a project with empty languages
        ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)
        project = Project.load(self.project_path, autogenerate=False)

        # Create language server manager with option enabled
        ls_manager = project.create_language_server_manager(allow_no_language_servers=True)

        assert ls_manager is None
        assert project.language_server_manager is None

    def test_create_language_server_manager_with_empty_languages_without_option(self):
        """Test that create_language_server_manager raises error when languages is empty and option is disabled."""
        # Create a project with empty languages
        ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)
        project = Project.load(self.project_path, autogenerate=False)

        # Try to create language server manager without option - should raise error
        with pytest.raises(ValueError) as exc_info:
            project.create_language_server_manager(allow_no_language_servers=False)

        error_message = str(exc_info.value)
        assert "no languages configured" in error_message
        assert "allow_no_language_servers" in error_message

    def test_activation_message_with_empty_languages(self):
        """Test that get_activation_message shows appropriate message for empty languages."""
        # Create a project with empty languages
        ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)
        project = Project.load(self.project_path, autogenerate=False)

        message = project.get_activation_message()

        assert "No language servers configured" in message
        assert "File-based tools" in message
        assert "symbolic tools" in message

    def test_file_operations_work_without_language_servers(self):
        """Test that file-based operations work even without language servers."""
        # Create a project with empty languages
        ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)
        project = Project.load(self.project_path, autogenerate=False)

        # Create a test file
        test_file = self.project_path / "test.sql"
        test_file.write_text("SELECT * FROM users;")

        # Test file operations - read_file should work
        content = project.read_file("test.sql")
        assert "SELECT * FROM users;" in content

        # Note: gather_source_files() returns empty list when no languages are configured
        # because all files are considered non-source files. This is expected behavior.
        files = project.gather_source_files()
        assert files == []

    def test_serena_config_with_allow_no_language_servers(self):
        """Test that SerenaConfig properly handles the allow_no_language_servers option."""
        config = SerenaConfig(gui_log_window=False, web_dashboard=False, log_level=logging.ERROR, allow_no_language_servers=True)

        assert config.allow_no_language_servers is True

    def test_project_with_sql_files_only(self):
        """Test the original use case: a project with only SQL files."""
        # Create SQL files
        (self.project_path / "schema.sql").write_text("CREATE TABLE users (id INT PRIMARY KEY);")
        (self.project_path / "queries.sql").write_text("SELECT * FROM users;")

        # Autogenerate with option enabled
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=True, allow_no_language_servers=True)

        assert config.languages == []

        # Load and verify file operations work
        project = Project.load(self.project_path, autogenerate=False)

        # Verify read_file works
        schema_content = project.read_file("schema.sql")
        assert "CREATE TABLE users" in schema_content

        queries_content = project.read_file("queries.sql")
        assert "SELECT * FROM users" in queries_content
