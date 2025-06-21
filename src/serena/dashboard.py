import os
import queue
import socket
import threading
from collections.abc import Callable

from flask import Flask, request, send_from_directory
from pydantic import BaseModel
from sensai.util import logging

from serena.constants import SERENA_DASHBOARD_DIR

log = logging.getLogger(__name__)

# disable Werkzeug's logging to avoid cluttering the output
logging.getLogger("werkzeug").setLevel(logging.WARNING)


class MemoryLogHandler(logging.Handler):
    def __init__(self, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self.setFormatter(logging.Formatter(logging.LOG_DEFAULT_FORMAT))
        self._log_buffer = LogBuffer()
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()

        # start background thread to process logs
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        self._log_queue.put_nowait(msg)

    def _process_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                msg = self._log_queue.get(timeout=1)
                self._log_buffer.append(msg)
                self._log_queue.task_done()
            except queue.Empty:
                continue

    def get_log_messages(self) -> list[str]:
        return self._log_buffer.logs


class LogBuffer:
    def __init__(self) -> None:
        self.logs: list[str] = []

    def append(self, msg: str) -> None:
        self.logs.append(msg)


class RequestLog(BaseModel):
    start_idx: int = 0


class ResponseLog(BaseModel):
    messages: list[str]
    max_idx: int


class ResponseToolNames(BaseModel):
    tool_names: list[str]


class SerenaDashboardAPI:
    log = logging.getLogger(__qualname__)

    def __init__(
        self, memory_log_handler: MemoryLogHandler, tool_names: list[str], shutdown_callback: Callable[[], None] | None = None
    ) -> None:
        self._memory_log_handler = memory_log_handler
        self._tool_names = tool_names
        self._shutdown_callback = shutdown_callback
        self._app = Flask(__name__)
        self._setup_routes()

    @property
    def memory_log_handler(self) -> MemoryLogHandler:
        return self._memory_log_handler

    def _setup_routes(self) -> None:
        # Static files
        @self._app.route("/dashboard/<path:filename>")
        def serve_dashboard(filename):
            return send_from_directory(SERENA_DASHBOARD_DIR, filename)

        @self._app.route("/dashboard/")
        def serve_dashboard_index():
            return send_from_directory(SERENA_DASHBOARD_DIR, "index.html")

        # API routes
        @self._app.route("/get_log_messages", methods=["POST"])
        def get_log_messages():
            request_data = request.get_json()
            if not request_data:
                request_log = RequestLog()
            else:
                request_log = RequestLog.model_validate(request_data)

            result = self._get_log_messages(request_log)
            return result.model_dump()

        @self._app.route("/get_tool_names", methods=["GET"])
        def get_tool_names():
            result = self._get_tool_names()
            return result.model_dump()

        @self._app.route("/shutdown", methods=["PUT"])
        def shutdown():
            self._shutdown()
            return {"status": "shutting down"}

    def _get_log_messages(self, request_log: RequestLog) -> ResponseLog:
        all_messages = self._memory_log_handler.get_log_messages()
        requested_messages = all_messages[request_log.start_idx :] if request_log.start_idx <= len(all_messages) else []
        return ResponseLog(messages=requested_messages, max_idx=len(all_messages) - 1)

    def _get_tool_names(self) -> ResponseToolNames:
        return ResponseToolNames(tool_names=self._tool_names)

    def _shutdown(self) -> None:
        log.info("Shutting down Serena")
        if self._shutdown_callback:
            self._shutdown_callback()
        else:
            # Try to use the global shutdown function from process_isolated_agent
            from serena.process_isolated_agent import request_global_shutdown

            request_global_shutdown()
            # noinspection PyProtectedMember
            os._exit(0)

    @staticmethod
    def _find_first_free_port(start_port: int) -> int:
        port = start_port
        while port <= 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("localhost", port))
                    return port
            except OSError:
                port += 1

        raise RuntimeError(f"No free ports found starting from {start_port}")

    def run(self, host: str = "0.0.0.0", port: int = 0x5EDA) -> int:
        """
        Runs the dashboard on the given host and port and returns the port number.
        """
        # patch flask.cli.show_server to avoid printing the server info
        from flask import cli

        cli.show_server_banner = lambda *args, **kwargs: None

        self._app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        return port

    def run_in_thread(self) -> tuple[threading.Thread, int]:
        port = self._find_first_free_port(0x5EDA)
        thread = threading.Thread(target=lambda: self.run(port=port), daemon=True)
        thread.start()
        return thread, port
