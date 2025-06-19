"""
The Serena Model Context Protocol (MCP) Server
"""

import inspect
import json
import os
import platform
import re
import shutil
import sys
import traceback
import webbrowser
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Sequence
from copy import copy, deepcopy
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from functools import cached_property
from logging import Logger
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, Self, TypeVar, Union, cast

import click
import yaml
from mcp.server.fastmcp.utilities.func_metadata import FuncMetadata, func_metadata
from overrides import override
from pathspec import PathSpec
from ruamel.yaml.comments import CommentedMap
from sensai.util import logging
from sensai.util.logging import LOG_DEFAULT_FORMAT, FallbackHandler
from sensai.util.string import ToStringMixin, dict_string

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_types import SymbolKind
from serena import serena_version
from serena.config import SerenaAgentContext, SerenaAgentMode
from serena.constants import PROJECT_TEMPLATE_FILE, REPO_ROOT, SELENA_CONFIG_TEMPLATE_FILE, SERENA_MANAGED_DIR_NAME
from serena.dashboard import MemoryLogHandler, SerenaDashboardAPI
from serena.prompt_factory import PromptFactory, SerenaPromptFactory
from serena.symbol import SymbolManager
from serena.text_utils import search_files
from serena.util.file_system import GitignoreParser, match_path, scan_directory
from serena.util.general import load_yaml, save_yaml
from serena.util.inspection import determine_programming_language_composition, iter_subclasses
from serena.util.shell import execute_shell_command
from serena.util.thread import ExecutionResult, execute_with_timeout

if TYPE_CHECKING:
    from serena.gui_log_viewer import GuiLogViewerHandler

log = logging.getLogger(__name__)
LOG_FORMAT = "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s"
TTool = TypeVar("TTool", bound="Tool")
SUCCESS_RESULT = "OK"
DEFAULT_TOOL_TIMEOUT: float = 240


