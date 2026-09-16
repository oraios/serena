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

    The write strategy is determined once at construction time and is one of:

    * non-blocking ``os.write`` on a pipe/socket file descriptor made non-blocking: when the
      buffer is full (``BlockingIOError``) or only part of the message fits, the record is
      dropped instead of blocking the logging lock
    * plain ``os.write`` on other file descriptors (tty, regular file): these have no bounded
      buffer that a non-draining consumer would let fill up
    * plain ``stream.write`` when the stream has no usable file descriptor (e.g. ``StringIO``)

    The authoritative log streams — the log file written by ``start-mcp-server`` /
    ``project-server`` and the in-memory buffer exposed via the dashboard — remain synchronous
    and lossless; only this best-effort console stream can lose records, and only while its
    consumer is not draining it.

    Limitation: on Windows, anonymous pipes are neither reported as FIFOs by ``fstat`` nor
    can they be made non-blocking (``os.set_blocking`` does not exist), so stderr writes there
    remain blocking, exactly as with a plain ``StreamHandler``.

    No background thread is used: a daemon thread stuck in a blocking ``write`` would
    deadlock CPython's interpreter shutdown (``PyThreadState_Clear`` waits for the thread's
    frame), trading one hang for another.
    """

    class _RecordWriter:
        """
        Writes formatted log records to the handler's destination.

        Subclasses encapsulate the concrete write mechanism; dropping a record that cannot
        be delivered is the handler's concern and happens uniformly via the exceptions
        raised by ``write``.
        """

        def write(self, msg: str) -> None:
            """
            Writes `msg` (without trailing newline) to the destination.
            """
            raise NotImplementedError

        def flush(self) -> None:
            """
            Flushes the destination; writers on raw file descriptors need no flush.
            """

    class _StreamRecordWriter(_RecordWriter):
        """
        Writes records via a stream object's ``write``/``flush``, for streams without a
        usable file descriptor (e.g. ``StringIO``).
        """

        def __init__(self, stream) -> None:
            self._stream = stream

        def write(self, msg: str) -> None:
            self._stream.write(msg)

        def flush(self) -> None:
            self._stream.flush()

    class _FdRecordWriter(_RecordWriter):
        """
        Writes records directly on a file descriptor.
        """

        def __init__(self, fd: int) -> None:
            self._fd = fd

        def write(self, msg: str) -> None:
            # a partial write means the buffer filled up mid-message; the remainder is
            # dropped rather than retried (a retry loop could still block if the consumer
            # never drains)
            os.write(self._fd, msg.encode(errors="replace"))

    class _NonBlockingFdRecordWriter(_FdRecordWriter):
        """
        Writes records on a pipe/socket file descriptor made non-blocking, so that a full
        buffer raises ``BlockingIOError`` (caught by the handler, which then drops the
        record) instead of blocking the caller.
        """

        def __init__(self, fd: int) -> None:
            super().__init__(fd)
            try:
                os.set_blocking(fd, False)
            except (AttributeError, OSError):
                # non-blocking mode is unavailable (e.g. os.set_blocking does not exist on
                # Windows); degrade to blocking writes, as with a plain StreamHandler
                pass

    def __init__(self, stream=None, level: int = logging.NOTSET) -> None:
        """
        :param stream: the stream to write to; defaults to ``sys.stderr``
        :param level: the handler level
        """
        super().__init__(level=level)
        self._stream = stream if stream is not None else sys.stderr
        self.setFormatter(logging.Formatter(SERENA_LOG_FORMAT))
        self._writer = self._create_writer(self._stream)

    def _create_writer(self, stream) -> _RecordWriter:
        """
        Determines the write strategy for `stream` exactly once, so that ``emit`` never has
        to branch on a nullable file descriptor.
        """
        try:
            fd = stream.fileno()
            mode = os.fstat(fd).st_mode

            # pipes (incl. socketpairs) and sockets have a bounded buffer: make the fd
            # non-blocking so that a full buffer raises instead of blocking the caller
            if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
                return self._NonBlockingFdRecordWriter(fd)

            # other descriptors (tty, regular file) have no bounded buffer to guard against
            return self._FdRecordWriter(fd)
        except (AttributeError, OSError, ValueError):
            # no usable fileno: write via the stream object instead
            return self._StreamRecordWriter(stream)

    def emit(self, record: logging.LogRecord) -> None:
        # stderr buffer full (or destination gone): drop the record rather than blocking the
        # logging lock — the log file and the dashboard buffer remain lossless; handleError
        # is deliberately not called, as it would itself write to stderr
        try:
            self._writer.write(self.format(record) + "\n")
        except (BlockingIOError, OSError, ValueError):
            pass

    def flush(self) -> None:
        self._writer.flush()
