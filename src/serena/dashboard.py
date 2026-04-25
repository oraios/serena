import json
import multiprocessing
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Self

import psutil
from flask import Flask, Response, redirect, request, send_from_directory
from PIL import Image
from pydantic import BaseModel
from sensai.util import logging
from sensai.util.pickle import dump_pickle, load_pickle

from serena.analytics import ToolUsageStats
from serena.config.serena_config import SerenaConfig, SerenaPaths
from serena.constants import SERENA_DASHBOARD_DIR, SerenaPorts
from serena.task_executor import TaskExecutor
from serena.util.logging import MemoryLogHandler
from serena.util.pywebview import WebViewWithTray

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


class ReadNews:
    def __init__(self, read_ids: list[str], legacy_last_read_id: str | None = None):
        self._read_ids = set(read_ids)
        self._legacy_last_read_id = legacy_last_read_id

    @staticmethod
    def load() -> "ReadNews":
        read_news_path = SerenaPaths().news_read_items_file
        legacy_last_read_id_path = SerenaPaths().news_legacy_last_read_id_file

        def load_legacy_last_read_id() -> str | None:
            if not os.path.exists(legacy_last_read_id_path):
                return None
            with open(legacy_last_read_id_path, encoding="utf-8") as f:
                last_read_news_id = f.read().strip()
                if last_read_news_id == "20262103":
                    last_read_news_id = "20260321"  # fix originally misnamed news id
                return last_read_news_id

        if os.path.exists(read_news_path):
            return load_pickle(read_news_path)
        else:
            instance = ReadNews(read_ids=[], legacy_last_read_id=load_legacy_last_read_id())
            instance._save()
            try:
                os.unlink(legacy_last_read_id_path)
            except:
                pass
            return instance

    def _save(self) -> None:
        dump_pickle(self, SerenaPaths().news_read_items_file)

    def is_read(self, identifier: str) -> bool:
        if identifier in self._read_ids:
            return True
        if self._legacy_last_read_id is not None and identifier <= self._legacy_last_read_id:
            return True
        return False

    def mark_read(self, identifier: str) -> None:
        """
        Marks the given news snippet as read, saving the new state to disk
        """
        self._read_ids.add(identifier)
        self._save()


