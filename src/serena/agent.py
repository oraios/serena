"""
The Serena Model Context Protocol (MCP) Server
"""
import inspect
import json
import os
import platform
import sys
import traceback
from abc import ABC
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar, Union

import yaml
from sensai.util import logging
from sensai.util.string import ToStringMixin

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from serena import serena_root_path, serena_version
from serena.context_mode_config import ContextConfig, ModeConfig, load_context_config, load_mode_config, resolve_tool_activations
from serena.llm.prompt_factory import PromptFactory
from serena.symbol import SymbolManager
from serena.util.class_decorators import singleton

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

LOG_FORMAT = "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s"

log = logging.getLogger(__name__)

T = TypeVar("T")


def show_fatal_exception_safe(e: Exception) -> None:
    """
    Show a fatal exception in a way that is safe to call from anywhere.
    """
    try:
        log.exception("Fatal exception: %s", e)
    except:
        print("Fatal exception:", e, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


class Tool(ABC):
    def __init__(self, agent: "SerenaAgent"):
        self.agent = agent

    def get_name(self) -> str:
        """
        :return: the name of the tool to appear in the UI
        """
        name = str(self.__class__.__name__)
        if name.endswith("Tool"):
            name = name[:-4]
        return name

    @classmethod
    def can_edit(cls) -> bool:
        """
        :return: whether the tool can edit files
        """
        return False

    def get_description(self) -> str:
        """
        :return: a description of the tool
        """
        doc = inspect.getdoc(self.apply)
        if doc is None:
            return ""
        return doc

    def apply(self, **kwargs) -> str:
        """
        Apply the tool with the given arguments. This is primarily meant to be overridden by subclasses.
        """
        raise NotImplementedError

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs) -> str:
        """
        Like apply, but logs the call and catches exceptions. This method is intended to be called by the client and not by the agent itself.
        """
        try:
            if log_call:
                name = self.get_name()
                # highlight tool name that actually perform edits
                if name.endswith("Tool"):
                    name = name[:-4]
                args_json = json.dumps({k: v for k, v in kwargs.items()})
                log.info(f"Tool {name} called with args: {args_json}")

            return self.apply(**kwargs)
        except Exception as e:
            if catch_exceptions:
                tb_str = traceback.format_exc()
                err_msg = f"Error executing tool: {e}\n{tb_str}"
                log.exception(err_msg)
                return err_msg
            else:
                raise

    def get_all_parameters(self) -> dict[str, dict[str, Any]]:
        """
        :return: all parameters of the tool
        """
        params = {}
        for name, param in inspect.signature(self.apply).parameters.items():
            if name != "self":
                params[name] = {}
                if param.default is not inspect.Parameter.empty:
                    params[name]["default"] = param.default
                if param.annotation is not inspect.Parameter.empty and param.annotation is not Any:
                    params[name]["type"] = str(param.annotation)
        return params

    def get_required_parameters(self) -> list[str]:
        """
        :return: the list of required parameters
        """
        required_params = []
        for name, param in inspect.signature(self.apply).parameters.items():
            if name != "self" and param.default is inspect.Parameter.empty:
                required_params.append(name)
        return required_params


TTool = TypeVar("TTool", bound=Tool)
"""
Type variable for Tool classes used in SerenaAgent.get_tool.
"""


def _print_tool_overview(tools: Iterable[Tool]) -> None:
    """
    Prints an overview of the available tools.
    """
    for tool in sorted(tools, key=lambda t: t.get_name()):
        params = []
        for name, param in inspect.signature(tool.apply).parameters.items():
            if name != "self":
                if param.default is not inspect.Parameter.empty:
                    params.append(f"{name}={param.default}")
                else:
                    params.append(name)
        print(f"{tool.get_name()}({', '.join(params)})")


def iter_tool_classes() -> Generator[type[Tool], None, None]:
    """
    Yield all concrete Tool classes.
    """
    for modname in dir(sys.modules["serena"]):
        if modname.endswith("_tool"):
            continue
        try:
            mod = getattr(sys.modules["serena"], modname)
            for name in dir(mod):
                if name.endswith("Tool") and name != "Tool":
                    cls = getattr(mod, name)
                    # skip abstract classes (subclasses of Tool)
                    if isinstance(cls, type) and issubclass(cls, Tool) and cls != Tool:
                        for c in cls.__mro__:
                            a = c.__dict__.get("__abstractmethods__", None)
                            if a and len(a) > 0:
                                break
                        else:
                            # No abstractmethod found, must be a concrete class
                            yield cls
        except AttributeError:
            pass


