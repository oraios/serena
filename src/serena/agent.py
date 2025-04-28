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
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar, Union, cast

import yaml
from sensai.util import logging
from sensai.util.logging import FallbackHandler
from sensai.util.string import ToStringMixin, dict_string

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_types import SymbolKind
from serena import serena_root_path, serena_version
from serena.llm.prompt_factory import PromptFactory
from serena.symbol import SymbolLocation, SymbolManager
from serena.text_utils import search_files
from serena.util.class_decorators import singleton
from serena.util.file_system import scan_directory
from serena.util.inspection import iter_subclasses
from serena.util.shell import execute_shell_command

if TYPE_CHECKING:
    from serena.gui_log_viewer import GuiLogViewerHandler

log = logging.getLogger(__name__)
LOG_FORMAT = "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s"
TTool = TypeVar("TTool", bound="Tool")
SUCCESS_RESULT = "OK"


def show_fatal_exception_safe(e: Exception) -> None:
    """
    Shows the given exception in the GUI log viewer on the main thread and ensures that the exception is logged or at
    least printed to stderr.
    """
    # Make sure the error is logged (adding a fallback handler which writes to stderr in case there is no other handler)
    fallback_handler = FallbackHandler(logging.StreamHandler(sys.stderr))
    Logger.root.addHandler(fallback_handler)
    log.error(f"Fatal exception: {e}", exc_info=e)

    # attempt to show the error in the GUI
    try:
        # NOTE: The import can fail on macOS if Tk is not available (depends on Python interpreter installation, which uv
        #   used as a base); while tkinter as such is always available, its dependencies can be unavailable on macOS.
        from serena.gui_log_viewer import show_fatal_exception

        show_fatal_exception(e)
    except:
        pass


class SerenaConfigError(Exception):
    pass


class ProjectConfig(ToStringMixin):
    SERENA_MANAGED_DIR = ".serena"
    SERENA_DEFAULT_PROJECT_FILE = "project.yml"

    def __init__(self, config_dict: dict[str, Any], project_name: str, project_root: Path | None = None):
        self.project_name: str = project_name
        try:
            self.language: Language = Language(config_dict["language"].lower())
        except ValueError as e:
            raise ValueError(f"Invalid language: {config_dict['language']}.\nValid languages are: {[l.value for l in Language]}") from e
        if project_root is None:
            project_root = Path(config_dict["project_root"])
        self.project_root: str = str(project_root.resolve())
        self.ignored_paths: list[str] = config_dict.get("ignored_paths", [])
        self.excluded_tools: set[str] = set(config_dict.get("excluded_tools", []))
        self.read_only: bool = config_dict.get("read_only", False)

        if "ignore_all_files_in_gitignore" not in config_dict:
            raise SerenaConfigError(
                f"`ignore_all_files_in_gitignore` key not found in configuration of project '{project_name}'. "
                "Please update your `.yml` configuration file for this project. "
                "It is recommended to set this to `True`."
            )
        self.ignore_all_files_in_gitignore = config_dict["ignore_all_files_in_gitignore"]

        # Raise errors for deprecated keys
        if "ignored_dirs" in config_dict:
            raise SerenaConfigError(
                f"Use of `ignored_dirs` key in configuration of project '{project_name}' deprecated. Please use `ignored_paths` instead. "
                "Note that you can also set `ignore_all_files_in_gitignore` to `True`, which will be enough for most cases."
            )

    @classmethod
    def from_yml(cls, yml_path: Path) -> Self:
        log.info(f"Loading project configuration from {yml_path}")
        try:
            with open(yml_path, encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)
            if yml_path.parent.name == cls.SERENA_MANAGED_DIR:
                project_root = yml_path.parent.parent
                project_name = project_root.name
            else:
                project_root = None
                project_name = yml_path.stem
            return cls(config_dict, project_name=project_name, project_root=project_root)
        except Exception as e:
            raise ValueError(f"Error loading project configuration from {yml_path}: {e}") from e

    def get_serena_managed_dir(self) -> str:
        return os.path.join(self.project_root, self.SERENA_MANAGED_DIR)


