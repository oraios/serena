# SPDX-License-Identifier: GPL-3.0-or-later
"""
Execution of facade methods in the context of an external project (i.e. a project other than the active one).
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from serena.project_server import ProjectServerClient


class ExternalProjectContext:
    """
    The context in which facade methods are executed while an external project is being queried:
    methods which use the project server (see `FacadeMethodInfo.uses_project_server`) are executed remotely
    in the project server (if remote execution applies to the language backend), all other methods are executed
    locally against the temporarily switched project. Editing methods are not permitted.
    """

    def __init__(self, project_name: str, remote_execution: bool) -> None:
        """
        :param project_name: the name of the external project
        :param remote_execution: whether methods using the project server are to be executed remotely
            (False for the JetBrains backend, where the IDE serves all projects)
        """
        self.project_name = project_name
        self._remote_execution = remote_execution
        self._client: ProjectServerClient | None = None

    def executes_remotely(self, uses_project_server: bool) -> bool:
        """
        :param uses_project_server: whether the method in question uses the project server
        :return: whether the method is to be executed remotely
        """
        return self._remote_execution and uses_project_server

    def call(self, facade_name: str, method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """
        Executes the given facade method in the external project's server.

        :param facade_name: the facade's name
        :param method_name: the method's name
        :param args: the positional arguments (must be JSON-serialisable)
        :param kwargs: the keyword arguments (must be JSON-serialisable)
        :return: the method's result (unpickled)
        """
        if self._client is None:
            from serena.project_server import ProjectServerClient

            self._client = ProjectServerClient()
        return self._client.call_facade_method(self.project_name, facade_name, method_name, list(args), kwargs)
