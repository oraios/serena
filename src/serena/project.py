import logging
import os
import re
import shutil
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

import pathspec
from sensai.util.logging import LogTime
from sensai.util.string import TextBuilder, ToStringMixin

from serena.config.serena_config import (
    ProjectConfig,
    SerenaConfig,
    SerenaPaths,
)
from serena.constants import SERENA_FILE_ENCODING
from serena.ls_manager import LanguageServerFactory, LanguageServerManager
from serena.util.file_system import GitignoreParser, match_path
from serena.util.text_utils import ContentReplacer, MatchedConsecutiveLines, search_files
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import FileUtils

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

log = logging.getLogger(__name__)


class MemoriesManager:
    GLOBAL_TOPIC = "global"
    _global_memory_dir = SerenaPaths().global_memories_path

    def __init__(
        self,
        serena_data_folder: str | Path | None,
        read_only_memory_patterns: Sequence[str] = (),
        ignored_memory_patterns: Sequence[str] = (),
    ):
        """
        :param serena_data_folder: the absolute path to the project's .serena data folder
        :param read_only_memory_patterns: whether to allow writing global memories in tool execution contexts
        :param ignored_memory_patterns: regex patterns for memories to completely exclude from listing, reading, and writing.
            Matching memories will not appear in list_memories or activate_project output and cannot be accessed
            via read_memory or write_memory. Use read_file on the raw path to access ignored memory files.
        """
        self._project_memory_dir: Path | None = None
        if serena_data_folder is not None:
            self._project_memory_dir = Path(serena_data_folder) / "memories"
            self._project_memory_dir.mkdir(parents=True, exist_ok=True)
        self._encoding = SERENA_FILE_ENCODING
        self._read_only_memory_patterns = [re.compile(pattern) for pattern in set(read_only_memory_patterns)]
        self._ignored_memory_patterns = [re.compile(pattern) for pattern in set(ignored_memory_patterns)]

    def _is_read_only_memory(self, name: str) -> bool:
        for pattern in self._read_only_memory_patterns:
            if pattern.fullmatch(name):
                return True
        return False

    def _is_ignored_memory(self, name: str) -> bool:
        for pattern in self._ignored_memory_patterns:
            if pattern.fullmatch(name):
                return True
        return False

    def _check_not_ignored(self, name: str) -> None:
        if self._is_ignored_memory(name):
            raise ValueError(
                f"Memory '{name}' matches an ignored_memory_patterns pattern and cannot be accessed. "
                f"Use the read_file tool on the raw file path instead."
            )

    def _is_global(self, name: str) -> bool:
        return name == self.GLOBAL_TOPIC or name.startswith(self.GLOBAL_TOPIC + "/")

    def get_memory_file_path(self, name: str) -> Path:
        # Strip .md extension if present
        name = name.replace(".md", "").replace(os.sep, "/")
        parts = name.split("/")
        if ".." in parts:
            raise ValueError(f"Memory name cannot contain '..' segments for security reasons. Got: {name}")

        if self._is_global(name):
            if name == self.GLOBAL_TOPIC:
                raise ValueError(
                    f'Bare "{self.GLOBAL_TOPIC}" is not a valid memory name. Use "{self.GLOBAL_TOPIC}/<name>" to address a global memory.'
                )
            # Strip "global/" prefix and resolve against global dir
            sub_name = name[len(self.GLOBAL_TOPIC) + 1 :]
            parts = sub_name.split("/")
            filename = f"{parts[-1]}.md"
            if len(parts) > 1:
                subdir = self._global_memory_dir / "/".join(parts[:-1])
                subdir.mkdir(parents=True, exist_ok=True)
                return subdir / filename
            return self._global_memory_dir / filename

        # Project-local memory
        assert self._project_memory_dir is not None, "Project dir was not passed at initialization"

        filename = f"{parts[-1]}.md"

        if len(parts) > 1:
            # Create subdirectory path
            subdir = self._project_memory_dir / "/".join(parts[:-1])
            subdir.mkdir(parents=True, exist_ok=True)
            return subdir / filename

        return self._project_memory_dir / filename

    def _check_write_access(self, name: str, is_tool_context: bool) -> None:
        # in tool context, memories can be read-only
        if is_tool_context and self._is_read_only_memory(name):
            raise PermissionError(f"Attempted to write to read_only memory: '{name}')")

    def load_memory(self, name: str) -> str:
        self._check_not_ignored(name)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory file {name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding=self._encoding) as f:
            return f.read()

    def save_memory(self, name: str, content: str, is_tool_context: bool) -> str:
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        with open(memory_file_path, "w", encoding=self._encoding) as f:
            f.write(content)
        return f"Memory {name} written."

    class MemoriesList:
        def __init__(self) -> None:
            self.memories: list[str] = []
            self.read_only_memories: list[str] = []

        def __len__(self) -> int:
            return len(self.memories) + len(self.read_only_memories)

        def add(self, memory_name: str, is_read_only: bool) -> None:
            if is_read_only:
                self.read_only_memories.append(memory_name)
            else:
                self.memories.append(memory_name)

        def extend(self, other: "MemoriesManager.MemoriesList") -> None:
            self.memories.extend(other.memories)
            self.read_only_memories.extend(other.read_only_memories)

        def to_dict(self) -> dict[str, list[str]]:
            result = {}
            if self.memories:
                result["memories"] = sorted(self.memories)
            if self.read_only_memories:
                result["read_only_memories"] = sorted(self.read_only_memories)
            return result

        def get_full_list(self) -> list[str]:
            return sorted(self.memories + self.read_only_memories)

    def _list_memories(self, search_dir: Path, base_dir: Path, prefix: str = "") -> MemoriesList:
        result = self.MemoriesList()
        if not search_dir.exists():
            return result
        for md_file in search_dir.rglob("*.md"):
            rel = str(md_file.relative_to(base_dir).with_suffix("")).replace(os.sep, "/")
            memory_name = prefix + rel
            if self._is_ignored_memory(memory_name):
                continue
            result.add(memory_name, is_read_only=self._is_read_only_memory(memory_name))
        return result

    def list_global_memories(self, subtopic: str = "") -> MemoriesList:
        dir_path = self._global_memory_dir
        if subtopic:
            dir_path = dir_path / subtopic.replace("/", os.sep)
        return self._list_memories(dir_path, self._global_memory_dir, self.GLOBAL_TOPIC + "/")

    def list_project_memories(self, topic: str = "") -> MemoriesList:
        assert self._project_memory_dir is not None, "Project dir was not passed at initialization"
        dir_path = self._project_memory_dir
        if topic:
            dir_path = dir_path / topic.replace("/", os.sep)
        return self._list_memories(dir_path, self._project_memory_dir)

    def list_memories(self, topic: str = "") -> MemoriesList:
        """
        Lists all memories, optionally filtered by topic.
        If the topic is omitted, both global and project-specific memories are returned.
        """
        memories: MemoriesManager.MemoriesList

        if topic:
            if self._is_global(topic):
                topic_parts = topic.split("/")
                subtopic = "/".join(topic_parts[1:])
                memories = self.list_global_memories(subtopic=subtopic)
            else:
                memories = self.list_project_memories(topic=topic)
        else:
            memories = self.list_project_memories()
            memories.extend(self.list_global_memories())

        return memories

    def delete_memory(self, name: str, is_tool_context: bool) -> str:
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory {name} not found."
        memory_file_path.unlink()
        return f"Memory {name} deleted."

    def move_memory(self, old_name: str, new_name: str, is_tool_context: bool) -> str:
        """
        Rename or move a memory file.
        Moving between global and project scope (e.g. "global/foo" -> "bar") is supported.
        """
        self._check_not_ignored(old_name)
        self._check_not_ignored(new_name)
        self._check_write_access(new_name, is_tool_context)

        old_path = self.get_memory_file_path(old_name)
        new_path = self.get_memory_file_path(new_name)

        if not old_path.exists():
            raise FileNotFoundError(f"Memory {old_name} not found.")
        if new_path.exists():
            raise FileExistsError(f"Memory {new_name} already exists.")

        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(old_path, new_path)

        return f"Memory renamed from {old_name} to {new_name}."

    def edit_memory(
        self, name: str, needle: str, repl: str, mode: Literal["literal", "regex"], allow_multiple_occurrences: bool, is_tool_context: bool
    ) -> str:
        """
        Edit a memory by replacing content matching a pattern.

        :param name: the memory name
        :param needle: the string or regex to search for
        :param repl: the replacement string
        :param mode: "literal" or "regex"
        :param allow_multiple_occurrences:
        """
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            raise FileNotFoundError(f"Memory {name} not found.")
        with open(memory_file_path, encoding=self._encoding) as f:
            original_content = f.read()
        replacer = ContentReplacer(mode=mode, allow_multiple_occurrences=allow_multiple_occurrences)
        updated_content = replacer.replace(original_content, needle, repl)
        with open(memory_file_path, "w", encoding=self._encoding) as f:
            f.write(updated_content)
        return f"Memory {name} edited successfully."


