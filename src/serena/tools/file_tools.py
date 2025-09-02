"""
File and file system-related tools, specifically for
  * listing directory contents
  * reading files
  * creating files
  * editing at the file level
"""

import json
import logging
import os
import re
from collections.abc import Generator
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from serena.text_utils import LineType, MatchedConsecutiveLines, search_files_chunked_with_state
from serena.tools import SUCCESS_RESULT, TOOL_DEFAULT_MAX_ANSWER_LENGTH, EditedFileContext, Tool, ToolMarkerCanEdit, ToolMarkerOptional
from serena.util.file_system import scan_directory


class ReadFileTool(Tool):
    """
    Reads a file within the project directory.
    """

    def apply(
        self, relative_path: str, start_line: int = 0, end_line: int | None = None, max_answer_chars: int = TOOL_DEFAULT_MAX_ANSWER_LENGTH
    ) -> str:
        """
        Reads the given file or a chunk of it. Generally, symbolic operations
        like find_symbol or find_referencing_symbols should be preferred if you know which symbols you are looking for.

        :param relative_path: the relative path to the file to read
        :param start_line: the 0-based index of the first line to be retrieved.
        :param end_line: the 0-based index of the last line to be retrieved (inclusive). If None, read until the end of the file.
        :param max_answer_chars: if the file (chunk) is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: the full text of the file at the given relative path
        """
        self.project.validate_relative_path(relative_path)

        result = self.project.read_file(relative_path)
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
        Write a new file or overwrite an existing file.

        :param relative_path: the relative path to the file to create
        :param content: the (utf-8-encoded) content to write to the file
        :return: a message indicating success or failure
        """
        project_root = self.get_project_root()
        abs_path = (Path(project_root) / relative_path).resolve()
        will_overwrite_existing = abs_path.exists()

        if will_overwrite_existing:
            self.project.validate_relative_path(relative_path)
        else:
            assert abs_path.is_relative_to(
                self.get_project_root()
            ), f"Cannot create file outside of the project directory, got {relative_path=}"

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        answer = f"File created: {relative_path}."
        if will_overwrite_existing:
            answer += " Overwrote existing file."
        return json.dumps(answer)


class ListDirTool(Tool):
    """
    Lists files and directories in the given directory (optionally with recursion).
    """

    def apply(self, relative_path: str, recursive: bool, max_answer_chars: int = TOOL_DEFAULT_MAX_ANSWER_LENGTH) -> str:
        """
        Lists all non-gitignored files and directories in the given directory (optionally with recursion).

        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: a JSON object with the names of directories and files within the given directory
        """
        # Check if the directory exists before validation
        if not self.project.relative_path_exists(relative_path):
            error_info = {
                "error": f"Directory not found: {relative_path}",
                "project_root": self.get_project_root(),
                "hint": "Check if the path is correct relative to the project root",
            }
            return json.dumps(error_info)

        self.project.validate_relative_path(relative_path)

        dirs, files = scan_directory(
            os.path.join(self.get_project_root(), relative_path),
            relative_to=self.get_project_root(),
            recursive=recursive,
            is_ignored_dir=self.project.is_ignored_path,
            is_ignored_file=self.project.is_ignored_path,
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
        self.project.validate_relative_path(relative_path)

        dir_to_scan = os.path.join(self.get_project_root(), relative_path)

        # find the files by ignoring everything that doesn't match
        def is_ignored_file(abs_path: str) -> bool:
            if self.project.is_ignored_path(abs_path):
                return True
            filename = os.path.basename(abs_path)
            return not fnmatch(filename, file_mask)

        dirs, files = scan_directory(
            path=dir_to_scan,
            recursive=True,
            is_ignored_dir=self.project.is_ignored_path,
            is_ignored_file=is_ignored_file,
            relative_to=self.get_project_root(),
        )

        result = json.dumps({"files": files})
        return result


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
            Make sure to escape special characters appropriately, e.g., use `\\n` for a literal `\n`.
        :param allow_multiple_occurrences: if True, the regex may match multiple occurrences in the file
            and all of them will be replaced.
            If this is set to False and the regex matches multiple occurrences, an error will be returned
            (and you may retry with a revised, more specific regex).
        """
        self.project.validate_relative_path(relative_path)
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


class DeleteLinesTool(Tool, ToolMarkerCanEdit, ToolMarkerOptional):
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
        code_editor = self.create_code_editor()
        code_editor.delete_lines(relative_path, start_line, end_line)
        return SUCCESS_RESULT


