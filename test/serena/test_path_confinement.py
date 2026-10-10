"""
Tests for the confinement of file access to the project root: a symlink contained in the project
(or a ".." segment in a path) must not redirect reads, writes, searches or edits to locations
outside the project root.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import SerenaConfig
from serena.language_backend import BuiltinLanguageBackend
from serena.project import Project
from serena.repl.api.edit_api import EditApi
from serena.repl.api.fs_api import FsApi
from serena.tools import CreateTextFileTool, ReadFileTool


def _create_symlink(link_path: Path, target: Path) -> None:
    """
    Creates a symlink, skipping the test if the environment does not permit symlink creation
    (e.g. Windows without the required privilege).
    """
    try:
        os.symlink(target, link_path)
    except OSError:
        pytest.skip("symlinks cannot be created in this environment")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """
    A project with a regular file, an in-project symlink, a symlink to a file outside the project,
    a symlink to a not-yet-existing file outside the project and a symlink to a directory outside
    the project; the external targets reside in a sibling directory.
    """
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    (root / "real.txt").write_text("in-project content\n", encoding="utf-8")
    (outside / "secret.txt").write_text("external secret\n", encoding="utf-8")
    (outside / "victim.txt").write_text("line0\nline1\nline2\n", encoding="utf-8")
    (outside / "outside_dir").mkdir()
    (outside / "outside_dir" / "secret.py").write_text("external_symbol = 1\n", encoding="utf-8")

    _create_symlink(root / "innocent.txt", outside / "secret.txt")
    _create_symlink(root / "notes.txt", outside / "planted.txt")
    _create_symlink(root / "linked_dir", outside / "outside_dir")
    _create_symlink(root / "inner_link.txt", root / "real.txt")
    return root


@pytest.fixture
def outside_dir(project_root: Path) -> Path:
    """:return: the directory outside the project root holding the symlink targets"""
    return project_root.parent / "outside"


def _untrusted_config() -> SerenaConfig:
    return SerenaConfig(gui_log_window=False, web_dashboard=False, trusted_project_path_patterns=[])


@pytest.fixture
def untrusted_project(project_root: Path) -> Project:
    """
    A project that is not trusted, i.e. the configuration trusts no project root
    (the default for newly created configurations).
    """
    return Project.load(str(project_root), serena_config=_untrusted_config())


@pytest.fixture
def trusted_project(project_root: Path) -> Project:
    """
    A trusted project (the default for existing configurations), for which following a symlink
    outside the project root remains possible.
    """
    return Project.load(str(project_root), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))


def _agent(project: Project) -> MagicMock:
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 10000
    return agent


def _edit_api(project: Project) -> EditApi:
    """
    :return: the editing API backed by the JetBrains backend, whose code editor can be constructed
        without a running IDE (the plugin client is only contacted when an edit is actually applied)
    """
    agent = _agent(project)
    agent.get_language_backend.return_value = BuiltinLanguageBackend.JETBRAINS.get_instance()
    return EditApi(agent)


class TestPathsOutsideProjectRootAreRefused:
    """File access outside the project root — through a symlink contained in the project or through a ".." path — must be refused."""

    def test_read_file_is_refused(self, untrusted_project: Project, outside_dir: Path) -> None:
        tool = ReadFileTool(_agent(untrusted_project))

        with pytest.raises(ValueError, match="outside the project root"):
            tool.apply("innocent.txt")

        assert (outside_dir / "secret.txt").read_text(encoding="utf-8") == "external secret\n"

    def test_create_text_file_is_refused(self, untrusted_project: Project, outside_dir: Path) -> None:
        tool = CreateTextFileTool(_agent(untrusted_project))

        with pytest.raises(ValueError, match="outside the project root"):
            tool.apply("notes.txt", "planted\n")

        assert not (outside_dir / "planted.txt").exists()

    def test_traversal_does_not_report_external_files(self, untrusted_project: Project) -> None:
        api = FsApi(_agent(untrusted_project))

        assert len(api.search_for_pattern("external")) == 0
        assert len(api.search_for_pattern("external", restrict_search_to_code_files=True)) == 0

        listing = api.list_dir(".", recursive=True)
        assert "linked_dir" not in listing.dirs
        assert not any(f.startswith("linked_dir") for f in listing.files)

        assert api.find_file("secret.py", ".") == []

    def test_traversal_ignores_links_entirely(self, untrusted_project: Project) -> None:
        # in an untrusted project, links are not part of the project's file set at all,
        # including links whose target is inside the project
        api = FsApi(_agent(untrusted_project))

        listing = api.list_dir(".", recursive=True)
        assert "inner_link.txt" not in listing.files
        assert "innocent.txt" not in listing.files
        assert api.find_file("*.txt", ".") == ["real.txt"]
        assert [m.source_file_path for m in api.search_for_pattern("in-project content").matches] == ["real.txt"]

    def test_discovery_refuses_to_enter_a_linked_directory(self, untrusted_project: Project) -> None:
        with pytest.raises(ValueError, match="outside the project root"):
            untrusted_project.gather_project_files("linked_dir")

    def test_editing_tools_are_refused(self, untrusted_project: Project, outside_dir: Path) -> None:
        api = _edit_api(untrusted_project)

        with pytest.raises(ValueError, match="outside the project root"):
            api.delete_lines("../outside/victim.txt", 1, 1)
        with pytest.raises(ValueError, match="outside the project root"):
            api.delete_lines("innocent.txt", 0, 0)
        with pytest.raises(ValueError, match="outside the project root"):
            api.replace_lines("../outside/victim.txt", 0, 0, "replaced\n")
        with pytest.raises(ValueError, match="outside the project root"):
            api.insert_at_line("../outside/victim.txt", 0, "inserted\n")
        with pytest.raises(ValueError, match="outside the project root"):
            api.replace_content("../outside/victim.txt", "line1", "changed", mode="literal")
        with pytest.raises(ValueError, match="outside the project root"):
            api.replace_symbol_body("SomeSymbol", "../outside/victim.txt", "body")
        with pytest.raises(ValueError, match="outside the project root"):
            api.insert_after_symbol("SomeSymbol", "../outside/victim.txt", "body")
        with pytest.raises(ValueError, match="outside the project root"):
            api.insert_before_symbol("SomeSymbol", "../outside/victim.txt", "body")

        assert (outside_dir / "victim.txt").read_text(encoding="utf-8") == "line0\nline1\nline2\n"
        assert (outside_dir / "secret.txt").read_text(encoding="utf-8") == "external secret\n"


class TestPathsRemainingInsideProjectRoot:
    """The confinement must not restrict access to paths that stay inside the project root."""

    def test_in_project_symlink_remains_readable(self, untrusted_project: Project) -> None:
        tool = ReadFileTool(_agent(untrusted_project))
        assert tool.apply("inner_link.txt") == "in-project content\n"

    def test_dotdot_path_is_refused_even_for_trusted_projects(self, trusted_project: Project) -> None:
        # trust only exempts symlink targets from the containment check, never lexical escapes
        tool = ReadFileTool(_agent(trusted_project))
        with pytest.raises(ValueError, match="outside the project root"):
            tool.apply("../outside/secret.txt")


class TestTrustedProjectsKeepSymlinkAccess:
    """For trusted projects, following a symlink outside the project root remains possible (as introduced for #936)."""

    def test_read_file_via_symlink_outside_project_root_is_allowed(self, trusted_project: Project, outside_dir: Path) -> None:
        tool = ReadFileTool(_agent(trusted_project))
        assert tool.apply("innocent.txt") == "external secret\n"
        assert (outside_dir / "secret.txt").read_text(encoding="utf-8") == "external secret\n"

    def test_traversal_reports_external_files(self, trusted_project: Project) -> None:
        api = FsApi(_agent(trusted_project))
        assert len(api.search_for_pattern("external")) > 0
        assert "linked_dir" in api.list_dir(".", recursive=True).dirs

    def test_traversal_reports_links_inside_the_project(self, trusted_project: Project) -> None:
        # for a trusted project, a link is just another file, whether or not it stays inside the project
        api = FsApi(_agent(trusted_project))

        listing = api.list_dir(".", recursive=True)
        assert "inner_link.txt" in listing.files
        assert "innocent.txt" in listing.files
