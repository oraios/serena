import fnmatch
import logging
import os
import re
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from joblib import Parallel, delayed

log = logging.getLogger(__name__)


class LineType(StrEnum):
    """Enum for different types of lines in search results."""

    MATCH = "match"
    """Part of the matched lines"""
    BEFORE_MATCH = "prefix"
    """Lines before the match"""
    AFTER_MATCH = "postfix"
    """Lines after the match"""


@dataclass(kw_only=True)
class TextLine:
    """Represents a line of text with information on how it relates to the match."""

    line_number: int
    line_content: str
    match_type: LineType
    """Represents the type of line (match, prefix, postfix)"""

    def get_display_prefix(self) -> str:
        """Get the display prefix for this line based on the match type."""
        if self.match_type == LineType.MATCH:
            return "  >"
        return "..."

    def format_line(self, include_line_numbers: bool = True) -> str:
        """Format the line for display (e.g.,for logging or passing to an LLM).

        :param include_line_numbers: Whether to include the line number in the result.
        """
        prefix = self.get_display_prefix()
        if include_line_numbers:
            line_num = str(self.line_number).rjust(4)
            prefix = f"{prefix}{line_num}"
        return f"{prefix}:{self.line_content}"


@dataclass(kw_only=True)
class MatchedConsecutiveLines:
    """Represents a collection of consecutive lines found through some criterion in a text file or a string.
    May include lines before, after, and matched.
    """

    lines: list[TextLine]
    """All lines in the context of the match. At least one of them is of `match_type` `MATCH`."""
    source_file_path: str | None = None
    """Path to the file where the match was found (Metadata)."""

    # set in post-init
    lines_before_matched: list[TextLine] = field(default_factory=list)
    matched_lines: list[TextLine] = field(default_factory=list)
    lines_after_matched: list[TextLine] = field(default_factory=list)

    def __post_init__(self) -> None:
        for line in self.lines:
            if line.match_type == LineType.BEFORE_MATCH:
                self.lines_before_matched.append(line)
            elif line.match_type == LineType.MATCH:
                self.matched_lines.append(line)
            elif line.match_type == LineType.AFTER_MATCH:
                self.lines_after_matched.append(line)

        assert len(self.matched_lines) > 0, "At least one matched line is required"

    @property
    def start_line(self) -> int:
        return self.lines[0].line_number

    @property
    def end_line(self) -> int:
        return self.lines[-1].line_number

    @property
    def num_matched_lines(self) -> int:
        return len(self.matched_lines)

    def to_display_string(self, include_line_numbers: bool = True) -> str:
        return "\n".join([line.format_line(include_line_numbers) for line in self.lines])

    @classmethod
    def from_file_contents(
        cls, file_contents: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0, source_file_path: str | None = None
    ) -> Self:
        line_contents = file_contents.split("\n")
        start_lineno = max(0, line - context_lines_before)
        end_lineno = min(len(line_contents) - 1, line + context_lines_after)
        text_lines: list[TextLine] = []
        # before the line
        for lineno in range(start_lineno, line):
            text_lines.append(TextLine(line_number=lineno, line_content=line_contents[lineno], match_type=LineType.BEFORE_MATCH))
        # the line
        text_lines.append(TextLine(line_number=line, line_content=line_contents[line], match_type=LineType.MATCH))
        # after the line
        for lineno in range(line + 1, end_lineno + 1):
            text_lines.append(TextLine(line_number=lineno, line_content=line_contents[lineno], match_type=LineType.AFTER_MATCH))

        return cls(lines=text_lines, source_file_path=source_file_path)


def glob_to_regex(glob_pat: str) -> str:
    regex_parts: list[str] = []
    i = 0
    while i < len(glob_pat):
        ch = glob_pat[i]
        if ch == "*":
            regex_parts.append(".*")
        elif ch == "?":
            regex_parts.append(".")
        elif ch == "\\":
            i += 1
            if i < len(glob_pat):
                regex_parts.append(re.escape(glob_pat[i]))
            else:
                regex_parts.append("\\")
        else:
            regex_parts.append(re.escape(ch))
        i += 1
    return "".join(regex_parts)


