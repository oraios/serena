"""
The Serena Model Context Protocol (MCP) Server
"""

import dataclasses
import os
import shutil
from collections.abc import Iterator, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Self, TypeVar

import yaml
from ruamel.yaml.comments import CommentedMap
from sensai.util import logging
from sensai.util.logging import LogTime, datetime_tag
from sensai.util.string import ToStringMixin

from serena.constants import (
    DEFAULT_SOURCE_FILE_ENCODING,
    PROJECT_TEMPLATE_FILE,
    REPO_ROOT,
    SERENA_CONFIG_TEMPLATE_FILE,
    SERENA_FILE_ENCODING,
    SERENA_MANAGED_DIR_NAME,
)
from serena.util.inspection import determine_programming_language_composition
from serena.util.yaml import YamlCommentNormalisation, load_yaml, normalise_yaml_comments, save_yaml, transfer_missing_yaml_comments
from solidlsp.ls_config import Language

from ..analytics import RegisteredTokenCountEstimator
from ..util.class_decorators import singleton
from ..util.cli_util import ask_yes_no
from ..util.dataclass import get_dataclass_default

if TYPE_CHECKING:
    from ..project import Project

log = logging.getLogger(__name__)
T = TypeVar("T")
DEFAULT_TOOL_TIMEOUT: float = 240
DictType = dict | CommentedMap
TDict = TypeVar("TDict", bound=DictType)


@singleton
class SerenaPaths:
    """
    Provides paths to various Serena-related directories and files.
    """

    def __init__(self) -> None:
        home_dir = os.getenv("SERENA_HOME")
        if home_dir is None or home_dir.strip() == "":
            home_dir = str(Path.home() / SERENA_MANAGED_DIR_NAME)
        else:
            home_dir = home_dir.strip()
        self.serena_user_home_dir: str = home_dir
        """
        the path to the Serena home directory, where the user's configuration/data is stored.
        This is ~/.serena by default, but it can be overridden via the SERENA_HOME environment variable.
        """
        self.user_prompt_templates_dir: str = os.path.join(self.serena_user_home_dir, "prompt_templates")
        """
        directory containing prompt templates defined by the user.
        Prompts defined by the user take precedence over Serena's built-in prompt templates.
        """
        self.user_contexts_dir: str = os.path.join(self.serena_user_home_dir, "contexts")
        """
        directory containing contexts defined by the user. 
        If a name of a context matches a name of a context in SERENAS_OWN_CONTEXT_YAMLS_DIR, 
        the user context will override the default context definition.
        """
        self.user_modes_dir: str = os.path.join(self.serena_user_home_dir, "modes")
        """
        directory containing modes defined by the user.
        If a name of a mode matches a name of a mode in SERENAS_OWN_MODES_YAML_DIR,
        the user mode will override the default mode definition.
        """
        self.news_snippet_id_file: str = os.path.join(self.serena_user_home_dir, "last_read_news_snippet_id.txt")
        """
        file containing the ID of the last read news snippet
        """

    def get_next_log_file_path(self, prefix: str) -> str:
        """
        :param prefix: the filename prefix indicating the type of the log file
        :return: the full path to the log file to use
        """
        log_dir = os.path.join(self.serena_user_home_dir, "logs", datetime.now().strftime("%Y-%m-%d"))
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, prefix + "_" + datetime_tag() + ".txt")

    # TODO: Paths from constants.py should be moved here


@dataclass
class ToolInclusionDefinition:
    """
    Defines which tools to include/exclude in Serena's operation.
    This can mean either
      * defining exclusions/inclusions to apply to an existing set of tools [incremental mode], or
      * defining a fixed set of tools to use [fixed mode].
    """

    excluded_tools: Sequence[str] = ()
    """
    the names of tools to exclude from use [incremental mode]
    """
    included_optional_tools: Sequence[str] = ()
    """
    the names of optional tools to include [incremental mode]
    """
    fixed_tools: Sequence[str] = ()
    """
    the names of tools to use as a fixed set of tools [fixed mode]
    """

    def is_fixed_tool_set(self) -> bool:
        num_fixed = len(self.fixed_tools)
        num_incremental = len(self.excluded_tools) + len(self.included_optional_tools)
        if num_fixed > 0 and num_incremental > 0:
            raise ValueError("Cannot use both fixed_tools and excluded_tools/included_optional_tools at the same time.")
        return num_fixed > 0


