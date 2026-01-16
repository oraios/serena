import shutil
import tempfile
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from solidlsp.ls_config import Language


class TestProjectConfigAutogenerate:
    """Test class for ProjectConfig autogeneration functionality."""

    def setup_method(self):
        """Set up test environment before each test method."""
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)

    def test_autogenerate_empty_directory(self):
        """Test that autogenerate raises ValueError with helpful message for empty directory."""
        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        error_message = str(exc_info.value)
        assert "No source files found" in error_message

    def test_autogenerate_with_python_files(self):
        """Test successful autogeneration with Python source files."""
        # Create a Python file
        python_file = self.project_path / "main.py"
        python_file.write_text("def hello():\n    print('Hello, world!')\n")

        # Run autogenerate
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        # Verify the configuration
        assert config.project_name == self.project_path.name
        assert config.languages == [Language.PYTHON]

    def test_autogenerate_with_js_files(self):
        """Test successful autogeneration with JavaScript source files."""
        # Create files for multiple languages
        (self.project_path / "small.js").write_text("console.log('JS');")

        # Run autogenerate - should pick Python as dominant
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        assert config.languages == [Language.TYPESCRIPT]

    def test_autogenerate_with_multiple_languages(self):
        """Test autogeneration picks dominant language when multiple are present."""
        # Create files for multiple languages
        (self.project_path / "main.py").write_text("print('Python')")
        (self.project_path / "util.py").write_text("def util(): pass")
        (self.project_path / "small.js").write_text("console.log('JS');")

        # Run autogenerate - should pick Python as dominant
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        assert config.languages == [Language.PYTHON]

    def test_autogenerate_saves_to_disk(self):
        """Test that autogenerate can save the configuration to disk."""
        # Create a Go file
        go_file = self.project_path / "main.go"
        go_file.write_text("package main\n\nfunc main() {}\n")

        # Run autogenerate with save_to_disk=True
        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=True)

        # Verify the configuration file was created
        config_path = self.project_path / ".serena" / "project.yml"
        assert config_path.exists()

        # Verify the content
        assert config.languages == [Language.GO]

    def test_autogenerate_nonexistent_path(self):
        """Test that autogenerate raises FileNotFoundError for non-existent path."""
        non_existent = self.project_path / "does_not_exist"

        with pytest.raises(FileNotFoundError) as exc_info:
            ProjectConfig.autogenerate(non_existent, save_to_disk=False)

        assert "Project root not found" in str(exc_info.value)

    def test_autogenerate_with_gitignored_files_only(self):
        """Test autogenerate behavior when only gitignored files exist."""
        # Create a .gitignore that ignores all Python files
        gitignore = self.project_path / ".gitignore"
        gitignore.write_text("*.py\n")

        # Create Python files that will be ignored
        (self.project_path / "ignored.py").write_text("print('ignored')")

        # Should still raise ValueError as no source files are detected
        with pytest.raises(ValueError) as exc_info:
            ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        assert "No source files found" in str(exc_info.value)

    def test_autogenerate_custom_project_name(self):
        """Test autogenerate with custom project name."""
        # Create a TypeScript file
        ts_file = self.project_path / "index.ts"
        ts_file.write_text("const greeting: string = 'Hello';\n")

        # Run autogenerate with custom name
        custom_name = "my-custom-project"
        config = ProjectConfig.autogenerate(self.project_path, project_name=custom_name, save_to_disk=False)

        assert config.project_name == custom_name
        assert config.languages == [Language.TYPESCRIPT]

    def test_auto_index_on_activate_default_false(self):
        """Test that auto_index_on_activate defaults to False."""
        # Create a Python file
        python_file = self.project_path / "main.py"
        python_file.write_text("def hello(): pass\n")

        config = ProjectConfig.autogenerate(self.project_path, save_to_disk=False)

        assert config.auto_index_on_activate is False

    def test_auto_index_on_activate_from_yaml(self):
        """Test loading auto_index_on_activate from YAML configuration."""
        # Create a Python file
        python_file = self.project_path / "main.py"
        python_file.write_text("def hello(): pass\n")

        # Create .serena directory and project.yml with auto_index_on_activate enabled
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            """project_name: test-project
languages:
  - python
auto_index_on_activate: true
"""
        )

        config = ProjectConfig.load(self.project_path)

        assert config.auto_index_on_activate is True
        assert config.project_name == "test-project"

    def test_auto_index_on_activate_missing_from_yaml(self):
        """Test that auto_index_on_activate defaults to False when not in YAML."""
        # Create a Python file
        python_file = self.project_path / "main.py"
        python_file.write_text("def hello(): pass\n")

        # Create .serena directory and project.yml without auto_index_on_activate
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir()
        project_yml = serena_dir / "project.yml"
        project_yml.write_text(
            """project_name: test-project
languages:
  - python
"""
        )

        config = ProjectConfig.load(self.project_path)

        assert config.auto_index_on_activate is False