class SerenaDashboardAPI:
    BASE_PORT = SerenaPorts.DASHBOARD_API_BASE_PORT

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
        self._read_news = ReadNews.load()
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
                    "message": f"Task with id {escape(request_data.get('task_id'))} not found, maybe execution was already finished",
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

                serena_config_creation_date = SerenaConfig.get_config_file_creation_date()
                if serena_config_creation_date is None:
                    # should not normally happen, since config file should exist when the dashboard is started
                    # We assume a fresh installation in this case
                    log.error("Serena config file not found when starting the dashboard")
                    return {}
                serena_config_creation_date = serena_config_creation_date.strftime("%Y%m%d")

                # filter for news after the installation date
                post_installation_news = {k: v for k, v in all_news.items() if k >= serena_config_creation_date}

                # read unread news
                return {k: v for k, v in post_installation_news.items() if not self._read_news.is_read(k)}

            try:
                unread_news = _fetch_unread_news()
                return {"news": unread_news, "status": "success"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        @self._app.route("/mark_news_snippet_as_read", methods=["POST"])
        def mark_news_snippet_as_read() -> dict[str, str]:
            try:
                request_data = request.get_json()
                news_snippet_id = escape(str(request_data.get("news_snippet_id")))
                self._read_news.mark_read(news_snippet_id)
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
    _NEWS_JSON_URL = "https://oraios-software.de/serena_news.json"

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
        port = self._find_first_free_port(self.BASE_PORT, host)
        log.info("Starting dashboard (listen_address=%s, port=%d)", host, port)
        thread = threading.Thread(target=lambda: self.run(host=host, port=port), daemon=True)
        thread.start()
        return thread, port


def open_url_in_browser(url: str, use_subprocess: bool = False) -> None:
    """
    Opens the given URL in the user's default web browser,
    optionally using a subprocess to ensure that no output is written to stdout
    (highly problematic when run within a stdio MCP server context)

    :param url: the URL to open
    :param use_subprocess: whether to use a subprocess to opening the URL, making stdio contamination impossible
    """
    if use_subprocess:
        # Use a subprocess to avoid any output from webbrowser.open being written to stdout
        try:
            subprocess.Popen(
                [sys.executable, "-c", f"import webbrowser; webbrowser.open({url!r})"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=False,
            )
        except Exception as e:
            # Subprocess creation can fail in rare cases (e.g. on some Linux systems; possibly subprocess/glibc bug)
            # See #1363
            log.error("Failed to open URL (%s) in subprocess; %s", url, e)
    else:
        import webbrowser

        webbrowser.open(url)


class SerenaDashboardViewer(WebViewWithTray):
    """
    Minimal pywebview wrapper that opens a dashboard in a native window with optional system tray.
    """

    DEBUG = False

    def __init__(
        self,
        url: str,
        *,
        width: int = 1400,
        height: int = 900,
        start_minimized: bool = False,
        parent_process_id: int | None = None,
        tray: bool = True,
    ):
        """
        :param url: the URL to open
        :param width: the width of the window
        :param height: the height of the window
        :param start_minimized: whether to start the window minimized (to the tray if tray is enabled)
        :param parent_process_id: the process ID of the parent Serena agent process, which is monitored for termination,
            automatically closing the dashboard when the parent process dies
        :param tray: whether to use a system tray icon (which the app minimizes to when the window is closed)
        """
        dashboard_path = Path(SERENA_DASHBOARD_DIR)

        # .ico is Windows-only; macOS expects a PNG for the window/dock icon.
        app_icon_filename = "serena.ico" if sys.platform == "win32" else "serena-icon-1024-mac.png"
        app_icon_path = str(dashboard_path / app_icon_filename)

        tray_icon_filename = "serena-icon-tray-mac.png" if sys.platform == "darwin" else "serena-icon-48.png"
        tray_icon_path = str(dashboard_path / tray_icon_filename)

        super().__init__(
            url,
            title="Serena Dashboard",
            tray=tray,
            width=width,
            height=height,
            start_minimized=start_minimized,
            parent_process_id=parent_process_id,
            app_id="oraios.serena",
            app_icon_path=app_icon_path,
            tray_icon_path=tray_icon_path,
        )

    @staticmethod
    def is_current_platform_supported() -> bool:
        """
        :return: whether the current platform supports the native dashboard viewer (and tray manager).
        """
        # supported on Windows and macOS; Linux support is problematic
        # (see https://github.com/oraios/serena/pull/1117#issuecomment-4128753943)
        supported_platforms = [
            "win32",
            "darwin",
        ]
        return sys.platform in supported_platforms

    def run(self) -> None:
        if self.DEBUG:
            logging.configure(level=logging.DEBUG, stream=sys.stderr)
            logging.add_file_logger(SerenaPaths().get_next_log_file_path("dashboard-viewer"))

        super().run()


@dataclass
class TrayManagedInstance:
    """A registered Serena dashboard instance managed by the tray manager."""

    port: int
    """the port on which the dashboard API is listening"""

    parent_process: psutil.Process
    """the process of the Serena agent owning this dashboard instance"""

    dashboard_url: str
    """the full URL to the dashboard frontend"""

    project: str | None
    """the name of the active project, or None if no project is activated"""

    started_at: str
    """ISO 8601 timestamp of when the agent instance was started"""


class SerenaDashboardTrayManager:
    """
    Singleton process managing a system tray icon for all Serena dashboard instances.

    Runs a Flask backend on a fixed port and displays a single tray icon that
    aggregates all running Serena instances. Individual dashboard viewers are
    spawned on demand when the user clicks a menu item.

    The manager is started as a detached process by the first Serena agent that
    needs it and terminates automatically when no dashboard instances remain.
    """

    DEBUG = False

    PORT = SerenaPorts.TRAY_MANAGER_PORT

    HOST = "127.0.0.1"
    """listen address (local only)"""

    ALIVE_CHECK_INTERVAL_SECONDS = 3
    """interval in seconds between alive checks of registered instances"""

    def __init__(self, use_pywebview: bool = False, alive_check_use_pid: bool = True) -> None:
        """
        :param use_pywebview: whether to use pywebview-based viewer applications (separate child processes)
            for opening dashboards; if False, open them directly in the user's default web browser.
        :param alive_check_use_pid: whether to use the process ID for alive checks of registered instances.
            If True, the manager will check whether the process with the registered PID is still running.
            If False, the manager will perform an HTTP request to the instance's heartbeat endpoint to check
            if it's alive.
        """
        import pystray

        self._instances: dict[int, TrayManagedInstance] = {}
        self._lock = threading.Lock()
        self._tray_icon: Optional["pystray.Icon"] = None
        self._alive_check_use_pid = alive_check_use_pid
        self._app = Flask(__name__)
        self._setup_routes()
        self._use_pywebview = use_pywebview

    def _setup_routes(self) -> None:
        @self._app.route("/health", methods=["GET"])
        def health() -> dict[str, str]:
            return {"status": "alive"}

        @self._app.route("/register", methods=["POST"])
        def register() -> dict[str, str]:
            data = request.get_json()
            instance = TrayManagedInstance(
                port=data["port"],
                parent_process=psutil.Process(data["pid"]),
                dashboard_url=data["dashboard_url"],
                project=data.get("project"),
                started_at=data["started_at"],
            )
            log.info("Registering instance on port %d (project=%s)", instance.port, instance.project)
            with self._lock:
                self._instances[instance.port] = instance
            self._update_menu()

            # open a viewer immediately if requested
            if data.get("open_viewer", False):
                self._open_dashboard(instance)

            return {"status": "registered"}

        @self._app.route("/update_project", methods=["POST"])
        def update_project() -> dict[str, str]:
            data = request.get_json()
            port = data["port"]
            project = data.get("project")
            with self._lock:
                if port in self._instances:
                    self._instances[port].project = project
            self._update_menu()
            log.info("Updated project for instance on port %d to '%s'", port, project)
            return {"status": "updated"}

        @self._app.route("/unregister", methods=["POST"])
        def unregister() -> dict[str, str]:
            data = request.get_json()
            port = data["port"]
            with self._lock:
                self._instances.pop(port, None)
            self._update_menu()
            log.info("Unregistered instance on port %d", port)
            return {"status": "unregistered"}

    def _update_menu(self) -> None:
        if self._tray_icon:
            self._tray_icon.update_menu()

    def _build_menu_items(self) -> tuple[Any, ...]:
        """
        Callable that returns the current tray menu items.

        Invoked dynamically by pystray each time the menu is shown.
        When there is exactly one instance, it is marked as the default action
        so that a left-click on the tray icon opens the viewer immediately.
        When there are multiple instances, a hidden default item forces the menu
        to appear on left-click (Windows only; macOS always shows the menu).
        """
        from pystray import MenuItem as Item

        with self._lock:
            instances = list(self._instances.values())

        if not instances:
            return (Item("No instances", None, enabled=False),)

        # determine whether a single-instance shortcut applies
        is_single = len(instances) == 1

        items: list[Any] = []

        # for multi-instance: add a hidden default item that opens the menu on left-click
        if not is_single:

            def _force_show_menu(icon: Any, _item: Any) -> None:
                if hasattr(icon, "_show_menu"):
                    icon._show_menu()

            items.append(Item("Instances", _force_show_menu, default=True, visible=False))

        for inst in sorted(instances, key=lambda i: i.started_at):
            label = f"{inst.project or 'SerenaAgent'} ({inst.started_at})"

            # closure to capture the current instance
            def _make_callback(instance: TrayManagedInstance) -> Callable:
                def _callback(_icon: Any, _item: Any) -> None:
                    self._open_dashboard(instance)

                return _callback

            items.append(Item(label, _make_callback(inst), default=is_single))

        return tuple(items)

    def _open_dashboard(self, instance: TrayManagedInstance) -> None:
        """Opens the dashboard of the given instance."""
        if self._use_pywebview:
            # spawn pywebview process showing the dashboard
            process = multiprocessing.Process(
                target=self._run_viewer,
                args=(instance.dashboard_url,),
                daemon=True,
            )
            process.start()
        else:
            open_url_in_browser(instance.dashboard_url)

    @staticmethod
    def _run_viewer(url: str) -> None:
        """Process target for running a dashboard viewer window."""
        SerenaDashboardViewer(url, tray=False, start_minimized=False).run()

    def _alive_check_loop(self) -> None:
        """Periodically check whether registered instances are still reachable.

        Removes unreachable instances and terminates the manager when none remain.
        """
        time.sleep(max(1, 5 - self.ALIVE_CHECK_INTERVAL_SECONDS))  # initial delay to allow instances to start and register

        while True:
            time.sleep(self.ALIVE_CHECK_INTERVAL_SECONDS)

            try:
                dead_ports: list[int] = []

                if self._alive_check_use_pid:
                    with self._lock:
                        ports_and_processes = [(port, inst.parent_process) for port, inst in self._instances.items()]

                    dead_ports = []
                    for port, process in ports_and_processes:
                        is_dead = False
                        try:
                            if not process.is_running():
                                is_dead = True
                        except psutil.NoSuchProcess:
                            # parent process already exited
                            is_dead = True
                        if is_dead:
                            dead_ports.append(port)
                else:
                    # collect ports to check
                    with self._lock:
                        ports_to_check = list(self._instances.keys())

                    # probe each instance
                    for port in ports_to_check:
                        try:
                            url = f"http://127.0.0.1:{port}/heartbeat"
                            req = urllib.request.Request(url, method="GET")
                            urllib.request.urlopen(req, timeout=1)
                        except Exception:
                            dead_ports.append(port)

                # remove dead instances
                if dead_ports:
                    with self._lock:
                        for port in dead_ports:
                            self._instances.pop(port, None)
                            log.info("Removed unreachable instance on port %d", port)

                # terminate if no instances remain
                with self._lock:
                    remaining = len(self._instances)
                if remaining == 0:
                    log.info("No dashboard instances remaining; shutting down tray manager")
                    if self._tray_icon is not None:
                        self._tray_icon.stop()
                    return

            except Exception as e:
                log.error("Error during alive check loop: %s", e, exc_info=e)

    def run(self) -> None:
        """Run the tray manager (blocking). Starts Flask, alive-check thread, and tray icon."""
        import pystray

        if self.DEBUG:
            logging.configure(level=logging.DEBUG, stream=sys.stderr)
            logging.add_file_logger(SerenaPaths().get_next_log_file_path("tray-manager"))

        log.info("Starting tray manager")

        dashboard_path = Path(SERENA_DASHBOARD_DIR)

        # select the appropriate icon for the platform
        icon_filename = "serena-icon-tray-mac.png" if sys.platform == "darwin" else "serena-icon-48.png"
        icon_img = Image.open(dashboard_path / icon_filename)

        # start Flask in a background thread
        flask_thread = threading.Thread(
            target=lambda: self._app.run(host=self.HOST, port=self.PORT, debug=False, use_reloader=False, threaded=True),
            daemon=True,
        )
        flask_thread.start()

        # start alive-check in a background thread
        alive_thread = threading.Thread(target=self._alive_check_loop, daemon=True)
        alive_thread.start()

        # set up tray icon with a dynamic menu (callable returns items on each open)
        kwargs: dict[str, Any] = {}
        if sys.platform == "darwin":
            from AppKit import NSApplication

            kwargs["darwin_nsapplication"] = NSApplication.sharedApplication()

        self._tray_icon = pystray.Icon(
            "serena_tray_manager",
            icon_img,
            "Serena",
            menu=pystray.Menu(self._build_menu_items),
            **kwargs,
        )

        # blocks until stop() is called
        self._tray_icon.run()

    # ------------------------------------------------------------------
    # Class-level helpers (used by agents to interact with the manager)
    # ------------------------------------------------------------------

    @classmethod
    def is_current_platform_supported(cls) -> bool:
        """
        :return: whether the current platform supports the tray manager
        """
        # supported_platforms = ["win32", "darwin"]
        # return sys.platform in supported_platforms
        # TODO: Enable all platforms for the time being for users to try out (only Windows tested)
        return True

    @classmethod
    def is_running(cls) -> bool:
        """
        :return: True if a tray manager process is already listening on the fixed port
        """
        try:
            url = f"http://{cls.HOST}:{cls.PORT}/health"
            req = urllib.request.Request(url, method="GET")
            urllib.request.urlopen(req, timeout=2)
            return True
        except Exception:
            return False

    @classmethod
    def ensure_running(cls) -> None:
        """Ensure a tray manager process is running, starting one if necessary."""
        log.info("Ensuring dashboard tray manager availability")
        if cls.is_running():
            log.info("Dashboard tray manager is already running")
            return

        # spawn a detached process
        log.info("Starting new dashboard tray manager process")
        cmd = [
            sys.executable,
            "-c",
            "from serena.dashboard import SerenaDashboardTrayManager; SerenaDashboardTrayManager().run()",
        ]
        kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # CREATE_NO_WINDOW suppresses the console; CREATE_NEW_PROCESS_GROUP
            # isolates the child from the parent's Ctrl+C group.
            # Note: DETACHED_PROCESS must NOT be combined with CREATE_NO_WINDOW.
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            CREATE_NO_WINDOW = 0x08000000
            kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        else:
            kwargs["start_new_session"] = True

        subprocess.Popen(cmd, **kwargs)

        # wait for the manager to become available
        for _ in range(30):
            time.sleep(0.1)
            if cls.is_running():
                log.info("Dashboard tray manager started successfully")
                return
        log.warning("Dashboard tray manager did not start within the expected time")

    @classmethod
    def register_instance(cls, port: int, dashboard_url: str, project: str | None, started_at: str, open_viewer: bool = False) -> None:
        """Register a dashboard instance with the running tray manager.

        :param port: the port of the dashboard API (used for alive checks)
        :param dashboard_url: the full URL to the dashboard frontend
        :param project: the currently active project name, or None
        :param started_at: ISO 8601 timestamp of when the agent was started
        :param open_viewer: whether the tray manager should immediately open a viewer for this instance
        """
        url = f"http://{cls.HOST}:{cls.PORT}/register"
        data = json.dumps(
            {
                "port": port,
                "pid": os.getpid(),
                "dashboard_url": dashboard_url,
                "project": project,
                "started_at": started_at,
                "open_viewer": open_viewer,
            }
        ).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            log.warning("Failed to register with tray manager: %s", e)

    @classmethod
    def update_project(cls, port: int, project: str | None) -> None:
        """Notify the tray manager of a project change for the given instance.

        :param port: the port of the dashboard API
        :param project: the new active project name, or None
        """
        url = f"http://{cls.HOST}:{cls.PORT}/update_project"
        data = json.dumps({"port": port, "project": project}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            log.warning("Failed to update project with tray manager: %s", e)

    @classmethod
    def unregister_instance(cls, port: int) -> None:
        """Unregister a dashboard instance from the tray manager.

        :param port: the port of the dashboard API to unregister
        """
        url = f"http://{cls.HOST}:{cls.PORT}/unregister"
        data = json.dumps({"port": port}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=2)
        except Exception as e:
            log.warning("Failed to unregister from tray manager: %s", e)
