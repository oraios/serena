# SPDX-License-Identifier: MIT

"""Tests for Bloop daemon cleanup on Scala LS stop (oraios/serena#1816)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from solidlsp.language_servers.scala_language_server import ScalaLanguageServer


def _make_ls(custom_settings: dict | None = None) -> ScalaLanguageServer:
    ls = object.__new__(ScalaLanguageServer)
    ls._custom_settings = custom_settings or {}
    return ls


def test_discover_only_descendant_bloop_processes():
    ls = _make_ls()
    our_pid = 111

    def fake_process_iter(attrs):
        bloop_child = SimpleNamespace(
            info={"pid": 222, "name": "java", "cmdline": ["java", "bloop.BloopServer", "daemon:x"]},
            parents=lambda: [SimpleNamespace(pid=200), SimpleNamespace(pid=our_pid)],
        )
        bloop_foreign = SimpleNamespace(
            info={"pid": 333, "name": "java", "cmdline": ["java", "bloop.BloopServer", "daemon:y"]},
            parents=lambda: [SimpleNamespace(pid=999)],
        )
        not_bloop = SimpleNamespace(
            info={"pid": 444, "name": "java", "cmdline": ["java", "metals"]},
            parents=lambda: [SimpleNamespace(pid=our_pid)],
        )
        return iter([bloop_child, bloop_foreign, not_bloop])

    with (
        patch("solidlsp.language_servers.scala_language_server.psutil.process_iter", side_effect=fake_process_iter),
        patch("solidlsp.language_servers.scala_language_server.os.getpid", return_value=our_pid),
    ):
        assert ls._discover_bloop_descendant_pids() == {222}


def test_stop_respects_terminate_bloop_on_stop_false():
    ls = _make_ls({"terminate_bloop_on_stop": False})
    with (
        patch.object(ScalaLanguageServer, "_discover_bloop_descendant_pids") as discover,
        patch.object(ScalaLanguageServer, "_terminate_orphaned_bloop_processes") as terminate,
        patch("solidlsp.ls.SolidLanguageServer.stop") as super_stop,
    ):
        ls.stop()
        discover.assert_not_called()
        terminate.assert_not_called()
        super_stop.assert_called_once()


def test_stop_terminates_discovered_bloop_after_super_stop():
    ls = _make_ls({})
    with (
        patch.object(ScalaLanguageServer, "_discover_bloop_descendant_pids", return_value={222}) as discover,
        patch.object(ScalaLanguageServer, "_terminate_orphaned_bloop_processes") as terminate,
        patch("solidlsp.ls.SolidLanguageServer.stop") as super_stop,
    ):
        ls.stop()
        discover.assert_called_once()
        super_stop.assert_called_once()
        terminate.assert_called_once_with({222})


def test_terminate_skips_pid_that_is_no_longer_bloop():
    ls = _make_ls()
    proc = MagicMock()
    proc.cmdline.return_value = ["java", "something-else"]
    with patch("solidlsp.language_servers.scala_language_server.psutil.Process", return_value=proc):
        ls._terminate_orphaned_bloop_processes({555})
    proc.terminate.assert_not_called()


def test_terminate_kills_surviving_bloop():
    ls = _make_ls()
    proc = MagicMock()
    proc.cmdline.return_value = ["java", "bloop.BloopServer", "daemon:z"]
    with patch("solidlsp.language_servers.scala_language_server.psutil.Process", return_value=proc):
        ls._terminate_orphaned_bloop_processes({555})
    proc.terminate.assert_called_once()
    proc.wait.assert_called_once()