@dataclass
class ModeSelectionDefinition:
    base_modes: Sequence[str] | None = None
    default_modes: Sequence[str] | None = None


class SerenaConfigError(Exception):
    pass


@dataclass
class LSConfig:
    """
    Configuration for language server behavior.
    In YAML, this is represented as a dictionary with the same field names.

    An instance will be associated with the global serena_config, providing defaults,
    and with the project level configuration, providing overrides.
    By convention, each field can take the value `"use_global"` to indicate that
    the value from the global config (or the default, if the latter is also missing) should be used.
    Defaults are defined in the method `with_global_defaults`.
    """

    hover_budget: float | Literal["use_global"] = "use_global"
    """
    Time budget (seconds) for LSP hover requests when tools request include_info.

    If budget is exceeded, Serena stops issuing further hover requests and returns partial info results.
    0 disables the budget (no early stopping).
    """

    def apply_overrides(self, other: "LSConfig") -> None:
        for f in dataclasses.fields(self):
            other_value = getattr(other, f.name)
            if other_value != "use_global":
                setattr(self, f.name, other_value)

    def assert_all_values_set(self) -> None:
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if value == "use_global":
                raise ValueError(f"Field {f.name} is set to 'use_global', expected a value to ne set.")

    @classmethod
    def with_global_defaults(cls) -> Self:
        """Returns a new LSConfig with global defaults (i.e., no value is "use_global")"""
        return cls(hover_budget=10)


def get_serena_managed_in_project_dir(project_root: str | Path) -> str:
    return os.path.join(project_root, SERENA_MANAGED_DIR_NAME)


class LanguageBackend(Enum):
    LSP = "LSP"
    """
    Use the language server protocol (LSP), spawning freely available language servers
    via the SolidLSP library that is part of Serena
    """
    JETBRAINS = "JetBrains"
    """
    Use the Serena plugin in your JetBrains IDE.
    (requires the plugin to be installed and the project being worked on to be open in your IDE)
    """

    @staticmethod
    def from_str(backend_str: str) -> "LanguageBackend":
        for backend in LanguageBackend:
            if backend.value.lower() == backend_str.lower():
                return backend
        raise ValueError(f"Unknown language backend '{backend_str}': valid values are {[b.value for b in LanguageBackend]}")