class ReplaceLinesTool(Tool, ToolMarkerCanEdit, ToolMarkerOptional):
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


class InsertAtLineTool(Tool, ToolMarkerCanEdit, ToolMarkerOptional):
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
        code_editor = self.create_code_editor()
        code_editor.insert_at_line(relative_path, line, content)
        return SUCCESS_RESULT


class SearchForPatternTool(Tool):
    """
    Performs a search for a pattern in the project.
    """

    def apply(
        self,
        substring_pattern: str,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str = "",
        paths_exclude_glob: str = "",
        relative_path: str = "",
        restrict_search_to_code_files: bool = False,
        max_answer_chars: int = TOOL_DEFAULT_MAX_ANSWER_LENGTH,
        max_results: int = 100,
        timeout_seconds: int = 30,
        show_progress: bool = True,
        skip_files: int = 0,
        return_search_state: bool = False,
    ) -> str:
        """
        Offers a flexible search for arbitrary patterns in the codebase, including the
        possibility to search in non-code files.
        Generally, symbolic operations like find_symbol or find_referencing_symbols
        should be preferred if you know which symbols you are looking for.

        Pattern Matching Logic:
            For each match, the returned result will contain the full lines where the
            substring pattern is found, as well as optionally some lines before and after it. The pattern will be compiled with
            DOTALL, meaning that the dot will match all characters including newlines.
            This also means that it never makes sense to have .* at the beginning or end of the pattern,
            but it may make sense to have it in the middle for complex patterns.
            If a pattern matches multiple lines, all those lines will be part of the match.
            Be careful to not use greedy quantifiers unnecessarily, it is usually better to use non-greedy quantifiers like .*? to avoid
            matching too much content.

        File Selection Logic:
            The files in which the search is performed can be restricted very flexibly.
            Using `restrict_search_to_code_files` is useful if you are only interested in code symbols (i.e., those
            symbols that can be manipulated with symbolic tools like find_symbol).
            You can also restrict the search to a specific file or directory,
            and provide glob patterns to include or exclude certain files on top of that.
            The globs are matched against relative file paths from the project root (not to the `relative_path` parameter that
            is used to further restrict the search).
            Smartly combining the various restrictions allows you to perform very targeted searches.


        :param substring_pattern: Regular expression for a substring pattern to search for
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: optional glob pattern specifying files to include in the search.
            Matches against relative file paths from the project root (e.g., "*.py", "src/**/*.ts").
            Only matches files, not directories. If left empty, all non-ignored files will be included.
        :param paths_exclude_glob: optional glob pattern specifying files to exclude from the search.
            Matches against relative file paths from the project root (e.g., "*test*", "**/*_generated.py").
            Takes precedence over paths_include_glob. Only matches files, not directories. If left empty, no files are excluded.
        :param relative_path: only subpaths of this path (relative to the repo root) will be analyzed. If a path to a single
            file is passed, only that will be searched. The path must exist, otherwise a `FileNotFoundError` is raised.
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task. Instead, if the output is too long, you should
            make a stricter query.
        :param restrict_search_to_code_files: whether to restrict the search to only those files where
            analyzed code symbols can be found. Otherwise, will search all non-ignored files.
            Set this to True if your search is only meant to discover code that can be manipulated with symbolic tools.
            For example, for finding classes or methods from a name pattern.
            Setting to False is a better choice if you also want to search in non-code files, like in html or yaml files,
            which is why it is the default.
        :param max_results: Maximum number of results to return (default 100). Search stops after finding this many matches.
        :param timeout_seconds: Maximum time in seconds to spend searching (default 30). Returns partial results if timeout.
        :param show_progress: Whether to log progress during long searches (default True).
        :param skip_files: Number of files to skip at the beginning (for pagination/continuation).
        :param return_search_state: Whether to include pagination info in response for continuing searches.
        :return: A mapping of file paths to lists of matched consecutive lines.
        """
        import time

        abs_path = os.path.join(self.get_project_root(), relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Relative path {relative_path} does not exist.")

        start_time = time.time()

        # Validate the pattern for efficiency
        try:
            re.compile(substring_pattern, re.DOTALL)
        except re.error as e:
            return json.dumps({"error": f"Invalid regex pattern: {e}"})

        try:
            if restrict_search_to_code_files:
                # Use generator for memory efficiency
                file_generator = (
                    self.project.gather_source_files_generator(relative_path=relative_path)
                    if hasattr(self.project, "gather_source_files_generator")
                    else self.project.gather_source_files(relative_path=relative_path)
                )

                if show_progress:
                    log.info(f"Searching code files for pattern: {substring_pattern[:50]}...")

                # Use chunked search with progress and continuation
                matches, search_state = search_files_chunked_with_state(
                    file_generator,
                    substring_pattern,
                    root_path=self.get_project_root(),
                    context_lines_before=context_lines_before,
                    context_lines_after=context_lines_after,
                    paths_include_glob=paths_include_glob.strip(),
                    paths_exclude_glob=paths_exclude_glob.strip(),
                    max_results=max_results,
                    chunk_size=50,  # Process 50 files at a time
                    timeout_seconds=timeout_seconds,
                    show_progress=show_progress,
                    skip_files=skip_files,
                )
            else:
                rel_paths_to_search: list[str] | Generator[str, None, None]
                if os.path.isfile(abs_path):
                    rel_paths_to_search = [relative_path]
                else:
                    # Use generator-based directory scan for memory efficiency
                    from serena.util.file_system import scan_directory_generator

                    rel_paths_generator = scan_directory_generator(
                        path=abs_path,
                        recursive=True,
                        is_ignored_dir=self.project.is_ignored_path,
                        is_ignored_file=self.project.is_ignored_path,
                        relative_to=self.get_project_root(),
                    )
                    rel_paths_to_search = rel_paths_generator

                if show_progress:
                    log.info(f"Searching all files for pattern: {substring_pattern[:50]}...")

                # Use chunked search with progress and continuation
                matches, search_state = search_files_chunked_with_state(
                    rel_paths_to_search,
                    substring_pattern,
                    root_path=self.get_project_root(),
                    context_lines_before=context_lines_before,
                    context_lines_after=context_lines_after,
                    paths_include_glob=paths_include_glob.strip(),
                    paths_exclude_glob=paths_exclude_glob.strip(),
                    max_results=max_results,
                    chunk_size=50,
                    timeout_seconds=timeout_seconds,
                    show_progress=show_progress,
                    skip_files=skip_files,
                )

        except Exception as e:
            log.error(f"Search error: {e}")
            return json.dumps({"error": str(e), "hint": "Try a more specific pattern or search path"})

        elapsed = time.time() - start_time

        if show_progress:
            log.info(f"Search completed in {elapsed:.1f}s, found {len(matches)} matches")

        # Format results
        formatted_matches = self._format_matches(matches[:max_results])

        # Add metadata
        metadata: dict[str, Any] = {
            "total_matches": len(matches),
            "returned_matches": min(len(matches), max_results),
            "search_time_seconds": round(elapsed, 2),
            "files_processed": search_state["files_processed"],
            "files_skipped": search_state["files_skipped_total"],
        }

        # Add pagination info if requested or if search was limited
        if return_search_state or search_state["has_more_files"] or search_state["timed_out"]:
            pagination = {
                "has_more_files": search_state["has_more_files"],
                "next_skip_files": search_state["next_skip_files"],
                "timed_out": search_state["timed_out"],
            }

            if search_state["timed_out"]:
                pagination["resume_hint"] = f"Search timed out. To continue, use skip_files={search_state['next_skip_files']}"
            elif search_state["has_more_files"]:
                pagination["resume_hint"] = f"More files available. To continue, use skip_files={search_state['next_skip_files']}"

            metadata["pagination"] = pagination

        if len(matches) > max_results:
            metadata["note"] = f"Showing first {max_results} of {len(matches)} total matches. Use more specific patterns to reduce results."

        final_result = {"metadata": metadata, "matches": formatted_matches}

        result_json = json.dumps(final_result)
        return self._limit_length(result_json, max_answer_chars)

    def _format_matches(self, matches: list[MatchedConsecutiveLines]) -> dict[str, list[str]]:
        """Format matches for JSON output."""
        result: dict[str, list[str]] = {}
        for match in matches:
            file_path = match.source_file_path or "unknown"
            if file_path not in result:
                result[file_path] = []

            # Format lines with line numbers
            formatted_lines = []
            for line in match.lines:
                prefix = "  > " if line.match_type == LineType.MATCH else "    "
                formatted_lines.append(f"{prefix}{line.line_number:4d}: {line.line_content}")

            result[file_path].append("\n".join(formatted_lines))

        return result
