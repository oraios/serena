import logging
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import (
    DEFAULT_PROJECT_SERENA_FOLDER_LOCATION,
    LanguageBackend,
    ProjectConfig,
    RegisteredProject,
    SerenaConfig,
    SerenaConfigError,
)
from serena.constants import PROJECT_TEMPLATE_FILE, SERENA_MANAGED_DIR_NAME
from serena.project import MemoriesManager, Project
from solidlsp.ls_config import Language
from test.conftest import create_default_serena_config


class TestProjectConfigAutogenerate:
    """Test class for ProjectConfig autogeneration functionality."""

    def setup_method(self):
        """Set up test environment before each test method."""
        # Create a temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.serena_config = create_default_serena_config()
        self.project_path = Path(self.test_dir)

    def teardown_method(self):
        """Clean up test environment after each test method."""
        # Remove the temporary directory
        shutil.rmtree(self.test_dir)

    def test_autogenerate_empty_directory(self):
        """Test that autogenerate succeeds with empty languages list for an empty directory."""
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=False)

        assert config.project_name == self.project_path.name
        assert config.languages == []

    def test_autogenerate_empty_directory_logs_warning(self, caplog):
        """Test that autogenerate logs a warning when no language files are found."""
        with caplog.at_level(logging.WARNING):
            ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=False)

        assert any("No source files for supported language servers were found" in msg for msg in caplog.messages)

    def test_autogenerate_with_python_files(self):
        """Test successful autogeneration with Python source files."""
        # Create a Python file
        python_file = self.project_path / "main.py"
        python_file.write_text("def hello():\n    print('Hello, world!')\n")

        # Run autogenerate
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=False)

        # Verify the configuration
        assert config.project_name == self.project_path.name
        assert config.languages == [Language.PYTHON]

    def test_autogenerate_with_js_files(self):
        """Test successful autogeneration with JavaScript source files."""
        # Create files for multiple languages
        (self.project_path / "small.js").write_text("console.log('JS');")

        # Run autogenerate - should pick Python as dominant
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=False)

        assert config.languages == [Language.TYPESCRIPT]

    def test_autogenerate_with_multiple_languages(self):
        """Test autogeneration picks dominant language when multiple are present."""
        # Create files for multiple languages
        (self.project_path / "main.py").write_text("print('Python')")
        (self.project_path / "util.py").write_text("def util(): pass")
        (self.project_path / "small.js").write_text("console.log('JS');")

        # Run autogenerate - should pick Python as dominant
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=False)

        assert config.languages == [Language.PYTHON]

    def test_autogenerate_saves_to_disk(self):
        """Test that autogenerate can save the configuration to disk."""
        # Create a Go file
        go_file = self.project_path / "main.go"
        go_file.write_text("package main\n\nfunc main() {}\n")

        # Run autogenerate with save_to_disk=True
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=True)

        # Verify the configuration file was created
        config_path = self.project_path / ".serena" / "project.yml"
        assert config_path.exists()

        # Verify the content
        assert config.languages == [Language.GO]

    def test_autogenerate_nonexistent_path(self):
        """Test that autogenerate raises FileNotFoundError for non-existent path."""
        non_existent = self.project_path / "does_not_exist"

        with pytest.raises(FileNotFoundError) as exc_info:
            ProjectConfig.autogenerate(non_existent, self.serena_config, save_to_disk=False)

        assert "Project root not found" in str(exc_info.value)

    def test_autogenerate_with_gitignored_files_only(self):
        """Test autogenerate creates a project with empty languages when only gitignored files exist."""
        # Create a .gitignore that ignores all Python files
        gitignore = self.project_path / ".gitignore"
        gitignore.write_text("*.py\n")

        # Create Python files that will be ignored
        (self.project_path / "ignored.py").write_text("print('ignored')")

        # Should succeed with empty languages (gitignored files are not counted)
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, save_to_disk=False)

        assert config.project_name == self.project_path.name
        assert config.languages == []

    def test_autogenerate_custom_project_name(self):
        """Test autogenerate with custom project name."""
        # Create a TypeScript file
        ts_file = self.project_path / "index.ts"
        ts_file.write_text("const greeting: string = 'Hello';\n")

        # Run autogenerate with custom name
        custom_name = "my-custom-project"
        config = ProjectConfig.autogenerate(self.project_path, self.serena_config, project_name=custom_name, save_to_disk=False)

        assert config.project_name == custom_name
        assert config.languages == [Language.TYPESCRIPT]


