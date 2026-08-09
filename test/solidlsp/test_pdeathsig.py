"""Regression test for issue #1490: a SIGKILLed Serena leaves its language server process running.

``StdioLanguageServer`` starts every LSP process in its own session
(``start_independent_lsp_process`` defaults to True, see ``ls_config.py``) so that our own
graceful-shutdown code can walk and terminate the whole process tree on a clean exit
(``subprocess_util.terminate_process_tree_with_kill_fallback``). That code never runs if Serena
itself is killed (SIGKILL, OOM, crash), and being in its own session means no signal to our
process group reaches the child either, so it survives as a PPID=1 orphan.

This drives a real ``StdioLanguageServer`` in a child ("fake Serena") process, SIGKILLs that
child, and checks whether the language server process it started is still alive afterwards.
Linux only: the fix is ``prctl(PR_SET_PDEATHSIG)``, which has no equivalent exercised here on
other platforms.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import textwrap
import time
import uuid

import psutil
import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Linux", reason="PR_SET_PDEATHSIG is Linux-specific")

_DRIVER_SRC = textwrap.dedent(
    """
    import sys
    from solidlsp.ls_config import LanguageServerId
    from solidlsp.ls_process import StdioLanguageServer
    from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

    marker = sys.argv[1]
    ls = StdioLanguageServer(
        process_launch_info=ProcessLaunchInfo(
            cmd=[sys.executable, "-c", f"import time; time.sleep(300)  # {marker}"],
            cwd="/tmp",
        ),
        ls_id=LanguageServerId.PYTHON,
        determine_log_level=lambda _line: 0,
    )
    ls._start()
    print("READY", flush=True)
    time.sleep(600)
    """
)


def _find_marked_processes(marker: str) -> list[psutil.Process]:
    found = []
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if any(marker in arg for arg in cmdline):
            found.append(proc)
    return found


_THREAD_DRIVER_SRC = textwrap.dedent(
    """
    import sys
    import threading
    import time
    from solidlsp.ls_config import LanguageServerId
    from solidlsp.ls_process import StdioLanguageServer
    from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

    marker = sys.argv[1]

    # Mirrors LanguageServerManager.from_languages's StartLSThread: the real code path spawns one
    # Thread per language server, that thread calls language_server.start() (-> ._start(), where
    # the process is actually launched), and the thread then simply returns -- terminating almost
    # immediately after Popen() returns, not on the process's main thread.
    def start_language_server():
        ls = StdioLanguageServer(
            process_launch_info=ProcessLaunchInfo(
                cmd=[sys.executable, "-c", f"import time; time.sleep(300)  # {marker}"],
                cwd="/tmp",
            ),
            ls_id=LanguageServerId.PYTHON,
            determine_log_level=lambda _line: 0,
        )
        ls.start()

    t = threading.Thread(target=start_language_server)
    t.start()
    t.join()  # the calling thread is gone from here on; the driver process itself lives on
    print("READY", flush=True)
    time.sleep(600)
    """
)


def test_language_server_process_survives_a_short_lived_calling_thread() -> None:
    """
    PR_SET_PDEATHSIG (per prctl(2)) ties the registration to the specific calling *thread*, not
    the process: if that thread terminates while the rest of the process lives on, the kernel
    delivers the death signal right then, even though "Serena" (the process) never died. Starting
    a language server is dispatched through TaskExecutor onto exactly such a short-lived thread, so
    a naive preexec_fn registration kills the language server itself within milliseconds of a normal
    startup, independent of any real SIGKILL scenario -- this is the CI-only regression this test
    guards against.
    """
    marker = f"pdeathsig-thread-test-{uuid.uuid4().hex}"
    driver = subprocess.Popen(
        [sys.executable, "-c", _THREAD_DRIVER_SRC, marker],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready_line = driver.stdout.readline()
        assert ready_line.strip() == "READY", f"driver failed to start the language server: {driver.stderr.read()}"

        time.sleep(2)
        # The driver's own argv also contains `marker` (it's passed as sys.argv[1]), so exclude
        # the driver's own pid or it would satisfy the assertion below on its own, regardless of
        # whether the actual language server process (its child) is still alive.
        survivors = [p for p in _find_marked_processes(marker) if p.pid != driver.pid]
        assert survivors, (
            "language server process died on its own even though the driver ('Serena') process "
            "is still alive -- the calling thread's exit, not a real parent death, killed it"
        )
    finally:
        for proc in _find_marked_processes(marker):
            proc.kill()
        if driver.poll() is None:
            driver.kill()


def test_language_server_process_dies_with_a_sigkilled_serena() -> None:
    marker = f"pdeathsig-test-{uuid.uuid4().hex}"
    driver = subprocess.Popen(
        [sys.executable, "-c", _DRIVER_SRC, marker],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready_line = driver.stdout.readline()
        assert ready_line.strip() == "READY", f"driver failed to start the language server: {driver.stderr.read()}"
        assert _find_marked_processes(marker), "language server process never started"

        driver.kill()  # SIGKILL: simulates Serena being killed without a chance to clean up
        driver.wait(timeout=5)

        deadline = time.monotonic() + 5
        survivors = _find_marked_processes(marker)
        while survivors and time.monotonic() < deadline:
            time.sleep(0.2)
            survivors = _find_marked_processes(marker)

        assert not survivors, (
            f"language server process(es) {[p.pid for p in survivors]} survived a SIGKILLed Serena "
            "(orphaned, will run until manually killed -- issue #1490)"
        )
    finally:
        for proc in _find_marked_processes(marker):
            proc.kill()
        if driver.poll() is None:
            driver.kill()
