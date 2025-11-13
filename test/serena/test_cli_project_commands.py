"""Tests for CLI project commands (create, index)."""

import os
import shutil
import tempfile
import time

import pytest
from click.testing import CliRunner

from serena.cli import ProjectCommands
from serena.config.serena_config import ProjectConfig

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture
def temp_project_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_project_dir_with_python_file():
    """Create a temporary directory with a Python file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple Python file so language detection works
        py_file = os.path.join(tmpdir, "test.py")
        with open(py_file, "w") as f:
            f.write("def hello():\n    pass\n")
        yield tmpdir


@pytest.fixture
def cli_runner():
    """Create a CliRunner for testing Click commands."""
    return CliRunner()


class TestProjectCreate:
    """Tests for 'project create' command."""

    def test_create_basic_with_language(self, cli_runner, temp_project_dir):
        """Test basic project creation with explicit language."""
        result = cli_runner.invoke(ProjectCommands.create, [temp_project_dir, "--language", "python"])
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Generated project.yml" in result.output
        assert "python" in result.output.lower()

        # Verify project.yml was created
        yml_path = os.path.join(temp_project_dir, ".serena", "project.yml")
        assert os.path.exists(yml_path), f"project.yml not found at {yml_path}"

    def test_create_auto_detect_language(self, cli_runner, temp_project_dir_with_python_file):
        """Test project creation with auto-detected language."""
        result = cli_runner.invoke(ProjectCommands.create, [temp_project_dir_with_python_file])
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Generated project.yml" in result.output
        assert "python" in result.output.lower()

        # Verify project.yml was created
        yml_path = os.path.join(temp_project_dir_with_python_file, ".serena", "project.yml")
        assert os.path.exists(yml_path)

    def test_create_with_name(self, cli_runner, temp_project_dir):
        """Test project creation with custom name and explicit language."""
        result = cli_runner.invoke(ProjectCommands.create, [temp_project_dir, "--name", "my-custom-project", "--language", "python"])
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Generated project.yml" in result.output

        # Verify project.yml was created
        yml_path = os.path.join(temp_project_dir, ".serena", "project.yml")
        assert os.path.exists(yml_path)

    def test_create_with_language(self, cli_runner, temp_project_dir):
        """Test project creation with specified language."""
        result = cli_runner.invoke(ProjectCommands.create, [temp_project_dir, "--language", "python"])
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Generated project.yml" in result.output
        assert "python" in result.output.lower()

    def test_create_with_multiple_languages(self, cli_runner, temp_project_dir):
        """Test project creation with multiple languages."""
        result = cli_runner.invoke(
            ProjectCommands.create,
            [temp_project_dir, "--language", "python", "--language", "typescript"],
        )
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Generated project.yml" in result.output

    def test_create_with_invalid_language(self, cli_runner, temp_project_dir):
        """Test project creation with invalid language raises error."""
        result = cli_runner.invoke(
            ProjectCommands.create,
            [temp_project_dir, "--language", "invalid-lang"],
        )
        assert result.exit_code != 0, "Should fail with invalid language"
        assert "Unknown language" in result.output or "invalid-lang" in result.output

    def test_create_already_exists(self, cli_runner, temp_project_dir):
        """Test that creating a project twice fails gracefully."""
        # Create once with explicit language
        result1 = cli_runner.invoke(ProjectCommands.create, [temp_project_dir, "--language", "python"])
        assert result1.exit_code == 0

        # Try to create again - should fail gracefully
        result2 = cli_runner.invoke(ProjectCommands.create, [temp_project_dir, "--language", "python"])
        assert result2.exit_code != 0, "Should fail when project.yml already exists"
        assert "already exists" in result2.output.lower()
        assert "Error:" in result2.output  # Should be user-friendly error

    def test_create_with_index_flag(self, cli_runner, temp_project_dir_with_python_file):
        """Test project creation with --index flag performs indexing."""
        result = cli_runner.invoke(
            ProjectCommands.create,
            [temp_project_dir_with_python_file, "--language", "python", "--index", "--log-level", "ERROR", "--timeout", "5"],
        )
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Generated project.yml" in result.output
        assert "Indexing project" in result.output

        # Verify project.yml was created
        yml_path = os.path.join(temp_project_dir_with_python_file, ".serena", "project.yml")
        assert os.path.exists(yml_path)

        # Verify cache directory was created (proof of indexing)
        cache_dir = os.path.join(temp_project_dir_with_python_file, ".serena", "cache")
        assert os.path.exists(cache_dir), "Cache directory should exist after indexing"

    def test_create_without_index_flag(self, cli_runner, temp_project_dir):
        """Test that project creation without --index does NOT perform indexing."""
        result = cli_runner.invoke(ProjectCommands.create, [temp_project_dir, "--language", "python"])
        assert result.exit_code == 0
        assert "Generated project.yml" in result.output
        assert "Indexing" not in result.output

        # Verify cache directory was NOT created
        cache_dir = os.path.join(temp_project_dir, ".serena", "cache")
        assert not os.path.exists(cache_dir), "Cache directory should not exist without --index"


class TestProjectIndex:
    """Tests for 'project index' command."""

    def test_index_auto_creates_project_with_files(self, cli_runner, temp_project_dir_with_python_file):
        """Test that index command auto-creates project.yml if it doesn't exist (with source files)."""
        result = cli_runner.invoke(ProjectCommands.index, [temp_project_dir_with_python_file, "--log-level", "ERROR", "--timeout", "5"])
        # Should succeed and perform indexing
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "Auto-creating" in result.output or "Indexing" in result.output

        # Verify project.yml was auto-created
        yml_path = os.path.join(temp_project_dir_with_python_file, ".serena", "project.yml")
        assert os.path.exists(yml_path), "project.yml should be auto-created"

    def test_index_with_explicit_language(self, cli_runner, temp_project_dir):
        """Test index with explicit --language for empty directory."""
        result = cli_runner.invoke(
            ProjectCommands.index,
            [temp_project_dir, "--language", "python", "--log-level", "ERROR", "--timeout", "5"],
        )
        # Should succeed even without source files if language is explicit
        assert result.exit_code == 0, f"Command failed: {result.output}"

        yml_path = os.path.join(temp_project_dir, ".serena", "project.yml")
        assert os.path.exists(yml_path)

    def test_index_with_language_auto_creates(self, cli_runner, temp_project_dir):
        """Test index with --language option for auto-creation."""
        result = cli_runner.invoke(
            ProjectCommands.index,
            [temp_project_dir, "--language", "python", "--log-level", "ERROR"],
        )
        assert result.exit_code == 0 or "Indexing" in result.output

        yml_path = os.path.join(temp_project_dir, ".serena", "project.yml")
        assert os.path.exists(yml_path)

    def test_index_is_equivalent_to_create_with_index(self, cli_runner, temp_project_dir_with_python_file):
        """Test that 'index' behaves like 'create --index' for new projects."""
        # Use manual temp directory creation with Windows-safe cleanup
        # to avoid PermissionError on Windows CI when language servers hold file locks
        dir1 = tempfile.mkdtemp()
        dir2 = tempfile.mkdtemp()

        try:
            # Setup both directories with same file
            for d in [dir1, dir2]:
                with open(os.path.join(d, "test.py"), "w") as f:
                    f.write("def hello():\n    pass\n")

            # Run 'create --index' on dir1
            result1 = cli_runner.invoke(
                ProjectCommands.create, [dir1, "--language", "python", "--index", "--log-level", "ERROR", "--timeout", "5"]
            )

            # Run 'index' on dir2
            result2 = cli_runner.invoke(ProjectCommands.index, [dir2, "--language", "python", "--log-level", "ERROR", "--timeout", "5"])

            # Both should succeed
            assert result1.exit_code == 0, f"create --index failed: {result1.output}"
            assert result2.exit_code == 0, f"index failed: {result2.output}"

            # Both should create project.yml
            assert os.path.exists(os.path.join(dir1, ".serena", "project.yml"))
            assert os.path.exists(os.path.join(dir2, ".serena", "project.yml"))

            # Both should create cache (proof of indexing)
            assert os.path.exists(os.path.join(dir1, ".serena", "cache"))
            assert os.path.exists(os.path.join(dir2, ".serena", "cache"))
        finally:
            # Windows-safe cleanup: wait for file handles to be released
            if os.name == "nt":
                time.sleep(0.2)
            # Use ignore_errors to handle lingering file locks on Windows
            shutil.rmtree(dir1, ignore_errors=True)
            shutil.rmtree(dir2, ignore_errors=True)