@singleton
class SerenaConfig:
    """
    Handles user-defined Serena configuration based on the configuration file
    """

    CONFIG_FILE = "serena_config.yml"

    def __init__(self) -> None:
        config_file = os.path.join(serena_root_path(), self.CONFIG_FILE)
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Serena configuration file not found: {config_file}")
        with open(config_file, encoding="utf-8") as f:
            try:
                log.info(f"Loading Serena configuration from {config_file}")
                config_yaml = yaml.safe_load(f)
            except Exception as e:
                raise ValueError(f"Error loading Serena configuration from {config_file}: {e}") from e

        # read projects
        self.projects: dict[str, ProjectConfig] = {}
        if "projects" not in config_yaml:
            raise SerenaConfigError("`projects` key not found in Serena configuration. Please update your `serena_config.yml` file.")
        for project_config_path in config_yaml["projects"]:
            project_config_path = Path(project_config_path)
            if not project_config_path.is_absolute():
                project_config_path = Path(serena_root_path()) / project_config_path
            if project_config_path.is_dir():  # assume project file in default location
                project_config_path = project_config_path / ProjectConfig.SERENA_MANAGED_DIR / ProjectConfig.SERENA_DEFAULT_PROJECT_FILE
            if not project_config_path.is_file():
                raise FileNotFoundError(f"Project file not found: {project_config_path}")
            log.info(f"Loading project configuration from {project_config_path}")
            project_config = ProjectConfig.from_yml(project_config_path)
            self.projects[project_config.project_name] = project_config
        self.project_names = list(self.projects.keys())

        self.gui_log_window_enabled = config_yaml.get("gui_log_window", False)
        self.gui_log_window_level = config_yaml.get("gui_log_level", logging.INFO)
        self.enable_project_activation = config_yaml.get("enable_project_activation", True)

    def get_project_configuration(self, project_name: str) -> ProjectConfig:
        if project_name not in self.projects:
            raise ValueError(f"Project '{project_name}' not found in Serena configuration; valid project names: {self.project_names}")
        return self.projects[project_name]


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


