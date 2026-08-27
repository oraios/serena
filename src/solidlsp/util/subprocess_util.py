import logging
import os
import platform
import queue
import signal
import subprocess
import threading
from collections.abc import Callable
from time import monotonic
from typing import IO, TYPE_CHECKING, Any, Generic, TypeVar, cast

import oslex
import psutil
from sensai.util.string import ToStringMixin

if TYPE_CHECKING:
    import ctypes

    from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

log = logging.getLogger(__name__)
TStream = TypeVar("TStream", bound=str | bytes)


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


class ManagedSubprocess(Generic[TStream], ToStringMixin):
    """
    Represents a subprocess.Popen instance with additional lifecycle management, including the ability to terminate the process
    and its children gracefully, with a fallback to forceful termination if necessary.
    """

    def __init__(self, popen: subprocess.Popen[TStream], name: str, start_new_session: bool) -> None:
        """
        :param popen: the subprocess.Popen instance representing the launched process
        :param name: the name of the process (used for logging purposes); should start with a capital letter
        :param start_new_session: whether the process was launched in its own session, i.e. whether it is the
            leader of its own process group
        """
        self._popen = popen
        self._name = name

        # a process launched with start_new_session=True is its own group leader, so its PGID is its PID
        self._process_group_id = popen.pid if (start_new_session and os.name == "posix") else None

    def _tostring_includes(self) -> list[str]:
        return ["_name"]

    @property
    def stdin(self) -> "IO[TStream] | None":
        return self._popen.stdin

    @property
    def stdout(self) -> "IO[TStream] | None":
        return self._popen.stdout

    @property
    def stderr(self) -> "IO[TStream] | None":
        return self._popen.stderr

    @property
    def returncode(self) -> int | None:
        """
        :return: the exit code of the process as of the most recent status check (see :meth:`poll`),
            or None if the process was not yet known to have terminated
        """
        return self._popen.returncode

    def poll(self) -> int | None:
        """
        Checks whether the process has terminated, updating :attr:`returncode` accordingly.

        :return: the exit code of the process or None if it is still running
        """
        return self._popen.poll()

    def terminate(self, timeout: float) -> None:
        """
        Terminates the process and its children, forcefully killing them if they do not exit in time.

        :param timeout: the time, in seconds, to wait for the process to terminate gracefully before killing it
        """
        terminate_process_tree_with_kill_fallback(
            self._popen,
            terminate_timeout=timeout,
            process_name=self._name,
            process_group_id=self._process_group_id,
        )


