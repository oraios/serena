import subprocess
import sys
import time
from dataclasses import dataclass
from unittest.mock import MagicMock

import psutil
import pytest

from serena.ls_manager import LanguageServerManager, LanguageServerManagerInitialisationError
from solidlsp.ls_config import LanguageServerId


def _pid_alive(pid: int) -> bool:
    # Not `os.kill(pid, 0)`: that is a no-op liveness probe on POSIX, but on Windows
    # `os.kill` has no signal-0 special case and falls through to `TerminateProcess(handle,
    # 0)`, so the "check" can itself kill (or, if the pid was already recycled, terminate an
    # unrelated process) instead of only reading process-table state.
    return psutil.pid_exists(pid)


class _FakeLanguageServer:
    """Duck-typed stand-in for SolidLanguageServer: `from_languages` only calls
    `.start()`/`.is_running()`/`.stop()` on it, never isinstance-checks the object.
    """

    def __init__(self, ls_id: LanguageServerId, should_fail: bool):
        self.ls_id = ls_id
        self.should_fail = should_fail
        self.proc: subprocess.Popen | None = None
        self._running = False

    def start(self) -> "_FakeLanguageServer":
        # Mirrors SolidLanguageServer.start(): the OS subprocess is spawned as part of
        # start(), a capability/initialize() check can still raise after that process is
        # already running, and start() stops the process it just spawned before re-raising
        # (see SolidLanguageServer.start).
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(100)"])
        if self.should_fail:
            self._running = True
            self.stop()
            raise RuntimeError(f"simulated: capability assertion failed after initialize() ({self.ls_id.value})")
        self._running = True
        return self

    def is_running(self) -> bool:
        return self._running

    def save_cache(self) -> None:
        pass

    def simulate_exit_leaving_processes(self) -> None:
        """Reports the server as no longer running while its process stays alive, like the children of an exited launcher."""
        self._running = False

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=shutdown_timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._running = False


class _FakeLanguageServerFactory:
    def __init__(self, fail_ids: set[LanguageServerId]):
        self.fail_ids = fail_ids
        self.created: dict[LanguageServerId, _FakeLanguageServer] = {}

    def create_language_server(self, ls_id: LanguageServerId) -> _FakeLanguageServer:
        ls = _FakeLanguageServer(ls_id, should_fail=ls_id in self.fail_ids)
        self.created[ls_id] = ls
        return ls


@pytest.fixture
def _cleanup_leftover_pids():
    """Belt-and-braces: kill any spawned test subprocess still alive after the test body,
    so a regression in the fix under test cannot leak a real OS process past this test.
    """
    pids: list[int] = []
    yield pids
    for pid in pids:
        try:
            psutil.Process(pid).kill()
        except psutil.NoSuchProcess:
            pass


def test_from_languages_stops_process_of_server_that_raises_after_spawning(_cleanup_leftover_pids):
    """End-to-end: a language server whose `start()` spawns its OS subprocess and then raises
    (e.g. a capability assertion or an initialize() timeout firing after the process is
    already up) must not leak that process, and a sibling that started successfully must be
    stopped too since `from_languages` fails the whole batch. The failing server cleans up its
    own process (SolidLanguageServer.start()); `from_languages` is responsible only for
    stopping the siblings that succeeded.
    """
    ok_id = LanguageServerId("python")
    failing_id = LanguageServerId("rust")
    factory = _FakeLanguageServerFactory(fail_ids={failing_id})

    with pytest.raises(LanguageServerManagerInitialisationError):
        LanguageServerManager.from_languages([ok_id, failing_id], factory, project=None)

    time.sleep(0.3)
    pids = {ls_id: ls.proc.pid for ls_id, ls in factory.created.items() if ls.proc is not None}
    _cleanup_leftover_pids.extend(pids.values())

    assert set(pids) == {ok_id, failing_id}
    assert not _pid_alive(pids[ok_id]), "the successfully-started server's process should be stopped"
    assert not _pid_alive(pids[failing_id]), "the process spawned by the server that raised post-spawn must not leak"


