import json
from pathlib import Path

import pytest

from serena.config.serena_config import ProjectConfig
from serena.project import Project
from serena.tools.config_tools import ListWorkspaceEntriesTool, SetActiveWorkspaceTool
from solidlsp.ls_config import Language
from test.conftest import create_default_serena_config


class StubAgent:
    def __init__(self, project: Project):
        self._project = project
        self.reset_calls = 0

    def get_active_project_or_raise(self) -> Project:
        return self._project

    def reset_language_server_manager(self) -> None:
        self.reset_calls += 1



def _create_csharp_project(tmp_path: Path) -> Project:
    main_dir = tmp_path / "src" / "Main"
    main_dir.mkdir(parents=True)
    (main_dir / "Main.sln").touch()
    (main_dir / "Main.csproj").touch()

    other_dir = tmp_path / "src" / "Other"
    other_dir.mkdir(parents=True)
    (other_dir / "Other.sln").touch()

    serena_config = create_default_serena_config()
    ProjectConfig.autogenerate(tmp_path, serena_config, languages=[Language.CSHARP], save_to_disk=True)
    return Project.load(tmp_path, serena_config)


class TestWorkspaceConfigTools:
    def test_list_workspace_entries_marks_selected_entry(self, tmp_path: Path) -> None:
        project = _create_csharp_project(tmp_path)
        project.project_config.active_workspace = "src/Main/Main.sln"

        entries = json.loads(ListWorkspaceEntriesTool(StubAgent(project)).apply())

        assert {"path": "src/Main/Main.sln", "kind": "solution", "selected": True} in entries
        assert {"path": "src/Main/Main.csproj", "kind": "project", "selected": False} in entries
        assert {"path": "src/Other/Other.sln", "kind": "solution", "selected": False} in entries

    def test_set_active_workspace_persists_to_project_local_and_restarts(self, tmp_path: Path) -> None:
        project = _create_csharp_project(tmp_path)
        agent = StubAgent(project)
        result = SetActiveWorkspaceTool(agent).apply("src/Main/Main.sln")
        reloaded = Project.load(tmp_path, project.serena_config)

        assert project.project_config.active_workspace == "src/Main/Main.sln"
        assert "active_workspace" in project.project_config._local_override_keys
        assert reloaded.project_config.active_workspace == "src/Main/Main.sln"
        assert "active_workspace" in reloaded.project_config._local_override_keys
        assert agent.reset_calls == 1
        assert "src/Main/Main.sln" in result

    def test_set_active_workspace_session_mode_does_not_write_to_disk(self, tmp_path: Path) -> None:
        project = _create_csharp_project(tmp_path)
        agent = StubAgent(project)
        SetActiveWorkspaceTool(agent).apply("src/Main/Main.sln", persist_mode="session", restart=False)
        reloaded = Project.load(tmp_path, project.serena_config)

        assert project.project_config.active_workspace == "src/Main/Main.sln"
        assert reloaded.project_config.active_workspace is None
        assert agent.reset_calls == 0

    def test_set_active_workspace_rejects_path_outside_project_root(self, tmp_path: Path) -> None:
        project = _create_csharp_project(tmp_path)
        outside_dir = tmp_path.parent / f"{tmp_path.name}_outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "Outside.sln"
        outside_file.touch()

        with pytest.raises(ValueError, match="inside the active project root"):
            SetActiveWorkspaceTool(StubAgent(project)).apply(str(outside_file))
