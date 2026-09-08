# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of operations on the project's files.
"""

import os
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from serena.tools import CreateTextFileTool, FindFileTool, ListDirTool, ReadFileTool, SearchForPatternTool
from serena.util.file_system import scan_directory
from serena.util.text_utils import MatchedConsecutiveLines
from solidlsp.ls_utils import TextUtils

from ..facade import FacadeApi, ReferencedType, facade_method
from ..representable import Renderer, RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class FileContent(RepresentableViaRenderer):
    """
    The content of a file (or of a range of its lines): `text` (the joined lines) and `lines`.
    """

    def __init__(self, lines: list[str], renderer: "FileContentRenderer"):
        """
        :param lines: the lines (without line breaks)
        :param renderer: the renderer to use for representing the content
        """
        super().__init__(renderer)
        self.lines = lines

    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class FileContentRenderer(Renderer[FileContent]):
    def render(self, obj: FileContent) -> str:
        return self._limit_length(obj.text)


class DirectoryListing(RepresentableViaRenderer):
    """
    The entries of a directory: `dirs` and `files` (relative paths).
    """

    def __init__(self, dirs: list[str], files: list[str], renderer: "DirectoryListingRenderer"):
        """
        :param dirs: the relative paths of the directories
        :param files: the relative paths of the files
        :param renderer: the renderer to use for representing the listing
        """
        super().__init__(renderer)
        self.dirs = dirs
        self.files = files

    dirs: list[str]
    files: list[str]


class DirectoryListingRenderer(Renderer[DirectoryListing]):
    def render(self, obj: DirectoryListing) -> str:
        return self._limit_length(self._to_json({"dirs": obj.dirs, "files": obj.files}))


class PatternMatches(RepresentableViaRenderer):
    """
    The matches of a pattern search (`MatchedConsecutiveLines`).
    """

    def __init__(self, matches: list[MatchedConsecutiveLines], renderer: "PatternMatchesRenderer"):
        """
        :param matches: the matches
        :param renderer: the renderer to use for representing the matches
        """
        super().__init__(renderer)
        self.matches = matches

    matches: list[MatchedConsecutiveLines]

    def __len__(self) -> int:
        return len(self.matches)

    def matches_by_file_(self) -> dict[str, list[MatchedConsecutiveLines]]:
        result: defaultdict[str, list[MatchedConsecutiveLines]] = defaultdict(list)
        for match in self.matches:
            assert match.source_file_path is not None
            result[match.source_file_path].append(match)
        return result


class PatternMatchesRenderer(Renderer[PatternMatches]):
    """
    Renders matches as a mapping from file paths to matched line blocks (with context), falling back to progressively
    shorter representations (first lines, truncated first lines, line numbers, per-file counts, a summary) if the
    length limit is exceeded.
    """

    _TEXT_TRUNCATE = 60

    def render(self, obj: PatternMatches) -> str:
        matches_by_file = obj.matches_by_file_()
        file_to_matches = {path: [m.to_display_string() for m in matches] for path, matches in matches_by_file.items()}

        # capture lightweight match data for shortening before serialization
        match_lines_by_file = {
            path: [{"line": m.matched_lines[0].line_number, "text": m.matched_lines[0].line_content.strip()} for m in matches]
            for path, matches in matches_by_file.items()
        }

        # shortened result closures, from least to most aggressive shortening
        def render_first_lines(truncate: bool) -> str:
            """Render each match's first line, either in full or truncated to a fixed length."""

            def entry_text(text: str) -> str:
                if truncate and len(text) > self._TEXT_TRUNCATE:
                    return text[: self._TEXT_TRUNCATE] + "..."
                return text

            compact = {
                path: [{"line": m["line"], "text": entry_text(str(m["text"]))} for m in lines]
                for path, lines in match_lines_by_file.items()
            }
            if truncate:
                header = (
                    f"Matched lines (text over {self._TEXT_TRUNCATE} chars is truncated, marked with a trailing '...'); "
                    "use read_file with the line numbers for full content:"
                )
            else:
                header = "Matched lines per file; use read_file with the line numbers for surrounding context:"
            return f"{header}\n{self._to_json(compact)}"

        def make_first_lines_full() -> str:
            return render_first_lines(truncate=False)

        def make_first_lines_truncated() -> str:
            return render_first_lines(truncate=True)

        def make_line_numbers_only() -> str:
            numbers = {path: [m["line"] for m in lines] for path, lines in match_lines_by_file.items()}
            return f"Match lines per file:\n{self._to_json(numbers)}"

        def make_per_file_counts() -> str:
            counts = {path: len(lines) for path, lines in match_lines_by_file.items()}
            return f"Match counts per file:\n{self._to_json(counts)}"

        def make_summary() -> str:
            return f"Found {len(obj)} matches in {len(match_lines_by_file)} files."

        return self._limit_length(
            self._to_json(file_to_matches),
            shortened_result_factories=[
                make_first_lines_full,
                make_first_lines_truncated,
                make_line_numbers_only,
                make_per_file_counts,
                make_summary,
            ],
        )