@dataclass(kw_only=True)
class ProjectConfig(ToolInclusionDefinition, ModeSelectionDefinition, ToStringMixin):
    project_name: str
    languages: list[Language]
    ignored_paths: list[str] = field(default_factory=list)
    read_only: bool = False
    ignore_all_files_in_gitignore: bool = True
    initial_prompt: str = ""
    encoding: str = DEFAULT_SOURCE_FILE_ENCODING
    ls_config: LSConfig = field(default_factory=LSConfig)
    """
    Per-project override for language server configuration.
    Values here override the global serena_config.yml settings.
    """
    SERENA_DEFAULT_PROJECT_FILE = "project.yml"
    FIELDS_WITHOUT_DEFAULTS = {"project_name", "languages"}
    YAML_COMMENT_NORMALISATION = YamlCommentNormalisation.LEADING
    """
    the comment normalisation strategy to use when loading/saving project configuration files.
    The template file must match this configuration (i.e. it must use leading comments if this is set to LEADING).
    """

    def _tostring_includes(self) -> list[str]:
        return ["project_name"]

    @classmethod
    def autogenerate(
        cls,
        project_root: str | Path,
        project_name: str | None = None,
        languages: list[Language] | None = None,
        save_to_disk: bool = True,
        interactive: bool = False,
    ) -> Self:
        """
        Autogenerate a project configuration for a given project root.

        :param project_root: the path to the project root
        :param project_name: the name of the project; if None, the name of the project will be the name of the directory
            containing the project
        :param languages: the languages of the project; if None, they will be determined automatically
        :param save_to_disk: whether to save the project configuration to disk
        :param interactive: whether to run in interactive CLI mode, asking the user for input where appropriate
        :return: the project configuration
        """
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        with LogTime("Project configuration auto-generation", logger=log):
            log.info("Project root: %s", project_root)
            project_name = project_name or project_root.name
            if languages is None:
                # determine languages automatically
                log.info("Determining programming languages used in the project")
                language_composition = determine_programming_language_composition(str(project_root))
                log.info("Language composition: %s", language_composition)
                if len(language_composition) == 0:
                    language_values = ", ".join([lang.value for lang in Language])
                    raise ValueError(
                        f"No source files found in {project_root}\n\n"
                        f"To use Serena with this project, you need to either\n"
                        f"  1. specify a programming language by adding parameters --language <language>\n"
                        f"     when creating the project via the Serena CLI command OR\n"
                        f"  2. add source files in one of the supported languages first.\n\n"
                        f"Supported languages are: {language_values}\n"
                        f"Read the documentation for more information."
                    )
                # sort languages by number of files found
                languages_and_percentages = sorted(
                    language_composition.items(), key=lambda item: (item[1], item[0].get_priority()), reverse=True
                )
                # find the language with the highest percentage and enable it
                top_language_pair = languages_and_percentages[0]
                other_language_pairs = languages_and_percentages[1:]
                languages_to_use: list[str] = [top_language_pair[0].value]
                # if in interactive mode, ask the user which other languages to enable
                if len(other_language_pairs) > 0 and interactive:
                    print(
                        "Detected and enabled main language '%s' (%.2f%% of source files)."
                        % (top_language_pair[0].value, top_language_pair[1])
                    )
                    print(f"Additionally detected {len(other_language_pairs)} other language(s).\n")
                    print("Note: Enable only languages you need symbolic retrieval/editing capabilities for.")
                    print("      Additional language servers use resources and some languages may require additional")
                    print("      system-level installations/configuration (see Serena documentation).")
                    print("\nWhich additional languages do you want to enable?")
                    for lang, perc in other_language_pairs:
                        enable = ask_yes_no("Enable %s (%.2f%% of source files)?" % (lang.value, perc), default=False)
                        if enable:
                            languages_to_use.append(lang.value)
                    print()
                log.info("Using languages: %s", languages_to_use)
            else:
                languages_to_use = [lang.value for lang in languages]
            config_with_comments, _ = cls._load_yaml(PROJECT_TEMPLATE_FILE)
            config_with_comments["project_name"] = project_name
            config_with_comments["languages"] = languages_to_use
            if save_to_disk:
                project_yml_path = cls.path_to_project_yml(project_root)
                log.info("Saving project configuration to %s", project_yml_path)
                save_yaml(project_yml_path, config_with_comments)
            return cls._from_dict(config_with_comments)

    @classmethod
    def path_to_project_yml(cls, project_root: str | Path) -> str:
        return os.path.join(project_root, cls.rel_path_to_project_yml())

    @classmethod
    def rel_path_to_project_yml(cls) -> str:
        return os.path.join(SERENA_MANAGED_DIR_NAME, cls.SERENA_DEFAULT_PROJECT_FILE)

    @classmethod
    def _load_yaml(
        cls, yml_path: str, comment_normalisation: YamlCommentNormalisation = YamlCommentNormalisation.NONE
    ) -> tuple[CommentedMap, bool]:
        """
        Load the project configuration as a CommentedMap, preserving comments and ensuring
        completeness of the configuration by applying default values for missing fields
        and backward compatibility adjustments.

        :param yml_path: the path to the project.yml file
        :return: a tuple `(dict, was_complete)` where dict is a CommentedMap representing a
          full project configuration and `was_complete` indicates whether the loaded configuration
          was complete (i.e., did not require any default values to be applied)
        """
        data = load_yaml(yml_path, comment_normalisation=comment_normalisation)

        # apply defaults
        was_complete = True
        for field_info in dataclasses.fields(cls):
            key = field_info.name
            if key in cls.FIELDS_WITHOUT_DEFAULTS:
                continue
            if key not in data:
                was_complete = False
                default_value = get_dataclass_default(cls, key)
                data.setdefault(key, default_value)

        # backward compatibility: handle single "language" field
        if "languages" not in data and "language" in data:
            data["languages"] = [data["language"]]
            del data["language"]

        return data, was_complete

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """
        Create a ProjectConfig instance from a (full) configuration dictionary
        """
        lang_name_mapping = {"javascript": "typescript"}
        languages: list[Language] = []
        for language_str in data["languages"]:
            orig_language_str = language_str
            try:
                language_str = language_str.lower()
                if language_str in lang_name_mapping:
                    language_str = lang_name_mapping[language_str]
                language = Language(language_str)
                languages.append(language)
            except ValueError as e:
                raise ValueError(
                    f"Invalid language: {orig_language_str}.\nValid language_strings are: {[l.value for l in Language]}"
                ) from e

        return cls(
            project_name=data["project_name"],
            languages=languages,
            ignored_paths=data["ignored_paths"],
            excluded_tools=data["excluded_tools"],
            fixed_tools=data["fixed_tools"],
            included_optional_tools=data["included_optional_tools"],
            read_only=data["read_only"],
            ignore_all_files_in_gitignore=data["ignore_all_files_in_gitignore"],
            initial_prompt=data["initial_prompt"],
            encoding=data["encoding"],
            base_modes=data["base_modes"],
            default_modes=data["default_modes"],
            ls_config=LSConfig(**data.get("ls_config", {})),
        )

    def _to_yaml_dict(self) -> dict:
        """
        :return: a yaml-serializable dictionary representation of this configuration
        """
        d = dataclasses.asdict(self)
        d["languages"] = [lang.value for lang in self.languages]
        return d

    @classmethod
    def load(cls, project_root: Path | str, autogenerate: bool = False) -> Self:
        """
        Load a ProjectConfig instance from the path to the project root.
        """
        project_root = Path(project_root)
        yaml_path = project_root / cls.rel_path_to_project_yml()

        # auto-generate if necessary
        if not yaml_path.exists():
            if autogenerate:
                return cls.autogenerate(project_root)
            else:
                raise FileNotFoundError(f"Project configuration file not found: {yaml_path}")

        # load the configuration dictionary
        yaml_data, was_complete = cls._load_yaml(str(yaml_path))
        if "project_name" not in yaml_data:
            yaml_data["project_name"] = project_root.name

        # instantiate the ProjectConfig
        project_config = cls._from_dict(yaml_data)

        # if the configuration was incomplete, re-save it to disk
        if not was_complete:
            log.info("Project configuration in %s was incomplete, re-saving with default values for missing fields", yaml_path)
            project_config.save(project_root)

        return project_config

    def save(self, project_root: Path | str) -> None:
        """
        Saves the project configuration to disk.

        :param project_root: the root directory of the project
        """
        config_path = self.path_to_project_yml(project_root)
        log.info("Saving updated project configuration to %s", config_path)

        # load original commented map and update it with current values
        config_with_comments, _ = self._load_yaml(config_path, self.YAML_COMMENT_NORMALISATION)
        config_with_comments.update(self._to_yaml_dict())

        # transfer missing comments from the template file
        template_config, _ = self._load_yaml(PROJECT_TEMPLATE_FILE, self.YAML_COMMENT_NORMALISATION)
        transfer_missing_yaml_comments(template_config, config_with_comments, self.YAML_COMMENT_NORMALISATION)

        save_yaml(config_path, config_with_comments)


