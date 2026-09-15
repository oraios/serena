# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import stat
import sys

from serena.constants import SERENA_LOG_FORMAT


class NonBlockingStderrHandler(logging.Handler):
    """
    A logging handler that writes formatted records to stderr without ever blocking the caller.

    This is a drop-in replacement for ``logging.StreamHandler(stream=sys.stderr)`` for the
    MCP server's logging setup. A blocking ``StreamHandler`` on stderr is dangerous in the MCP
    scenario: some client hosts never read the spawned server process' stderr at all. Since
    stderr is then a socketpair with a finite buffer (64 KiB), the handler eventually blocks
    inside ``write()`` — while holding the logging module's global lock — and freezes every
    other thread that logs. Observed in practice: a tool whose work completed in milliseconds
    never returned its result because the post-completion ``save_all_caches`` logging call
    hung, surfacing as a ``tool_timeout`` exactly ``tool_timeout`` seconds later.

    The write is issued directly from ``emit`` on a non-blocking file descriptor (pipes and
    sockets only; a tty is written normally, as it cannot fill up). If the stderr buffer is
    full (``BlockingIOError``) or only part of the message fits, the record is dropped. The
    authoritative log streams — the log file written by ``start-mcp-server`` /
    ``project-server`` and the in-memory buffer exposed via the dashboard — remain synchronous
    and lossless; only this best-effort console stream can lose records, and only while its
    consumer is not draining it.

    No background thread is used: a daemon thread stuck in a blocking ``write`` would
    deadlock CPython's interpreter shutdown (``PyThreadState_Clear`` waits for the thread's
    frame), trading one hang for another.
    """

    def __init__(self, stream=None, level: int = logging.NOTSET) -> None:
        """
        :param stream: the stream to write to; defaults to ``sys.stderr``
        :param level: the handler level
        """
        super().__init__(level=level)
        self._stream = stream if stream is not None else sys.stderr
        self.setFormatter(logging.Formatter(SERENA_LOG_FORMAT))
        self._fd: int | None = None
        self._nonblocking_fd = False
        try:
            fileno = self._stream.fileno()
            mode = os.fstat(fileno).st_mode
            # pipes (incl. socketpairs) and sockets have a bounded buffer: make the fd
            # non-blocking so that a full buffer raises instead of blocking the caller
            if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
                os.set_blocking(fileno, False)
                self._nonblocking_fd = True
            self._fd = fileno
        except (AttributeError, OSError, ValueError):
            # no usable fileno (e.g. StringIO in tests): fall back to stream.write
            self._fd = None

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        data = (msg + "\n").encode(errors="replace")
        try:
            if self._fd is not None:
                self._write_fd(data)
            else:
                self._stream.write(msg + "\n")
        except (BlockingIOError, OSError, ValueError):
            # stderr buffer full (or fd gone): drop the record rather than blocking the
            # logging lock — the log file and the dashboard buffer remain lossless
            pass

    def _write_fd(self, data: bytes) -> None:
        """Writes `data` to the raw fd, dropping the remainder if the buffer is full."""
        written = os.write(self._fd, data)
        if written < len(data):
            # partial write: the buffer filled up mid-message; drop the rest instead of
            # retrying (a retry loop could still block if the consumer never drains)
            pass

    def flush(self) -> None:
        """Flushes the underlying stream if it provides one (non-blocking fds need no flush)."""
        try:
            if self._fd is None:
                self._stream.flush()
        except (OSError, ValueError):
            pass
