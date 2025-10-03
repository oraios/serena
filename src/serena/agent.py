"""
The Serena Model Context Protocol (MCP) Server
"""

import multiprocessing
import os
import platform
import sys
import threading
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from logging import Logger
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from interprompt.jinja_template import JinjaTemplate
from sensai.util import logging
from sensai.util.logging import LogTime
from serena import serena_version
from serena.analytics import RegisteredTokenCountEstimator, ToolUsageStats
from serena.config.context_mode import RegisteredContext, SerenaAgentContext, SerenaAgentMode
from serena.config.serena_config import SerenaConfig, ToolInclusionDefinition, ToolSet
from serena.dashboard import SerenaDashboardAPI
from serena.project import Project
from serena.prompt_factory import SerenaPromptFactory
from serena.tools import ActivateProjectTool, GetCurrentConfigTool, Tool, ToolMarker, ToolRegistry
from serena.util.inspection import iter_subclasses
from serena.util.logging import MemoryLogHandler
from solidlsp import SolidLanguageServer

if TYPE_CHECKING:
    from serena.gui_log_viewer import GuiLogViewer
    from serena.lsp_manager import LSPManager  # FIX #5: Proper forward reference

log = logging.getLogger(__name__)
TTool = TypeVar("TTool", bound="Tool")
T = TypeVar("T")
SUCCESS_RESULT = "OK"


class ProjectNotFoundError(Exception):
    pass


class AvailableTools:
    def __init__(self, tools: list[Tool]):
        """
        :param tools: the list of available tools
        """
        self.tools = tools
        self.tool_names = [tool.get_name_from_cls() for tool in tools]
        self.tool_marker_names = set()
        for marker_class in iter_subclasses(ToolMarker):
            for tool in tools:
                if isinstance(tool, marker_class):
                    self.tool_marker_names.add(marker_class.__name__)

    def __len__(self) -> int:
        return len(self.tools)