class TestProjectConfig:
    def test_template_is_complete(self):
        _, is_complete = ProjectConfig._load_yaml_dict(PROJECT_TEMPLATE_FILE)
        assert is_complete, "Project template YAML is incomplete; all fields must be present (with descriptions)."


class TestProjectConfigLanguageBackend:
    """Tests for the per-project language_backend field."""

    def test_language_backend_defaults_to_none(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.PYTHON],
        )
        assert config.language_backend is None

    def test_language_backend_can_be_set(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.PYTHON],
            language_backend=LanguageBackend.JETBRAINS,
        )
        assert config.language_backend == LanguageBackend.JETBRAINS

    def test_language_backend_roundtrips_through_yaml(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.PYTHON],
            language_backend=LanguageBackend.JETBRAINS,
        )
        d = config._to_yaml_dict()
        assert d["language_backend"] == "JetBrains"

    def test_language_backend_none_roundtrips_through_yaml(self):
        config = ProjectConfig(
            project_name="test",
            languages=[Language.PYTHON],
        )
        d = config._to_yaml_dict()
        assert d["language_backend"] is None

    def test_language_backend_parsed_from_dict(self):
        """Test that _from_dict parses language_backend correctly."""
        template_path = PROJECT_TEMPLATE_FILE
        data, _ = ProjectConfig._load_yaml_dict(template_path)
        data["project_name"] = "test"
        data["languages"] = ["python"]
        data["language_backend"] = "JetBrains"
        config = ProjectConfig._from_dict(data, local_override_keys=[])
        assert config.language_backend == LanguageBackend.JETBRAINS

    def test_language_backend_none_when_missing_from_dict(self):
        """Test that _from_dict handles missing language_backend gracefully."""
        template_path = PROJECT_TEMPLATE_FILE
        data, _ = ProjectConfig._load_yaml_dict(template_path)
        data["project_name"] = "test"
        data["languages"] = ["python"]
        data.pop("language_backend", None)
        config = ProjectConfig._from_dict(data, local_override_keys=[])
        assert config.language_backend is None


def _make_config_with_project(
    project_name: str,
    language_backend: LanguageBackend | None = None,
    global_backend: LanguageBackend = LanguageBackend.LSP,
) -> tuple[SerenaConfig, str]:
    """Create a SerenaConfig with a single registered project and return (config, project_name)."""
    config = SerenaConfig(
        gui_log_window=False,
        web_dashboard=False,
        log_level=logging.ERROR,
        language_backend=global_backend,
    )
    project = Project(
        project_root=str(Path(__file__).parent.parent / "resources" / "repos" / "python" / "test_repo"),
        project_config=ProjectConfig(
            project_name=project_name,
            languages=[Language.PYTHON],
            language_backend=language_backend,
        ),
        serena_config=config,
    )
    config.projects = [RegisteredProject.from_project_instance(project)]
    return config, project_name


