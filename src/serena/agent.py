"""
The Serena Model Context Protocol (MCP) Server
"""

import inspect
import json
import os
import platform
import shutil
import sys
import traceback
import webbrowser
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Sequence
from copy import copy, deepcopy
from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import cached_property
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, TypeVar, Union

import yaml
from overrides import override
from ruamel.yaml.comments import CommentedMap
from sensai.util import logging
from sensai.util.logging import FallbackHandler
from sensai.util.string import ToStringMixin, dict_string

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_types import SymbolKind
from serena import serena_root_path, serena_version
from serena.config import SerenaAgentContext, SerenaAgentMode
from serena.constants import PROJECT_TEMPLATE_FILE, SERENA_MANAGED_DIR_NAME
from serena.dashboard import MemoryLogHandler, SerenaDashboardAPI
from serena.prompt_factory import PromptFactory, SerenaPromptFactory
from serena.symbol import SymbolLocation, SymbolManager
from serena.text_utils import search_files
from serena.util.file_system import scan_directory
from serena.util.general import load_yaml, save_yaml
from serena.util.inspection import determine_programming_language_composition, iter_subclasses
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


def get_serena_managed_dir(project_root: str | Path) -> str:
    return os.path.join(project_root, SERENA_MANAGED_DIR_NAME)


