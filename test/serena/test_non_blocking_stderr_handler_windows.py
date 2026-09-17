# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sys

import pytest

from serena.util.non_blocking_stderr_handler import NonBlockingStderrHandler


@pytest.mark.skipif(sys.platform != "win32", reason="PIPE_NOWAIT path is Windows-only")
def test_windows_pipe_writer_enables_nonblocking_on_pipe():
    import os

    r, w = os.pipe()
    try:
        writer = NonBlockingStderrHandler._WindowsPipeRecordWriter(w)
        assert writer._nonblocking is True
    finally:
        os.close(r)
        os.close(w)


def test_windows_error_no_data_maps_to_blocking_io_error(monkeypatch):
    if sys.platform != "win32":
        # construct the mapping without a real Windows pipe
        writer = NonBlockingStderrHandler._WindowsPipeRecordWriter.__new__(NonBlockingStderrHandler._WindowsPipeRecordWriter)
        writer._fd = 1
        writer._nonblocking = True

        class _OSError(OSError):
            winerror = NonBlockingStderrHandler._ERROR_NO_DATA

        monkeypatch.setattr(os, "write", lambda *a, **k: (_ for _ in ()).throw(_OSError(232, "pipe full")))
        with pytest.raises(BlockingIOError):
            writer.write("x")
    else:
        r, w = os.pipe()
        try:
            writer = NonBlockingStderrHandler._WindowsPipeRecordWriter(w)
            # fill the pipe until write fails (should not hang)
            import errno

            for _ in range(10_000):
                try:
                    os.write(w, b"x" * 4096)
                except OSError as e:
                    assert e.winerror in (NonBlockingStderrHandler._ERROR_NO_DATA, errno.ENOBUFS)
                    break
            else:
                pytest.fail("pipe never reported full")
        finally:
            os.close(r)
            os.close(w)
