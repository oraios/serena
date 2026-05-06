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
from collections.abc import Iterable
from typing import Any, cast

import psutil

from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import LanguageServerTerminatedException
from solidlsp.lsp_protocol_handler.server import ProcessLaunchInfo
from solidlsp.util.subprocess_util import quote_arg, subprocess_kwargs

log = logging.getLogger(__name__)


class LSPTransport(ABC):
    """Abstract base class for LSP communication transports."""

    @abstractmethod
    def start(self) -> None:
        """Start the transport (launch process, open socket, etc.)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the transport and release all resources."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Return True if the transport is active and ready for I/O."""

    @abstractmethod
    def write(self, chunks: Iterable[bytes]) -> None:
        """Write chunks to the transport. Implementations must be thread-safe."""

    @abstractmethod
    def read_line(self) -> bytes:
        """Read one header line. Returns b'' on EOF or after stop()."""

    @abstractmethod
    def read_bytes(self, n: int) -> bytes:
        """Read exactly n bytes. Raises LanguageServerTerminatedException on failure."""

    def read_stderr_line(self) -> bytes:
        """Read one line from stderr. Returns b'' if not supported by this transport."""
        return b""


class StdioTransport(LSPTransport):
    """LSP transport over subprocess stdin/stdout/stderr."""

    def __init__(
        self,
        process_launch_info: ProcessLaunchInfo,
        language: Language,
        start_independent_lsp_process: bool = True,
    ) -> None:
        self._process_launch_info = process_launch_info
        self._language = language
        self._start_independent_lsp_process = start_independent_lsp_process
        self._process: subprocess.Popen[bytes] | None = None
        self._stdin_lock = threading.Lock()

    @property
    def process(self) -> subprocess.Popen[bytes] | None:
        """Direct access to the underlying subprocess for subprocess-specific operations."""
        return self._process

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

    def stop(self) -> None:
        process = self._process
        self._process = None
        if process:
            self._cleanup_process(process)

    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None

    def write(self, chunks: Iterable[bytes]) -> None:
        if not self._process or not self._process.stdin:
            return
        with self._stdin_lock:
            try:
                self._process.stdin.writelines(chunks)
                self._process.stdin.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                log.error("Failed to write to stdin: %s", e)

    def read_line(self) -> bytes:
        if not self._process or not self._process.stdout:
            return b""
        return self._process.stdout.readline()

    def read_bytes(self, n: int) -> bytes:
        process = self._process
        if not process or not process.stdout:
            return b""
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

    def read_stderr_line(self) -> bytes:
        if not self._process or not self._process.stderr:
            return b""
        return self._process.stderr.readline()

    def _cleanup_process(self, process: subprocess.Popen[bytes]) -> None:
        # Close stdin first to prevent deadlocks
        # See: https://bugs.python.org/issue35539
        self._safely_close_pipe(process.stdin)
        if process.returncode is None:
            self._terminate_or_kill_process(process)
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

    def _terminate_or_kill_process(self, process: subprocess.Popen[bytes]) -> None:
        self._signal_process_tree(process, terminate=True)

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
