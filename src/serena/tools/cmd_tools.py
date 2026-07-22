"""
Tools supporting the execution of (external) commands
"""

import os.path
from pathlib import Path

from serena.tools import Tool, ToolMarkerCanEdit, ToolMarkerOptional
from serena.util.shell import execute_shell_command


def resolve_cwd_within_project(cwd: str | None, project_root: str) -> str:
    """
    Resolves a requested working directory to an absolute path confined to the project root.

    This is a best-effort ergonomic guard that keeps *accidental* relative-path operations inside the
    project tree; it is NOT a security boundary. A shell command executed with ``shell=True`` can still
    reference or navigate to any path regardless of its working directory. The primary control against
    arbitrary shell execution is that the shell tool is optional (disabled by default).

    :param cwd: the requested working directory; if None or ".", the project root is used. A relative
        path is resolved against the project root; an absolute path is used as given.
    :param project_root: the absolute path of the active project's root directory.
    :return: the resolved absolute working directory (symlinks resolved).
    :raises ValueError: if the resolved directory is neither the project root nor a descendant of it.
    """
    # resolve the requested directory against the project root (symlinks included)
    root = Path(project_root).resolve()
    if cwd is None:
        return str(root)
    requested = Path(cwd)
    resolved = requested.resolve() if requested.is_absolute() else (root / requested).resolve()

    # confine to the project root using component-aware containment (not string prefixing)
    if resolved != root and not resolved.is_relative_to(root):
        raise ValueError(f"The requested working directory ({cwd}) resolves outside the project root ({root}): {resolved}")

    return str(resolved)


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit, ToolMarkerOptional):
    """
    Executes a shell command.

    This tool is optional (disabled by default) and must be explicitly enabled via
    `included_optional_tools` in the project/context/mode configuration, since arbitrary
    shell execution is a security-sensitive capability.
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
            The resolved directory is confined to the project root (paths resolving outside it are rejected)
            and must already exist; a command that intends to create and enter its own working directory must
            therefore create it as part of the command (e.g. ``mkdir -p sub``) rather than pass it as ``cwd``.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. -1 means using the default value, don't adjust unless there is no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        # confine the working directory to the project root (raises before any execution if it escapes)
        _cwd = resolve_cwd_within_project(cwd, self.get_project_root())
        if not os.path.isdir(_cwd):
            raise FileNotFoundError(f"Specified working directory ({cwd}) does not resolve to an existing directory: {_cwd}")

        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        result = result.model_dump_json()
        return self._limit_length(result, max_answer_chars)
