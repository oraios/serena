"""Regression tests for the TypeScript/Svelte timeout policy split.

The base TypeScript server keeps its historical permissive behavior on readiness and
indexing timeouts (log and proceed), while the Svelte companion TS server is strict
(raise instead of serving requests from a cold or partially indexed program). These
tests pin that policy and the settings plumbing directly, without spawning language
server processes, so a future refactor cannot silently revert either side.
"""

import threading
import time

import pytest

from solidlsp.language_servers.svelte_language_server import (
    SvelteCompanionPreparationError,
    SvelteLanguageServer,
    SvelteTypeScriptServer,
)
from solidlsp.language_servers.typescript_language_server import TypeScriptLanguageServer
from solidlsp.settings import SolidLSPSettings


def _bare_ts_server(cls: type[TypeScriptLanguageServer], custom_settings: dict | None = None) -> TypeScriptLanguageServer:
    """Create an instance without running __init__ (no process, no repo scan), setting only the
    state the timeout machinery touches; same technique as test_rename_didopen.py.
    """
    server = object.__new__(cls)
    server.server_ready = threading.Event()
    server._progress_lock = threading.Lock()
    server._active_progress_tokens = set()
    server._indexing_complete = threading.Event()
    server._indexing_complete.set()  # mirrors __init__: initially no active work
    server._custom_settings = SolidLSPSettings.CustomLSSettings(custom_settings)
    return server


class TestBaseTypeScriptTimeoutPolicy:
    """The base server must stay permissive: plain TypeScript setups are unchanged."""

    def test_server_ready_timeout_proceeds(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer)
        assert not server.server_ready.is_set()

        server._handle_server_ready_timeout(10.0)  # must not raise

        assert server.server_ready.is_set()

    def test_indexing_timeout_proceeds(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer)
        server.expect_indexing()
        server._active_progress_tokens.add("indexing-1")

        server._handle_project_indexing_timeout(30.0)  # must not raise

    def test_timeout_defaults(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer)
        assert server._get_server_ready_timeout() == 10.0
        assert server._get_indexing_timeout() == 30.0

    def test_timeouts_configurable_via_ls_specific_settings(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer, {"server_ready_timeout": 1.5, "indexing_timeout": 2.5})
        assert server._get_server_ready_timeout() == 1.5
        assert server._get_indexing_timeout() == 2.5


class TestSvelteCompanionTimeoutPolicy:
    """The Svelte companion must be strict: raise instead of serving from a cold/partial program."""

    def test_server_ready_timeout_raises(self) -> None:
        server = _bare_ts_server(SvelteTypeScriptServer)

        with pytest.raises(TimeoutError, match="did not become ready within 30s"):
            server._handle_server_ready_timeout(30.0)

        assert not server.server_ready.is_set()  # a strict server must not fake readiness

    def test_indexing_timeout_raises_with_diagnostic_state(self) -> None:
        server = _bare_ts_server(SvelteTypeScriptServer)
        server.expect_indexing()
        server._active_progress_tokens.add("initializing-js-ts-features")

        with pytest.raises(TimeoutError) as exc_info:
            server._handle_project_indexing_timeout(120.0)

        message = str(exc_info.value)
        assert "did not complete within 120s" in message
        assert "complete=False" in message
        assert "initializing-js-ts-features" in message

    def test_companion_timeout_defaults_are_raised(self) -> None:
        server = _bare_ts_server(SvelteTypeScriptServer)
        assert server._get_server_ready_timeout() == 30.0
        assert server._get_indexing_timeout() == 120.0


class TestWaitForIndexingStartOrCompletion:
    def test_returns_false_when_active_progress_never_completes(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer)
        server.expect_indexing()
        server._active_progress_tokens.add("stuck-progress")

        assert server._wait_for_indexing_start_or_completion(timeout=0.1, start_grace=0.0) is False

    def test_treats_absent_progress_as_ready(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer)
        server.expect_indexing()

        assert server._wait_for_indexing_start_or_completion(timeout=30.0, start_grace=0.0) is True
        assert server._indexing_complete.is_set()

    def test_returns_immediately_when_no_indexing_expected(self) -> None:
        # _indexing_complete is initially set; a long grace must not block in that case
        server = _bare_ts_server(TypeScriptLanguageServer)

        start = time.monotonic()
        assert server._wait_for_indexing_start_or_completion(timeout=30.0, start_grace=30.0) is True
        # must return via the early is_set() check, not sit out the 30s grace; the path is
        # pure in-memory, so a 10s bound cannot flake on a slow runner
        assert time.monotonic() - start < 10.0

    def test_returns_true_when_progress_completes(self) -> None:
        server = _bare_ts_server(TypeScriptLanguageServer)
        server.expect_indexing()
        server._active_progress_tokens.add("indexing-1")

        def finish_indexing() -> None:
            with server._progress_lock:
                server._active_progress_tokens.clear()
            server._indexing_complete.set()

        timer = threading.Timer(0.05, finish_indexing)
        timer.start()
        try:
            # both timer orderings pass: an early fire takes the absent-progress branch,
            # which sets the event itself, while a late fire wakes Event.wait; ordering
            # cannot flake this test. It fails only if the spawned thread does not run
            # within the 30s ceiling, which means the runner is hung.
            assert server._wait_for_indexing_start_or_completion(timeout=30.0, start_grace=0.0) is True
        finally:
            timer.cancel()


