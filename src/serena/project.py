import logging
import os
from pathlib import Path
from typing import Any

import pathspec
from charset_normalizer import from_path

from serena.config.serena_config import DEFAULT_TOOL_TIMEOUT, ProjectConfig
from serena.constants import SERENA_MANAGED_DIR_IN_HOME, SERENA_MANAGED_DIR_NAME
from serena.text_utils import MatchedConsecutiveLines, search_files
from serena.util.file_system import GitignoreParser, match_path
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger
from solidlsp.settings import SolidLSPSettings

log = logging.getLogger(__name__)


class Project:
    def __init__(self, project_root: str, project_config: ProjectConfig, is_newly_created: bool = False):
        self.project_root = project_root
        self.project_config = project_config
        self.is_newly_created = is_newly_created

        # create .gitignore file in the project's Serena data folder if not yet present
        serena_data_gitignore_path = os.path.join(self.path_to_serena_data_folder(), ".gitignore")
        if not os.path.exists(serena_data_gitignore_path):
            os.makedirs(os.path.dirname(serena_data_gitignore_path), exist_ok=True)
            log.info(f"Creating .gitignore file in {serena_data_gitignore_path}")
            with open(serena_data_gitignore_path, "w", encoding="utf-8") as f:
                f.write(f"/{SolidLanguageServer.CACHE_FOLDER_NAME}\n")

        # gather ignored paths from the project configuration and gitignore files
        ignored_patterns = project_config.ignored_paths
        if len(ignored_patterns) > 0:
            log.info(f"Using {len(ignored_patterns)} ignored paths from the explicit project configuration.")
            log.debug(f"Ignored paths: {ignored_patterns}")
        if project_config.ignore_all_files_in_gitignore:
            gitignore_parser = GitignoreParser(self.project_root)
            for spec in gitignore_parser.get_ignore_specs():
                log.debug(f"Adding {len(spec.patterns)} patterns from {spec.file_path} to the ignored paths.")
                ignored_patterns.extend(spec.patterns)
        self._ignored_patterns = ignored_patterns

        # Set up the pathspec matcher for the ignored paths
        # for all absolute paths in ignored_paths, convert them to relative paths
        processed_patterns = []
        for pattern in set(ignored_patterns):
            # Normalize separators (pathspec expects forward slashes)
            pattern = pattern.replace(os.path.sep, "/")
            processed_patterns.append(pattern)
        log.debug(f"Processing {len(processed_patterns)} ignored paths")
        self._ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, processed_patterns)

    @property
    def project_name(self) -> str:
        return self.project_config.project_name

    @property
    def language(self) -> Language:
        return self.project_config.language

    @classmethod
    def load(cls, project_root: str | Path, autogenerate: bool = True) -> "Project":
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_config = ProjectConfig.load(project_root, autogenerate=autogenerate)
        return Project(project_root=str(project_root), project_config=project_config)

    def path_to_serena_data_folder(self) -> str:
        return os.path.join(self.project_root, SERENA_MANAGED_DIR_NAME)

    def path_to_project_yml(self) -> str:
        return os.path.join(self.project_root, self.project_config.rel_path_to_project_yml())

    def read_file(self, relative_path: str) -> str:
        """
        Reads a file relative to the project root.

        :param relative_path: the path to the file relative to the project root
        :return: the content of the file
        """
        abs_path = Path(self.project_root) / relative_path
        if not abs_path.exists():
            raise FileNotFoundError(f"File not found: {abs_path}")
        try:
            return abs_path.read_text(encoding=self.project_config.encoding)
        except UnicodeDecodeError as ude:
            results = from_path(abs_path)
            match = results.best()
            if match:
                return match.raw.decode(match.encoding)
            raise ude

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """
        :return: the pathspec matcher for the paths that were configured to be ignored,
            either explicitly or implicitly through .gitignore files.
        """
        return self._ignore_spec

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
            fn_matcher = self.language.get_source_fn_matcher()
            if not fn_matcher.is_relevant_filename(abs_path):
                return True

        # Create normalized path for consistent handling
        rel_path = Path(relative_path)

        # always ignore paths inside .git
        if len(rel_path.parts) > 0 and rel_path.parts[0] == ".git":
            return True

        return match_path(str(relative_path), self.get_ignore_spec(), root_path=self.project_root)

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
        Note that even relative paths may be outside if they contain ".." or point to symlinks.
        """
        path = Path(path)
        _proj_root = Path(self.project_root)
        if not path.is_absolute():
            path = _proj_root / path

        path = path.resolve()
        return path.is_relative_to(_proj_root)

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

    def create_language_server(
        self,
        log_level: int = logging.INFO,
        ls_timeout: float | None = DEFAULT_TOOL_TIMEOUT - 5,
        trace_lsp_communication: bool = False,
        ls_specific_settings: dict[Language, Any] | None = None,
    ) -> SolidLanguageServer:
        """
        Create a language server for a project. Note that you will have to start it
        before performing any LS operations.

        :param project: either a path to the project root or a ProjectConfig instance.
            If no project.yml is found, the default project configuration will be used.
        :param log_level: the log level for the language server
        :param ls_timeout: the timeout for the language server
        :param trace_lsp_communication: whether to trace LSP communication
        :param ls_specific_settings: optional LS specific configuration of the language server,
            see docstrings in the inits of subclasses of SolidLanguageServer to see what values may be passed.
        :return: the language server
        """
        ls_config = LanguageServerConfig(
            code_language=self.language,
            ignored_paths=self._ignored_patterns,
            trace_lsp_communication=trace_lsp_communication,
            encoding=self.project_config.encoding,
        )
        ls_logger = LanguageServerLogger(log_level=log_level)

        log.info(f"Creating language server instance for {self.project_root}.")
        return SolidLanguageServer.create(
            ls_config,
            ls_logger,
            self.project_root,
            timeout=ls_timeout,
            solidlsp_settings=SolidLSPSettings(
                solidlsp_dir=SERENA_MANAGED_DIR_IN_HOME,
                project_data_relative_path=SERENA_MANAGED_DIR_NAME,
                ls_specific_settings=ls_specific_settings or {},
            ),
        )
