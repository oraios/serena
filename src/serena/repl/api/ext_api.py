# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of access to external projects (projects other than the active one).
"""

from types import TracebackType
from typing import TYPE_CHECKING

from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClientManager
from serena.tools import ListQueryableProjectsTool, QueryProjectTool

from ..external_project import ExternalProjectContext
from ..facade import FacadeApi, facade_method
from ..representable import JsonObject, JsonObjectRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class ExternalProjectContextManager:
    """
    A context manager (for use in a `with` statement) within which the facades operate on an external project
    (read-only): the external project is temporarily activated, and operations requiring language servers are
    executed in the project's server. Contexts cannot be nested.
    """

    def __init__(self, agent: "SerenaAgent", project_name: str) -> None:
        """
        :param agent: the agent
        :param project_name: the name (or root path) of the registered external project
        """
        self._agent = agent
        self._project_name = project_name
        self._active_project_context = None

    def __enter__(self) -> None:
        entrypoint = self._agent.get_repl().entrypoint
        if entrypoint.get_external_project_() is not None:
            raise ValueError("External project contexts cannot be nested")

        # temporarily activate the external project
        registered_project = self._agent.serena_config.get_registered_project(self._project_name)
        if registered_project is None:
            raise ValueError(f"Project '{self._project_name}' is not registered and cannot be queried")
        project = registered_project.get_project_instance(self._agent.serena_config)
        self._active_project_context = self._agent.active_project_context(project)
        self._active_project_context.__enter__()

        # switch the facades to the external project (remote execution of language server operations for the LSP backend)
        remote_execution = self._agent.get_language_backend().is_lsp()
        entrypoint.set_external_project_(ExternalProjectContext(registered_project.project_name, remote_execution))

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        self._agent.get_repl().entrypoint.set_external_project_(None)
        assert self._active_project_context is not None
        self._active_project_context.__exit__(exc_type, exc_value, traceback)


class ExternalProjectsApi(FacadeApi):
    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(agent, name="ext", description="read-only access to external projects (projects other than the active one)")

    @facade_method(corresponding_tool=ListQueryableProjectsTool)
    def list_projects(self, symbol_access: bool = True) -> JsonObject:
        """
        Lists the registered projects which can be queried.

        :param symbol_access: whether to list only projects for which symbol-level access is available
        :return: the project names mapped to their root directories
        """
        registered_projects = self._agent.serena_config.projects
        if symbol_access and self._agent.get_language_backend().is_jetbrains():
            # only projects with open IDE instances can be queried
            matched_clients = JetBrainsPluginClientManager().match_clients(registered_projects)
            relevant_projects = [mc.registered_project for mc in matched_clients]
        else:
            # all projects can be queried (the project server instantiates projects dynamically)
            relevant_projects = registered_projects
        result = {p.project_name: str(p.project_root) for p in relevant_projects}
        return JsonObject(result, JsonObjectRenderer(self._agent, -1))

    @facade_method(corresponding_tool=QueryProjectTool)
    def project_context(self, project_name: str) -> ExternalProjectContextManager:
        """
        Provides a context (for use in a `with` statement) within which all facades operate on the given external
        project instead of the active one, with read-only access: e.g.
        `with s.ext.project_context("other"): result = s.lsp.find_symbol("Foo")`.
        Results obtained within the context can be used after it (they are self-contained).

        :param project_name: the name (or root path) of the project, as listed by `list_projects`
        :return: the context manager
        """
        return ExternalProjectContextManager(self._agent, project_name)