@dataclass
class ProjectConfig(ToStringMixin):
    """
    Project configuration
    """

    project_name: str
    language: Language
    project_root: Path
    ignored_paths: list[str]
    excluded_tools: set[str]
    read_only: bool = False
    ignore_all_files_in_gitignore: bool = True

    @classmethod
    def from_dict(cls, config_dict: dict[str, Any], project_name: str, project_root: Path | None = None) -> Self:
        language = Language.from_string(config_dict.get("language", "python"))
        root_path = config_dict.get("project_root")
        if root_path is None and project_root is None:
            # if project_root is not provided, use the current working directory as a default
            project_root = Path.cwd()
        elif root_path is not None:
            project_root = Path(root_path)
        assert project_root is not None
        ignored_paths = config_dict.get("ignored_paths", [])
        # We have to handle the case where excluded_tools was None in the yml file, which results in None instead of []
        excluded_tools = set(config_dict.get("excluded_tools", []) or [])
        read_only = config_dict.get("read_only", False)
        ignore_all_files_in_gitignore = config_dict.get("ignore_all_files_in_gitignore", True)
        return cls(
            project_name=project_name,
            language=language,
            project_root=project_root,
            ignored_paths=ignored_paths,
            excluded_tools=excluded_tools,
            read_only=read_only,
            ignore_all_files_in_gitignore=ignore_all_files_in_gitignore,
        )

    @classmethod
    def from_yml(cls, path: Path) -> Self:
        project_name = path.stem
        project_root = path.parent
        with open(path) as f:
            config_dict = yaml.safe_load(f)
        return cls.from_dict(config_dict, project_name=project_name, project_root=project_root)

    def get_serena_managed_dir(self) -> str:
        """
        :return: path to directory managed by serena (for memories, etc.)
        """
        serena_dir = os.path.join(self.project_root, ".serena")
        os.makedirs(serena_dir, exist_ok=True)
        return serena_dir


class LinesRead:
    def __init__(self) -> None:
        self.files: dict[str, set[tuple[int, int]]] = defaultdict(lambda: set())

    def add_lines_read(self, relative_path: str, start_line: int, end_line: int) -> None:
        range_to_insert = (start_line, end_line)
        ranges = []

        if relative_path in self.files:
            # Find ranges that can be merged or are contained in another range
            for existing_range in self.files[relative_path]:
                # If the new range is fully contained in an existing range, don't need to insert it
                if start_line >= existing_range[0] and end_line <= existing_range[1]:
                    return

                # If the existing range is fully contained in the new range, drop the existing range
                if existing_range[0] >= start_line and existing_range[1] <= end_line:
                    continue

                # If the ranges overlap, merge them
                if max(start_line, existing_range[0]) <= min(end_line, existing_range[1]) + 1:
                    start_line = min(start_line, existing_range[0])
                    end_line = max(end_line, existing_range[1])
                else:
                    ranges.append(existing_range)

        ranges.append((start_line, end_line))
        self.files[relative_path] = set(ranges)

    def invalidate_lines_read(self, relative_path: str) -> None:
        if relative_path in self.files:
            del self.files[relative_path]