class Project(ToStringMixin):
    def __init__(
        self,
        *,
        project_root: str,
        project_config: ProjectConfig,
        serena_config: SerenaConfig,
        is_newly_created: bool = False,
    ):
        assert serena_config is not None
        self.project_root = project_root
        self.project_config = project_config
        self.serena_config = serena_config
        self._serena_data_folder = serena_config.get_project_serena_folder(self.project_root)
        log.info("Serena project data folder: %s", self._serena_data_folder)

        read_only_memory_patterns = serena_config.read_only_memory_patterns + project_config.read_only_memory_patterns
        ignored_memory_patterns = serena_config.ignored_memory_patterns + project_config.ignored_memory_patterns
        self.memories_manager = MemoriesManager(
            self._serena_data_folder,
            read_only_memory_patterns=read_only_memory_patterns,
            ignored_memory_patterns=ignored_memory_patterns,
        )

        # resolve line ending (project -> global)
        self.line_ending = project_config.line_ending or serena_config.line_ending

        self.language_server_manager: LanguageServerManager | None = None
        self._language_server_manager_init_error: Exception | None = None
        self.is_newly_created = is_newly_created
        self._agent: Optional["SerenaAgent"] = None

        # create .gitignore file in the project's Serena data folder if not yet present
        serena_data_gitignore_path = os.path.join(self._serena_data_folder, ".gitignore")
        if not os.path.exists(serena_data_gitignore_path):
            os.makedirs(os.path.dirname(serena_data_gitignore_path), exist_ok=True)
            log.info(f"Creating .gitignore file in {serena_data_gitignore_path}")
            with open(serena_data_gitignore_path, "w", encoding="utf-8") as f:
                f.write(f"/{SolidLanguageServer.CACHE_FOLDER_NAME}\n")
                f.write(f"/{ProjectConfig.SERENA_LOCAL_PROJECT_FILE}\n")

        # prepare ignore spec asynchronously, ensuring immediate project activation.
        self.__ignored_patterns: list[str] | None = None
        self.__ignore_spec: pathspec.PathSpec | None = None
        self._ignore_spec_available = threading.Event()
        threading.Thread(name=f"gather-ignorespec[{self.project_config.project_name}]", target=self._gather_ignorespec, daemon=True).start()

    def _gather_ignorespec(self) -> None:
        with LogTime(f"Gathering ignore spec for project {self.project_config.project_name}", logger=log):
            try:
                # gather ignored paths from the global configuration, project configuration, and gitignore files
                global_ignored_paths = self.serena_config.ignored_paths
                ignored_patterns = list(global_ignored_paths) + list(self.project_config.ignored_paths)
                if len(global_ignored_paths) > 0:
                    log.info(f"Using {len(global_ignored_paths)} ignored paths from the global configuration.")
                    log.debug(f"Global ignored paths: {list(global_ignored_paths)}")
                if len(self.project_config.ignored_paths) > 0:
                    log.info(f"Using {len(self.project_config.ignored_paths)} ignored paths from the project configuration.")
                    log.debug(f"Project ignored paths: {self.project_config.ignored_paths}")
                log.debug(f"Combined ignored patterns: {ignored_patterns}")
                if self.project_config.ignore_all_files_in_gitignore:
                    gitignore_parser = GitignoreParser(self.project_root)
                    for spec in gitignore_parser.get_ignore_specs():
                        log.debug(f"Adding {len(spec.patterns)} patterns from {spec.file_path} to the ignored paths.")
                        ignored_patterns.extend(spec.patterns)
                self.__ignored_patterns = ignored_patterns

                # Set up the pathspec matcher for the ignored paths
                # for all absolute paths in ignored_paths, convert them to relative paths
                processed_patterns = []
                for pattern in ignored_patterns:
                    # Normalize separators (pathspec expects forward slashes)
                    pattern = pattern.replace(os.path.sep, "/")
                    processed_patterns.append(pattern)
                log.debug(f"Processing {len(processed_patterns)} ignored paths")
                self.__ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, processed_patterns)
            except Exception as e:
                log.error(f"Error while gathering ignore spec for project {self.project_config.project_name}: {e}", exc_info=e)

        self._ignore_spec_available.set()

    def _tostring_includes(self) -> list[str]:
        return []

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return {"root": self.project_root, "name": self.project_name}

    def set_agent(self, agent: "SerenaAgent") -> None:
        self._agent = agent

    @property
    def project_name(self) -> str:
        return self.project_config.project_name

    @classmethod
    def load(
        cls,
        project_root: str | Path,
        serena_config: "SerenaConfig",
        autogenerate: bool = True,
    ) -> "Project":
        assert serena_config is not None
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_config = ProjectConfig.load(project_root, serena_config=serena_config, autogenerate=autogenerate)
        return Project(project_root=str(project_root), project_config=project_config, serena_config=serena_config)

    def save_config(self) -> None:
        """
        Saves the current project configuration to disk.
        """
        self.project_config.save(self.path_to_project_yml())

    def path_to_serena_data_folder(self) -> str:
        return self._serena_data_folder

    def path_to_project_yml(self) -> str:
        return self.serena_config.get_project_yml_location(self.project_root)

    def read_file(self, relative_path: str) -> str:
        """
        Reads a file relative to the project root.

        :param relative_path: the path to the file relative to the project root
        :return: the content of the file
        """
        abs_path = Path(self.project_root) / relative_path
        return FileUtils.read_file(str(abs_path), self.project_config.encoding)

    @property
    def _ignore_spec(self) -> pathspec.PathSpec:
        """
        :return: the pathspec matcher for the paths that were configured to be ignored,
            either explicitly or implicitly through .gitignore files.
        """
        if not self._ignore_spec_available.is_set():
            log.info("Waiting for ignore spec to become available ...")
            self._ignore_spec_available.wait()
            if self.__ignore_spec is not None:
                log.info("Ignore spec is now available for project; proceeding")
        if self.__ignore_spec is None:
            raise ValueError(
                "The ignore spec could not be computed; please check the log for errors and report here: https://github.com/oraios/serena/issues"
            )
        return self.__ignore_spec

    @property
    def _ignored_patterns(self) -> list[str]:
        """
        :return: the list of ignored path patterns
        """
        if not self._ignore_spec_available.is_set():
            log.info("Waiting for ignored patterns to become available ...")
            self._ignore_spec_available.wait()
            if self.__ignored_patterns is not None:
                log.info("Ignored patterns are now available for project; proceeding")
        if self.__ignored_patterns is None:
            raise ValueError(
                "The ignored patterns could not be computed; please check the log for errors and report here: https://github.com/oraios/serena/issues"
            )
        return self.__ignored_patterns

    def _is_ignored_relative_path(self, relative_path: str | Path, ignore_non_source_files: bool = True) -> bool:
        """
        Determine whether an existing path should be ignored based on file type and ignore patterns.
        Raises `FileNotFoundError` if the path does not exist.

        :param relative_path: Relative path to check
        :param ignore_non_source_files: whether files that are not source files (according to the file masks
            determined by the project's programming language) shall be ignored

        :return: whether the path should be ignored
        """
        # special case, never ignore the project root itself
        # If the user ignores hidden files, "." might match against the corresponding PathSpec pattern.
        # The empty string also points to the project root and should never be ignored.
        if str(relative_path) in [".", ""]:
            return False

        abs_path = os.path.join(self.project_root, relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File {abs_path} not found, the ignore check cannot be performed")

        # Check file extension if it's a file
        is_file = os.path.isfile(abs_path)
        if is_file and ignore_non_source_files:
            is_file_in_supported_language = False
            for language in self.project_config.languages:
                fn_matcher = language.get_source_fn_matcher()
                if fn_matcher.is_relevant_filename(abs_path):
                    is_file_in_supported_language = True
                    break
            if not is_file_in_supported_language:
                return True

        # Create normalized path for consistent handling
        rel_path = Path(relative_path)

        # always ignore paths inside .git
        if len(rel_path.parts) > 0 and ".git" in rel_path.parts:
            return True

        return match_path(str(relative_path), self._ignore_spec, root_path=self.project_root)

    def is_ignored_path(self, path: str | Path, ignore_non_source_files: bool = False) -> bool:
        """
        Checks whether the given path is ignored

        :param path: the path to check, can be absolute or relative
        :param ignore_non_source_files: whether to ignore files that are not source files
            (according to the file masks determined by the project's programming language)
        """
        path = Path(path)
        if path.is_absolute():
            try:
                relative_path = path.relative_to(self.project_root)
            except ValueError:
                # If the path is not relative to the project root, we consider it as an absolute path outside the project
                # (which we ignore)
                log.warning(f"Path {path} is not relative to the project root {self.project_root} and was therefore ignored")
                return True
        else:
            relative_path = path

        return self._is_ignored_relative_path(str(relative_path), ignore_non_source_files=ignore_non_source_files)

    def is_path_in_project(self, path: str | Path) -> bool:
        """
        Checks if the given (absolute or relative) path is inside the project directory.

        Note: This is intended to catch cases where ".." segments would lead outside of the project directory,
        but we intentionally allow symlinks, as the assumption is that they point to relevant project files.
        """
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)

        # collapse any ".." or "." segments (purely lexically)
        path = os.path.normpath(path)

        try:
            return os.path.commonpath([self.project_root, path]) == self.project_root
        except ValueError:
            # occurs, in particular, if paths are on different drives on Windows
            return False

    def relative_path_exists(self, relative_path: str) -> bool:
        """
        Checks if the given relative path exists in the project directory.

        :param relative_path: the path to check, relative to the project root
        :return: True if the path exists, False otherwise
        """
        abs_path = Path(self.project_root) / relative_path
        return abs_path.exists()

    def validate_relative_path(self, relative_path: str, require_not_ignored: bool = False) -> None:
        """
        Validates that the given relative path to an existing file/dir is safe to read or edit,
        meaning it's inside the project directory.

        Passing a path to a non-existing file will lead to a `FileNotFoundError`.

        :param relative_path: the path to validate, relative to the project root
        :param require_not_ignored: if True, the path must not be ignored according to the project's ignore settings
        """
        if not self.is_path_in_project(relative_path):
            raise ValueError(f"{relative_path=} points to path outside of the repository root; cannot access for safety reasons")

        if require_not_ignored:
            if self.is_ignored_path(relative_path):
                raise ValueError(f"Path {relative_path} is ignored; cannot access for safety reasons")

    def gather_source_files(self, relative_path: str = "") -> list[str]:
        """Retrieves relative paths of all source files, optionally limited to the given path

        :param relative_path: if provided, restrict search to this path
        """
        rel_file_paths = []
        start_path = os.path.join(self.project_root, relative_path)
        if not os.path.exists(start_path):
            raise FileNotFoundError(f"Relative path {start_path} not found.")
        if os.path.isfile(start_path):
            return [relative_path]
        else:
            for root, dirs, files in os.walk(start_path, followlinks=True):
                # prevent recursion into ignored directories
                dirs[:] = [d for d in dirs if not self.is_ignored_path(os.path.join(root, d))]

                # collect non-ignored files
                for file in files:
                    abs_file_path = os.path.join(root, file)
                    try:
                        if not self.is_ignored_path(abs_file_path, ignore_non_source_files=True):
                            try:
                                rel_file_path = os.path.relpath(abs_file_path, start=self.project_root)
                            except Exception:
                                log.warning(
                                    "Ignoring path '%s' because it appears to be outside of the project root (%s)",
                                    abs_file_path,
                                    self.project_root,
                                )
                                continue
                            rel_file_paths.append(rel_file_path)
                    except FileNotFoundError:
                        log.warning(
                            f"File {abs_file_path} not found (possibly due it being a symlink), skipping it in request_parsed_files",
                        )
            return rel_file_paths

    def search_source_files_for_pattern(
        self,
        pattern: str,
        relative_path: str = "",
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
    ) -> list[MatchedConsecutiveLines]:
        """
        Search for a pattern across all (non-ignored) source files

        :param pattern: Regular expression pattern to search for, either as a compiled Pattern or string
        :param relative_path:
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: Glob pattern to filter which files to include in the search
        :param paths_exclude_glob: Glob pattern to filter which files to exclude from the search. Takes precedence over paths_include_glob.
        :return: List of matched consecutive lines with context
        """
        relative_file_paths = self.gather_source_files(relative_path=relative_path)
        return search_files(
            relative_file_paths,
            pattern,
            root_path=self.project_root,
            file_reader=self.read_file,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
        )

    def retrieve_content_around_line(
        self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> MatchedConsecutiveLines:
        """
        Retrieve the content of the given file around the given line.

        :param relative_file_path: The relative path of the file to retrieve the content from
        :param line: The line number to retrieve the content around
        :param context_lines_before: The number of lines to retrieve before the given line
        :param context_lines_after: The number of lines to retrieve after the given line

        :return MatchedConsecutiveLines: A container with the desired lines.
        """
        file_contents = self.read_file(relative_file_path)
        return MatchedConsecutiveLines.from_file_contents(
            file_contents,
            line=line,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            source_file_path=relative_file_path,
        )

    def create_language_server_manager(self) -> LanguageServerManager:
        """
        Creates the language server manager for the project, starting one language server per configured programming language.

        :return: the language server manager, which is also stored in the project instance
        """
        try:
            # determine timeout to use for LS calls
            tool_timeout = self.serena_config.tool_timeout
            if tool_timeout is None or tool_timeout < 0:
                ls_timeout = None
            else:
                if tool_timeout < 10:
                    raise ValueError(f"Tool timeout must be at least 10 seconds, but is {tool_timeout} seconds")
                ls_timeout = tool_timeout - 5  # the LS timeout is for a single call, it should be smaller than the tool timeout

            # if there is an existing instance, stop its language servers first
            if self.language_server_manager is not None:
                log.info("Stopping existing language server manager ...")
                self.language_server_manager.stop_all()
                self.language_server_manager = None

            log.info(f"Creating language server manager for {self.project_root}")
            self._language_server_manager_init_error = None
            ls_specific_settings = {**self.serena_config.ls_specific_settings, **self.project_config.ls_specific_settings}
            factory = LanguageServerFactory(
                project_root=self.project_root,
                project_data_path=self._serena_data_folder,
                encoding=self.project_config.encoding,
                ignored_patterns=self._ignored_patterns,
                ls_timeout=ls_timeout,
                ls_specific_settings=ls_specific_settings,
                additional_workspace_folders=self.project_config.additional_workspace_folders,
                trace_lsp_communication=self.serena_config.trace_lsp_communication,
            )
            self.language_server_manager = LanguageServerManager.from_languages(self.project_config.languages, factory)
            return self.language_server_manager
        except Exception as e:
            self._language_server_manager_init_error = e
            raise

    def get_language_server_manager_or_raise(self) -> LanguageServerManager:
        if self.language_server_manager is None:
            msg = TextBuilder("The language server manager is not initialized, indicating a problem during project initialisation.")
            if self._language_server_manager_init_error is not None:
                msg.with_text(str(self._language_server_manager_init_error))
            if self._agent is not None:
                msg.with_text("For details, please check the logs. " + self._agent.get_log_inspection_instructions())
            msg.with_text(
                "IMPORTANT: Stop, do not attempt workarounds. Inform the user and wait for further instructions before you continue!"
            )
            raise Exception(msg.build())
        return self.language_server_manager

    def add_language(self, language: Language) -> None:
        """
        Adds a new programming language to the project configuration, starting the corresponding
        language server instance if the LS manager is active.
        The project configuration is saved to disk after adding the language.

        :param language: the programming language to add
        """
        if language in self.project_config.languages:
            log.info(f"Language {language.value} is already present in the project configuration.")
            return

        # start the language server (if the LS manager is active)
        if self.language_server_manager is None:
            log.info("Language server manager is not active; skipping language server startup for the new language.")
        else:
            log.info("Adding and starting the language server for new language %s ...", language.value)
            self.language_server_manager.add_language_server(language)

        # update the project configuration
        self.project_config.languages.append(language)
        self.save_config()

    def remove_language(self, language: Language) -> None:
        """
        Removes a programming language from the project configuration, stopping the corresponding
        language server instance if the LS manager is active.
        The project configuration is saved to disk after removing the language.

        :param language: the programming language to remove
        """
        if language not in self.project_config.languages:
            log.info(f"Language {language.value} is not present in the project configuration.")
            return
        # update the project configuration
        self.project_config.languages.remove(language)
        self.save_config()

        # stop the language server (if the LS manager is active)
        if self.language_server_manager is None:
            log.info("Language server manager is not active; skipping language server shutdown for the removed language.")
        else:
            log.info("Removing and stopping the language server for language %s ...", language.value)
            self.language_server_manager.remove_language_server(language)

    def shutdown(self, timeout: float = 2.0) -> None:
        if self.language_server_manager is not None:
            self.language_server_manager.stop_all(save_cache=True, timeout=timeout)
            self.language_server_manager = None
