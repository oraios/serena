import os
import shutil
import tempfile
from pathlib import Path

from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.project import Project
from solidlsp.ls_config import Language


def _create_test_project(
    project_root: Path,
    project_ignored_paths: list[str] | None = None,
    global_ignored_paths: list[str] | None = None,
) -> Project:
    """Helper to create a Project with the given ignored paths configuration."""
    config = ProjectConfig(
        project_name="test_project",
        languages=[Language.PYTHON],
        ignored_paths=project_ignored_paths or [],
        ignore_all_files_in_gitignore=False,
    )
    serena_config: SerenaConfig | None = None
    if global_ignored_paths:
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False, ignored_paths=global_ignored_paths)
    return Project(
        project_root=str(project_root),
        project_config=config,
        serena_config=serena_config,
    )


class TestGlobalIgnoredPaths:
    """Tests for system-global ignored_paths feature."""

    def setup_method(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir)
        # Create some test files and directories
        (self.project_path / "main.py").write_text("print('hello')")
        os.makedirs(self.project_path / "node_modules" / "pkg", exist_ok=True)
        (self.project_path / "node_modules" / "pkg" / "index.js").write_text("module.exports = {}")
        os.makedirs(self.project_path / "build", exist_ok=True)
        (self.project_path / "build" / "output.js").write_text("compiled")
        os.makedirs(self.project_path / "src", exist_ok=True)
        (self.project_path / "src" / "app.py").write_text("def app(): pass")
        (self.project_path / "debug.log").write_text("log data")

    def teardown_method(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_global_ignored_paths_are_applied(self) -> None:
        """Global ignored_paths from SerenaConfig are respected by Project.is_ignored_path()."""
        project = _create_test_project(
            self.project_path,
            global_ignored_paths=["node_modules"],
        )
        assert project.is_ignored_path(str(self.project_path / "node_modules" / "pkg" / "index.js"))
        assert not project.is_ignored_path(str(self.project_path / "src" / "app.py"))

    def test_additive_merge_of_global_and_project_patterns(self) -> None:
        """Global + project patterns are merged additively (both applied)."""
        project = _create_test_project(
            self.project_path,
            project_ignored_paths=["build"],
            global_ignored_paths=["node_modules"],
        )
        # Global pattern should be applied
        assert project.is_ignored_path(str(self.project_path / "node_modules" / "pkg" / "index.js"))
        # Project pattern should also be applied
        assert project.is_ignored_path(str(self.project_path / "build" / "output.js"))
        # Non-ignored files should not be affected
        assert not project.is_ignored_path(str(self.project_path / "src" / "app.py"))

    def test_empty_global_ignored_paths_has_no_effect(self) -> None:
        """Empty global ignored_paths (default) has no effect on existing behavior."""
        project = _create_test_project(
            self.project_path,
            project_ignored_paths=["build"],
            global_ignored_paths=[],
        )
        # Project pattern still works
        assert project.is_ignored_path(str(self.project_path / "build" / "output.js"))
        # Non-ignored files still accessible
        assert not project.is_ignored_path(str(self.project_path / "node_modules" / "pkg" / "index.js"))

    def test_default_global_ignored_paths_backward_compatible(self) -> None:
        """Project created without global_ignored_paths parameter works as before."""
        config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON],
            ignored_paths=["build"],
            ignore_all_files_in_gitignore=False,
        )
        project = Project(
            project_root=str(self.project_path),
            project_config=config,
        )
        assert project.is_ignored_path(str(self.project_path / "build" / "output.js"))
        assert not project.is_ignored_path(str(self.project_path / "node_modules" / "pkg" / "index.js"))

    def test_duplicate_patterns_across_global_and_project(self) -> None:
        """Duplicate patterns across global and project do not cause errors."""
        project = _create_test_project(
            self.project_path,
            project_ignored_paths=["node_modules", "build"],
            global_ignored_paths=["node_modules", "build"],
        )
        assert project.is_ignored_path(str(self.project_path / "node_modules" / "pkg" / "index.js"))
        assert project.is_ignored_path(str(self.project_path / "build" / "output.js"))
        assert not project.is_ignored_path(str(self.project_path / "src" / "app.py"))

    def test_glob_patterns_in_global_ignored_paths(self) -> None:
        """Global ignored_paths support gitignore-style glob patterns."""
        project = _create_test_project(
            self.project_path,
            global_ignored_paths=["*.log"],
        )
        assert project.is_ignored_path(str(self.project_path / "debug.log"))
        assert not project.is_ignored_path(str(self.project_path / "main.py"))