class FsApi(FacadeApi):
    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(
            agent,
            name="fs",
            description="the project's files as units (as opposed to their content, see `edit`)",
            types=[
                ReferencedType(
                    MatchedConsecutiveLines, members=["source_file_path", "matched_lines", "start_line", "end_line", "to_display_string"]
                ),
            ],
        )

    @facade_method(corresponding_tool=ReadFileTool)
    def read_file(self, relative_path: str, start_line: int = 0, end_line: int | None = None, max_answer_chars: int = -1) -> FileContent:
        """
        Reads the given file or a range of its lines.

        :param relative_path: the relative path to the file to read
        :param start_line: the 0-based index of the first line to be retrieved, negative values count from the end of the file.
        :param end_line: the 0-based index of the last line to be retrieved (inclusive). If None, read until the end of the file.
        :param max_answer_chars: if the rendered content is longer than this number of characters, no content is rendered;
            -1 for the configured default. Don't adjust unless there is really no other way to get the content required for the task.
        :return: the content
        """
        project = self._get_project()
        project.validate_relative_path(relative_path)

        # read lines, using the same (LSP-compliant) notion of line breaks as the line-based editing operations
        lines = TextUtils.split_lines(project.read_file(relative_path))
        lines = lines[start_line:] if end_line is None else lines[start_line : end_line + 1]
        return FileContent(lines, FileContentRenderer(self._agent, max_answer_chars))

    @facade_method(can_edit=True, corresponding_tool=CreateTextFileTool)
    def create_text_file(self, relative_path: str, content: str) -> str:
        """
        Writes a new file or overwrites an existing file with the given content.

        :param relative_path: the relative path to the file to create
        :param content: the (appropriately encoded) content to write to the file
        :return: a message indicating success
        """
        project = self._get_project()
        project_root = Path(project.project_root)
        abs_path = (project_root / relative_path).resolve()
        will_overwrite_existing = abs_path.exists()

        # validate the destination path
        if will_overwrite_existing:
            project.validate_relative_path(relative_path)
        else:
            assert abs_path.is_relative_to(project_root), f"Cannot create file outside of the project directory, got {relative_path=}"

        # write the file
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding=project.project_config.encoding, newline=project.line_ending.newline_str)
        answer = f"File created: {relative_path}."
        if will_overwrite_existing:
            answer += " Overwrote existing file."
        return answer

    @facade_method(corresponding_tool=ListDirTool)
    def list_dir(
        self, relative_path: str, recursive: bool, skip_ignored_files: bool = False, max_answer_chars: int = -1
    ) -> DirectoryListing:
        """
        Lists files and directories in the given directory (optionally with recursion).

        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param skip_ignored_files: whether to skip files and directories that are ignored
        :param max_answer_chars: if the rendered listing is longer than this number of characters, no content is rendered;
            -1 for the configured default. Don't adjust unless there is really no other way to get the content required for the task.
        :return: the listing
        """
        project = self._get_project()
        if not project.relative_path_exists(relative_path):
            raise FileNotFoundError(f"Directory not found: {relative_path} (check if the path is correct relative to the project root)")
        project.validate_relative_path(relative_path)

        is_ignored_path_fn = project.get_is_ignored_path_fn(relative_path, skip_ignored_files)
        dirs, files = scan_directory(
            os.path.join(project.project_root, relative_path),
            relative_to=project.project_root,
            recursive=recursive,
            is_ignored_dir=is_ignored_path_fn,
            is_ignored_file=is_ignored_path_fn,
        )
        return DirectoryListing(dirs, files, DirectoryListingRenderer(self._agent, max_answer_chars))

    @facade_method(corresponding_tool=FindFileTool)
    def find_file(self, file_mask: str, relative_path: str) -> list[str]:
        """
        Finds files matching the given file mask within the given relative path.

        :param file_mask: the filename or file mask (using the wildcards * or ?) to search for
        :param relative_path: the relative path to the directory to search in; pass "." to scan the project root
        :return: the relative paths of the matching files
        """
        project = self._get_project()
        project.validate_relative_path(relative_path)

        is_ignored_path_fn = project.get_is_ignored_path_fn(relative_path, skip_ignored_paths=False)

        # find the files by ignoring everything that doesn't match
        def is_ignored_file(abs_path: str) -> bool:
            if is_ignored_path_fn(abs_path):
                return True
            return not fnmatch(os.path.basename(abs_path), file_mask)

        _dirs, files = scan_directory(
            path=os.path.join(project.project_root, relative_path),
            recursive=True,
            is_ignored_dir=is_ignored_path_fn,
            is_ignored_file=is_ignored_file,
            relative_to=project.project_root,
        )
        return files

    @facade_method(corresponding_tool=SearchForPatternTool)
    def search_for_pattern(
        self,
        substring_pattern: str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str = "",
        paths_exclude_glob: str = "",
        relative_path: str = "",
        restrict_search_to_code_files: bool = False,
        skip_ignored_files: bool = True,
        multiline: bool = True,
        max_answer_chars: int = -1,
    ) -> PatternMatches:
        """
        Searches for a regex pattern across project files, returning whole matched lines (plus optional context).
        Prefer symbolic operations if you know which symbols you are looking for!

        :param substring_pattern: regular expression to search for.
        :param context_lines_before: number of context lines to include before each match.
        :param context_lines_after: number of context lines to include after each match.
        :param paths_include_glob: optional glob (relative to project root, e.g. ``"src/**/*.ts"``) restricting which files are searched.
        :param paths_exclude_glob: optional glob to exclude files; takes precedence over `paths_include_glob`.
        :param relative_path: restricts the search to this file or subdirectory of the project root
        :param restrict_search_to_code_files: whether to search only (non-ignored) files containing analyzable code symbols
            (useful when looking for class/method definitions); otherwise also search non-code files.
        :param skip_ignored_files: whether to skip ignored sub-paths (default: True)
        :param multiline: whether to apply multi-line matching (default: True), enabling the flags re.DOTALL and re.MULTILINE
        :param max_answer_chars: if the rendered output exceeds this many characters, a progressively shortened summary is
            rendered instead. -1 for the configured default.
        :return: the matches, rendered as a mapping from file paths to matched consecutive lines (0-based line numbers)
        """
        project = self._get_project()
        relative_path = relative_path.strip()
        if relative_path:
            project.validate_relative_path(relative_path)

        matches = project.search_project_files_for_pattern(
            pattern=substring_pattern,
            relative_path=relative_path,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            paths_include_glob=paths_include_glob.strip(),
            paths_exclude_glob=paths_exclude_glob.strip(),
            multiline=multiline,
            code_files_only=restrict_search_to_code_files,
            skip_ignored_files=skip_ignored_files,
        )
        return PatternMatches(matches, PatternMatchesRenderer(self._agent, max_answer_chars))
