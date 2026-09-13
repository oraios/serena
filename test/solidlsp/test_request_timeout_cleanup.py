"""Unit tests: a request that times out is removed from ``LanguageServerInterface._pending_requests``.

``_pending_requests`` holds the requests that are still being awaited. Until issue #2003 the only
place an entry was ever removed was ``_response_handler``, which runs when a response arrives, so a
request that timed out against a hung (but still running) server kept its entry for the lifetime of
the server: the caller had already given up, and nothing would ever pop it.

No language markers: these use a local test double and run in catch-all.
"""

from __future__ import annotations

import logging

import pytest

from solidlsp.ls_config import LanguageServerId
from solidlsp.ls_process import LanguageServerInterface, Request


class _HungServer(LanguageServerInterface):
    """Test double for a server that is running but never answers: the payload goes nowhere."""

    def __init__(self, request_timeout: float = 0.05) -> None:
        super().__init__(LanguageServerId.PYTHON, lambda _line: logging.INFO, request_timeout=request_timeout)
        self.sent_requests: list[Request] = []

    def is_running(self) -> bool:
        return True

    def _start(self) -> None:
        pass

    def _stop(self, timeout: float) -> None:
        pass

    def _send_payload(self, payload: dict) -> None:
        self.sent_requests.append(self._pending_requests[payload["id"]])


class _AnsweringServer(LanguageServerInterface):
    """Test double that answers every request synchronously, as a control for the timeout case."""

    def __init__(self) -> None:
        super().__init__(LanguageServerId.PYTHON, lambda _line: logging.INFO, request_timeout=5)

    def is_running(self) -> bool:
        return True

    def _start(self) -> None:
        pass

    def _stop(self, timeout: float) -> None:
        pass

    def _send_payload(self, payload: dict) -> None:
        self._response_handler({"id": payload["id"], "result": {"contents": "ok"}})


def test_timed_out_requests_do_not_accumulate() -> None:
    server = _HungServer()

    for _ in range(3):
        with pytest.raises(TimeoutError):
            server.send_request("textDocument/documentSymbol")

    assert len(server.sent_requests) == 3
    assert server._pending_requests == {}


def test_a_late_response_to_a_timed_out_request_is_discarded() -> None:
    """The server can still answer after the caller has given up. The response must not be delivered to
    a request nobody is reading, and it must not put the entry back.
    """
    server = _HungServer()
    with pytest.raises(TimeoutError):
        server.send_request("textDocument/documentSymbol")
    abandoned = server.sent_requests[0]

    server._response_handler({"id": 1, "result": {"contents": "too late"}})

    assert server._pending_requests == {}
    with pytest.raises(TimeoutError):
        abandoned.get_result(timeout=0.05)


def test_answered_requests_also_leave_no_entry_behind() -> None:
    server = _AnsweringServer()
    assert server.send_request("textDocument/hover") == {"contents": "ok"}
    assert server._pending_requests == {}


def test_cancelling_after_a_timeout_only_sees_the_live_request() -> None:
    """``_cancel_pending_requests`` pushes an error into every entry it finds, so a request that has
    already timed out would be counted in its log line and sent a result nobody reads.
    """
    server = _HungServer()
    with pytest.raises(TimeoutError):
        server.send_request("textDocument/documentSymbol")

    live = Request(request_id=99, method="textDocument/hover")
    server._pending_requests[99] = live

    assert list(server._pending_requests) == [99]

    server._cancel_pending_requests(RuntimeError("server gone"))
    assert live.get_result(timeout=0.05).is_error()