class SerenaAgent:
    def __init__(self, project_file_path: str | None = None, project_activation_callback: Callable[[], None] | None = None):
        """
        :param project_file_path: the configuration file (.yml) of the project to load immediately;
            if None, do not load any project (must use project selection tool to activate a project).
            If a project is provided, the corresponding language server will be started.
        :param project_activation_callback: a callback function to be called when a project is activated.
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
                if tool_class in (GetActiveProjectTool, ActivateProjectTool):
                    log.info(f"Excluding tool '{tool_instance.get_name()}' because project activation is disabled in configuration")
                    continue
            self._all_tools[tool_class] = tool_instance
        self._active_tools = dict(self._all_tools)
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name() for tool in self._all_tools.values()])}")

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

    def activate_project(self, project_config: ProjectConfig) -> None:
        log.info(f"Activating {project_config}")
        self.project_config = project_config

        # handle project-specific tool exclusions (if any)
        if self.project_config.excluded_tools:
            self._active_tools = {
                key: tool for key, tool in self._all_tools.items() if tool.get_name() not in project_config.excluded_tools
            }
            log.info(f"Active tools after exclusions ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")
        else:
            self._active_tools = dict(self._all_tools)

        # if read_only mode is enabled, exclude all editing tools
        if self.project_config.read_only:
            self._active_tools = {key: tool for key, tool in self._active_tools.items() if not key.can_edit()}
            log.info(
                f"Project is in read-only mode. Editing tools excluded. Active tools ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}"
            )

        # start the language server
        self.reset_language_server()
        assert self.language_server is not None

        # initialize project-specific instances
        self.symbol_manager = SymbolManager(self.language_server, self)
        self.memories_manager = MemoriesManager(os.path.join(self.project_config.get_serena_managed_dir(), "memories"))
        self.lines_read = LinesRead()

        if self._project_activation_callback is not None:
            self._project_activation_callback()

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
        return f"Memory file {memory_file_name} written."

    def list_memories(self) -> list[str]:
        return [f.name for f in self._memory_dir.iterdir() if f.is_file()]

    def delete_memory(self, memory_file_name: str) -> str:
        memory_file_path = self._get_memory_file_path(memory_file_name)
        memory_file_path.unlink()
        return f"Memory file {memory_file_name} deleted."


class Component(ABC):
    def __init__(self, agent: "SerenaAgent"):
        self.agent = agent

    @property
    def language_server(self) -> SyncLanguageServer:
        assert self.agent.language_server is not None
        return self.agent.language_server

    @property
    def project_root(self) -> str:
        assert self.project_config is not None
        return self.project_config.project_root

    @property
    def project_config(self) -> ProjectConfig:
        assert self.agent.project_config is not None
        return self.agent.project_config

    @property
    def prompt_factory(self) -> PromptFactory:
        return self.agent.prompt_factory

    @property
    def memories_manager(self) -> MemoriesManager:
        assert self.agent.memories_manager is not None
        return self.agent.memories_manager

    @property
    def symbol_manager(self) -> SymbolManager:
        assert self.agent.symbol_manager is not None
        return self.agent.symbol_manager

    @property
    def lines_read(self) -> LinesRead:
        assert self.agent.lines_read is not None
        return self.agent.lines_read


_DEFAULT_MAX_ANSWER_LENGTH = int(2e5)


class ToolMarkerCanEdit:
    """
    Marker class for all tools that can perform editing operations on files.
    """


class ToolMarkerDoesNotRequireActiveProject:
    pass


class Tool(Component):
    # NOTE: each tool should implement the apply method, which is then used in
    # the central method of the Tool class `apply_ex`.
    # Failure to do so will result in a RuntimeError at tool execution time.
    # The apply method is not declared as part of the base Tool interface since we cannot
    # know the signature of the (input parameters of the) method in advance.
    #
    # The docstring and types of the apply method are used to generate the tool description
    # (which is use by the LLM, so a good description is important)
    # and to validate the tool call arguments.

    @classmethod
    def get_name(cls) -> str:
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # convert to snake_case
        name = "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")
        return name

    def get_apply_fn(self) -> Callable:
        apply_fn = getattr(self, "apply")
        if apply_fn is None:
            raise RuntimeError(f"apply not defined in {self}. Did you forget to implement it?")
        return apply_fn

    @classmethod
    def can_edit(cls) -> bool:
        """
        Returns whether this tool can perform editing operations on code.

        :return: True if the tool can edit code, False otherwise
        """
        return issubclass(cls, ToolMarkerCanEdit)

    @classmethod
    def get_tool_description(cls) -> str:
        docstring = cls.__doc__
        if docstring is None:
            return ""
        return docstring.strip()

    def get_function_description(self) -> str:
        apply_fn = self.get_apply_fn()
        docstring = apply_fn.__doc__
        if docstring is None:
            raise Exception(f"Missing docstring for {self}")
        return docstring

    def _log_tool_application(self, frame: Any) -> None:
        params = {}
        ignored_params = {"self", "log_call", "catch_exceptions", "args", "apply_fn"}
        for param, value in frame.f_locals.items():
            if param in ignored_params:
                continue
            if param == "kwargs":
                params.update(value)
            else:
                params[param] = value
        log.info(f"{self.get_name()}: {dict_string(params)}")

    @staticmethod
    def _limit_length(result: str, max_answer_chars: int) -> str:
        if (n_chars := len(result)) > max_answer_chars:
            result = (
                f"The answer is too long ({n_chars} characters). "
                + "Please try a more specific tool query or raise the max_answer_chars parameter."
            )
        return result

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs) -> str:  # type: ignore
        """
        Applies the tool with the given arguments
        """
        apply_fn = self.get_apply_fn()

        if log_call:
            self._log_tool_application(inspect.currentframe())

        try:
            # check whether the tool requires an active project and language server
            if not isinstance(self, ToolMarkerDoesNotRequireActiveProject):
                if self.agent.project_config is None:
                    return (
                        "Error: No active project. Ask to user to select a project from this list: "
                        + f"{self.agent.serena_config.project_names}"
                    )
                if not self.agent.is_language_server_running():
                    log.info("Language server is not running. Starting it ...")
                    self.agent.reset_language_server()

            # check whether the tool is enabled
            if self.agent.project_config is not None and self.get_name() in self.agent.project_config.excluded_tools:
                return (
                    f"Error: Tool '{self.get_name()}' is disabled for the active project ('{self.project_config.project_name}'); "
                    f"active tools: {self.agent.get_active_tool_names()}"
                )

            # check if the project is in read-only mode and this is an editing tool
            if self.agent.project_config is not None and self.agent.project_config.read_only and self.__class__.can_edit():
                return (
                    f"Error: Tool '{self.get_name()}' cannot be used because the project '{self.project_config.project_name}' "
                    f"is in read-only mode. Editing operations are not allowed."
                )

            # apply the actual tool
            result = apply_fn(**kwargs)

        except Exception as e:
            if not catch_exceptions:
                raise
            msg = f"Error executing tool: {e}\n{traceback.format_exc()}"
            log.error(f"Error executing tool: {e}", exc_info=e)
            result = msg

        if log_call:
            log.info(f"Result: {result}")

        return result


class RestartLanguageServerTool(Tool):
    """Restarts the language server, may be necessary when edits not through Serena happen."""

    def apply(self) -> str:
        """Use this tool only on explicit user request or after confirmation.
        It may be necessary to restart the language server if the user performs edits
        not through Serena, so the language server state becomes outdated and further editing attempts lead to errors.

        If such editing errors happen, you should suggest using this tool.
        """
        self.agent.reset_language_server()
        return SUCCESS_RESULT


class ReadFileTool(Tool):
    """
    Reads a file within the project directory.
    """

    def apply(
        self, relative_path: str, start_line: int = 0, end_line: int | None = None, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH
    ) -> str:
        """
        Reads the given file or a chunk of it. Generally, symbolic operations
        like find_symbol or find_referencing_symbols should be preferred if you know which symbols you are looking for.
        Reading the entire file is only recommended if there is no other way to get the content required for the task.

        :param relative_path: the relative path to the file to read
        :param start_line: the 0-based index of the first line to be retrieved.
        :param end_line: the 0-based index of the last line to be retrieved (inclusive). If None, read until the end of the file.
        :param max_answer_chars: if the file (chunk) is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: the full text of the file at the given relative path
        """
        result = self.language_server.retrieve_full_file_content(relative_path)
        result_lines = result.splitlines()
        if end_line is None:
            result_lines = result_lines[start_line:]
        else:
            self.lines_read.add_lines_read(relative_path, (start_line, end_line))
            result_lines = result_lines[start_line : end_line + 1]
        result = "\n".join(result_lines)

        return self._limit_length(result, max_answer_chars)


class CreateTextFileTool(Tool, ToolMarkerCanEdit):
    """
    Creates/overwrites a file in the project directory.
    """

    def apply(self, relative_path: str, content: str) -> str:
        """
        Write a new file (or overwrite an existing file). For existing files, it is strongly recommended
        to use symbolic operations like replace_symbol_body or insert_after_symbol/insert_before_symbol, if possible.
        You can also use insert_at_line to insert content at a specific line for existing files if the symbolic operations
        are not the right choice for what you want to do.

        If ever used on an existing file, the content has to be the complete content of that file (so it
        may never end with something like "The remaining content of the file is left unchanged.").
        For operations that just replace a part of a file, use the replace_lines or the symbolic editing tools instead.

        :param relative_path: the relative path to the file to create
        :param content: the (utf-8-encoded) content to write to the file
        :return: a message indicating success or failure
        """
        absolute_path = os.path.join(self.project_root, relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File created: {relative_path}"


class ListDirTool(Tool):
    """
    Lists files and directories in the given directory (optionally with recursion).
    """

    def apply(self, relative_path: str, recursive: bool, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Lists files and directories in the given directory (optionally with recursion).

        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object with the names of directories and files within the given directory
        """

        def is_ignored_path(abs_path: str) -> bool:
            rel_path = os.path.relpath(abs_path, self.project_root)
            return self.language_server.is_ignored_path(rel_path, ignore_unsupported_files=False)

        dirs, files = scan_directory(
            os.path.join(self.project_root, relative_path),
            relative_to=self.project_root,
            recursive=recursive,
            is_ignored_dir=is_ignored_path,
            is_ignored_file=is_ignored_path,
        )

        result = json.dumps({"dirs": dirs, "files": files})
        return self._limit_length(result, max_answer_chars)


