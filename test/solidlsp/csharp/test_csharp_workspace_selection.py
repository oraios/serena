from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from solidlsp.language_servers.csharp_language_server import CSharpLanguageServer, resolve_selected_workspace_entry
from solidlsp.settings import SolidLSPSettings


@dataclass
class CSharpWorkspaceFixture:
    repository_root: Path
    main_solution: Path
    secondary_solutionx: Path
    standalone_project: Path
    stray_project: Path

    def relative_path(self, path: Path) -> str:
        return path.relative_to(self.repository_root).as_posix()


@dataclass
class CSharpFallbackFixture:
    repository_root: Path
    fallback_solution: Path
    stray_project: Path


def _make_csharp_language_server_stub(repository_root: Path, active_workspace: str | None = None) -> CSharpLanguageServer:
    server = object.__new__(CSharpLanguageServer)
    server.repository_root_path = str(repository_root)
    settings = {}
    if active_workspace is not None:
        settings["active_workspace"] = active_workspace
    server._custom_settings = SolidLSPSettings.CustomLSSettings(settings)
    server.server = Mock()
    server.server.notify = Mock()
    server.server.notify.send_notification = Mock()
    return server


def _create_workspace_fixture(tmp_path: Path) -> CSharpWorkspaceFixture:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    main_solution = repository_root / "workspaces" / "Main" / "Main.sln"
    main_solution.parent.mkdir(parents=True)
    main_solution.touch()

    secondary_solutionx = repository_root / "workspaces" / "Secondary" / "Secondary.slnx"
    secondary_solutionx.parent.mkdir(parents=True)
    secondary_solutionx.touch()

    standalone_project = repository_root / "apps" / "Standalone" / "Standalone.csproj"
    standalone_project.parent.mkdir(parents=True)
    standalone_project.touch()

    stray_project = repository_root / "StrayRoot.csproj"
    stray_project.touch()

    return CSharpWorkspaceFixture(
        repository_root=repository_root,
        main_solution=main_solution,
        secondary_solutionx=secondary_solutionx,
        standalone_project=standalone_project,
        stray_project=stray_project,
    )


def _create_fallback_fixture(tmp_path: Path) -> CSharpFallbackFixture:
    repository_root = tmp_path / "repo"
    repository_root.mkdir()

    fallback_solution = repository_root / "workspace" / "Fallback" / "Fallback.sln"
    fallback_solution.parent.mkdir(parents=True)
    fallback_solution.touch()

    stray_project = repository_root / "StrayRoot.csproj"
    stray_project.touch()

    return CSharpFallbackFixture(
        repository_root=repository_root,
        fallback_solution=fallback_solution,
        stray_project=stray_project,
    )


@pytest.mark.csharp
class TestCSharpWorkspaceSelection:
    def test_resolve_selected_workspace_entry_supports_slnx(self, tmp_path: Path) -> None:
        fixture = _create_workspace_fixture(tmp_path)

        workspace_entry = resolve_selected_workspace_entry(
            str(fixture.repository_root),
            fixture.relative_path(fixture.secondary_solutionx),
        )

        assert workspace_entry is not None
        assert workspace_entry.kind == "solution"
        assert workspace_entry.path == str(fixture.secondary_solutionx)
        assert workspace_entry.workspace_root == str(fixture.secondary_solutionx.parent)

    def test_get_initialize_params_uses_selected_project_root(self, tmp_path: Path) -> None:
        fixture = _create_workspace_fixture(tmp_path)
        language_server = _make_csharp_language_server_stub(
            fixture.repository_root,
            fixture.relative_path(fixture.standalone_project),
        )

        initialize_params = language_server._get_initialize_params()

        expected_root = str(fixture.standalone_project.parent)
        expected_uri = fixture.standalone_project.parent.as_uri()
        assert initialize_params["rootPath"] == expected_root
        assert initialize_params["rootUri"] == expected_uri
        assert initialize_params["workspaceFolders"] == [{"uri": expected_uri, "name": "Standalone"}]

    def test_open_solution_and_projects_uses_selected_solution_only(self, tmp_path: Path) -> None:
        fixture = _create_workspace_fixture(tmp_path)
        language_server = _make_csharp_language_server_stub(
            fixture.repository_root,
            fixture.relative_path(fixture.main_solution),
        )

        language_server._open_solution_and_projects()

        language_server.server.notify.send_notification.assert_called_once_with(
            "solution/open",
            {"solution": fixture.main_solution.as_uri()},
        )

    def test_open_solution_and_projects_uses_selected_solutionx_only(self, tmp_path: Path) -> None:
        fixture = _create_workspace_fixture(tmp_path)
        language_server = _make_csharp_language_server_stub(
            fixture.repository_root,
            fixture.relative_path(fixture.secondary_solutionx),
        )

        language_server._open_solution_and_projects()

        language_server.server.notify.send_notification.assert_called_once_with(
            "solution/open",
            {"solution": fixture.secondary_solutionx.as_uri()},
        )

    def test_open_solution_and_projects_uses_selected_project_only(self, tmp_path: Path) -> None:
        fixture = _create_workspace_fixture(tmp_path)
        language_server = _make_csharp_language_server_stub(
            fixture.repository_root,
            fixture.relative_path(fixture.standalone_project),
        )

        language_server._open_solution_and_projects()

        language_server.server.notify.send_notification.assert_called_once_with(
            "project/open",
            {"projects": [fixture.standalone_project.as_uri()]},
        )

    def test_open_solution_and_projects_falls_back_when_selected_workspace_is_stale(self, tmp_path: Path) -> None:
        fixture = _create_fallback_fixture(tmp_path)
        language_server = _make_csharp_language_server_stub(
            fixture.repository_root,
            "workspace/Missing/Missing.sln",
        )

        language_server._open_solution_and_projects()

        assert language_server.server.notify.send_notification.mock_calls == [
            call("solution/open", {"solution": fixture.fallback_solution.as_uri()}),
            call("project/open", {"projects": [fixture.stray_project.as_uri()]}),
        ]
