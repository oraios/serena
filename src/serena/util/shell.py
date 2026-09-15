# SPDX-License-Identifier: GPL-3.0-or-later

import os
import subprocess

from pydantic import BaseModel

from solidlsp.util.subprocess_util import subprocess_kwargs, terminate_process_tree_with_kill_fallback


class ShellCommandResult(BaseModel):
    stdout: str
    return_code: int
    cwd: str
    stderr: str | None = None


def execute_shell_command(
    command: str, cwd: str | None = None, capture_stderr: bool = False, timeout: float | None = None
) -> ShellCommandResult:
    """
    Execute a shell command and return the output.

    :param command: The command to execute.
    :param cwd: The working directory to execute the command in. If None, the current working directory will be used.
    :param capture_stderr: Whether to capture the stderr output.
    :param timeout: the maximum time to wait for the command to complete, in seconds, or None to wait indefinitely.
        If the command does not complete in time, its process tree is terminated (with a kill fallback) and
        :class:`subprocess.TimeoutExpired` is raised.
    :return: The output of the command.
    """
    if cwd is None:
        cwd = os.getcwd()

    process = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        **subprocess_kwargs(),
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # communicate() does not terminate the process when the timeout expires, so without this the command
        # would keep running - and keep holding the calling thread - for the remaining lifetime of the server
        terminate_process_tree_with_kill_fallback(process, terminate_timeout=5.0, process_name="Shell command")
        raise
    return ShellCommandResult(stdout=stdout, stderr=stderr, return_code=process.returncode, cwd=cwd)


def subprocess_check_output(
    args: list[str], encoding: str = "utf-8", strip: bool = True, timeout: float | None = None, cwd: str | None = None
) -> str:
    output = subprocess.check_output(
        args, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout, env=os.environ.copy(), cwd=cwd, **subprocess_kwargs()
    ).decode(encoding)
    if strip:
        output = output.strip()
    return output