class _CacheSavingLanguageServer:
    def __init__(self, ls_id: LanguageServerId):
        self.ls_id = ls_id
        self.cache_saves = 0
        self._running = False

    def start(self) -> "_CacheSavingLanguageServer":
        self._running = True
        return self

    def is_running(self) -> bool:
        return self._running

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        self._running = False

    def save_cache(self) -> None:
        self.cache_saves += 1


class _CacheSavingLanguageServerFactory:
    def __init__(self) -> None:
        self.created: list[_CacheSavingLanguageServer] = []

    def create_language_server(self, ls_id: LanguageServerId) -> _CacheSavingLanguageServer:
        ls = _CacheSavingLanguageServer(ls_id)
        self.created.append(ls)
        return ls


class _ProjectWithoutFiles:
    def gather_source_files(self) -> list:
        return []


def _manager_with_one_server() -> tuple[LanguageServerManager, _CacheSavingLanguageServerFactory]:
    factory = _CacheSavingLanguageServerFactory()
    manager = LanguageServerManager.from_languages([LanguageServerId("python")], factory, project=_ProjectWithoutFiles())
    return manager, factory


def test_cache_is_saved_at_most_once_per_interval_after_tool_calls() -> None:
    manager, factory = _manager_with_one_server()

    for _ in range(3):
        manager.save_all_caches_if_due()

    assert factory.created[0].cache_saves == 1


def test_cache_is_saved_again_once_the_interval_has_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LanguageServerManager, "_CACHE_SAVE_INTERVAL", 0.05)
    manager, factory = _manager_with_one_server()
    manager.save_all_caches_if_due()

    time.sleep(0.1)
    manager.save_all_caches_if_due()

    assert factory.created[0].cache_saves == 2


def test_restart_saves_the_cache_of_the_replaced_server() -> None:
    manager, factory = _manager_with_one_server()
    manager.save_all_caches_if_due()
    replaced_server = factory.created[0]
    replaced_server.stop()

    manager.restart_language_server(LanguageServerId("python"))

    assert replaced_server.cache_saves == 2


@dataclass
class _ManagerWithExitedServer:
    """A manager whose single language server is no longer running but still has a live process."""

    manager: LanguageServerManager
    factory: _FakeLanguageServerFactory
    ls_id: LanguageServerId
    exited: _FakeLanguageServer
    exited_proc: subprocess.Popen


@pytest.fixture
def manager_with_exited_server(_cleanup_leftover_pids) -> _ManagerWithExitedServer:
    ls_id = LanguageServerId("python")
    factory = _FakeLanguageServerFactory(fail_ids=set())
    manager = LanguageServerManager.from_languages([ls_id], factory, project=MagicMock())
    exited = factory.created[ls_id]
    assert exited.proc is not None
    _cleanup_leftover_pids.append(exited.proc.pid)
    exited.simulate_exit_leaving_processes()
    return _ManagerWithExitedServer(manager, factory, ls_id, exited, exited.proc)


def test_restart_stops_previous_instance_whose_processes_outlive_it(manager_with_exited_server, _cleanup_leftover_pids):
    """A language server that is no longer running may still have processes alive (e.g. children of
    an exited launcher); restarting it must release them rather than leak them.
    """
    m = manager_with_exited_server

    m.manager.restart_language_server(m.ls_id)

    restarted = m.factory.created[m.ls_id]
    assert restarted is not m.exited
    assert restarted.proc is not None
    _cleanup_leftover_pids.append(restarted.proc.pid)
    assert m.exited_proc.poll() is not None, "the previous instance's surviving process should be stopped"


def test_stop_all_releases_processes_of_exited_server_without_restarting_it(manager_with_exited_server):
    m = manager_with_exited_server

    m.manager.stop_all()

    assert m.factory.created[m.ls_id] is m.exited, "an exited server should not be restarted only to be stopped"
    assert m.exited_proc.poll() is not None, "the exited server's surviving process should be stopped"


def test_remove_releases_processes_of_exited_server(manager_with_exited_server):
    m = manager_with_exited_server

    m.manager.remove_language_server(m.ls_id)

    assert m.exited_proc.poll() is not None, "the removed server's surviving process should be stopped"
