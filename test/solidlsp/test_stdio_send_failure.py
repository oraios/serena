"""Unit tests: a failed stdin write must fail the pending request (#2004).

``StdioLanguageServer._send_payload`` used to swallow ``BrokenPipeError`` /
``ConnectionResetError`` / ``OSError`` and return, stranding the just-registered
request until its timeout (up to 235 s with Serena's defaults). A failed write
means the server is gone, so the honest outcome is
``LanguageServerTerminatedException`` — the restart path's signal, and what the
stdout-reader death path and ``TCPLanguageServer`` already emit.

No language server needed: the process stdin is faked to raise.
"""

import logging
from unittest.mock import MagicMock

from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_process import (
    LanguageServerTerminatedException,
    Request,
    StdioLanguageServer,
)


def _server_with_broken_stdin(exc: Exception) -> StdioLanguageServer:
    server = StdioLanguageServer(
        process_launch_info=MagicMock(),
        ls_id=LanguageServerId.PYTHON,
        determine_log_level=lambda _line: logging.INFO,
    )
    process = MagicMock()
    process.stdin.writelines.side_effect = exc
    server._process = process
    return server


def test_broken_pipe_fails_pending_request_with_terminated() -> None:
    """#2004: the stranded-until-timeout case now fails fast."""
    server = _server_with_broken_stdin(BrokenPipeError(32, "Broken pipe"))
    request = Request(request_id=1, method="textDocument/hover")
    server._pending_requests[1] = request

    server._send_payload({"jsonrpc": "2.0"})

    result = request.get_result(timeout=10)
    assert result.is_error()
    assert isinstance(result.error, LanguageServerTerminatedException)
    assert isinstance(result.error.cause, BrokenPipeError)
    assert server._pending_requests == {}


def test_failed_write_does_not_raise_from_send_payload() -> None:
    """Failing the request must not become a raise: no cascading failures."""
    server = _server_with_broken_stdin(ConnectionResetError("reset by peer"))
    request = Request(request_id=2, method="textDocument/hover")
    server._pending_requests[2] = request

    server._send_payload({"jsonrpc": "2.0"})  # must return, not raise

    result = request.get_result(timeout=10)
    assert result.is_error()
    assert isinstance(result.error, LanguageServerTerminatedException)


def test_healthy_write_leaves_request_pending() -> None:
    """The normal path is untouched: no error is synthesized on success."""
    server = _server_with_broken_stdin(BrokenPipeError(32, "Broken pipe"))
    server._process.stdin.writelines.side_effect = None
    request = Request(request_id=3, method="textDocument/hover")
    server._pending_requests[3] = request

    server._send_payload({"jsonrpc": "2.0"})

    try:
        request.get_result(timeout=0.2)
    except TimeoutError:
        pass
    else:
        raise AssertionError("healthy write should leave the request pending")