@dataclass
class ProjectConfig(ToStringMixin):
    project_name: str
    language: Language
    ignored_paths: list[str] = field(default_factory=list)
    excluded_tools: set[str] = field(default_factory=set)
    read_only: bool = False
    ignore_all_files_in_gitignore: bool = True
    initial_prompt: str = ""

    SERENA_DEFAULT_PROJECT_FILE = "project.yml"

    @classmethod
    def autogenerate(cls, project_root: str | Path, project_name: str | None = None, save_to_disk: bool = True) -> Self:
        """
        Autogenerate a project configuration for a given project root.

        :param project_root: the path to the project root
        :param project_name: the name of the project; if None, the name of the project will be the name of the directory
            containing the project
        :param save_to_disk: whether to save the project configuration to disk
        :return: the project configuration
        """
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_name = project_name or project_root.name
        language_composition = determine_programming_language_composition(str(project_root))
        if len(language_composition) == 0:
            raise ValueError(
                f"Failed to autogenerate project.yaml: no programming language detected in project {project_root}. "
                f"You can either add some files that correspond to one of the supported programming languages, "
                f"or create the file {os.path.join(project_root, cls.rel_path_to_project_yml())} manually and specify the language there."
            )
        # find the language with the highest percentage
        dominant_language = max(language_composition.keys(), key=lambda lang: language_composition[lang])
        config_with_comments = load_yaml(PROJECT_TEMPLATE_FILE, preserve_comments=True)
        config_with_comments["project_name"] = project_name
        config_with_comments["language"] = dominant_language
        if save_to_disk:
            save_yaml(str(project_root / cls.rel_path_to_project_yml()), config_with_comments, preserve_comments=True)
        return cls._from_yml_data(config_with_comments)

    @classmethod
    def rel_path_to_project_yml(cls) -> str:
        return os.path.join(SERENA_MANAGED_DIR_NAME, cls.SERENA_DEFAULT_PROJECT_FILE)

    @classmethod
    def _from_yml_data(cls, yaml_data: dict[str, Any]) -> Self:
        """
        Create a ProjectConfig instance from a configuration dictionary
        """
        try:
            yaml_data["language"] = Language(yaml_data["language"].lower())
        except ValueError as e:
            raise ValueError(f"Invalid language: {yaml_data['language']}.\nValid languages are: {[l.value for l in Language]}") from e
        return cls(
            project_name=yaml_data["project_name"],
            language=yaml_data["language"],
            ignored_paths=yaml_data.get("ignored_paths", []),
            excluded_tools=set(yaml_data.get("excluded_tools", [])),
            read_only=yaml_data.get("read_only", False),
            ignore_all_files_in_gitignore=yaml_data.get("ignore_all_files_in_gitignore", True),
            initial_prompt=yaml_data.get("initial_prompt", ""),
        )

    @classmethod
    def load(cls, project_root: Path | str) -> Self:
        """
        Load a ProjectConfig instance from the path to the project root.
        """
        project_root = Path(project_root)
        yaml_path = project_root / cls.rel_path_to_project_yml()
        if not yaml_path.exists():
            raise FileNotFoundError(f"Project configuration file not found: {yaml_path}")
        with open(yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        if "project_name" not in yaml_data:
            yaml_data["project_name"] = project_root.name
        return cls._from_yml_data(yaml_data)

    def get_excluded_tool_classes(self) -> set[type["Tool"]]:
        return set(ToolRegistry.get_tool_class_by_name(tool_name) for tool_name in self.excluded_tools)


@dataclass
class Project:
    project_root: str
    project_config: ProjectConfig

    @property
    def project_name(self) -> str:
        return self.project_config.project_name

    @property
    def language(self) -> Language:
        return self.project_config.language

    @classmethod
    def load(cls, project_root: str | Path) -> Self:
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_config = ProjectConfig.load(project_root)
        return cls(project_root=str(project_root), project_config=project_config)

    def path_to_project_yml(self) -> str:
        return os.path.join(self.project_root, self.project_config.rel_path_to_project_yml())


@dataclass(kw_only=True)
class SerenaConfigBase(ABC):
    """
    Abstract base class for Serena configuration handling
    """

    projects: list[Project] = field(default_factory=list)
    gui_log_window_enabled: bool = False
    gui_log_window_level: int = logging.INFO
    web_dashboard: bool = True

    @cached_property
    def project_paths(self) -> list[str]:
        return sorted(project.project_root for project in self.projects)

    @cached_property
    def project_names(self) -> list[str]:
        return sorted(project.project_config.project_name for project in self.projects)

    def get_project(self, project_root_or_name: str) -> Project | None:
        for project in self.projects:
            if project.project_config.project_name == project_root_or_name:
                return project
        if os.path.isdir(project_root_or_name):
            project_root = Path(project_root_or_name).resolve()
            for project in self.projects:
                if Path(project.project_root).resolve() == project_root:
                    return project
        return None

    def add_project_from_path(self, project_root: Path | str, project_name: str | None = None) -> tuple[Project, bool]:
        """
        Add a project to the Serena configuration from a given path. Will raise a FileExistsError if the
        name or path is already registered.

        :param project_root: the path to the project to add
        :param project_name: the name of the project to add; if None, the name of the project will be the name of the directory
            containing the project
        :return: the project that was added and a boolean indicating whether a new project configuration was generated and
            saved to disk. It may be that no new project configuration was generated if the project configuration already
            exists on disk but the project itself was not added yet to the Serena configuration.
        """
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Error: Path does not exist: {project_root}")
        if not project_root.is_dir():
            raise FileNotFoundError(f"Error: Path is not a directory: {project_root}")

        if project_name is None:
            project_name = project_root.name
        for already_registered_project in self.projects:
            if already_registered_project.project_name == project_name:
                raise FileExistsError(
                    f"Project name '{project_name}' already exists and points to {already_registered_project.project_root}."
                )
            if str(already_registered_project.project_root) == str(project_root):
                raise FileExistsError(
                    f"Project with path {project_root} was already added with name '{already_registered_project.project_name}'."
                )

        try:
            project_config = ProjectConfig.load(project_root)
            new_project_config_generated = False
        except FileNotFoundError:
            project_config = ProjectConfig.autogenerate(project_root, save_to_disk=True)
            new_project_config_generated = True

        new_project = Project(project_root=str(project_root), project_config=project_config)
        self._add_new_project(new_project)

        return new_project, new_project_config_generated

    def _add_new_project(self, project: Project) -> None:
        """
        Adds a new project to the Serena configuration. No checks are performed here,
        this method is intended to be overridden by subclasses.
        """
        self.projects.append(project)

    def remove_project(self, project_name: str) -> None:
        # find the index of the project with the desired name and remove it
        for i, project in enumerate(self.projects):
            if project.project_name == project_name:
                del self.projects[i]
                break
        else:
            raise ValueError(f"Project '{project_name}' not found in Serena configuration; valid project names: {self.project_names}")


@dataclass(kw_only=True)
class SerenaConfig(SerenaConfigBase):
    """
    Handles user-defined Serena configuration based on the (fixed) Serena configuration file.
    Updates to the instance will be automatically saved to the configuration file.
    Usually, there should be only one instance of this class in the application.
    """

    loaded_commented_yaml: CommentedMap

    CONFIG_FILE = "serena_config.yml"

    @classmethod
    def get_config_file_path(cls) -> str:
        return os.path.join(serena_root_path(), cls.CONFIG_FILE)

    @classmethod
    def from_config_file(cls) -> "SerenaConfig":
        """
        Static constructor to create SerenaConfig from the configuration file
        """
        config_file = cls.get_config_file_path()
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Serena configuration file not found: {config_file}")

        log.info(f"Loading Serena configuration from {config_file}")
        try:
            loaded_commented_yaml = load_yaml(config_file, preserve_comments=True)
        except Exception as e:
            raise ValueError(f"Error loading Serena configuration from {config_file}: {e}") from e

        # Create instance
        instance = cls(loaded_commented_yaml=loaded_commented_yaml)

        # read projects
        if "projects" not in loaded_commented_yaml:
            raise SerenaConfigError("`projects` key not found in Serena configuration. Please update your `serena_config.yml` file.")

        # load list of known projects
        instance.projects = []
        num_project_migrations = 0
        for path in loaded_commented_yaml["projects"]:
            path = Path(path).resolve()
            if not path.exists() or (path.is_dir() and not (path / ProjectConfig.rel_path_to_project_yml()).exists()):
                log.warning(f"Project path {path} does not exist or does not contain a project configuration file, skipping.")
                continue
            if path.is_file():
                path = cls._migrate_out_of_project_config_file(path)
                if path is None:
                    continue
                num_project_migrations += 1
            project = Project.load(path)
            instance.projects.append(project)

        instance.gui_log_window_enabled = loaded_commented_yaml.get("gui_log_window", False)
        instance.gui_log_window_level = loaded_commented_yaml.get("gui_log_level", logging.INFO)
        instance.web_dashboard = loaded_commented_yaml.get("web_dashboard", True)

        # re-save the configuration file if any migrations were performed
        if num_project_migrations > 0:
            log.info(
                f"Migrated {num_project_migrations} project configurations from legacy format to in-project configuration; re-saving configuration"
            )
            instance.save()

        return instance

    @classmethod
    def _migrate_out_of_project_config_file(cls, path: Path) -> Path | None:
        """
        Migrates a legacy project configuration file (which is a YAML file containing the project root) to the
        in-project configuration file (project.yml) inside the project root directory.

        :param path: the path to the legacy project configuration file
        :return: the project root path if the migration was successful, None otherwise.
        """
        log.info(f"Found legacy project configuration file {path}, migrating to in-project configuration.")
        try:
            with open(path, encoding="utf-8") as f:
                project_config_data = yaml.safe_load(f)
            if "project_name" not in project_config_data:
                project_name = path.stem
                with open(path, "a", encoding="utf-8") as f:
                    f.write(f"\nproject_name: {project_name}")
            project_root = project_config_data["project_root"]
            shutil.move(str(path), str(Path(project_root) / ProjectConfig.rel_path_to_project_yml()))
            return Path(project_root).resolve()
        except Exception as e:
            log.error(f"Error migrating configuration file: {e}")
            return None

    def save(self) -> None:
        loaded_original_yaml = deepcopy(self.loaded_commented_yaml)
        # projects are unique absolute paths
        # we also canonicalize them before saving
        loaded_original_yaml["projects"] = sorted({str(Path(project.project_root).resolve()) for project in self.projects})
        save_yaml(self.get_config_file_path(), loaded_original_yaml, preserve_comments=True)

    @override
    def _add_new_project(self, project: Project) -> None:
        super()._add_new_project(project)
        self.save()

    @override
    def remove_project(self, project_name: str) -> None:
        super().remove_project(project_name)
        self.save()


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
        return [f.name for f in self._memory_dir.iterdir() if f.is_file()]

    def delete_memory(self, name: str) -> str:
        memory_file_path = self._get_memory_file_path(name)
        memory_file_path.unlink()
        return f"Memory {name} deleted."


class SerenaAgent:
    def __init__(
        self,
        project: str | None = None,
        project_activation_callback: Callable[[], None] | None = None,
        serena_config: SerenaConfigBase | None = None,
        context: SerenaAgentContext | None = None,
        modes: list[SerenaAgentMode] | None = None,
    ):
        """
        :param project: the project to load immediately or None to not load any project; may be a path to the project or a name of
            an already registered project;
        :param project_activation_callback: a callback function to be called when a project is activated.
        :param context: the context in which the agent is operating, None for default context.
            The context may adjust prompts, tool availability, and tool descriptions.
        :param modes: list of modes in which the agent is operating (they will be combined), None for default modes.
            The modes may adjust prompts, tool availability, and tool descriptions.
        :param serena_config: the Serena configuration or None to read the configuration from the default location.
        """
        # obtain serena configuration
        self.serena_config = serena_config or SerenaConfig.from_config_file()

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
                self._gui_log_handler = GuiLogViewerHandler(
                    GuiLogViewer("dashboard", title="Serena Logs"), level=log_level, format_string=LOG_FORMAT
                )
                Logger.root.addHandler(self._gui_log_handler)

        # instantiate all tool classes
        self._all_tools: dict[type[Tool], Tool] = {tool_class: tool_class(self) for tool_class in ToolRegistry.get_all_tool_classes()}
        tool_names = [tool.get_name() for tool in self._all_tools.values()]

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_handler is not None:
            self._gui_log_handler.log_viewer.set_tool_names(tool_names)

        # start the dashboard (web frontend), registering its log handler
        if self.serena_config.web_dashboard:
            dashboard_log_handler = MemoryLogHandler()
            Logger.root.addHandler(dashboard_log_handler)
            self._dashboard_thread, port = SerenaDashboardAPI(dashboard_log_handler, tool_names).run_in_thread()
            webbrowser.open(f"http://localhost:{port}/dashboard/index.html")

        log.info(f"Starting Serena server (version={serena_version()}, process id={os.getpid()}, parent process id={os.getppid()})")
        log.info("Available projects: {}".format(", ".join(self.serena_config.project_names)))

        # Initialize the prompt factory
        self.prompt_factory = SerenaPromptFactory()
        self._project_activation_callback = project_activation_callback

        # project-specific instances, which will be initialized upon project activation
        self._active_project: Project | None = None
        self._active_project_root: str | None = None
        self.language_server: SyncLanguageServer | None = None
        self.symbol_manager: SymbolManager | None = None
        self.memories_manager: MemoriesManager | None = None
        self.lines_read: LinesRead | None = None

        # Apply context and mode tool configurations
        if context is None:
            context = SerenaAgentContext.load_default()
        if modes is None:
            modes = SerenaAgentMode.load_default_modes()
        self._context = context
        self._modes = modes
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name() for tool in self._all_tools.values()])}")

        self._active_tools: dict[type[Tool], Tool] = {}
        self._update_active_tools()

        # activate a project configuration (if provided or if there is only a single project available)
        if project is not None:
            try:
                self.activate_project_from_path_or_name(project)
            except Exception as e:
                log.error(
                    f"Error activating project '{project}': {e}; Note that out-of-project configurations were migrated. "
                    "You should now pass either --project <project_name> or --project <project_root>."
                )

    def get_exposed_tool_instances(self) -> list["Tool"]:
        """
        :return: all tool instances, including the non-active ones. For MCP clients, we need to expose them all since typical
            clients don't react to changes in the set of tools.
            An attempt to use a non-active tool will result in an error.
        """
        return list(self._all_tools.values())

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
            excluded_tool_classes.update(mode.get_excluded_tool_classes())
        # context
        excluded_tool_classes.update(self._context.get_excluded_tool_classes())
        # project config
        if self._active_project is not None:
            excluded_tool_classes.update(self._active_project.project_config.get_excluded_tool_classes())
            if self._active_project.project_config.read_only:
                for tool_class in self._all_tools:
                    if tool_class.can_edit():
                        excluded_tool_classes.add(tool_class)

        self._active_tools = {
            tool_class: tool_instance for tool_class, tool_instance in self._all_tools.items() if tool_class not in excluded_tool_classes
        }

        log.info(f"Active tools after all exclusions ({len(self._active_tools)}): {', '.join(self.get_active_tool_names())}")

    def _activate_project(self, project: Project) -> None:
        log.info(f"Activating {project.project_name} at {project.project_root}")
        self._active_project = project
        self._update_active_tools()

        # start the language server
        self.reset_language_server()
        assert self.language_server is not None

        # initialize project-specific instances
        self.symbol_manager = SymbolManager(self.language_server, self)
        self.memories_manager = MemoriesManagerMDFilesInProject(project.project_root)
        self.lines_read = LinesRead()

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
                raise ValueError(
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
        return sorted([tool.get_name() for tool in self.get_active_tool_classes()])

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
        if self._active_project is not None:
            result_str += f"Active project: {self._active_project.project_name}\n"
        else:
            result_str += "No active project\n"
        result_str += "Available projects:\n" + "\n".join(list(self.serena_config.project_names))
        result_str += f"Active context: {self._context.name}\n"

        # Active modes
        active_mode_names = [mode.name for mode in self.get_active_modes()]
        result_str += "Active modes: {}\n".format(", ".join(active_mode_names))

        # Available but not active modes
        all_available_modes = SerenaAgentMode.list_registered_mode_names()
        inactive_modes = [mode for mode in all_available_modes if mode not in active_mode_names]
        if inactive_modes:
            result_str += "Available but not active modes: {}\n".format(", ".join(inactive_modes))

        # Active tools
        result_str += "Active tools (after all exclusions from the project, context, and modes):\n"
        active_tool_names = self.get_active_tool_names()
        # print the tool names in chunks
        chunk_size = 4
        for i in range(0, len(active_tool_names), chunk_size):
            chunk = active_tool_names[i : i + chunk_size]
            result_str += "  " + ", ".join(chunk) + "\n"

        # Available but not active tools
        all_tool_names = sorted([tool.get_name() for tool in self._all_tools.values()])
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
        # stop the language server if it is running
        if self.is_language_server_running():
            log.info("Stopping the language server ...")
            assert self.language_server is not None
            self.language_server.stop()
            self.language_server = None

        # instantiate and start the language server
        assert self._active_project is not None
        multilspy_config = MultilspyConfig(
            code_language=self._active_project.project_config.language, ignored_paths=self._active_project.project_config.ignored_paths
        )
        ls_logger = MultilspyLogger()
        self.language_server = SyncLanguageServer.create(
            multilspy_config,
            ls_logger,
            self._active_project.project_root,
            add_gitignore_content_to_config=self._active_project.project_config.ignore_all_files_in_gitignore,
        )
        self.language_server.start()
        if not self.language_server.is_running():
            raise RuntimeError(
                f"Failed to start the language server for {self._active_project.project_name} at {self._active_project.project_root}"
            )

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
            self.language_server.stop()
        if self._gui_log_handler:
            log.info("Stopping the GUI log window ...")
            self._gui_log_handler.stop_viewer()
            Logger.root.removeHandler(self._gui_log_handler)


class Component(ABC):
    def __init__(self, agent: "SerenaAgent"):
        self.agent = agent

    @property
    def language_server(self) -> SyncLanguageServer:
        assert self.agent.language_server is not None
        return self.agent.language_server

    def get_project_root(self) -> str:
        """
        :return: the root directory of the active project, raises a ValueError if no active project configuration is set
        """
        project_config = self.agent.get_active_project()
        if project_config is None:
            raise ValueError("Cannot get project root if no active project configuration is set.")
        return project_config.project_root

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

    def is_active(self) -> bool:
        return self.agent.tool_is_active(self.__class__)

    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs) -> str:  # type: ignore
        """
        Applies the tool with the given arguments
        """
        apply_fn = self.get_apply_fn()

        try:
            if not self.is_active():
                return f"Error: Tool '{self.get_name()}' is not active. Active tools: {self.agent.get_active_tool_names()}"
        except Exception as e:
            return f"RuntimeError while checking if tool {self.get_name()} is active: {e}"

        if log_call:
            self._log_tool_application(inspect.currentframe())
        try:
            # check whether the tool requires an active project and language server
            if not isinstance(self, ToolMarkerDoesNotRequireActiveProject):
                if self.agent._active_project is None:
                    return (
                        "Error: No active project. Ask to user to select a project from this list: "
                        + f"{self.agent.serena_config.project_names}"
                    )
                if not self.agent.is_language_server_running():
                    log.info("Language server is not running. Starting it ...")
                    self.agent.reset_language_server()
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
        absolute_path = os.path.join(self.get_project_root(), relative_path)
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
            rel_path = os.path.relpath(abs_path, self.get_project_root())
            return self.language_server.is_ignored_path(rel_path, ignore_unsupported_files=False)

        dirs, files = scan_directory(
            os.path.join(self.get_project_root(), relative_path),
            relative_to=self.get_project_root(),
            recursive=recursive,
            is_ignored_dir=is_ignored_path,
            is_ignored_file=is_ignored_path,
        )

        result = json.dumps({"dirs": dirs, "files": files})
        return self._limit_length(result, max_answer_chars)