class ManagedSubprocessLauncher:
    """
    Launcher for managed subprocesses (see :class:`ManagedSubprocess`), which are started for stdio-based communication.
    It is home to the concern of launching a subprocess with well-defined lifecycle properties,
    ensuring, in particular, that a launched subprocess cannot outlive this process (insofar as
    the platform allows) -- even if the subprocess is started in its own session (see
    :meth:`launch`) and this process is terminated forcefully without the opportunity to perform
    cleanup (e.g. SIGKILL).

    The class is a singleton, as it is (potentially) home to a persistent worker thread.
    """

    _PR_SET_PDEATHSIG = 1
    """the PR_SET_PDEATHSIG option value for prctl(2)"""

    _instance: "ManagedSubprocessLauncher | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._libc = self._load_libc()
        self._spawner: "ManagedSubprocessLauncher._PDeathSigSpawner | None" = None
        self._spawner_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ManagedSubprocessLauncher":
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
                "Could not load libc (%s); subprocesses will not be protected against "
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

    def launch(self, process_launch_info: "ProcessLaunchInfo", name: str, start_new_session: bool) -> ManagedSubprocess[bytes]:
        """
        Launches a subprocess from ``process_launch_info``.

        :param process_launch_info: the command, environment and working directory to launch with
        :param name: the name of the process (used for logging purposes); should start with a capital letter
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

        def do_popen() -> ManagedSubprocess[bytes]:
            popen = cast(
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
            return ManagedSubprocess(popen, name, start_new_session)

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
            self._queue: queue.Queue[tuple[Callable[[], ManagedSubprocess[bytes]], "queue.Queue"]] = queue.Queue()
            self._thread = threading.Thread(target=self._run, name="solidlsp-pdeathsig-spawner", daemon=True)
            self._thread.start()

        def _run(self) -> None:
            while True:
                func, result_queue = self._queue.get()
                try:
                    result_queue.put((None, func()))
                except BaseException as e:
                    result_queue.put((e, None))

        def spawn(self, func: Callable[[], ManagedSubprocess[bytes]]) -> ManagedSubprocess[bytes]:
            result_queue: queue.Queue = queue.Queue(maxsize=1)
            self._queue.put((func, result_queue))
            error, process = result_queue.get()
            if error is not None:
                raise error
            return process


def _signal_process_tree(
    process: subprocess.Popen[bytes],
    terminate: bool = True,
    descendants: list[psutil.Process] | None = None,
) -> None:
    """
    Sends a signal (terminate or kill) to the given process and its descendants.

    ``descendants`` is an optional snapshot captured before the leader is signaled.
    It is needed for kill fallback: the leader may have exited and been reaped before
    the fallback runs, in which case re-enumerating from ``process.pid`` loses the tree.

    :param terminate: if True, signal terminate, otherwise signal kill
    :param descendants: previously discovered descendants to signal even if the leader is gone
    """

    def signal_process(p: subprocess.Popen | psutil.Process) -> None:
        try:
            if terminate:
                p.terminate()
            else:
                p.kill()
        except (psutil.Error, OSError):
            pass

    if descendants is None:
        descendants = []
        try:
            parent = psutil.Process(process.pid)
            if parent.is_running():
                descendants = parent.children(recursive=True)
        except (psutil.Error, OSError):
            pass

    # Signal the snapshot first, then the leader. The snapshot remains usable after
    # the leader has exited, while newly spawned children are outside its guarantee.
    for child in descendants:
        signal_process(child)
    signal_process(process)


def _signal_process_group(pgid: int, terminate: bool = True) -> None:
    """
    Sends a signal to every process in the given POSIX process group by group ID, without
    enumerating the system process table. Requires the caller to know the group already exists
    and is owned by us (see ``terminate_process_tree_with_kill_fallback``'s ``process_group_id``).

    :param pgid: the process group ID to signal
    :param terminate: if True, signal terminate (SIGTERM), otherwise signal kill (SIGKILL)
    """
    sig = signal.SIGTERM if terminate else signal.SIGKILL
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        # the group is already gone; nothing left to signal
        pass
    except PermissionError as e:
        log.warning(f"Permission denied signaling process group {pgid} with {sig.name}: {e}")
    except Exception as e:
        log.warning(f"Unexpected error signaling process group {pgid} with {sig.name}: {e}")


def _get_process_descendants(process: subprocess.Popen) -> list[psutil.Process]:
    """Return a snapshot of descendants that should be waited on after signaling."""
    try:
        return psutil.Process(process.pid).children(recursive=True)
    except (psutil.Error, OSError):
        return []


def _wait_for_processes_until(processes: list[psutil.Process], deadline: float) -> bool:
    """Wait for a process snapshot until an absolute monotonic deadline.

    Descendants are waited in reverse depth-first discovery order so that a child
    has a chance to exit before its parent is reaped. A process that disappears
    or cannot be waited by the current OS process is already clean for our
    purposes; a timeout is returned to trigger the caller's kill fallback.
    """
    for child in reversed(processes):
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        try:
            child.wait(timeout=remaining)
        except psutil.TimeoutExpired:
            return False
        except (psutil.Error, OSError):
            continue
    return True


def _wait_for_processes(processes: list[psutil.Process], timeout: float) -> bool:
    """Wait for a process snapshot within one shared timeout budget."""
    return _wait_for_processes_until(processes, monotonic() + timeout)


def terminate_process_tree_with_kill_fallback(
    process: subprocess.Popen,
    terminate_timeout: float,
    process_name: str = "Process",
    process_group_id: int | None = None,
) -> None:
    """
    Attempts to terminate the given process and its children by signaling them to terminate,
    and if that fails (i.e. they don't exit within the given timeout), forcefully kills them.

    The termination is logged.

    :param process: the process to terminate
    :param terminate_timeout: the time to wait for the process to terminate gracefully before killing it
    :param process_name: the name of the process (used for logging purposes); should start with capital letter
    :param process_group_id: if given, the POSIX process group ID that ``process`` leads (i.e. it was
        launched with ``start_new_session=True``, so its PGID equals its PID). When set, cleanup
        signals the whole group directly via ``os.killpg`` rather than walking the process tree to
        signal it. Descendant discovery remains best-effort so cleanup can wait for children after
        the group is signaled; ``_get_process_descendants`` safely returns an empty list when the
        platform denies process-table enumeration (for example, ``sysctl(KERN_PROC_ALL)`` on macOS).
        Only pass this for a process that was started in its own session: signaling the group of a
        process that shares ours would also signal us.
    """
    log.debug(f"Terminating process {process.pid}, current status: {process.poll()}")
    descendants = _get_process_descendants(process)

    def signal_tree(terminate: bool) -> None:
        if process_group_id is not None:
            _signal_process_group(process_group_id, terminate=terminate)
        else:
            _signal_process_tree(process, terminate=terminate, descendants=None if terminate else descendants)

    signal_tree(terminate=True)
    try:
        log.debug(f"Waiting for process {process.pid} to terminate...")
        terminate_deadline = monotonic() + terminate_timeout
        descendants_finished = _wait_for_processes_until(descendants, terminate_deadline)
        remaining = terminate_deadline - monotonic()
        if not descendants_finished or remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, terminate_timeout)
        exit_code = process.wait(timeout=remaining)
        log.info(f"{process_name} terminated successfully with exit code {exit_code}.")
    except subprocess.TimeoutExpired:
        # If termination failed, forcefully kill the process
        log.warning(f"{process_name} (pid={process.pid}) termination timed out, killing process forcefully...")
        signal_tree(terminate=False)
        kill_deadline = monotonic() + 2.0
        _wait_for_processes_until(descendants, kill_deadline)
        remaining = max(kill_deadline - monotonic(), 0.1)
        try:
            exit_code = process.wait(timeout=remaining)
            log.info(f"{process_name} killed successfully with exit code {exit_code}.")
        except subprocess.TimeoutExpired:
            log.error(f"{process_name} (pid={process.pid}) could not be killed within timeout.")
    except Exception as e:
        log.error(f"Error during process shutdown: {e}")
