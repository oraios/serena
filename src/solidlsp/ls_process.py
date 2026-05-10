import asyncio
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any

from sensai.util.string import ToStringMixin

from solidlsp.ls_config import Language
from solidlsp.ls_exceptions import LanguageServerTerminatedException, SolidLSPException
from solidlsp.ls_request import LanguageServerRequest
from solidlsp.lsp_protocol_handler.lsp_requests import LspNotification
from solidlsp.lsp_protocol_handler.lsp_types import ErrorCodes
from solidlsp.lsp_protocol_handler.server import (
    ENCODING,
    LSPError,
    PayloadLike,
    StringDict,
    content_length,
    create_message,
    make_error_response,
    make_notification,
    make_request,
    make_response,
)
from solidlsp.lsp_transport import LSPTransport

log = logging.getLogger(__name__)


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


class LanguageServerProcess:
    """
    Provides methods for communicating with a language server using the Language Server Protocol (LSP).

    Delegates all I/O and process/connection lifecycle to an LSPTransport instance.
    Uses JSON-RPC 2.0 for communication.
    """

    def __init__(
        self,
        transport: LSPTransport,
        language: Language,
        logger: Callable[[str, str, StringDict | str], None] | None = None,
        request_timeout: float | None = None,
    ) -> None:
        self.language = language
        self.send = LanguageServerRequest(self)
        self.notify = LspNotification(self.send_notification)

        self._transport = transport
        self._is_shutting_down = False

        self.request_id = 1
        self._pending_requests: dict[Any, Request] = {}
        self.on_request_handlers: dict[str, Callable[[Any], Any]] = {}
        self.on_notification_handlers: dict[str, Callable[[Any], None]] = {}
        self._notification_observers: list[Callable[[str, Any], None]] = []
        self._trace_log_fn = logger
        self.tasks: dict[int, Any] = {}
        self.task_counter = 0
        self.loop = None
        self._request_timeout = request_timeout

        self._request_id_lock = threading.Lock()
        self._response_handlers_lock = threading.Lock()
        self._tasks_lock = threading.Lock()

    def get_transport(self) -> LSPTransport:
        return self._transport

    def set_request_timeout(self, timeout: float | None) -> None:
        """
        :param timeout: the timeout, in seconds, for all requests sent to the language server.
        """
        self._request_timeout = timeout

    def is_running(self) -> bool:
        """
        Checks if the language server is currently running.
        """
        return self._transport.is_alive()

    def start(self) -> None:
        """
        Starts the transport and spawns the stdout reader thread.
        Stderr reading (if any) is the transport's responsibility.
        """
        self._transport.start()
        threading.Thread(
            target=self._read_ls_process_stdout,
            name=f"LSP-stdout-reader:{self.language.value}",
            daemon=True,
        ).start()

    def stop(self) -> None:
        """
        Stops the transport and releases resources.
        """
        self._transport.stop()

    def shutdown(self) -> None:
        """
        Perform the shutdown sequence for the client, including sending the shutdown request to the server and notifying it of exit
        """
        self._is_shutting_down = True
        log.info("Sending shutdown request to server")
        self.send.shutdown()
        log.info("Received shutdown response from server")
        log.info("Sending exit notification to server")
        self.notify.exit()
        log.info("Sent exit notification to server")

    def _trace(self, src: str, dest: str, message: str | StringDict) -> None:
        """
        Traces LS communication by logging the message with the source and destination of the message
        """
        if self._trace_log_fn is not None:
            self._trace_log_fn(src, dest, message)

    def _read_ls_process_stdout(self) -> None:
        """
        Continuously read from the language server stdout and handle the messages,
        invoking the registered response and notification handlers.
        """
        exception: Exception | None = None
        try:
            while self._transport.is_alive():
                line = self._transport.read_line()
                try:
                    num_bytes = content_length(line)
                except ValueError:
                    continue
                if num_bytes is None:
                    continue
                # Read remaining header lines until the blank separator line.
                while line.strip():
                    line = self._transport.read_line()
                body = self._transport.read_bytes(num_bytes)
                self._handle_body(body)
        except LanguageServerTerminatedException as e:
            exception = e
        except (BrokenPipeError, ConnectionResetError) as e:
            exception = LanguageServerTerminatedException("Language server terminated while reading stdout", self.language, cause=e)
        except Exception as e:
            exception = LanguageServerTerminatedException(
                "Unexpected error while reading stdout from language server", self.language, cause=e
            )
        log.info("Language server stdout reader thread has terminated")
        if not self._is_shutting_down:
            if exception is None:
                exception = LanguageServerTerminatedException("Language server stdout read process terminated unexpectedly", self.language)
            log.error(str(exception))
            self._cancel_pending_requests(exception)

    def _handle_body(self, body: bytes) -> None:
        """
        Parse the body text received from the language server process and invoke the appropriate handler
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

    def _send_payload(self, payload: StringDict) -> None:
        """
        Send the payload to the language server via the transport.
        Swallows transport-termination errors during shutdown; otherwise propagates.
        """
        self._trace("solidlsp", "ls", payload)
        try:
            self._transport.write(create_message(payload))
        except LanguageServerTerminatedException:
            if not self._is_shutting_down:
                raise

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
                if not self._is_shutting_down:
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
            if not self._is_shutting_down:
                log.error("Error handling notification for method '%s': %s", method, ex, exc_info=ex)
