# SPDX-License-Identifier: MIT

"""Tests for Bloop daemon cleanup on Scala LS stop (oraios/serena#1816)."""

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psutil

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer, _get_scala_settings
from solidlsp.ls_config import LanguageServerId
from solidlsp.settings import SolidLSPSettings

MODULE = "solidlsp.language_servers.scala_language_server"
OUR_PID = 111
BLOOP_CMDLINE = ["java", "bloop.BloopServer", "daemon:x"]


def _make_ls(terminate_bloop_on_stop: bool) -> ScalaLanguageServer:
    ls = object.__new__(ScalaLanguageServer)
    ls._terminate_bloop_on_stop = terminate_bloop_on_stop
    return ls


def _make_process(pid: int, ancestor_pids: list[int], cmdline: list[str] = BLOOP_CMDLINE) -> MagicMock:
    process = MagicMock()
    process.pid = pid
    process.info = {"pid": pid, "name": "java", "cmdline": cmdline}
    process.cmdline.return_value = cmdline
    process.parents.return_value = [SimpleNamespace(pid=ancestor_pid) for ancestor_pid in ancestor_pids]
    return process


@contextmanager
def _running_processes(processes: dict[int, MagicMock], events: list[str]) -> Iterator[None]:
    """Makes the given processes the ones running on the machine while the Metals shutdown is recorded in ``events``."""
    with (
        patch(f"{MODULE}.psutil.process_iter", side_effect=lambda attrs: iter(processes.values())),
        patch(f"{MODULE}.os.getpid", return_value=OUR_PID),
        patch("solidlsp.ls.SolidLanguageServer.stop", side_effect=lambda **kwargs: events.append("metals stopped")),
    ):
        yield


def test_terminate_bloop_on_stop_is_disabled_by_default():
    assert _get_scala_settings(SolidLSPSettings())["terminate_bloop_on_stop"] is False


def test_terminate_bloop_on_stop_can_be_enabled():
    settings = _get_scala_settings(SolidLSPSettings(ls_specific_settings={LanguageServerId.SCALA: {"terminate_bloop_on_stop": True}}))
    assert settings["terminate_bloop_on_stop"] is True


def test_bloop_daemon_is_left_running_if_termination_is_not_enabled():
    daemon = _make_process(222, ancestor_pids=[200, OUR_PID])
    events: list[str] = []
    with _running_processes({222: daemon}, events):
        _make_ls(terminate_bloop_on_stop=False).stop()

    assert events == ["metals stopped"]
    daemon.terminate.assert_not_called()


def test_only_bloop_daemons_of_this_session_are_terminated_once_metals_has_stopped():
    events: list[str] = []
    own_daemon = _make_process(222, ancestor_pids=[200, OUR_PID])
    own_daemon.terminate.side_effect = lambda: events.append("daemon terminated")
    foreign_daemon = _make_process(333, ancestor_pids=[999])
    other_program = _make_process(444, ancestor_pids=[OUR_PID], cmdline=["java", "metals"])

    with _running_processes({222: own_daemon, 333: foreign_daemon, 444: other_program}, events):
        _make_ls(terminate_bloop_on_stop=True).stop()

    assert events == ["metals stopped", "daemon terminated"]
    foreign_daemon.terminate.assert_not_called()
    other_program.terminate.assert_not_called()


def test_daemon_which_does_not_exit_after_termination_is_killed():
    daemon = _make_process(222, ancestor_pids=[OUR_PID])
    daemon.wait.side_effect = psutil.TimeoutExpired(seconds=3.0)
    with _running_processes({222: daemon}, []):
        _make_ls(terminate_bloop_on_stop=True).stop()

    daemon.kill.assert_called_once()


def test_process_which_is_no_longer_a_bloop_daemon_is_left_alone():
    process = _make_process(222, ancestor_pids=[OUR_PID])
    process.cmdline.return_value = ["java", "something-else"]
    with _running_processes({222: process}, []):
        _make_ls(terminate_bloop_on_stop=True).stop()

    process.terminate.assert_not_called()


def test_stop_does_not_raise_if_a_daemon_cannot_be_terminated_or_killed():
    denied_termination = _make_process(222, ancestor_pids=[OUR_PID])
    denied_termination.terminate.side_effect = psutil.AccessDenied(pid=222)
    denied_kill = _make_process(223, ancestor_pids=[OUR_PID])
    denied_kill.wait.side_effect = psutil.TimeoutExpired(seconds=3.0)
    denied_kill.kill.side_effect = psutil.AccessDenied(pid=223)
    accessible = _make_process(224, ancestor_pids=[OUR_PID])

    with _running_processes({222: denied_termination, 223: denied_kill, 224: accessible}, []):
        _make_ls(terminate_bloop_on_stop=True).stop()

    accessible.terminate.assert_called_once()
