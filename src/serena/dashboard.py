import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import webview
from flask import Flask, Response, redirect, request, send_from_directory
from PIL import Image
from pydantic import BaseModel
from sensai.util import logging

from serena.analytics import ToolUsageStats
from serena.config.serena_config import SerenaConfig, SerenaPaths
from serena.constants import SERENA_DASHBOARD_DIR
from serena.task_executor import TaskExecutor
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


class ResponseConfigOverview(BaseModel):
    active_project: dict[str, str | None]
    context: dict[str, str]
    modes: list[dict[str, str]]
    active_tools: list[str]
    tool_stats_summary: dict[str, dict[str, int]]
    registered_projects: list[dict[str, str | bool]]
    available_tools: list[dict[str, str | bool]]
    available_modes: list[dict[str, str | bool]]
    available_contexts: list[dict[str, str | bool]]
    available_memories: list[str] | None
    jetbrains_mode: bool
    languages: list[str]
    encoding: str | None
    current_client: str | None
    serena_version: str


class ResponseAvailableLanguages(BaseModel):
    languages: list[str]


class RequestAddLanguage(BaseModel):
    language: str


class RequestRemoveLanguage(BaseModel):
    language: str


class RequestGetMemory(BaseModel):
    memory_name: str


class ResponseGetMemory(BaseModel):
    content: str
    memory_name: str


class RequestSaveMemory(BaseModel):
    memory_name: str
    content: str


class RequestDeleteMemory(BaseModel):
    memory_name: str


class RequestRenameMemory(BaseModel):
    old_name: str
    new_name: str


class ResponseGetSerenaConfig(BaseModel):
    content: str


class RequestSaveSerenaConfig(BaseModel):
    content: str


class RequestCancelTaskExecution(BaseModel):
    task_id: int


class QueuedExecution(BaseModel):
    task_id: int
    is_running: bool
    name: str
    finished_successfully: bool
    logged: bool

    @classmethod
    def from_task_info(cls, task_info: TaskExecutor.TaskInfo) -> Self:
        return cls(
            task_id=task_info.task_id,
            is_running=task_info.is_running,
            name=task_info.name,
            finished_successfully=task_info.finished_successfully(),
            logged=task_info.logged,
        )


