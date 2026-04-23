import json

from serena.config.serena_config import LanguageBackend
from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClientManager
from serena.project_server import ProjectServerClient
from serena.tools import Tool, ToolMarkerDoesNotRequireActiveProject, ToolMarkerOptional


class ListQueryableProjectsTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject):
    """
    Tool for listing all projects that can be queried by the QueryProjectTool.
    """

    def apply(self, symbol_access: bool = True) -> str:
        """
        Lists available projects that can be queried with `query_project_tool`.

        :param symbol_access: whether to return only projects for which symbol access is available. Default: true
        :return: project names and roots
        """
        # determine relevant projects
        registered_projects = self.agent.serena_config.projects
        if symbol_access:
            backend = self.agent.get_language_backend()
            if backend.is_jetbrains():
                # projects with open IDE instances can be queried
                matched_clients = JetBrainsPluginClientManager().match_clients(registered_projects)
                relevant_projects = [mc.registered_project for mc in matched_clients]
            else:
                # all projects can be queried via ProjectServer (which instantiates projects dynamically)
                relevant_projects = registered_projects
        else:
            relevant_projects = registered_projects

        # return project names and roots
        result = {p.project_name: str(p.project_root) for p in relevant_projects}
        return self._to_json(result)


class QueryProjectTool(Tool, ToolMarkerOptional, ToolMarkerDoesNotRequireActiveProject):
    """
    Tool for querying external project information (i.e. information from projects other than the current one),
    by executing a read-only tool.
    """

    def apply(self, project_name: str, tool_name: str, tool_params_json: str) -> str:
        """
        Queries a project by executing a read-only Serena tool. The tool will be executed in the context of the project.
        Use this to query information from projects other than the activated project.

        :param project_name: the name of the project to query (or root path)
        :param tool_name: the name of the tool to execute in the other project. The tool must be read-only.
        :param tool_params_json: the parameters to pass to the tool, encoded as a JSON string
        """
        tool = self.agent.get_tool_by_name(tool_name)
        assert tool.is_active(), f"Tool {tool_name} is not active."
        assert tool.is_readonly(), f"Tool {tool_name} is not read-only and cannot be executed in another project."
        if self._is_project_server_required(tool):
            client = ProjectServerClient()
            return client.query_project(project_name, tool_name, tool_params_json)
        else:
            registered_project = self.agent.serena_config.get_registered_project(project_name)
            assert registered_project is not None, f"Project {project_name} is not registered and cannot be queried."
            project = registered_project.get_project_instance(self.agent.serena_config)
            with tool.agent.active_project_context(project):
                return tool.apply(**json.loads(tool_params_json))  # type: ignore

    def _is_project_server_required(self, tool: Tool) -> bool:
        match self.agent.get_language_backend():
            case LanguageBackend.JETBRAINS:
                return False
            case LanguageBackend.LSP:
                # Note: As long as only read-only tools are considered, only symbolic tools require the project server.
                #   But if we were to allow non-read-only tools, then tools using a CodeEditor also indirectly require language servers.
                assert tool.is_readonly()
                return tool.is_symbolic()
            case _:
                raise NotImplementedError