class GetSymbolsOverviewTool(Tool):
    """
    Gets an overview of the top-level symbols defined in a given file or directory.
    """

    def apply(self, relative_path: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Gets an overview of the given file or directory.
        For each analyzed file, we list the top-level symbols in the file (name, kind, line).
        Use this tool to get a high-level understanding of the code symbols.
        Calling this is often a good idea before more targeted reading, searching or editing operations on the code symbols.

        :param relative_path: the relative path to the file or directory to get the overview of
        :param max_answer_chars: if the overview is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. If the overview is too long, you should use a smaller directory instead,
            (e.g. a subdirectory).
        :return: a JSON object mapping relative paths of all contained files to info about top-level symbols in the file (name, kind, line, column).
        """
        path_to_symbol_infos = self.language_server.request_overview(relative_path)
        result = {}
        for file_path, symbols in path_to_symbol_infos.items():
            result[file_path] = [_tuple_to_info(*symbol_info) for symbol_info in symbols]

        result_json_str = json.dumps(result)
        return self._limit_length(result_json_str, max_answer_chars)


class FindSymbolTool(Tool):
    """
    Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
    """

    def apply(
        self,
        name: str,
        depth: int = 0,
        within_relative_path: str | None = None,
        include_body: bool = False,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        substring_matching: bool = False,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Retrieves information on all symbols/code entities, i.e. classes, methods, attributes, variables, etc.
        with the given name.
        The returned symbol location information can subsequently be used to edit the returned symbols
        or to retrieve further information using other tools.
        If you already anticipate that you will need to reference children of the symbol (like methods or fields contained in a class),
        you can specify a depth > 0.

        :param name: the name of the symbols to find
        :param depth: specifies the depth up to which descendants of the symbol are to be retrieved
            (e.g. depth 1 will retrieve methods and attributes for the case where the symbol refers to a class).
            Provide a non-zero depth if you intend to subsequently query symbols that are contained in the
            retrieved symbol.
        :param within_relative_path: pass a relative path to only consider symbols within this path.
            If a file is passed, only the symbols within this file will be considered.
            If a directory is passed, all files within this directory will be considered.
            If None, the entire codebase will be considered.
        :param include_body: whether to include the body of all symbols in the result. You should only use this
            if you actually need the body of the symbol for the task at hand (for example, for a deep analysis
            of the functionality or for an editing task).
        :param include_kinds: an optional list of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
            Valid kinds:
            1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :param substring_matching: whether to use substring matching for the symbol name.
            If True, the symbol name will be matched if it contains the given name as a substring.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :return: a list of symbols (with symbol locations) that match the given name in JSON format
        """
        include_kinds = cast(list[SymbolKind] | None, include_kinds)
        exclude_kinds = cast(list[SymbolKind] | None, exclude_kinds)
        symbols = self.symbol_manager.find_by_name(
            name,
            include_body=include_body,
            include_kinds=include_kinds,
            exclude_kinds=exclude_kinds,
            substring_matching=substring_matching,
            within_relative_path=within_relative_path,
        )
        symbol_dicts = [s.to_dict(kind=True, location=True, depth=depth, include_body=include_body) for s in symbols]
        result = json.dumps(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingSymbolsTool(Tool):
    """
    Finds symbols that reference the symbol at the given location (optionally filtered by type).
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        include_body: bool = False,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Finds symbols that reference the symbol at the given location.
        Note that among other kinds of references, this function can be used to find (direct) subclasses of a class,
        as subclasses are referencing symbols that have the kind class.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param include_body: whether to include the body of the symbols in the result.
            Note that this might lead to a very long output, so you should only use this if you actually need the body
            of the referencing symbols for the task at hand. Usually it is a better idea to find
            the referencing symbols without the body and then use the find_symbol tool to get the body of
            specific symbols if needed.
        :param include_kinds: an optional list of integers representing the LSP symbol kinds to include.
            If provided, only symbols of the given kinds will be included in the result.
            Valid kinds:
            1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        include_kinds = cast(list[SymbolKind] | None, include_kinds)
        exclude_kinds = cast(list[SymbolKind] | None, exclude_kinds)
        symbols = self.symbol_manager.find_referencing_symbols(
            SymbolLocation(relative_path, line, column),
            include_body=include_body,
            include_kinds=include_kinds,
            exclude_kinds=exclude_kinds,
        )
        symbol_dicts = [s.to_dict(kind=True, location=True, depth=0, include_body=include_body) for s in symbols]
        result = json.dumps(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingCodeSnippetsTool(Tool):
    """
    Finds code snippets in which the symbol at the given location is referenced.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Returns short code snippets where the symbol at the given location is referenced.

        Contrary to the `find_referencing_symbols` tool, this tool returns references that are not symbols but instead
        code snippets that may or may not be contained in a symbol (for example, file-level calls).
        It may make sense to use this tool to get a quick overview of the code that references
        the symbol. Usually, just looking at code snippets is not enough to understand the full context,
        unless the case you are investigating is very simple,
        or you already have read the relevant symbols using the find_referencing_symbols tool and
        now want to get an overview of how the referenced symbol (at the given location) is used in them.
        The size of the snippets is controlled by the context_lines_before and context_lines_after parameters.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number of the symbol to find references for
        :param column: the column of the symbol to find references for
        :param context_lines_before: the number of lines to include before the line containing the reference
        :param context_lines_after: the number of lines to include after the line containing the reference
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        """
        matches = self.language_server.request_references_with_content(
            relative_path, line, column, context_lines_before, context_lines_after
        )
        result = [match.to_display_string() for match in matches]
        result_json_str = json.dumps(result)
        return self._limit_length(result_json_str, max_answer_chars)


class ReplaceSymbolBodyTool(Tool, ToolMarkerCanEdit):
    """
    Replaces the full definition of a symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        body: str,
    ) -> str:
        """
        Replaces the body of the symbol at the given location.
        Important: Do not try to guess symbol locations but instead use the find_symbol tool to get the correct location.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param body: the new symbol body. Important: Provide the correct level of indentation
            (as the original body). Note that the first line must not be indented (i.e. no leading spaces).
        """
        self.symbol_manager.replace_body(
            SymbolLocation(relative_path, line, column),
            body=body,
        )
        return SUCCESS_RESULT


class InsertAfterSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content after the end of the definition of a given symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        body: str,
    ) -> str:
        """
        Inserts the given body/content after the end of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param body: the body/content to be inserted
        """
        location = SymbolLocation(relative_path, line, column)
        self.symbol_manager.insert_after(
            location,
            body=body,
        )
        return SUCCESS_RESULT


class InsertBeforeSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content before the beginning of the definition of a given symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        body: str,
    ) -> str:
        """
        Inserts the given body/content before the beginning of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.
        It also can be used to insert a new import statement before the first symbol in the file.

        :param relative_path: the relative path to the file containing the symbol
        :param line: the line number
        :param column: the column
        :param body: the body/content to be inserted
        """
        self.symbol_manager.insert_before(
            SymbolLocation(relative_path, line, column),
            body=body,
        )
        return SUCCESS_RESULT


class DeleteLinesTool(Tool, ToolMarkerCanEdit):
    """
    Deletes a range of lines within a file.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Deletes the given lines in the file.
        Requires that the same range of lines was previously read using the `read_file` tool to verify correctness
        of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        """
        if not self.lines_read.were_lines_read(relative_path, (start_line, end_line)):
            read_lines_tool = self.agent.get_tool(ReadFileTool)
            return f"Error: Must call `{read_lines_tool.get_name()}` first to read exactly the affected lines."
        self.symbol_manager.delete_lines(relative_path, start_line, end_line)
        return SUCCESS_RESULT


class ReplaceLinesTool(Tool, ToolMarkerCanEdit):
    """
    Replaces a range of lines within a file with new content.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int,
        end_line: int,
        content: str,
    ) -> str:
        """
        Replaces the given range of lines in the given file.
        Requires that the same range of lines was previously read using the `read_file` tool to verify correctness
        of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        :param content: the content to insert
        """
        if not content.endswith("\n"):
            content += "\n"
        result = self.agent.get_tool(DeleteLinesTool).apply(relative_path, start_line, end_line)
        if result != SUCCESS_RESULT:
            return result
        self.agent.get_tool(InsertAtLineTool).apply(relative_path, start_line, content)
        return SUCCESS_RESULT


class InsertAtLineTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content at a given line in a file.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        content: str,
    ) -> str:
        """
        Inserts the given content at the given line in the file, pushing existing content of the line down.
        In general, symbolic insert operations like insert_after_symbol or insert_before_symbol should be preferred if you know which
        symbol you are looking for.
        However, this can also be useful for small targeted edits of the body of a longer symbol (without replacing the entire body).

        :param relative_path: the relative path to the file
        :param line: the 0-based index of the line to insert content at
        :param content: the content to be inserted
        """
        if not content.endswith("\n"):
            content += "\n"
        self.symbol_manager.insert_at_line(relative_path, line, content)
        return SUCCESS_RESULT


class CheckOnboardingPerformedTool(Tool):
    """
    Checks whether project onboarding was already performed.
    """

    def apply(self) -> str:
        """
        Checks whether project onboarding was already performed.
        You should always call this tool before beginning to actually work on the project/after activating a project,
        but after calling the initial instructions tool.
        If onboarding was already performed, you will receive a list of available memories.
        Don't read the memories immediately after if not needed, just remember that they exist and that you can read them later.
        """
        list_memories_tool = self.agent.get_tool(ListMemoriesTool)
        memories = json.loads(list_memories_tool.apply())
        if len(memories) == 0:
            return (
                "Onboarding not performed yet (no memories available). "
                + "You should perform onboarding by calling the `onboarding` tool before proceeding with the task."
            )
        else:
            return json.dumps({"result": "Onboarding already performed.", "available_memories": memories})


class OnboardingTool(Tool):
    """
    Performs onboarding (identifying the project structure and essential tasks, e.g. for testing or building).
    """

    def apply(self) -> str:
        """
        Call this tool if onboarding was not performed yet.
        You will call this tool at most once per conversation.

        :return: instructions on how to create the onboarding information
        """
        system = platform.system()
        return self.prompt_factory.create_onboarding_prompt(system=system)


class WriteMemoryTool(Tool):
    """
    Writes a named memory (for future reference) to Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, content: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Write some information about this project that can be useful for future tasks to a memory file.
        The information should be short and to the point.
        The memory file name should be meaningful, such that from the name you can infer what the information is about.
        It is better to have multiple small memory files than to have a single large one because
        memories will be read one by one and we only ever want to read relevant memories.

        This tool is either called during the onboarding process or when you have identified
        something worth remembering about the project from the past conversation.
        """
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_file_name} is too long. Max length is {max_answer_chars} characters. "
                + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_file_name, content)


class ReadMemoryTool(Tool):
    """
    Reads the memory with the given name from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Read the content of a memory file. This tool should only be used if the information
        is relevant to the current task. You can infer whether the information
        is relevant from the memory file name.
        You should not read the same memory file multiple times in the same conversation.
        """
        return self.memories_manager.load_memory(memory_file_name)


class ListMemoriesTool(Tool):
    """
    Lists memories in Serena's project-specific memory store.
    """

    def apply(self) -> str:
        """
        List available memories. Any memory can be read using the `read_memory` tool.
        """
        return json.dumps(self.memories_manager.list_memories())


class DeleteMemoryTool(Tool):
    """
    Deletes a memory from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str) -> str:
        """
        Delete a memory file. Should only happen if a user asks for it explicitly,
        for example by saying that the information retrieved from a memory file is no longer correct
        or no longer relevant for the project.
        """
        return self.memories_manager.delete_memory(memory_file_name)


