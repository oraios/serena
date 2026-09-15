# SPDX-License-Identifier: MIT

"""Unit tests: a failed stdin write must fail the pending request (#2004).

``StdioLanguageServer._send_payload`` used to swallow ``BrokenPipeError`` /
``ConnectionResetError`` / ``OSError`` and return, stranding the just-registered
request until its timeout. A failed write means the server is gone, so the honest
outcome is ``LanguageServerTerminatedException``: the restart path's signal, and
what the stdout-reader death path and ``TCPLanguageServer`` already emit.

Two kinds of failed write matter. A pipe that broke raises from the ``OSError``
family; a stdin that ``_stop`` already closed raises ``ValueError``.
"""

import logging
import subprocess
import sys
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_process import (
    LanguageServerTerminatedException,
    Request,
    StdioLanguageServer,
)
from solidlsp.util.subprocess_util import ManagedSubprocess


def _server() -> StdioLanguageServer:
    return StdioLanguageServer(
        process_launch_info=MagicMock(),
        ls_id=LanguageServerId.PYTHON,
        determine_log_level=lambda _line: logging.INFO,
    )


def _server_with_failing_stdin(exc: Exception) -> StdioLanguageServer:
    server = _server()
    process = MagicMock()
    process.stdin.writelines.side_effect = exc
    server._process = process
    return server


@pytest.fixture()
def server_with_live_process() -> Iterator[StdioLanguageServer]:
    """A server holding a real subprocess, for behaviour a mock cannot model.

    Whether a write reaches closed-file semantics depends on the stream, so the
    closed-stdin case needs an actual pipe rather than a stand-in.
    """
    server = _server()
    popen = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    server._process = ManagedSubprocess(popen, name="Test ls", start_new_session=False)
    yield server
    server._process.terminate(timeout=2)


def test_broken_pipe_fails_pending_request_with_terminated() -> None:
    """#2004: the stranded-until-timeout case now fails fast."""
    server = _server_with_failing_stdin(BrokenPipeError(32, "Broken pipe"))
    request = Request(request_id=1, method="textDocument/hover")
    server._pending_requests[1] = request

    server._send_payload({"jsonrpc": "2.0"})

    result = request.get_result(timeout=10)
    assert result.is_error()
    assert isinstance(result.error, LanguageServerTerminatedException)
    assert isinstance(result.error.cause, BrokenPipeError)
    assert server._pending_requests == {}


def test_closed_stdin_fails_pending_request_with_terminated(server_with_live_process: StdioLanguageServer) -> None:
    """A stdin which ``_stop`` closed raises ``ValueError``, which is not an ``OSError``.

    ``_stop`` closes stdin, then waits for the process to terminate and only afterwards
    nulls ``_process``, so a request sent from another thread lands in that window.
    """
    server = server_with_live_process
    server._safely_close_pipe(server._process.stdin)
    assert server._process.stdin.closed
    request = Request(request_id=4, method="textDocument/hover")
    server._pending_requests[4] = request

    server._send_payload({"jsonrpc": "2.0"})  # must return, not raise

    result = request.get_result(timeout=10)
    assert result.is_error()
    assert isinstance(result.error, LanguageServerTerminatedException)
    assert isinstance(result.error.cause, ValueError)
    assert server._pending_requests == {}


def test_failed_write_does_not_raise_from_send_payload() -> None:
    """Failing the request must not become a raise: no cascading failures."""
    server = _server_with_failing_stdin(ConnectionResetError("reset by peer"))
    request = Request(request_id=2, method="textDocument/hover")
    server._pending_requests[2] = request

    server._send_payload({"jsonrpc": "2.0"})  # must return, not raise

    result = request.get_result(timeout=10)
    assert result.is_error()
    assert isinstance(result.error, LanguageServerTerminatedException)


def test_healthy_write_leaves_request_pending() -> None:
    """The normal path is untouched: no error is synthesized on success."""
    server = _server_with_failing_stdin(BrokenPipeError(32, "Broken pipe"))
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
