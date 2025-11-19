import dataclasses
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self, TypeVar

from ruamel.yaml.comments import CommentedMap
from sensai.util import logging
from sensai.util.logging import LogTime
from sensai.util.string import ToStringMixin

from serena.constants import (
    DEFAULT_SOURCE_FILE_ENCODING,
    PROJECT_TEMPLATE_FILE,
    SERENA_MANAGED_DIR_NAME,
)
from serena.util.general import load_yaml, save_yaml
from serena.util.inspection import determine_programming_language_composition
from solidlsp.ls_config import Language

log = logging.getLogger(__name__)
DictType = dict | CommentedMap
TDict = TypeVar("TDict", bound=DictType)


@dataclass
class ToolInclusionDefinition:
    excluded_tools: Iterable[str] = ()
    included_optional_tools: Iterable[str] = ()


@dataclass(kw_only=True)
class ProjectConfig(ToolInclusionDefinition, ToStringMixin):
    project_name: str
    languages: list[Language]
    ignored_paths: list[str] = field(default_factory=list)
    read_only: bool = False
    ignore_all_files_in_gitignore: bool = True
    initial_prompt: str = ""
    encoding: str = DEFAULT_SOURCE_FILE_ENCODING

    SERENA_DEFAULT_PROJECT_FILE = "project.yml"

    def _tostring_includes(self) -> list[str]:
        return ["project_name"]

    @classmethod
    def autogenerate(
        cls,
        project_root: str | Path,
        project_name: str | None = None,
        languages: list[Language] | None = None,
        save_to_disk: bool = True,
    ) -> Self:
        """
        Autogenerate a project configuration for a given project root.

        :param project_root: the path to the project root
        :param project_name: the name of the project; if None, the name of the project will be the name of the directory
            containing the project
        :param languages: the languages of the project; if None, they will be determined automatically
        :param save_to_disk: whether to save the project configuration to disk
        :return: the project configuration
        """
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        with LogTime("Project configuration auto-generation", logger=log):
            project_name = project_name or project_root.name
            if languages is None:
                language_composition = determine_programming_language_composition(str(project_root))
                if len(language_composition) == 0:
                    raise ValueError(
                        f"No source files found in {project_root}\n\n"
                        f"To use Serena with this project, you need to either:\n"
                        f"1. Add source files in one of the supported languages (Python, JavaScript/TypeScript, Java, C#, Rust, Go, Ruby, C++, PHP, Swift, Elixir, Terraform, Bash)\n"
                        f"2. Create a project configuration file manually at:\n"
                        f"   {os.path.join(project_root, cls.rel_path_to_project_yml())}\n\n"
                        f"Example project.yml:\n"
                        f"  project_name: {project_name}\n"
                        f"  language: python  # or typescript, java, csharp, rust, go, ruby, cpp, php, swift, elixir, terraform, bash\n"
                    )
                # find the language with the highest percentage
                dominant_language = max(language_composition.keys(), key=lambda lang: language_composition[lang])
                languages_to_use = [dominant_language]
            else:
                languages_to_use = [lang.value for lang in languages]
            config_with_comments = cls.load_commented_map(PROJECT_TEMPLATE_FILE)
            config_with_comments["project_name"] = project_name
            config_with_comments["languages"] = languages_to_use
            if save_to_disk:
                save_yaml(str(project_root / cls.rel_path_to_project_yml()), config_with_comments, preserve_comments=True)
            return cls._from_dict(config_with_comments)

    @classmethod
    def rel_path_to_project_yml(cls) -> str:
        return os.path.join(SERENA_MANAGED_DIR_NAME, cls.SERENA_DEFAULT_PROJECT_FILE)

    @classmethod
    def _apply_defaults_to_dict(cls, data: TDict) -> TDict:
        # apply defaults for new fields
        data["languages"] = data.get("languages", [])
        data["ignored_paths"] = data.get("ignored_paths", [])
        data["excluded_tools"] = data.get("excluded_tools", [])
        data["included_optional_tools"] = data.get("included_optional_tools", [])
        data["read_only"] = data.get("read_only", False)
        data["ignore_all_files_in_gitignore"] = data.get("ignore_all_files_in_gitignore", True)
        data["initial_prompt"] = data.get("initial_prompt", "")
        data["encoding"] = data.get("encoding", DEFAULT_SOURCE_FILE_ENCODING)

        # backward compatibility: handle single "language" field
        if len(data["languages"]) == 0 and "language" in data:
            data["languages"] = [data["language"]]
        if "language" in data:
            del data["language"]

        return data

    @classmethod
    def load_commented_map(cls, yml_path: str) -> CommentedMap:
        """
        Load the project configuration as a CommentedMap, preserving comments and ensuring
        completeness of the configuration by applying default values for missing fields
        and backward compatibility adjustments.

        :param yml_path: the path to the project.yml file
        :return: a CommentedMap representing a full project configuration
        """
        data = load_yaml(yml_path, preserve_comments=True)
        return cls._apply_defaults_to_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> Self:
        """
        Create a ProjectConfig instance from a (full) configuration dictionary
        """
        lang_name_mapping = {"javascript": "typescript"}
        languages: list[Language] = []
        for language_str in data["languages"]:
            try:
                language_str = language_str.lower()
                if language_str in lang_name_mapping:
                    language_str = lang_name_mapping[language_str]
                language = Language(language_str)
                languages.append(language)
            except ValueError as e:
                raise ValueError(f"Invalid language: {data['language']}.\nValid language_strings are: {[l.value for l in Language]}") from e

        return cls(
            project_name=data["project_name"],
            languages=languages,
            ignored_paths=data["ignored_paths"],
            excluded_tools=data["excluded_tools"],
            included_optional_tools=data["included_optional_tools"],
            read_only=data["read_only"],
            ignore_all_files_in_gitignore=data["ignore_all_files_in_gitignore"],
            initial_prompt=data["initial_prompt"],
            encoding=data["encoding"],
        )

    def to_yaml_dict(self) -> dict:
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
        if not yaml_path.exists():
            if autogenerate:
                return cls.autogenerate(project_root)
            else:
                raise FileNotFoundError(f"Project configuration file not found: {yaml_path}")
        yaml_data = cls.load_commented_map(str(yaml_path))
        if "project_name" not in yaml_data:
            yaml_data["project_name"] = project_root.name
        return cls._from_dict(yaml_data)