def search_text(
    pattern: str,
    content: str | None = None,
    source_file_path: str | None = None,
    allow_multiline_match: bool = False,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
    is_glob: bool = False,
) -> list[MatchedConsecutiveLines]:
    """
    Search for a pattern in text content. Supports both regex and glob-like patterns.

    :param pattern: Pattern to search for (regex or glob-like pattern)
    :param content: The text content to search. May be None if source_file_path is provided.
    :param source_file_path: Optional path to the source file. If content is None,
        this has to be passed and the file will be read.
    :param allow_multiline_match: Whether to search across multiple lines. Currently, the default
        option (False) is very inefficient, so it is recommended to set this to True.
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :param is_glob: If True, pattern is treated as a glob-like pattern (e.g., "*.py", "test_??.py")
             and will be converted to regex internally

    :return: List of `TextSearchMatch` objects

    :raises: ValueError if the pattern is not valid

    """
    if source_file_path and content is None:
        with open(source_file_path) as f:
            content = f.read()

    if content is None:
        raise ValueError("Pass either content or source_file_path")

    matches = []
    lines = content.splitlines()
    total_lines = len(lines)

    # Convert pattern to a compiled regex if it's a string
    if is_glob:
        pattern = glob_to_regex(pattern)
    if allow_multiline_match:
        # For multiline matches, we need to use the DOTALL flag to make '.' match newlines
        compiled_pattern = re.compile(pattern, re.DOTALL)
        # Search across the entire content as a single string
        for match in compiled_pattern.finditer(content):
            start_pos = match.start()
            end_pos = match.end()

            # Find the line numbers for the start and end positions
            start_line_num = content[:start_pos].count("\n") + 1
            end_line_num = content[:end_pos].count("\n") + 1

            # Calculate the range of lines to include in the context
            context_start = max(1, start_line_num - context_lines_before)
            context_end = min(total_lines, end_line_num + context_lines_after)

            # Create TextLine objects for the context
            context_lines = []
            for i in range(context_start - 1, context_end):
                line_num = i + 1
                if context_start <= line_num < start_line_num:
                    match_type = LineType.BEFORE_MATCH
                elif end_line_num < line_num <= context_end:
                    match_type = LineType.AFTER_MATCH
                else:
                    match_type = LineType.MATCH

                context_lines.append(TextLine(line_number=line_num, line_content=lines[i], match_type=match_type))

            matches.append(MatchedConsecutiveLines(lines=context_lines, source_file_path=source_file_path))
    else:
        # TODO: extremely inefficient! Since we currently don't use this option in SerenaAgent or LanguageServer,
        #   it is not urgent to fix, but should be either improved or the option should be removed.
        # Search line by line, normal compile without DOTALL
        compiled_pattern = re.compile(pattern)
        for i, line in enumerate(lines):
            line_num = i + 1
            if compiled_pattern.search(line):
                # Calculate the range of lines to include in the context
                context_start = max(0, i - context_lines_before)
                context_end = min(total_lines - 1, i + context_lines_after)

                # Create TextLine objects for the context
                context_lines = []
                for j in range(context_start, context_end + 1):
                    context_line_num = j + 1
                    if j < i:
                        match_type = LineType.BEFORE_MATCH
                    elif j > i:
                        match_type = LineType.AFTER_MATCH
                    else:
                        match_type = LineType.MATCH

                    context_lines.append(TextLine(line_number=context_line_num, line_content=lines[j], match_type=match_type))

                matches.append(MatchedConsecutiveLines(lines=context_lines, source_file_path=source_file_path))

    return matches


def default_file_reader(file_path: str) -> str:
    """Reads using utf-8 encoding."""
    with open(file_path, encoding="utf-8") as f:
        return f.read()