class SerenaDashboardAPI:
    log = logging.getLogger(__qualname__)

    def __init__(
        self,
        memory_log_handler: MemoryLogHandler,
        tool_names: list[str],
        agent: "SerenaAgent",
        tool_usage_stats: ToolUsageStats | None = None,
    ) -> None:
        self._memory_log_handler = memory_log_handler
        self._tool_names = tool_names
        self._agent = agent
        self._app = Flask(__name__)
        self._tool_usage_stats = tool_usage_stats
        self._loaded_news: dict[str, str] = {}
        self._news_ready = threading.Event()
        self._setup_routes()
        # Fetch remote news in background on startup (non-blocking)
        threading.Thread(target=self._fetch_news, daemon=True).start()

    @property
    def memory_log_handler(self) -> MemoryLogHandler:
        return self._memory_log_handler

    def _setup_routes(self) -> None:
        @self._app.route("/")
        def redirect_to_dashboard() -> Response:
            return redirect("/dashboard/")  # type: ignore[return-value]

        # Static files
        @self._app.route("/dashboard/<path:filename>")
        def serve_dashboard(filename: str) -> Response:
            return send_from_directory(SERENA_DASHBOARD_DIR, filename)

        @self._app.route("/dashboard/")
        def serve_dashboard_index() -> Response:
            return send_from_directory(SERENA_DASHBOARD_DIR, "index.html")

        # API routes

        @self._app.route("/heartbeat", methods=["GET"])
        def get_heartbeat() -> dict[str, Any]:
            return {"status": "alive"}

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

        @self._app.route("/clear_logs", methods=["POST"])
        def clear_logs() -> dict[str, str]:
            self._memory_log_handler.clear_log_messages()
            return {"status": "cleared"}

        @self._app.route("/get_token_count_estimator_name", methods=["GET"])
        def get_token_count_estimator_name() -> dict[str, str]:
            estimator_name = self._tool_usage_stats.token_estimator_name if self._tool_usage_stats else "unknown"
            return {"token_count_estimator_name": estimator_name}

        @self._app.route("/get_config_overview", methods=["GET"])
        def get_config_overview() -> dict[str, Any]:
            result = self._agent.execute_task(self._get_config_overview, logged=False)
            return result.model_dump()

        @self._app.route("/shutdown", methods=["PUT"])
        def shutdown() -> dict[str, str]:
            self._agent.shutdown()
            return {"status": "shutting down"}

        @self._app.route("/get_available_languages", methods=["GET"])
        def get_available_languages() -> dict[str, Any]:
            result = self._get_available_languages()
            return result.model_dump()

        @self._app.route("/add_language", methods=["POST"])
        def add_language() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_add_language = RequestAddLanguage.model_validate(request_data)
            try:
                self._add_language(request_add_language)
                return {"status": "success", "message": f"Language {request_add_language.language} added successfully"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/remove_language", methods=["POST"])
        def remove_language() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_remove_language = RequestRemoveLanguage.model_validate(request_data)
            try:
                self._remove_language(request_remove_language)
                return {"status": "success", "message": f"Language {request_remove_language.language} removed successfully"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/get_memory", methods=["POST"])
        def get_memory() -> dict[str, Any]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_get_memory = RequestGetMemory.model_validate(request_data)
            try:
                result = self._get_memory(request_get_memory)
                return result.model_dump()
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/save_memory", methods=["POST"])
        def save_memory() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_save_memory = RequestSaveMemory.model_validate(request_data)
            try:
                self._save_memory(request_save_memory)
                return {"status": "success", "message": f"Memory {request_save_memory.memory_name} saved successfully"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/delete_memory", methods=["POST"])
        def delete_memory() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_delete_memory = RequestDeleteMemory.model_validate(request_data)
            try:
                self._delete_memory(request_delete_memory)
                return {"status": "success", "message": f"Memory {request_delete_memory.memory_name} deleted successfully"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/rename_memory", methods=["POST"])
        def rename_memory() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_rename_memory = RequestRenameMemory.model_validate(request_data)
            try:
                result_message = self._rename_memory(request_rename_memory)
                return {"status": "success", "message": result_message}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/get_serena_config", methods=["GET"])
        def get_serena_config() -> dict[str, Any]:
            try:
                result = self._get_serena_config()
                return result.model_dump()
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/save_serena_config", methods=["POST"])
        def save_serena_config() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_save_config = RequestSaveSerenaConfig.model_validate(request_data)
            try:
                self._save_serena_config(request_save_config)
                return {"status": "success", "message": "Serena config saved successfully"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/queued_task_executions", methods=["GET"])
        def get_queued_executions() -> dict[str, Any]:
            try:
                current_executions = self._agent.get_current_tasks()
                response = [QueuedExecution.from_task_info(task_info).model_dump() for task_info in current_executions]
                return {"queued_executions": response, "status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/cancel_task_execution", methods=["POST"])
        def cancel_task_execution() -> dict[str, Any]:
            request_data = request.get_json()
            try:
                request_cancel_task = RequestCancelTaskExecution.model_validate(request_data)
                for task in self._agent.get_current_tasks():
                    if task.task_id == request_cancel_task.task_id:
                        task.cancel()
                        return {"status": "success", "was_cancelled": True}
                return {
                    "status": "success",
                    "was_cancelled": False,
                    "message": f"Task with id {request_data.get('task_id')} not found, maybe execution was already finished",
                }
            except Exception as e:
                return {"status": "error", "message": str(e), "was_cancelled": False}

        @self._app.route("/last_execution", methods=["GET"])
        def get_last_execution() -> dict[str, Any]:
            try:
                last_execution_info = self._agent.get_last_executed_task()
                response = QueuedExecution.from_task_info(last_execution_info).model_dump() if last_execution_info is not None else None
                return {"last_execution": response, "status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/fetch_unread_news", methods=["GET"])
        def fetch_unread_news() -> dict[str, dict[str, str] | str]:
            def _fetch_unread_news() -> dict[str, str]:
                """News ids are strings of format YYYYMMDD (publication dates)"""
                self._news_ready.wait()
                all_news = self._loaded_news

                # Filter news items by installation date
                serena_config_creation_date = SerenaConfig.get_config_file_creation_date()
                if serena_config_creation_date is None:
                    # should not normally happen, since config file should exist when the dashboard is started
                    # We assume a fresh installation in this case
                    log.error("Serena config file not found when starting the dashboard")
                    return {}
                serena_config_creation_date = serena_config_creation_date.strftime("%Y%m%d")
                # Only include news items published on or after the installation date
                post_installation_news = {k: v for k, v in all_news.items() if k >= serena_config_creation_date}

                news_snippet_id_file = SerenaPaths().news_snippet_id_file
                if not os.path.exists(news_snippet_id_file):
                    return post_installation_news
                with open(news_snippet_id_file, encoding="utf-8") as f:
                    last_read_news_id = f.read().strip()
                    if last_read_news_id == "20262103":
                        last_read_news_id = "20260321"  # fix originally misnamed news id
                return {k: v for k, v in post_installation_news.items() if k > last_read_news_id}

            try:
                unread_news = _fetch_unread_news()
                return {"news": unread_news, "status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/mark_news_snippet_as_read", methods=["POST"])
        def mark_news_snippet_as_read() -> dict[str, str]:
            try:
                request_data = request.get_json()
                news_snippet_id = str(request_data.get("news_snippet_id"))
                news_snippet_id_file = SerenaPaths().news_snippet_id_file
                with open(news_snippet_id_file, "w", encoding="utf-8") as f:
                    f.write(news_snippet_id)
                return {"status": "success", "message": f"Marked news snippet {news_snippet_id} as read"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

    def _get_log_messages(self, request_log: RequestLog) -> ResponseLog:
        messages = self._memory_log_handler.get_log_messages(from_idx=request_log.start_idx)
        project = self._agent.get_active_project()
        project_name = project.project_name if project else None
        return ResponseLog(messages=messages.messages, max_idx=messages.max_idx, active_project=project_name)

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

    def _get_config_overview(self) -> ResponseConfigOverview:
        from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode
        from serena.tools.tools_base import Tool

        # Get active project info
        project = self._agent.get_active_project()
        active_project_name = project.project_name if project else None
        project_info = {
            "name": active_project_name,
            "language": ", ".join([l.value for l in project.project_config.languages]) if project else None,
            "path": str(project.project_root) if project else None,
        }

        # Get context info
        context = self._agent.get_context()
        context_info = {
            "name": context.name,
            "description": context.description,
            "path": SerenaAgentContext.get_path(context.name, instance=context),
        }

        # Get active modes
        modes = self._agent.get_active_modes()
        modes_info = [
            {"name": mode.name, "description": mode.description, "path": SerenaAgentMode.get_path(mode.name, instance=mode)}
            for mode in modes
        ]
        active_mode_names = [mode.name for mode in modes]

        # Get active tools
        active_tools = self._agent.get_active_tool_names()

        # Get registered projects
        registered_projects: list[dict[str, str | bool]] = []
        for proj in self._agent.serena_config.projects:
            registered_projects.append(
                {
                    "name": proj.project_name,
                    "path": str(proj.project_root),
                    "is_active": proj.project_name == active_project_name,
                }
            )

        # Get all available tools (excluding active ones)
        all_tool_names = sorted([tool.get_name_from_cls() for tool in self._agent._all_tools.values()])
        available_tools: list[dict[str, str | bool]] = []
        for tool_name in all_tool_names:
            if tool_name not in active_tools:
                available_tools.append(
                    {
                        "name": tool_name,
                        "is_active": False,
                    }
                )

        # Get all available modes
        all_mode_names = SerenaAgentMode.list_registered_mode_names()
        available_modes: list[dict[str, str | bool]] = []
        for mode_name in all_mode_names:
            try:
                mode_path = SerenaAgentMode.get_path(mode_name)
            except FileNotFoundError:
                # Skip modes that can't be found (shouldn't happen for registered modes)
                continue
            available_modes.append(
                {
                    "name": mode_name,
                    "is_active": mode_name in active_mode_names,
                    "path": mode_path,
                }
            )

        # Get all available contexts
        all_context_names = SerenaAgentContext.list_registered_context_names()
        available_contexts: list[dict[str, str | bool]] = []
        for context_name in all_context_names:
            try:
                context_path = SerenaAgentContext.get_path(context_name)
            except FileNotFoundError:
                # Skip contexts that can't be found (shouldn't happen for registered contexts)
                continue
            available_contexts.append(
                {
                    "name": context_name,
                    "is_active": context_name == context.name,
                    "path": context_path,
                }
            )

        # Get basic tool stats (just num_calls for overview)
        tool_stats_summary = {}
        if self._tool_usage_stats is not None:
            full_stats = self._tool_usage_stats.get_tool_stats_dict()
            tool_stats_summary = {name: {"num_calls": stats["num_times_called"]} for name, stats in full_stats.items()}

        # Get available memories if ReadMemoryTool is active
        available_memories = None
        if self._agent.tool_is_active("read_memory") and project is not None:
            available_memories = project.memories_manager.list_memories().get_full_list()

        # Get list of languages for the active project
        languages = []
        if project is not None:
            languages = [lang.value for lang in project.project_config.languages]

        # Get file encoding for the active project
        encoding = None
        if project is not None:
            encoding = project.project_config.encoding

        return ResponseConfigOverview(
            active_project=project_info,
            context=context_info,
            modes=modes_info,
            active_tools=active_tools,
            tool_stats_summary=tool_stats_summary,
            registered_projects=registered_projects,
            available_tools=available_tools,
            available_modes=available_modes,
            available_contexts=available_contexts,
            available_memories=available_memories,
            jetbrains_mode=self._agent.get_language_backend().is_jetbrains(),
            languages=languages,
            encoding=encoding,
            current_client=Tool.get_last_tool_call_client_str(),
            serena_version=self._agent.version,
        )

    def _get_available_languages(self) -> ResponseAvailableLanguages:
        from solidlsp.ls_config import Language

        def run() -> ResponseAvailableLanguages:
            all_languages = [lang.value for lang in Language.iter_all(include_experimental=True)]

            # Filter out already added languages for the active project
            project = self._agent.get_active_project()
            if project:
                current_languages = [lang.value for lang in project.project_config.languages]
                available_languages = [lang for lang in all_languages if lang not in current_languages]
            else:
                available_languages = all_languages

            return ResponseAvailableLanguages(languages=sorted(available_languages))

        return self._agent.execute_task(run, logged=False)

    def _get_memory(self, request_get_memory: RequestGetMemory) -> ResponseGetMemory:
        def run() -> ResponseGetMemory:
            project = self._agent.get_active_project()
            if project is None:
                raise ValueError("No active project")

            content = project.memories_manager.load_memory(request_get_memory.memory_name)
            return ResponseGetMemory(content=content, memory_name=request_get_memory.memory_name)

        return self._agent.execute_task(run, logged=False)

    def _save_memory(self, request_save_memory: RequestSaveMemory) -> None:
        def run() -> None:
            project = self._agent.get_active_project()
            if project is None:
                raise ValueError("No active project")
            project.memories_manager.save_memory(request_save_memory.memory_name, request_save_memory.content, is_tool_context=False)

        self._agent.execute_task(run, logged=True, name="SaveMemory")

    def _delete_memory(self, request_delete_memory: RequestDeleteMemory) -> None:
        def run() -> None:
            project = self._agent.get_active_project()
            if project is None:
                raise ValueError("No active project")
            project.memories_manager.delete_memory(request_delete_memory.memory_name, is_tool_context=False)

        self._agent.execute_task(run, logged=True, name="DeleteMemory")

    def _rename_memory(self, request_rename_memory: RequestRenameMemory) -> str:
        def run() -> str:
            project = self._agent.get_active_project()
            if project is None:
                raise ValueError("No active project")

            return project.memories_manager.move_memory(
                request_rename_memory.old_name, request_rename_memory.new_name, is_tool_context=False
            )

        return self._agent.execute_task(run, logged=True, name="RenameMemory")

    def _get_serena_config(self) -> ResponseGetSerenaConfig:
        config_path = self._agent.serena_config.config_file_path
        if config_path is None or not os.path.exists(config_path):
            raise ValueError("Serena config file not found")

        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        return ResponseGetSerenaConfig(content=content)

    def _save_serena_config(self, request_save_config: RequestSaveSerenaConfig) -> None:
        def run() -> None:
            config_path = self._agent.serena_config.config_file_path
            if config_path is None:
                raise ValueError("Serena config file path not set")

            with open(config_path, "w", encoding="utf-8") as f:
                f.write(request_save_config.content)

        self._agent.execute_task(run, logged=True, name="SaveSerenaConfig")

    # ===== Remote News Methods =====

    # The branch from which news are fetched. Change to a feature branch for testing.
    _NEWS_JSON_URL = (
        "https://raw.githubusercontent.com/oraios/serena/release/added_fetch_news_mechanism_and_bump_version_script/news/news.json"
    )

    def _fetch_news(self) -> None:
        """Fetch news.json from GitHub using ETag-based caching and store in memory. Silently ignores network errors."""
        paths = SerenaPaths()

        headers: dict[str, str] = {}
        # Load stored ETag if available
        if os.path.exists(paths.news_etag_file) and os.path.exists(paths.news_file):
            try:
                with open(paths.news_etag_file, encoding="utf-8") as f:
                    stored_etag = f.read().strip()
                if stored_etag:
                    headers["If-None-Match"] = stored_etag
            except Exception:
                log.warning("Failed to read stored news ETag at %s, proceeding without it", paths.news_etag_file, exc_info=True)

        fetched_news_dict = None
        try:
            req = urllib.request.Request(self._NEWS_JSON_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                etag = response.headers.get("ETag", "")
                body = response.read().decode("utf-8")
                # Validate JSON
                fetched_news_dict = json.loads(body)
                # Store news content and ETag
                with open(paths.news_file, "w", encoding="utf-8") as f:
                    f.write(body)
                if etag:
                    with open(paths.news_etag_file, "w", encoding="utf-8") as f:
                        f.write(etag)
                log.info("Remote news updated from %s", self._NEWS_JSON_URL)
        except urllib.error.HTTPError as e:
            if e.code == 304:
                log.debug("Remote news unchanged (304 Not Modified)")
            else:
                log.warning("Failed to fetch remote news (HTTP %d): %s", e.code, e.reason)
        except Exception as e:
            log.warning("Failed to fetch remote news: %s", e)
        if fetched_news_dict is None:
            fetched_news_dict = self._load_previously_fetched_news_data()
        self._loaded_news = fetched_news_dict
        self._news_ready.set()

    @staticmethod
    def _load_previously_fetched_news_data() -> dict[str, str]:
        """Return the news data dict. Uses local cache if available, otherwise falls back to local news files."""
        paths = SerenaPaths()

        if os.path.exists(paths.news_file):
            try:
                with open(paths.news_file, encoding="utf-8") as f:
                    return json.loads(f.read())
            except Exception:
                log.warning("Failed to read cached news data from %s", paths.news_file)
        return {}

    def _add_language(self, request_add_language: RequestAddLanguage) -> None:
        from solidlsp.ls_config import Language

        try:
            language = Language(request_add_language.language)
        except ValueError:
            raise ValueError(f"Invalid language: {request_add_language.language}")
        # add_language is already thread-safe
        self._agent.add_language(language)

    def _remove_language(self, request_remove_language: RequestRemoveLanguage) -> None:
        from solidlsp.ls_config import Language

        try:
            language = Language(request_remove_language.language)
        except ValueError:
            raise ValueError(f"Invalid language: {request_remove_language.language}")
        # remove_language is already thread-safe
        self._agent.remove_language(language)

    @staticmethod
    def _find_first_free_port(start_port: int, host: str) -> int:
        port = start_port
        while port <= 65535:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind((host, port))
                    return port
            except OSError:
                port += 1

        raise RuntimeError(f"No free ports found starting from {start_port}")

    def run(self, host: str, port: int) -> int:
        """
        Runs the dashboard on the given host and port and returns the port number.
        """
        # patch flask.cli.show_server to avoid printing the server info
        from flask import cli

        cli.show_server_banner = lambda *args, **kwargs: None

        self._app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
        return port

    def run_in_thread(self, host: str) -> tuple[threading.Thread, int]:
        port = self._find_first_free_port(0x5EDA, host)
        log.info("Starting dashboard (listen_address=%s, port=%d)", host, port)
        thread = threading.Thread(target=lambda: self.run(host=host, port=port), daemon=True)
        thread.start()
        return thread, port


class SerenaDashboardViewer:
    """
    Minimal pywebview wrapper with optional system tray.
    """

    def __init__(
        self,
        url: str,
        *,
        start_minimized: bool = False,
        width: int = 1400,
        height: int = 900,
    ):
        self.url = url
        # Use system tray to allow hiding to tray and intercepting close to hide instead of quit
        self.tray = True
        self.title = "Serena Dashboard"
        self.width = width
        self.height = height
        self.start_minimized = start_minimized

        self.window: webview.Window
        self._tray_icon: Any
        self._quitting = False
        self._app_icon_path: str | None = None

    @staticmethod
    def is_current_platform_supported() -> bool:
        """
        :return: whether the current platform supports the dashboard viewer
        """
        # The dashboard viewer (with system tray) is technically supported only on Windows and macOS.
        # Linux support is problematic; see https://github.com/oraios/serena/pull/1117#issuecomment-4128753943
        supported_platforms = [
            "win32",
            # NOTE: Disabling macOS support for now, because the tray behaviour is suboptimal (too many icons when
            #   subagents are spawned, etc.)
            # "darwin"
        ]
        return sys.platform in supported_platforms

    def run(self) -> None:
        # set app id (avoid app being lumped together with other Python-based apps in Windows taskbar)
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("oraios.serena")

        dashboard_path = Path(SERENA_DASHBOARD_DIR)
        # .ico is Windows-only; macOS expects a PNG for the window/dock icon.
        icon_filename = "serena.ico" if sys.platform == "win32" else "serena-icon-1024-mac.png"
        icon_path = str(dashboard_path / icon_filename)
        self._app_icon_path = icon_path

        # Create hidden to avoid flash; show/restore/minimize in start callback.
        window = webview.create_window(
            self.title,
            self.url,
            width=self.width,
            height=self.height,
            hidden=self.start_minimized,
            text_select=True,
            zoomable=True,
        )
        assert window is not None
        self.window = window

        if self.tray:
            self.window.events.closing += self._on_closing
            self._start_tray()

        def _start_callback() -> None:
            if self.start_minimized:
                self._hide_window()
            else:
                self._show_window()

        webview.start(_start_callback, icon=icon_path)

    def _show_window(self) -> None:
        if not self.window:
            return

        if sys.platform == "darwin":
            from PyObjCTools.AppHelper import callAfter

            callAfter(self._show_window_on_macos)
        else:
            self.window.show()
            self.window.restore()

    def _hide_window(self) -> None:
        if not self.window:
            return

        if sys.platform == "darwin":
            from PyObjCTools.AppHelper import callAfter

            callAfter(self._hide_window_on_macos)
        else:
            self.window.hide()

    def _show_window_on_macos(self) -> None:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyRegular,
        )
        from PyObjCTools.AppHelper import callLater

        ns_app = NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        self._set_macos_app_icon(ns_app)
        ns_app.unhide_(None)
        ns_app.activateIgnoringOtherApps_(True)
        # Give the status item menu a beat to close before restoring the window.
        callLater(0.1, self._restore_window_on_macos)

    def _restore_window_on_macos(self) -> None:
        self.window.show()
        self.window.restore()

    def _hide_window_on_macos(self) -> None:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )

        self.window.hide()
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    def _set_macos_app_icon(self, ns_app: Any) -> None:
        if not self._app_icon_path:
            return

        from AppKit import NSImage

        ns_image = NSImage.alloc().initByReferencingFile_(self._app_icon_path)
        if ns_image is not None:
            ns_app.setApplicationIconImage_(ns_image)

    def _on_closing(self) -> bool:
        """Intercept window close: hide window instead of quitting (macOS standard behavior)."""
        if self._quitting:
            return True
        self._hide_window()
        return False  # prevent the window from actually closing

    def _start_tray(self) -> None:
        # import pystray locally, because the import fails when there is no display!
        import pystray
        from pystray import MenuItem as Item
        from pystray._base import Icon as TrayIcon

        dashboard_path = Path(SERENA_DASHBOARD_DIR)

        # macOS menu bar icons are displayed at 16pt; 32px covers Retina (@2x).
        # Windows/Linux tray icons are larger, so 48px is the better fit there.
        icon_filename = "serena-icon-tray-mac.png" if sys.platform == "darwin" else "serena-icon-48.png"
        icon_img = Image.open(dashboard_path / icon_filename)

        def show(_icon: TrayIcon, _item: Item) -> None:
            self._show_window()

        def hide(_icon: TrayIcon, _item: Item) -> None:
            self._hide_window()

        def quit_app(_icon: TrayIcon, _item: Item) -> None:
            self._quitting = True
            try:
                _icon.stop()
            finally:
                if self.window:
                    self.window.destroy()

        menu = pystray.Menu(
            Item("Open", show, default=True),
            Item("Hide", hide),
            Item("Quit", quit_app),
        )

        kwargs: dict[str, Any] = {}
        if sys.platform == "darwin":
            # Passing darwin_nsapplication integrates pystray with the NSApplication
            # run loop that webview.start() is about to enter.  sharedApplication()
            # is idempotent; pywebview will reuse the same singleton.
            from AppKit import NSApplication

            kwargs["darwin_nsapplication"] = NSApplication.sharedApplication()

        self._tray_icon = pystray.Icon("dashboard_viewer", icon_img, self.title, menu, **kwargs)

        # On Windows/Linux, run_detached spawns pystray's own internal thread and
        # returns immediately.  On macOS it hooks into the NSApplication run loop
        # that webview.start() is about to enter (run_detached is always called
        # before webview.start() on macOS — see run()).
        self._tray_icon.run_detached()
