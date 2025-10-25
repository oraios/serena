"""
Tests covering TCP transport setup for the GDScript language server handler.
"""

import io
import socket
import subprocess
import threading

from solidlsp.ls_handler import SolidLanguageServerHandler
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo


class _DummyStream(io.BytesIO):
    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):  # no-op for BytesIO
        pass


class _DummySocket:
    def __init__(self):
        self.closed = False
        self.timeout = None
        self.timeouts: list[float | None] = []

    def settimeout(self, timeout):
        self.timeout = timeout
        self.timeouts.append(timeout)

    def setsockopt(self, *_args):
        pass

    def makefile(self, mode):
        return _DummyStream()

    def close(self):
        self.closed = True


class _DummyProcess:
    def __init__(self):
        self.stdout = None
        self.stderr = None
        self.stdin = None
        self._returncode = None

    @property
    def returncode(self):
        return self._returncode

    def poll(self):
        return self._returncode

    def terminate(self):
        self._returncode = 0

    def wait(self, timeout=None):
        return self._returncode

    def kill(self):
        self._returncode = -9


def test_tcp_transport_uses_socket(monkeypatch):
    """Ensure TCP transport bypasses stdio pipes and connects via socket."""

    captured: dict[str, object] = {}

    dummy_process = _DummyProcess()

    real_popen = subprocess.Popen

    def fake_popen(cmd, stdout=None, stdin=None, stderr=None, **kwargs):  # type: ignore[override]
        cmd_list = cmd if isinstance(cmd, list) else [cmd]
        if any(str(part).startswith("fake-godot") for part in cmd_list):
            captured["cmd"] = cmd
            captured["stdout"] = stdout
            captured["stdin"] = stdin
            captured["stderr"] = stderr
            return dummy_process
        return real_popen(cmd, stdout=stdout, stdin=stdin, stderr=stderr, **kwargs)

    monkeypatch.setattr("solidlsp.ls_handler.subprocess.Popen", fake_popen)

    dummy_socket = _DummySocket()

    def fake_create_connection(addr, timeout=None):
        captured["addr"] = addr
        captured["timeout"] = timeout
        return dummy_socket

    monkeypatch.setattr("solidlsp.ls_handler.socket.create_connection", fake_create_connection)

    # Prevent reader threads from actually running during the test.
    class DummyThread:
        def __init__(self, target, name=None, daemon=None):
            self._target = target

        def start(self):
            pass

    monkeypatch.setattr("solidlsp.ls_handler.threading.Thread", DummyThread)

    launch_info = ProcessLaunchInfo(
        cmd=["fake-godot"],
        cwd=".",
        tcp_host="127.0.0.1",
        tcp_port=4242,
        tcp_connection_timeout=1.0,
    )

    handler = SolidLanguageServerHandler(launch_info, logger=None)
    handler.start()

    try:
        assert captured["stdout"] is subprocess.DEVNULL
        assert captured["stdin"] is subprocess.DEVNULL
        assert captured["stderr"] is subprocess.DEVNULL
        assert captured["addr"] == ("127.0.0.1", 4242)
        assert handler._transport_is_tcp  # type: ignore[attr-defined]
        assert handler._stdin_stream is not None  # type: ignore[attr-defined]
        assert handler._stdout_stream is not None  # type: ignore[attr-defined]
        assert not dummy_socket.closed
        assert dummy_socket.timeouts and dummy_socket.timeouts[-1] is None
    finally:
        handler.stop()
        assert dummy_socket.closed
