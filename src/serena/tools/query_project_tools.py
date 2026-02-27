import json

from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClientManager
from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional


class ListQueryableProjectsTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Tool for listing all projects that can be queried by the QueryProjectTool.
    """

    def apply(self, symbol_access: bool = True) -> str:
        """
        Lists available projects that can be queried with `query_project_tool`.

        :param symbol_access: whether to return only projects for which symbol access is available. Default: true
        """
        # determine relevant projects
        registered_projects = self.agent.serena_config.projects
        if symbol_access:
            backend = self.agent.get_language_backend()
            if backend.is_jetbrains():
                matched_clients = JetBrainsPluginClientManager().match_clients(registered_projects)
                relevant_projects = [mc.registered_project for mc in matched_clients]
            else:
                raise NotImplementedError(f"External symbol access is generally unavailable for language backend {backend.value}")
        else:
            relevant_projects = registered_projects

        # return project names, excluding the active project (if any)
        project_names = [p.project_name for p in relevant_projects]
        active_project = self.agent.get_active_project()
        if active_project is not None:
            project_names = [n for n in project_names if n != active_project.project_name]
        return self._to_json(project_names)


class QueryProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional):
    """
    Tool for querying external project information (i.e. information from projects other than the current one),
    by executing a read-only tool.
    """

    def apply(self, project_name: str, tool_name: str, tool_params_json: str) -> str:
        """
        Queries a project by executing a read-only Serena tool. The tool will be executed in the context of the project.
        Use this to query information from projects other than the activated project.

        :param project_name: the name of the project to query
        :param tool_name: the name of the tool to execute in the other project. The tool must be read-only.
        :param tool_params_json: the parameters to pass to the tool, encoded as a JSON string
        """
        tool = self.agent.get_tool_by_name(tool_name)
        assert tool.is_active(), f"Tool {tool_name} is not active."
        assert tool.is_readonly(), f"Tool {tool_name} is not read-only and cannot be executed in another project."
        registered_project = self.agent.serena_config.get_registered_project(project_name)
        assert registered_project is not None, f"Project {project_name} is not registered and cannot be queried."
        project = registered_project.get_project_instance(self.agent.serena_config)
        with tool.project_override_context(project):
            return tool.apply(**json.loads(tool_params_json))  # type: ignore
