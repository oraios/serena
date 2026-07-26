import logging
import os
import platform
import queue
import signal
import subprocess
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import oslex
import psutil

if TYPE_CHECKING:
    import ctypes

    from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

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


def subprocess_run(
    cmd: list[str] | str, timeout: int | None = None, check: bool = False, capture_output: bool = True, text: bool = True, **kwargs
) -> subprocess.CompletedProcess:
    """
    Runs a command in a subprocess, applying safe default settings.

    The stdin of the subprocess is set to DEVNULL to avoid interference with the parent process' stdin;
    this cannot be overridden by passing a different value for stdin in kwargs.

    :param cmd: the command to run, specified as a list of arguments or a string
    :param timeout: the timeout in seconds for the command to complete; if None, no timeout is applied
    :param check: if True, raises CalledProcessError if the command exits with a non-zero status
    :param capture_output: if True, captures stdout and stderr; otherwise, they are not captured
    :param text: if True, captures output as text (str); otherwise, captures as bytes
    :return: a CompletedProcess instance containing information about the completed process
    """
    kwargs = dict(kwargs)
    kwargs.update(subprocess_kwargs())
    kwargs.update(
        {
            "timeout": timeout,
            "capture_output": capture_output,
            "text": text,
            "stdin": subprocess.DEVNULL,  # important to avoid interference with parent process' stdin
        }
    )
    return subprocess.run(cmd, check=check, **kwargs)


def convert_shell_cmd(cmd: str | list[str]) -> str:
    """
    Converts a command (specified as a list or string) to a format supported by subprocess calls with shell=True on the current platform,
    applying necessary escaping and quoting if the command is specified as a list of arguments.

    :param cmd: the command to convert, specified as a list of arguments
    :return: a suitable representation of the command for subprocess calls on the current platform
    """
    return oslex.join(cmd) if isinstance(cmd, list) else cmd


class LanguageServerSubprocessLauncher:
    """
    Launcher for language server subprocesses, which are started for stdio-based communication.
    It is home to the concern of launching a subprocess with well-defined lifecycle properties,
    ensuring, in particular, that a launched subprocess cannot outlive this process (insofar as
    the platform allows) -- even if the subprocess is started in its own session (see
    :meth:`launch`) and this process is terminated forcefully without the opportunity to perform
    cleanup (e.g. SIGKILL).

    The class is a singleton, as it is (potentially) home to a persistent worker thread.
    """

    _PR_SET_PDEATHSIG = 1
    """the PR_SET_PDEATHSIG option value for prctl(2)"""

    _instance: "LanguageServerSubprocessLauncher | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._libc = self._load_libc()
        self._spawner: "LanguageServerSubprocessLauncher._PDeathSigSpawner | None" = None
        self._spawner_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "LanguageServerSubprocessLauncher":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def _load_libc() -> "ctypes.CDLL | None":
        """
        Loads libc if on Linux, where it is needed for pdeathsig protection.
        """
        if platform.system() != "Linux":
            return None
        import ctypes

        try:
            # resolve libc, passing None to resolve symbols from the current process image (which is linked against libc on any Linux)
            return ctypes.CDLL(None)
        except OSError as e:
            log.warning(
                "Could not load libc (%s); language server processes will not be protected against "
                "orphaning if this process is killed without a chance to shut down cleanly",
                e,
            )
            return None

    def _set_pdeathsig_on_parent_exit(self) -> None:
        """
        preexec_fn for subprocess.Popen (no-op if libc is unavailable), which asks the kernel, via
        prctl(PR_SET_PDEATHSIG), to send this process SIGTERM when its parent dies for any reason,
        including SIGKILL.
        """
        if self._libc is not None:
            self._libc.prctl(self._PR_SET_PDEATHSIG, signal.SIGTERM)

    def launch(self, process_launch_info: "ProcessLaunchInfo", start_new_session: bool) -> subprocess.Popen[bytes]:
        """
        Launches a language server process from ``process_launch_info``.

        :param process_launch_info: the command, environment and working directory to launch with
        :param start_new_session: whether to start the process in its own session (own process
            group, detached from ours)
        """
        # build the child environment from ours, overridden by the launch info's entries
        child_proc_env = os.environ.copy()
        child_proc_env.update(process_launch_info.env)

        # convert the command for shell=True execution, prefixing `exec` when pdeathsig applies
        use_pdeathsig = start_new_session and self._libc is not None
        cmd = convert_shell_cmd(process_launch_info.cmd)
        if use_pdeathsig:
            # `exec` makes the shell replace its own process image with the program (execve)
            # instead of forking it as a child, so the PID -- and therefore the PR_SET_PDEATHSIG
            # registration below, which execve preserves -- carries through to the actual language
            # server process rather than protecting only the intermediate shell
            cmd = f"exec {cmd}"

        # assemble platform kwargs and lifecycle settings
        kwargs: dict[str, Any] = subprocess_kwargs()
        kwargs["start_new_session"] = start_new_session
        if use_pdeathsig:
            kwargs["preexec_fn"] = self._set_pdeathsig_on_parent_exit

        def do_popen() -> subprocess.Popen[bytes]:
            return cast(
                "subprocess.Popen[bytes]",
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=child_proc_env,
                    cwd=process_launch_info.cwd,
                    shell=True,
                    **kwargs,
                ),
            )

        # perform the actual Popen call, funneling the fork() through the dedicated spawner thread
        # when pdeathsig applies
        if not use_pdeathsig:
            return do_popen()
        else:
            with self._spawner_lock:
                if self._spawner is None:
                    self._spawner = self._PDeathSigSpawner()
                spawner = self._spawner
            return spawner.spawn(do_popen)

    class _PDeathSigSpawner:
        """
        Runs subprocess.Popen() calls that register PR_SET_PDEATHSIG on one dedicated, permanently
        running daemon thread, so the "parent thread" the kernel ties the registration to is one
        that has the same lifetime as the process
        """

        def __init__(self) -> None:
            self._queue: queue.Queue[tuple[Callable[[], subprocess.Popen], "queue.Queue"]] = queue.Queue()
            self._thread = threading.Thread(target=self._run, name="solidlsp-pdeathsig-spawner", daemon=True)
            self._thread.start()

        def _run(self) -> None:
            while True:
                func, result_queue = self._queue.get()
                try:
                    result_queue.put((None, func()))
                except BaseException as e:
                    result_queue.put((e, None))

        def spawn(self, func: Callable[[], subprocess.Popen]) -> subprocess.Popen:
            result_queue: queue.Queue = queue.Queue(maxsize=1)
            self._queue.put((func, result_queue))
            error, process = result_queue.get()
            if error is not None:
                raise error
            return process


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
