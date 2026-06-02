import asyncio
import json
import logging
import os
import socket
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from typing import IO, Any, AnyStr

from sensai.util.string import ToStringMixin

from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_request import LanguageServerRequest
from solidlsp.lsp_protocol_handler.lsp_requests import LspNotification
from solidlsp.lsp_protocol_handler.lsp_types import ErrorCodes
from solidlsp.lsp_protocol_handler.server import (
    ENCODING,
    LSPError,
    PayloadLike,
    ProcessLaunchInfo,
    StringDict,
    content_length,
    create_message,
    make_error_response,
    make_notification,
    make_request,
    make_response,
)
from solidlsp.util import subprocess_util

log = logging.getLogger(__name__)


class LanguageServerTerminatedException(Exception):
    """
    Exception raised when the language server process has terminated unexpectedly.
    """

    def __init__(self, message: str, language: Language, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.language = language
        self.cause = cause

    def __str__(self) -> str:
        return f"LanguageServerTerminatedException: {self.message}" + (f"; Cause: {self.cause}" if self.cause else "")


class Request(ToStringMixin):
    @dataclass
    class Result:
        payload: PayloadLike | None = None
        error: Exception | None = None

        def is_error(self) -> bool:
            return self.error is not None

    def __init__(self, request_id: int, method: str) -> None:
        self._request_id = request_id
        self._method = method
        self._status = "pending"
        self._result_queue: Queue[Request.Result] = Queue()

    def _tostring_includes(self) -> list[str]:
        return ["_request_id", "_status", "_method"]

    def on_result(self, params: PayloadLike) -> None:
        self._status = "completed"
        self._result_queue.put(Request.Result(payload=params))

    def on_error(self, err: Exception) -> None:
        """
        :param err: the error that occurred while processing the request (typically an LSPError
            for errors returned by the LS or LanguageServerTerminatedException if the error
            is due to the language server process terminating unexpectedly).
        """
        self._status = "error"
        self._result_queue.put(Request.Result(error=err))

    def get_result(self, timeout: float | None = None) -> Result:
        try:
            return self._result_queue.get(timeout=timeout)
        except Empty as e:
            if timeout is not None:
                raise TimeoutError(f"Request timed out ({timeout=})") from e
            raise e


class LanguageServerInterface(ABC):
    """
    Represents an interface to a language server, providing methods for communicating with it using the
    Language Server Protocol (LSP).

    It provides methods for sending requests, responses, and notifications to the server
    and for registering handlers for requests and notifications from the server.

    Uses JSON-RPC 2.0 for communication with the server over stdin/stdout.
    """

    def __init__(
        self,
        language: Language,
        determine_log_level: Callable[[str], int],
        logger: Callable[[str, str, StringDict | str], None] | None = None,
        request_timeout: float | None = None,
    ) -> None:
        """
        :param language: the language
        :param determine_log_level: a function for log lines read from stderr, which determines the log level
        :param logger: the trace logger function
        :param request_timeout: the timeout, in seconds, for all requests sent to the language server. If None, no timeout will be applied.
        """
        self.language = language
        self._determine_log_level = determine_log_level
        self.send = LanguageServerRequest(self)
        """
        an object that can be used to send requests to the server 
        """
        self.notify = LspNotification(self.send_notification)
        """
        an object that can be used to send notifications to the server
        """
        self.request_id = 1
        """
        the next request id to use for requests
        """
        self._pending_requests: dict[Any, Request] = {}
        """
        maps request ids to Request objects that store the results or errors of the requests
        """
        self.on_request_handlers: dict[str, Callable[[Any], Any]] = {}
        self.on_notification_handlers: dict[str, Callable[[Any], None]] = {}
        """
        maps method names to callback functions that handle notifications from the server
        """
        self._notification_observers: list[Callable[[str, Any], None]] = []
        self._trace_log_fn = logger
        self.task_counter = 0
        self._is_stopping = False
        """
        Flag indicating whether the interface is in the process of stopping (or already stopped).
        Exception handlers should check this flag to avoid logging errors that are caused by the interface being stopped.
        """
        self._incoming_messages_queue: Queue[bytes] = Queue()
        self._request_timeout = request_timeout

        # Add thread locks for shared resources to prevent race conditions
        self._request_id_lock = threading.Lock()
        self._response_handlers_lock = threading.Lock()
        self._tasks_lock = threading.Lock()

    def set_request_timeout(self, timeout: float | None) -> None:
        """
        :param timeout: the timeout, in seconds, for all requests sent to the language server.
        """
        self._request_timeout = timeout

    @abstractmethod
    def is_running(self) -> bool:
        """
        Checks whether the language server interface is running
        """

    def start(self) -> None:
        """
        Starts communication with the language server
        """
        self._is_stopping = False
        self._start()

    @abstractmethod
    def _start(self) -> None:
        """
        Starts the actual communication mechanism with the language server, calling `_handle_body` for each message received from the
        language server
        """

    def stop(self, timeout: float = 5.0) -> None:
        """
        Terminates communication with the language server, freeing resources

        :param timeout: the maximum time, in seconds, to wait for the language server to terminate before forcefully killing it
            (if applicable)
        """
        if not self.is_running():
            log.debug("Server process not running, skipping shutdown.")
            return

        self._is_stopping = True

        log.info(f"Initiating shutdown with a {timeout}s timeout...")
        self._stop(timeout)

    @abstractmethod
    def _stop(self, timeout: float) -> None:
        pass

    def _send_shutdown(self) -> None:
        """
        Signals shutdown to the server
        """
        log.info("Sending shutdown request to server")
        self.send.shutdown()
        log.info("Received shutdown response from server")
        log.info("Sending exit notification to server")
        self.notify.exit()
        log.info("Sent exit notification to server")

    def _send_shutdown_in_thread(self) -> None:
        """
        Signals shutdown to the server in a separate thread (requests can hang),
        and waits for the thread to complete with a timeout.

        :param timeout: timeout, in seconds, to wait for the requests to be handled
        """
        log.debug("Sending LSP shutdown request...")
        shutdown_thread = threading.Thread(target=self._send_shutdown)
        shutdown_thread.daemon = True
        shutdown_thread.start()
        shutdown_thread.join(timeout=2.0)
        if shutdown_thread.is_alive():
            log.debug("LSP shutdown request timed out, proceeding to terminate...")
        else:
            log.debug("LSP shutdown request completed.")

    def _trace(self, src: str, dest: str, message: str | StringDict) -> None:
        """
        Traces LS communication by logging the message with the source and destination of the message
        """
        if self._trace_log_fn is not None:
            self._trace_log_fn(src, dest, message)

    def _handle_body(self, body: bytes) -> None:
        """
        Parses the body text received from the language server process and invokes the appropriate handler
        """
        try:
            self._receive_payload(json.loads(body))
        except OSError as ex:
            log.error(f"Error processing payload: {ex}", exc_info=ex)
        except UnicodeDecodeError as ex:
            log.error(f"Decoding error for encoding={ENCODING}: {ex}")
        except json.JSONDecodeError as ex:
            log.error(f"JSON decoding error: {ex}")

    def _receive_payload(self, payload: StringDict) -> None:
        """
        Determine if the payload received from server is for a request, response, or notification and invoke the appropriate handler
        """
        self._trace("ls", "solidlsp", payload)
        try:
            if "method" in payload:
                if "id" in payload:
                    self._request_handler(payload)
                else:
                    self._notification_handler(payload)
            elif "id" in payload:
                self._response_handler(payload)
            else:
                log.error(f"Unknown payload type: {payload}")
        except Exception as err:
            log.error(f"Error handling server payload: {err}")

    def send_notification(self, method: str, params: dict | None = None) -> None:
        """
        Send notification pertaining to the given method to the server with the given parameters
        """
        self._send_payload(make_notification(method, params))

    def send_response(self, request_id: Any, params: PayloadLike) -> None:
        """
        Send response to the given request id to the server with the given parameters
        """
        self._send_payload(make_response(request_id, params))

    def send_error_response(self, request_id: Any, err: LSPError) -> None:
        """
        Send error response to the given request id to the server with the given error
        """
        self._send_payload(make_error_response(request_id, err))

    def _cancel_pending_requests(self, exception: Exception) -> None:
        """
        Cancel all pending requests by setting their results to an error
        """
        with self._response_handlers_lock:
            log.info("Cancelling %d pending language server requests", len(self._pending_requests))
            for request in self._pending_requests.values():
                log.info("Cancelling %s", request)
                request.on_error(exception)
            self._pending_requests.clear()

    def send_request(self, method: str, params: dict | None = None) -> PayloadLike:
        """
        Send request to the server, register the request id, and wait for the response
        """
        with self._request_id_lock:
            request_id = self.request_id
            self.request_id += 1

        request = Request(request_id=request_id, method=method)
        log.debug("Starting: %s", request)

        with self._response_handlers_lock:
            self._pending_requests[request_id] = request

        self._send_payload(make_request(method, request_id, params))

        log.debug("Waiting for response to request %s with params:\n%s", method, params)
        result = request.get_result(timeout=self._request_timeout)
        log.debug("Completed: %s", request)

        if result.is_error():
            raise SolidLSPException(f"Error processing request {method} with params:\n{params}", cause=result.error) from result.error

        log.debug("Returning result:\n%s", result.payload)
        return result.payload

    @abstractmethod
    def _send_payload(self, payload: StringDict) -> None:
        """
        Send the given payload to the server
        """

    def on_request(self, method: str, cb: Callable[[Any], Any]) -> None:
        """
        Register the callback function to handle requests from the server to the client for the given method
        """
        self.on_request_handlers[method] = cb

    def on_notification(self, method: str, cb: Callable[[Any], None]) -> None:
        """
        Register the callback function to handle notifications from the server to the client for the given method
        """
        self.on_notification_handlers[method] = cb

    def on_any_notification(self, cb: Callable[[str, Any], None]) -> None:
        """
        Register an observer that is invoked for every notification received from the server.
        """
        self._notification_observers.append(cb)

    def _response_handler(self, response: StringDict) -> None:
        """
        Handle the response received from the server for a request, using the id to determine the request
        """
        response_id = response["id"]
        with self._response_handlers_lock:
            request = self._pending_requests.pop(response_id, None)
            if request is None and isinstance(response_id, str) and response_id.isdigit():
                request = self._pending_requests.pop(int(response_id), None)

            if request is None:  # need to convert response_id to the right type
                log.debug("Request interrupted by user or not found for ID %s", response_id)
                return

        if "result" in response and "error" not in response:
            request.on_result(response["result"])
        elif "result" not in response and "error" in response:
            request.on_error(LSPError.from_lsp(response["error"]))
        else:
            request.on_error(LSPError(ErrorCodes.InvalidRequest, ""))

    def _request_handler(self, response: StringDict) -> None:
        """
        Handle the request received from the server: call the appropriate callback function and return the result
        """
        method = response.get("method", "")
        params = response.get("params")
        request_id = response.get("id")
        handler = self.on_request_handlers.get(method)
        if not handler:
            self.send_error_response(
                request_id,
                LSPError(
                    ErrorCodes.MethodNotFound,
                    f"method '{method}' not handled on client.",
                ),
            )
            return
        try:
            self.send_response(request_id, handler(params))
        except LSPError as ex:
            self.send_error_response(request_id, ex)
        except Exception as ex:
            self.send_error_response(request_id, LSPError(ErrorCodes.InternalError, str(ex)))

    def _notification_handler(self, response: StringDict) -> None:
        """
        Handle the notification received from the server: call the appropriate callback function
        """
        method = response.get("method", "")
        params = response.get("params")

        for observer in self._notification_observers:
            try:
                observer(method, params)
            except asyncio.CancelledError:
                return
            except Exception as ex:
                if not self._is_stopping:
                    log.error("Error handling notification observer for method '%s': %s", method, ex, exc_info=ex)

        handler = self.on_notification_handlers.get(method)
        if not handler:
            log.warning("Unhandled method '%s'", method)
            return
        try:
            handler(params)
        except asyncio.CancelledError:
            return
        except Exception as ex:
            if not self._is_stopping:
                log.error("Error handling notification for method '%s': %s", method, ex, exc_info=ex)


class StdioLanguageServer(LanguageServerInterface):
    """
    Represents a language server interface where the language server is launched as a subprocess
    and communication takes place over the process' stdin/stdout streams.
    """

    def __init__(
        self,
        process_launch_info: ProcessLaunchInfo,
        language: Language,
        determine_log_level: Callable[[str], int],
        logger: Callable[[str, str, StringDict | str], None] | None = None,
        start_independent_lsp_process: bool = True,
        request_timeout: float | None = None,
    ) -> None:
        """
        :param process_launch_info: the information required to launch the language server process
        :param language: the language
        :param determine_log_level: a function for log lines read from stderr, which determines the log level
        :param logger: the trace logger function
        :param start_independent_lsp_process: whether to start the language server process in an independent process group
        :param request_timeout: the timeout, in seconds, for all requests sent to the language server. If None, no timeout will be applied.
        """
        super().__init__(language, determine_log_level, logger, request_timeout)

        self.process_launch_info = process_launch_info
        self.process: subprocess.Popen[bytes] | None = None
        self.start_independent_lsp_process = start_independent_lsp_process

        self._stdin_lock = threading.Lock()

    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def _start(self) -> None:
        child_proc_env = os.environ.copy()
        child_proc_env.update(self.process_launch_info.env)

        cmd = subprocess_util.convert_shell_cmd(self.process_launch_info.cmd)
        log.info("Starting language server process via command: %s", self.process_launch_info.cmd)
        kwargs = subprocess_util.subprocess_kwargs()
        kwargs["start_new_session"] = self.start_independent_lsp_process
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=child_proc_env,
            cwd=self.process_launch_info.cwd,
            shell=True,
            **kwargs,
        )

        # Check if process terminated immediately
        if self.process.returncode is not None:
            log.error("Language server has already terminated/could not be started")
            # Process has already terminated
            stderr_data = self.process.stderr.read() if self.process.stderr else b""
            error_message = stderr_data.decode("utf-8", errors="replace")
            raise RuntimeError(f"Process terminated immediately with code {self.process.returncode}. Error: {error_message}")

        # start threads to read stdout and stderr of the process
        threading.Thread(
            target=self._read_ls_process_stdout,
            name=f"LSP-stdout-reader:{self.language.value}",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_ls_process_stderr,
            name=f"LSP-stderr-reader:{self.language.value}",
            daemon=True,
        ).start()

    def _stop(self, timeout: float) -> None:
        if self.process is None:
            log.debug("Server process is None, cannot shutdown.")
            return

        try:
            # send LSP shutdown and close stdin to signal no more input
            try:
                self._send_shutdown_in_thread()
                self._safely_close_pipe(self.process.stdin)
            except Exception as e:
                log.debug(f"Exception during graceful shutdown: {e}")
                # Ignore errors here, we are proceeding to terminate anyway.
            # terminate the process
            subprocess_util.terminate_process_tree_with_kill_fallback(
                self.process, terminate_timeout=timeout, process_name=f"LS[{self.language.value}]"
            )
        finally:
            self.process = None

    @staticmethod
    def _safely_close_pipe(pipe: IO[AnyStr] | None) -> None:
        """Safely close a pipe, ignoring any exceptions."""
        if pipe and not pipe.closed:
            try:
                pipe.close()
            except Exception:
                pass

    def _read_bytes_from_process(self, process, stream, num_bytes) -> bytes:  # type: ignore
        """Read exactly num_bytes from process stdout"""
        data = b""
        while len(data) < num_bytes:
            chunk = stream.read(num_bytes - len(data))
            if not chunk:
                if process.poll() is not None:
                    raise LanguageServerTerminatedException(
                        f"Process terminated while trying to read response (read {len(data)} of {num_bytes} bytes before termination)",
                        language=self.language,
                    )
                # Process still running but no data available yet, retry after a short delay
                time.sleep(0.01)
                continue
            data += chunk
        return data

    def _read_ls_process_stdout(self) -> None:
        """
        Continuously read from the language server process stdout and handle the messages
        invoking the registered response and notification handlers
        """
        exception: Exception | None = None
        try:
            while self.process and self.process.stdout:
                if self.process.poll() is not None:  # process has terminated
                    break
                line = self.process.stdout.readline()
                if not line:
                    continue
                try:
                    num_bytes = content_length(line)
                except ValueError:
                    continue
                if num_bytes is None:
                    continue
                while line and line.strip():
                    line = self.process.stdout.readline()
                if not line:
                    continue
                body = self._read_bytes_from_process(self.process, self.process.stdout, num_bytes)

                self._handle_body(body)
        except LanguageServerTerminatedException as e:
            exception = e
        except (BrokenPipeError, ConnectionResetError) as e:
            exception = LanguageServerTerminatedException("Language server process terminated while reading stdout", self.language, cause=e)
        except Exception as e:
            exception = LanguageServerTerminatedException(
                "Unexpected error while reading stdout from language server process", self.language, cause=e
            )
        log.info("Language server stdout reader thread has terminated")
        if not self._is_stopping:
            if exception is None:
                exception = LanguageServerTerminatedException("Language server stdout read process terminated unexpectedly", self.language)
            log.error(str(exception))
            self._cancel_pending_requests(exception)

    def _read_ls_process_stderr(self) -> None:
        """
        Continuously read from the language server process stderr and log the messages
        """
        try:
            while self.process and self.process.stderr:
                if self.process.poll() is not None:
                    # process has terminated
                    break
                line = self.process.stderr.readline()
                if not line:
                    continue
                line_str = line.decode(ENCODING, errors="replace")
                level = self._determine_log_level(line_str)
                log.log(level, line_str)
        except Exception as e:
            log.error("Error while reading stderr from language server process: %s", e, exc_info=e)
        if not self._is_stopping:
            log.error("Language server stderr reader thread terminated unexpectedly")
        else:
            log.info("Language server stderr reader thread has terminated")

    def _send_payload(self, payload: StringDict) -> None:
        if not self.process or not self.process.stdin:
            return
        self._trace("solidlsp", "ls", payload)
        msg = create_message(payload)

        # Use lock to prevent concurrent writes to stdin that cause buffer corruption
        with self._stdin_lock:
            try:
                self.process.stdin.writelines(msg)
                self.process.stdin.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                # Log the error but don't raise to prevent cascading failures
                log.error(f"Failed to write to stdin: {e}")
                return