def glob_match(pattern: str, path: str) -> bool:
    """
    Match a file path against a glob pattern.

    Supports standard glob patterns:
    - * matches any number of characters except /
    - ** matches any number of directories (zero or more)
    - ? matches a single character except /
    - [seq] matches any character in seq

    :param pattern: Glob pattern (e.g., 'src/**/*.py', '**agent.py')
    :param path: File path to match against
    :return: True if path matches pattern
    """
    pattern = pattern.replace("\\", "/")  # Normalize backslashes to forward slashes
    path = path.replace("\\", "/")  # Normalize path backslashes to forward slashes

    # Handle ** patterns that should match zero or more directories
    if "**" in pattern:
        # Method 1: Standard fnmatch (matches one or more directories)
        regex1 = fnmatch.translate(pattern)
        if re.match(regex1, path):
            return True

        # Method 2: Handle zero-directory case by removing /** entirely
        # Convert "src/**/test.py" to "src/test.py"
        if "/**/" in pattern:
            zero_dir_pattern = pattern.replace("/**/", "/")
            regex2 = fnmatch.translate(zero_dir_pattern)
            if re.match(regex2, path):
                return True

        # Method 3: Handle leading ** case by removing **/
        # Convert "**/test.py" to "test.py"
        if pattern.startswith("**/"):
            zero_dir_pattern = pattern[3:]  # Remove "**/"
            regex3 = fnmatch.translate(zero_dir_pattern)
            if re.match(regex3, path):
                return True

        return False
    else:
        # Simple pattern without **, use fnmatch directly
        return fnmatch.fnmatch(path, pattern)


def search_text_optimized(
    compiled_pattern: re.Pattern,
    content: str,
    source_file_path: str | None = None,
    allow_multiline_match: bool = True,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
) -> list[MatchedConsecutiveLines]:
    """
    Optimized version of search_text that accepts pre-compiled pattern and uses efficient line indexing.

    :param compiled_pattern: Pre-compiled regex pattern
    :param content: The text content to search
    :param source_file_path: Optional path to the source file
    :param allow_multiline_match: Whether to search across multiple lines
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :return: List of MatchedConsecutiveLines objects
    """
    if not content:
        return []

    matches = []
    lines = content.splitlines()
    total_lines = len(lines)

    # Build line offset index for efficient line number calculation
    line_offsets = [0]
    offset = 0
    for line in lines:
        offset += len(line) + 1  # +1 for newline
        line_offsets.append(offset)

    def pos_to_line_num(pos: int) -> int:
        """Binary search to find line number for a position."""
        left, right = 0, len(line_offsets) - 1
        while left < right:
            mid = (left + right) // 2
            if line_offsets[mid] <= pos:
                left = mid + 1
            else:
                right = mid
        return left

    # Search for matches
    for match in compiled_pattern.finditer(content):
        start_pos = match.start()
        end_pos = match.end()

        # Use binary search for line numbers (much faster than counting newlines)
        start_line_num = pos_to_line_num(start_pos)
        end_line_num = pos_to_line_num(end_pos - 1)  # -1 to handle edge case

        # Calculate the range of lines to include in the context
        context_start = max(1, start_line_num - context_lines_before)
        context_end = min(total_lines, end_line_num + context_lines_after)

        # Create TextLine objects for the context
        context_lines = []
        for i in range(context_start - 1, context_end):
            line_num = i + 1
            if context_start <= line_num < start_line_num:
                match_type = LineType.BEFORE_MATCH
            elif end_line_num < line_num <= context_end:
                match_type = LineType.AFTER_MATCH
            else:
                match_type = LineType.MATCH

            context_lines.append(TextLine(line_number=line_num, line_content=lines[i], match_type=match_type))

        matches.append(MatchedConsecutiveLines(lines=context_lines, source_file_path=source_file_path))

    return matches