class ThinkAboutCollectedInformationTool(Tool):
    """
    Thinking tool for pondering the completeness of collected information.
    """

    def apply(self) -> str:
        """
        Think about the collected information and whether it is sufficient and relevant.
        This tool should ALWAYS be called after you have completed a non-trivial sequence of searching steps like
        find_symbol, find_referencing_symbols, search_files_for_pattern, read_file, etc.
        """
        return self.prompt_factory.create_think_about_collected_information()


class ThinkAboutTaskAdherenceTool(Tool):
    """
    Thinking tool for determining whether the agent is still on track with the current task.
    """

    def apply(self) -> str:
        """
        Think about the task at hand and whether you are still on track.
        Especially important if the conversation has been going on for a while and there
        has been a lot of back and forth.

        This tool should ALWAYS be called before you insert, replace, or delete code.
        """
        return self.prompt_factory.create_think_about_task_adherence()


class ThinkAboutWhetherYouAreDoneTool(Tool):
    """
    Thinking tool for determining whether the task is truly completed.
    """

    def apply(self) -> str:
        """
        Whenever you feel that you are done with what the user has asked for, it is important to call this tool.
        """
        return self.prompt_factory.create_think_about_whether_you_are_done()


class SummarizeChangesTool(Tool):
    """
    Provides instructions for summarizing the changes made to the codebase.
    """

    def apply(self) -> str:
        """
        Summarize the changes you have made to the codebase.
        This tool should always be called after you have fully completed any non-trivial coding task,
        but only after the think_about_whether_you_are_done call.
        """
        return self.prompt_factory.create_summarize_changes()


