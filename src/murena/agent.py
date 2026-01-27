"""
The Murena Model Context Protocol (MCP) Server
"""

import os
import platform
import subprocess
import sys
import threading
from collections.abc import Callable
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, TypeVar

from sensai.util import logging
from sensai.util.logging import LogTime

from interprompt.jinja_template import JinjaTemplate
from murena import murena_version
from murena.analytics import RegisteredTokenCountEstimator, ToolUsageStats
from murena.config.context_mode import MurenaAgentContext, MurenaAgentMode
from murena.config.murena_config import LanguageBackend, MurenaConfig, ToolInclusionDefinition
from murena.dashboard import MurenaDashboardAPI
from murena.hooks import HookEvent, get_global_registry
from murena.ls_manager import LanguageServerManager
from murena.project import Project
from murena.prompt_factory import MurenaPromptFactory
from murena.symbol_cache import SessionSymbolCache
from murena.task_executor import TaskExecutor
from murena.tools import ActivateProjectTool, GetCurrentConfigTool, OpenDashboardTool, ReplaceContentTool, Tool, ToolMarker, ToolRegistry
from murena.util.gui import system_has_usable_display
from murena.util.inspection import iter_subclasses
from murena.util.logging import MemoryLogHandler
from solidlsp.ls_config import Language

if TYPE_CHECKING:
    from murena.gui_log_viewer import GuiLogViewer
    from murena.util.resource_monitor import ResourceMonitor, ResourceSnapshot

log = logging.getLogger(__name__)
TTool = TypeVar("TTool", bound="Tool")
T = TypeVar("T")
SUCCESS_RESULT = "OK"


class ProjectNotFoundError(Exception):
    pass


class AvailableTools:
    """
    Represents the set of available/exposed tools of a MurenaAgent.
    """

    def __init__(self, tools: list[Tool]):
        """
        :param tools: the list of available tools
        """
        self.tools = tools
        self.tool_names = sorted([tool.get_name_from_cls() for tool in tools])
        """
        the list of available tool names, sorted alphabetically
        """
        self._tool_name_set = set(self.tool_names)
        self.tool_marker_names = set()
        for marker_class in iter_subclasses(ToolMarker):
            for tool in tools:
                if isinstance(tool, marker_class):
                    self.tool_marker_names.add(marker_class.__name__)

    def __len__(self) -> int:
        return len(self.tools)

    def contains_tool_name(self, tool_name: str) -> bool:
        return tool_name in self._tool_name_set


class ToolSet:
    """
    Represents a set of tools by their names.
    """

    LEGACY_TOOL_NAME_MAPPING = {"replace_regex": ReplaceContentTool.get_name_from_cls()}
    """
    maps legacy tool names to their new names for backward compatibility
    """

    def __init__(self, tool_names: set[str]) -> None:
        self._tool_names = tool_names

    @classmethod
    def default(cls) -> "ToolSet":
        """
        :return: the default tool set, which contains all tools that are enabled by default
        """
        from murena.tools import ToolRegistry

        return cls(set(ToolRegistry().get_tool_names_default_enabled()))

    def apply(self, *tool_inclusion_definitions: "ToolInclusionDefinition") -> "ToolSet":
        """
        Applies one or more tool inclusion definitions to this tool set,
        resulting in a new tool set.

        :param tool_inclusion_definitions: the definitions to apply
        :return: a new tool set with the definitions applied
        """
        from murena.tools import ToolRegistry

        def get_updated_tool_name(tool_name: str) -> str:
            """Retrieves the updated tool name if the provided tool name is deprecated, logging a warning."""
            if tool_name in self.LEGACY_TOOL_NAME_MAPPING:
                new_tool_name = self.LEGACY_TOOL_NAME_MAPPING[tool_name]
                log.warning("Tool name '%s' is deprecated, please use '%s' instead", tool_name, new_tool_name)
                return new_tool_name
            return tool_name

        registry = ToolRegistry()
        tool_names = set(self._tool_names)
        for definition in tool_inclusion_definitions:
            if definition.is_fixed_tool_set():
                tool_names = set()
                for fixed_tool in definition.fixed_tools:
                    fixed_tool = get_updated_tool_name(fixed_tool)
                    if not registry.is_valid_tool_name(fixed_tool):
                        raise ValueError(f"Invalid tool name '{fixed_tool}' provided for fixed tool set")
                    tool_names.add(fixed_tool)
                log.info(f"{definition} defined a fixed tool set with {len(tool_names)} tools: {', '.join(tool_names)}")
            else:
                included_tools = []
                excluded_tools = []
                for included_tool in definition.included_optional_tools:
                    included_tool = get_updated_tool_name(included_tool)
                    if not registry.is_valid_tool_name(included_tool):
                        raise ValueError(f"Invalid tool name '{included_tool}' provided for inclusion")
                    if included_tool not in tool_names:
                        tool_names.add(included_tool)
                        included_tools.append(included_tool)
                for excluded_tool in definition.excluded_tools:
                    excluded_tool = get_updated_tool_name(excluded_tool)
                    if not registry.is_valid_tool_name(excluded_tool):
                        raise ValueError(f"Invalid tool name '{excluded_tool}' provided for exclusion")
                    if excluded_tool in tool_names:
                        tool_names.remove(excluded_tool)
                        excluded_tools.append(excluded_tool)
                if included_tools:
                    log.info(f"{definition} included {len(included_tools)} tools: {', '.join(included_tools)}")
                if excluded_tools:
                    log.info(f"{definition} excluded {len(excluded_tools)} tools: {', '.join(excluded_tools)}")
        return ToolSet(tool_names)

    def without_editing_tools(self) -> "ToolSet":
        """
        :return: a new tool set that excludes all tools that can edit
        """
        from murena.tools import ToolRegistry

        registry = ToolRegistry()
        tool_names = set(self._tool_names)
        for tool_name in self._tool_names:
            if registry.get_tool_class_by_name(tool_name).can_edit():
                tool_names.remove(tool_name)
        return ToolSet(tool_names)

    def get_tool_names(self) -> set[str]:
        """
        Returns the names of the tools that are currently included in the tool set.
        """
        return self._tool_names

    def includes_name(self, tool_name: str) -> bool:
        return tool_name in self._tool_names


