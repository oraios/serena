from unittest.mock import MagicMock

import pytest

from solidlsp.ls import SolidLanguageServer


class _RaisingLanguageServer(SolidLanguageServer):
    """Bypasses SolidLanguageServer.__init__ (like DummyLanguageServer in
    test_rename_didopen.py) so _start_server can be made to raise after the underlying
    process is already considered running, without spinning up a real language server.
    """

    def _start_server(self) -> None:
        raise RuntimeError("simulated: capability assertion failed after initialize()")

    def _create_base_initialize_params(self) -> dict:
        return {}


def _make_server(is_running: bool) -> _RaisingLanguageServer:
    server = object.__new__(_RaisingLanguageServer)
    server.ls_id = "python"
    server.repository_root_path = "/tmp/project"
    server.server_started = False
    server.server = MagicMock()
    server.server.is_running.return_value = is_running
    return server


def test_start_stops_process_when_start_server_raises_after_spawning():
    """_start_server() spawning the OS process and then raising (e.g. a capability
    assertion or an initialize() timeout firing post-spawn) must not leak that process:
    start() itself stops it before re-raising.
    """
    server = _make_server(is_running=True)

    with pytest.raises(RuntimeError, match="capability assertion"):
        server.start()

    server.server.stop.assert_called_once()
    assert server.server_started is False


def test_start_still_calls_stop_when_start_server_raises_before_spawning():
    """start() must call stop() even when _start_server() raises before any process was ever
    spawned (e.g. a subclass acquires some other resource in __init__/create_launch_command
    before the process exists, as Eclipse JDTLS's workspace lock does) - ls_manager.py's
    multi-server startup depends on "start() cleans up after itself on failure" holding
    unconditionally, not just for post-spawn failures. stop() is documented to never raise,
    so calling it here is safe even though there is no OS process to actually stop.
    """
    server = _make_server(is_running=False)

    with pytest.raises(RuntimeError, match="capability assertion"):
        server.start()

    server.server.stop.assert_called_once()
    assert server.server_started is False