class RegisteredProject(ToStringMixin):
    def __init__(self, project_root: str, project_config: "ProjectConfig", project_instance: Optional["Project"] = None) -> None:
        """
        Represents a registered project in the Serena configuration.

        :param project_root: the root directory of the project
        :param project_config: the configuration of the project
        """
        self.project_root = Path(project_root).resolve()
        self.project_config = project_config
        self._project_instance = project_instance

    def _tostring_exclude_private(self) -> bool:
        return True

    @property
    def project_name(self) -> str:
        return self.project_config.project_name

    @classmethod
    def from_project_instance(cls, project_instance: "Project") -> "RegisteredProject":
        return RegisteredProject(
            project_root=project_instance.project_root,
            project_config=project_instance.project_config,
            project_instance=project_instance,
        )

    @classmethod
    def from_project_root(cls, project_root: str | Path) -> "RegisteredProject":
        project_config = ProjectConfig.load(project_root)
        return RegisteredProject(
            project_root=str(project_root),
            project_config=project_config,
        )

    def matches_root_path(self, path: str | Path) -> bool:
        """
        Check if the given path matches the project root path.

        :param path: the path to check
        :return: True if the path matches the project root, False otherwise
        """
        return self.project_root.samefile(Path(path).resolve())

    def get_project_instance(self) -> "Project":
        """
        Returns the project instance for this registered project, loading it if necessary.
        """
        if self._project_instance is None:
            from ..project import Project

            with LogTime(f"Loading project instance for {self}", logger=log):
                self._project_instance = Project(project_root=str(self.project_root), project_config=self.project_config)
        return self._project_instance


