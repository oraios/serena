# SPDX-License-Identifier: GPL-3.0-or-later
"""
Execution of facade methods in the context of an external project (i.e. a project other than the active one).
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from serena.project_server import ProjectServerClient

    from ..agent import SerenaAgent
    from .facade import FacadeMethod


class ExternalProjectExecution:
    """
    The context in which facade methods are executed while an external project is being queried:
    methods which use the project server (see `FacadeMethodInfo.uses_project_server`) are executed remotely
    in the project server (if remote execution applies to the language backend), all other methods are executed
    locally against the temporarily switched project. Editing methods are not permitted.
    """

    def __init__(self, project_name: str, read_only: bool, agent: "SerenaAgent") -> None:
        """
        :param project_name: the name of the external project
        :param read_only: whether the external project is to be treated as read-only (editing methods are not permitted)
        """
        self.project_name = project_name
        self._client: ProjectServerClient | None = None
        self._read_only = read_only
        self._agent = agent

    def is_called_remotely(self, method: "FacadeMethod") -> bool:
        """
        :param method: the method to check
        :return: whether the given method must be executed remotely
        """
        # Any method that uses the project server must be executed remotely,
        # as does any edit operation when using the LSP backend (as edit operations indirectly
        # use the language server via the CodeEditor abstraction)
        return method.info.uses_project_server or (self._agent.get_language_backend().is_lsp() and method.info.can_edit)

    def check_call_permission(self, method: "FacadeMethod") -> None:
        """
        Checks whether the given method is permitted to be called in the context of this external project execution.
        Raises an exception if the method is not permitted.

        :param method: the facade method to check
        """
        if self._read_only and method.info.can_edit:
            raise PermissionError(f"Editing methods are not permitted in read-only external project execution: {method.qualified_name}")

    def call_remotely(self, facade_name: str, method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """
        Executes the given facade method remotely via the project server.

        :param facade_name: the facade's name
        :param method_name: the method's name
        :param args: the positional arguments (must be JSON-serialisable)
        :param kwargs: the keyword arguments (must be JSON-serialisable)
        :return: the method's result (unpickled)
        """
        if self._client is None:
            from serena.project_server import ProjectServerClient

            self._client = ProjectServerClient(self._agent.serena_config)
        return self._client.call_facade_method(self.project_name, facade_name, method_name, list(args), kwargs)
