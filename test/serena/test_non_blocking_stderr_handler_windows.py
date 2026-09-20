# SPDX-License-Identifier: GPL-3.0-or-later

import errno
import os
import sys

import pytest

from serena.util.non_blocking_stderr_handler import NonBlockingStderrHandler


@pytest.mark.skipif(sys.platform != "win32", reason="PIPE_NOWAIT path is Windows-only")
def test_windows_pipe_writer_enables_nonblocking_on_pipe():
    r, w = os.pipe()
    try:
        writer = NonBlockingStderrHandler._WindowsPipeRecordWriter(w)
        assert writer._nonblocking is True
    finally:
        os.close(r)
        os.close(w)


def test_windows_full_pipe_errors_map_to_blocking_io_error(monkeypatch):
    """CI showed Windows can raise ENOSPC (errno 28) with winerror unset, not only ERROR_NO_DATA."""
    writer = NonBlockingStderrHandler._WindowsPipeRecordWriter.__new__(NonBlockingStderrHandler._WindowsPipeRecordWriter)
    writer._fd = 1
    writer._nonblocking = True

    class _WinErr(OSError):
        winerror = NonBlockingStderrHandler._ERROR_NO_DATA

    class _Enospc(OSError):
        winerror = None

        def __init__(self):
            super().__init__(errno.ENOSPC, "No space left on device")

    with pytest.raises(BlockingIOError):
        monkeypatch.setattr(os, "write", lambda *a, **k: (_ for _ in ()).throw(_WinErr(232, "pipe full")))
        writer.write("x")

    with pytest.raises(BlockingIOError):
        monkeypatch.setattr(os, "write", lambda *a, **k: (_ for _ in ()).throw(_Enospc()))
        writer.write("x")


@pytest.mark.skipif(sys.platform != "win32", reason="live full-pipe exercise is Windows-only")
def test_windows_live_full_pipe_does_not_hang():
    r, w = os.pipe()
    try:
        NonBlockingStderrHandler._WindowsPipeRecordWriter(w)
        for _ in range(10_000):
            try:
                os.write(w, b"x" * 4096)
            except OSError as e:
                assert e.winerror in NonBlockingStderrHandler._WINDOWS_FULL_PIPE_ERRORS or e.errno in (
                    errno.ENOSPC,
                    errno.ENOBUFS,
                    errno.EPIPE,
                )
                break
        else:
            pytest.fail("pipe never reported full")
    finally:
        os.close(r)
        os.close(w)