class SerenaAgent:
    def __init__(
        self, 
        project_file_path: str | None = None, 
        project_activation_callback: Callable[[], None] | None = None,
        context_name_or_path: str | None = None,
        mode_names_or_paths: list[str] | None = None
    ):
        """
        :param project_file_path: the configuration file (.yml) of the project to load immediately;
            if None, do not load any project (must use project selection tool to activate a project).
            If a project is provided, the corresponding language server will be started.
        :param project_activation_callback: a callback function to be called when a project is activated.
        :param context_name_or_path: Name or path to a context configuration file
        :param mode_names_or_paths: List of names or paths to mode configuration files
        """
        # obtain serena configuration
        self.serena_config = SerenaConfig()

        # open GUI log window if enabled
        self._gui_log_handler: Union["GuiLogViewerHandler", None] = None  # noqa
        if self.serena_config.gui_log_window_enabled:
            if platform.system() == "Darwin":
                log.warning("GUI log window is not supported on macOS")
            else:
                # even importing on macOS may fail if tkinter dependencies are unavailable (depends on Python interpreter installation
                # which uv used as a base, unfortunately)
                from serena.gui_log_viewer import GuiLogViewer, GuiLogViewerHandler

                log_level = self.serena_config.gui_log_window_level
                if Logger.root.level > log_level:
                    log.info(f"Root logger level is higher than GUI log level; changing the root logger level to {log_level}")
                    Logger.root.setLevel(log_level)
                self._gui_log_handler = GuiLogViewerHandler(GuiLogViewer(title="Serena Logs"), level=log_level, format_string=LOG_FORMAT)
                Logger.root.addHandler(self._gui_log_handler)

        log.info(f"Starting Serena server (version={serena_version()}, process id={os.getpid()}, parent process id={os.getppid()})")
        log.info("Available projects: {}".format(", ".join(self.serena_config.project_names)))

        self.prompt_factory = PromptFactory()
        self._project_activation_callback = project_activation_callback

        # Initialize context and modes
        self.context_config: ContextConfig | None = None
        self.mode_configs: list[ModeConfig] = []
        
        # Load context and modes if provided
        if context_name_or_path:
            self.context_config = load_context_config(context_name_or_path)
            log.info(f"Loaded context: {self.context_config.name}")
        
        if mode_names_or_paths:
            for mode_name_or_path in mode_names_or_paths:
                mode_config = load_mode_config(mode_name_or_path)
                self.mode_configs.append(mode_config)
            log.info(f"Loaded modes: {', '.join([mode.name for mode in self.mode_configs])}")

        # project-specific instances, which will be initialized upon project activation
        self.project_config: ProjectConfig | None = None
        self.language_server: SyncLanguageServer | None = None
        self.symbol_manager: SymbolManager | None = None
        self.memories_manager: MemoriesManager | None = None
        self.lines_read: LinesRead | None = None

        # find all tool classes and instantiate them
        self._all_tools: dict[type[Tool], Tool] = {}
        for tool_class in iter_tool_classes():
            tool_instance = tool_class(self)
            if not self.serena_config.enable_project_activation:
                # Check for project activation tools by name to avoid circular imports
                tool_name = tool_instance.get_name()
                if tool_name in ("ActivateProject", "GetActiveProject"):
                    log.info(f"Excluding tool '{tool_instance.get_name()}' because project activation is disabled in configuration")
                    continue
            self._all_tools[tool_class] = tool_instance
        
        # Apply context and mode tool settings
        self._active_tools = dict(self._all_tools)
        self._apply_context_and_mode_tool_settings()
        
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name() for tool in self._all_tools.values()])}")
        log.info(f"Active tools ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_handler is not None:
            tool_names = [tool.get_name() for tool in self._active_tools.values()]
            self._gui_log_handler.log_viewer.set_tool_names(tool_names)

        # activate a project configuration (if provided or if there is only a single project available)
        project_config: ProjectConfig | None = None
        if project_file_path is not None:
            if not os.path.exists(project_file_path):
                raise FileNotFoundError(f"Project file not found: {project_file_path}")
            log.info(f"Loading project configuration from {project_file_path}")
            project_config = ProjectConfig.from_yml(Path(project_file_path))
        else:
            match len(self.serena_config.projects):
                case 0:
                    raise RuntimeError(f"No projects found in {SerenaConfig.CONFIG_FILE} and no project file specified.")
                case 1:
                    project_config = self.serena_config.get_project_configuration(self.serena_config.project_names[0])
        if project_config is not None:
            self.activate_project(project_config)
        else:
            if not self.serena_config.enable_project_activation:
                raise ValueError("Tool-based project activation is disabled in the configuration but no project file was provided.")

    def get_exposed_tools(self) -> list["Tool"]:
        """
        :return: the list of tools that are to be exposed/registered in the client
        """
        if self.serena_config.enable_project_activation:
            # With project activation, we must expose all tools and handle tool activation within Serena
            # (because clients do not react to changed tools)
            return list(self._all_tools.values())
        else:
            # When project activation is not enabled, we only expose the active tools
            return list(self._active_tools.values())

    def _apply_context_and_mode_tool_settings(self) -> None:
        """Apply tool settings from context and mode configurations."""
        # Start with all tools
        self._active_tools = dict(self._all_tools)
        
        # Apply context and mode tool settings
        if self.context_config or self.mode_configs:
            included_tools, excluded_tools = resolve_tool_activations(self.context_config, self.mode_configs)
            
            # Apply explicit includes if any are specified
            if included_tools:
                self._active_tools = {
                    key: tool for key, tool in self._all_tools.items() 
                    if tool.get_name() in included_tools
                }
            
            # Apply excludes
            if excluded_tools:
                self._active_tools = {
                    key: tool for key, tool in self._active_tools.items() 
                    if tool.get_name() not in excluded_tools
                }
                
            log.info(f"Active tools after context/mode configuration ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")

    def set_modes(self, mode_names_or_paths: list[str]) -> None:
        """
        Set new modes for the agent.
        
        :param mode_names_or_paths: List of mode names or paths
        """
        # Clear current modes
        self.mode_configs = []
        
        # Load new modes
        for mode_name_or_path in mode_names_or_paths:
            mode_config = load_mode_config(mode_name_or_path)
            self.mode_configs.append(mode_config)
        
        log.info(f"Updated modes: {', '.join([mode.name for mode in self.mode_configs])}")
        
        # Reapply tool settings
        self._apply_context_and_mode_tool_settings()
        
        # If project is active, apply project tool exclusions
        if self.project_config:
            self._apply_project_tool_exclusions()

    def _apply_project_tool_exclusions(self) -> None:
        """Apply tool exclusions from the project configuration."""
        if not self.project_config:
            return
        
        # Apply project-specific exclusions
        if self.project_config.excluded_tools:
            self._active_tools = {
                key: tool for key, tool in self._active_tools.items() 
                if tool.get_name() not in self.project_config.excluded_tools
            }
            log.info(f"Active tools after project exclusions ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")
        
        # If read_only mode is enabled, exclude all editing tools
        if self.project_config.read_only:
            self._active_tools = {key: tool for key, tool in self._active_tools.items() if not key.can_edit()}
            log.info(
                f"Project is in read-only mode. Editing tools excluded. Active tools ({len(self._active_tools)}): "
                f"{', '.join(self.get_active_tool_names())}"
            )

    def activate_project(self, project_config: ProjectConfig) -> None:
        """
        Activate a project configuration.
        
        :param project_config: The project configuration to activate
        """
        log.info(f"Activating {project_config}")
        self.project_config = project_config

        # Apply project tool exclusions
        self._apply_project_tool_exclusions()

        # start the language server
        self.reset_language_server()
        assert self.language_server is not None

        # initialize project-specific instances
        self.symbol_manager = SymbolManager(self.language_server, self)
        self.memories_manager = MemoriesManager(os.path.join(self.project_config.get_serena_managed_dir(), "memories"))
        self.lines_read = LinesRead()

        if self._project_activation_callback is not None:
            self._project_activation_callback()

    def get_system_prompt(self) -> str:
        """
        Get the system prompt with context and mode information.
        
        :return: The system prompt
        """
        return self.prompt_factory.create_system_prompt(
            context=self.context_config,
            modes=self.mode_configs
        )

    def get_active_tool_names(self) -> list[str]:
        """
        :return: the list of names of the active tools for the current project
        """
        return sorted([tool.get_name() for tool in self._active_tools.values()])

    def is_language_server_running(self) -> bool:
        return self.language_server is not None and self.language_server.is_running()

    def reset_language_server(self) -> None:
        """
        Starts/resets the language server for the current project
        """
        # stop the language server if it is running
        if self.is_language_server_running():
            log.info("Stopping the language server ...")
            assert self.language_server is not None
            self.language_server.stop()
            self.language_server = None

        # instantiate and start the language server
        assert self.project_config is not None
        multilspy_config = MultilspyConfig(code_language=self.project_config.language, ignored_paths=self.project_config.ignored_paths)
        ls_logger = MultilspyLogger()
        self.language_server = SyncLanguageServer.create(
            multilspy_config,
            ls_logger,
            self.project_config.project_root,
            add_gitignore_content_to_config=self.project_config.ignore_all_files_in_gitignore,
        )
        self.language_server.start()
        if not self.language_server.is_running():
            raise RuntimeError(f"Failed to start the language server for {self.project_config}")

    def get_tool(self, tool_class: type[TTool]) -> TTool:
        return self._all_tools[tool_class]  # type: ignore

    def print_tool_overview(self) -> None:
        _print_tool_overview(self._active_tools.values())

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
            self.language_server.stop()
        if self._gui_log_handler:
            log.info("Stopping the GUI log window ...")
            self._gui_log_handler.stop_viewer()
            Logger.root.removeHandler(self._gui_log_handler)


class MemoriesManager:
    def __init__(self, memory_dir: str):
        self._memory_dir = Path(memory_dir)
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_memory_file_path(self, memory_file_name: str) -> Path:
        return self._memory_dir / memory_file_name

    def load_memory(self, memory_file_name: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        if not memory_file_path.exists():
            return f"Memory file {memory_file_name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding="utf-8") as f:
            return f.read()

    def save_memory(self, memory_file_name: str, content: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        with open(memory_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Memory {memory_file_name} has been saved."

    def list_memories(self) -> list[str]:
        return [file.name for file in self._memory_dir.glob("*") if file.is_file()]

    def delete_memory(self, memory_file_name: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        if not memory_file_path.exists():
            return f"Memory file {memory_file_name} does not exist."
        memory_file_path.unlink()
        return f"Memory {memory_file_name} has been deleted."


@singleton
class SerenaConfig:
    """
    Serena Configuration, which is loaded from ~/.serena/serena.yml
    """

    CONFIG_FILE = os.path.expanduser("~/.serena/serena.yml")

    def __init__(self) -> None:
        config_file = os.path.join(serena_root_path(), self.CONFIG_FILE)
        if not os.path.exists(config_file):
            # create default configuration
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            config = {}
            with open(config_file, "w") as f:
                yaml.dump(config, f)

        # load configuration
        with open(config_file) as f:
            self.config_dict = yaml.safe_load(f) or {}

        # Projects that serena knows about, typically from ~/.serena/projects
        self.projects_dir = os.path.expanduser("~/.serena/projects")
        os.makedirs(self.projects_dir, exist_ok=True)
        self.projects: dict[str, str] = {}
        for f in os.listdir(self.projects_dir):
            if f.endswith(".yml"):
                name = f[:-4]
                self.projects[name] = os.path.join(self.projects_dir, f)

        # GUI log window (tkinter)
        self.gui_log_window_enabled = self.config_dict.get("gui_log_window_enabled", False)
        # disable GUI log window for MCP server (led to strange crashes)
        if "SERENA_MCP_SERVER" in os.environ:
            self.gui_log_window_enabled = False
        self.gui_log_window_level = self.config_dict.get("gui_log_window_level", logging.INFO)

        # project activation
        self.enable_project_activation = self.config_dict.get("enable_project_activation", True)

    @property
    def project_names(self) -> list[str]:
        """
        :return: the list of project names available
        """
        return sorted(self.projects.keys())

    def get_project_configuration(self, project_name: str) -> ProjectConfig:
        """
        :param project_name: the name of the project (typically loaded from ~/.serena/projects)
        :return: project configuration
        """
        project_file = self.projects.get(project_name)
        if project_file is None:
            raise KeyError(f"Project '{project_name}' not found. Available projects: {', '.join(self.project_names)}")
        return ProjectConfig.from_yml(Path(project_file))

    def add_project(self, project_name: str, project_file_path: str) -> None:
        """
        :param project_name: the name of the project, as stored in the config
        :param project_file_path: the path to the project file
        """
        if not os.path.exists(project_file_path):
            raise FileNotFoundError(f"Project file not found: {project_file_path}")
        if not os.path.isabs(project_file_path):
            project_file_path = os.path.abspath(project_file_path)
        self.projects[project_name] = project_file_path
        # save to projects dir
        projects_file = os.path.join(self.projects_dir, f"{project_name}.yml")
        with open(projects_file, "w") as f:
            yaml.dump({"project_file_path": project_file_path}, f)

    def remove_project(self, project_name: str) -> None:
        """
        :param project_name: the name of the project, as stored in the config
        """
        if project_name not in self.projects:
            raise KeyError(f"Project '{project_name}' not found. Available projects: {', '.join(self.project_names)}")
        del self.projects[project_name]
        # remove from projects dir
        projects_file = os.path.join(self.projects_dir, f"{project_name}.yml")
        if os.path.exists(projects_file):
            os.remove(projects_file)


# Import these classes to avoid circular dependencies