class SerenaAgent:
    def __init__(
        self,
        project: str | None = None,
        project_activation_callback: Callable[[], None] | None = None,
        serena_config: SerenaConfig | None = None,
        context: SerenaAgentContext | None = None,
        modes: list[SerenaAgentMode] | None = None,
        memory_log_handler: MemoryLogHandler | None = None,
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
        :param memory_log_handler: a MemoryLogHandler instance from which to read log messages; if None, a new one will be created
            if necessary.
        """
        # obtain serena configuration using the decoupled factory function
        self.serena_config = serena_config or SerenaConfig.from_config_file()

        # project-specific instances, which will be initialized upon project activation
        self._active_project: Project | None = None
        # FIX #5: Use proper TYPE_CHECKING import instead of string literal
        self.lsp_manager: "LSPManager | None" = None  # NEW: Polyglot support
        self._language_server: SolidLanguageServer | None = None  # DEPRECATED: Use lsp_manager
        self.memories_manager: MemoriesManager | None = None
        self.lines_read: LinesRead | None = None

        # adjust log level
        serena_log_level = self.serena_config.log_level
        if Logger.root.level != serena_log_level:
            log.info(f"Changing the root logger level to {serena_log_level}")
            Logger.root.setLevel(serena_log_level)

        def get_memory_log_handler() -> MemoryLogHandler:
            nonlocal memory_log_handler
            if memory_log_handler is None:
                memory_log_handler = MemoryLogHandler(level=serena_log_level)
                Logger.root.addHandler(memory_log_handler)
            return memory_log_handler

        # open GUI log window if enabled
        self._gui_log_viewer: Optional["GuiLogViewer"] = None
        if self.serena_config.gui_log_window_enabled:
            if platform.system() == "Darwin":
                log.warning("GUI log window is not supported on macOS")
            else:
                # even importing on macOS may fail if tkinter dependencies are unavailable (depends on Python interpreter installation
                # which uv used as a base, unfortunately)
                from serena.gui_log_viewer import GuiLogViewer

                self._gui_log_viewer = GuiLogViewer("dashboard", title="Serena Logs", memory_log_handler=get_memory_log_handler())
                self._gui_log_viewer.start()

        # set the agent context
        if context is None:
            context = SerenaAgentContext.load_default()
        self._context = context

        # instantiate all tool classes
        self._all_tools: dict[type[Tool], Tool] = {tool_class: tool_class(self) for tool_class in ToolRegistry().get_all_tool_classes()}
        tool_names = [tool.get_name_from_cls() for tool in self._all_tools.values()]

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_viewer is not None:
            self._gui_log_viewer.set_tool_names(tool_names)

        self._tool_usage_stats: ToolUsageStats | None = None
        if self.serena_config.record_tool_usage_stats:
            token_count_estimator = RegisteredTokenCountEstimator[self.serena_config.token_count_estimator]
            log.info(f"Tool usage statistics recording is enabled with token count estimator: {token_count_estimator.name}.")
            self._tool_usage_stats = ToolUsageStats(token_count_estimator)

        # start the dashboard (web frontend), registering its log handler
        if self.serena_config.web_dashboard:
            self._dashboard_thread, port = SerenaDashboardAPI(
                get_memory_log_handler(), tool_names, agent=self, tool_usage_stats=self._tool_usage_stats
            ).run_in_thread()
            dashboard_url = f"http://127.0.0.1:{port}/dashboard/index.html"
            log.info("Serena web dashboard started at %s", dashboard_url)
            if self.serena_config.web_dashboard_open_on_launch:
                # open the dashboard URL in the default web browser (using a separate process to control
                # output redirection)
                process = multiprocessing.Process(target=self._open_dashboard, args=(dashboard_url,))
                process.start()
                process.join(timeout=1)

        # log fundamental information
        log.info(f"Starting Serena server (version={serena_version()}, process id={os.getpid()}, parent process id={os.getppid()})")
        log.info("Configuration file: %s", self.serena_config.config_file_path)
        log.info("Available projects: {}".format(", ".join(self.serena_config.project_names)))
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name_from_cls() for tool in self._all_tools.values()])}")

        self._check_shell_settings()

        # determine the base toolset defining the set of exposed tools (which e.g. the MCP shall see),
        # limited by the Serena config, the context (which is fixed for the session) and JetBrains mode
        tool_inclusion_definitions: list[ToolInclusionDefinition] = [self.serena_config, self._context]
        if self._context.name == RegisteredContext.IDE_ASSISTANT.value:
            tool_inclusion_definitions.extend(self._ide_assistant_context_tool_inclusion_definitions(project))
        if self.serena_config.jetbrains:
            tool_inclusion_definitions.append(SerenaAgentMode.from_name_internal("jetbrains"))

        self._base_tool_set = ToolSet.default().apply(*tool_inclusion_definitions)
        self._exposed_tools = AvailableTools([t for t in self._all_tools.values() if self._base_tool_set.includes_name(t.get_name())])
        log.info(f"Number of exposed tools: {len(self._exposed_tools)}")

        # create executor for starting the language server and running tools in another thread
        # This executor is used to achieve linear task execution, so it is important to use a single-threaded executor.
        self._task_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="SerenaAgentExecutor")
        self._task_executor_lock = threading.Lock()
        self._task_executor_task_index = 1

        # Initialize the prompt factory
        self.prompt_factory = SerenaPromptFactory()
        self._project_activation_callback = project_activation_callback

        # set the active modes
        if modes is None:
            modes = SerenaAgentMode.load_default_modes()
        self._modes = modes

        self._active_tools: dict[type[Tool], Tool] = {}
        self._update_active_tools()

        # activate a project configuration (if provided or if there is only a single project available)
        if project is not None:
            try:
                self.activate_project_from_path_or_name(project)
            except Exception as e:
                log.error(f"Error activating project '{project}' at startup: {e}", exc_info=e)

    def get_context(self) -> SerenaAgentContext:
        return self._context

    def get_tool_description_override(self, tool_name: str) -> str | None:
        return self._context.tool_description_overrides.get(tool_name, None)

    def _check_shell_settings(self) -> None:
        # On Windows, Claude Code sets COMSPEC to Git-Bash (often even with a path containing spaces),
        # which causes all sorts of trouble, preventing language servers from being launched correctly.
        # So we make sure that COMSPEC is unset if it has been set to bash specifically.
        if platform.system() == "Windows":
            comspec = os.environ.get("COMSPEC", "")
            if "bash" in comspec:
                os.environ["COMSPEC"] = ""  # force use of default shell
                log.info("Adjusting COMSPEC environment variable to use the default shell instead of '%s'", comspec)

    def _ide_assistant_context_tool_inclusion_definitions(self, project_root_or_name: str | None) -> list[ToolInclusionDefinition]:
        """
        In the IDE assistant context, the agent is assumed to work on a single project, and we thus
        want to apply that project's tool exclusions/inclusions from the get-go, limiting the set
        of tools that will be exposed to the client.
        Furthermore, we disable tools that are only relevant for project activation.
        So if the project exists, we apply all the aforementioned exclusions.

        :param project_root_or_name: the project root path or project name
        :return:
        """
        tool_inclusion_definitions = []
        if project_root_or_name is not None:
            # Note: Auto-generation is disabled, because the result must be returned instantaneously
            #   (project generation could take too much time), so as not to delay MCP server startup
            #   and provide responses to the client immediately.
            project = self.load_project_from_path_or_name(project_root_or_name, autogenerate=False)
            if project is not None:
                tool_inclusion_definitions.append(
                    ToolInclusionDefinition(
                        excluded_tools=[ActivateProjectTool.get_name_from_cls(), GetCurrentConfigTool.get_name_from_cls()]
                    )
                )
                tool_inclusion_definitions.append(project.project_config)
        return tool_inclusion_definitions

    def record_tool_usage_if_enabled(self, input_kwargs: dict, tool_result: str | dict, tool: Tool) -> None:
        """
        Record the usage of a tool with the given input and output strings if tool usage statistics recording is enabled.
        """
        tool_name = tool.get_name()
        if self._tool_usage_stats is not None:
            input_str = str(input_kwargs)
            output_str = str(tool_result)
            log.debug(f"Recording tool usage for tool '{tool_name}'")
            self._tool_usage_stats.record_tool_usage(tool_name, input_str, output_str)
        else:
            log.debug(f"Tool usage statistics recording is disabled, not recording usage of '{tool_name}'.")

    @staticmethod
    def _open_dashboard(url: str) -> None:
        # Redirect stdout and stderr file descriptors to /dev/null,
        # making sure that nothing can be written to stdout/stderr, even by subprocesses
        null_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null_fd, sys.stdout.fileno())
        os.dup2(null_fd, sys.stderr.fileno())
        os.close(null_fd)

        # open the dashboard URL in the default web browser
        webbrowser.open(url)

    def get_project_root(self) -> str:
        """
        :return: the root directory of the active project (if any); raises a ValueError if there is no active project
        """
        project = self.get_active_project()
        if project is None:
            raise ValueError("Cannot get project root if no project is active.")
        return project.project_root

    def get_exposed_tool_instances(self) -> list["Tool"]:
        """
        :return: the tool instances which are exposed (e.g. to the MCP client).
            Note that the set of exposed tools is fixed for the session, as
            clients don't react to changes in the set of tools, so this is the superset
            of tools that can be offered during the session.
            If a client should attempt to use a tool that is dynamically disabled
            (e.g. because a project is activated that disables it), it will receive an error.
        """
        return list(self._exposed_tools.tools)

    def get_active_project(self) -> Project | None:
        """
        :return: the active project or None if no project is active
        """
        return self._active_project

    def get_active_project_or_raise(self) -> Project:
        """
        :return: the active project or raises an exception if no project is active
        """
        project = self.get_active_project()
        if project is None:
            raise ValueError("No active project. Please activate a project first.")
        return project

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

    def _format_prompt(self, prompt_template: str) -> str:
        template = JinjaTemplate(prompt_template)
        return template.render(available_tools=self._exposed_tools.tool_names, available_markers=self._exposed_tools.tool_marker_names)

    def create_system_prompt(self) -> str:
        available_markers = self._exposed_tools.tool_marker_names
        log.info("Generating system prompt with available_tools=(see exposed tools), available_markers=%s", available_markers)
        system_prompt = self.prompt_factory.create_system_prompt(
            context_system_prompt=self._format_prompt(self._context.prompt),
            mode_system_prompts=[self._format_prompt(mode.prompt) for mode in self._modes],
            available_tools=self._exposed_tools.tool_names,
            available_markers=available_markers,
        )

        # If a project is active at startup, append its activation message
        if self._active_project is not None:
            system_prompt += "\n\n" + self._active_project.get_activation_message()

        log.info("System prompt:\n%s", system_prompt)
        return system_prompt

    def _update_active_tools(self) -> None:
        """
        Update the active tools based on enabled modes and the active project.
        The base tool set already takes the Serena configuration and the context into account
        (as well as any internal modes that are not handled dynamically, such as JetBrains mode).
        """
        tool_set = self._base_tool_set.apply(*self._modes)
        if self._active_project is not None:
            tool_set = tool_set.apply(self._active_project.project_config)
            if self._active_project.project_config.read_only:
                tool_set = tool_set.without_editing_tools()

        self._active_tools = {
            tool_class: tool_instance
            for tool_class, tool_instance in self._all_tools.items()
            if tool_set.includes_name(tool_instance.get_name())
        }

        log.info(f"Active tools ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")

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

    def is_using_language_server(self) -> bool:
        """
        :return: whether this agent uses language server-based code analysis
        """
        return not self.serena_config.jetbrains

    def _activate_project(self, project: Project) -> None:
        log.info(f"Activating {project.project_name} at {project.project_root}")
        self._active_project = project
        self._update_active_tools()

        def init_language_server() -> None:
            # start the language server
            with LogTime("Language server initialization", logger=log):
                self.reset_language_server()
                assert self.language_server is not None

        # initialize the language server in the background (if in language server mode)
        if self.is_using_language_server():
            self.issue_task(init_language_server)

        if self._project_activation_callback is not None:
            self._project_activation_callback()

    def load_project_from_path_or_name(self, project_root_or_name: str, autogenerate: bool) -> Project | None:
        """
        Get a project instance from a path or a name.

        :param project_root_or_name: the path to the project root or the name of the project
        :param autogenerate: whether to autogenerate the project for the case where first argument is a directory
            which does not yet contain a Serena project configuration file
        :return: the project instance if it was found/could be created, None otherwise
        """
        project_instance: Project | None = self.serena_config.get_project(project_root_or_name)
        if project_instance is not None:
            log.info(f"Found registered project '{project_instance.project_name}' at path {project_instance.project_root}")
        elif autogenerate and os.path.isdir(project_root_or_name):
            project_instance = self.serena_config.add_project_from_path(project_root_or_name)
            log.info(f"Added new project {project_instance.project_name} for path {project_instance.project_root}")
        return project_instance

    def activate_project_from_path_or_name(self, project_root_or_name: str) -> Project:
        """
        Activate a project from a path or a name.
        If the project was already registered, it will just be activated.
        If the argument is a path at which no Serena project previously existed, the project will be created beforehand.
        Raises ProjectNotFoundError if the project could neither be found nor created.

        :return: a tuple of the project instance and a Boolean indicating whether the project was newly
            created
        """
        project_instance: Project | None = self.load_project_from_path_or_name(project_root_or_name, autogenerate=True)
        if project_instance is None:
            raise ProjectNotFoundError(
                f"Project '{project_root_or_name}' not found: Not a valid project name or directory. "
                f"Existing project names: {self.serena_config.project_names}"
            )
        self._activate_project(project_instance)
        return project_instance

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

    @property
    def language_server(self) -> SolidLanguageServer | None:
        """
        Backward compatibility property: returns first working LSP from manager.
        DEPRECATED: Use lsp_manager for polyglot support.

        FIX #3 (WARNING): Caches manager reference to prevent race condition.
        """
        # FIX #3: Cache manager reference to prevent race condition
        manager = self.lsp_manager
        if manager is not None:
            working_lsps = manager.get_all_working_language_servers()
            if working_lsps:
                return working_lsps[0]
        return self._language_server

    def is_language_server_running(self) -> bool:
        """Check if any language server is running (checks LSPManager if available)."""
        # FIX #3: Cache lsp_manager reference to prevent race condition
        manager = self.lsp_manager
        if manager is not None:
            working_lsps = manager.get_all_working_language_servers()
            return len(working_lsps) > 0
        return self._language_server is not None and self._language_server.is_running()

    def _calculate_ls_timeout(self) -> float | None:
        """
        Calculate language server timeout from tool timeout.

        FIX #4 (WARNING): Extracted shared timeout calculation logic to eliminate DRY violation.

        Returns:
            Timeout in seconds (tool_timeout - 5), or None if no timeout configured

        Raises:
            ValueError: If tool timeout is less than 10 seconds
        """
        tool_timeout = self.serena_config.tool_timeout
        if tool_timeout is None or tool_timeout < 0:
            return None

        if tool_timeout < 10:
            raise ValueError(f"Tool timeout must be at least 10 seconds, but is {tool_timeout} seconds")

        # LSP timeout should be smaller than tool timeout to allow for overhead
        return tool_timeout - 5

    def reset_lsp_manager(self) -> None:
        """
        Starts/resets the LSPManager for the current project (polyglot support).

        FIX #1 (CRITICAL): Uses synchronous shutdown wrapper for proper resource cleanup.
        FIX #2 (ERROR): Adds comprehensive error handling with validation and rollback.
        FIX #3 (WARNING): Caches manager reference to prevent race conditions.
        FIX #4 (WARNING): Uses extracted _calculate_ls_timeout() method.
        """
        from serena.lsp_manager import LSPManager

        # FIX #4: Use extracted timeout calculation method
        ls_timeout = self._calculate_ls_timeout()

        # FIX #1 & #3: Properly shutdown existing LSPManager with cached reference
        old_manager = self.lsp_manager
        if old_manager is not None:
            log.info("Stopping existing LSPManager...")
            try:
                # FIX #1: Use synchronous shutdown wrapper instead of just setting to None
                old_manager.shutdown_all_sync()
                log.info("Existing LSPManager stopped successfully")
            except Exception as e:
                log.error(f"Error shutting down existing LSPManager: {e}", exc_info=True)
                # Continue anyway - we'll create a new manager
            finally:
                self.lsp_manager = None

        # FIX #2: Add comprehensive error handling for LSPManager creation
        assert self._active_project is not None
        try:
            new_manager = self._active_project.create_lsp_manager(
                log_level=self.serena_config.log_level,
                ls_timeout=ls_timeout,
                trace_lsp_communication=self.serena_config.trace_lsp_communication,
                ls_specific_settings=self.serena_config.ls_specific_settings,
            )

            # FIX #2: Validate that LSPManager was created successfully
            if new_manager is None:
                raise RuntimeError("create_lsp_manager() returned None")

            self.lsp_manager = new_manager
            log.info(
                f"Created LSPManager for {len(self._active_project.languages)} languages: "
                f"{[lang.value for lang in self._active_project.languages]}"
            )

        except Exception as e:
            # FIX #2: Rollback on failure - restore old manager if possible
            log.error(f"Failed to create LSPManager: {e}", exc_info=True)
            if old_manager is not None:
                log.warning("Attempting to restore previous LSPManager...")
                self.lsp_manager = old_manager
            raise RuntimeError(f"Failed to create LSPManager for {self._active_project.project_name}: {e}") from e

    def reset_language_server(self) -> None:
        """
        Starts/resets the language server for the current project.
        DEPRECATED: Use reset_lsp_manager() for polyglot support.

        FIX #4 (WARNING): Uses extracted _calculate_ls_timeout() method.
        """
        # Delegate to new method for polyglot projects
        if self._active_project and len(self._active_project.languages) > 1:
            log.info("Polyglot project detected, using LSPManager instead of single LSP")
            self.reset_lsp_manager()
            return

        # FIX #4: Use extracted timeout calculation method
        ls_timeout = self._calculate_ls_timeout()

        # stop the language server if it is running
        if self._language_server is not None and self._language_server.is_running():
            log.info(f"Stopping the current language server at {self._language_server.repository_root_path} ...")
            self._language_server.stop()
            self._language_server = None

        # instantiate and start the language server
        assert self._active_project is not None
        self._language_server = self._active_project.create_language_server(
            log_level=self.serena_config.log_level,
            ls_timeout=ls_timeout,
            trace_lsp_communication=self.serena_config.trace_lsp_communication,
            ls_specific_settings=self.serena_config.ls_specific_settings,
        )
        log.info(f"Starting the language server for {self._active_project.project_name}")
        self._language_server.start()
        if not self._language_server.is_running():
            raise RuntimeError(
                f"Failed to start the language server for {self._active_project.project_name} at {self._active_project.project_root}"
            )

    def get_language_server_for_file(self, file_path: str) -> SolidLanguageServer | None:
        """
        Get the appropriate language server for a given file path.
        Routes to correct LSP based on file extension when using LSPManager.

        FIX #3 (WARNING): Caches manager reference to prevent race condition.
        """
        # FIX #3: Cache manager reference to prevent race condition
        manager = self.lsp_manager
        if manager is not None:
            return manager.get_language_server_for_file(file_path)
        return self._language_server

    def get_tool(self, tool_class: type[TTool]) -> TTool:
        return self._all_tools[tool_class]  # type: ignore

    def print_tool_overview(self) -> None:
        ToolRegistry().print_tool_overview(self._active_tools.values())

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
        if self._gui_log_viewer:
            log.info("Stopping the GUI log window ...")
            self._gui_log_viewer.stop()

    def get_tool_by_name(self, tool_name: str) -> Tool:
        tool_class = ToolRegistry().get_tool_class_by_name(tool_name)
        return self.get_tool(tool_class)
