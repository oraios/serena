import logging
import os
from pathlib import Path

import pathspec

from serena.config.serena_config import DEFAULT_TOOL_TIMEOUT, ProjectConfig
from serena.text_utils import MatchedConsecutiveLines, search_files
from serena.util.file_system import GitignoreParser, match_path
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language, LanguageServerConfig
from solidlsp.ls_logger import LanguageServerLogger

log = logging.getLogger(__name__)


class Project:
    def __init__(self, project_root: str, project_config: ProjectConfig, is_newly_created: bool = False):
        self.project_root = project_root
        self.project_config = project_config
        self.is_newly_created = is_newly_created

        # gather ignored paths from the project configuration and gitignore files
        ignored_patterns = project_config.ignored_paths
        if len(ignored_patterns) > 0:
            log.info(f"Using {len(ignored_patterns)} ignored paths from the explicit project configuration.")
            log.debug(f"Ignored paths: {ignored_patterns}")
        if project_config.ignore_all_files_in_gitignore:
            log.info(f"Parsing all gitignore files in {self.project_root}")
            gitignore_parser = GitignoreParser(self.project_root)
            log.info(f"Found {len(gitignore_parser.get_ignore_specs())} gitignore files.")
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
        return abs_path.read_text(encoding=self.project_config.encoding)

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """
        :return: the pathspec matcher for the paths that were configured to be ignored,
            either explicitly or implicitly through .gitignore files.
        """
        return self._ignore_spec

    def _is_ignored_dirname(self, dirname: str) -> bool:
        return dirname.startswith(".")

    def _is_ignored_relative_path(self, relative_path: str, ignore_non_source_files: bool = True) -> bool:
        """
        Determine whether a path should be ignored based on file type and ignore patterns.

        :param relative_path: Relative path to check
        :param ignore_non_source_files: whether files that are not source files (according to the file masks
            determined by the project's programming language) shall be ignored

        :return: whether the path should be ignored
        """
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

        # Check each part of the path against always fulfilled ignore conditions
        dir_parts = rel_path.parts
        if is_file:
            dir_parts = dir_parts[:-1]
        for part in dir_parts:
            if not part:  # Skip empty parts (e.g., from leading '/')
                continue
            if self._is_ignored_dirname(part):
                return True

        return match_path(relative_path, self.get_ignore_spec(), root_path=self.project_root)

    def is_ignored_path(self, path: str | Path) -> bool:
        """
        Checks whether the given path is ignored

        :param path: the path to check, can be absolute or relative
        """
        path = Path(path)
        if path.is_absolute():
            relative_path = path.relative_to(self.project_root)
        else:
            relative_path = path

        # always ignore paths inside .git
        if len(relative_path.parts) > 0 and relative_path.parts[0] == ".git":
            return True

        return match_path(str(relative_path), self.get_ignore_spec(), root_path=self.project_root)

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

    def validate_relative_path(self, relative_path: str) -> None:
        """
        Validates that the given relative path is safe to read or edit,
        meaning it's inside the project directory and is not ignored by git.
        """
        if not self.is_path_in_project(relative_path):
            raise ValueError(f"{relative_path=} points to path outside of the repository root; cannot access for safety reasons")

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
                dirs[:] = [d for d in dirs if not self._is_ignored_relative_path(os.path.join(root, d))]
                for file in files:
                    rel_file_path = os.path.relpath(os.path.join(root, file), start=self.project_root)
                    try:
                        if not self._is_ignored_relative_path(rel_file_path):
                            rel_file_paths.append(rel_file_path)
                    except FileNotFoundError:
                        log.warning(
                            f"File {rel_file_path} not found (possibly due it being a symlink), skipping it in request_parsed_files",
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
        intelephense_options: dict[str, int] | None = None,
    ) -> SolidLanguageServer:
        """
        Create a language server for a project. Note that you will have to start it
        before performing any LS operations.

        :param project: either a path to the project root or a ProjectConfig instance.
            If no project.yml is found, the default project configuration will be used.
        :param log_level: the log level for the language server
        :param ls_timeout: the timeout for the language server
        :param trace_lsp_communication: whether to trace LSP communication
        :param intelephense_options: optional configuration options for Intelephense (PHP only)
        :return: the language server
        """
        ls_config = LanguageServerConfig(
            code_language=self.language,
            ignored_paths=self._ignored_patterns,
            trace_lsp_communication=trace_lsp_communication,
        )
        ls_logger = LanguageServerLogger(log_level=log_level)

        log.info(f"Creating language server instance for {self.project_root}.")

        # Pass intelephense_options if provided and language is PHP
        if self.language == Language.PHP and intelephense_options:
            return SolidLanguageServer.create(
                ls_config,
                ls_logger,
                self.project_root,
                timeout=ls_timeout,
                intelephense_options=intelephense_options,
            )
        else:
            return SolidLanguageServer.create(
                ls_config,
                ls_logger,
                self.project_root,
                timeout=ls_timeout,
            )
