import logging
import platform
import queue
import signal
import subprocess
import threading
from collections.abc import Callable

import oslex
import psutil

log = logging.getLogger(__name__)

# Resolved once at import time rather than inside the preexec_fn below: preexec_fn runs in the
# forked child before exec(), where only async-signal-safe operations are safe to perform, and an
# import/ctypes.CDLL lookup at that point is not.
_libc = None
if platform.system() == "Linux":
    import ctypes

    _libc = ctypes.CDLL("libc.so.6", use_errno=True)
_PR_SET_PDEATHSIG = 1


def set_pdeathsig_on_parent_exit() -> None:
    """
    preexec_fn for subprocess.Popen (Linux only, no-op elsewhere): asks the kernel to send this
    process SIGTERM if its parent dies for any reason, including SIGKILL, via
    prctl(PR_SET_PDEATHSIG). This is the only mechanism that can free the child when the parent
    is killed rather than exiting gracefully, since a graceful exit is required to run any
    signal-the-tree cleanup code ourselves.

    Only protects the immediate process this is passed to. When launching with shell=True, that
    process is the shell, not the program it runs, so the registration alone will not protect a
    program the shell forks as a child; see convert_shell_cmd's `exec` prefix, which makes the
    shell replace itself with the program instead of forking it, so the same PID (and therefore
    the same PDEATHSIG registration, which execve preserves) carries through.

    Warning this function's caller (popen_preserving_pdeathsig below) exists to guard against: per
    `man 2 prctl`, PR_SET_PDEATHSIG's "parent" is specifically the OS THREAD that called fork() to
    create this process, not the parent process as a whole -- if that thread terminates while the
    rest of the parent process (e.g. its main thread) keeps running, the death signal fires anyway.
    """
    if _libc is not None:
        _libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)


class _PDeathSigSpawner:
    """
    Runs subprocess.Popen() calls that register PR_SET_PDEATHSIG on one dedicated, permanently
    running daemon thread, so the "parent thread" the kernel ties the registration to is never a
    short-lived one.

    Why this exists: StdioLanguageServer._start() (the sole caller of popen_preserving_pdeathsig)
    is very often invoked from a thread that is *intentionally* short-lived. For example,
    LanguageServerManager.from_languages spawns one StartLSThread per language server; each one
    calls language_server.start() (-> ._start(), where Popen() happens) and then simply returns,
    terminating moments after Popen() itself returns. Because PR_SET_PDEATHSIG's delivery is tied
    to that specific calling thread (see the warning on set_pdeathsig_on_parent_exit above), the
    language server would then receive the parent-death signal and exit almost immediately, even
    though Serena's process is still fully alive -- the exact CI-only regression this class fixes.
    Funneling the fork()/exec() itself through one thread that never voluntarily exits (it only
    ever terminates alongside the whole process, which is exactly the case PR_SET_PDEATHSIG is
    meant to detect) decouples "which caller thread happened to invoke _start()" from "does the
    language server survive."
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


class _SpawnerHolder:
    instance: "_PDeathSigSpawner | None" = None


_pdeathsig_spawner_holder = _SpawnerHolder()
_pdeathsig_spawner_lock = threading.Lock()


def popen_preserving_pdeathsig(cmd: str | list[str], **kwargs) -> subprocess.Popen:
    """
    subprocess.Popen wrapper for spawns that pass preexec_fn=set_pdeathsig_on_parent_exit.

    On Linux, delegates the actual Popen() call to a single dedicated daemon thread (see
    _PDeathSigSpawner) instead of performing it on the calling thread directly, so that the
    PR_SET_PDEATHSIG registration set up by the preexec_fn remains tied to a thread that lives as
    long as the process does. On any other platform (or if no preexec_fn is passed), this is
    exactly equivalent to calling subprocess.Popen(cmd, **kwargs) directly.
    """
    if platform.system() != "Linux" or kwargs.get("preexec_fn") is None:
        return subprocess.Popen(cmd, **kwargs)
    with _pdeathsig_spawner_lock:
        if _pdeathsig_spawner_holder.instance is None:
            _pdeathsig_spawner_holder.instance = _PDeathSigSpawner()
        spawner = _pdeathsig_spawner_holder.instance
    return spawner.spawn(lambda: subprocess.Popen(cmd, **kwargs))


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


def convert_shell_cmd(cmd: str | list[str], use_exec: bool = False) -> str:
    """
    Converts a command (specified as a list or string) to a format supported by subprocess calls with shell=True on the current platform,
    applying necessary escaping and quoting if the command is specified as a list of arguments.

    :param cmd: the command to convert, specified as a list of arguments
    :param use_exec: if True (POSIX only; must not be set on Windows), prefix the command with the shell's
        `exec` builtin, so the shell replaces its own process image with the command instead of forking it
        as a child. Combined with set_pdeathsig_on_parent_exit, this is what makes the parent-death signal
        reach the actual program rather than only the intermediate shell.
    :return: a suitable representation of the command for subprocess calls on the current platform
    """
    cmd_str = oslex.join(cmd) if isinstance(cmd, list) else cmd
    if use_exec:
        cmd_str = f"exec {cmd_str}"
    return cmd_str


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
