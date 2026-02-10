"""
Tests for the extra_source_file_extensions configuration option.

This test suite verifies that projects can be created and activated without any language servers
when extra_source_file_extensions is configured.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from serena.config.serena_config import ProjectConfig
from serena.project import Project


class TestNoLSPMode:
    """Test suite for projects without language servers using extra_source_file_extensions."""

    def setup_method(self):
        """Set up a temporary directory for each test."""
        self.temp_dir = TemporaryDirectory()
        self.project_path = Path(self.temp_dir.name) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up the temporary directory."""
        self.temp_dir.cleanup()

    def test_autogenerate_empty_directory_fails(self):
        """Test that autogenerate raises ValueError for empty directory (default behavior)."""
        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        error_message = str(exc_info.value)
        assert "No source files found" in error_message
        assert "extra_source_file_extensions" in error_message

    def test_manual_config_with_extra_extensions(self):
        """Test that a manually created config with empty languages and extra_source_file_extensions works."""
        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually with empty languages and extra extensions
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql", ".md"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Load the config
        config = ProjectConfig.load(self.project_path)

        assert config.languages == []
        assert config.extra_source_file_extensions == [".sql", ".md"]

    def test_project_load_with_empty_languages_and_extra_extensions(self):
        """Test that Project.load works with empty languages list and extra_source_file_extensions."""
        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Load the project
        project = Project.load(self.project_path, autogenerate=False)

        assert project.project_config.languages == []
        assert project.project_config.extra_source_file_extensions == [".sql"]
        assert project.language_server_manager is None

    def test_create_language_server_manager_with_empty_languages_and_extra_extensions(self):
        """Test that create_language_server_manager returns None when languages is empty but extra_source_file_extensions is set."""
        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        project = Project.load(self.project_path, autogenerate=False)

        # Create language server manager - should return None
        ls_manager = project.create_language_server_manager()

        assert ls_manager is None
        assert project.language_server_manager is None

    def test_create_language_server_manager_with_empty_languages_without_extra_extensions(self):
        """Test that create_language_server_manager raises error when languages is empty and no extra_source_file_extensions."""
        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually with empty languages and NO extra extensions
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        project = Project.load(self.project_path, autogenerate=False)

        # Try to create language server manager - should raise error
        with pytest.raises(ValueError) as exc_info:
            project.create_language_server_manager()

        error_message = str(exc_info.value)
        assert "no languages configured" in error_message
        assert "extra_source_file_extensions" in error_message

    def test_activation_message_with_empty_languages_and_extra_extensions(self):
        """Test that get_activation_message shows appropriate message for empty languages with extra extensions."""
        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql", ".md"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        project = Project.load(self.project_path, autogenerate=False)

        message = project.get_activation_message()

        assert "No language servers configured" in message
        assert "File-based tools" in message
        assert "symbolic tools" in message
        assert ".sql" in message
        assert ".md" in message

    def test_file_operations_work_without_language_servers(self):
        """Test that file-based operations work even without language servers."""
        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        project = Project.load(self.project_path, autogenerate=False)

        # Create a test file
        test_file = self.project_path / "test.sql"
        test_file.write_text("SELECT * FROM users;")

        # Test file operations - read_file should work
        content = project.read_file("test.sql")
        assert "SELECT * FROM users;" in content

        # gather_source_files() should include .sql files
        files = project.gather_source_files()
        assert "test.sql" in files

    def test_project_with_sql_files_only(self):
        """Test the original use case: a project with only SQL files."""
        # Create SQL files
        (self.project_path / "schema.sql").write_text("CREATE TABLE users (id INT PRIMARY KEY);")
        (self.project_path / "queries.sql").write_text("SELECT * FROM users;")

        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml manually
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Load and verify file operations work
        project = Project.load(self.project_path, autogenerate=False)

        # Verify read_file works
        schema_content = project.read_file("schema.sql")
        assert "CREATE TABLE users" in schema_content

        queries_content = project.read_file("queries.sql")
        assert "SELECT * FROM users" in queries_content

        # Verify files are recognized as source files
        files = project.gather_source_files()
        assert "schema.sql" in files
        assert "queries.sql" in files

    def test_extra_extensions_with_languages(self):
        """Test that extra_source_file_extensions works alongside configured languages."""
        # Create Python and SQL files
        (self.project_path / "main.py").write_text("print('hello')")
        (self.project_path / "queries.sql").write_text("SELECT * FROM users;")

        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml with Python language + SQL extension
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": ["python"],
            "extra_source_file_extensions": [".sql"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        project = Project.load(self.project_path, autogenerate=False)

        # Both Python and SQL files should be recognized as source files
        files = project.gather_source_files()
        assert "main.py" in files
        assert "queries.sql" in files

    def test_file_filtering_with_extra_extensions(self):
        """Test that file filtering works correctly with extra_source_file_extensions."""
        # Create various files
        (self.project_path / "schema.sql").write_text("CREATE TABLE users;")
        (self.project_path / "readme.md").write_text("# README")
        (self.project_path / "data.json").write_text("{}")

        # Create .serena directory
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(parents=True, exist_ok=True)

        # Create project.yml with only .sql as extra extension
        config_path = serena_dir / "project.yml"
        config_data = {
            "project_name": "test_project",
            "languages": [],
            "extra_source_file_extensions": [".sql"],
            "encoding": "utf-8",
            "ignore_all_files_in_gitignore": True,
            "ignored_paths": [],
            "read_only": False,
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        project = Project.load(self.project_path, autogenerate=False)

        # Only .sql files should be recognized as source files
        files = project.gather_source_files()
        assert "schema.sql" in files
        assert "readme.md" not in files
        assert "data.json" not in files
