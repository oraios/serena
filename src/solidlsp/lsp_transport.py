"""
LSP transport abstraction layer.

Provides the LSPTransport ABC and StdioTransport (subprocess stdio) implementation.
Additional transports (TCP, WebSocket) will be added in a follow-up.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import Any, cast

import psutil

from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import LanguageServerTerminatedException
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.util.subprocess_util import quote_arg, subprocess_kwargs

log = logging.getLogger(__name__)


class LSPTransport(ABC):
    """Abstract base class for LSP communication transports.

    The contract for read/write methods is fail-loud: if the transport is not
    alive (or becomes not alive mid-call), they raise
    :class:`LanguageServerTerminatedException` rather than returning empty
    bytes. Callers running a read loop should guard with :meth:`is_alive` and
    treat the exception as a normal termination signal.
    """

    @abstractmethod
    def start(self) -> None:
        """Start the transport (launch process, open socket, etc.)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the transport immediately and release all resources.

        For a graceful shutdown with bounded escalation, use :meth:`shutdown`.
        """

    @abstractmethod
    def shutdown(self, timeout: float) -> None:
        """Shut down the transport gracefully, escalating to forceful termination.

        Implementations should:
          1. Signal the peer that no more input is coming (e.g., close write side).
          2. Wait up to ``timeout`` seconds for the peer to exit on its own.
          3. Escalate to forceful termination if it does not.
          4. Release all resources.
        """

    @abstractmethod
    def is_alive(self) -> bool:
        """Return True if the transport is active and ready for I/O."""

    @abstractmethod
    def write(self, chunks: Iterable[bytes]) -> None:
        """Write chunks to the transport. Implementations must be thread-safe.

        Raises:
            LanguageServerTerminatedException: if the transport is not alive
                or the write fails because the peer is gone.

        """

    @abstractmethod
    def read_line(self) -> bytes:
        """Read one header line.

        Raises:
            LanguageServerTerminatedException: on EOF or after stop().

        """

    @abstractmethod
    def read_bytes(self, n: int) -> bytes:
        """Read exactly n bytes.

        Raises:
            LanguageServerTerminatedException: on transport termination.

        """


class StdioTransport(LSPTransport):
    """LSP transport over subprocess stdin/stdout/stderr.

    The transport owns its stderr reader thread internally. Construct with a
    ``stderr_handler`` to receive each raw stderr line as bytes; the handler
    decides what to do with it (decode, parse severity, log, discard, route
    elsewhere). If no handler is provided, stderr is not read.
    """

    def __init__(
        self,
        process_launch_info: ProcessLaunchInfo,
        language: Language,
        start_independent_lsp_process: bool = True,
        stderr_handler: Callable[[bytes], None] | None = None,
    ) -> None:
        """
        :param process_launch_info: command, working directory, and environment for the subprocess.
        :param language: the language served by this transport (used in error messages and thread names).
        :param start_independent_lsp_process: if True, the subprocess is launched in its own
            session/process group so SIGINT/SIGTERM to the parent does not propagate to it.
        :param stderr_handler: optional callback invoked with each raw stderr line (including its
            trailing newline). When provided, the transport spawns an internal reader thread that
            forwards every line to this handler until EOF. When ``None``, stderr is not consumed and
            the OS pipe buffer may eventually fill — supply a handler unless the LS is known not to
            write to stderr.
        """
        self._process_launch_info = process_launch_info
        self._language = language
        self._start_independent_lsp_process = start_independent_lsp_process
        self._stderr_handler = stderr_handler
        self._process: subprocess.Popen[bytes] | None = None
        self._stdin_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        child_proc_env = os.environ.copy()
        child_proc_env.update(self._process_launch_info.env)
        cmd = self._process_launch_info.cmd
        is_windows = platform.system() == "Windows"
        if not isinstance(cmd, str) and not is_windows:
            cmd = " ".join(map(quote_arg, cmd))
        log.info("Starting language server process via command: %s", self._process_launch_info.cmd)
        kwargs = subprocess_kwargs()
        kwargs["start_new_session"] = self._start_independent_lsp_process
        # cast: Popen stubs type shell=True+str as Popen[str], but PIPE streams are always bytes
        self._process = cast(
            "subprocess.Popen[bytes]",
            subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_proc_env,
                cwd=self._process_launch_info.cwd,
                shell=True,
                **kwargs,
            ),
        )
        if self._process.returncode is not None:
            log.error("Language server has already terminated/could not be started")
            stderr_data = self._process.stderr.read() if self._process.stderr else b""
            error_message = stderr_data.decode("utf-8", errors="replace")
            raise RuntimeError(f"Process terminated immediately with code {self._process.returncode}. Error: {error_message}")

        if self._stderr_handler is not None:
            self._stderr_thread = threading.Thread(
                target=self._read_stderr_loop,
                name=f"LSP-stderr-reader:{self._language.value}",
                daemon=True,
            )
            self._stderr_thread.start()

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process:
            self._cleanup_process(process)

    def shutdown(self, timeout: float) -> None:
        process = self._process
        if process is None:
            return
        # Stage 1: signal end-of-input by closing stdin (under lock so concurrent
        # writers can't have the pipe yanked mid-message).
        with self._stdin_lock:
            self._safely_close_pipe(process.stdin)
        # Stage 2: wait for the peer to exit on its own.
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.debug("LS process did not exit within %.1fs after stdin close, terminating tree", timeout)
            self._signal_process_tree(process, terminate=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning("LS process tree termination timed out after %.1fs, killing", timeout)
                self._signal_process_tree(process, terminate=False)
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    log.error("LS process could not be killed within %.1fs", timeout)
        # Stage 3: release pipes; drop the reference so is_alive() reports False.
        self._safely_close_pipe(process.stdout)
        self._safely_close_pipe(process.stderr)
        self._process = None

    def is_alive(self) -> bool:
        process = self._process
        if process is None:
            return False
        # poll() is required to refresh returncode; without it a dead child looks alive forever
        return process.poll() is None

    def write(self, chunks: Iterable[bytes]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise LanguageServerTerminatedException(
                "Cannot write: language server transport is not running",
                language=self._language,
            )
        with self._stdin_lock:
            if process.stdin.closed:
                raise LanguageServerTerminatedException(
                    "Cannot write: language server stdin is closed",
                    language=self._language,
                )
            try:
                process.stdin.writelines(chunks)
                process.stdin.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                raise LanguageServerTerminatedException(
                    "Failed to write to language server stdin",
                    language=self._language,
                    cause=e,
                ) from e

    def read_line(self) -> bytes:
        process = self._process
        if process is None or process.stdout is None:
            raise LanguageServerTerminatedException(
                "Cannot read: language server transport is not running",
                language=self._language,
            )
        line = process.stdout.readline()
        if not line:
            raise LanguageServerTerminatedException(
                "EOF on stdout: language server has terminated",
                language=self._language,
            )
        return line

    def read_bytes(self, n: int) -> bytes:
        process = self._process
        if process is None or process.stdout is None:
            raise LanguageServerTerminatedException(
                "Cannot read: language server transport is not running",
                language=self._language,
            )
        data = b""
        while len(data) < n:
            chunk = process.stdout.read(n - len(data))
            if not chunk:
                if process.poll() is not None:
                    raise LanguageServerTerminatedException(
                        f"Process terminated while trying to read response (read {len(data)} of {n} bytes before termination)",
                        language=self._language,
                    )
                time.sleep(0.01)
                continue
            data += chunk
        return data

    def _read_stderr_loop(self) -> None:
        """Continuously read raw stderr lines from the subprocess and forward them to the handler."""
        assert self._stderr_handler is not None
        try:
            process = self._process
            if process is None or process.stderr is None:
                return
            for line in iter(process.stderr.readline, b""):
                self._stderr_handler(line)
        except Exception as e:
            log.error("Error while reading stderr from language server: %s", e, exc_info=e)

    def _cleanup_process(self, process: subprocess.Popen[bytes]) -> None:
        # Close stdin first to prevent deadlocks
        # See: https://bugs.python.org/issue35539
        # Take the stdin lock so a concurrent write() can't have the pipe closed mid-message,
        # which would leave the LS waiting on a half-sent body and hang the next request.
        with self._stdin_lock:
            self._safely_close_pipe(process.stdin)
        if process.poll() is None:
            self._signal_process_tree(process, terminate=True)
        # Close stdout and stderr after process has exited to prevent I/O errors during GC
        # See: https://bugs.python.org/issue41320 and https://github.com/python/cpython/issues/88050
        self._safely_close_pipe(process.stdout)
        self._safely_close_pipe(process.stderr)

    def _safely_close_pipe(self, pipe: Any) -> None:
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass

    def _signal_process_tree(self, process: subprocess.Popen[bytes], terminate: bool = True) -> None:
        signal_method = "terminate" if terminate else "kill"
        parent = None
        try:
            parent = psutil.Process(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            pass
        if parent and parent.is_running():
            for child in parent.children(recursive=True):
                try:
                    getattr(child, signal_method)()
                except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                    pass
            try:
                getattr(parent, signal_method)()
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
        else:
            try:
                getattr(process, signal_method)()
            except Exception:
                pass
