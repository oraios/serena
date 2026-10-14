# SPDX-License-Identifier: MIT

"""Tests for Bloop daemon cleanup on Scala LS stop (oraios/serena#1816).

The Bloop daemon is represented by a plain Python helper process whose command line contains
``bloop.BloopServer``, so no JVM is required.
"""

import platform
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Iterator

import pytest

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer, _get_scala_settings
from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_config import LanguageServerId
from solidlsp.settings import SolidLSPSettings

pytestmark = pytest.mark.skipif(platform.system() == "Windows", reason="POSIX signal semantics are used by the helper processes")

_IDLE = "import time; time.sleep(300)"
_IDLE_IGNORING_TERMINATION = textwrap.dedent(
    """
    import signal, time
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("READY", flush=True)
    time.sleep(300)
    """
)


def _wait_until(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def helper_processes() -> Iterator[list[subprocess.Popen]]:
    """Provides a list to which helper processes are added; they are killed at the end of the test."""
    processes: list[subprocess.Popen] = []
    yield processes
    for process in processes:
        process.kill()
        process.wait()


def _start_idle_process(processes: list[subprocess.Popen], *args: str, code: str = _IDLE) -> subprocess.Popen:
    process = subprocess.Popen([sys.executable, "-c", code, *args], stdout=subprocess.PIPE, text=True)
    processes.append(process)
    return process


def _stop_scala_ls(terminate_bloop_on_stop: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stops a Scala language server whose Metals shutdown is a no-op."""
    monkeypatch.setattr(SolidLanguageServer, "stop", lambda self, **kwargs: None)
    ls = object.__new__(ScalaLanguageServer)
    ls._terminate_bloop_on_stop = terminate_bloop_on_stop
    ls.stop()


def test_terminate_bloop_on_stop_is_disabled_by_default():
    assert _get_scala_settings(SolidLSPSettings())["terminate_bloop_on_stop"] is False


def test_terminate_bloop_on_stop_can_be_enabled():
    settings = _get_scala_settings(SolidLSPSettings(ls_specific_settings={LanguageServerId.SCALA: {"terminate_bloop_on_stop": True}}))
    assert settings["terminate_bloop_on_stop"] is True


def test_bloop_daemon_is_left_running_if_termination_is_not_enabled(helper_processes, monkeypatch):
    daemon = _start_idle_process(helper_processes, "bloop.BloopServer")

    _stop_scala_ls(terminate_bloop_on_stop=False, monkeypatch=monkeypatch)

    assert daemon.poll() is None


def test_only_bloop_daemons_are_terminated_if_termination_is_enabled(helper_processes, monkeypatch):
    daemon = _start_idle_process(helper_processes, "bloop.BloopServer")
    other_program = _start_idle_process(helper_processes, "metals")

    _stop_scala_ls(terminate_bloop_on_stop=True, monkeypatch=monkeypatch)

    assert _wait_until(lambda: daemon.poll() is not None)
    assert other_program.poll() is None


def test_bloop_daemon_which_ignores_termination_is_killed(helper_processes, monkeypatch):
    daemon = _start_idle_process(helper_processes, "bloop.BloopServer", code=_IDLE_IGNORING_TERMINATION)
    assert daemon.stdout is not None and daemon.stdout.readline().strip() == "READY"

    _stop_scala_ls(terminate_bloop_on_stop=True, monkeypatch=monkeypatch)

    assert _wait_until(lambda: daemon.poll() is not None)
