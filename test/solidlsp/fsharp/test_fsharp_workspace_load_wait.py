"""
FsAutoComplete loads the workspace's projects asynchronously once it receives `initialized`,
and reports completion with an `fsharp/notifyWorkspace` notification of kind `workspaceLoad`;
requests sent before that are answered from a project graph that is still loading. This pins
FSharpLanguageServer._start_server's wait for that notification directly, without spinning up
FsAutoComplete: F# language server tests are unconditionally disabled (test/conftest.py,
category 1, "F# language server is currently unreliable"), so a live-LS test can never run
here or on CI.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from solidlsp.language_servers.fsharp_language_server import FSharpLanguageServer

_WORKSPACE_LOAD_FINISHED = '{"Kind":"workspaceLoad","Data":{"Status":"finished"}}'


class _FakeServer:
    """A stand-in for the LSP process which reports a project load as FsAutoComplete does."""

    def __init__(self, workspace_load_delay: float | None) -> None:
        self._workspace_load_delay = workspace_load_delay
        self._notification_handlers: dict[str, Callable[[dict], None]] = {}
        self.workspace_load_reported_at: float | None = None
        self.send = self
        self.notify = self

    def on_notification(self, method: str, handler: Callable[[dict], None]) -> None:
        self._notification_handlers[method] = handler

    def on_request(self, method: str, handler: Callable[[dict], Any]) -> None:
        pass

    def start(self) -> None:
        pass

    def initialize(self, params: dict) -> dict:
        return {"capabilities": {}}

    def initialized(self, params: dict) -> None:
        if self._workspace_load_delay is not None:
            threading.Timer(self._workspace_load_delay, self._report_workspace_load).start()

    def _report_workspace_load(self) -> None:
        self.workspace_load_reported_at = time.perf_counter()
        self._notification_handlers["fsharp/notifyWorkspace"]({"content": _WORKSPACE_LOAD_FINISHED})


def _fsharp_ls(repository_root_path: str, workspace_load_delay: float | None) -> tuple[FSharpLanguageServer, _FakeServer]:
    """Instance without running __init__ (no dotnet tool install, no process); same technique
    as test_fsharp_module_selection_range.py's _bare_fsharp_server.

    The fake is returned alongside the server so assertions read it directly rather than
    through the server's typed `server` attribute.
    """
    fake = _FakeServer(workspace_load_delay)
    ls = object.__new__(FSharpLanguageServer)
    ls.repository_root_path = repository_root_path
    ls.server_ready = threading.Event()
    ls.server = fake
    ls._create_initialize_params = dict
    return ls, fake


def test_start_returns_only_after_the_workspace_has_been_loaded(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "TestProject.fsproj").write_text("<Project />")
    monkeypatch.setattr(FSharpLanguageServer, "WORKSPACE_LOAD_TIMEOUT", 5.0)
    ls, fake = _fsharp_ls(str(tmp_path), workspace_load_delay=0.5)

    started_at = time.perf_counter()
    ls._start_server()
    returned_at = time.perf_counter()

    assert fake.workspace_load_reported_at is not None, "the fake server never reported a project load"
    assert returned_at > fake.workspace_load_reported_at
    # the wait must end because the notification arrived, not because it timed out
    assert returned_at - started_at < 5.0


def test_start_does_not_wait_when_there_is_no_project_to_load(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "script.fsx").write_text("let x = 1")
    monkeypatch.setattr(FSharpLanguageServer, "WORKSPACE_LOAD_TIMEOUT", 0.2)
    ls, _ = _fsharp_ls(str(tmp_path), workspace_load_delay=None)

    started_at = time.perf_counter()
    ls._start_server()

    assert time.perf_counter() - started_at < 0.2


def test_start_gives_up_when_the_workspace_load_is_never_reported(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "TestProject.fsproj").write_text("<Project />")
    monkeypatch.setattr(FSharpLanguageServer, "WORKSPACE_LOAD_TIMEOUT", 0.2)
    ls, _ = _fsharp_ls(str(tmp_path), workspace_load_delay=None)

    started_at = time.perf_counter()
    ls._start_server()

    # the lower bound allows for a wait that returns a hair early on a coarse platform clock
    assert 0.15 <= time.perf_counter() - started_at < 1.0
    assert ls.server_ready.is_set(), "the timeout branch must release anything else waiting on readiness"
