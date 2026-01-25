from murena.config.context_mode import MurenaAgentMode
from murena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional


class OpenDashboardTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject):
    """
    Opens the Murena web dashboard in the default web browser.
    The dashboard provides logs, session information, and tool usage statistics.
    """

    def apply(self) -> str:
        """
        Opens the Murena web dashboard in the default web browser.
        """
        if self.agent.open_dashboard():
            return f"Murena web dashboard has been opened in the user's default web browser: {self.agent.get_dashboard_url()}"
        else:
            return f"Murena web dashboard could not be opened automatically; tell the user to open it via {self.agent.get_dashboard_url()}"


class ActivateProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Activates a project based on the project name or path.
    """

    def apply(self, project: str) -> str:
        """
        Activates the project with the given name or path.

        :param project: the name of a registered project to activate or a path to a project directory
        """
        active_project = self.agent.activate_project_from_path_or_name(project)
        result = active_project.get_activation_message()
        result += "\nIMPORTANT: If you have not yet read the 'Murena Instructions Manual', do it now before continuing!"
        return result


class RemoveProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Removes a project from the Murena configuration.
    """

    def apply(self, project_name: str) -> str:
        """
        Removes a project from the Murena configuration.

        :param project_name: Name of the project to remove
        """
        self.agent.murena_config.remove_project(project_name)
        return f"Successfully removed project '{project_name}' from configuration."


class SwitchModesTool(Tool, ToolMarkerOptional):
    """
    Activates modes by providing a list of their names
    """

    def apply(self, modes: list[str]) -> str:
        """
        Activates the desired modes, like ["editing", "interactive"] or ["planning", "one-shot"]

        :param modes: the names of the modes to activate
        """
        mode_instances = [MurenaAgentMode.load(mode) for mode in modes]
        self.agent.set_modes(mode_instances)

        # Inform the Agent about the activated modes and the currently active tools
        result_str = f"Successfully activated modes: {', '.join([mode.name for mode in mode_instances])}" + "\n"
        result_str += "\n".join([mode_instance.prompt for mode_instance in mode_instances]) + "\n"
        result_str += f"Currently active tools: {', '.join(self.agent.get_active_tool_names())}"
        return result_str


class GetCurrentConfigTool(Tool):
    """
    Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
    """

    def apply(self) -> str:
        """
        Print the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
        """
        return self.agent.get_current_config_overview()
