import contextlib
import os
import platform
import shutil
import tempfile
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language


def _create_project(
    project_root: str,
    project_ignored_paths: list[str] | None = None,
) -> Project:
    """Helper to create a minimal Project with the given root."""
    config = ProjectConfig(
        project_name="test_project",
        languages=[Language.PYTHON],
        ignored_paths=project_ignored_paths or [],
        ignore_all_files_in_gitignore=False,
    )
    serena_config = SerenaConfig(
        gui_log_window=False, web_dashboard=False
    ).with_headless_mode_overrides()
    return Project(
        project_root=project_root,
        project_config=config,
        serena_config=serena_config,
    )


class TestIsPathInProject:
    """Tests for Project.is_path_in_project."""

    def setup_method(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)
        # Create a subdirectory and file
        os.makedirs(self.project_path / "subdir", exist_ok=True)
        (self.project_path / "main.py").write_text("print('hello')")
        (self.project_path / "subdir" / "helper.py").write_text("def helper(): pass")

        # Store project_root in both separator styles
        self.project_root_backslash = str(self.project_path)  # native Windows backslashes
        self.project_root_forward = str(self.project_path).replace(os.sep, "/")

    def teardown_method(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_absolute_path_equal_to_project_root(self) -> None:
        """The project root itself should always be considered inside the project."""
        project = _create_project(self.project_root_backslash)
        assert project.is_path_in_project(self.project_root_backslash)

    def test_relative_path(self) -> None:
        """A relative path should be considered inside the project."""
        project = _create_project(self.project_root_backslash)
        assert project.is_path_in_project("main.py")
        assert project.is_path_in_project("subdir/helper.py")

    def test_subdirectory_absolute_path(self) -> None:
        """An absolute path to a subdirectory should be inside the project."""
        project = _create_project(self.project_root_backslash)
        subdir_path = str(self.project_path / "subdir")
        assert project.is_path_in_project(subdir_path)

    def test_sibling_path_outside_project(self) -> None:
        """A sibling directory should be outside the project."""
        project = _create_project(self.project_root_backslash)
        outside_path = str(self.project_path.parent / "sibling")
        os.makedirs(outside_path, exist_ok=True)
        assert not project.is_path_in_project(outside_path)

    def test_path_with_dot_dot_escape(self) -> None:
        """A path with '..' trying to escape the project root should be rejected."""
        project = _create_project(self.project_root_backslash)
        escape_path = os.path.join(self.test_dir, "..", "..", "etc")
        assert not project.is_path_in_project(escape_path)

    def test_non_existent_path_inside_project(self) -> None:
        """A non-existent path that would be inside the project should be accepted."""
        project = _create_project(self.project_root_backslash)
        nonexistent = str(self.project_path / "nonexistent" / "file.txt")
        assert project.is_path_in_project(nonexistent)

    def test_forward_slash_project_root_with_backslash_absolute_path(self) -> None:
        """Windows: forward-slash project_root must not break is_path_in_project.

        When project_root is stored with forward slashes (common in Git Bash/MSYS
        environments on Windows) and os.path.commonpath returns backslashes,
        the equality check must handle the separator mismatch.
        """
        project = _create_project(self.project_root_forward)
        # Pass a native backslash path (like Windows native tools produce)
        path = str(self.project_path / "main.py")
        assert project.is_path_in_project(
            path
        ), f"Forward-slash project_root should match backslash paths: {self.project_root_forward} vs {path}"
        # Also check subdirectory
        subdir_path = str(self.project_path / "subdir")
        assert project.is_path_in_project(subdir_path)
        # Check the project root itself
        assert project.is_path_in_project(self.test_dir)

    def test_forward_slash_project_root_rejects_outside_paths(self) -> None:
        """Forward-slash project_root must still reject paths outside the project."""
        project = _create_project(self.project_root_forward)
        outside_path = str(self.project_path.parent / "sibling")
        os.makedirs(outside_path, exist_ok=True)
        assert not project.is_path_in_project(outside_path)
        # Path with .. should also be rejected
        escape_path = os.path.join(self.test_dir, "..", "..", "etc")
        assert not project.is_path_in_project(escape_path)

    def test_forward_slash_project_root_with_forward_slash_path(self) -> None:
        """Forward-slash project_root with a forward-slash path should work."""
        project = _create_project(self.project_root_forward)
        fwd_path = str(self.project_path / "main.py").replace(os.sep, "/")
        assert project.is_path_in_project(fwd_path)

    def test_project_root_itself_not_ignored_when_empty_string(self) -> None:
        """The project root (empty string or '.') should never be ignored."""
        project = _create_project(self.project_root_backslash)
        assert not project.is_ignored_path(".")
        assert not project.is_ignored_path("")

    def test_different_drive_path_on_windows(self) -> None:
        """A path on a different drive should be outside the project."""
        project = _create_project(self.project_root_backslash)
        if os.name == "nt":
            diff_drive = "Z:\\nonexistent\\path"
            assert not project.is_path_in_project(diff_drive)
        else:
            # On Linux, test with a path anchored to a different root
            assert not project.is_path_in_project("/nonexistent")


class TestValidateRelativePath:
    """Tests for Project.validate_relative_path."""

    def setup_method(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)
        (self.project_path / "main.py").write_text("print('hello')")
        self.project = _create_project(str(self.project_path))
        # Forward-slash project root version
        self.project_fwd = _create_project(str(self.project_path).replace(os.sep, "/"))

    def teardown_method(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_validate_nonexistent_relative_path(self) -> None:
        """A non-existent relative path should be accepted (allows creating new files)."""
        # Should not raise
        self.project.validate_relative_path("new_file.py")

    def test_validate_relative_path_outside_project(self) -> None:
        """A relative path pointing outside the project should raise."""
        with pytest.raises(ValueError, match="outside of the repository root"):
            self.project.validate_relative_path("../outside.py")

    def test_validate_relative_path_outside_project_forward_root(self) -> None:
        """Forward-slash project_root must also reject paths outside the project."""
        with pytest.raises(ValueError, match="outside of the repository root"):
            self.project_fwd.validate_relative_path("../outside.py")


class TestForwardSlashProjectRootRegression:
    """Regression: Project is_ignored_path with forward-slash project_root.

    This mimics the real-world scenario reported in the bug:
    - project_root comes from external config (e.g. RegisteredProject)
      and may be stored with forward slashes (Git Bash / MSYS on Windows)
    - The path to check is an absolute native Windows path with backslashes
    """

    def setup_method(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)
        (self.project_path / "main.py").write_text("print('hello')")
        os.makedirs(self.project_path / ".git", exist_ok=True)
        (self.project_path / ".git" / "config").write_text("[core]\n")

    def teardown_method(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_is_ignored_path_with_forward_slash_project_root(self) -> None:
        """is_ignored_path must handle forward-slash project_root correctly."""
        project_root_forward = str(self.project_path).replace(os.sep, "/")
        project = _create_project(project_root_forward)
        # Check an absolute path within the project
        abs_path = str(self.project_path / "main.py")
        # main.py is a Python source file, should not be ignored by default
        assert not project.is_ignored_path(abs_path)

    def test_is_ignored_path_outside_project(self) -> None:
        """is_ignored_path must return True for paths outside the project."""
        project_root_forward = str(self.project_path).replace(os.sep, "/")
        project = _create_project(project_root_forward)
        # Check a path outside the project
        outside_path = str(self.project_path.parent / "outside.py")
        assert project.is_ignored_path(outside_path)