class TestProjectCreateHelper:
    """Tests for _create_project helper method."""

    def test_create_project_helper_returns_config(self, temp_project_dir):
        """Test that _create_project returns a ProjectConfig with explicit language."""
        config = ProjectCommands._create_project(temp_project_dir, "test-project", ("python",))
        assert isinstance(config, ProjectConfig)
        assert config.project_name == "test-project"

    def test_create_project_helper_with_auto_detect(self, temp_project_dir_with_python_file):
        """Test _create_project with auto-detected language."""
        config = ProjectCommands._create_project(temp_project_dir_with_python_file, "my-project", ())
        assert isinstance(config, ProjectConfig)
        assert config.project_name == "my-project"
        assert len(config.languages) >= 1

    def test_create_project_helper_with_languages(self, temp_project_dir):
        """Test _create_project with language specification."""
        config = ProjectCommands._create_project(temp_project_dir, None, ("python", "typescript"))
        assert isinstance(config, ProjectConfig)
        assert len(config.languages) >= 1

    def test_create_project_helper_file_exists_error(self, temp_project_dir):
        """Test _create_project raises error if project.yml exists."""
        # Create project first with explicit language
        ProjectCommands._create_project(temp_project_dir, None, ("python",))

        # Try to create again - should raise FileExistsError
        with pytest.raises(FileExistsError):
            ProjectCommands._create_project(temp_project_dir, None, ("python",))


if __name__ == "__main__":
    # For manual testing, you can run this file directly:
    # uv run pytest test/serena/test_cli_project_commands.py -v
    pytest.main([__file__, "-v"])
