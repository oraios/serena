import asyncio
import json
import logging
import os
import platform
import select
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any

import psutil
from sensai.util.string import ToStringMixin

from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_request import LanguageServerRequest
from solidlsp.lsp_protocol_handler.lsp_requests import LspNotification
from solidlsp.lsp_protocol_handler.lsp_types import ErrorCodes
from solidlsp.lsp_protocol_handler.server import (
    ENCODING,
    LSPError,
    MessageType,
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
from solidlsp.util.subprocess_util import subprocess_kwargs

log = logging.getLogger(__name__)


class LanguageServerTerminatedException(Exception):
    """
    Exception raised when the language server process has terminated unexpectedly.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
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
        self._result_queue = Queue()

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


class SolidLanguageServerHandler:
    """
    This class provides the implementation of Python client for the Language Server Protocol.
    A class that launches the language server and communicates with it
    using the Language Server Protocol (LSP).

    It provides methods for sending requests, responses, and notifications to the server
    and for registering handlers for requests and notifications from the server.

    Uses JSON-RPC 2.0 for communication with the server over stdin/stdout.

    Attributes:
        send: A LspRequest object that can be used to send requests to the server and
            await for the responses.
        notify: A LspNotification object that can be used to send notifications to the server.
        cmd: A string that represents the command to launch the language server process.
        process: A subprocess.Popen object that represents the language server process.
        request_id: An integer that represents the next available request id for the client.
        _pending_requests: A dictionary that maps request ids to Request objects that
            store the results or errors of the requests.
        on_request_handlers: A dictionary that maps method names to callback functions
            that handle requests from the server.
        on_notification_handlers: A dictionary that maps method names to callback functions
            that handle notifications from the server.
        logger: An optional function that takes two strings (source and destination) and
            a payload dictionary, and logs the communication between the client and the server.
        tasks: A dictionary that maps task ids to asyncio.Task objects that represent
            the asynchronous tasks created by the handler.
        task_counter: An integer that represents the next available task id for the handler.
        loop: An asyncio.AbstractEventLoop object that represents the event loop used by the handler.
        start_independent_lsp_process: An optional boolean flag that indicates whether to start the
        language server process in an independent process group. Default is `True`. Setting it to
        `False` means that the language server process will be in the same process group as the
        the current process, and any SIGINT and SIGTERM signals will be sent to both processes.

    """

    def __init__(
        self,
        process_launch_info: ProcessLaunchInfo,
        logger: Callable[[str, str, StringDict | str], None] | None = None,
        start_independent_lsp_process=True,
        request_timeout: float | None = None,
    ) -> None:
        self.send = LanguageServerRequest(self)
        self.notify = LspNotification(self.send_notification)

        self.process_launch_info = process_launch_info
        self.process: subprocess.Popen | None = None
        self._is_shutting_down = False

        self.request_id = 1
        self._pending_requests: dict[Any, Request] = {}
        self.on_request_handlers = {}
        self.on_notification_handlers = {}
        self.logger = logger
        self.tasks = {}
        self.task_counter = 0
        self.loop = None
        self.start_independent_lsp_process = start_independent_lsp_process
        self._request_timeout = request_timeout
        self._tcp_socket: socket.socket | None = None
        self._stdout_stream = None
        self._stdin_stream = None
        self._transport_is_tcp = False

        # Add thread locks for shared resources to prevent race conditions
        self._stdin_lock = threading.Lock()
        self._request_id_lock = threading.Lock()
        self._response_handlers_lock = threading.Lock()
        self._tasks_lock = threading.Lock()

    def set_request_timeout(self, timeout: float | None) -> None:
        """
        :param timeout: the timeout, in seconds, for all requests sent to the language server.
        """
        self._request_timeout = timeout

    def get_request_timeout(self) -> float | None:
        """
        :return: the currently configured request timeout in seconds, or None if unlimited.
        """
        return self._request_timeout

    def is_running(self) -> bool:
        """
        Checks if the language server process is currently running.
        """
        if self._transport_is_tcp:
            return self._tcp_socket is not None
        return self.process is not None and self.process.returncode is None

    def start(self) -> None:
        """
        Starts the language server process and creates a task to continuously read from its stdout to handle communications
        from the server to the client
        """
        child_proc_env = os.environ.copy()
        child_proc_env.update(self.process_launch_info.env)

        cmd = self.process_launch_info.cmd
        use_tcp_transport = bool(self.process_launch_info.tcp_host and self.process_launch_info.tcp_port is not None)
        if cmd:
            is_windows = platform.system() == "Windows"
            if not isinstance(cmd, str) and not is_windows:
                # Since we are using the shell, we need to convert the command list to a single string
                # on Linux/macOS
                cmd_to_run = " ".join(cmd)
            else:
                cmd_to_run = cmd
            log.info("Starting language server process via command: %s", self.process_launch_info.cmd)
            kwargs = subprocess_kwargs()
            kwargs["start_new_session"] = self.start_independent_lsp_process

            stdout_sink = subprocess.PIPE
            stdin_sink = subprocess.PIPE
            stderr_sink = subprocess.PIPE
            if use_tcp_transport:
                stdout_sink = subprocess.DEVNULL
                stdin_sink = subprocess.DEVNULL
                stderr_sink = subprocess.DEVNULL

            self.process = subprocess.Popen(
                cmd_to_run,
                stdout=stdout_sink,
                stdin=stdin_sink,
                stderr=stderr_sink,
                env=child_proc_env,
                cwd=self.process_launch_info.cwd,
                shell=True,
                **kwargs,
            )

            # Check if process terminated immediately
            if self.process.returncode is not None:
                log.error("Language server has already terminated/could not be started")
                # Process has already terminated
                stderr_data = self.process.stderr.read()
                error_message = stderr_data.decode("utf-8", errors="replace")
                raise RuntimeError(f"Process terminated immediately with code {self.process.returncode}. Error: {error_message}")
        else:
            log.info("Skipping language server process launch because no command was provided.")
            self.process = None

        self._setup_transport_streams()

        # start threads to read stdout and stderr of the process
        if self._stdout_stream is not None:
            threading.Thread(
                target=self._read_ls_process_stdout,
                name="LSP-stdout-reader",
                daemon=True,
            ).start()
        if self.process and self.process.stderr is not None:
            threading.Thread(
                target=self._read_ls_process_stderr,
                name="LSP-stderr-reader",
                daemon=True,
            ).start()

    def _setup_transport_streams(self) -> None:
        """Configure the reader/writer streams used to communicate with the language server."""
        self._transport_is_tcp = False
        self._tcp_socket = None
        self._stdout_stream = self.process.stdout if self.process else None
        self._stdin_stream = self.process.stdin if self.process else None

        tcp_host = self.process_launch_info.tcp_host
        tcp_port = self.process_launch_info.tcp_port
        if tcp_host and tcp_port is not None:
            connection_deadline = time.time() + max(self.process_launch_info.tcp_connection_timeout, 0)
            last_error: Exception | None = None
            while time.time() < connection_deadline:
                if self.process and self.process.poll() is not None:
                    raise RuntimeError("Language server process terminated before TCP transport became ready")
                try:
                    self._tcp_socket = socket.create_connection((tcp_host, tcp_port), timeout=1.0)
                    break
                except OSError as exc:
                    last_error = exc
                    time.sleep(0.1)
            if not self._tcp_socket:
                raise RuntimeError(f"Timed out connecting to language server TCP endpoint at {tcp_host}:{tcp_port}") from last_error

            try:
                self._tcp_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

            try:
                self._tcp_socket.settimeout(None)
            except OSError:
                pass

            self._stdout_stream = self._tcp_socket  # use raw socket for reading
            self._stdin_stream = self._tcp_socket.makefile("wb")
            self._transport_is_tcp = True
            log.info("Connected to language server TCP endpoint at %s:%s", tcp_host, tcp_port)

    def stop(self) -> None:
        """
        Sends the terminate signal to the language server process and waits for it to exit, with a timeout, killing it if necessary
        """
        process = self.process
        self.process = None
        self._close_transport_streams()
        if process:
            self._cleanup_process(process)

    def _cleanup_process(self, process):
        """Clean up a process: close stdin, terminate/kill process, close stdout/stderr."""
        # Close stdin first to prevent deadlocks
        # See: https://bugs.python.org/issue35539
        self._safely_close_pipe(process.stdin)

        # Terminate/kill the process if it's still running
        if process.returncode is None:
            self._terminate_or_kill_process(process)

        # Close stdout and stderr pipes after process has exited
        # This is essential to prevent "I/O operation on closed pipe" errors and
        # "Event loop is closed" errors during garbage collection
        # See: https://bugs.python.org/issue41320 and https://github.com/python/cpython/issues/88050
        self._safely_close_pipe(process.stdout)
        self._safely_close_pipe(process.stderr)

    def _safely_close_pipe(self, pipe):
        """Safely close a pipe, ignoring any exceptions."""
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass

    def _close_transport_streams(self) -> None:
        """Close any non-stdio transport resources that were created."""
        if self._transport_is_tcp:
            for stream in (self._stdin_stream, self._stdout_stream):
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
            if self._tcp_socket:
                try:
                    self._tcp_socket.close()
                except Exception:
                    pass
        self._tcp_socket = None
        self._stdin_stream = None
        self._stdout_stream = None
        self._transport_is_tcp = False

    def _terminate_or_kill_process(self, process):
        """Try to terminate the process gracefully, then forcefully if necessary."""
        # First try to terminate the process tree gracefully
        self._signal_process_tree(process, terminate=True)

    def _signal_process_tree(self, process, terminate=True):
        """Send signal (terminate or kill) to the process and all its children."""
        signal_method = "terminate" if terminate else "kill"

        # Try to get the parent process
        parent = None
        try:
            parent = psutil.Process(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            pass

        # If we have the parent process and it's running, signal the entire tree
        if parent and parent.is_running():
            # Signal children first
            for child in parent.children(recursive=True):
                try:
                    getattr(child, signal_method)()
                except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                    pass

            # Then signal the parent
            try:
                getattr(parent, signal_method)()
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
        else:
            # Fall back to direct process signaling
            try:
                getattr(process, signal_method)()
            except Exception:
                pass

    def shutdown(self) -> None:
        """
        Perform the shutdown sequence for the client, including sending the shutdown request to the server and notifying it of exit
        """
        self._is_shutting_down = True
        self._log("Sending shutdown request to server")
        self.send.shutdown()
        self._log("Received shutdown response from server")
        self._log("Sending exit notification to server")
        self.notify.exit()
        self._log("Sent exit notification to server")

    def _log(self, message: str | StringDict) -> None:
        """
        Create a log message
        """
        if self.logger is not None:
            self.logger("client", "logger", message)

    @staticmethod
    def _read_bytes_from_process(process, stream, num_bytes):
        """Read exactly num_bytes from process stdout"""
        data = b""
        while len(data) < num_bytes:
            chunk = stream.read(num_bytes - len(data))
            if not chunk:
                if process is not None and process.poll() is not None:
                    raise LanguageServerTerminatedException(
                        f"Process terminated while trying to read response (read {num_bytes} of {len(data)} bytes before termination)"
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
        stream = self._stdout_stream
        try:
            if self._transport_is_tcp:
                sock = self._tcp_socket
                buffer = b""
                while sock:
                    try:
                        ready, _, _ = select.select([sock], [], [], 1.0)
                        if not ready:
                            continue
                        chunk = sock.recv(4096)
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    if not chunk:
                        time.sleep(0.01)
                        continue
                    buffer += chunk
                    while True:
                        header_end = buffer.find(b"\r\n\r\n")
                        if header_end == -1:
                            break
                        header_blob = buffer[:header_end].split(b"\r\n")
                        buffer = buffer[header_end + 4 :]
                        try:
                            num_bytes_val = None
                            for line_bytes in header_blob:
                                num_bytes_val = content_length(line_bytes + b"\r\n")
                                if num_bytes_val is not None:
                                    break
                        except ValueError:
                            num_bytes_val = None
                        if num_bytes_val is None:
                            continue
                        while len(buffer) < num_bytes_val:
                            chunk = sock.recv(num_bytes_val - len(buffer))
                            if not chunk:
                                time.sleep(0.01)
                                continue
                            buffer += chunk
                        body = buffer[:num_bytes_val]
                        buffer = buffer[num_bytes_val:]
                        self._handle_body(body)
            else:
                while stream:
                    if self.process is not None and self.process.poll() is not None:  # process has terminated
                        break
                    line = stream.readline()
                    if not line:
                        continue
                    try:
                        num_bytes = content_length(line)
                    except ValueError:
                        continue
                    if num_bytes is None:
                        continue
                    while line and line.strip():
                        line = stream.readline()
                    if not line:
                        continue
                    body = self._read_bytes_from_process(self.process, stream, num_bytes)

                    self._handle_body(body)
        except LanguageServerTerminatedException as e:
            exception = e
        except (BrokenPipeError, ConnectionResetError) as e:
            exception = LanguageServerTerminatedException("Language server process terminated while reading stdout", cause=e)
        except Exception as e:
            exception = LanguageServerTerminatedException("Unexpected error while reading stdout from language server process", cause=e)
        log.info("Language server stdout reader thread has terminated")
        if not self._is_shutting_down:
            if exception is None:
                exception = LanguageServerTerminatedException("Language server stdout read process terminated unexpectedly")
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
                line = line.decode(ENCODING, errors="replace")
                line_lower = line.lower()
                if "error" in line_lower or "exception" in line_lower or line.startswith("E["):
                    level = logging.ERROR
                else:
                    level = logging.INFO
                log.log(level, line)
        except Exception as e:
            log.error("Error while reading stderr from language server process: %s", e, exc_info=e)
        if not self._is_shutting_down:
            log.error("Language server stderr reader thread terminated unexpectedly")
        else:
            log.info("Language server stderr reader thread has terminated")

    def _handle_body(self, body: bytes) -> None:
        """
        Parse the body text received from the language server process and invoke the appropriate handler
        """
        try:
            self._receive_payload(json.loads(body))
        except OSError as ex:
            self._log(f"malformed {ENCODING}: {ex}")
        except UnicodeDecodeError as ex:
            self._log(f"malformed {ENCODING}: {ex}")
        except json.JSONDecodeError as ex:
            self._log(f"malformed JSON: {ex}")

    def _receive_payload(self, payload: StringDict) -> None:
        """
        Determine if the payload received from server is for a request, response, or notification and invoke the appropriate handler
        """
        payload_type = "unknown"
        method = payload.get("method")
        payload_id = payload.get("id")
        if method is not None:
            payload_type = "request" if payload_id is not None else "notification"
        elif payload_id is not None:
            payload_type = "response"

        log.debug(
            "LSP inbound payload type=%s method=%s id=%s keys=%s",
            payload_type,
            method,
            payload_id,
            list(payload.keys()),
        )

        if self.logger:
            self.logger("server", "client", payload)
        try:
            if "method" in payload:
                if "id" in payload:
                    self._request_handler(payload)
                else:
                    self._notification_handler(payload)
            elif "id" in payload:
                self._response_handler(payload)
            else:
                self._log(f"Unknown payload type: {payload}")
        except Exception as err:
            self._log(f"Error handling server payload: {err}")

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
        # Use lock to prevent race conditions on tasks and task_counter
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

        self._log(f"Waiting for response to request {method} with params:\n{params}")
        result = request.get_result(timeout=self._request_timeout)
        log.debug("Completed: %s", request)

        self._log("Processing result")
        if result.is_error():
            raise SolidLSPException(f"Error processing request {method} with params:\n{params}", cause=result.error) from result.error

        self._log(f"Returning non-error result, which is:\n{result.payload}")
        return result.payload

    def _send_payload(self, payload: StringDict) -> None:
        """
        Send the payload to the server by writing to its stdin asynchronously.
        """
        if self._transport_is_tcp and self._tcp_socket:
            data = b"".join(create_message(payload, include_content_type=False))
            self._log(payload)
            with self._stdin_lock:
                try:
                    self._tcp_socket.sendall(data)
                except (BrokenPipeError, ConnectionResetError, OSError) as e:
                    if self.logger:
                        self.logger("client", "logger", f"Failed to write to tcp socket: {e}")
            return

        stream = self._stdin_stream
        if stream is None:
            return
        self._log(payload)
        msg = create_message(payload)

        # Use lock to prevent concurrent writes to stdin that cause buffer corruption
        with self._stdin_lock:
            try:
                stream.writelines(msg)
                stream.flush()
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                # Log the error but don't raise to prevent cascading failures
                if self.logger:
                    self.logger("client", "logger", f"Failed to write to stdin: {e}")
                return

    def on_request(self, method: str, cb) -> None:
        """
        Register the callback function to handle requests from the server to the client for the given method
        """
        self.on_request_handlers[method] = cb

    def on_notification(self, method: str, cb) -> None:
        """
        Register the callback function to handle notifications from the server to the client for the given method
        """
        self.on_notification_handlers[method] = cb

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
        handler = self.on_notification_handlers.get(method)
        if not handler:
            self._log(f"unhandled {method}")
            return
        try:
            handler(params)
        except asyncio.CancelledError:
            return
        except Exception as ex:
            if (not self._is_shutting_down) and self.logger:
                self.logger(
                    "client",
                    "logger",
                    str(
                        {
                            "type": MessageType.error,
                            "message": str(ex),
                            "method": method,
                            "params": params,
                        }
                    ),
                )