class TestEffectiveLanguageBackend:
    """Tests for per-project language_backend override logic in SerenaAgent."""

    def test_default_backend_is_global(self):
        """When no project override, effective backend matches global config."""
        config, name = _make_config_with_project("test_proj", language_backend=None, global_backend=LanguageBackend.LSP)
        agent = SerenaAgent(project=name, serena_config=config)
        try:
            assert agent.get_language_backend().is_lsp()
        finally:
            agent.on_shutdown(timeout=5)

    def test_project_overrides_global_backend(self):
        """When startup project has language_backend set, it overrides the global."""
        config, name = _make_config_with_project(
            "test_jetbrains", language_backend=LanguageBackend.JETBRAINS, global_backend=LanguageBackend.LSP
        )
        agent = SerenaAgent(project=name, serena_config=config)
        try:
            assert agent.get_language_backend().is_jetbrains()
        finally:
            agent.on_shutdown(timeout=5)

    def test_no_project_uses_global_backend(self):
        """When no startup project is provided, effective backend is the global one."""
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            log_level=logging.ERROR,
            language_backend=LanguageBackend.LSP,
        )
        agent = SerenaAgent(project=None, serena_config=config)
        try:
            assert agent.get_language_backend() == LanguageBackend.LSP
        finally:
            agent.on_shutdown(timeout=5)

    def test_activate_project_rejects_backend_mismatch(self):
        """Post-init activation of a project with mismatched backend raises ValueError."""
        # Start with LSP backend
        config, name = _make_config_with_project("lsp_proj", language_backend=None, global_backend=LanguageBackend.LSP)

        # Add a second project that requires JetBrains
        jb_project = Project(
            project_root=str(Path(__file__).parent.parent / "resources" / "repos" / "java" / "test_repo"),
            project_config=ProjectConfig(
                project_name="jb_proj",
                languages=[Language.JAVA],
                language_backend=LanguageBackend.JETBRAINS,
            ),
            serena_config=config,
        )
        config.projects.append(RegisteredProject.from_project_instance(jb_project))

        agent = SerenaAgent(project=name, serena_config=config)
        try:
            with pytest.raises(ValueError, match="Cannot activate project"):
                agent.activate_project_from_path_or_name("jb_proj")
        finally:
            agent.on_shutdown(timeout=5)

    def test_activate_project_allows_matching_backend(self):
        """Post-init activation of a project with matching backend succeeds."""
        config, name = _make_config_with_project("lsp_proj", language_backend=None, global_backend=LanguageBackend.LSP)

        # Add a second project that also uses LSP
        lsp_project2 = Project(
            project_root=str(Path(__file__).parent.parent / "resources" / "repos" / "python" / "test_repo"),
            project_config=ProjectConfig(
                project_name="lsp_proj2",
                languages=[Language.PYTHON],
                language_backend=LanguageBackend.LSP,
            ),
            serena_config=config,
        )
        config.projects.append(RegisteredProject.from_project_instance(lsp_project2))

        agent = SerenaAgent(project=name, serena_config=config)
        try:
            # Should not raise
            agent.activate_project_from_path_or_name("lsp_proj2")
        finally:
            agent.on_shutdown(timeout=5)

    def test_activate_project_allows_none_backend(self):
        """Post-init activation of a project with no backend override succeeds."""
        config, name = _make_config_with_project("lsp_proj", language_backend=None, global_backend=LanguageBackend.LSP)

        # Add a second project with no backend override
        proj2 = Project(
            project_root=str(Path(__file__).parent.parent / "resources" / "repos" / "python" / "test_repo"),
            project_config=ProjectConfig(
                project_name="proj2",
                languages=[Language.PYTHON],
                language_backend=None,
            ),
            serena_config=config,
        )
        config.projects.append(RegisteredProject.from_project_instance(proj2))

        agent = SerenaAgent(project=name, serena_config=config)
        try:
            # Should not raise — None means "inherit session backend"
            agent.activate_project_from_path_or_name("proj2")
        finally:
            agent.on_shutdown(timeout=5)


