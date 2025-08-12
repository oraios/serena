"""
Tools supporting the execution of (external) commands
"""

import shlex
import shutil

from serena.tools import TOOL_DEFAULT_MAX_ANSWER_LENGTH, Tool, ToolMarkerCanEdit
from serena.util.shell import execute_shell_command


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit):
    """
    Executes a shell command.
    """

    def apply(
        self,
        command: str,
        cwd: str | None = None,
        capture_stderr: bool = True,
        max_answer_chars: int = TOOL_DEFAULT_MAX_ANSWER_LENGTH,
        timeout: float | None = None,
        preflight: bool = True,
        preflight_cmds: list[str] | None = None,
    ) -> str:
        """
        Execute a shell command and return its output. If there is a memory about suggested commands, read that first.
        Never execute unsafe shell commands like `rm -rf /` or similar!

        :param command: the shell command to execute
        :param cwd: the working directory to execute the command in. If None, the project root will be used.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        _cwd = cwd or self.get_project_root()

        # Lightweight, generic preflight (tool-agnostic)
        # 1) Ensure the target binary exists in PATH
        if preflight:
            try:
                parts = shlex.split(command)
                exe = parts[0] if parts else None
            except Exception:
                exe = None
            if exe and shutil.which(exe) is None:
                return self._limit_length(
                    '{"error":"executable not found in PATH","exe":"' + exe + '","hint":"Install it or adjust PATH"}',
                    max_answer_chars,
                )
            # 2) Optional caller-provided preflight checks (fast, tool-agnostic)
            if preflight_cmds:
                for check in preflight_cmds:
                    probe = execute_shell_command(check, cwd=_cwd, capture_stderr=True, timeout=5)
                    if probe.return_code != 0:
                        import json as _json

                        payload = {
                            "error": "preflight check failed",
                            "check": check,
                            "summary": {
                                "exit_code": probe.return_code,
                                "stderr_tail": (probe.stderr or "")[-512:],
                                "stdout_tail": (probe.stdout or "")[-512:],
                                "cwd": probe.cwd,
                            },
                        }
                        return self._limit_length(_json.dumps(payload), max_answer_chars)

        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr, timeout=timeout)
        payload = result.model_dump()  # dict

        # Add a concise summary for non-zero exit or timeout to improve downstream logs
        if result.return_code != 0:
            stderr_tail = (result.stderr or "")[-1024:]
            stdout_tail = (result.stdout or "")[-1024:]
            summary = {
                "summary": {
                    "exit_code": result.return_code,
                    "stderr_tail": stderr_tail,
                    "stdout_tail": stdout_tail,
                    "cwd": result.cwd,
                }
            }
            try:
                payload.update(summary)
            except Exception:
                pass

        import json

        return self._limit_length(json.dumps(payload), max_answer_chars)
