"""
The Serena Model Context Protocol (MCP) Server
"""

import multiprocessing
import os
import platform
import sys
import threading
import webbrowser
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, Union

import click
from pathspec import PathSpec
from sensai.util import logging
from sensai.util.logging import LogTime

from serena import serena_version
from serena.config.context_mode import SerenaAgentContext, SerenaAgentMode
from serena.config.serena_config import Project, SerenaConfig, get_serena_managed_dir
from serena.constants import (
    SERENA_LOG_FORMAT,
)
from serena.dashboard import MemoryLogHandler, SerenaDashboardAPI
from serena.prompt_factory import SerenaPromptFactory
from serena.symbol import SymbolManager
from serena.tools import Tool, ToolRegistry
from serena.util.file_system import GitignoreParser, match_path
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger

if TYPE_CHECKING:
    from serena.gui_log_viewer import GuiLogViewerHandler

log = logging.getLogger(__name__)
TTool = TypeVar("TTool", bound="Tool")
T = TypeVar("T")
SUCCESS_RESULT = "OK"
DEFAULT_TOOL_TIMEOUT: float = 240


class ProjectNotFoundError(Exception):
    pass


class LinesRead:
    def __init__(self) -> None:
        self.files: dict[str, set[tuple[int, int]]] = defaultdict(lambda: set())

    def add_lines_read(self, relative_path: str, lines: tuple[int, int]) -> None:
        self.files[relative_path].add(lines)

    def were_lines_read(self, relative_path: str, lines: tuple[int, int]) -> bool:
        lines_read_in_file = self.files[relative_path]
        return lines in lines_read_in_file

    def invalidate_lines_read(self, relative_path: str) -> None:
        if relative_path in self.files:
            del self.files[relative_path]


class MemoriesManager(ABC):
    @abstractmethod
    def load_memory(self, name: str) -> str:
        pass

    @abstractmethod
    def save_memory(self, name: str, content: str) -> str:
        pass

    @abstractmethod
    def list_memories(self) -> list[str]:
        pass

    @abstractmethod
    def delete_memory(self, name: str) -> str:
        pass


class MemoriesManagerMDFilesInProject(MemoriesManager):
    def __init__(self, project_root: str):
        self._memory_dir = Path(get_serena_managed_dir(project_root)) / "memories"
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_memory_file_path(self, name: str) -> Path:
        # strip all .md from the name. Models tend to get confused, sometimes passing the .md extension and sometimes not.
        name = name.replace(".md", "")
        filename = f"{name}.md"
        return self._memory_dir / filename

    def load_memory(self, name: str) -> str:
        memory_file_path = self._get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory file {name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding="utf-8") as f:
            return f.read()

    def save_memory(self, name: str, content: str) -> str:
        memory_file_path = self._get_memory_file_path(name)
        with open(memory_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Memory {name} written."

    def list_memories(self) -> list[str]:
        return [f.name.replace(".md", "") for f in self._memory_dir.iterdir() if f.is_file()]

    def delete_memory(self, name: str) -> str:
        memory_file_path = self._get_memory_file_path(name)
        memory_file_path.unlink()
        return f"Memory {name} deleted."


def create_ls_for_project(
    project: str | Project,
    log_level: int = logging.INFO,
    ls_timeout: float | None = DEFAULT_TOOL_TIMEOUT - 5,
    trace_lsp_communication: bool = False,
) -> SolidLanguageServer:
    """
    Create a language server for a project. Note that you will have to start it
    before performing any LS operations.

    :param project: either a path to the project root or a ProjectConfig instance.
        If no project.yml is found, the default project configuration will be used.
    :param log_level: the log level for the language server
    :param ls_timeout: the timeout for the language server
    :param trace_lsp_communication: whether to trace LSP communication
    :return: the language server
    """
    if isinstance(project, str):
        project_instance = Project.load(project, autogenerate=True)
    else:
        project_instance = project

    project_config = project_instance.project_config
    ignored_paths = project_config.ignored_paths
    if len(ignored_paths) > 0:
        log.info(f"Using {len(ignored_paths)} ignored paths from the explicit project configuration.")
        log.debug(f"Ignored paths: {ignored_paths}")
    if project_config.ignore_all_files_in_gitignore:
        log.info(f"Parsing all gitignore files in {project_instance.project_root}")
        gitignore_parser = GitignoreParser(project_instance.project_root)
        log.info(f"Found {len(gitignore_parser.get_ignore_specs())} gitignore files.")
        for spec in gitignore_parser.get_ignore_specs():
            log.debug(f"Adding {len(spec.patterns)} patterns from {spec.file_path} to the ignored paths.")
            ignored_paths.extend(spec.patterns)
    log.debug(f"Using {len(ignored_paths)} ignored paths in total.")
    multilspy_config = LanguageServerConfig(
        code_language=project_instance.language,
        ignored_paths=ignored_paths,
        trace_lsp_communication=trace_lsp_communication,
    )
    ls_logger = LanguageServerLogger(log_level=log_level)
    log.info(f"Creating language server instance for {project_instance.project_root}.")
    return SolidLanguageServer.create(
        multilspy_config,
        ls_logger,
        project_instance.project_root,
        timeout=ls_timeout,
    )


@click.command()
@click.argument("project", type=click.Path(exists=True), required=False, default=os.getcwd())
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]), default="WARNING")
def index_project(project: str, log_level: str = "INFO") -> None:
    """
    Index a project by saving the symbols of files to Serena's language server cache.

    :param project: the project to index. By default, the current working directory is used.
    """
    log_level_int = logging.getLevelNamesMapping()[log_level.upper()]
    project = os.path.abspath(project)
    print(f"Indexing symbols in project {project}")
    ls = create_ls_for_project(project, log_level=log_level_int)
    with ls.start_server():
        ls.index_repository()
    print(f"Symbols saved to {ls.cache_path}")