class FindFileTool(Tool):
    """
    Finds files in the given relative paths
    """

    def apply(self, file_mask: str, relative_path: str) -> str:
        """
        Finds files matching the given file mask within the given relative path

        :param file_mask: the filename or file mask (using the wildcards * or ?) to search for
        :param relative_path: the relative path to the directory to search in; pass "." to scan the project root
        :return: a JSON object with the list of matching files
        """

        def is_ignored_path(abs_path: str) -> bool:
            rel_path = os.path.relpath(abs_path, self.get_project_root())
            return self.language_server.is_ignored_path(rel_path, ignore_unsupported_files=False)

        def is_ignored_file(abs_path: str) -> bool:
            if is_ignored_path(abs_path):
                return True
            filename = os.path.basename(abs_path)
            is_ignored = not fnmatch(filename, file_mask)
            if not is_ignored:
                is_ignored = not fnmatch(filename, file_mask)
            return is_ignored

        dirs, files = scan_directory(
            os.path.join(self.get_project_root(), relative_path),
            relative_to=self.get_project_root(),
            recursive=True,
            is_ignored_dir=is_ignored_path,
            is_ignored_file=is_ignored_file,
        )

        result = json.dumps({"files": files})
        return result


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
        name_path: str,
        depth: int = 0,
        within_relative_path: str | None = None,
        include_body: bool = False,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        substring_matching: bool = False,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given `name_path`,
        which represents a pattern for the symbol's path within the symbol tree of a single file.
        The returned symbol location can be used for edits or further queries.
        Specify `depth > 0` to retrieve children (e.g., methods of a class).

        The matching behavior is determined by the structure of `name_path`, which can
        either be a simple name (e.g. "method") or a name path like "class/method" (relative name path)
        or "/class/method" (absolute name path). Note that the name path is not a path in the file system
        but rather a path in the symbol tree **within a single file**. Thus, file or directory names should never
        be included in the `name_path`. For restricting the search to a single file or directory,
        the `within_relative_path` parameter should be used instead. The retrieved symbols' `name_path` attribute
        will always be composed of symbol names, never file or directory names.

        Key aspects of the name path matching behavior:
        - Trailing slashes in `name_path` play no role and are ignored.
        - The name of the retrieved symbols will match (either exactly or as a substring)
          the last segment of `name_path`, while other segments will restrict the search to symbols that
          have a desired sequence of ancestors.
        - If there is no starting or intermediate slash in `name_path`, there is no
          restriction on the ancestor symbols. For example, passing `method` will match
          against symbols with name paths like `method`, `class/method`, `class/nested_class/method`, etc.
        - If `name_path` contains a `/` but doesn't start with a `/`, the matching is restricted to symbols
          with the same ancestors as the last segment of `name_path`. For example, passing `class/method` will match against
          `class/method` as well as `nested_class/class/method` but not `method`.
        - If `name_path` starts with a `/`, it will be treated as an absolute name path pattern, meaning
          that the first segment of it must match the first segment of the symbol's name path.
          For example, passing `/class` will match only against top-level symbols like `class` but not against `nested_class/class`.
          Passing `/class/method` will match against `class/method` but not `nested_class/class/method` or `method`.


        :param name_path: The name path pattern to search for, see above for details.
        :param depth: Depth to retrieve descendants (e.g., 1 for class methods/attributes).
        :param within_relative_path: Optional. Restrict search to this file or directory. If None, searches entire codebase.
        :param include_body: If True, include the symbol's source code. Use judiciously.
        :param include_kinds: Optional. List of LSP symbol kind integers to include. (e.g., 5 for Class, 12 for Function).
            Valid kinds: 1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter
        :param exclude_kinds: Optional. List of LSP symbol kind integers to exclude. Takes precedence over `include_kinds`.
        :param substring_matching: If True, use substring matching for the last segment of `name`.
        :param max_answer_chars: Max characters for the JSON result. If exceeded, no content is returned.
        :return: JSON string: a list of symbols (with locations) matching the name.
        """
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbols = self.symbol_manager.find_by_name(
            name_path,
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
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
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbols = self.symbol_manager.find_referencing_symbols(
            SymbolLocation(relative_path, line, column),
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
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

class PatchSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Apply targeted patches to a symbol without requiring the entire symbol body.
    This tool enables token-efficient code editing by accepting only the changed portions of a symbol.
    """

    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        chunks: list[dict],
    ) -> str:
        """
        Apply changes to a symbol using diff chunks.
        
        :param relative_path: Path to the file containing the symbol
        :param line: Symbol start line number
        :param column: Symbol start column
        :param chunks: List of diff chunks, each containing:
                      {
                        "context_before": str | list[str],  # Line(s) before change
                        "old_lines": list[str], # Lines to be replaced/deleted
                        "new_lines": list[str], # Lines to insert/replace with
                        "context_after": str | list[str],   # Line(s) after change
                      }
        :return: Success message or error description
        """
        try:
            # Input validation
            if not chunks or not isinstance(chunks, list):
                return "Error: chunks must be a non-empty list"
            
            for i, chunk in enumerate(chunks):
                required_keys = ["context_before", "old_lines", "new_lines", "context_after"]
                if not all(key in chunk for key in required_keys):
                    return f"Error: chunk {i+1} missing required keys: {required_keys}"
                
                if isinstance(chunk["context_before"], str):
                    chunk["context_before"] = [chunk["context_before"]]
                if isinstance(chunk["context_after"], str):
                    chunk["context_after"] = [chunk["context_after"]]
            
            symbols = self.symbol_manager.get_document_symbols(relative_path)
            
            target_symbol = None
            for symbol in symbols:
                if (symbol.relative_path == relative_path and 
                    symbol.line == line and 
                    symbol.column == column):
                    symbols_with_body = self.symbol_manager.find_by_name(
                        symbol.name,
                        include_body=True,
                        within_relative_path=relative_path
                    )
                    for s in symbols_with_body:
                        if (s.relative_path == relative_path and 
                            s.line == line and 
                            s.column == column):
                            target_symbol = s
                            break
                    break
            
            if target_symbol is None or target_symbol.body is None:
                return "Error: Symbol not found or has no body"
            
            # Apply the chunks atomically
            result = self.apply_chunks_to_symbol(target_symbol.body, chunks)
            
            # Check if it's an error message
            if result.startswith("Error:") or "failed" in result:
                return result
            
            # Replace the symbol body
            symbol_location = SymbolLocation(relative_path, line, column)
            self.symbol_manager.replace_body(symbol_location, result)
            return SUCCESS_RESULT
            
        except Exception as e:
            log.error(f"Error in PatchSymbolTool: {str(e)}", exc_info=e)
            return f"Error applying chunks: {str(e)}"




    def _detect_line_ending(self, text: str) -> str:
        """
        Detect the dominant line ending in text.
        Prioritizes CRLF > LF > CR, with LF as fallback.

        :param text: The text to analyze
        :return: The detected line ending ('\r\n', '\n', or '\r')
        """
        crlf_count = text.count('\r\n')
        lf_count = text.count('\n') - crlf_count
        cr_only_count = text.count('\r') - crlf_count

        if crlf_count > 0 and crlf_count >= lf_count and crlf_count >= cr_only_count:
            return '\r\n'
        elif lf_count > 0 and lf_count >= cr_only_count:
            return '\n'
        elif cr_only_count > 0:
            return '\r'
        else:
            return '\n'

    def _lines_match(self, actual_lines: list[str], expected_lines: list[str]) -> bool:
        """
        Check if lines match, allowing for some flexibility in trailing whitespace.

        :param actual_lines: The actual lines from the file
        :param expected_lines: The expected lines from the chunk
        :return: True if lines match (after rstrip()), False otherwise
        """
        if len(actual_lines) != len(expected_lines):
            return False

        for actual, expected in zip(actual_lines, expected_lines):
            if actual.rstrip() != expected.rstrip():
                return False
        return True

    def _run_comprehensive_validation(self, original_lines: list[str], chunk: dict, position: int, symbol_body: str) -> str | None:
        """
        Run comprehensive validation checks on a chunk.

        :param original_lines: Lines from the original symbol body
        :param chunk: Chunk dictionary with all fields
        :param position: Position of the last line of context_before
        :param symbol_body: Original symbol body string for line ending detection
        :return: None if all checks pass, error message string if any check fails
        """
        context_before_lines = chunk["context_before"] if isinstance(chunk["context_before"], list) else [chunk["context_before"]]
        context_after_lines = chunk["context_after"] if isinstance(chunk["context_after"], list) else [chunk["context_after"]]
        old_lines = chunk["old_lines"] # Assumed to be list by `apply`
        new_lines = chunk["new_lines"] # Assumed to be list by `apply`

        # Check 1: Context After Validation
        # Position is the 0-based index of the last line of context_before.
        # old_lines start at original_lines[position + 1].
        # context_after lines start after old_lines.
        expected_after_start_index = position + 1 + len(old_lines)

        if expected_after_start_index + len(context_after_lines) > len(original_lines):
            # This check means context_after extends beyond the current symbol body.
            # It's only an error if context_after is non-empty. If it's empty, it's fine.
            if len(context_after_lines) > 0 :
                 return f"Check 1 failed: context_after sequence (length {len(context_after_lines)}) starting at line {expected_after_start_index} extends beyond symbol end (total lines {len(original_lines)})"

        # Only validate non-empty context_after
        if len(context_after_lines) > 0:
            actual_context_after_lines = original_lines[expected_after_start_index : expected_after_start_index + len(context_after_lines)]
            if not self._lines_match(actual_context_after_lines, context_after_lines):
                 return f"Check 1 failed: context_after mismatch. Expected {context_after_lines}, got {actual_context_after_lines} at line index {expected_after_start_index}"

        # Check 2: Old Lines Matching
        actual_old_lines_start_index = position + 1
        # Ensure old_lines don't go past end of original_lines
        if actual_old_lines_start_index + len(old_lines) > len(original_lines):
            return f"Check 2 failed: old_lines (length {len(old_lines)}) starting at line index {actual_old_lines_start_index} extend beyond symbol end (total lines {len(original_lines)})"

        if len(old_lines) > 0: # Only match if old_lines is not empty
            actual_old_lines_content = original_lines[actual_old_lines_start_index : actual_old_lines_start_index + len(old_lines)]
            if not self._lines_match(actual_old_lines_content, old_lines):
                return f"Check 2 failed: old_lines don't match actual content. Expected {old_lines}, got {actual_old_lines_content} at line index {actual_old_lines_start_index}"

        # Check 3: Insertion Logic (empty old_lines)
        # If old_lines is empty, it's an insertion. context_before and context_after must be contiguous.
        # expected_after_start_index is position + 1 + len(old_lines). If old_lines is empty, it's position + 1.
        # This means the first line of context_after should be original_lines[position + 1].
        # This check is implicitly covered by Check 1 if context_after is validated correctly relative to position.
        # No specific additional check needed here if Check 1 and 2 are sound.

        # Check 4: Deletion Logic (empty new_lines)
        # If new_lines is empty, it's a deletion. old_lines must exactly match. (Covered by Check 2)
        # No specific additional check needed here.

        # Check 5: Symbol Boundary Validation (overall chunk placement)
        # Chunk is defined by context_before, old_lines, context_after.
        # The critical part is that `old_lines` must be within `original_lines`.
        # `position` is index of last line of `context_before`.
        # `context_before` lines are `original_lines[position - len(context_before_lines) + 1 : position + 1]`
        # `old_lines` are `original_lines[position + 1 : position + 1 + len(old_lines)]`
        # `context_after` are `original_lines[position + 1 + len(old_lines) : position + 1 + len(old_lines) + len(context_after_lines)]`
        # These boundaries are implicitly checked by the matching process and previous checks.
        # Explicit check for `position` itself:
        if position < -1 : # position can be -1 if context_before is empty (insert at beginning)
             return f"Check 5 failed: Invalid position {position} for context_before."
        if position >= len(original_lines):
             return f"Check 5 failed: Position {position} for context_before is outside symbol boundaries (total lines {len(original_lines)})."


        # Check 6: End-of-Symbol Context Validation
        # If context_after is empty, are we truly at the end of what's being replaced by old_lines?
        # Or is there more content in original_lines that context_after *should* have matched?
        # This is effectively asking: if context_after is empty, does original_lines end after old_lines?
        if len(context_after_lines) == 0:
            end_of_old_lines_index = position + 1 + len(old_lines)
            if end_of_old_lines_index < len(original_lines):
                # There's content after old_lines, but context_after was empty.
                # This implies the chunk expects nothing after, but there is something.
                # This might be valid if the LLM intends to delete trailing content by not specifying it.
                # However, for strict diff application, this is a mismatch.
                # Let's consider this a warning or a point of careful consideration.
                # For now, let's flag it if strictness is desired.
                # log.debug(f"Check 6: Empty context_after, but content exists in original from line index {end_of_old_lines_index}")
                pass # This scenario can be valid.

        # Check 7: Line Ending Consistency (Optional, but good for hygiene)
        # This is a more advanced check, ensuring line endings in chunk strings
        # don't introduce mixed line endings if the original file has a consistent one.
        # For simplicity, we might skip this if _detect_line_ending is robustly used during reconstruction.
        # The _detect_line_ending on the whole symbol_body is used for reconstruction.
        # Individual lines in chunks are just strings, their internal newlines are usually not intended.
        # If a chunk line *contains* a newline character, that's unusual for diffs.
        original_body_line_ending = self._detect_line_ending(symbol_body)
        all_chunk_content_lines = []
        if isinstance(chunk["context_before"], list): all_chunk_content_lines.extend(chunk["context_before"])
        else: all_chunk_content_lines.append(chunk["context_before"])
        all_chunk_content_lines.extend(chunk["old_lines"])
        all_chunk_content_lines.extend(chunk["new_lines"])
        if isinstance(chunk["context_after"], list): all_chunk_content_lines.extend(chunk["context_after"])
        else: all_chunk_content_lines.append(chunk["context_after"])

        for line_content in all_chunk_content_lines:
            if isinstance(line_content, str): # Ensure it's a string
                if '\n' in line_content and original_body_line_ending != '\n':
                    if not ('\r\n' in line_content and original_body_line_ending == '\r\n'): # LF in chunk, but original is not LF (and not CRLF if chunk has CRLF)
                        return f"Check 7 failed: Line content '{line_content[:20]}...' contains LF, but symbol body uses {repr(original_body_line_ending)}"
                if '\r' in line_content and not '\n' in line_content and original_body_line_ending != '\r': # CR only in chunk, but original is not CR
                     return f"Check 7 failed: Line content '{line_content[:20]}...' contains CR, but symbol body uses {repr(original_body_line_ending)}"

        return None  # All checks passed

    def _validate_and_position_chunk(self, original_lines: list[str], symbol_body: str, chunk: dict) -> tuple[int | None, str | None]:
        """
        Validate a single chunk and find its position.
        Tests ALL candidate positions with comprehensive validation.

        :param original_lines: Lines from the original symbol body
        :param symbol_body: Original symbol body string for line ending detection
        :param chunk: Chunk dictionary with all fields
        :return: (position, None) if valid, or (None, error_message) if invalid.
                 Position is the 0-based index of the last line of context_before.
                 Returns -1 for position if context_before is empty and it's an insert at the beginning.
        """
        context_before_lines = chunk["context_before"]
        # Ensure context_before_lines is a list
        if isinstance(context_before_lines, str):
            context_before_lines = [context_before_lines]

        candidate_positions = []
        if not context_before_lines: # Empty context_before means insert at the beginning
            candidate_positions.append(-1) # Special position for beginning
        else:
            context_len = len(context_before_lines)
            for i in range(len(original_lines) - context_len + 1):
                # Check if original_lines[i : i + context_len] matches context_before_lines
                segment_to_match = original_lines[i : i + context_len]
                if self._lines_match(segment_to_match, context_before_lines):
                    candidate_positions.append(i + context_len - 1)  # Index of the last line of context_before

        if not candidate_positions:
            return None, f"Context_before ({context_before_lines}) not found in symbol body."

        # Test each candidate position with comprehensive validation
        for position in candidate_positions:
            validation_error = self._run_comprehensive_validation(original_lines, chunk, position, symbol_body)
            if validation_error is None:
                return position, None  # Found a valid position

        return None, f"All {len(candidate_positions)} candidate positions for context_before failed validation. Last error for position {candidate_positions[-1]}: {validation_error if 'validation_error' in locals() else 'unknown'}"


    def apply_chunks_to_symbol(self, symbol_body: str, chunks: list[dict]) -> str:
        """
        Apply multiple chunks to a symbol body atomically with comprehensive validation.
        All chunks are validated before any modifications are applied (atomic operation).

        :param symbol_body: The original symbol body as a string
        :param chunks: List of chunks to apply
        :return: New symbol body string or error message
        """
        original_line_ending = self._detect_line_ending(symbol_body)
        original_lines = symbol_body.splitlines() # Works even if symbol_body is empty

        validated_applications = [] # Store (position, chunk_index, chunk_data)

        # Phase 1: Validate ALL chunks and determine their application points
        for i, chunk in enumerate(chunks):
            # Normalize context and old/new lines within the chunk if not already done
            # (though `apply` method should handle this)
            if isinstance(chunk["context_before"], str): chunk["context_before"] = [chunk["context_before"]]
            if isinstance(chunk["context_after"], str): chunk["context_after"] = [chunk["context_after"]]
            if not isinstance(chunk["old_lines"], list): chunk["old_lines"] = [chunk["old_lines"]] if chunk["old_lines"] else []
            if not isinstance(chunk["new_lines"], list): chunk["new_lines"] = [chunk["new_lines"]] if chunk["new_lines"] else []


            position, error = self._validate_and_position_chunk(original_lines, symbol_body, chunk)
            if error:
                log.error(f"Chunk {i+1} validation failed: {error}")
                return f"Error: Chunk {i+1} (content: {str(chunk)[:100]}...) validation failed: {error}"
            validated_applications.append({'position': position, 'chunk_index': i, 'chunk': chunk})
            log.debug(f"Chunk {i+1} validated successfully, applies after line index {position}.")

        # Phase 2: Apply all validated chunks. Must be done in reverse order of position
        # to ensure line indices remain correct for subsequent patches on the original lines.
        # If multiple chunks affect the same starting position, their original order (chunk_index) should be preserved.
        validated_applications.sort(key=lambda app: (app['position'], app['chunk_index']), reverse=True)

        working_lines = list(original_lines)
        for app_info in validated_applications:
            position = app_info['position']
            chunk = app_info['chunk']
            old_lines = chunk["old_lines"]
            new_lines = chunk["new_lines"]

            # `position` is the index of the last line of context_before.
            # `old_lines` start at `position + 1`.
            start_index_for_old = position + 1
            end_index_for_old = start_index_for_old + len(old_lines)

            # Replace `old_lines` with `new_lines`
            working_lines[start_index_for_old:end_index_for_old] = new_lines

        # Reconstruct body with original line ending
        new_body = original_line_ending.join(working_lines)

        # Preserve trailing newline if original body had one and new_body doesn't (and vice-versa if needed)
        original_had_trailing_newline = symbol_body.endswith(original_line_ending) if symbol_body else False # Handle empty symbol_body
        new_has_trailing_newline = new_body.endswith(original_line_ending) if new_body else False

        if original_had_trailing_newline and not new_has_trailing_newline and new_body: # Add if missing and new_body not empty
            new_body += original_line_ending
        elif not original_had_trailing_newline and new_has_trailing_newline: # Remove if added and original didn't have it
             if new_body == original_line_ending: # If new_body is ONLY a line ending
                 new_body = ""
             else:
                 new_body = new_body[:-len(original_line_ending)]


        return new_body


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
        """
        list_memories_tool = self.agent.get_tool(ListMemoriesTool)
        memories = json.loads(list_memories_tool.apply())
        if len(memories) == 0:
            return (
                "Onboarding not performed yet (no memories available). "
                + "You should perform onboarding by calling the `onboarding` tool before proceeding with the task."
            )
        else:
            return f"""The onboarding was already performed, below is the list of available memories.
            Do not read them immediately, just remember that they exist and that you can read them later, if it is necessary
            for the current task.
            Some memories may be based on previous conversations, others may be general for the current project.
            You should be able to tell which one you need based on the name of the memory.
            
            {memories}"""


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
            for root, dirs, files in os.walk(self.get_project_root()):
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
        _cwd = cwd or self.get_project_root()
        result = execute_shell_command(command, cwd=_cwd, capture_stderr=capture_stderr)
        result = result.json()
        return self._limit_length(result, max_answer_chars)


class ActivateProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Activates a project by name.
    """

    def apply(self, project: str) -> str:
        """
        Activates the project with the given name.

        :param project: the name of a registered project to activate or a path to a project directory
        """
        active_project, new_project_generated, new_project_config_generated = self.agent.activate_project_from_path_or_name(project)
        if new_project_generated:
            result_str = (
                f"Created and activated a new project with name {active_project.project_name} at {active_project.project_root}, language: {active_project.project_config.language.value}. "
                + "You can activate this project later by name."
            )
        else:
            result_str = f"Activated existing project with name {active_project.project_name} at {active_project.project_root}, language: {active_project.project_config.language.value}"
        if new_project_config_generated:
            result_str += (
                f"\nNote: A new project configuration was autogenerated because the given path did not contain a {ProjectConfig.SERENA_DEFAULT_PROJECT_FILE} file."
                + f"You can now edit the project configuration in the file {active_project.path_to_project_yml()}. In particular, you may want to edit the project name and the initial prompt."
            )

        if active_project.project_config.initial_prompt:
            result_str += f"\nAdditional project information:\n {active_project.project_config.initial_prompt}"
        result_str += (
            f"\nAvailable memories:\n {json.dumps(list(self.memories_manager.list_memories()))}"
            + "You should not read these memories directly, but rather use the `read_memory` tool to read them later if needed for the task."
        )
        result_str += f"\nAvailable tools:\n {json.dumps(self.agent.get_active_tool_names())}"
        return result_str


class RemoveProjectTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Removes a project from the Serena configuration.
    """

    def apply(self, project_name: str) -> str:
        """
        Removes a project from the Serena configuration.

        :param project_name: Name of the project to remove
        """
        self.agent.serena_config.remove_project(project_name)
        return f"Successfully removed project '{project_name}' from configuration."


class SwitchModesTool(Tool):
    """
    Activates modes by providing a list of their names
    """

    def apply(self, modes: list[str]) -> str:
        """
        Activates the desired modes, like ["editing", "interactive"] or ["planning", "one-shot"]

        :param modes: the names of the modes to activate
        """
        mode_instances = [SerenaAgentMode.load(mode) for mode in modes]
        self.agent.set_modes(mode_instances)

        # Inform the Agent about the activated modes and the currently active tools
        result_str = f"Successfully activated modes: {', '.join([mode.name for mode in mode_instances])}" + "\n"
        result_str += "\n".join([mode_instance.prompt for mode_instance in mode_instances]) + "\n"
        result_str += f"Currently active tools: {', '.join(self.agent.get_active_tool_names())}"
        return result_str


class GetCurrentConfigTool(Tool):
    """
    Prints the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
    """

    def apply(self) -> str:
        """
        Print the current configuration of the agent, including the active and available projects, tools, contexts, and modes.
        """
        return self.agent.get_current_config_overview()


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
        return self.agent.create_system_prompt()


def _iter_tool_classes(same_module_only: bool = True) -> Generator[type[Tool], None, None]:
    """
    Iterate over Tool subclasses.

    :param same_module_only: Whether to only iterate over tools defined in the same module as the Tool class
        or over all subclasses of Tool.
    """
    for tool_class in iter_subclasses(Tool):
        if same_module_only and tool_class.__module__ != Tool.__module__:
            continue
        yield tool_class


_TOOL_REGISTRY_DICT: dict[str, type[Tool]] = {tool_class.get_name(): tool_class for tool_class in _iter_tool_classes()}
"""maps tool name to the corresponding tool class"""


class ToolRegistry:
    @staticmethod
    def get_tool_class_by_name(tool_name: str) -> type[Tool]:
        try:
            return _TOOL_REGISTRY_DICT[tool_name]
        except KeyError as e:
            available_tools = "\n".join(ToolRegistry.get_tool_names())
            raise ValueError(f"Tool with name {tool_name} not found. Available tools:\n{available_tools}") from e

    @staticmethod
    def get_all_tool_classes() -> list[type[Tool]]:
        return list(_TOOL_REGISTRY_DICT.values())

    @staticmethod
    def get_tool_names() -> list[str]:
        return list(_TOOL_REGISTRY_DICT.keys())

    @staticmethod
    def tool_dict() -> dict[str, type[Tool]]:
        """Maps tool name to the corresponding tool class"""
        return copy(_TOOL_REGISTRY_DICT)

    @staticmethod
    def print_tool_overview(tools: Iterable[type[Tool] | Tool] | None = None) -> None:
        """
        Print a summary of the tools. If no tools are passed, a summary of all tools is printed.
        """
        if tools is None:
            tools = _TOOL_REGISTRY_DICT.values()

        tool_dict: dict[str, type[Tool] | Tool] = {}
        for tool_class in tools:
            tool_dict[tool_class.get_name()] = tool_class
        for tool_name in sorted(tool_dict.keys()):
            tool_class = tool_dict[tool_name]
            print(f" * `{tool_name}`: {tool_class.get_tool_description().strip()}")


def _tuple_to_info(name: str, symbol_type: SymbolKind, line: int, column: int) -> dict[str, int | str]:
    return {"name": name, "symbol_kind": symbol_type, "line": line, "column": column}
