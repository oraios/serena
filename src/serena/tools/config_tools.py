# SPDX-License-Identifier: GPL-3.0-or-later

from typing import TYPE_CHECKING, cast

from sensai.util.helper import mark_used

from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional

if TYPE_CHECKING:
    from serena.repl.api.cfg_api import ConfigApi


class ConfigApiMixin:
    """
    Mixin for tools which delegate to the configuration API.
    The API is imported locally, since the API module refers to the tools (as corresponding tools).
    """

    def _api(self) -> "ConfigApi":
        from serena.repl.api.cfg_api import ConfigApi

        tool = cast(Tool, cast(object, self))
        return ConfigApi(tool.agent)


class OpenDashboardTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject, ConfigApiMixin):
    """
    Opens the Serena web dashboard in the default web browser.
    The dashboard provides logs, session information, and tool usage statistics.
    """

    def apply(self) -> str:
        """
        Opens the Serena web dashboard in the default web browser.
        """
        return self._api().open_dashboard()


class ActivateProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Activates a project based on the project name or path.
    """

    def apply(self, project: str, session_id: str) -> str:
        """
        Activates the project with the given name or path.

        :param project: the name of a registered project to activate or a path to a project directory
        :param session_id: your Serena session id, as provided in Serena's instructions (call `initial_instructions` if you do not have one)
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


class GetCurrentConfigTool(Tool, ConfigApiMixin):
    """
    Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
    """

    def apply(self) -> str:
        """
        Print the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
        """
        return self._api().get_current_config()