def _sanitize_symbol_dict(symbol_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize a symbol dictionary inplace by removing unnecessary information.
    """
    # We replace the location entry, which repeats line information already included in body_location
    # and has unnecessary information on column, by just the relative path.
    symbol_dict = copy(symbol_dict)
    s_relative_path = symbol_dict.get("location", {}).get("relative_path")
    if s_relative_path is not None:
        symbol_dict["relative_path"] = s_relative_path
    symbol_dict.pop("location", None)
    # also remove name, name_path should be enough
    symbol_dict.pop("name")
    return symbol_dict


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


def get_serena_managed_dir(project_root: str | Path, custom_serena_dir: str | None = None) -> str:
    if custom_serena_dir is not None:
        return str(Path(custom_serena_dir).resolve())
    return os.path.join(project_root, SERENA_MANAGED_DIR_NAME)


def is_running_in_docker() -> bool:
    """Check if we're running inside a Docker container."""
    # Check for Docker-specific files
    if os.path.exists("/.dockerenv"):
        return True
    # Check cgroup for docker references
    try:
        with open("/proc/self/cgroup") as f:
            return "docker" in f.read()
    except FileNotFoundError:
        return False


@dataclass
class ProjectConfig(ToStringMixin):
    project_name: str
    language: Language
    ignored_paths: list[str] = field(default_factory=list)
    excluded_tools: set[str] = field(default_factory=set)
    read_only: bool = False
    ignore_all_files_in_gitignore: bool = True
    initial_prompt: str = ""
    encoding: str = "utf-8"

    SERENA_DEFAULT_PROJECT_FILE = "project.yml"

    @classmethod
    def autogenerate(
        cls, project_root: str | Path, project_name: str | None = None, save_to_disk: bool = True, serena_config_dir: str | None = None
    ) -> Self:
        """
        Autogenerate a project configuration for a given project root.

        :param project_root: the path to the project root
        :param project_name: the name of the project; if None, the name of the project will be the name of the directory
            containing the project
        :param save_to_disk: whether to save the project configuration to disk
        :param serena_config_dir: custom path for the .serena directory
        :return: the project configuration
        """
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_name = project_name or project_root.name
        language_composition = determine_programming_language_composition(str(project_root))
        if len(language_composition) == 0:
            config_path = serena_config_dir if serena_config_dir else str(project_root / cls.rel_path_to_project_yml())
            raise ValueError(
                f"Failed to autogenerate project.yaml: no programming language detected in project {project_root}. "
                f"You can either add some files that correspond to one of the supported programming languages, "
                f"or create the file {config_path} manually and specify the language there."
            )
        # find the language with the highest percentage
        dominant_language = max(language_composition.keys(), key=lambda lang: language_composition[lang])
        config_with_comments = load_yaml(PROJECT_TEMPLATE_FILE, preserve_comments=True)
        config_with_comments["project_name"] = project_name
        config_with_comments["language"] = dominant_language
        if save_to_disk:
            if serena_config_dir is not None:
                config_path_obj = Path(serena_config_dir) / cls.SERENA_DEFAULT_PROJECT_FILE
                # Ensure the custom directory exists
                config_path_obj.parent.mkdir(parents=True, exist_ok=True)
                config_path = str(config_path_obj)
            else:
                config_path_obj = project_root / cls.rel_path_to_project_yml()
                # Ensure the .serena directory exists
                config_path_obj.parent.mkdir(parents=True, exist_ok=True)
                config_path = str(config_path_obj)
            save_yaml(str(config_path), config_with_comments, preserve_comments=True)
        return cls.from_json_dict(config_with_comments)

    @classmethod
    def rel_path_to_project_yml(cls, custom_serena_dir: str | None = None) -> str:
        if custom_serena_dir is not None:
            return os.path.join(custom_serena_dir, cls.SERENA_DEFAULT_PROJECT_FILE)
        return os.path.join(SERENA_MANAGED_DIR_NAME, cls.SERENA_DEFAULT_PROJECT_FILE)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> Self:
        """
        Create a ProjectConfig instance from a configuration dictionary
        """
        data = copy(data)
        try:
            data["language"] = Language(data["language"].lower())
        except ValueError as e:
            raise ValueError(f"Invalid language: {data['language']}.\nValid languages are: {[l.value for l in Language]}") from e
        return cls(**data)

    def to_json_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["language"] = result["language"].value
        result["excluded_tools"] = list(result["excluded_tools"])
        return result

    @classmethod
    def load(cls, project_root: Path | str, autogenerate: bool = True, serena_config_dir: str | None = None) -> Self:
        """
        Load a ProjectConfig instance from the path to the project root.
        """
        project_root = Path(project_root)
        if serena_config_dir is not None:
            yaml_path = Path(serena_config_dir) / cls.SERENA_DEFAULT_PROJECT_FILE
        else:
            yaml_path = project_root / cls.rel_path_to_project_yml()

        if not yaml_path.exists():
            if autogenerate:
                return cls.autogenerate(project_root, serena_config_dir=serena_config_dir)
            else:
                raise FileNotFoundError(f"Project configuration file not found: {yaml_path}")
        with open(yaml_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        if "project_name" not in yaml_data:
            yaml_data["project_name"] = project_root.name
        return cls.from_json_dict(yaml_data)

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
    def load(cls, project_root: str | Path, autogenerate: bool = True, serena_config_dir: str | None = None) -> Self:
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_config = ProjectConfig.load(project_root, autogenerate=autogenerate, serena_config_dir=serena_config_dir)
        return cls(project_root=str(project_root), project_config=project_config)

    @classmethod
    def from_json_dict(cls, data: dict) -> Self:
        return cls(project_root=data["project_root"], project_config=ProjectConfig.from_json_dict(data["project_config"]))

    def to_json_dict(self) -> dict:
        return {"project_root": self.project_root, "project_config": self.project_config.to_json_dict()}

    def path_to_project_yml(self, custom_serena_dir: str | None = None) -> str:
        if custom_serena_dir is not None:
            return str(Path(custom_serena_dir) / ProjectConfig.SERENA_DEFAULT_PROJECT_FILE)
        return os.path.join(self.project_root, self.project_config.rel_path_to_project_yml())


@dataclass(kw_only=True)
class SerenaConfigBase(ABC):
    """
    Abstract base class for Serena configuration handling
    """

    projects: list[Project] = field(default_factory=list)
    gui_log_window_enabled: bool = False
    log_level: int = logging.INFO
    trace_lsp_communication: bool = False
    web_dashboard: bool = True
    tool_timeout: float = DEFAULT_TOOL_TIMEOUT

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

    def to_json_dict(self) -> dict:
        """Convert configuration to dictionary for serialization."""
        result = asdict(self)
        result["projects"] = [project.to_json_dict() for project in self.projects]
        return result

    @classmethod
    def from_json_dict(cls, data: dict) -> Self:
        """Create configuration from dictionary."""
        data = copy(data)
        data["projects"] = [Project.from_json_dict(project_data) for project_data in data["projects"]]
        return cls(**data)


@dataclass(kw_only=True)
class SerenaConfig(SerenaConfigBase):
    """
    Handles user-defined Serena configuration based on the (fixed) Serena configuration file.
    Updates to the instance will be automatically saved to the configuration file.
    Usually, there should be only one instance of this class in the application.
    """

    loaded_commented_yaml: CommentedMap

    CONFIG_FILE = "serena_config.yml"
    CONFIG_FILE_DOCKER = "serena_config.docker.yml"  # Docker-specific config file; auto-generated if missing, mounted via docker-compose for user customization

    @classmethod
    def autogenerate(cls) -> None:
        log.info("Autogenerating Serena configuration file")
        if os.path.exists(cls.get_config_file_path()):
            raise FileExistsError(
                f"Serena configuration file already exists at {cls.get_config_file_path()}. Please remove it if you want to autogenerate a new one."
            )
        loaded_commented_yaml = load_yaml(SELENA_CONFIG_TEMPLATE_FILE, preserve_comments=True)
        save_yaml(cls.get_config_file_path(), loaded_commented_yaml, preserve_comments=True)

    @classmethod
    def get_config_file_path(cls) -> str:
        config_file = cls.CONFIG_FILE_DOCKER if is_running_in_docker() else cls.CONFIG_FILE
        return os.path.join(REPO_ROOT, config_file)

    @classmethod
    def _load_commented_yaml(cls, config_file: str, generate_if_missing: bool = True) -> CommentedMap:
        if not os.path.exists(config_file):
            if not generate_if_missing:
                raise FileNotFoundError(f"Serena configuration file not found: {config_file}")
            log.info(f"Serena configuration file not found at {config_file}, autogenerating...")
            cls.autogenerate()
        try:
            return load_yaml(config_file, preserve_comments=True)
        except Exception as e:
            raise ValueError(f"Error loading Serena configuration from {config_file}: {e}") from e

    @classmethod
    def from_config_file(cls, generate_if_missing: bool = True) -> "SerenaConfig":
        """
        Static constructor to create SerenaConfig from the configuration file
        """
        config_file = cls.get_config_file_path()
        log.info(f"Loading Serena configuration from {config_file}")
        loaded_commented_yaml = cls._load_commented_yaml(config_file, generate_if_missing)
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

        # Force disable GUI in Docker environment
        if is_running_in_docker():
            instance.gui_log_window_enabled = False
        else:
            instance.gui_log_window_enabled = loaded_commented_yaml.get("gui_log_window", False)
        instance.log_level = loaded_commented_yaml.get("log_level", loaded_commented_yaml.get("gui_log_level", logging.INFO))
        instance.web_dashboard = loaded_commented_yaml.get("web_dashboard", True)
        instance.tool_timeout = loaded_commented_yaml.get("tool_timeout", DEFAULT_TOOL_TIMEOUT)
        instance.trace_lsp_communication = loaded_commented_yaml.get("trace_lsp_communication", False)

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

    def to_json_dict(self) -> dict:
        result = super().to_json_dict()
        result.pop("loaded_commented_yaml", None)
        return result

    @classmethod
    def from_json_dict(cls, data: dict) -> Self:
        data["loaded_commented_yaml"] = cls._load_commented_yaml(cls.get_config_file_path())
        return super().from_json_dict(data)


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
    def __init__(self, project_root: str, custom_serena_dir: str | None = None):
        self._memory_dir = Path(get_serena_managed_dir(project_root, custom_serena_dir)) / "memories"
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


def create_serena_config(
    serena_config: SerenaConfigBase | None = None,
    enable_web_dashboard: bool | None = None,
    enable_gui_log_window: bool | None = None,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
    trace_lsp_communication: bool | None = None,
    tool_timeout: float | None = None,
) -> SerenaConfig:
    """
    Create a SerenaConfig instance without instantiating a full SerenaAgent.

    This function extracts the configuration creation logic from SerenaAgent.__init__
    to allow creating configurations independently for process isolation and other use cases.

    :param serena_config: the base Serena configuration or None to read from default location
    :param enable_web_dashboard: Whether to enable the web dashboard
    :param enable_gui_log_window: Whether to enable the GUI log window
    :param log_level: Log level
    :param trace_lsp_communication: Whether to trace LSP communication
    :param tool_timeout: Timeout in seconds for tool execution
    :return: A fully configured SerenaConfig instance
    """
    # obtain serena configuration
    if serena_config is not None:
        # If a complete SerenaConfig is provided, use it directly
        if isinstance(serena_config, SerenaConfig):
            config = serena_config
        else:
            # For SerenaConfigBase instances (like test configs), create an in-memory SerenaConfig
            # that preserves the base config attributes without loading from file
            from ruamel.yaml.comments import CommentedMap

            config = SerenaConfig.__new__(SerenaConfig)  # Create without calling __init__
            # Initialize basic attributes from base config
            config.projects = getattr(serena_config, "projects", [])
            config.gui_log_window_enabled = serena_config.gui_log_window_enabled
            config.log_level = serena_config.log_level
            config.trace_lsp_communication = serena_config.trace_lsp_communication
            config.web_dashboard = serena_config.web_dashboard
            config.tool_timeout = serena_config.tool_timeout
            # Set empty yaml for in-memory config
            config.loaded_commented_yaml = CommentedMap()
    else:
        config = SerenaConfig.from_config_file()

    # Apply parameter overrides
    if enable_web_dashboard is not None:
        config.web_dashboard = enable_web_dashboard
    if enable_gui_log_window is not None:
        config.gui_log_window_enabled = enable_gui_log_window
    if log_level is not None:
        log_level = cast(Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], log_level.upper())
        # transform to int
        config.log_level = logging.getLevelNamesMapping()[log_level]
    if trace_lsp_communication is not None:
        config.trace_lsp_communication = trace_lsp_communication
    if tool_timeout is not None:
        config.tool_timeout = tool_timeout

    # Note: Project registration/activation is handled separately by the caller
    # since it involves complex logic that may require the full agent context

    return config


def create_ls_for_project(
    project: str | Project,
    log_level: int = logging.INFO,
    ls_timeout: float | None = DEFAULT_TOOL_TIMEOUT - 5,
    trace_lsp_communication: bool = False,
    serena_config_dir: str | None = None,
) -> SyncLanguageServer:
    """
    Create a language server for a project. Note that you will have to start it
    before performing any LS operations.

    :param project: either a path to the project root or a ProjectConfig instance.
        If no project.yml is found, the default project configuration will be used.
    :param log_level: the log level for the language server
    :param ls_timeout: the timeout for the language server
    :param trace_lsp_communication: whether to trace LSP communication
    :param serena_config_dir: custom path for the .serena directory
    :return: the language server
    """
    if isinstance(project, str):
        project_instance = Project.load(project, autogenerate=True, serena_config_dir=serena_config_dir)
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
    multilspy_config = MultilspyConfig(
        code_language=project_instance.language,
        ignored_paths=ignored_paths,
        trace_lsp_communication=trace_lsp_communication,
    )
    ls_logger = MultilspyLogger(log_level=log_level)
    log.info(f"Creating language server instance for {project_instance.project_root}.")
    return SyncLanguageServer.create(
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
        serena_config: SerenaConfigBase | None = None,
        context: SerenaAgentContext | None = None,
        modes: list[SerenaAgentMode] | None = None,
        enable_web_dashboard: bool | None = None,
        enable_gui_log_window: bool | None = None,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None,
        trace_lsp_communication: bool | None = None,
        tool_timeout: float | None = None,
        serena_config_dir: str | None = None,
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
        :param enable_web_dashboard: Whether to enable the web dashboard. If not specified, will take the value from the serena configuration.
        :param enable_gui_log_window: Whether to enable the GUI log window. It currently does not work on macOS, and setting this to True will be ignored then.
            If not specified, will take the value from the serena configuration.
        :param log_level: Log level for the GUI log window. If not specified, will take the value from the serena configuration.
        :param tool_timeout: Timeout in seconds for tool execution. If not specified, will take the value from the serena configuration.
        :param serena_config_dir: Custom path for the .serena directory. If not specified, will use the default .serena directory within the project root.
        """
        # Store the custom serena config directory for later use
        self._serena_config_dir = serena_config_dir

        # obtain serena configuration using the decoupled factory function
        self.serena_config = create_serena_config(
            serena_config=serena_config,
            enable_web_dashboard=enable_web_dashboard,
            enable_gui_log_window=enable_gui_log_window,
            log_level=log_level,
            trace_lsp_communication=trace_lsp_communication,
            tool_timeout=tool_timeout,
        )

        # adjust log level
        serena_log_level = self.serena_config.log_level
        if Logger.root.level > serena_log_level:
            log.info(f"Changing the root logger level to {serena_log_level}")
            Logger.root.setLevel(serena_log_level)
            # Override existing configuration (needed to configure multilspy logger as desired)
            logging.basicConfig(format=LOG_DEFAULT_FORMAT, level=serena_log_level, force=True)

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
                    GuiLogViewer("dashboard", title="Serena Logs"), level=serena_log_level, format_string=LOG_FORMAT
                )
                Logger.root.addHandler(self._gui_log_handler)

        # instantiate all tool classes
        self._all_tools: dict[type[Tool], Tool] = {tool_class: tool_class(self) for tool_class in ToolRegistry.get_all_tool_classes()}
        tool_names = [tool.get_name_from_cls() for tool in self._all_tools.values()]

        # If GUI log window is enabled, set the tool names for highlighting
        if self._gui_log_handler is not None:
            self._gui_log_handler.log_viewer.set_tool_names(tool_names)

        # start the dashboard (web frontend), registering its log handler
        if self.serena_config.web_dashboard:
            dashboard_log_handler = MemoryLogHandler(level=serena_log_level)
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
        self.ignore_spec: PathSpec  # not set to None to avoid assert statements
        """Ignore spec, extracted from the project's gitignore files and the explicitly configured ignored paths."""

        # Apply context and mode tool configurations
        if context is None:
            context = SerenaAgentContext.load_default()
        if modes is None:
            modes = SerenaAgentMode.load_default_modes()
        self._context = context
        self._modes = modes
        log.info(f"Loaded tools ({len(self._all_tools)}): {', '.join([tool.get_name_from_cls() for tool in self._all_tools.values()])}")

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

        return match_path(str(relative_path), self.ignore_spec)

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

    def _activate_project(self, project: Project) -> None:
        log.info(f"Activating {project.project_name} at {project.project_root}")
        self._active_project = project
        self._update_active_tools()

        # start the language server
        self.reset_language_server()
        assert self.language_server is not None
        self.ignore_spec = self.language_server.get_ignore_spec()

        # initialize project-specific instances
        log.debug(f"Initializing symbol and memories manager for {project.project_name} at {project.project_root}")
        self.symbol_manager = SymbolManager(self.language_server, self)
        self.memories_manager = MemoriesManagerMDFilesInProject(project.project_root, self._serena_config_dir)
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
            serena_config_dir=self._serena_config_dir,
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
        return self.agent.get_project_root()

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


class ToolInterface(ABC):
    """Protocol defining the complete interface that make_tool() expects from a tool."""

    @abstractmethod
    def get_name(self) -> str:
        """Get the tool name."""
        ...

    @abstractmethod
    def get_apply_docstring(self) -> str:
        """Get the docstring for the tool application, used by the MCP server."""
        ...

    @abstractmethod
    def get_apply_fn_metadata(self) -> FuncMetadata:
        """Get the metadata for the tool application function, used by the MCP server."""
        ...

    @abstractmethod
    def apply_ex(self, log_call: bool = True, catch_exceptions: bool = True, **kwargs: Any) -> str:
        """Apply the tool with logging and exception handling."""
        ...


class Tool(Component, ToolInterface):
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
    def get_name_from_cls(cls) -> str:
        name = cls.__name__
        if name.endswith("Tool"):
            name = name[:-4]
        # convert to snake_case
        name = "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")
        return name

    def get_name(self) -> str:
        return self.get_name_from_cls()

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

    @classmethod
    def get_apply_docstring_from_cls(cls) -> str:
        """Get the docstring for the apply method from the class (static metadata).
        Needed for creating MCP tools in a separate process without running into serialization issues.
        """
        # First try to get from __dict__ to handle dynamic docstring changes
        if "apply" in cls.__dict__:
            apply_fn = cls.__dict__["apply"]
        else:
            # Fall back to getattr for inherited methods
            apply_fn = getattr(cls, "apply", None)
            if apply_fn is None:
                raise AttributeError(f"apply method not defined in {cls}. Did you forget to implement it?")

        docstring = apply_fn.__doc__
        if not docstring:
            raise AttributeError(f"apply method has no (or empty) docstring in {cls}. Did you forget to implement it?")
        return docstring.strip()

    def get_apply_docstring(self) -> str:
        """Get the docstring for the apply method (instance method implementing ToolProtocol)."""
        return self.get_apply_docstring_from_cls()

    def get_apply_fn_metadata(self) -> FuncMetadata:
        """Get the metadata for the apply method (instance method implementing ToolProtocol)."""
        return self.get_apply_fn_metadata_from_cls()

    @classmethod
    def get_apply_fn_metadata_from_cls(cls) -> FuncMetadata:
        """Get the metadata for the apply method from the class (static metadata).
        Needed for creating MCP tools in a separate process without running into serialization issues.
        """
        # First try to get from __dict__ to handle dynamic docstring changes
        if "apply" in cls.__dict__:
            apply_fn = cls.__dict__["apply"]
        else:
            # Fall back to getattr for inherited methods
            apply_fn = getattr(cls, "apply", None)
            if apply_fn is None:
                raise AttributeError(f"apply method not defined in {cls}. Did you forget to implement it?")

        return func_metadata(apply_fn, skip_names=["self", "cls"])

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
        log.info(f"{self.get_name_from_cls()}: {dict_string(params)}")

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
                return f"Error: Tool '{self.get_name_from_cls()}' is not active. Active tools: {self.agent.get_active_tool_names()}"
        except Exception as e:
            return f"RuntimeError while checking if tool {self.get_name_from_cls()} is active: {e}"

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

            # apply the actual tool with a timeout
            execution_fn = lambda: apply_fn(**kwargs)
            execution_result = execute_with_timeout(execution_fn, self.agent.serena_config.tool_timeout, self.get_name_from_cls())
            if execution_result.status == ExecutionResult.Status.SUCCESS:
                result = cast(str, execution_result.result_value)
            else:
                assert execution_result.exception is not None
                raise execution_result.exception

        except Exception as e:
            if not catch_exceptions:
                raise
            msg = f"Error executing tool: {e}\n{traceback.format_exc()}"
            log.error(
                f"Error executing tool: {e}. "
                f"Consider restarting the language server to solve this (especially, if it's a timeout of a symbolic operation)",
                exc_info=e,
            )
            result = msg

        if log_call:
            log.info(f"Result: {result}")

        try:
            self.language_server.save_cache()
        except Exception as e:
            log.error(f"Error saving language server cache: {e}")

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
        self.agent.validate_relative_path(relative_path)

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
        self.agent.validate_relative_path(relative_path)

        abs_path = (Path(self.get_project_root()) / relative_path).resolve()
        will_overwrite_existing = abs_path.exists()

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        answer = f"File created: {relative_path}."
        if will_overwrite_existing:
            answer += " Overwrote existing file."
        return answer


class ListDirTool(Tool):
    """
    Lists files and directories in the given directory (optionally with recursion).
    """

    def apply(self, relative_path: str, recursive: bool, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Lists all non-gitignored files and directories in the given directory (optionally with recursion).

        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object with the names of directories and files within the given directory
        """
        self.agent.validate_relative_path(relative_path)

        dirs, files = scan_directory(
            os.path.join(self.get_project_root(), relative_path),
            relative_to=self.get_project_root(),
            recursive=recursive,
            is_ignored_dir=self.agent.path_is_gitignored,
            is_ignored_file=self.agent.path_is_gitignored,
        )

        result = json.dumps({"dirs": dirs, "files": files})
        return self._limit_length(result, max_answer_chars)


class FindFileTool(Tool):
    """
    Finds files in the given relative paths
    """

    def apply(self, file_mask: str, relative_path: str) -> str:
        """
        Finds non-gitignored files matching the given file mask within the given relative path

        :param file_mask: the filename or file mask (using the wildcards * or ?) to search for
        :param relative_path: the relative path to the directory to search in; pass "." to scan the project root
        :return: a JSON object with the list of matching files
        """
        self.agent.validate_relative_path(relative_path)

        dir_to_scan = os.path.join(self.get_project_root(), relative_path)

        # find the files by ignoring everything that doesn't match
        def is_ignored_file(abs_path: str) -> bool:
            if self.agent.path_is_gitignored(abs_path):
                return True
            filename = os.path.basename(abs_path)
            return not fnmatch(filename, file_mask)

        dirs, files = scan_directory(
            path=dir_to_scan,
            recursive=True,
            is_ignored_dir=self.agent.path_is_gitignored,
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
        For each analyzed file, we list the top-level symbols in the file (name_path, kind).
        Use this tool to get a high-level understanding of the code symbols.
        Calling this is often a good idea before more targeted reading, searching or editing operations on the code symbols.

        :param relative_path: the relative path to the file or directory to get the overview of
        :param max_answer_chars: if the overview is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. If the overview is too long, you should use a smaller directory instead,
            (e.g. a subdirectory).
        :return: a JSON object mapping relative paths of all contained files to info about top-level symbols in the file (name_path, kind).
        """
        path_to_symbol_infos = self.language_server.request_overview(relative_path)
        result = {}
        for file_path, symbols in path_to_symbol_infos.items():
            # TODO: maybe include not just top-level symbols? We could filter by kind to exclude variables
            #  The language server methods would need to be adjusted for this.
            result[file_path] = [{"name_path": symbol[0], "kind": int(symbol[1])} for symbol in symbols]

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
        relative_path: str | None = None,
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
        :param relative_path: Optional. Restrict search to this file or directory. If None, searches entire codebase.
            If a directory is passed, the search will be restricted to the files in that directory.
            If a file is passed, the search will be restricted to that file.
            If you have some knowledge about the codebase, you should use this parameter, as it will significantly
            speed up the search as well as reduce the number of results.
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
            within_relative_path=relative_path,
        )
        symbol_dicts = [_sanitize_symbol_dict(s.to_dict(kind=True, location=True, depth=depth, include_body=include_body)) for s in symbols]
        result = json.dumps(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingSymbolsTool(Tool):
    """
    Finds symbols that reference the symbol at the given location (optionally filtered by type).
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_kinds: list[int] | None = None,
        exclude_kinds: list[int] | None = None,
        max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH,
    ) -> str:
        """
        Finds symbols that reference the symbol at the given `name_path`. The result will contain metadata about the referencing symbols
        as well as a short code snippet around the reference (unless `include_body` is True, then the short snippet will be omitted).
        Note that among other kinds of references, this function can be used to find (direct) subclasses of a class,
        as subclasses are referencing symbols that have the kind class.

        :param name_path: for finding the symbol to find references for, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol for which to find references.
            Note that here you can't pass a directory but must pass a file.
        :param include_kinds: same as in the `find_symbol` tool.
        :param exclude_kinds: same as in the `find_symbol` tool.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        include_body = False  # It is probably never a good idea to include the body of the referencing symbols
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        references_in_symbols = self.symbol_manager.find_referencing_symbols(
            name_path,
            relative_file_path=relative_path,
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
        )
        reference_dicts = []
        for ref in references_in_symbols:
            ref_dict = ref.symbol.to_dict(kind=True, location=True, depth=0, include_body=include_body)
            ref_dict = _sanitize_symbol_dict(ref_dict)
            if not include_body:
                ref_relative_path = ref.symbol.location.relative_path
                assert ref_relative_path is not None, f"Referencing symbol {ref.symbol.name} has no relative path, this is likely a bug."
                content_around_ref = self.language_server.retrieve_content_around_line(
                    relative_file_path=ref_relative_path, line=ref.line, context_lines_before=1, context_lines_after=1
                )
                ref_dict["content_around_reference"] = content_around_ref.to_display_string()
            reference_dicts.append(ref_dict)
        result = json.dumps(reference_dicts)
        return self._limit_length(result, max_answer_chars)


class ReplaceSymbolBodyTool(Tool, ToolMarkerCanEdit):
    """
    Replaces the full definition of a symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        r"""
        Replaces the body of the symbol with the given `name_path`.

        Important:
        You don't need to provide an adjusted indentation,
        as the tool will automatically add the indentation of the original symbol to each line. For example,
        for replacing a method in python, you can just write (using the standard python indentation):
        body="def my_method_replacement(self, ...):\n    first_line\n    second_line...". So each line after the first line only has
        an indentation of 4 (the indentation relative to the first character),
        since the additional indentation will be added by the tool. Same for more deeply nested
        cases. You always only need to write the relative indentation to the first character of the first line, and that
        in turn should not have any indentation.
        ALWAYS REMEMBER TO USE THE CORRECT INDENTATION IN THE BODY!

        :param name_path: for finding the symbol to replace, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol
        :param body: the new symbol body.

        """
        self.symbol_manager.replace_body(
            name_path,
            relative_file_path=relative_path,
            body=body,
            use_same_indentation=True,
        )
        return SUCCESS_RESULT


class InsertAfterSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content after the end of the definition of a given symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        """
        Inserts the given body/content after the end of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.

        :param name_path: for finding the symbol to insert after, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted. Important: the inserted code will automatically have the
            same indentation as the symbol's body, so you do not need to provide any additional indentation.
        """
        self.symbol_manager.insert_after_symbol(
            name_path,
            relative_file_path=relative_path,
            body=body,
            use_same_indentation=True,
        )
        return SUCCESS_RESULT


class InsertBeforeSymbolTool(Tool, ToolMarkerCanEdit):
    """
    Inserts content before the beginning of the definition of a given symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        """
        Inserts the given body/content before the beginning of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.
        It also can be used to insert a new import statement before the first symbol in the file.

        :param name_path: for finding the symbol to insert before, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted. Important: the inserted code will automatically have the
            same indentation as the symbol's body, so you do not need to provide any additional indentation.
        """
        self.symbol_manager.insert_before_symbol(
            name_path,
            relative_file_path=relative_path,
            body=body,
            use_same_indentation=True,
        )
        return SUCCESS_RESULT


class EditedFileContext:
    """
    Context manager for file editing.

    Create the context, then use `set_updated_content` to set the new content, the original content
    being provided in `original_content`.
    When exiting the context without an exception, the updated content will be written back to the file.
    """

    def __init__(self, relative_path: str, agent: SerenaAgent):
        self._project = agent.get_active_project()
        assert self._project is not None
        self._abs_path = os.path.join(self._project.project_root, relative_path)
        if not os.path.isfile(self._abs_path):
            raise FileNotFoundError(f"File {self._abs_path} does not exist.")
        with open(self._abs_path, encoding=self._project.project_config.encoding) as f:
            self._original_content = f.read()
        self._updated_content: str | None = None

    def __enter__(self) -> Self:
        return self

    def get_original_content(self) -> str:
        """
        :return: the original content of the file before any modifications.
        """
        return self._original_content

    def set_updated_content(self, content: str) -> None:
        """
        Sets the updated content of the file, which will be written back to the file
        when the context is exited without an exception.

        :param content: the updated content of the file
        """
        self._updated_content = content

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        if self._updated_content is not None and exc_type is None:
            assert self._project is not None
            with open(self._abs_path, "w", encoding=self._project.project_config.encoding) as f:
                f.write(self._updated_content)
            log.info(f"Updated content written to {self._abs_path}")
            # Language servers should automatically detect the change and update its state accordingly.
            # If they do not, we may have to add a call to notify it.


class ReplaceRegexTool(Tool, ToolMarkerCanEdit):
    """
    Replaces content in a file by using regular expressions.
    """

    def apply(
        self,
        relative_path: str,
        regex: str,
        repl: str,
        allow_multiple_occurrences: bool = False,
    ) -> str:
        r"""
        Replaces one or more occurrences of the given regular expression.
        This is the preferred way to replace content in a file whenever the symbol-level
        tools are not appropriate.
        Even large sections of code can be replaced by providing a concise regular expression of
        the form "beginning.*?end-of-text-to-be-replaced".
        Always try to use wildcards to avoid specifying the exact content of the code to be replaced,
        especially if it spans several lines.

        IMPORTANT: REMEMBER TO USE WILDCARDS WHEN APPROPRIATE! I WILL BE VERY UNHAPPY IF YOU WRITE LONG REGEXES WITHOUT USING WILDCARDS INSTEAD!

        :param relative_path: the relative path to the file
        :param regex: a Python-style regular expression, matches of which will be replaced.
            Dot matches all characters, multi-line matching is enabled.
        :param repl: the string to replace the matched content with, which may contain
            backreferences like \1, \2, etc.
        :param allow_multiple_occurrences: if True, the regex may match multiple occurrences in the file
            and all of them will be replaced.
            If this is set to False and the regex matches multiple occurrences, an error will be returned
            (and you may retry with a revised, more specific regex).
        """
        self.agent.validate_relative_path(relative_path)
        with EditedFileContext(relative_path, self.agent) as context:
            original_content = context.get_original_content()
            updated_content, n = re.subn(regex, repl, original_content, flags=re.DOTALL | re.MULTILINE)
            if n == 0:
                return f"Error: No matches found for regex '{regex}' in file '{relative_path}'."
            if not allow_multiple_occurrences and n > 1:
                return (
                    f"Error: Regex '{regex}' matches {n} occurrences in file '{relative_path}'. "
                    "Please revise the regex to be more specific or enable allow_multiple_occurrences if this is expected."
                )
            context.set_updated_content(updated_content)
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
            return f"Error: Must call `{read_lines_tool.get_name_from_cls()}` first to read exactly the affected lines."
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

    def apply(self, memory_name: str, content: str, max_answer_chars: int = _DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Write some information about this project that can be useful for future tasks to a memory.
        Use markdown formatting for the content.
        The information should be short and to the point.
        The memory name should be meaningful, such that from the name you can infer what the information is about.
        It is better to have multiple small memories than to have a single large one because
        memories will be read one by one and we only ever want to read relevant memories.

        This tool is either called during the onboarding process or when you have identified
        something worth remembering about the project from the past conversation.
        """
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_name} is too long. Max length is {max_answer_chars} characters. " + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_name, content)


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
            project_root = self.get_project_root()
            rel_paths_to_search = []
            for root, dirs, files in os.walk(project_root):
                dirs[:] = [d for d in dirs if not self.agent.path_is_gitignored(os.path.join(root, d))]
                for file in files:
                    file_path = os.path.join(root, file)
                    if not self.agent.path_is_gitignored(file_path):
                        relative_path = os.path.relpath(file_path, project_root)
                        rel_paths_to_search.append(relative_path)
            # TODO (maybe): not super efficient to walk through the files again and filter if glob patterns are provided
            #   but it probably never matters and this version required no further refactoring
            matches = search_files(
                rel_paths_to_search,
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
        The only exception is when a user asks you to activate a project, in which case you should call the `activate_project` first
        instead and then call this tool.
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


_TOOL_REGISTRY_DICT: dict[str, type[Tool]] = {tool_class.get_name_from_cls(): tool_class for tool_class in _iter_tool_classes()}
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
            tool_dict[tool_class.get_name_from_cls()] = tool_class
        for tool_name in sorted(tool_dict.keys()):
            tool_class = tool_dict[tool_name]
            print(f" * `{tool_name}`: {tool_class.get_tool_description().strip()}")
