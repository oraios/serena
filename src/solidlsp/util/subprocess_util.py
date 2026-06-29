import logging
import platform
import subprocess

import oslex
import psutil

log = logging.getLogger(__name__)


def subprocess_kwargs() -> dict:
    """
    Returns a dictionary of keyword arguments for subprocess calls, adding platform-specific
    flags that we want to use consistently.
    """
    kwargs = {}
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def convert_shell_cmd(cmd: str | list[str]) -> str:
    """
    Converts a command (specified as a list or string) to a format supported by subprocess calls with shell=True on the current platform,
    applying necessary escaping and quoting if the command is specified as a list of arguments.

    :param cmd: the command to convert, specified as a list of arguments
    :return: a suitable representation of the command for subprocess calls on the current platform
    """
    if isinstance(cmd, list):
        return oslex.join(cmd)
    else:
        return cmd


def _signal_process_tree(process: subprocess.Popen[bytes], terminate: bool = True) -> None:
    """
    Sends a signal (terminate or kill) to the given process and all its children.

    :param terminate: if True, signal terminate, otherwise signal kill
    """

    def signal_process(p: subprocess.Popen | psutil.Process) -> None:
        try:
            if terminate:
                p.terminate()
            else:
                p.kill()
        except:
            pass

    # Try to get the parent process
    parent = None
    try:
        parent = psutil.Process(process.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        pass

    # If we have the parent process and it's running, signal the entire tree
    if parent and parent.is_running():
        for child in parent.children(recursive=True):
            signal_process(child)
        signal_process(parent)
    # Otherwise, fall back to direct process signaling
    else:
        signal_process(process)


def terminate_process_tree_with_kill_fallback(process: subprocess.Popen, terminate_timeout: float, process_name: str = "Process") -> None:
    """
    Attempts to terminate the given process and its children by signaling them to terminate,
    and if that fails (i.e. they don't exit within the given timeout), forcefully kills them.

    The termination is logged.

    :param process: the process to terminate
    :param terminate_timeout: the time to wait for the process to terminate gracefully before killing it
    :param process_name: the name of the process (used for logging purposes); should start with capital letter
    """
    log.debug(f"Terminating process {process.pid}, current status: {process.poll()}")
    _signal_process_tree(process, terminate=True)
    try:
        log.debug(f"Waiting for process {process.pid} to terminate...")
        exit_code = process.wait(timeout=terminate_timeout)
        log.info(f"{process_name} terminated successfully with exit code {exit_code}.")
    except subprocess.TimeoutExpired:
        # If termination failed, forcefully kill the process
        log.warning(f"{process_name} (pid={process.pid}) termination timed out, killing process forcefully...")
        _signal_process_tree(process, terminate=False)
        try:
            exit_code = process.wait(timeout=2.0)
            log.info(f"{process_name} killed successfully with exit code {exit_code}.")
        except subprocess.TimeoutExpired:
            log.error(f"{process_name} (pid={process.pid}) could not be killed within timeout.")
    except Exception as e:
        log.error(f"Error during process shutdown: {e}")
