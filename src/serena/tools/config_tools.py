from sensai.util.helper import mark_used
from pathlib import Path

from solidlsp.language_servers.csharp_language_server import breadth_first_file_scan
from solidlsp.ls_config import Language

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional


class OpenDashboardTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject):
    """
    Opens the Serena web dashboard in the default web browser.
    The dashboard provides logs, session information, and tool usage statistics.
    """

    def apply(self) -> str:
        """
        Opens the Serena web dashboard in the default web browser.
        """
        if self.agent.open_dashboard():
            return f"Serena web dashboard has been opened in the user's default web browser: {self.agent.get_dashboard_url()}"
        else:
            return f"Serena web dashboard could not be opened automatically; tell the user to open it via {self.agent.get_dashboard_url()}"


class ActivateProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Activates a project based on the project name or path.
    """

    # noinspection PyIncorrectDocstring
    # (session_id is injected via apply_ex)
    def apply(self, project: str, session_id: str) -> str:
        """
        Activates the project with the given name or path.

        :param project: the name of a registered project to activate or a path to a project directory
        """
        is_new_activation = self.agent.activate_project_from_path_or_name(project)
        mark_used(is_new_activation)
        result = self.agent.get_project_activation_message(session_id)
        result += "\nIMPORTANT: If you have not yet read the 'Serena Instructions Manual', do it now before continuing!"
        return result


class RemoveProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Removes a project from the Serena configuration.
    """

    def apply(self, project_name: str) -> str:
        """
        Removes a project from the Serena configuration.

        :param project_name: Name of the project to remove
        """
        self.agent.serena_config.remove_project(project_name)
        return f"Successfully removed project '{project_name}' from configuration."


class GetCurrentConfigTool(Tool):
    """
    Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
    """

    def apply(self) -> str:
        """
        Print the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
        """
        return self.agent.get_current_config_overview()



def _project_supports_csharp_workspace_selection(project) -> bool:
    return Language.CSHARP in project.project_config.languages or Language.CSHARP_OMNISHARP in project.project_config.languages



def _iter_csharp_workspace_entries(project_root: str, include_projects: bool) -> list[dict[str, str]]:
    entries = []
    root = Path(project_root).resolve()
    for filename in breadth_first_file_scan(project_root):
        absolute_path = Path(filename).resolve()
        suffix = absolute_path.suffix.lower()
        if suffix in (".sln", ".slnx"):
            kind = "solution"
        elif include_projects and suffix == ".csproj":
            kind = "project"
        else:
            continue

        relative_path = absolute_path.relative_to(root).as_posix()
        entries.append({"path": relative_path, "kind": kind})
    return entries



def _resolve_workspace_path(project_root: str, path: str) -> tuple[str, Path]:
    if not path:
        raise ValueError("Workspace path must not be empty.")

    root = Path(project_root).resolve()
    candidate = Path(path)
    absolute_path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

    try:
        relative_path = absolute_path.relative_to(root).as_posix()
    except ValueError as e:
        raise ValueError(f"Workspace path '{path}' must be inside the active project root {project_root}.") from e

    if not absolute_path.is_file():
        raise ValueError(f"Workspace path '{path}' does not resolve to a file.")

    if absolute_path.suffix.lower() not in (".sln", ".slnx", ".csproj"):
        raise ValueError("Workspace path must point to a .sln, .slnx, or .csproj file.")

    return relative_path, absolute_path


class ListWorkspaceEntriesTool(Tool):
    """
    Lists candidate C# workspace entries under the active project root.
    """

    def apply(self, kind: str = "csharp", include_projects: bool = True) -> str:
        """
        Lists candidate workspace entries for the active project.

        :param kind: workspace kind to list. Currently only 'csharp' is supported.
        :param include_projects: whether to include .csproj files in addition to solutions
        """
        if kind != "csharp":
            raise ValueError("Only kind='csharp' is currently supported.")

        project = self.project
        if not _project_supports_csharp_workspace_selection(project):
            raise ValueError("Workspace selection is currently only supported for C# projects.")

        selected_path = Path(project.project_config.active_workspace).as_posix() if project.project_config.active_workspace else None
        entries = _iter_csharp_workspace_entries(project.project_root, include_projects)
        for entry in entries:
            entry["selected"] = entry["path"] == selected_path  # type: ignore[index]
        return self._to_json(entries)


class SetActiveWorkspaceTool(Tool):
    """
    Sets the active workspace entry for the active project.
    """

    def apply(self, path: str, persist_mode: str = "project_local", restart: bool = True) -> str:
        """
        Sets the active workspace entry for the active project.

        :param path: relative or absolute path to the selected workspace entry
        :param persist_mode: whether to persist to project.local.yml or only change the current session
        :param restart: whether to restart the language server manager after changing the active workspace
        """
        if persist_mode not in ("project_local", "session"):
            raise ValueError("persist_mode must be either 'project_local' or 'session'.")

        project = self.project
        if not _project_supports_csharp_workspace_selection(project):
            raise ValueError("Workspace selection is currently only supported for C# projects.")

        relative_path, absolute_path = _resolve_workspace_path(project.project_root, path)
        project.project_config.active_workspace = relative_path

        if persist_mode == "project_local":
            if "active_workspace" not in project.project_config._local_override_keys:
                project.project_config._local_override_keys.append("active_workspace")
            project.save_config()

        if restart:
            self.agent.reset_language_server_manager()

        suffix = absolute_path.suffix.lower()
        return (
            f"Active workspace set to '{relative_path}' ({suffix}) "
            f"with persist_mode='{persist_mode}' and restart={str(restart).lower()}."
        )