class TestGetConfiguredProjectSerenaFolder:
    """Tests for SerenaConfig.get_configured_project_serena_folder (pure template resolution)."""

    def test_default_location(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
        )
        result = config.get_configured_project_serena_folder("/home/user/myproject")
        assert result == os.path.abspath("/home/user/myproject/.serena")

    def test_custom_location_with_project_folder_name(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="/projects-metadata/$projectFolderName/.serena",
        )
        result = config.get_configured_project_serena_folder("/home/user/myproject")
        assert result == os.path.abspath("/projects-metadata/myproject/.serena")

    def test_custom_location_with_project_dir(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="$projectDir/.custom-serena",
        )
        result = config.get_configured_project_serena_folder("/home/user/myproject")
        assert result == os.path.abspath("/home/user/myproject/.custom-serena")

    def test_custom_location_with_both_placeholders(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="/data/$projectFolderName/$projectDir/.serena",
        )
        result = config.get_configured_project_serena_folder("/home/user/proj")
        assert result == os.path.abspath("/data/proj/home/user/proj/.serena")

    def test_default_field_value(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
        )
        assert config.project_serena_folder_location == DEFAULT_PROJECT_SERENA_FOLDER_LOCATION

    def test_rejects_unknown_placeholder(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="$projectDir/$unknownVar/.serena",
        )
        with pytest.raises(SerenaConfigError, match=r"Unknown placeholder '\$unknownVar'"):
            config.get_configured_project_serena_folder("/home/user/myproject")

    def test_rejects_typo_projectDirs(self):
        """$projectDirs should not be silently treated as $projectDir + 's'."""
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="$projectDirs/.serena",
        )
        with pytest.raises(SerenaConfigError, match=r"Unknown placeholder '\$projectDirs'"):
            config.get_configured_project_serena_folder("/home/user/myproject")

    def test_rejects_typo_projectfoldername_lowercase(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="/data/$projectfoldername/.serena",
        )
        with pytest.raises(SerenaConfigError, match=r"Unknown placeholder '\$projectfoldername'"):
            config.get_configured_project_serena_folder("/home/user/myproject")

    def test_no_placeholders_is_valid(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="/fixed/path/.serena",
        )
        result = config.get_configured_project_serena_folder("/home/user/myproject")
        assert result == os.path.abspath("/fixed/path/.serena")

    def test_error_message_lists_supported_placeholders(self):
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="$bogus/.serena",
        )
        with pytest.raises(SerenaConfigError, match=r"\$projectDir.*\$projectFolderName|\$projectFolderName.*\$projectDir"):
            config.get_configured_project_serena_folder("/home/user/myproject")