class SerenaAgent:
    def __init__(
        self,
        project: str | None = None,
        project_activation_callback: Callable[[], None] | None = None,
        serena_config: SerenaConfig | None = None,
        context: SerenaAgentContext | None = None,
        modes: list[SerenaAgentMode] | None = None,
    ):
        """
        :param project: the project to load immediately or None to not load any project; may be a path to the project or a name of
            an already registered project;
        :param project_activation_callback: a callback function to be called when a project is activated.
        :param serena_config: the Serena configuration or None to read the configuration from the default location.
        :param context: the context in which the agent is operating, None for default context.
            The context may adjust prompts, tool availability, and tool descriptions.
        :param modes: list of modes in which the agent is operating (they will be combined), None for default modes.
            The modes may adjust prompts, tool availability, and tool descriptions.
        """
        # obtain serena configuration using the decoupled factory function
        self.serena_config = serena_config or SerenaConfig.from_config_file()

        # adjust log level
        serena_log_level = self.serena_config.log_level
        if Logger.root.level > serena_log_level:
            log.info(f"Changing the root logger level to {serena_log_level}")
            Logger.root.setLevel(serena_log_level)

        # open GUI log window if enabled
        self._gui_log_handler: Union["GuiLogViewerHandler", None] = None  # noqa
        if self.serena_config.gui_log_window_enabled:
            if platform.system() == "Darwin":
                log.warning("GUI log window is not supported on macOS")
            else:
                # even importing on macOS may fail if tkinter dependencies are unavailable (depends on Python interpreter installation
                # which uv used as a base, unfortunately)
                from serena.gui_log_viewer import GuiLogViewer, GuiLogViewerHandler

                self._gui_log_handler = GuiLogViewerHandler(
                    GuiLogViewer("dashboard", title="Serena Logs"), level=serena_log_level, format_string=SERENA_LOG_FORMAT
                )
                Logger.root.addHandler(self._gui_log_handler)

        # set the agent context
        if context is None:
            context = SerenaAgentContext.load_default()
        self._context = context

        # instantiate all tool classes
        self._all_tools: dict[type[Tool], Tool] = {tool_class: tool_class(self) for tool_class in ToolRegistry.get_all_tool_classes()}
        tool_names = [tool.get_name_from_cls() for tool in self._all_tools.values()]

        # determine the set exposed tools (which e.g. the MCP shall see), limited by the context
        # (which is fixed for the session)
        excluded_tool_classes = set(self._context.get_excluded_tool_classes())
        self._exposed_tools = {tc: t for tc, t in self._all_tools.items() if tc not in excluded_tool_classes}

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_handler is not None:
            self._gui_log_handler.log_viewer.set_tool_names(tool_names)

        # start the dashboard (web frontend), registering its log handler
        if self.serena_config.web_dashboard:
            dashboard_log_handler = MemoryLogHandler(level=serena_log_level)
            Logger.root.addHandler(dashboard_log_handler)
            self._dashboard_thread, port = SerenaDashboardAPI(dashboard_log_handler, tool_names).run_in_thread()
            if self.serena_config.web_dashboard_open_on_launch:
                # open the dashboard URL in the default web browser (using a separate process to control
                # output redirection)
                process = multiprocessing.Process(target=self._open_dashboard, args=(port,))
                process.start()

        # log fundamental information
        log.info(f"Starting Serena server (version={serena_version()}, process id={os.getpid()}, parent process id={os.getppid()})")
        log.info("Configuration file: %s", self.serena_config.config_file_path)
        log.info("Available projects: {}".format(", ".join(self.serena_config.project_names)))

        # create executor for starting the language server and running tools in another thread
        # This executor is used to achieve linear task execution, so it is important to use a single-threaded executor.
        self._task_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SerenaAgentExecutor")
        self._task_executor_lock = threading.Lock()
        self._task_executor_task_index = 1

        # Initialize the prompt factory
        self.prompt_factory = SerenaPromptFactory()
        self._project_activation_callback = project_activation_callback

        # project-specific instances, which will be initialized upon project activation
        self._active_project: Project | None = None
        self._active_project_root: str | None = None
        self.language_server: SolidLanguageServer | None = None
        self.symbol_manager: SymbolManager | None = None
        self.memories_manager: MemoriesManager | None = None
        self.lines_read: LinesRead | None = None
        self.ignore_spec: PathSpec  # not set to None to avoid assert statements
        """Ignore spec, extracted from the project's gitignore files and the explicitly configured ignored paths."""

        # set the active modes
        if modes is None:
            modes = SerenaAgentMode.load_default_modes()
        self._modes = modes

        # log tool information
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name_from_cls() for tool in self._all_tools.values()])}")
        log.info(f"Number of exposed tools given {self._context}: {len(self._exposed_tools)}")

        self._active_tools: dict[type[Tool], Tool] = {}
        self._update_active_tools()

        # activate a project configuration (if provided or if there is only a single project available)
        if project is not None:
            try:
                self.activate_project_from_path_or_name(project)
            except ProjectNotFoundError as e:
                log.error(
                    f"Error activating project '{project}': {e}; Note that out-of-project configurations were migrated. "
                    "You should now pass either --project <project_name> or --project <project_root>."
                )

    @staticmethod
    def _open_dashboard(port: int) -> None:
        # Redirect stdout and stderr file descriptors to /dev/null,
        # making sure that nothing can be written to stdout/stderr, even by subprocesses
        null_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null_fd, sys.stdout.fileno())
        os.dup2(null_fd, sys.stderr.fileno())
        os.close(null_fd)

        # open the dashboard URL in the default web browser
        webbrowser.open(f"http://localhost:{port}/dashboard/index.html")

    def get_project_root(self) -> str:
        """
        :return: the root directory of the active project (if any); raises a ValueError if there is no active project
        """
        project = self.get_active_project()
        if project is None:
            raise ValueError("Cannot get project root if no project is active.")
        return project.project_root

    def path_is_inside_project(self, path: str | Path) -> bool:
        """
        Checks if the given (absolute or relative) path is inside the project directory.
        Note that even relative paths may be outside if the contain ".." or point to symlinks.
        """
        path = Path(path)
        _proj_root = Path(self.get_project_root())
        if not path.is_absolute():
            path = _proj_root / path

        path = path.resolve()
        return path.is_relative_to(_proj_root)

    def path_is_gitignored(self, path: str | Path) -> bool:
        """
        Checks if the given path is ignored by git. Non absolute paths are assumed to be relative to the project root.
        """
        path = Path(path)
        if path.is_absolute():
            relative_path = path.relative_to(self.get_project_root())
        else:
            relative_path = path

        # always ignore paths inside .git
        if len(relative_path.parts) > 0 and relative_path.parts[0] == ".git":
            return True

        return match_path(str(relative_path), self.ignore_spec, root_path=self.get_project_root())

    def validate_relative_path(self, relative_path: str) -> None:
        """
        Validates that the given relative path is safe to read or edit,
        meaning it's inside the project directory and is not ignored by git.
        """
        if not self.path_is_inside_project(relative_path):
            raise ValueError(f"{relative_path=} points to path outside of the repository root, can't use it for safety reasons")

        if self.path_is_gitignored(relative_path):
            raise ValueError(f"File {relative_path} is gitignored, can't read or edit it for safety reasons")

    def get_exposed_tool_instances(self) -> list["Tool"]:
        """
        :return: the tool instances which are exposed (e.g. to the MCP client).
            Note that the set of exposed tools is fixed for the session, as
            clients don't react to changes in the set of tools, so this is the superset
            of tools that can be offered during the session.
            If a client should attempt to use a tool that is dynamically disabled
            (e.g. because a project is activated that disables it), it will receive an error.
        """
        return list(self._exposed_tools.values())

    def get_active_project(self) -> Project | None:
        """
        :return: the active project or None if no project is active
        """
        return self._active_project

    def set_modes(self, modes: list[SerenaAgentMode]) -> None:
        """
        Set the current mode configurations.

        :param modes: List of mode names or paths to use
        """
        self._modes = modes
        self._update_active_tools()

        log.info(f"Set modes to {[mode.name for mode in modes]}")

    def get_active_modes(self) -> list[SerenaAgentMode]:
        """
        :return: the list of active modes
        """
        return list(self._modes)

    def create_system_prompt(self) -> str:
        return self.prompt_factory.create_system_prompt(
            context_system_prompt=self._context.prompt,
            mode_system_prompts=[mode.prompt for mode in self._modes],
        )

    def _update_active_tools(self) -> None:
        """
        Update the active tools based on context, modes, and project configuration.
        All tool exclusions are merged together.
        """
        excluded_tool_classes: set[type[Tool]] = set()
        # modes
        for mode in self._modes:
            mode_excluded_tool_classes = mode.get_excluded_tool_classes()
            if len(mode_excluded_tool_classes) > 0:
                log.info(
                    f"Mode {mode.name} excluded {len(mode_excluded_tool_classes)} tools: {', '.join([tool.get_name_from_cls() for tool in mode_excluded_tool_classes])}"
                )
                excluded_tool_classes.update(mode_excluded_tool_classes)
        # context
        context_excluded_tool_classes = self._context.get_excluded_tool_classes()
        if len(context_excluded_tool_classes) > 0:
            log.info(
                f"Context {self._context.name} excluded {len(context_excluded_tool_classes)} tools: {', '.join([tool.get_name_from_cls() for tool in context_excluded_tool_classes])}"
            )
            excluded_tool_classes.update(context_excluded_tool_classes)
        # project config
        if self._active_project is not None:
            project_excluded_tool_classes = self._active_project.project_config.get_excluded_tool_classes()
            if len(project_excluded_tool_classes) > 0:
                log.info(
                    f"Project {self._active_project.project_name} excluded {len(project_excluded_tool_classes)} tools: {', '.join([tool.get_name_from_cls() for tool in project_excluded_tool_classes])}"
                )
                excluded_tool_classes.update(project_excluded_tool_classes)
            if self._active_project.project_config.read_only:
                for tool_class in self._all_tools:
                    if tool_class.can_edit():
                        excluded_tool_classes.add(tool_class)

        self._active_tools = {
            tool_class: tool_instance for tool_class, tool_instance in self._all_tools.items() if tool_class not in excluded_tool_classes
        }

        log.info(f"Active tools after all exclusions ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")

    def issue_task(self, task: Callable[[], Any], name: str | None = None) -> Future:
        """
        Issue a task to the executor for asynchronous execution.
        It is ensured that tasks are executed in the order they are issued, one after another.

        :param task: the task to execute
        :param name: the name of the task for logging purposes; if None, use the task function's name
        :return: a Future object representing the execution of the task
        """
        with self._task_executor_lock:
            task_name = f"Task-{self._task_executor_task_index}[{name or task.__name__}]"
            self._task_executor_task_index += 1

            def task_execution_wrapper() -> Any:
                with LogTime(task_name, logger=log):
                    return task()

            log.info(f"Scheduling {task_name}")
            return self._task_executor.submit(task_execution_wrapper)

    def execute_task(self, task: Callable[[], T]) -> T:
        """
        Executes the given task synchronously via the agent's task executor.
        This is useful for tasks that need to be executed immediately and whose results are needed right away.

        :param task: the task to execute
        :return: the result of the task execution
        """
        future = self.issue_task(task)
        return future.result()

    def _activate_project(self, project: Project) -> None:
        log.info(f"Activating {project.project_name} at {project.project_root}")
        self._active_project = project
        self._update_active_tools()

        # initialize project-specific instances which do not depend on the language server
        self.memories_manager = MemoriesManagerMDFilesInProject(project.project_root)
        self.lines_read = LinesRead()

        # reset project-specific instances that depend on the language server
        self.symbol_manager = None

        def init_language_server() -> None:
            # start the language server
            with LogTime("Language server initialization", logger=log):
                self.reset_language_server()
                assert self.language_server is not None
                self.ignore_spec = self.language_server.get_ignore_spec()

            # initialize project-specific instances which depend on the language server
            log.debug(f"Initializing symbol and memories manager for {project.project_name} at {project.project_root}")
            self.symbol_manager = SymbolManager(self.language_server, self)

        # initialize the language server in the background
        self.issue_task(init_language_server)

        if self._project_activation_callback is not None:
            self._project_activation_callback()

    def activate_project_from_path_or_name(self, project_root_or_name: str) -> tuple[Project, bool, bool]:
        """
        Activate a project from a path or a name.
        If the project was already registered, it will just be activated. If it was not registered,
        the project will be registered and activated. After that, the project can be activated again
        by name (not just by path).
        :return: a tuple of the project instance and two booleans indicating if a new project was added and if a new project configuration for the
            added project was generated.
        """
        new_project_generated = False
        new_project_config_generated = False
        project_instance: Project | None = self.serena_config.get_project(project_root_or_name)
        if project_instance is not None:
            log.info(f"Found registered project {project_instance.project_name} at path {project_instance.project_root}.")
        else:
            if not os.path.isdir(project_root_or_name):
                raise ProjectNotFoundError(
                    f"Project '{project_root_or_name}' not found: Not a valid project name or directory. "
                    f"Existing project names: {self.serena_config.project_names}"
                )
            project_instance, new_project_config_generated = self.serena_config.add_project_from_path(project_root_or_name)
            new_project_generated = True
            log.info(f"Added new project {project_instance.project_name} for path {project_instance.project_root}.")
            if new_project_config_generated:
                log.info(
                    f"Note: A new project configuration with language {project_instance.project_config.language.value} "
                    f"was autogenerated since no project configuration was found in {project_root_or_name}."
                )
        self._activate_project(project_instance)
        return project_instance, new_project_generated, new_project_config_generated

    def get_active_tool_classes(self) -> list[type["Tool"]]:
        """
        :return: the list of active tool classes for the current project
        """
        return list(self._active_tools.keys())

    def get_active_tool_names(self) -> list[str]:
        """
        :return: the list of names of the active tools for the current project
        """
        return sorted([tool.get_name_from_cls() for tool in self.get_active_tool_classes()])

    def tool_is_active(self, tool_class: type["Tool"] | str) -> bool:
        """
        :param tool_class: the class or name of the tool to check
        :return: True if the tool is active, False otherwise
        """
        if isinstance(tool_class, str):
            return tool_class in self.get_active_tool_names()
        else:
            return tool_class in self.get_active_tool_classes()

    def get_current_config_overview(self) -> str:
        """
        :return: a string overview of the current configuration, including the active and available configuration options
        """
        result_str = "Current configuration:\n"
        result_str += f"Serena version: {serena_version()}\n"
        result_str += f"Loglevel: {self.serena_config.log_level}, trace_lsp_communication={self.serena_config.trace_lsp_communication}\n"
        if self._active_project is not None:
            result_str += f"Active project: {self._active_project.project_name}\n"
        else:
            result_str += "No active project\n"
        result_str += "Available projects:\n" + "\n".join(list(self.serena_config.project_names)) + "\n"
        result_str += f"Active context: {self._context.name}\n"

        # Active modes
        active_mode_names = [mode.name for mode in self.get_active_modes()]
        result_str += "Active modes: {}\n".format(", ".join(active_mode_names)) + "\n"

        # Available but not active modes
        all_available_modes = SerenaAgentMode.list_registered_mode_names()
        inactive_modes = [mode for mode in all_available_modes if mode not in active_mode_names]
        if inactive_modes:
            result_str += "Available but not active modes: {}\n".format(", ".join(inactive_modes)) + "\n"

        # Active tools
        result_str += "Active tools (after all exclusions from the project, context, and modes):\n"
        active_tool_names = self.get_active_tool_names()
        # print the tool names in chunks
        chunk_size = 4
        for i in range(0, len(active_tool_names), chunk_size):
            chunk = active_tool_names[i : i + chunk_size]
            result_str += "  " + ", ".join(chunk) + "\n"

        # Available but not active tools
        all_tool_names = sorted([tool.get_name_from_cls() for tool in self._all_tools.values()])
        inactive_tool_names = [tool for tool in all_tool_names if tool not in active_tool_names]
        if inactive_tool_names:
            result_str += "Available but not active tools:\n"
            for i in range(0, len(inactive_tool_names), chunk_size):
                chunk = inactive_tool_names[i : i + chunk_size]
                result_str += "  " + ", ".join(chunk) + "\n"

        return result_str

    def is_language_server_running(self) -> bool:
        return self.language_server is not None and self.language_server.is_running()

    def reset_language_server(self) -> None:
        """
        Starts/resets the language server for the current project
        """
        tool_timeout = self.serena_config.tool_timeout
        if tool_timeout is None or tool_timeout < 0:
            ls_timeout = None
        else:
            if tool_timeout < 10:
                raise ValueError(f"Tool timeout must be at least 10 seconds, but is {tool_timeout} seconds")
            ls_timeout = tool_timeout - 5  # the LS timeout is for a single call, it should be smaller than the tool timeout

        # stop the language server if it is running
        if self.is_language_server_running():
            assert self.language_server is not None
            log.info(f"Stopping the current language server at {self.language_server.repository_root_path} ...")
            self.language_server.stop()
            self.language_server = None

        # instantiate and start the language server
        assert self._active_project is not None
        self.language_server = create_ls_for_project(
            self._active_project,
            log_level=self.serena_config.log_level,
            ls_timeout=ls_timeout,
            trace_lsp_communication=self.serena_config.trace_lsp_communication,
        )
        log.info(f"Starting the language server for {self._active_project.project_name}")
        self.language_server.start()
        if not self.language_server.is_running():
            raise RuntimeError(
                f"Failed to start the language server for {self._active_project.project_name} at {self._active_project.project_root}"
            )
        if self.symbol_manager is not None:
            log.debug("Setting the language server in the agent's symbol manager")
            self.symbol_manager.set_language_server(self.language_server)
        else:
            log.debug("No symbol manager available yet, skipping setting the language server")

    def get_tool(self, tool_class: type[TTool]) -> TTool:
        return self._all_tools[tool_class]  # type: ignore

    def print_tool_overview(self) -> None:
        ToolRegistry.print_tool_overview(self._active_tools.values())

    def mark_file_modified(self, relativ_path: str) -> None:
        assert self.lines_read is not None
        self.lines_read.invalidate_lines_read(relativ_path)

    def __del__(self) -> None:
        """
        Destructor to clean up the language server instance and GUI logger
        """
        if not hasattr(self, "_is_initialized"):
            return
        log.info("SerenaAgent is shutting down ...")
        if self.is_language_server_running():
            log.info("Stopping the language server ...")
            assert self.language_server is not None
            self.language_server.save_cache()
            self.language_server.stop()
        if self._gui_log_handler:
            log.info("Stopping the GUI log window ...")
            self._gui_log_handler.stop_viewer()
            Logger.root.removeHandler(self._gui_log_handler)
