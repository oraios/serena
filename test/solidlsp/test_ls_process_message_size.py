"""Unit tests for the LSP wire-size guards in ``solidlsp.ls_process``.

Regression coverage for the unbounded-allocation memory leak (see issue #944): a language
server that declares an oversized ``Content-Length`` must not drive an unbounded read.
Instead the read loop aborts with a ``LanguageServerTerminatedException`` so the server is
torn down and restarted rather than exhausting host memory.
"""

import io
from unittest.mock import MagicMock

import pytest

from solidlsp.ls_config import Language
from solidlsp.ls_process import (
    MAX_LSP_MESSAGE_SIZE,
    LanguageServerTerminatedException,
    StdioLanguageServer,
    _check_message_size,
)


def test_check_message_size_allows_normal_and_boundary() -> None:
    # Values within the limit, and exactly at the limit, are accepted (no exception).
    _check_message_size(0, Language.PYTHON)
    _check_message_size(1024, Language.PYTHON)
    _check_message_size(MAX_LSP_MESSAGE_SIZE, Language.PYTHON)


def test_check_message_size_rejects_oversized() -> None:
    with pytest.raises(LanguageServerTerminatedException) as excinfo:
        _check_message_size(MAX_LSP_MESSAGE_SIZE + 1, Language.PYTHON)
    assert excinfo.value.language == Language.PYTHON
    assert str(MAX_LSP_MESSAGE_SIZE + 1) in str(excinfo.value)


def test_check_message_size_rejects_negative() -> None:
    # A negative Content-Length is malformed and must be rejected, not silently accepted.
    with pytest.raises(LanguageServerTerminatedException):
        _check_message_size(-1, Language.PYTHON)


class _FakeProcess:
    """Minimal stand-in for ``subprocess.Popen`` exposing only what the reader touches."""

    def __init__(self, stdout: io.BytesIO) -> None:
        self.stdout = stdout

    def poll(self) -> None:
        # Report the process as still running so the loop reads the frame rather than
        # breaking out early on termination.
        return None


def test_read_loop_aborts_on_oversized_frame_without_allocating() -> None:
    """The real stdout read loop must abort on an oversized declared frame.

    Regression for the memory-exhaustion bug: a header declaring a body far larger than
    the limit must terminate the reader (via ``_cancel_pending_requests``) *before* the
    body read, rather than attempting the allocation.
    """
    oversized = MAX_LSP_MESSAGE_SIZE + 1
    stdout = io.BytesIO(f"Content-Length: {oversized}\r\n\r\n".encode())

    ls = object.__new__(StdioLanguageServer)  # bypass the heavy real __init__
    ls.process = _FakeProcess(stdout)
    ls.language = Language.PYTHON
    ls._is_stopping = False
    ls._cancel_pending_requests = MagicMock()

    # Must return promptly (no hang, no multi-GB allocation).
    ls._read_ls_process_stdout()

    ls._cancel_pending_requests.assert_called_once()
    (raised,) = ls._cancel_pending_requests.call_args.args
    assert isinstance(raised, LanguageServerTerminatedException)
    assert str(oversized) in str(raised)
