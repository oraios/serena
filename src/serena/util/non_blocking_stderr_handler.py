# SPDX-License-Identifier: GPL-3.0-or-later

import ctypes
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

    * non-blocking ``os.write`` on a POSIX pipe/socket file descriptor made non-blocking: when
      the buffer is full (``BlockingIOError``), the record is dropped instead of blocking the
      logging lock. Records longer than the fd's atomic write size (``PIPE_BUF``) are
      truncated to it first, so that a partially free buffer can never elicit a partial
      write (POSIX guarantees all-or-nothing writes only up to ``PIPE_BUF``)
    * on Windows, ``PIPE_NOWAIT`` via ``SetNamedPipeHandleState`` for anonymous/named pipes
      (oraios/serena#2047, follow-up to #2044): a full pipe raises ``OSError`` with
      ``ERROR_NO_DATA`` and the record is dropped, matching the POSIX contract
    * plain ``os.write`` on other file descriptors (tty, regular file): these have no bounded
      buffer that a non-draining consumer would let fill up
    * plain ``stream.write`` when the stream has no usable file descriptor (e.g. ``StringIO``)

    The authoritative log streams — the log file written by ``start-mcp-server`` /
    ``project-server`` and the in-memory buffer exposed via the dashboard — remain synchronous
    and lossless; only this best-effort console stream can lose records, and only while its
    consumer is not draining it.

    Residual Windows limitation: if ``SetNamedPipeHandleState(PIPE_NOWAIT)`` cannot be applied
    (unsupported handle type, or the deprecated API is removed in a future Windows release),
    the writer falls back to blocking ``os.write``, exactly as with a plain ``StreamHandler``.
    ``PIPE_NOWAIT`` is documented as deprecated by Microsoft but remains the only in-process
    way to make an anonymous pipe non-blocking without a helper thread.

    No background thread is used: a daemon thread stuck in a blocking ``write`` would
    deadlock CPython's interpreter shutdown (``PyThreadState_Clear`` waits for the thread's
    frame), trading one hang for another.
    """

    _PIPE_NOWAIT = 0x00000001
    _ERROR_NO_DATA = 232
    _ERROR_BROKEN_PIPE = 109
    _ERROR_PIPE_NOT_CONNECTED = 233
    _WINDOWS_FULL_PIPE_ERRORS = frozenset({_ERROR_NO_DATA, _ERROR_BROKEN_PIPE, _ERROR_PIPE_NOT_CONNECTED})

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

        Records longer than the fd's atomic write size are truncated before writing:
        POSIX guarantees all-or-nothing behaviour for non-blocking pipe writes only up to
        ``PIPE_BUF`` bytes (queryable via ``os.fpathconf(fd, "PC_PIPE_BUF")``) — a longer
        record would be written partially when the buffer had some but not enough free
        space, corrupting the stream with a truncated, newline-less record.
        """

        _TRUNCATION_SUFFIX = "... [truncated]\n"

        def __init__(self, fd: int) -> None:
            super().__init__(fd)
            try:
                os.set_blocking(fd, False)
            except (AttributeError, OSError):
                # non-blocking mode is unavailable (e.g. os.set_blocking does not exist on
                # Windows); degrade to blocking writes, as with a plain StreamHandler
                pass
            try:
                atomic_write_size = os.fpathconf(fd, "PC_PIPE_BUF")
            except (AttributeError, OSError, ValueError):
                atomic_write_size = None
            # POSIX requires PIPE_BUF >= 512; treat a missing/invalid value conservatively
            self._atomic_write_size = atomic_write_size if atomic_write_size and atomic_write_size > 0 else 512

        def write(self, msg: str) -> None:
            encoded = msg.encode(errors="replace")
            suffix = self._TRUNCATION_SUFFIX.encode()
            if len(encoded) > self._atomic_write_size:
                # reserve 3 bytes: a truncation point inside a multi-byte sequence may
                # expand to a 3-byte replacement character when decoded
                payload = encoded[: self._atomic_write_size - len(suffix) - 3].decode(errors="replace")
                encoded = (payload + self._TRUNCATION_SUFFIX).encode(errors="replace")
            os.write(self._fd, encoded)

    class _WindowsPipeRecordWriter(_FdRecordWriter):
        """
        Windows pipe writer that sets ``PIPE_NOWAIT`` so a full buffer fails the write
        instead of blocking (oraios/serena#2047).

        ``SetNamedPipeHandleState`` is the documented (if deprecated) way to make an
        anonymous pipe non-blocking in-process. When the call fails, the writer keeps
        blocking semantics rather than inventing a thread (see the handler docstring).
        """

        def __init__(self, fd: int) -> None:
            super().__init__(fd)
            self._nonblocking = self._enable_pipe_nowait(fd)

        @staticmethod
        def _enable_pipe_nowait(fd: int) -> bool:
            try:
                import msvcrt

                handle = msvcrt.get_osfhandle(fd)
            except (ImportError, OSError, ValueError):
                return False
            try:
                mode = ctypes.c_ulong(NonBlockingStderrHandler._PIPE_NOWAIT)
                ok = ctypes.windll.kernel32.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None)
                return bool(ok)
            except Exception:
                return False

        def write(self, msg: str) -> None:
            try:
                os.write(self._fd, msg.encode(errors="replace"))
            except OSError as e:
                # full non-blocking pipe or peer gone: drop, never block
                winerror = getattr(e, "winerror", None)
                if winerror in NonBlockingStderrHandler._WINDOWS_FULL_PIPE_ERRORS:
                    raise BlockingIOError(winerror, "pipe full or disconnected") from e
                raise

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
        except (AttributeError, OSError, ValueError):
            # no usable fileno: write via the stream object instead
            return self._StreamRecordWriter(stream)

        if sys.platform == "win32":
            # anonymous pipes are not S_ISFIFO on Windows; try PIPE_NOWAIT first
            writer = self._WindowsPipeRecordWriter(fd)
            if writer._nonblocking:
                return writer
            # not a pipe we can switch: tty / regular file / unsupported handle
            return self._FdRecordWriter(fd)

        try:
            mode = os.fstat(fd).st_mode

            # pipes (incl. socketpairs) and sockets have a bounded buffer: make the fd
            # non-blocking so that a full buffer raises instead of blocking the caller
            if stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
                return self._NonBlockingFdRecordWriter(fd)

            # other descriptors (tty, regular file) have no bounded buffer to guard against
            return self._FdRecordWriter(fd)
        except (OSError, ValueError):
            return self._FdRecordWriter(fd)

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