def search_files(
    relative_file_paths: list[str],
    pattern: str,
    root_path: str = "",
    file_reader: Callable[[str], str] = default_file_reader,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
    paths_include_glob: str | None = None,
    paths_exclude_glob: str | None = None,
) -> list[MatchedConsecutiveLines]:
    """
    Search for a pattern in a list of files.

    :param relative_file_paths: List of relative file paths in which to search
    :param pattern: Pattern to search for
    :param root_path: Root path to resolve relative paths against (by default, current working directory).
    :param file_reader: Function to read a file, by default will just use os.open.
        All files that can't be read by it will be skipped.
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :param paths_include_glob: Optional glob pattern to include files from the list
    :param paths_exclude_glob: Optional glob pattern to exclude files from the list
    :return: List of MatchedConsecutiveLines objects
    """
    # Pre-compile the regex pattern once for all files (major optimization)
    try:
        compiled_pattern = re.compile(pattern, re.DOTALL)
    except re.error as e:
        log.error(f"Invalid regex pattern: {pattern}. Error: {e}")
        return []

    # Pre-filter paths (done sequentially to avoid overhead)
    # Use proper glob matching instead of gitignore patterns
    filtered_paths = []
    for path in relative_file_paths:
        if paths_include_glob and not glob_match(paths_include_glob, path):
            log.debug(f"Skipping {path}: does not match include pattern {paths_include_glob}")
            continue
        if paths_exclude_glob and glob_match(paths_exclude_glob, path):
            log.debug(f"Skipping {path}: matches exclude pattern {paths_exclude_glob}")
            continue
        filtered_paths.append(path)

    log.info(f"Processing {len(filtered_paths)} files.")

    def process_single_file(path: str) -> dict[str, Any]:
        """Process a single file - this function will be parallelized."""
        try:
            abs_path = os.path.join(root_path, path)
            file_content = file_reader(abs_path)
            search_results = search_text_optimized(
                compiled_pattern,
                content=file_content,
                source_file_path=path,
                allow_multiline_match=True,
                context_lines_before=context_lines_before,
                context_lines_after=context_lines_after,
            )
            if len(search_results) > 0:
                log.debug(f"Found {len(search_results)} matches in {path}")
            return {"path": path, "results": search_results, "error": None}
        except Exception as e:
            log.debug(f"Error processing {path}: {e}")
            return {"path": path, "results": [], "error": str(e)}

    # Use multiprocessing backend for CPU-bound regex operations (avoids GIL)
    # Use loky backend which is more robust than multiprocessing
    results = Parallel(
        n_jobs=-1,
        backend="loky",
        batch_size="auto",
    )(delayed(process_single_file)(path) for path in filtered_paths)

    # Collect results and errors
    matches = []
    skipped_file_error_tuples = []

    for result in results:
        if result["error"]:
            skipped_file_error_tuples.append((result["path"], result["error"]))
        else:
            matches.extend(result["results"])

    if skipped_file_error_tuples:
        log.debug(f"Failed to read {len(skipped_file_error_tuples)} files: {skipped_file_error_tuples}")

    log.info(f"Found {len(matches)} total matches across {len(filtered_paths)} files")
    return matches


