"""Unit tests: ``LanguageServerInterface.send_request`` retries LSP ``ContentModified`` errors.

Per the LSP spec, ``ContentModified`` (-32801) means the server discarded a stale, in-flight
computation because the workspace changed underneath it, not that the request itself is
invalid -- clients are expected to retry. This is what caused issue #1724 (flaky
``test_find_symbol[rust_add_function]`` on windows-latest): rust-analyzer returns
``ContentModified`` for cancelled hover requests, and Serena surfaced it as a hard error.

Retrying is only spec-compliant for methods the client actually declared, via
``general.staleRequestSupport.retryOnContentModified`` in its InitializeParams, that it will
retry -- so ``send_request`` only retries methods registered with it through
``set_content_modified_retry_methods`` (see ``SolidLanguageServer._create_initialize_params``).

No language markers: these use a local test double and run in catch-all.
"""

from __future__ import annotations

import logging

import pytest

from solidlsp import ls_process
from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_process import LanguageServerInterface, Request
from solidlsp.lsp_protocol_handler.lsp_types import LSPErrorCodes
from solidlsp.lsp_protocol_handler.server import LSPError


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """The retry delay is only there to be polite to the real server; don't pay for it in tests."""
    monkeypatch.setattr(ls_process.time, "sleep", lambda _seconds: None)


class _ScriptedServer(LanguageServerInterface):
    """Test double that answers each request synchronously from a scripted list of results,
    without a real language server process.
    """

    def __init__(self, results: list[Request.Result], retry_methods: tuple[str, ...] = ("textDocument/hover",)) -> None:
        super().__init__(Language.PYTHON, lambda _line: logging.INFO)
        self._results = list(results)
        self.sent_payload_count = 0
        self.set_content_modified_retry_methods(retry_methods)

    def is_running(self) -> bool:
        return True

    def _start(self) -> None:
        pass

    def _stop(self, timeout: float) -> None:
        pass

    def _send_payload(self, payload: dict) -> None:
        self.sent_payload_count += 1
        request = self._pending_requests[payload["id"]]
        result = self._results.pop(0)
        if result.is_error():
            request.on_error(result.error)
        else:
            request.on_result(result.payload)


def _content_modified() -> Request.Result:
    return Request.Result(error=LSPError(LSPErrorCodes.ContentModified, "content modified"))


def test_content_modified_is_retried_until_success() -> None:
    server = _ScriptedServer([_content_modified(), _content_modified(), Request.Result(payload={"contents": "ok"})])
    assert server.send_request("textDocument/hover") == {"contents": "ok"}
    assert server.sent_payload_count == 3


def test_content_modified_gives_up_after_max_attempts() -> None:
    max_attempts = ls_process._CONTENT_MODIFIED_MAX_ATTEMPTS
    server = _ScriptedServer([_content_modified() for _ in range(max_attempts)])
    with pytest.raises(SolidLSPException):
        server.send_request("textDocument/hover")
    assert server.sent_payload_count == max_attempts


def test_other_lsp_errors_are_not_retried() -> None:
    server = _ScriptedServer([Request.Result(error=LSPError(LSPErrorCodes.RequestFailed, "boom"))])
    with pytest.raises(SolidLSPException):
        server.send_request("textDocument/hover")
    assert server.sent_payload_count == 1


def test_request_cancelled_is_not_retried() -> None:
    """-32800 is client-initiated cancellation per the LSP spec, so it must not be retried here."""
    server = _ScriptedServer([Request.Result(error=LSPError(LSPErrorCodes.RequestCancelled, "cancelled"))])
    with pytest.raises(SolidLSPException):
        server.send_request("textDocument/hover")
    assert server.sent_payload_count == 1


def test_content_modified_is_not_retried_for_undeclared_method() -> None:
    """Retrying is a promise to the server about which methods will be reissued (per
    ``general.staleRequestSupport.retryOnContentModified``); a method that was never registered
    via ``set_content_modified_retry_methods`` must not be retried, even on ContentModified.
    This also covers non-idempotent requests like ``workspace/executeCommand``, which no server
    declaration should ever include.
    """
    server = _ScriptedServer([_content_modified()], retry_methods=("textDocument/hover",))
    with pytest.raises(SolidLSPException):
        server.send_request("workspace/executeCommand")
    assert server.sent_payload_count == 1


def test_content_modified_retry_methods_default_to_empty() -> None:
    """A server that never calls `set_content_modified_retry_methods` must not retry anything."""
    server = _ScriptedServer([_content_modified()], retry_methods=())
    with pytest.raises(SolidLSPException):
        server.send_request("textDocument/hover")
    assert server.sent_payload_count == 1
