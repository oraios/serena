import os
import subprocess
import sys
import time

import pytest

from serena.ls_manager import LanguageServerManager, LanguageServerManagerInitialisationError
from solidlsp.ls_config import LanguageServerId


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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
        # Mirrors e.g. clangd_language_server.py: the OS subprocess is spawned as part of
        # start(), and a capability/initialize() check can still raise after that process
        # is already running.
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(100)"])
        if self.should_fail:
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
        if _pid_alive(pid):
            os.kill(pid, 15)


def test_from_languages_stops_process_of_server_that_raises_after_spawning(_cleanup_leftover_pids):
    """A language server whose `start()` spawns its OS subprocess and then raises (e.g. a
    capability assertion or an initialize() timeout firing after the process is already up)
    must still have that process stopped by `from_languages`'s failure-path cleanup, exactly
    like a server that started successfully and is stopped because a sibling failed.
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
