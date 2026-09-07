"""
Tools supporting the execution of (external) commands
"""
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import TYPE_CHECKING, cast

from serena.tools import Tool, ToolMarkerCanEdit

if TYPE_CHECKING:
    from serena.repl.api.shell_api import ShellApi


class ShellApiMixin:
    """
    Mixin for tools which delegate to the shell API.
    The API is imported locally, since the API module refers to the tools (as corresponding tools).
    """

    def _api(self) -> "ShellApi":
        from serena.repl.api.shell_api import ShellApi

        tool = cast(Tool, cast(object, self))
        return ShellApi(tool.agent)


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit, ShellApiMixin):
    """
    Executes a shell command.
    """

    def apply(
        self,
        command: str,
        cwd: str | None = None,
        capture_stderr: bool = True,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Execute a shell command and return its output. If there is a memory about suggested commands, read that first.
        Never execute unsafe shell commands!
        IMPORTANT: Do not use this tool to start
          * long-running processes (e.g. servers) that are not intended to terminate quickly,
          * processes that require user interaction.

        :param command: the shell command to execute
        :param cwd: the working directory to execute the command in. If None, the project root will be used.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. -1 means using the default value, don't adjust unless there is no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        return self._api().execute_shell_command(command, cwd, capture_stderr, max_answer_chars).represent()