def search_files_chunked(
    relative_file_paths: list[str] | Generator[str, None, None],
    pattern: str,
    root_path: str = "",
    file_reader: Callable[[str], str] = default_file_reader,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
    paths_include_glob: str | None = None,
    paths_exclude_glob: str | None = None,
    max_results: int | None = None,
    chunk_size: int = 100,
    timeout_seconds: int | None = None,
    show_progress: bool = True,
) -> list[MatchedConsecutiveLines]:
    """
    Chunked version of search_files that processes files in batches and supports early termination.
    Optimized for large codebases (6000+ files, 1M+ LOC).

    :param relative_file_paths: List or generator of relative file paths
    :param pattern: Pattern to search for
    :param root_path: Root path to resolve relative paths against
    :param file_reader: Function to read a file
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :param paths_include_glob: Optional glob pattern to include files
    :param paths_exclude_glob: Optional glob pattern to exclude files
    :param max_results: Maximum number of results to return (early termination)
    :param chunk_size: Number of files to process in each batch
    :param timeout_seconds: Maximum time to spend searching
    :param show_progress: Whether to log progress updates
    :return: List of MatchedConsecutiveLines objects
    """
    start_time = time.time()

    # Pre-compile the regex pattern once
    try:
        compiled_pattern = re.compile(pattern, re.DOTALL)
    except re.error as e:
        log.error(f"Invalid regex pattern: {pattern}. Error: {e}")
        return []

    all_matches: list[MatchedConsecutiveLines] = []
    skipped_files: list[tuple[str, str]] = []
    files_processed = 0
    files_skipped_filter = 0
    last_progress_time = start_time

    def should_continue() -> bool:
        """Check if we should continue processing."""
        if timeout_seconds:
            if time.time() - start_time > timeout_seconds:
                return False
        if max_results and len(all_matches) >= max_results:
            return False
        return True

    def log_progress(force: bool = False) -> None:
        """Log progress at reasonable intervals."""
        nonlocal last_progress_time
        now = time.time()
        if force or (show_progress and now - last_progress_time > 2.0):  # Log every 2 seconds
            elapsed = now - start_time
            rate = files_processed / elapsed if elapsed > 0 else 0
            log.info(
                f"Progress: {files_processed} files processed, "
                f"{len(all_matches)} matches found, "
                f"{rate:.1f} files/sec, "
                f"{elapsed:.1f}s elapsed"
            )
            last_progress_time = now

    def process_file_batch(batch: list[str]) -> tuple[list[MatchedConsecutiveLines], list[tuple[str, str]]]:
        """Process a batch of files in parallel."""

        def process_single_file(path: str) -> dict[str, Any]:
            try:
                abs_path = os.path.join(root_path, path)
                file_content = file_reader(abs_path)
                search_results = search_text_optimized(
                    compiled_pattern,
                    content=file_content,
                    source_file_path=path,
                    allow_multiline_match=True,
                    context_lines_before=context_lines_before,
                    context_lines_after=context_lines_after,
                )
                return {"path": path, "results": search_results, "error": None}
            except Exception as e:
                return {"path": path, "results": [], "error": str(e)}

        # Process batch in parallel with timeout consideration
        remaining_time = None
        if timeout_seconds:
            elapsed = time.time() - start_time
            remaining_time = max(1, int(timeout_seconds - elapsed))

        try:
            results = Parallel(
                n_jobs=-1,
                backend="loky",
                batch_size="auto",
                timeout=remaining_time,
            )(delayed(process_single_file)(path) for path in batch)
        except Exception as e:
            log.warning(f"Batch processing error: {e}")
            return [], [(path, str(e)) for path in batch]

        batch_matches = []
        batch_errors = []

        for result in results:
            if result["error"]:
                batch_errors.append((result["path"], result["error"]))
            else:
                batch_matches.extend(result["results"])

        return batch_matches, batch_errors

    # Process files in chunks
    current_batch = []

    # Convert generator to iterator if needed
    file_iterator = iter(relative_file_paths)

    try:
        for path in file_iterator:
            if not should_continue():
                log.info("Stopping search: limit reached or timeout")
                break

            # Apply filtering
            if paths_include_glob and not glob_match(paths_include_glob, path):
                files_skipped_filter += 1
                continue
            if paths_exclude_glob and glob_match(paths_exclude_glob, path):
                files_skipped_filter += 1
                continue

            current_batch.append(path)

            # Process batch when it reaches chunk_size
            if len(current_batch) >= chunk_size:
                if not should_continue():
                    break

                batch_matches, batch_errors = process_file_batch(current_batch)
                all_matches.extend(batch_matches)
                skipped_files.extend(batch_errors)
                files_processed += len(current_batch)
                current_batch = []

                log_progress()

                # Early termination if we have enough results
                if max_results and len(all_matches) >= max_results:
                    log.info(f"Reached max_results limit ({max_results}), stopping search")
                    break

        # Process remaining files in the last batch
        if current_batch and should_continue():
            batch_matches, batch_errors = process_file_batch(current_batch)
            all_matches.extend(batch_matches)
            skipped_files.extend(batch_errors)
            files_processed += len(current_batch)

    except KeyboardInterrupt:
        log.warning("Search interrupted by user")
    except Exception as e:
        log.error(f"Unexpected error during search: {e}")

    # Final progress log
    log_progress(force=True)

    elapsed = time.time() - start_time

    if skipped_files:
        log.debug(f"Failed to read {len(skipped_files)} files")
    if files_skipped_filter > 0:
        log.debug(f"Skipped {files_skipped_filter} files due to glob filters")

    log.info(f"Search complete: processed {files_processed} files in {elapsed:.1f}s, found {len(all_matches)} matches")

    # Limit results if max_results is specified
    if max_results and len(all_matches) > max_results:
        all_matches = all_matches[:max_results]

    return all_matches


