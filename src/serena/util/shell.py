import os
import platform
import subprocess
from subprocess import TimeoutExpired

from pydantic import BaseModel

from solidlsp.util.subprocess_util import subprocess_kwargs


class ShellCommandResult(BaseModel):
    stdout: str
    return_code: int
    cwd: str
    stderr: str | None = None


def execute_shell_command(
    command: str,
    cwd: str | None = None,
    capture_stderr: bool = False,
    timeout: float | None = None,
) -> ShellCommandResult:
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
    process = subprocess.Popen(
        command,
        shell=not is_windows,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else None,
        creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0,  # type: ignore
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        **subprocess_kwargs(),
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return ShellCommandResult(stdout=stdout, stderr=stderr, return_code=process.returncode, cwd=cwd)
    except TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass
        # Try to collect whatever output is available to aid debugging
        try:
            out_tail = (process.stdout.read() if process.stdout else "") or ""  # type: ignore
        except Exception:
            out_tail = ""
        try:
            err_tail = (process.stderr.read() if process.stderr else "") or ""  # type: ignore
        except Exception:
            err_tail = ""
        # Use a conventional timeout-like code (124) to signal timeout
        return ShellCommandResult(stdout=out_tail, stderr=err_tail, return_code=124, cwd=cwd)


def subprocess_check_output(args: list[str], encoding: str = "utf-8", strip: bool = True, timeout: float | None = None) -> str:
    output = subprocess.check_output(args, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=timeout, env=os.environ.copy(), **subprocess_kwargs()).decode(encoding)  # type: ignore
    if strip:
        output = output.strip()
    return output