class PrepareForNewConversationTool(Tool):
    """
    Provides instructions for preparing for a new conversation (in order to continue with the necessary context).
    """

    def apply(self) -> str:
        """
        Instructions for preparing for a new conversation. This tool should only be called on explicit user request.
        """
        return self.prompt_factory.create_prepare_for_new_conversation()


class SearchForPatternTool(Tool):
    """
    Performs a search for a pattern in the project.
    """

    def apply(
        self,
        pattern: str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
        only_in_code_files: bool = True,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Search for a pattern in the project. You can select whether all files or only code files should be searched.
        Generally, symbolic operations like find_symbol or find_referencing_symbols
        should be preferred if you know which symbols you are looking for.

        :param pattern: Regular expression pattern to search for, either as a compiled Pattern or string
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: optional glob pattern specifying files to include in the search; if not provided, search globally.
        :param paths_exclude_glob: optional glob pattern specifying files to exclude from the search (takes precedence over paths_include_glob).
        :param only_in_code_files: whether to search only in code files or in the entire code base.
            The explicitly ignored files (from serena config and gitignore) are never searched.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :return: A JSON object mapping file paths to lists of matched consecutive lines (with context, if requested).
        """
        if only_in_code_files:
            matches = self.language_server.search_files_for_pattern(
                pattern=pattern,
                context_lines_before=context_lines_before,
                context_lines_after=context_lines_after,
                paths_include_glob=paths_include_glob,
                paths_exclude_glob=paths_exclude_glob,
            )
        else:
            # we walk through all files in the project starting from the root
            files_to_search = []
            ignore_spec = self.language_server.get_ignore_spec()
            for root, dirs, files in os.walk(self.project_root):
                # Don't go into directories that are ignored by modifying dirs inplace
                # Explanation for the  + "/" part:
                # pathspec can't handle the matching of directories if they don't end with a slash!
                # see https://github.com/cpburnz/python-pathspec/issues/89
                dirs[:] = [d for d in dirs if not ignore_spec.match_file(d + "/")]
                for file in files:
                    if not ignore_spec.match_file(os.path.join(root, file)):
                        files_to_search.append(os.path.join(root, file))
            # TODO (maybe): not super efficient to walk through the files again and filter if glob patterns are provided
            #   but it probably never matters and this version required no further refactoring
            matches = search_files(
                files_to_search,
                pattern,
                paths_include_glob=paths_include_glob,
                paths_exclude_glob=paths_exclude_glob,
            )
        # group matches by file
        file_to_matches: dict[str, list[str]] = defaultdict(list)
        for match in matches:
            assert match.source_file_path is not None
            file_to_matches[match.source_file_path].append(match.to_display_string())
        result = json.dumps(file_to_matches)
        return self._limit_length(result, max_answer_chars)


class ExecuteShellCommandTool(Tool, ToolMarkerCanEdit):
    """
    Executes a shell command.
    """

    def apply(
        self,
        command: str,
        cwd: str | None = None,
        capture_stderr: bool = True,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Execute a shell command and return its output.

        IMPORTANT: you should always consider the memory about suggested shell commands before using this tool.
        If this memory was not loaded in the current conversation, you should load it using the `read_memory` tool
        before using this tool.

        You should have at least once looked at the suggested shell commands from the corresponding memory
        created during the onboarding process before using this tool.
        Never execute unsafe shell commands like `rm -rf /` or similar! Generally be very careful with deletions.

        :param command: the shell command to execute
        :param cwd: the working directory to execute the command in. If None, the project root will be used.
        :param capture_stderr: whether to capture and return stderr output
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object containing the command's stdout and optionally stderr output
        """
        _cwd = cwd or self.project_root
        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        result = result.json()
        return self._limit_length(result, max_answer_chars)


class GetActiveProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Gets the name of the currently active project (if any) and lists existing projects
    """

    def apply(
        self,
    ) -> str:
        """
        Gets the name of the currently active project (if any) and returns the list of all available projects.
        To change the current project, use the `activate_project` tool.

        :return: an object containing the name of the currently activated project (if any) and the list of all available projects
        """
        active_project = None if self.agent.project_config is None else self.agent.project_config.project_name
        return json.dumps({"active_project": active_project, "available_projects": self.agent.serena_config.project_names})


class ActivateProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Activates a project by name.
    """

    def apply(self, project_name: str) -> str:
        """
        Activates the project with the given name

        :param project_name: the name of the project to activate
        """
        try:
            project_config = self.agent.serena_config.get_project_configuration(project_name)
        except ValueError as e:
            return str(e)
        self.agent.activate_project(project_config)
        return SUCCESS_RESULT


class InitialInstructionsTool(Tool):
    """
    Gets the initial instructions for the current project.
    Should only be used in settings where the system prompt cannot be set,
    e.g. in clients you have no control over, like Claude Desktop.
    """

    def apply(self) -> str:
        """
        Get the initial instructions for the current coding project.
        You should always call this tool before starting to work (including using any other tool) on any programming task!
        """
        return self.agent.prompt_factory.create_system_prompt()


def iter_tool_classes(same_module_only: bool = True) -> Generator[type[Tool], None, None]:
    """
    Iterate over Tool subclasses.

    :param same_module_only: Whether to only iterate over tools defined in the same module as the Tool class
        or over all subclasses of Tool.
    """
    for tool_class in iter_subclasses(Tool):
        if same_module_only and tool_class.__module__ != Tool.__module__:
            continue
        yield tool_class


def print_tool_overview() -> None:
    _print_tool_overview(iter_tool_classes())


def _print_tool_overview(tools: Iterable[type[Tool] | Tool]) -> None:
    tool_dict: dict[str, type[Tool] | Tool] = {}
    for tool in tools:
        tool_dict[tool.get_name()] = tool
    for tool_name in sorted(tool_dict.keys()):
        tool = tool_dict[tool_name]
        print(f" * `{tool_name}`: {tool.get_tool_description().strip()}")


def _tuple_to_info(name: str, symbol_type: SymbolKind, line: int, column: int) -> dict[str, int | str]:
    return {"name": name, "symbol_kind": symbol_type, "line": line, "column": column}