def search_files_chunked_with_state(
    relative_file_paths: list[str] | Generator[str, None, None],
    pattern: str,
    root_path: str = "",
    file_reader: Callable[[str], str] = default_file_reader,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
    paths_include_glob: str | None = None,
    paths_exclude_glob: str | None = None,
    max_results: int | None = None,
    chunk_size: int = 100,
    timeout_seconds: int | None = None,
    show_progress: bool = True,
    skip_files: int = 0,
) -> tuple[list[MatchedConsecutiveLines], dict[str, Any]]:
    """
    Stateful version of search_files_chunked that supports continuation/pagination.
    Returns both matches and search state for resuming interrupted searches.

    :param relative_file_paths: List or generator of relative file paths
    :param pattern: Pattern to search for
    :param root_path: Root path to resolve relative paths against
    :param file_reader: Function to read a file
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :param paths_include_glob: Optional glob pattern to include files
    :param paths_exclude_glob: Optional glob pattern to exclude files
    :param max_results: Maximum number of results to return (early termination)
    :param chunk_size: Number of files to process in each batch
    :param timeout_seconds: Maximum time to spend searching
    :param show_progress: Whether to log progress updates
    :param skip_files: Number of files to skip at the beginning (for continuation)
    :return: Tuple of (matches, search_state)
    """
    start_time = time.time()

    # Pre-compile the regex pattern once
    try:
        compiled_pattern = re.compile(pattern, re.DOTALL)
    except re.error as e:
        log.error(f"Invalid regex pattern: {pattern}. Error: {e}")
        return [], {"error": str(e)}

    all_matches: list[MatchedConsecutiveLines] = []
    skipped_files: list[tuple[str, str]] = []
    files_processed = 0
    files_skipped_filter = 0
    files_skipped_total = skip_files
    last_progress_time = start_time
    timed_out = False
    has_more_files = False

    def should_continue() -> bool:
        """Check if we should continue processing."""
        nonlocal timed_out
        if timeout_seconds:
            if time.time() - start_time > timeout_seconds:
                timed_out = True
                return False
        if max_results and len(all_matches) >= max_results:
            return False
        return True

    def log_progress(force: bool = False) -> None:
        """Log progress at reasonable intervals."""
        nonlocal last_progress_time
        now = time.time()
        if force or (show_progress and now - last_progress_time > 2.0):  # Log every 2 seconds
            elapsed = now - start_time
            rate = files_processed / elapsed if elapsed > 0 else 0
            log.info(
                f"Progress: {files_processed} files processed "
                f"(skipped {files_skipped_total}), "
                f"{len(all_matches)} matches found, "
                f"{rate:.1f} files/sec, "
                f"{elapsed:.1f}s elapsed"
            )
            last_progress_time = now

    def process_file_batch(batch: list[str]) -> tuple[list[MatchedConsecutiveLines], list[tuple[str, str]]]:
        """Process a batch of files in parallel with thread-safe timeout."""

        def process_single_file(path: str) -> dict[str, Any]:
            try:
                abs_path = os.path.join(root_path, path)
                file_content = file_reader(abs_path)
                search_results = search_text_optimized(
                    compiled_pattern,
                    content=file_content,
                    source_file_path=path,
                    allow_multiline_match=True,
                    context_lines_before=context_lines_before,
                    context_lines_after=context_lines_after,
                )
                return {"path": path, "results": search_results, "error": None}
            except Exception as e:
                return {"path": path, "results": [], "error": str(e)}

        # Calculate remaining time for this batch
        remaining_time = None
        if timeout_seconds:
            elapsed = time.time() - start_time
            remaining_time = max(1, int(timeout_seconds - elapsed))
            if remaining_time <= 0:
                return [], [(path, "timeout") for path in batch]

        try:
            # Use joblib's timeout parameter which is thread-safe
            results = Parallel(
                n_jobs=-1,
                backend="loky",
                batch_size="auto",
                timeout=remaining_time,
            )(delayed(process_single_file)(path) for path in batch)
        except Exception as e:
            log.warning(f"Batch processing error: {e}")
            return [], [(path, str(e)) for path in batch]

        batch_matches = []
        batch_errors = []

        for result in results:
            if result["error"]:
                batch_errors.append((result["path"], result["error"]))
            else:
                batch_matches.extend(result["results"])

        return batch_matches, batch_errors

    # Process files in chunks with skip support
    current_batch = []
    file_count = 0

    # Convert generator to iterator if needed
    file_iterator = iter(relative_file_paths)

    try:
        for path in file_iterator:
            # Skip files if we're continuing from a previous search
            if file_count < skip_files:
                file_count += 1
                continue

            if not should_continue():
                log.info("Stopping search: limit reached or timeout")
                # Check if there are more files
                try:
                    next(file_iterator)
                    has_more_files = True
                except StopIteration:
                    has_more_files = False
                break

            # Apply filtering
            if paths_include_glob and not glob_match(paths_include_glob, path):
                files_skipped_filter += 1
                file_count += 1
                continue
            if paths_exclude_glob and glob_match(paths_exclude_glob, path):
                files_skipped_filter += 1
                file_count += 1
                continue

            current_batch.append(path)
            file_count += 1

            # Process batch when it reaches chunk_size
            if len(current_batch) >= chunk_size:
                if not should_continue():
                    # Check if there are more files
                    try:
                        next(file_iterator)
                        has_more_files = True
                    except StopIteration:
                        has_more_files = False
                    break

                batch_matches, batch_errors = process_file_batch(current_batch)
                all_matches.extend(batch_matches)
                skipped_files.extend(batch_errors)
                files_processed += len(current_batch)
                current_batch = []

                log_progress()

                # Early termination if we have enough results
                if max_results and len(all_matches) >= max_results:
                    log.info(f"Reached max_results limit ({max_results}), stopping search")
                    # Check if there are more files
                    try:
                        next(file_iterator)
                        has_more_files = True
                    except StopIteration:
                        has_more_files = False
                    break
        else:
            # Iterator exhausted normally
            has_more_files = False

        # Process remaining files in the last batch
        if current_batch and should_continue():
            batch_matches, batch_errors = process_file_batch(current_batch)
            all_matches.extend(batch_matches)
            skipped_files.extend(batch_errors)
            files_processed += len(current_batch)

    except KeyboardInterrupt:
        log.warning("Search interrupted by user")
        has_more_files = True
    except Exception as e:
        log.error(f"Unexpected error during search: {e}")

    # Final progress log
    log_progress(force=True)

    elapsed = time.time() - start_time

    if skipped_files:
        log.debug(f"Failed to read {len(skipped_files)} files")
    if files_skipped_filter > 0:
        log.debug(f"Skipped {files_skipped_filter} files due to glob filters")

    log.info(f"Search complete: processed {files_processed} files in {elapsed:.1f}s, " f"found {len(all_matches)} matches")

    # Calculate where to resume from
    next_skip_files = skip_files + files_processed + files_skipped_filter

    # Create search state
    search_state = {
        "files_processed": files_processed,
        "files_skipped_total": files_skipped_total + files_skipped_filter,
        "next_skip_files": next_skip_files,
        "has_more_files": has_more_files,
        "timed_out": timed_out,
        "total_elapsed": elapsed,
    }

    # Limit results if max_results is specified
    if max_results and len(all_matches) > max_results:
        all_matches = all_matches[:max_results]

    return all_matches, search_state