@dataclass(kw_only=True)
class SerenaConfig(ToolInclusionDefinition, ModeSelectionDefinition, ToStringMixin):
    """
    Holds the Serena agent configuration, which is typically loaded from a YAML configuration file
    (when instantiated via :method:`from_config_file`), which is updated when projects are added or removed.
    For testing purposes, it can also be instantiated directly with the desired parameters.
    """

    # *** fields that are mapped directly to/from the configuration file (DO NOT RENAME) ***

    projects: list[RegisteredProject] = field(default_factory=list)
    gui_log_window: bool = False
    log_level: int = logging.INFO
    trace_lsp_communication: bool = False
    web_dashboard: bool = True
    web_dashboard_open_on_launch: bool = True
    web_dashboard_listen_address: str = "127.0.0.1"
    jetbrains_plugin_server_address: str = "127.0.0.1"
    tool_timeout: float = DEFAULT_TOOL_TIMEOUT

    language_backend: LanguageBackend = LanguageBackend.LSP
    """
    the language backend to use for code understanding features
    """

    token_count_estimator: str = RegisteredTokenCountEstimator.CHAR_COUNT.name
    """Only relevant if `record_tool_usage` is True; the name of the token count estimator to use for tool usage statistics.
    See the `RegisteredTokenCountEstimator` enum for available options.
    
    Note: some token estimators (like tiktoken) may require downloading data files
    on the first run, which can take some time and require internet access. Others, like the Anthropic ones, may require an API key
    and rate limits may apply.
    """
    default_max_tool_answer_chars: int = 150_000
    """Used as default for tools where the apply method has a default maximal answer length.
    Even though the value of the max_answer_chars can be changed when calling the tool, it may make sense to adjust this default 
    through the global configuration.
    """
    ls_specific_settings: dict = field(default_factory=dict)
    """Advanced configuration option allowing to configure language server implementation specific options, see SolidLSPSettings for more info."""

    ls_config: LSConfig = field(default_factory=LSConfig.with_global_defaults)
    """
    Configuration for language server behavior.
    These are the default values that can be overridden per-project.
    """

    # settings with overridden defaults
    default_modes: Sequence[str] | None = ("interactive", "editing")

    # *** fields that are NOT mapped to/from the configuration file ***

    _loaded_commented_yaml: CommentedMap | None = None
    _config_file_path: str | None = None
    """
    the path to the configuration file to which updates of the configuration shall be saved;
    if None, the configuration is not saved to disk
    """

    # *** static members ***
    CONFIG_FILE = "serena_config.yml"
    CONFIG_FIELDS_WITH_TYPE_CONVERSION = {"projects", "language_backend", "ls_config"}

    # *** methods ***

    @property
    def config_file_path(self) -> str | None:
        return self._config_file_path

    def _iter_config_file_mapped_fields_without_type_conversion(self) -> Iterator[str]:
        for field_info in dataclasses.fields(self):
            field_name = field_info.name
            if field_name.startswith("_"):
                continue
            if field_name in self.CONFIG_FIELDS_WITH_TYPE_CONVERSION:
                continue
            yield field_name

    def _tostring_includes(self) -> list[str]:
        return ["config_file_path"]

    @classmethod
    def _generate_config_file(cls, config_file_path: str) -> None:
        """
        Generates a Serena configuration file at the specified path from the template file.

        :param config_file_path: the path where the configuration file should be generated
        """
        log.info(f"Auto-generating Serena configuration file in {config_file_path}")
        loaded_commented_yaml = load_yaml(SERENA_CONFIG_TEMPLATE_FILE)
        save_yaml(config_file_path, loaded_commented_yaml)

    @classmethod
    def _determine_config_file_path(cls) -> str:
        """
        :return: the location where the Serena configuration file is stored/should be stored
        """
        config_path = os.path.join(SerenaPaths().serena_user_home_dir, cls.CONFIG_FILE)

        # if the config file does not exist, check if we can migrate it from the old location
        if not os.path.exists(config_path):
            old_config_path = os.path.join(REPO_ROOT, cls.CONFIG_FILE)
            if os.path.exists(old_config_path):
                log.info(f"Moving Serena configuration file from {old_config_path} to {config_path}")
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                shutil.move(old_config_path, config_path)

        return config_path

    @classmethod
    def from_config_file(cls, generate_if_missing: bool = True) -> "SerenaConfig":
        """
        Static constructor to create SerenaConfig from the configuration file
        """
        config_file_path = cls._determine_config_file_path()

        # create the configuration file from the template if necessary
        if not os.path.exists(config_file_path):
            if not generate_if_missing:
                raise FileNotFoundError(f"Serena configuration file not found: {config_file_path}")
            log.info(f"Serena configuration file not found at {config_file_path}, autogenerating...")
            cls._generate_config_file(config_file_path)

        # load the configuration
        log.info(f"Loading Serena configuration from {config_file_path}")
        try:
            loaded_commented_yaml = load_yaml(config_file_path)
        except Exception as e:
            raise ValueError(f"Error loading Serena configuration from {config_file_path}: {e}") from e

        # create the configuration instance
        instance = cls(_loaded_commented_yaml=loaded_commented_yaml, _config_file_path=config_file_path)
        num_migrations = 0

        def get_value_or_default(field_name: str) -> Any:
            nonlocal num_migrations
            if field_name not in loaded_commented_yaml:
                num_migrations += 1
            return loaded_commented_yaml.get(field_name, get_dataclass_default(SerenaConfig, field_name))

        # transfer regular fields that do not require type conversion
        for field_name in instance._iter_config_file_mapped_fields_without_type_conversion():
            assert hasattr(instance, field_name)
            setattr(instance, field_name, get_value_or_default(field_name))

        # read projects
        if "projects" not in loaded_commented_yaml:
            raise SerenaConfigError("`projects` key not found in Serena configuration. Please update your `serena_config.yml` file.")
        instance.projects = []
        for path in loaded_commented_yaml["projects"]:
            path = Path(path).resolve()
            if not path.exists() or (path.is_dir() and not (path / ProjectConfig.rel_path_to_project_yml()).exists()):
                log.warning(f"Project path {path} does not exist or does not contain a project configuration file, skipping.")
                continue
            if path.is_file():
                path = cls._migrate_out_of_project_config_file(path)
                if path is None:
                    continue
                num_migrations += 1
            project_config = ProjectConfig.load(path)
            project = RegisteredProject(
                project_root=str(path),
                project_config=project_config,
            )
            instance.projects.append(project)

        # determine language backend
        language_backend = get_dataclass_default(SerenaConfig, "language_backend")
        if "language_backend" in loaded_commented_yaml:
            backend_str = loaded_commented_yaml["language_backend"]
            language_backend = LanguageBackend.from_str(backend_str)
        else:
            # backward compatibility (migrate Boolean field "jetbrains")
            if "jetbrains" in loaded_commented_yaml:
                num_migrations += 1
                if loaded_commented_yaml["jetbrains"]:
                    language_backend = LanguageBackend.JETBRAINS
                del loaded_commented_yaml["jetbrains"]
        instance.language_backend = language_backend

        # load LSConfig, applying defaults and overrides
        # we use the same mechanism for defaults and user-provided overrides as for the project-level
        # overrides of the global config. Could be considered a slight abuse (due to the keyword use_global
        # that forms part of that mechanism not being semantically applicable here).
        ls_config = LSConfig.with_global_defaults()
        ls_config_overrides = LSConfig(**loaded_commented_yaml.get("ls_config", {}))
        ls_config.apply_overrides(ls_config_overrides)
        instance.ls_config = ls_config

        # migrate deprecated "gui_log_level" field if necessary
        if "gui_log_level" in loaded_commented_yaml:
            num_migrations += 1
            if "log_level" not in loaded_commented_yaml:
                instance.log_level = loaded_commented_yaml["gui_log_level"]
            del loaded_commented_yaml["gui_log_level"]

        # re-save the configuration file if any migrations were performed
        if num_migrations > 0:
            log.info("Legacy configuration was migrated; re-saving configuration file")
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
            with open(path, encoding=SERENA_FILE_ENCODING) as f:
                project_config_data = yaml.safe_load(f)
            if "project_name" not in project_config_data:
                project_name = path.stem
                with open(path, "a", encoding=SERENA_FILE_ENCODING) as f:
                    f.write(f"\nproject_name: {project_name}")
            project_root = project_config_data["project_root"]
            shutil.move(str(path), str(Path(project_root) / ProjectConfig.rel_path_to_project_yml()))
            return Path(project_root).resolve()
        except Exception as e:
            log.error(f"Error migrating configuration file: {e}")
            return None

    @cached_property
    def project_paths(self) -> list[str]:
        return sorted(str(project.project_root) for project in self.projects)

    @cached_property
    def project_names(self) -> list[str]:
        return sorted(project.project_config.project_name for project in self.projects)

    def get_registered_project(self, project_root_or_name: str, autoregister: bool = False) -> Optional[RegisteredProject]:
        """
        :param project_root_or_name: path to the project root or the name of the project
        :param autoregister: whether to register the project if it exists but is not registered yet
        :return: the registered project, or None if not found
        """
        # look for project by name
        project_candidates = []
        for project in self.projects:
            if project.project_config.project_name == project_root_or_name:
                project_candidates.append(project)
        if len(project_candidates) == 1:
            return project_candidates[0]
        elif len(project_candidates) > 1:
            raise ValueError(
                f"Multiple projects found with name '{project_root_or_name}'. Please activate it by location instead. "
                f"Locations: {[p.project_root for p in project_candidates]}"
            )
        # no project found by name; check if it's a path
        if os.path.isdir(project_root_or_name):
            for project in self.projects:
                if project.matches_root_path(project_root_or_name):
                    return project
        # no registered project found; auto-register if project configuration exists
        if autoregister:
            config_path = ProjectConfig.path_to_project_yml(project_root_or_name)
            if os.path.isfile(config_path):
                registered_project = RegisteredProject.from_project_root(project_root_or_name)
                self.add_registered_project(registered_project)
                return registered_project
        # nothing found
        return None

    def get_project(self, project_root_or_name: str) -> Optional["Project"]:
        registered_project = self.get_registered_project(project_root_or_name)
        if registered_project is None:
            return None
        else:
            return registered_project.get_project_instance()

    def add_registered_project(self, registered_project: RegisteredProject) -> None:
        """
        Adds a registered project, saving the configuration file.
        """
        self.projects.append(registered_project)
        self.save()

    def add_project_from_path(self, project_root: Path | str) -> "Project":
        """
        Add a new project to the Serena configuration from a given path, auto-generating the project
        with defaults if it does not exist.
        Will raise a FileExistsError if a project already exists at the path.

        :param project_root: the path to the project to add
        :return: the project that was added
        """
        from ..project import Project

        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Error: Path does not exist: {project_root}")
        if not project_root.is_dir():
            raise FileNotFoundError(f"Error: Path is not a directory: {project_root}")

        for already_registered_project in self.projects:
            if str(already_registered_project.project_root) == str(project_root):
                raise FileExistsError(
                    f"Project with path {project_root} was already added with name '{already_registered_project.project_name}'."
                )

        project_config = ProjectConfig.load(project_root, autogenerate=True)

        new_project = Project(project_root=str(project_root), project_config=project_config, is_newly_created=True)
        self.add_registered_project(RegisteredProject.from_project_instance(new_project))

        return new_project

    def remove_project(self, project_name: str) -> None:
        # find the index of the project with the desired name and remove it
        for i, project in enumerate(list(self.projects)):
            if project.project_name == project_name:
                del self.projects[i]
                break
        else:
            raise ValueError(f"Project '{project_name}' not found in Serena configuration; valid project names: {self.project_names}")
        self.save()

    def save(self) -> None:
        """
        Saves the configuration to the file from which it was loaded (if any)
        """
        if self.config_file_path is None:
            return

        assert self._loaded_commented_yaml is not None, "Cannot save configuration without loaded YAML"

        commented_yaml = deepcopy(self._loaded_commented_yaml)

        # update fields with current values
        for field_name in self._iter_config_file_mapped_fields_without_type_conversion():
            commented_yaml[field_name] = getattr(self, field_name)

        # convert project objects into list of paths
        commented_yaml["projects"] = sorted({str(project.project_root) for project in self.projects})

        # convert language backend to string
        commented_yaml["language_backend"] = self.language_backend.value

        # convert ls_config to dict
        commented_yaml["ls_config"] = dataclasses.asdict(self.ls_config)

        # transfer comments from the template file
        # NOTE: The template file now uses leading comments, but we previously used trailing comments,
        #       so we apply a conversion, which detects the old style and transforms it.
        # For some keys, we force updates, because old comments are problematic/misleading.
        normalise_yaml_comments(commented_yaml, YamlCommentNormalisation.LEADING_WITH_CONVERSION_FROM_TRAILING)
        template_yaml = load_yaml(SERENA_CONFIG_TEMPLATE_FILE, comment_normalisation=YamlCommentNormalisation.LEADING)
        transfer_missing_yaml_comments(template_yaml, commented_yaml, YamlCommentNormalisation.LEADING, forced_update_keys=["projects"])

        save_yaml(self.config_file_path, commented_yaml)

    def propagate_settings(self) -> None:
        """
        Propagate settings from this configuration to individual components that are statically configured
        """
        from serena.tools import JetBrainsPluginClient

        JetBrainsPluginClient.set_server_address(self.jetbrains_plugin_server_address)
