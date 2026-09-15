"""
Tools supporting the execution of (external) commands
"""
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path

from serena.tools import Tool, ToolMarkerCanEdit
from serena.util.shell import execute_shell_command

TOOL_TIMEOUT_MARGIN = 5.0
"""
seconds by which a shell command's timeout undercuts the configured tool timeout, so that the command's
process tree is terminated and reported as such before the tool call itself times out
"""


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit):
    """
    Executes a shell command.
    """

    def _get_command_timeout(self) -> float | None:
        """
        :return: the timeout to apply to the command itself, derived from the configured tool timeout
            (analogously to the language server timeout in :meth:`Project.create_language_server_manager`),
            or None if tool calls are not subject to a timeout
        """
        tool_timeout = self.agent.serena_config.tool_timeout
        if tool_timeout is None or tool_timeout < 0:
            return None
        # the fixed margin is not applicable to timeouts that are smaller than it; falling back to half the
        # tool timeout keeps the command's deadline strictly below the tool's one for any configured value
        return max(tool_timeout - TOOL_TIMEOUT_MARGIN, tool_timeout / 2)

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
        if cwd is None:
            _cwd = self.get_project_root()
        else:
            if os.path.isabs(cwd):
                _cwd = cwd
            else:
                _cwd = os.path.join(self.get_project_root(), cwd)
                if not os.path.isdir(_cwd):
                    raise FileNotFoundError(
                        f"Specified a relative working directory ({cwd}), but the resulting path is not a directory: {_cwd}"
                    )

        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr, timeout=self._get_command_timeout())
        result = result.model_dump_json()
        return self._limit_length(result, max_answer_chars)
