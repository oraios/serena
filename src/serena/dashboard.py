import os
import socket
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from flask import Flask, Response, request, send_from_directory
from pydantic import BaseModel
from sensai.util import logging

from serena.analytics import ToolUsageStats
from serena.constants import SERENA_DASHBOARD_DIR
from serena.util.logging import MemoryLogHandler

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

log = logging.getLogger(__name__)

# disable Werkzeug's logging to avoid cluttering the output
logging.getLogger("werkzeug").setLevel(logging.WARNING)


class RequestLog(BaseModel):
    start_idx: int = 0


class ResponseLog(BaseModel):
    messages: list[str]
    max_idx: int
    active_project: str | None = None


class ResponseToolNames(BaseModel):
    tool_names: list[str]


class ResponseToolStats(BaseModel):
    stats: dict[str, dict[str, int]]


class SerenaDashboardAPI:
    log = logging.getLogger(__qualname__)

    def __init__(
        self,
        memory_log_handler: MemoryLogHandler,
        tool_names: list[str],
        agent: "SerenaAgent",
        shutdown_callback: Callable[[], None] | None = None,
        tool_usage_stats: ToolUsageStats | None = None,
    ) -> None:
        self._memory_log_handler = memory_log_handler
        self._tool_names = tool_names
        self._agent = agent
        self._shutdown_callback = shutdown_callback
        self._app = Flask(__name__)
        self._tool_usage_stats = tool_usage_stats
        self._setup_routes()

    @property
    def memory_log_handler(self) -> MemoryLogHandler:
        return self._memory_log_handler

    def _setup_routes(self) -> None:
        # Static files
        @self._app.route("/dashboard/<path:filename>")
        def serve_dashboard(filename: str) -> Response:
            return send_from_directory(SERENA_DASHBOARD_DIR, filename)

        @self._app.route("/dashboard/")
        def serve_dashboard_index() -> Response:
            return send_from_directory(SERENA_DASHBOARD_DIR, "index.html")

        # API routes
        @self._app.route("/get_log_messages", methods=["POST"])
        def get_log_messages() -> dict[str, Any]:
            request_data = request.get_json()
            if not request_data:
                request_log = RequestLog()
            else:
                request_log = RequestLog.model_validate(request_data)

            result = self._get_log_messages(request_log)
            return result.model_dump()

        @self._app.route("/get_tool_names", methods=["GET"])
        def get_tool_names() -> dict[str, Any]:
            result = self._get_tool_names()
            return result.model_dump()

        @self._app.route("/get_tool_stats", methods=["GET"])
        def get_tool_stats_route() -> dict[str, Any]:
            result = self._get_tool_stats()
            return result.model_dump()

        @self._app.route("/clear_tool_stats", methods=["POST"])
        def clear_tool_stats_route() -> dict[str, str]:
            self._clear_tool_stats()
            return {"status": "cleared"}

        @self._app.route("/get_token_count_estimator_name", methods=["GET"])
        def get_token_count_estimator_name() -> dict[str, str]:
            estimator_name = self._tool_usage_stats.token_estimator_name if self._tool_usage_stats else "unknown"
            return {"token_count_estimator_name": estimator_name}

        @self._app.route("/shutdown", methods=["PUT"])
        def shutdown() -> dict[str, str]:
            self._shutdown()
            return {"status": "shutting down"}

    def _get_log_messages(self, request_log: RequestLog) -> ResponseLog:
        all_messages = self._memory_log_handler.get_log_messages()
        requested_messages = all_messages[request_log.start_idx :] if request_log.start_idx <= len(all_messages) else []
        project = self._agent.get_active_project()
        project_name = project.project_name if project else None
        return ResponseLog(messages=requested_messages, max_idx=len(all_messages) - 1, active_project=project_name)

    def _get_tool_names(self) -> ResponseToolNames:
        return ResponseToolNames(tool_names=self._tool_names)

    def _get_tool_stats(self) -> ResponseToolStats:
        if self._tool_usage_stats is not None:
            return ResponseToolStats(stats=self._tool_usage_stats.get_tool_stats_dict())
        else:
            return ResponseToolStats(stats={})

    def _clear_tool_stats(self) -> None:
        if self._tool_usage_stats is not None:
            self._tool_usage_stats.clear()

    def _shutdown(self) -> None:
        log.info("Shutting down Serena")
        if self._shutdown_callback:
            self._shutdown_callback()
        else:
            # noinspection PyProtectedMember
            # noinspection PyUnresolvedReferences
            os._exit(0)

    @staticmethod
    def _find_first_free_port(start_port: int) -> int:
        port = start_port
        while port <= 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("0.0.0.0", port))
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