class TestRegisteredProjectGlobalIgnoredPaths:
    """RegisteredProject.get_project_instance() correctly passes global patterns to Project."""

    def setup_method(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir).resolve()
        (self.project_path / "main.py").write_text("print('hello')")
        os.makedirs(self.project_path / "node_modules", exist_ok=True)
        (self.project_path / "node_modules" / "pkg.js").write_text("module")

    def teardown_method(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_get_project_instance_passes_global_ignored_paths(self) -> None:
        """RegisteredProject.get_project_instance() passes global_ignored_paths to Project."""
        config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON],
            ignored_paths=[],
            ignore_all_files_in_gitignore=False,
        )
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False, ignored_paths=["node_modules"])
        registered = RegisteredProject(
            project_root=str(self.project_path),
            project_config=config,
        )
        project = registered.get_project_instance(serena_config=serena_config)
        assert project.is_ignored_path(str(self.project_path / "node_modules" / "pkg.js"))

    def test_get_project_instance_without_global_ignored_paths(self) -> None:
        """RegisteredProject without global_ignored_paths defaults to empty."""
        config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON],
            ignored_paths=[],
            ignore_all_files_in_gitignore=False,
        )
        registered = RegisteredProject(
            project_root=str(self.project_path),
            project_config=config,
        )
        project = registered.get_project_instance(serena_config=None)
        assert not project.is_ignored_path(str(self.project_path / "node_modules" / "pkg.js"))

    def test_from_project_root_passes_global_ignored_paths(self) -> None:
        """RegisteredProject.from_project_root() threads global_ignored_paths to Project."""
        # Create a minimal project.yml so from_project_root can load config
        serena_dir = self.project_path / ".serena"
        serena_dir.mkdir(exist_ok=True)
        (serena_dir / "project.yml").write_text(
            'project_name: "test_project"\nlanguages: ["python"]\nignored_paths: []\nignore_all_files_in_gitignore: false\n'
        )
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False, ignored_paths=["node_modules"])
        registered = RegisteredProject.from_project_root(
            str(self.project_path),
        )
        project = registered.get_project_instance(serena_config=serena_config)
        assert project.is_ignored_path(str(self.project_path / "node_modules" / "pkg.js"))

    def test_from_project_instance_passes_global_ignored_paths(self) -> None:
        """RegisteredProject.from_project_instance() threads global_ignored_paths to Project."""
        config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON],
            ignored_paths=[],
            ignore_all_files_in_gitignore=False,
        )
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False, ignored_paths=["node_modules"])
        project = Project(
            project_root=str(self.project_path),
            project_config=config,
            serena_config=serena_config,
        )
        registered = RegisteredProject.from_project_instance(project)
        # The registered project already has a project_instance, so get_project_instance() returns it directly
        retrieved = registered.get_project_instance(serena_config=serena_config)
        assert retrieved.is_ignored_path(str(self.project_path / "node_modules" / "pkg.js"))


class TestGlobalIgnoredPathsWithGitignore:
    """Global ignored_paths combined with ignore_all_files_in_gitignore produces correct three-way merge."""

    def setup_method(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir).resolve()
        # Create test files
        (self.project_path / "main.py").write_text("print('hello')")
        os.makedirs(self.project_path / "node_modules", exist_ok=True)
        (self.project_path / "node_modules" / "pkg.js").write_text("module")
        os.makedirs(self.project_path / "dist", exist_ok=True)
        (self.project_path / "dist" / "bundle.js").write_text("bundled")
        os.makedirs(self.project_path / "build", exist_ok=True)
        (self.project_path / "build" / "output.js").write_text("compiled")
        # Create .gitignore that ignores dist/
        (self.project_path / ".gitignore").write_text("dist/\n")

    def teardown_method(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_three_way_merge_global_project_and_gitignore(self) -> None:
        """Global patterns, project patterns, and .gitignore patterns are all applied together."""
        config = ProjectConfig(
            project_name="test_project",
            languages=[Language.PYTHON],
            ignored_paths=["build"],
            ignore_all_files_in_gitignore=True,
        )
        serena_config = SerenaConfig(gui_log_window=False, web_dashboard=False, ignored_paths=["node_modules"])
        project = Project(
            project_root=str(self.project_path),
            project_config=config,
            serena_config=serena_config,
        )
        # Global pattern: node_modules
        assert project.is_ignored_path(str(self.project_path / "node_modules" / "pkg.js"))
        # Project pattern: build
        assert project.is_ignored_path(str(self.project_path / "build" / "output.js"))
        # Gitignore pattern: dist/
        assert project.is_ignored_path(str(self.project_path / "dist" / "bundle.js"))
        # Non-ignored file
        assert not project.is_ignored_path(str(self.project_path / "main.py"))


class TestSerenaConfigIgnoredPaths:
    """Config loading with ignored_paths in serena_config.yml works correctly."""

    def test_serena_config_default_ignored_paths(self) -> None:
        """SerenaConfig defaults to empty ignored_paths."""
        config = SerenaConfig(gui_log_window=False, web_dashboard=False)
        assert config.ignored_paths == []

    def test_serena_config_with_ignored_paths(self) -> None:
        """SerenaConfig can be created with explicit ignored_paths."""
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            ignored_paths=["node_modules", "*.log", "build"],
        )
        assert config.ignored_paths == ["node_modules", "*.log", "build"]
