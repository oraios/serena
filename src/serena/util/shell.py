import os
import platform
import subprocess
from typing import Any

from pydantic import BaseModel

# Import CREATE_NO_WINDOW safely across platforms
try:
    from subprocess import CREATE_NO_WINDOW
except ImportError:
    # Not available on non-Windows systems
    CREATE_NO_WINDOW = 0x08000000


class ShellCommandResult(BaseModel):
    stdout: str
    return_code: int
    cwd: str
    stderr: str | None = None


def execute_shell_command(command: str, cwd: str | None = None, capture_stderr: bool = False) -> ShellCommandResult:
    """
    Execute a shell command and return the output.

    :param command: The command to execute.
    :param cwd: The working directory to execute the command in. If None, the current working directory will be used.
    :param capture_stderr: Whether to capture the stderr output.
    :return: The output of the command.
    """
    if cwd is None:
        cwd = os.getcwd()

    is_windows = platform.system() == "Windows"

    # Platform-specific kwargs for window suppression
    platform_kwargs: dict[str, Any] = {}
    if is_windows:
        platform_kwargs["creationflags"] = CREATE_NO_WINDOW
    else:
        # On Unix-like systems, start new session to detach from terminal
        platform_kwargs["start_new_session"] = True

    process = subprocess.Popen(
        command,
        shell=not is_windows,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        **platform_kwargs,
    )

    stdout, stderr = process.communicate()
    return ShellCommandResult(stdout=stdout, stderr=stderr, return_code=process.returncode, cwd=cwd)


def subprocess_check_output(args: list[str], encoding: str = "utf-8", strip: bool = True, timeout: float | None = None) -> str:
    # Platform-specific kwargs for window suppression
    platform_kwargs: dict[str, Any] = {}
    if platform.system() == "Windows":
        platform_kwargs["creationflags"] = CREATE_NO_WINDOW
    else:
        # On Unix-like systems, start new session to detach from terminal
        platform_kwargs["start_new_session"] = True

    output = subprocess.check_output(
        args,
        stdin=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=os.environ.copy(),
        **platform_kwargs,
    ).decode(encoding)
    if strip:
        output = output.strip()
    return output
