import shutil
import tempfile
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from serena.constants import PROJECT_TEMPLATE_FILE
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


class TestProjectConfig:
    def test_template_is_complete(self):
        _, is_complete = ProjectConfig._load_yaml(PROJECT_TEMPLATE_FILE)
        assert is_complete, "Project template YAML is incomplete; all fields must be present (with descriptions)."


class TestProjectConfigHoverBudget:
    """Test class for include_info_hover_budget_seconds validation in ProjectConfig."""

    def _base_project_dict(self, **overrides):
        data = {
            "project_name": "test_project",
            "languages": ["python"],
            "ignored_paths": [],
            "excluded_tools": [],
            "included_optional_tools": [],
            "read_only": False,
            "ignore_all_files_in_gitignore": True,
            "initial_prompt": "",
            "encoding": "utf-8",
            "include_info_hover_budget_seconds": None,
        }
        data.update(overrides)
        return data

    def test_from_dict_accepts_null_budget(self):
        """Test that _from_dict accepts null hover budget (for inheritance)."""
        data = self._base_project_dict()
        config = ProjectConfig._from_dict(data)
        assert config.include_info_hover_budget_seconds is None

    def test_from_dict_accepts_positive_budget(self):
        """Test that _from_dict accepts positive hover budget."""
        data = self._base_project_dict(include_info_hover_budget_seconds=10.5)
        config = ProjectConfig._from_dict(data)
        assert config.include_info_hover_budget_seconds == 10.5

    def test_from_dict_accepts_zero_budget(self):
        """Test that _from_dict accepts zero hover budget (disabled)."""
        data = self._base_project_dict(include_info_hover_budget_seconds=0)
        config = ProjectConfig._from_dict(data)
        assert config.include_info_hover_budget_seconds == 0.0

    def test_from_dict_rejects_negative_budget(self):
        """Test that _from_dict raises ValueError for negative hover budget."""
        data = self._base_project_dict(include_info_hover_budget_seconds=-1.0)
        with pytest.raises(ValueError) as exc_info:
            ProjectConfig._from_dict(data)
        assert "cannot be negative" in str(exc_info.value)

    def test_apply_defaults_preserves_null(self):
        """Test that _apply_defaults_to_dict preserves None for hover budget."""
        data = {"project_name": "test", "languages": ["python"]}
        result = ProjectConfig._apply_defaults_to_dict(data)
        assert result["include_info_hover_budget_seconds"] is None

    def test_apply_defaults_preserves_explicit_value(self):
        """Test that _apply_defaults_to_dict preserves explicit hover budget value."""
        data = {
            "project_name": "test",
            "languages": ["python"],
            "include_info_hover_budget_seconds": 15.0,
        }
        result = ProjectConfig._apply_defaults_to_dict(data)
        assert result["include_info_hover_budget_seconds"] == 15.0