class TestProjectSerenaDataFolder:
    """Tests for SerenaConfig.get_project_serena_folder fallback logic (via Project)."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.project_path = Path(self.test_dir) / "myproject"
        self.project_path.mkdir()
        (self.project_path / "main.py").write_text("print('hello')\n")

    def teardown_method(self):
        shutil.rmtree(self.test_dir)

    def _make_project(self, serena_config: "SerenaConfig | None" = None) -> Project:
        project_config = ProjectConfig(
            project_name="myproject",
            languages=[Language.PYTHON],
        )
        project = Project(
            project_root=str(self.project_path),
            project_config=project_config,
            serena_config=serena_config,
        )
        project._ignore_spec_available.wait()
        return project

    def test_default_config_creates_in_project_dir(self):
        config = SerenaConfig(gui_log_window=False, web_dashboard=False)
        project = self._make_project(config)
        expected = os.path.abspath(str(self.project_path / SERENA_MANAGED_DIR_NAME))
        assert project.path_to_serena_data_folder() == expected

    def test_custom_location_creates_outside_project(self):
        custom_base = Path(self.test_dir) / "metadata"
        custom_base.mkdir()
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location=str(custom_base) + "/$projectFolderName/.serena",
        )
        project = self._make_project(config)
        expected = os.path.abspath(str(custom_base / "myproject" / ".serena"))
        assert project.path_to_serena_data_folder() == expected

    def test_fallback_to_existing_project_dir(self):
        """If config points to a non-existent path but .serena exists in the project root, use the existing one."""
        existing_serena = self.project_path / SERENA_MANAGED_DIR_NAME
        existing_serena.mkdir()
        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location="/nonexistent/path/$projectFolderName/.serena",
        )
        project = self._make_project(config)
        assert project.path_to_serena_data_folder() == str(existing_serena)

    def test_configured_path_takes_precedence_when_exists(self):
        """If both config path and project root path exist, use the config path."""
        existing_serena = self.project_path / SERENA_MANAGED_DIR_NAME
        existing_serena.mkdir()

        custom_base = Path(self.test_dir) / "metadata"
        custom_serena = custom_base / "myproject" / ".serena"
        custom_serena.mkdir(parents=True)

        config = SerenaConfig(
            gui_log_window=False,
            web_dashboard=False,
            project_serena_folder_location=str(custom_base) + "/$projectFolderName/.serena",
        )
        project = self._make_project(config)
        assert project.path_to_serena_data_folder() == str(custom_serena)


class TestSerenaConfigFromConfigFileRobustness:
    """Tests that ``SerenaConfig.from_config_file`` does not abort the whole
    loader when a single registered project has a broken ``project.yml``.
    """

    def setup_method(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.master_config_path = self.test_dir / "serena_config.yml"

    def teardown_method(self):
        shutil.rmtree(self.test_dir)

    def _make_project_dir(self, name: str, project_yml_body: str) -> Path:
        project_dir = self.test_dir / name
        (project_dir / SERENA_MANAGED_DIR_NAME).mkdir(parents=True)
        (project_dir / SERENA_MANAGED_DIR_NAME / "project.yml").write_text(project_yml_body)
        return project_dir

    def _write_master_config(self, project_paths: list[Path]) -> None:
        body_lines = ["projects:"]
        for p in project_paths:
            body_lines.append(f"  - {p}")
        self.master_config_path.write_text("\n".join(body_lines) + "\n")

    def test_malformed_project_is_skipped_with_warning(self, caplog, monkeypatch):
        """A malformed project.yml must not abort loading of the others."""
        good_project = self._make_project_dir(
            "good_project",
            'project_name: "good_project"\nlanguages: ["python"]\n',
        )
        # Invalid YAML: a stray colon at the start of a mapping value.
        bad_project = self._make_project_dir(
            "bad_project",
            ": this is not : valid : yaml :\n",
        )
        self._write_master_config([good_project, bad_project])

        # SerenaPaths is a process-wide singleton, so we cannot reliably
        # redirect it via SERENA_HOME after the fact. Instead, redirect the
        # config-file-path resolver directly.
        monkeypatch.setattr(
            SerenaConfig,
            "_determine_config_file_path",
            classmethod(lambda cls: str(self.master_config_path)),
        )

        with caplog.at_level(logging.ERROR):
            config = SerenaConfig.from_config_file(generate_if_missing=False)

        registered_roots = {Path(p.project_root).resolve() for p in config.projects}
        assert registered_roots == {good_project.resolve()}, f"Expected only the good project to be registered, got {registered_roots}"
        assert any("Failed to load project configuration" in msg and str(bad_project.resolve()) in msg for msg in caplog.messages), (
            f"Expected a warning naming {bad_project.resolve()}, got: {caplog.messages}"
        )


class TestMemoriesManagerCustomPath:
    """Tests for MemoriesManager with a custom serena data folder."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.data_folder = Path(self.test_dir) / "custom_serena"

    def teardown_method(self):
        shutil.rmtree(self.test_dir)

    def test_memories_subdir_is_created(self):
        assert not self.data_folder.exists()
        MemoriesManager(str(self.data_folder))
        assert (self.data_folder / "memories").exists()

    def test_save_and_load_memory(self):
        manager = MemoriesManager(str(self.data_folder))
        manager.save_memory("test_topic", "test content", is_tool_context=False)
        content = manager.load_memory("test_topic")
        assert content == "test content"

    def test_list_memories(self):
        manager = MemoriesManager(str(self.data_folder))
        manager.save_memory("topic_a", "content a", is_tool_context=False)
        manager.save_memory("topic_b", "content b", is_tool_context=False)
        memories = manager.list_project_memories()
        assert sorted(memories.get_full_list()) == ["topic_a", "topic_b"]
