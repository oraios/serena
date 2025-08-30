"""Regression tests for generic handler stderr behavior (post-refactor).

Previous tests asserted Roslyn internal error counting inside the generic
`SolidLanguageServerHandler` implementation. That logic has been moved into the
`CSharpLanguageServer` via a language-specific `stderr_line_filter`. The generic
handler must now:

* Remain agnostic about Roslyn-specific signatures (no counters / suppression).
* Still log arbitrary stderr lines (including the Roslyn signature) at INFO/ERROR.

This test purposefully feeds signature lines through a bare handler and asserts:
1. No attribute like `_roslyn_internal_error_count` exists.
2. Lines (including the signature) are logged (appear in captured logs).

Language-specific filtering & suppression are covered in
`test_csharp_roslyn_internal_error_filter.py`.
"""

import logging

import pytest

from solidlsp.ls_handler import SolidLanguageServerHandler
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo

SIGNATURE = "unexpected value kind: null"


class _DummyStderr:
    def __init__(self, lines):
        self._lines = [l.encode("utf-8") for l in lines]
        self._i = 0

    def readline(self):
        if self._i < len(self._lines):
            line = self._lines[self._i]
            self._i += 1
            return line
        return b""


class _DummyProc:
    def __init__(self, lines):
        self.stderr = _DummyStderr(lines)

    def poll(self):  # returns None (running) until all lines consumed, then 0
        return 0 if self.stderr._i >= len(self.stderr._lines) else None


@pytest.fixture
def handler(monkeypatch):
    # Construct real handler (so stderr_line_filter attribute exists) but skip starting a process.
    pli = ProcessLaunchInfo(cmd=["echo"], cwd=".", env={})
    h = SolidLanguageServerHandler(pli, logger=None)
    # Avoid unexpected thread warnings - mark shutting down after read.
    return h


def test_generic_handler_logs_signature_without_roslyn_counters(handler, caplog):
    lines = ["preface line", f"{SIGNATURE} occurred", f"{SIGNATURE} again"]
    handler.process = _DummyProc(lines)
    handler._is_shutting_down = True  # suppress unexpected termination warning
    caplog.set_level(logging.INFO, logger="solidlsp.ls_handler")

    # Execute stderr reader loop (will exit after feeding lines)
    handler._read_ls_process_stderr()

    # Generic handler must not have Roslyn-specific counter attributes
    assert not hasattr(handler, "_roslyn_internal_error_count")

    # All signature lines should appear verbatim in logs (no filter suppression)
    text = caplog.text.lower()
    assert SIGNATURE in text
    # Ensure we logged at least the two signature occurrences
    assert text.count(SIGNATURE) >= 2
