"""
Unit tests for companion-process cleanup when an Angular companion fails to start.

Deliberately **not** marked ``angular``: no language server is started, so these belong in the
default suite rather than behind the slow, node-dependent job.

Both companions spawn their node process inside ``server.start()`` and only *then* initialize
(``send.initialize`` plus capability asserts on the response). A failure after the spawn must
still reach ``stop()``, or the process is orphaned: nothing else holds a handle to it once
``_start_*_server`` drops its reference.
"""

import pytest

from solidlsp.language_servers import angular_language_server as als
from solidlsp.ls_config import LanguageServerConfig, LanguageServerId


class _FailsAfterSpawn:
    """Stand-in for a companion whose node process is up but whose initialize fails."""

    def __init__(self, **_kwargs) -> None:
        self.stopped = False

    def start(self) -> None:
        raise RuntimeError("initialize failed after the process was spawned")

    def stop(self) -> None:
        self.stopped = True


def _bare_angular_ls() -> als.AngularLanguageServer:
    """Bypass ``__init__`` (which would install and launch the LS) and set only what the
    ``_start_*_server`` methods read.
    """
    ls = object.__new__(als.AngularLanguageServer)
    ls.config = LanguageServerConfig(ls_id=LanguageServerId.ANGULAR)
    ls.repository_root_path = "/nonexistent"
    ls._solidlsp_settings = None
    ls._angular_plugin_path = "/nonexistent/plugin"
    ls._tsdk_path = "/nonexistent/tsdk"
    ls._ts_ls_executable = "/nonexistent/tsls"
    ls._ts_server = None
    ls._ts_server_started = False
    ls._html_server = None
    ls._html_server_started = False
    return ls


def test_failing_ts_companion_is_stopped_before_the_reference_is_dropped(monkeypatch) -> None:
    spawned: list[_FailsAfterSpawn] = []
    monkeypatch.setattr(als, "AngularTypeScriptServer", lambda **kw: spawned.append(_FailsAfterSpawn()) or spawned[-1])
    ls = _bare_angular_ls()

    with pytest.raises(RuntimeError):
        ls._start_typescript_server()

    assert spawned[0].stopped, "companion was dropped without stop(); its node process is orphaned"
    assert ls._ts_server is None
    assert ls._ts_server_started is False


def test_failing_html_companion_is_stopped_and_startup_continues(monkeypatch) -> None:
    """The HTML companion failure stays non-fatal — but must not leak on the way out."""
    spawned: list[_FailsAfterSpawn] = []
    monkeypatch.setattr(als, "VsCodeHtmlLanguageServer", lambda **kw: spawned.append(_FailsAfterSpawn()) or spawned[-1])
    ls = _bare_angular_ls()

    ls._start_html_server()  # must not raise

    assert spawned[0].stopped, "companion was dropped without stop(); its node process is orphaned"
    assert ls._html_server is None
    assert ls._html_server_started is False
