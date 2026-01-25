import os
import socket
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from flask import Flask, Response, request, send_from_directory
from pydantic import BaseModel
from sensai.util import logging

from murena.analytics import ToolUsageStats
from murena.config.murena_config import LanguageBackend, MurenaPaths
from murena.constants import MURENA_DASHBOARD_DIR
from murena.task_executor import TaskExecutor
from murena.util.logging import MemoryLogHandler

if TYPE_CHECKING:
    from murena.agent import MurenaAgent

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


class ResponseGetMurenaConfig(BaseModel):
    content: str


class RequestSaveMurenaConfig(BaseModel):
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


class MurenaDashboardAPI:
    log = logging.getLogger(__qualname__)

    def __init__(
        self,
        memory_log_handler: MemoryLogHandler,
        tool_names: list[str],
        agent: "MurenaAgent",
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
            return send_from_directory(MURENA_DASHBOARD_DIR, filename)

        @self._app.route("/dashboard/")
        def serve_dashboard_index() -> Response:
            return send_from_directory(MURENA_DASHBOARD_DIR, "index.html")

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
            self._shutdown()
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

        @self._app.route("/get_murena_config", methods=["GET"])
        def get_murena_config() -> dict[str, Any]:
            try:
                result = self._get_murena_config()
                return result.model_dump()
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/save_murena_config", methods=["POST"])
        def save_murena_config() -> dict[str, str]:
            request_data = request.get_json()
            if not request_data:
                return {"status": "error", "message": "No data provided"}
            request_save_config = RequestSaveMurenaConfig.model_validate(request_data)
            try:
                self._save_murena_config(request_save_config)
                return {"status": "success", "message": "Murena config saved successfully"}
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

        @self._app.route("/news_snippet_ids", methods=["GET"])
        def get_news_snippet_ids() -> dict[str, str | list[int]]:
            def _get_unread_news_ids() -> list[int]:
                all_news_files = (Path(MURENA_DASHBOARD_DIR) / "news").glob("*.html")
                all_news_ids = [int(f.stem) for f in all_news_files]
                news_snippet_id_file = MurenaPaths().news_snippet_id_file
                if not os.path.exists(news_snippet_id_file):
                    return all_news_ids
                with open(news_snippet_id_file, encoding="utf-8") as f:
                    last_read_news_id = int(f.read().strip())
                return [news_id for news_id in all_news_ids if news_id > last_read_news_id]

            try:
                unread_news_ids = _get_unread_news_ids()
                return {"news_snippet_ids": unread_news_ids, "status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/mark_news_snippet_as_read", methods=["POST"])
        def mark_news_snippet_as_read() -> dict[str, str]:
            try:
                request_data = request.get_json()
                news_snippet_id = int(request_data.get("news_snippet_id"))
                news_snippet_id_file = MurenaPaths().news_snippet_id_file
                with open(news_snippet_id_file, "w", encoding="utf-8") as f:
                    f.write(str(news_snippet_id))
                return {"status": "success", "message": f"Marked news snippet {news_snippet_id} as read"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

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

    def _get_config_overview(self) -> ResponseConfigOverview:
        from murena.config.context_mode import MurenaAgentContext, MurenaAgentMode
        from murena.tools.tools_base import Tool

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
            "path": MurenaAgentContext.get_path(context.name, instance=context),
        }

        # Get active modes
        modes = self._agent.get_active_modes()
        modes_info = [
            {"name": mode.name, "description": mode.description, "path": MurenaAgentMode.get_path(mode.name, instance=mode)}
            for mode in modes
        ]
        active_mode_names = [mode.name for mode in modes]

        # Get active tools
        active_tools = self._agent.get_active_tool_names()

        # Get registered projects
        registered_projects: list[dict[str, str | bool]] = []
        for proj in self._agent.murena_config.projects:
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
        all_mode_names = MurenaAgentMode.list_registered_mode_names()
        available_modes: list[dict[str, str | bool]] = []
        for mode_name in all_mode_names:
            try:
                mode_path = MurenaAgentMode.get_path(mode_name)
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
        all_context_names = MurenaAgentContext.list_registered_context_names()
        available_contexts: list[dict[str, str | bool]] = []
        for context_name in all_context_names:
            try:
                context_path = MurenaAgentContext.get_path(context_name)
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
            available_memories = project.memories_manager.list_memories()

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
            jetbrains_mode=self._agent.murena_config.language_backend == LanguageBackend.JETBRAINS,
            languages=languages,
            encoding=encoding,
            current_client=Tool.get_last_tool_call_client_str(),
        )

    def _shutdown(self) -> None:
        log.info("Shutting down Murena")
        if self._shutdown_callback:
            self._shutdown_callback()
        else:
            # noinspection PyProtectedMember
            # noinspection PyUnresolvedReferences
            os._exit(0)

    def _get_available_languages(self) -> ResponseAvailableLanguages:
        from solidlsp.ls_config import Language

        def run() -> ResponseAvailableLanguages:
            all_languages = [lang.value for lang in Language.iter_all(include_experimental=False)]

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

            project.memories_manager.save_memory(request_save_memory.memory_name, request_save_memory.content)

        self._agent.execute_task(run, logged=True, name="SaveMemory")

    def _delete_memory(self, request_delete_memory: RequestDeleteMemory) -> None:
        def run() -> None:
            project = self._agent.get_active_project()
            if project is None:
                raise ValueError("No active project")

            project.memories_manager.delete_memory(request_delete_memory.memory_name)

        self._agent.execute_task(run, logged=True, name="DeleteMemory")

    def _get_murena_config(self) -> ResponseGetMurenaConfig:
        config_path = self._agent.murena_config.config_file_path
        if config_path is None or not os.path.exists(config_path):
            raise ValueError("Murena config file not found")

        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        return ResponseGetMurenaConfig(content=content)

    def _save_murena_config(self, request_save_config: RequestSaveMurenaConfig) -> None:
        def run() -> None:
            config_path = self._agent.murena_config.config_file_path
            if config_path is None:
                raise ValueError("Murena config file path not set")

            with open(config_path, "w", encoding="utf-8") as f:
                f.write(request_save_config.content)

        self._agent.execute_task(run, logged=True, name="SaveMurenaConfig")

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

    def run_in_thread(self, host: str, start_port: int = 0x5EE2) -> tuple[threading.Thread, int]:
        port = self._find_first_free_port(start_port, host)
        log.info("Starting dashboard (listen_address=%s, port=%d)", host, port)
        thread = threading.Thread(target=lambda: self.run(host=host, port=port), daemon=True)
        thread.start()
        return thread, port
