"""
Tools supporting the execution of (external) commands
"""

import os.path
import shlex

from serena.tools import Tool, ToolMarkerCanEdit
from serena.util.shell import safe_execute_shell_command


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit):
    """
    Executes a shell command.
    """

    def _validate_path_containment(self, path: str, base_dir: str):

        real_base_dir = os.path.realpath(base_dir)

        if not os.path.isabs(path):
            path = os.path.join(real_base_dir, path)

        real_path = os.path.realpath(path)
        common_path = os.path.commonpath([real_base_dir, real_path])
        if common_path != real_base_dir:
            raise PermissionError(f"Path traversal attempt blocked. The path '{path}' is outside the allowed directory '{base_dir}'.")

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

        try:
            parts = shlex.split(command)
            for part in parts:
                if "/" in part or part.startswith(".", "-"):
                    potential_path = os.path.join(_cwd, part)
                    if os.path.exists(os.path.dirname(potential_path)):
                        self._validate_path_containment(part, _cwd)

        except PermissionError:
            raise
        except Exception as e:
            return f'{{"error": "Failed to parse or validate command: {e}"}}'

        # If you want Command Chain, Use line 78 instead of 79
        # result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        result = safe_execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)

        result = result.json()
        return self._limit_length(result, max_answer_chars)
