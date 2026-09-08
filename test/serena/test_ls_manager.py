import subprocess
import sys
import time

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
