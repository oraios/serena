"""Tests for the CLI's ``project remove`` command."""

import shutil
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from serena.cli import ProjectCommands
from serena.config.serena_config import SerenaConfig
from serena.constants import SERENA_MANAGED_DIR_NAME


class TestProjectRemove:
    """
    Drives ``serena project remove`` against a temporary Serena configuration file, so the
    user's real project registry is never touched.
    """

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.test_dir = Path(tempfile.mkdtemp())
        self.master_config_path = self.test_dir / "serena_config.yml"
        monkeypatch.setattr(
            SerenaConfig,
            "_determine_config_file_path",
            classmethod(lambda cls: str(self.master_config_path)),
        )
        self.runner = CliRunner()

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_project_dir(self, dir_name: str, project_name: str | None = None) -> Path:
        project_dir = self.test_dir / dir_name
        (project_dir / SERENA_MANAGED_DIR_NAME).mkdir(parents=True)
        (project_dir / SERENA_MANAGED_DIR_NAME / "project.yml").write_text(
            f'project_name: "{project_name or dir_name}"\nlanguages: ["python"]\n'
        )
        return project_dir

    def _write_master_config(self, project_paths: list[Path]) -> None:
        self.master_config_path.write_text("projects:\n" + "".join(f"  - {p}\n" for p in project_paths))

    def _registered_roots(self) -> set[Path]:
        config = SerenaConfig.from_config_file(generate_if_missing=False)
        return {Path(project.project_root) for project in config.projects}

    def test_remove_by_name_unregisters_only_that_project(self):
        keep = self._make_project_dir("keep")
        drop = self._make_project_dir("drop")
        self._write_master_config([keep, drop])

        result = self.runner.invoke(ProjectCommands.remove, ["drop"])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert self._registered_roots() == {keep.resolve()}

    def test_remove_by_path_unregisters_only_that_project(self):
        keep = self._make_project_dir("keep")
        drop = self._make_project_dir("drop")
        self._write_master_config([keep, drop])

        result = self.runner.invoke(ProjectCommands.remove, [str(drop)])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert self._registered_roots() == {keep.resolve()}

    def test_remove_names_the_project_it_removed(self):
        drop = self._make_project_dir("drop")
        self._write_master_config([drop])

        result = self.runner.invoke(ProjectCommands.remove, [str(drop)])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert "drop" in result.output
        assert str(drop.resolve()) in result.output

    def test_remove_keeps_the_project_configuration_file_on_disk(self):
        """Unregistering must not delete the project's own files; re-registering it must remain possible."""
        drop = self._make_project_dir("drop")
        self._write_master_config([drop])

        result = self.runner.invoke(ProjectCommands.remove, [str(drop)])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert (drop / SERENA_MANAGED_DIR_NAME / "project.yml").is_file()

    def test_remove_unknown_project_fails_without_changing_the_registry(self):
        keep = self._make_project_dir("keep")
        self._write_master_config([keep])

        result = self.runner.invoke(ProjectCommands.remove, ["no_such_project"])

        assert result.exit_code != 0
        assert "no_such_project" in result.output
        assert self._registered_roots() == {keep.resolve()}

    def test_remove_by_path_picks_the_entry_at_that_path_when_names_collide(self):
        """Two directories may carry the same ``project_name``; a path must remove the entry at that path."""
        first = self._make_project_dir("first_dir", project_name="twin")
        second = self._make_project_dir("second_dir", project_name="twin")
        self._write_master_config([first, second])

        result = self.runner.invoke(ProjectCommands.remove, [str(second)])

        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert self._registered_roots() == {first.resolve()}

    def test_remove_by_ambiguous_name_fails_with_a_message_rather_than_a_traceback(self):
        first = self._make_project_dir("first_dir", project_name="twin")
        second = self._make_project_dir("second_dir", project_name="twin")
        self._write_master_config([first, second])

        result = self.runner.invoke(ProjectCommands.remove, ["twin"])

        assert result.exit_code != 0
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"Expected a handled CLI error, got: {result.exception!r}"
        )
        assert "twin" in result.output
        assert self._registered_roots() == {first.resolve(), second.resolve()}