@dataclass
class TCPConnectionInfo:
    """Connection parameters for an LSP server reachable over a TCP socket."""

    host: str = "127.0.0.1"
    port: int = 6008
    connection_timeout: float = 30.0
    retry_interval: float = 1.0


class TCPLanguageServer(LanguageServerInterface):
    """LanguageServerInterface that connects to an already-running LSP server over TCP.

    Unlike :class:`StdioLanguageServer`, this class does not own the server process — it
    connects to an externally-managed server (e.g. the Godot editor) and simply closes
    the socket on stop. No LSP ``shutdown``/``exit`` sequence is sent, because the remote
    server is expected to keep running after Serena disconnects.
    """

    def __init__(
        self,
        connection_info: TCPConnectionInfo,
        language: Language,
        determine_log_level: Callable[[str], int],
        logger: Callable[[str, str, StringDict | str], None] | None = None,
        request_timeout: float | None = None,
    ) -> None:
        super().__init__(language, determine_log_level, logger, request_timeout)
        self._connection_info = connection_info
        self._sock: socket.socket | None = None
        self._file: Any = None  # socket.makefile("rb") - buffered reader
        self._write_lock = threading.Lock()

    def is_running(self) -> bool:
        return self._sock is not None

    def _start(self) -> None:
        deadline = time.monotonic() + self._connection_info.connection_timeout
        last_exc: Exception | None = None
        while True:
            try:
                sock = socket.create_connection((self._connection_info.host, self._connection_info.port), timeout=5.0)
                sock.settimeout(None)
                self._sock = sock
                self._file = sock.makefile("rb")
                log.info("TCPLanguageServer connected to %s:%d", self._connection_info.host, self._connection_info.port)
                break
            except OSError as exc:
                last_exc = exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"Could not connect to {self._connection_info.host}:{self._connection_info.port} "
                        f"within {self._connection_info.connection_timeout}s"
                    ) from last_exc
                log.debug(
                    "TCPLanguageServer: connection failed (%s), retrying in %.1fs (%.0fs left)",
                    exc,
                    self._connection_info.retry_interval,
                    remaining,
                )
                time.sleep(min(self._connection_info.retry_interval, remaining))

        threading.Thread(
            target=self._read_loop,
            name=f"LSP-tcp-reader:{self.language.value}",
            daemon=True,
        ).start()

    def _stop(self, timeout: float) -> None:
        # Close the socket first — this unblocks any readline() in the reader thread.
        # BufferedReader.close() acquires an internal lock that readline() holds while
        # blocked waiting for data; closing the socket first causes readline() to return
        # with an error, releasing the lock before we call f.close().
        sock = self._sock
        self._sock = None
        f = self._file
        self._file = None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
        if f:
            try:
                f.close()
            except Exception:
                pass

    def _send_payload(self, payload: StringDict) -> None:
        sock = self._sock
        if sock is None:
            return
        self._trace("solidlsp", "ls", payload)
        data = b"".join(create_message(payload))
        with self._write_lock:
            try:
                sock.sendall(data)
            except OSError as e:
                log.error("Failed to write to TCP language server: %s", e)
                self._sock = None
                self._file = None
                self._cancel_pending_requests(LanguageServerTerminatedException("TCP send error", self.language, cause=e))

    def _read_loop(self) -> None:
        """Read Content-Length-framed LSP messages from the TCP socket and dispatch them."""
        exception: Exception | None = None
        try:
            while self._sock is not None:
                f = self._file
                if f is None:
                    break
                try:
                    line = f.readline()
                except OSError as exc:
                    if not self._is_stopping:
                        exception = LanguageServerTerminatedException("TCP read error", self.language, cause=exc)
                    break
                if not line:
                    break
                try:
                    num_bytes = content_length(line)
                except ValueError:
                    continue
                if num_bytes is None:
                    continue
                while line and line.strip():
                    try:
                        line = f.readline()
                    except OSError:
                        line = b""
                        break
                if not line:
                    continue
                try:
                    body = f.read(num_bytes)
                except OSError as exc:
                    if not self._is_stopping:
                        exception = LanguageServerTerminatedException("TCP read error", self.language, cause=exc)
                    break
                if len(body) < num_bytes:
                    break
                self._handle_body(body)
        except Exception as exc:
            exception = LanguageServerTerminatedException("Unexpected error in TCP language server read loop", self.language, cause=exc)
        log.info("TCP language server read loop has terminated")
        if not self._is_stopping:
            if exception is None:
                exception = LanguageServerTerminatedException("TCP language server read loop terminated unexpectedly", self.language)
            log.error(str(exception))
            self._cancel_pending_requests(exception)
            # Clear the socket so is_running() returns False, allowing _ensure_functional_ls
            # to detect the broken connection and restart the language server.
            self._sock = None
            self._file = None