class _FakeSolidLSPSettings:
    """Minimal settings stand-in: returns a fixed TypeScript indexing_timeout so the guard tests can
    prove the svelte-key value takes precedence over the typescript-key value.
    """

    def __init__(self, ts_indexing_timeout: float) -> None:
        self._ts_indexing_timeout = ts_indexing_timeout

    def get_ls_specific_settings(self, language: object) -> "SolidLSPSettings.CustomLSSettings":
        return SolidLSPSettings.CustomLSSettings({"indexing_timeout": self._ts_indexing_timeout})


class _FakeCompanionTSServer:
    """Hand-written stand-in for the companion TS server that records calls, so the guard tests assert
    observable behavior (raised errors, message shape, which timeout is used) instead of mock interactions.
    """

    class _FileBuffer:
        def __init__(self, uri: str) -> None:
            self.uri = uri
            self.ref_count = 0

        def __enter__(self) -> "_FakeCompanionTSServer._FileBuffer":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def __init__(self, *, wait_result: bool = True, open_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.wait_timeout: float | None = None
        self._wait_result = wait_result
        self._open_error = open_error

    def expect_indexing(self) -> None:
        self.calls.append("expect_indexing")

    def open_file(self, relative_path: str) -> "_FakeCompanionTSServer._FileBuffer":
        self.calls.append("open_file")
        if self._open_error is not None:
            raise self._open_error
        return self._FileBuffer(uri=f"file:///{relative_path}")

    def _wait_for_indexing_start_or_completion(self, timeout: float) -> bool:
        self.calls.append("wait")
        self.wait_timeout = timeout
        return self._wait_result

    def describe_indexing_state(self) -> str:
        return "complete=False, active_progress_tokens=stuck-progress"


class TestSvelteLanguageServerCompanionGuard:
    """SvelteLanguageServer._ensure_svelte_files_indexed_on_ts_server must fail loudly, not degrade."""

    def _bare_svelte_ls(self, ts_server: _FakeCompanionTSServer, repo_path: str) -> SvelteLanguageServer:
        ls = object.__new__(SvelteLanguageServer)
        ls.repo_path = repo_path
        ls._svelte_files_indexed = False
        ls._indexed_svelte_file_uris = []
        ls._custom_settings = SolidLSPSettings.CustomLSSettings({"indexing_timeout": 0.01})
        # conflicting typescript-key value: the timeout assertions below prove the svelte key wins
        ls._solidlsp_settings = _FakeSolidLSPSettings(ts_indexing_timeout=999.0)
        ls._ts_server = ts_server
        return ls

    def test_raises_when_companion_indexing_times_out(self, tmp_path) -> None:
        (tmp_path / "App.svelte").touch()
        ts_server = _FakeCompanionTSServer(wait_result=False)
        ls = self._bare_svelte_ls(ts_server, str(tmp_path))

        with pytest.raises(TimeoutError, match="did not finish indexing 1 .svelte files"):
            ls._ensure_svelte_files_indexed_on_ts_server()

        # the svelte-key indexing_timeout (0.01), not the typescript-key (999.0), must reach the wait
        assert ts_server.wait_timeout == 0.01

    def test_succeeds_and_arms_progress_tracking_before_opening_files(self, tmp_path) -> None:
        (tmp_path / "App.svelte").touch()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "skip.svelte").touch()
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "skip.svelte").touch()
        ts_server = _FakeCompanionTSServer(wait_result=True)
        ls = self._bare_svelte_ls(ts_server, str(tmp_path))

        ls._ensure_svelte_files_indexed_on_ts_server()

        assert ts_server.calls.count("open_file") == 1
        # a second call is a no-op — the observable consequence of the indexed flag
        calls_after_indexing = list(ts_server.calls)
        ls._ensure_svelte_files_indexed_on_ts_server()
        assert ts_server.calls == calls_after_indexing
        # expect_indexing must be armed BEFORE any file is opened, or early progress is lost to a race
        assert ts_server.calls[0] == "expect_indexing"
        assert ts_server.calls.index("expect_indexing") < ts_server.calls.index("open_file")

    def test_collects_failed_opens_and_raises_preparation_error(self, tmp_path) -> None:
        (tmp_path / "B.svelte").touch()
        (tmp_path / "A.svelte").touch()
        ts_server = _FakeCompanionTSServer(open_error=RuntimeError("didOpen failed"))
        ls = self._bare_svelte_ls(ts_server, str(tmp_path))

        with pytest.raises(SvelteCompanionPreparationError, match="2 Svelte file") as exc_info:
            ls._ensure_svelte_files_indexed_on_ts_server()

        assert "A.svelte, B.svelte" in str(exc_info.value)
        # the first underlying error must be chained so the cause survives without DEBUG logs
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        # a failed preparation must short-circuit before the indexing wait
        assert "wait" not in ts_server.calls

    def test_preparation_error_caps_file_listing(self, tmp_path) -> None:
        for i in reversed(range(15)):
            (tmp_path / f"{i:02d}.svelte").touch()
        ts_server = _FakeCompanionTSServer(open_error=RuntimeError("didOpen failed"))
        ls = self._bare_svelte_ls(ts_server, str(tmp_path))

        with pytest.raises(SvelteCompanionPreparationError) as exc_info:
            ls._ensure_svelte_files_indexed_on_ts_server()

        message = str(exc_info.value)
        assert "15 Svelte file(s)" in message
        assert "09.svelte" in message  # the 10th entry of the sorted listing is still shown
        assert "10.svelte" not in message  # the 11th is capped
        assert "and 5 more" in message