class MurenaAgent:
    def __init__(
        self,
        project: str | None = None,
        project_activation_callback: Callable[[], None] | None = None,
        murena_config: MurenaConfig | None = None,
        context: MurenaAgentContext | None = None,
        modes: list[MurenaAgentMode] | None = None,
        memory_log_handler: MemoryLogHandler | None = None,
    ):
        """
        :param project: the project to load immediately or None to not load any project; may be a path to the project or a name of
            an already registered project;
        :param project_activation_callback: a callback function to be called when a project is activated.
        :param murena_config: the Murena configuration or None to read the configuration from the default location.
        :param context: the context in which the agent is operating, None for default context.
            The context may adjust prompts, tool availability, and tool descriptions.
        :param modes: list of modes in which the agent is operating (they will be combined), None for default modes.
            The modes may adjust prompts, tool availability, and tool descriptions.
        :param memory_log_handler: a MemoryLogHandler instance from which to read log messages; if None, a new one will be created
            if necessary.
        """
        # obtain murena configuration using the decoupled factory function
        self.murena_config = murena_config or MurenaConfig.from_config_file()

        # propagate configuration to other components
        self.murena_config.propagate_settings()

        # project-specific instances, which will be initialized upon project activation
        self._active_project: Project | None = None

        # dashboard URL (set when dashboard is started)
        self._dashboard_url: str | None = None

        # session-level symbol cache for token optimization (initialized when project is activated)
        self._symbol_cache: "SessionSymbolCache | None" = None

        # adjust log level
        serena_log_level = self.murena_config.log_level
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
        if self.murena_config.gui_log_window:
            log.info("Opening GUI window")
            if platform.system() == "Darwin":
                log.warning("GUI log window is not supported on macOS")
            else:
                # even importing on macOS may fail if tkinter dependencies are unavailable (depends on Python interpreter installation
                # which uv used as a base, unfortunately)
                from murena.gui_log_viewer import GuiLogViewer

                self._gui_log_viewer = GuiLogViewer("dashboard", title="Murena Logs", memory_log_handler=get_memory_log_handler())
                self._gui_log_viewer.start()
        else:
            log.debug("GUI window is disabled")

        # set the agent context
        if context is None:
            context = MurenaAgentContext.load_default()
        self._context = context

        # instantiate all tool classes
        self._all_tools: dict[type[Tool], Tool] = {tool_class: tool_class(self) for tool_class in ToolRegistry().get_all_tool_classes()}
        tool_names = [tool.get_name_from_cls() for tool in self._all_tools.values()]

        # Register built-in hooks (e.g., auto-indexing)
        from murena.hooks import register_builtin_hooks

        register_builtin_hooks()

        # Trigger TOOL_REGISTERED hooks for each tool
        hook_registry = get_global_registry()
        for tool in self._all_tools.values():
            hook_registry.trigger(
                HookEvent.TOOL_REGISTERED,
                agent=self,
                data={"tool_name": tool.get_name_from_cls(), "tool_instance": tool},
            )

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_viewer is not None:
            self._gui_log_viewer.set_tool_names(tool_names)

        token_count_estimator = RegisteredTokenCountEstimator[self.murena_config.token_count_estimator]
        log.info(f"Will record tool usage statistics with token count estimator: {token_count_estimator.name}.")
        self._tool_usage_stats = ToolUsageStats(token_count_estimator)

        # log fundamental information
        log.info(
            f"Starting Murena server (version={murena_version()}, process id={os.getpid()}, parent process id={os.getppid()}; "
            f"language backend={self.murena_config.language_backend.name})"
        )
        log.info("Configuration file: %s", self.murena_config.config_file_path)
        log.info("Available projects: {}".format(", ".join(self.murena_config.project_names)))
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name_from_cls() for tool in self._all_tools.values()])}")

        self._check_shell_settings()

        # determine the base toolset defining the set of exposed tools (which e.g. the MCP shall see),
        # determined by the
        #   * dashboard availability/opening on launch
        #   * Serena config
        #   * the context (which is fixed for the session)
        #   * single-project mode reductions (if applicable)
        #   * JetBrains mode
        tool_inclusion_definitions: list[ToolInclusionDefinition] = []
        if (
            self.murena_config.web_dashboard
            and not self.murena_config.web_dashboard_open_on_launch
            and not self.murena_config.gui_log_window
        ):
            tool_inclusion_definitions.append(ToolInclusionDefinition(included_optional_tools=[OpenDashboardTool.get_name_from_cls()]))
        tool_inclusion_definitions.append(self.murena_config)
        tool_inclusion_definitions.append(self._context)
        if self._context.single_project:
            tool_inclusion_definitions.extend(self._single_project_context_tool_inclusion_definitions(project))
        if self.murena_config.language_backend == LanguageBackend.JETBRAINS:
            tool_inclusion_definitions.append(MurenaAgentMode.from_name_internal("jetbrains"))
        self._base_tool_set = ToolSet.default().apply(*tool_inclusion_definitions)
        self._exposed_tools = AvailableTools([t for t in self._all_tools.values() if self._base_tool_set.includes_name(t.get_name())])
        log.info(f"Number of exposed tools: {len(self._exposed_tools)}")

        # create executor for starting the language server and running tools in another thread
        # This executor is used to achieve linear task execution
        self._task_executor = TaskExecutor("MurenaAgentTaskExecutor")

        # create async executor for parallel tool execution (reused across calls)
        from murena.async_task_executor import AsyncTaskExecutor

        rm_config = self.murena_config.resource_management
        self._async_executor = AsyncTaskExecutor(max_workers=rm_config.async_execution_max_workers)

        # Initialize resource monitoring with graceful degradation
        self._degradation_level = 0
        self._resource_monitor: "ResourceMonitor | None" = None
        if rm_config.monitoring_enabled:
            from murena.util.resource_monitor import ResourceMonitor as _ResourceMonitor
            from murena.util.resource_monitor import ResourceThresholds

            self._resource_monitor = _ResourceMonitor(
                sample_interval=rm_config.monitoring_sample_interval,
                thresholds=ResourceThresholds(
                    memory_warning_mb=rm_config.monitoring_memory_warning_mb,
                    memory_critical_mb=rm_config.monitoring_memory_critical_mb,
                ),
                on_warning=self._on_resource_warning,
                on_critical=self._on_resource_critical,
            )
            self._resource_monitor.start()
            log.info(
                f"Resource monitoring started (warning={rm_config.monitoring_memory_warning_mb}MB, "
                f"critical={rm_config.monitoring_memory_critical_mb}MB)"
            )

        # Initialize the prompt factory
        self.prompt_factory = MurenaPromptFactory()
        self._project_activation_callback = project_activation_callback

        # set the active modes
        if modes is None:
            modes = MurenaAgentMode.load_default_modes()
        self._modes = modes

        # determine the subset of active tools (depending on active modes and the active project)
        self._active_tools: AvailableTools = self._exposed_tools
        self._update_active_tools()

        # activate a project configuration (if provided or if there is only a single project available)
        self._lazy_initializer: "LazyProjectInitializer | None" = None
        if project is not None:
            try:
                self.activate_project_from_path_or_name(project)
            except Exception as e:
                log.error(f"Error activating project '{project}' at startup: {e}", exc_info=e)
                # Setup lazy initialization if project activation failed
                # This handles --project-from-cwd with missing .murena/project.yml
                if isinstance(project, str | Path) and Path(project).is_dir():
                    from murena.lazy_init import LazyProjectInitializer

                    self._lazy_initializer = LazyProjectInitializer(self)
                    self._lazy_initializer.set_project_root(str(Path(project).resolve()))
                    log.info(f"Lazy initialization enabled for: {project}")

        # register tenant in multi-project registry
        self._health_monitor_thread: threading.Thread | None = None
        self._tenant_id: str | None = None
        try:
            from murena.multi_project import TenantMetadata, TenantRegistry, TenantStatus
            from murena.multi_project.health_monitor import BackgroundHealthMonitor

            # Determine tenant ID from project or use default
            self._tenant_id = Path(self._active_project.project_root).name if self._active_project else "default"

            registry = TenantRegistry()
            tenant_metadata = TenantMetadata(
                tenant_id=self._tenant_id,
                server_name=f"murena-{self._tenant_id}",
                project_root=self._active_project.project_root if self._active_project else os.getcwd(),
                pid=os.getpid(),
                status=TenantStatus.STARTING,
            )
            registry.register_tenant(tenant_metadata)

            # Start background health monitoring if enabled
            health_config = self.murena_config.resource_management
            if health_config.monitoring_enabled:
                self._health_monitor = BackgroundHealthMonitor(
                    tenant_id=self._tenant_id,
                    pid=os.getpid(),
                    interval_seconds=health_config.monitoring_sample_interval,
                    enabled=True,
                )
                self._health_monitor.start()

            # Update status to RUNNING
            registry.update_status(self._tenant_id, TenantStatus.RUNNING)
            log.info(f"Registered tenant '{self._tenant_id}' in multi-project registry")

        except ImportError:
            log.debug("Multi-project registry not available")
        except Exception as e:
            log.warning(f"Failed to register tenant: {e}")

        # start the dashboard (web frontend), registering its log handler
        # should be the last thing to happen in the initialization since the dashboard
        # may access various parts of the agent
        if self.murena_config.web_dashboard:
            self._dashboard_thread, port = MurenaDashboardAPI(
                get_memory_log_handler(), tool_names, agent=self, tool_usage_stats=self._tool_usage_stats
            ).run_in_thread(
                host=self.murena_config.web_dashboard_listen_address,
                start_port=self.murena_config.web_dashboard_port,
            )
            dashboard_host = self.murena_config.web_dashboard_listen_address
            if dashboard_host == "0.0.0.0":
                dashboard_host = "localhost"
            dashboard_url = f"http://{dashboard_host}:{port}/dashboard/index.html"
            self._dashboard_url = dashboard_url
            log.info("Murena web dashboard started at %s", dashboard_url)
            if self.murena_config.web_dashboard_open_on_launch:
                self.open_dashboard()
            # inform the GUI window (if any)
            if self._gui_log_viewer is not None:
                self._gui_log_viewer.set_dashboard_url(dashboard_url)

    def get_current_tasks(self) -> list[TaskExecutor.TaskInfo]:
        """
        Gets the list of tasks currently running or queued for execution.
        The function returns a list of thread-safe TaskInfo objects (specifically created for the caller).

        :return: the list of tasks in the execution order (running task first)
        """
        return self._task_executor.get_current_tasks()

    def get_last_executed_task(self) -> TaskExecutor.TaskInfo | None:
        """
        Gets the last executed task.

        :return: the last executed task info or None if no task has been executed yet
        """
        return self._task_executor.get_last_executed_task()

    def get_language_server_manager(self) -> LanguageServerManager | None:
        if self._active_project is not None:
            return self._active_project.language_server_manager
        return None

    def get_language_server_manager_or_raise(self) -> LanguageServerManager:
        language_server_manager = self.get_language_server_manager()
        if language_server_manager is None:
            raise Exception(
                "The language server manager is not initialized, indicating a problem during project activation. "
                "Inform the user, telling them to inspect Murena's logs in order to determine the issue. "
                "IMPORTANT: Wait for further instructions before you continue!"
            )
        return language_server_manager

    def get_context(self) -> MurenaAgentContext:
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

    def _single_project_context_tool_inclusion_definitions(self, project_root_or_name: str | None) -> list[ToolInclusionDefinition]:
        """
        When in a single-project context, the agent is assumed to work on a single project, and we thus
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
                log.info(
                    "Applying tool inclusion/exclusion definitions for single-project context based on project '%s'", project.project_name
                )
                tool_inclusion_definitions.append(
                    ToolInclusionDefinition(
                        excluded_tools=[ActivateProjectTool.get_name_from_cls(), GetCurrentConfigTool.get_name_from_cls()]
                    )
                )
                tool_inclusion_definitions.append(project.project_config)
        return tool_inclusion_definitions

    def record_tool_usage(self, input_kwargs: dict, tool_result: str | dict, tool: Tool) -> None:
        """
        Record the usage of a tool with the given input and output strings if tool usage statistics recording is enabled.
        """
        tool_name = tool.get_name()
        input_str = str(input_kwargs)
        output_str = str(tool_result)
        log.debug(f"Recording tool usage for tool '{tool_name}'")
        self._tool_usage_stats.record_tool_usage(tool_name, input_str, output_str)

    def get_dashboard_url(self) -> str | None:
        """
        :return: the URL of the web dashboard, or None if the dashboard is not running
        """
        return self._dashboard_url

    def open_dashboard(self) -> bool:
        """
        Opens the Murena web dashboard in the default web browser.

        :return: a message indicating success or failure
        """
        if self._dashboard_url is None:
            raise Exception("Dashboard is not running.")

        if not system_has_usable_display():
            log.warning("Not opening the Murena web dashboard because no usable display was detected.")
            return False

        # Use a subprocess to avoid any output from webbrowser.open being written to stdout
        subprocess.Popen(
            [sys.executable, "-c", f"import webbrowser; webbrowser.open({self._dashboard_url!r})"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process
        )
        return True

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

    def get_symbol_cache(self) -> "SessionSymbolCache | None":
        """
        :return: the session symbol cache or None if no project is active
        """
        return self._symbol_cache

    def get_embedding_model(self) -> Any:
        """
        Get the embedding model for semantic search (lazy-loaded).

        :return: SentenceTransformer model instance
        :raises ImportError: If semantic search dependencies are not installed
        """
        if not hasattr(self, "_embedding_model"):
            self._embedding_model = None

        if self._embedding_model is None:
            try:
                from murena.semantic import SEMANTIC_AVAILABLE

                if not SEMANTIC_AVAILABLE:
                    raise ImportError("Semantic search dependencies not installed. Install with: uv pip install 'murena-agent[semantic]'")

                from sentence_transformers import SentenceTransformer

                log.info("Loading embedding model for semantic search")
                self._embedding_model = SentenceTransformer("jinaai/jina-embeddings-v2-base-code")
                log.info("Embedding model loaded successfully")

            except Exception as e:
                log.error(f"Failed to load embedding model: {e}")
                raise

        return self._embedding_model

    def get_chroma_client(self) -> Any:
        """
        Get the ChromaDB client for semantic search (lazy-loaded).

        :return: ChromaDB client instance
        :raises ImportError: If semantic search dependencies are not installed
        """
        if not hasattr(self, "_chroma_client"):
            self._chroma_client = None

        if self._chroma_client is None:
            try:
                from murena.semantic import SEMANTIC_AVAILABLE

                if not SEMANTIC_AVAILABLE:
                    raise ImportError("Semantic search dependencies not installed. Install with: uv pip install 'murena-agent[semantic]'")

                from pathlib import Path

                import chromadb
                from chromadb.config import Settings

                project = self.get_active_project_or_raise()
                persist_dir = Path(project.project_root) / ".murena" / "semantic_index"
                persist_dir.mkdir(parents=True, exist_ok=True)

                log.info(f"Initializing ChromaDB client at {persist_dir}")
                self._chroma_client = chromadb.PersistentClient(
                    path=str(persist_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
                log.info("ChromaDB client initialized successfully")

            except Exception as e:
                log.error(f"Failed to initialize ChromaDB client: {e}")
                raise

        return self._chroma_client

    def set_modes(self, modes: list[MurenaAgentMode]) -> None:
        """
        Set the current mode configurations.

        :param modes: List of mode names or paths to use
        """
        old_modes = self._modes
        self._modes = modes
        self._update_active_tools()

        log.info(f"Set modes to {[mode.name for mode in modes]}")

        # Trigger MODE_CHANGED hook
        hook_registry = get_global_registry()
        hook_registry.trigger(
            HookEvent.MODE_CHANGED,
            agent=self,
            data={
                "old_modes": [m.name for m in old_modes],
                "new_modes": [m.name for m in modes],
                "modes": modes,
            },
        )

    def get_active_modes(self) -> list[MurenaAgentMode]:
        """
        :return: the list of active modes
        """
        return list(self._modes)

    def _format_prompt(self, prompt_template: str) -> str:
        template = JinjaTemplate(prompt_template)
        return template.render(available_tools=self._exposed_tools.tool_names, available_markers=self._exposed_tools.tool_marker_names)

    def create_system_prompt(self) -> str:
        available_tools = self._active_tools
        available_markers = available_tools.tool_marker_names
        log.info("Generating system prompt with available_tools=(see active tools), available_markers=%s", available_markers)
        system_prompt = self.prompt_factory.create_system_prompt(
            context_system_prompt=self._format_prompt(self._context.prompt),
            mode_system_prompts=[self._format_prompt(mode.prompt) for mode in self._modes],
            available_tools=available_tools.tool_names,
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
        The base tool set already takes the Murena configuration and the context into account
        (as well as any internal modes that are not handled dynamically, such as JetBrains mode).
        """
        # apply modes
        tool_set = self._base_tool_set.apply(*self._modes)

        # apply active project configuration (if any)
        if self._active_project is not None:
            tool_set = tool_set.apply(self._active_project.project_config)
            if self._active_project.project_config.read_only:
                tool_set = tool_set.without_editing_tools()

        tools = [t for t in self._all_tools.values() if tool_set.includes_name(t.get_name())]
        self._active_tools = AvailableTools(tools)

        log.info(f"Active tools ({len(self._active_tools)}): {', '.join(self._active_tools.tool_names)}")

    def issue_task(
        self, task: Callable[[], T], name: str | None = None, logged: bool = True, timeout: float | None = None
    ) -> TaskExecutor.Task[T]:
        """
        Issue a task to the executor for asynchronous execution.
        It is ensured that tasks are executed in the order they are issued, one after another.

        :param task: the task to execute
        :param name: the name of the task for logging purposes; if None, use the task function's name
        :param logged: whether to log management of the task; if False, only errors will be logged
        :param timeout: the maximum time to wait for task completion in seconds, or None to wait indefinitely
        :return: the task object, through which the task's future result can be accessed
        """
        return self._task_executor.issue_task(task, name=name, logged=logged, timeout=timeout)

    def execute_task(self, task: Callable[[], T], name: str | None = None, logged: bool = True, timeout: float | None = None) -> T:
        """
        Executes the given task synchronously via the agent's task executor.
        This is useful for tasks that need to be executed immediately and whose results are needed right away.

        :param task: the task to execute
        :param name: the name of the task for logging purposes; if None, use the task function's name
        :param logged: whether to log management of the task; if False, only errors will be logged
        :param timeout: the maximum time to wait for task completion in seconds, or None to wait indefinitely
        :return: the result of the task execution
        """
        result = self._task_executor.execute_task(task, name=name, logged=logged, timeout=timeout)

        # Record activity in multi-project registry
        if hasattr(self, "_tenant_id") and self._tenant_id:
            try:
                from murena.multi_project import TenantRegistry

                registry = TenantRegistry()
                registry.mark_activity(self._tenant_id)
            except Exception:
                pass  # Silently ignore registry errors

        return result

    def execute_tools_parallel(
        self,
        tool_names: list[str],
        tool_params: list[dict[str, Any]],
        enabled: bool = True,
    ) -> list[Any]:
        """
        Execute multiple tools in parallel with automatic dependency analysis.

        This method analyzes dependencies between tools (e.g., read-after-write)
        and executes them in waves to maximize parallelism while respecting
        dependencies.

        Args:
            tool_names: List of tool names to execute
            tool_params: List of parameter dicts for each tool
            enabled: Whether parallel execution is enabled (False = sequential)

        Returns:
            List of results in the same order as inputs

        Example:
            >>> agent.execute_tools_parallel(
            ...     ["read_file", "read_file", "edit_file"],
            ...     [{"file_path": "a.py"}, {"file_path": "b.py"}, {"file_path": "c.py"}],
            ... )

        """
        import asyncio

        from murena.tool_dependency_analyzer import ToolCall, ToolDependencyAnalyzer

        if not enabled or len(tool_names) <= 1:
            # Fall back to sequential execution
            results = []
            for tool_name, params in zip(tool_names, tool_params, strict=False):
                tool = self.get_tool_by_name(tool_name)
                if tool is None:
                    raise ValueError(f"Tool not found: {tool_name}")
                result = tool.apply_ex(**params)
                results.append(result)
            return results

        # Build tool calls
        tool_calls = [
            ToolCall(tool_name=name, params=params, index=i) for i, (name, params) in enumerate(zip(tool_names, tool_params, strict=False))
        ]

        # Analyze dependencies
        analyzer = ToolDependencyAnalyzer()
        dep_graph = analyzer.analyze(tool_calls)

        # Execute function for each tool
        def execute_tool(tc: ToolCall) -> Any:
            tool = self.get_tool_by_name(tc.tool_name)
            if tool is None:
                raise ValueError(f"Tool not found: {tc.tool_name}")
            return tool.apply_ex(**tc.params)

        # Check if we're already in an async context (e.g., FastMCP server)
        # If so, fall back to sequential execution to avoid event loop conflicts
        try:
            # This will raise RuntimeError if no event loop is running
            asyncio.get_running_loop()
            # We're in an async context - fall back to sequential execution
            log.debug("execute_tools_parallel: Detected running event loop, falling back to sequential execution")
            results = []
            for tc in tool_calls:
                result = execute_tool(tc)
                results.append(result)
            return results
        except RuntimeError:
            # No running event loop - safe to create new one for parallel execution
            pass

        # Run async execution with reusable executor
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(
                self._async_executor.execute_tools(
                    tool_calls=tool_calls,
                    dependency_graph=dep_graph,
                    execute_func=execute_tool,
                    timeout_per_tool=self.murena_config.tool_timeout,
                )
            )
            return results
        finally:
            loop.close()
            # Clear thread-local event loop reference to prevent leak
            asyncio.set_event_loop(None)

    def is_using_language_server(self) -> bool:
        """
        :return: whether this agent uses language server-based code analysis
        """
        return self.murena_config.language_backend == LanguageBackend.LSP

    def _activate_project(self, project: Project) -> None:
        log.info(f"Activating {project.project_name} at {project.project_root}")
        self._active_project = project
        self._update_active_tools()

        # Initialize session symbol cache for token optimization
        rm_config = self.murena_config.resource_management
        self._symbol_cache = SessionSymbolCache(
            project.project_root,
            ttl_seconds=rm_config.symbol_cache_ttl_seconds,
            max_entries=rm_config.symbol_cache_max_entries,
            max_memory_mb=rm_config.symbol_cache_max_memory_mb,
        )
        log.info(
            f"Initialized symbol cache (max_entries={rm_config.symbol_cache_max_entries}, "
            f"max_memory_mb={rm_config.symbol_cache_max_memory_mb})"
        )

        def init_language_server_manager() -> None:
            # start the language server
            with LogTime("Language server initialization", logger=log):
                self.reset_language_server_manager()

        # initialize the language server in the background (if in language server mode)
        if self.is_using_language_server():
            self.issue_task(init_language_server_manager)

        if self._project_activation_callback is not None:
            self._project_activation_callback()

        # Trigger PROJECT_ACTIVATED hook
        hook_registry = get_global_registry()
        hook_registry.trigger(
            HookEvent.PROJECT_ACTIVATED,
            agent=self,
            data={"project": project, "project_name": project.project_name, "project_root": project.project_root},
        )

    def load_project_from_path_or_name(self, project_root_or_name: str, autogenerate: bool) -> Project | None:
        """
        Get a project instance from a path or a name.

        :param project_root_or_name: the path to the project root or the name of the project
        :param autogenerate: whether to autogenerate the project for the case where first argument is a directory
            which does not yet contain a Serena project configuration file
        :return: the project instance if it was found/could be created, None otherwise
        """
        project_instance: Project | None = self.murena_config.get_project(project_root_or_name)
        if project_instance is not None:
            log.info(f"Found registered project '{project_instance.project_name}' at path {project_instance.project_root}")
        elif autogenerate and os.path.isdir(project_root_or_name):
            project_instance = self.murena_config.add_project_from_path(project_root_or_name)
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
                f"Existing project names: {self.murena_config.project_names}"
            )
        self._activate_project(project_instance)
        return project_instance

    def get_active_tool_names(self) -> list[str]:
        """
        :return: the list of names of the active tools for the current project, sorted alphabetically
        """
        return self._active_tools.tool_names

    def tool_is_active(self, tool_name: str) -> bool:
        """
        :param tool_class: the name of the tool to check
        :return: True if the tool is active, False otherwise
        """
        return self._active_tools.contains_tool_name(tool_name)

    def get_current_config_overview(self) -> str:
        """
        :return: a string overview of the current configuration, including the active and available configuration options
        """
        result_str = "Current configuration:\n"
        result_str += f"Murena version: {murena_version()}\n"
        result_str += f"Loglevel: {self.murena_config.log_level}, trace_lsp_communication={self.murena_config.trace_lsp_communication}\n"
        if self._active_project is not None:
            result_str += f"Active project: {self._active_project.project_name}\n"
        else:
            result_str += "No active project\n"
        result_str += "Available projects:\n" + "\n".join(list(self.murena_config.project_names)) + "\n"
        result_str += f"Active context: {self._context.name}\n"

        # Active modes
        active_mode_names = [mode.name for mode in self.get_active_modes()]
        result_str += "Active modes: {}\n".format(", ".join(active_mode_names)) + "\n"

        # Available but not active modes
        all_available_modes = MurenaAgentMode.list_registered_mode_names()
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

    def reset_language_server_manager(self) -> None:
        """
        Starts/resets the language server manager for the current project
        """
        tool_timeout = self.murena_config.tool_timeout
        if tool_timeout is None or tool_timeout < 0:
            ls_timeout = None
        else:
            if tool_timeout < 10:
                raise ValueError(f"Tool timeout must be at least 10 seconds, but is {tool_timeout} seconds")
            ls_timeout = tool_timeout - 5  # the LS timeout is for a single call, it should be smaller than the tool timeout

        # instantiate and start the necessary language servers
        rm_config = self.murena_config.resource_management
        self.get_active_project_or_raise().create_language_server_manager(
            log_level=self.murena_config.log_level,
            ls_timeout=ls_timeout,
            trace_lsp_communication=self.murena_config.trace_lsp_communication,
            ls_specific_settings=self.murena_config.ls_specific_settings,
            async_cache_enabled=self.murena_config.cache.async_persistence_enabled,
            async_cache_debounce_interval=self.murena_config.cache.async_persistence_debounce_interval,
            lsp_rate_limiting_enabled=rm_config.lsp_rate_limiting_enabled,
            lsp_rate_limiting_rate=rm_config.lsp_rate_limiting_rate_per_second,
            lsp_rate_limiting_burst=rm_config.lsp_rate_limiting_burst,
            performance_config=self.murena_config.performance,
        )

    def add_language(self, language: Language) -> None:
        """
        Adds a new language to the active project, spawning the respective language server and updating the project configuration.
        The addition is scheduled via the agent's task executor and executed synchronously, i.e. the method returns
        when the addition is complete.

        :param language: the language to add
        """
        self.execute_task(lambda: self.get_active_project_or_raise().add_language(language), name=f"AddLanguage:{language.value}")

    def remove_language(self, language: Language) -> None:
        """
        Removes a language from the active project, shutting down the respective language server and updating the project configuration.
        The removal is scheduled via the agent's task executor and executed asynchronously.

        :param language: the language to remove
        """
        self.issue_task(lambda: self.get_active_project_or_raise().remove_language(language), name=f"RemoveLanguage:{language.value}")

    def get_tool(self, tool_class: type[TTool]) -> TTool:
        return self._all_tools[tool_class]  # type: ignore

    def print_tool_overview(self) -> None:
        ToolRegistry().print_tool_overview(self._active_tools.tools)

    def _on_resource_warning(self, snapshot: "ResourceSnapshot") -> None:
        """Callback when resource warning threshold is exceeded."""
        if self._degradation_level < 1:
            self._degradation_level = 1
            log.warning(
                f"Resource warning: memory={snapshot.memory_rss_mb:.1f}MB, cpu={snapshot.cpu_percent:.1f}% - "
                f"Entering degradation level 1 (reducing cache by 50%)"
            )
            # Level 1: Reduce cache by 50%
            if self._symbol_cache:
                old_max = self._symbol_cache._max_entries
                self._symbol_cache._max_entries = old_max // 2
                log.info(f"Reduced symbol cache max_entries: {old_max} -> {self._symbol_cache._max_entries}")

    def _on_resource_critical(self, snapshot: "ResourceSnapshot") -> None:
        """Callback when resource critical threshold is exceeded."""
        if snapshot.memory_rss_mb > self.murena_config.resource_management.monitoring_memory_critical_mb * 0.9:
            if self._degradation_level < 3:
                self._degradation_level = 3
                log.error(
                    f"Resource CRITICAL: memory={snapshot.memory_rss_mb:.1f}MB, cpu={snapshot.cpu_percent:.1f}% - "
                    f"Entering degradation level 3 (aggressive cleanup)"
                )
                # Level 3: Aggressive cleanup
                if self._symbol_cache:
                    self._symbol_cache.clear()
                    self._symbol_cache._max_entries = 100  # Minimal cache
                    log.warning("Cleared symbol cache and set to minimal capacity (100 entries)")

        elif self._degradation_level < 2:
            self._degradation_level = 2
            log.warning(
                f"Resource critical: memory={snapshot.memory_rss_mb:.1f}MB, cpu={snapshot.cpu_percent:.1f}% - "
                f"Entering degradation level 2 (clearing cache)"
            )
            # Level 2: Clear cache
            if self._symbol_cache:
                self._symbol_cache.clear()
                log.info("Cleared symbol cache")

    def __del__(self) -> None:
        self.shutdown()

    def shutdown(self, timeout: float = 2.0) -> None:
        """
        Shuts down the agent, freeing resources and stopping background tasks.
        """
        if not hasattr(self, "_is_initialized"):
            return
        log.info("MurenaAgent is shutting down ...")

        # Shutdown task executor
        if hasattr(self, "_task_executor"):
            log.info("Shutting down task executor...")
            self._task_executor.shutdown(timeout=timeout)

        # Shutdown async executor
        if hasattr(self, "_async_executor"):
            log.info("Shutting down async executor...")
            self._async_executor.shutdown()

        # Shutdown resource monitoring
        if hasattr(self, "_resource_monitor") and self._resource_monitor is not None:
            log.info("Shutting down resource monitor...")
            self._resource_monitor.stop(timeout=timeout)

        # Shutdown active project
        if self._active_project is not None:
            self._active_project.shutdown(timeout=timeout)
            self._active_project = None

        # Stop GUI log viewer
        if self._gui_log_viewer:
            log.info("Stopping the GUI log window ...")
            self._gui_log_viewer.stop()
            self._gui_log_viewer = None

        # Join dashboard thread
        if hasattr(self, "_dashboard_thread") and self._dashboard_thread is not None:
            log.info("Waiting for dashboard thread...")
            self._dashboard_thread.join(timeout=1.0)
            if self._dashboard_thread.is_alive():
                log.warning("Dashboard thread did not terminate in time")

        # Stop health monitor and unregister from multi-project registry
        if hasattr(self, "_health_monitor") and self._health_monitor is not None:
            log.info("Stopping health monitor...")
            self._health_monitor.stop()

        if hasattr(self, "_tenant_id") and self._tenant_id:
            try:
                from murena.multi_project import TenantRegistry

                registry = TenantRegistry()
                registry.unregister_tenant(self._tenant_id)
                log.debug(f"Unregistered tenant '{self._tenant_id}' from multi-project registry")
            except Exception as e:
                log.warning(f"Failed to unregister tenant: {e}")

    def get_tool_by_name(self, tool_name: str) -> Tool:
        tool_class = ToolRegistry().get_tool_class_by_name(tool_name)
        return self.get_tool(tool_class)

    def get_active_lsp_languages(self) -> list[Language]:
        ls_manager = self.get_language_server_manager()
        if ls_manager is None:
            return []
        return ls_manager.get_active_languages()
