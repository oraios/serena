# SPDX-License-Identifier: GPL-3.0-or-later

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Self

from bs4 import BeautifulSoup
from joblib import Parallel, delayed
from sensai.util.string import ToStringMixin

from serena.util.file_proxy import FileCollection, FileProxy
from solidlsp.ls_utils import TextCoordinateProvider, TextCoordinates, TextUtils

if TYPE_CHECKING:
    from serena.code_editor import CodeEditor
    from serena.project import Project

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
        line_contents = TextUtils.split_lines(file_contents)
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


def search_text(
    pattern: str,
    content: str | None = None,
    source_file_path: str | None = None,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
    multiline: bool = True,
) -> list[MatchedConsecutiveLines]:
    """
    Search for a pattern in text content. Supports both regex and glob-like patterns.

    :param pattern: Pattern to search for (regex or glob-like pattern)
    :param content: The text content to search. May be None if source_file_path is provided.
    :param source_file_path: Optional path to the source file. If content is None,
        this has to be passed and the file will be read.
    :param context_lines_before: Number of context lines to include before matches
    :param context_lines_after: Number of context lines to include after matches
    :param multiline: whether to apply multi-line matching, enabling the flags re.DOTALL and re.MULTILINE
    :return: List of `TextSearchMatch` objects
    :raises: ValueError if the pattern is not valid
    """
    if source_file_path and content is None:
        with open(source_file_path) as f:
            content = f.read()

    if content is None:
        raise ValueError("Pass either content or source_file_path")

    matches = []
    lines = TextUtils.split_lines(content)
    total_lines = len(lines)

    # precompute line start offsets once so that each match's coordinates can be resolved via binary search
    # instead of re-scanning the text from the beginning for every match
    coordinates = TextCoordinateProvider(content)

    # For multiline matches, optionally use DOTALL so '.' matches newlines
    flags = (re.MULTILINE | re.DOTALL) if multiline else 0
    compiled_pattern = re.compile(pattern, flags)
    # Search across the entire content as a single string
    for match in compiled_pattern.finditer(content):
        start_pos = match.start()
        end_pos = match.end()

        # Find the line numbers for the start and end positions
        start_loc = coordinates.compute_coordinates(start_pos)
        end_loc = coordinates.compute_coordinates(end_pos)
        start_line_num, end_line_num = start_loc.line, end_loc.line
        if end_line_num > start_line_num and end_loc.col == 0:
            # `end_pos` is exclusive, so if it is at the start of a line, the match ends with the
            # preceding line's newline and does not extend into the line that `end_pos` points to
            end_line_num -= 1

        # Calculate the range of lines to include in the context
        context_start = max(0, start_line_num - context_lines_before)
        context_end = min(total_lines - 1, end_line_num + context_lines_after)

        # Create TextLine objects for the context
        context_lines = []
        for line_num in range(context_start, context_end + 1):
            if context_start <= line_num < start_line_num:
                match_type = LineType.BEFORE_MATCH
            elif end_line_num < line_num <= context_end:
                match_type = LineType.AFTER_MATCH
            else:
                match_type = LineType.MATCH

            context_lines.append(TextLine(line_number=line_num, line_content=lines[line_num], match_type=match_type))

        matches.append(MatchedConsecutiveLines(lines=context_lines, source_file_path=source_file_path))

    return matches


class GlobMatcher(ToStringMixin):
    """
    Supports matching a file path against a glob pattern.

    Supports standard glob patterns:
    - * matches any number of characters except /
    - ** matches any number of directories (zero or more)
    - ? matches a single character except /
    - [seq] matches any character in seq

    Supports brace expansion:
    - {a,b,c} expands to multiple patterns (including nesting)
    """

    def __init__(self, expr: str):
        """
        :param expr: a glob pattern which may make use of brace expansion (e.g., "src/**/*.{js,jsx,ts,tsx}")
        """
        expr = expr.replace("\\", "/")  # normalise backslashes to forward slashes
        self._glob_expr = expr
        self._glob_patterns = self._expand_braces(expr)
        self._regex_patterns = [re.compile(self._translate_glob_to_regex(p)) for p in self._glob_patterns]

    def _tostring_includes(self) -> list[str]:
        return ["_glob_expr"]

    @staticmethod
    def _expand_braces(pattern: str) -> list[str]:
        """
        Expands brace patterns in a glob string.
        For example, "**/*.{js,jsx,ts,tsx}" becomes ["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx"].
        Handles multiple brace sets as well.
        """
        patterns = [pattern]
        while any("{" in p or "}" in p for p in patterns):
            new_patterns = []
            for p in patterns:
                match = re.search(r"\{([^{}]*)\}", p)
                if match:
                    options_expr = match.group(1)
                    if not options_expr:
                        raise ValueError(f"Invalid glob brace expression in {pattern!r}: empty braces are not allowed")

                    prefix = p[: match.start()]
                    suffix = p[match.end() :]
                    options = options_expr.split(",")
                    for option in options:
                        new_patterns.append(f"{prefix}{option}{suffix}")
                else:
                    raise ValueError(f"Invalid glob brace expression in {pattern!r}: unmatched brace")
            patterns = new_patterns
        return patterns

    @staticmethod
    def _translate_glob_to_regex(pattern: str) -> str:
        res = []
        i = 0
        n = len(pattern)
        while i < n:
            c = pattern[i]
            i += 1
            if c == "*":
                if i < n and pattern[i] == "*":  # **
                    i += 1
                    if i < n and pattern[i] == "/":  # **/
                        i += 1
                        if res and res[-1] == "/":  # /**/
                            res = res[:-1]
                            res.append("(?:/|/.*/)")
                        elif res:  # c**/ (with c != '/')
                            res.append(".*/")
                        else:  # **/ at the start of the pattern
                            res.append("(?:.*/)?")
                    else:  # c**d  (with c, d != '/')
                        res.append(".*")
                else:  # single *
                    if not res or res[-1] != "[^/]*":
                        res.append("[^/]*")
            elif c == "?":
                res.append("[^/]")
            elif c == "[":
                j = i
                if j < n and pattern[j] == "!":
                    j += 1
                if j < n and pattern[j] == "]":
                    j += 1
                while j < n and pattern[j] != "]":
                    j += 1
                if j >= n:
                    res.append(r"\[")
                else:
                    stuff = pattern[i:j]
                    if stuff.startswith("!"):
                        stuff = "^" + stuff[1:]
                    elif stuff.startswith("^"):
                        stuff = r"\^" + stuff
                    res.append(f"[{stuff}]")
                    i = j + 1
            else:
                res.append(re.escape(c))
        inner = "".join(res)
        return f"(?s:{inner})\\Z"

    def matches(self, path: str) -> bool:
        path = path.replace("\\", "/")  # normalise backslashes to forward slashes
        return any(regex.match(path) for regex in self._regex_patterns)


def search_files(
    file_collection: FileCollection,
    pattern: str,
    context_lines_before: int = 0,
    context_lines_after: int = 0,
    paths_include_glob: str | None = None,
    paths_exclude_glob: str | None = None,
    multiline: bool = True,
) -> list[MatchedConsecutiveLines]:
    """
    Search for a pattern in a list of files.

    :param file_collection: the collection of files to search (will be optionally filtered by glob patterns)
    :param pattern: pattern to search for
    :param context_lines_before: number of context lines to include before matches
    :param context_lines_after: number of context lines to include after matches
    :param paths_include_glob: optional glob pattern to include files from the list
    :param paths_exclude_glob: optional glob pattern to exclude files from the list
    :param multiline: whether to apply multi-line matching, enabling the flags re.DOTALL and re.MULTILINE (default: True)
    :return: list of MatchedConsecutiveLines objects
    """
    # apply glob filter
    file_collection = file_collection.filter_glob(paths_include_glob=paths_include_glob, paths_exclude_glob=paths_exclude_glob)
    log.info(f"Processing {len(file_collection)} files.")

    def process_single_file(file_proxy: FileProxy) -> dict[str, Any]:
        """Process a single file - this function will be parallelized."""
        relative_path = file_proxy.get_relative_path()
        try:
            file_content = file_proxy.get_contents()
            search_results = search_text(
                pattern,
                content=file_content,
                source_file_path=relative_path,
                context_lines_before=context_lines_before,
                context_lines_after=context_lines_after,
                multiline=multiline,
            )
            if len(search_results) > 0:
                log.debug(f"Found {len(search_results)} matches in {relative_path}")
            return {"path": relative_path, "results": search_results, "error": None}
        except Exception as e:
            log.debug(f"Error processing {relative_path}: {e}")
            return {"path": relative_path, "results": [], "error": str(e)}

    # Execute in parallel using joblib
    results = Parallel(
        n_jobs=-1,
        backend="threading",
    )(delayed(process_single_file)(file_proxy) for file_proxy in file_collection)

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

    log.info(f"Found {len(matches)} total matches across {len(file_collection)} files")
    return matches


def render_html(html: str) -> str:
    """
    Remove HTML tags and decode HTML entities from text while preserving the actual content.
    This keeps type information and structure but removes all formatting.

    :param html: HTML text to clean
    :return: Plain text without HTML tags and with decoded entities
    """
    soup = BeautifulSoup(html, "html.parser")
    # join text with spaces to avoid concatenation of words
    text = soup.get_text(separator=" ", strip=True)

    # normalize non-breaking spaces
    text = text.replace("\xa0", " ")

    return text.strip()


class ContentReplacer:
    """
    This is an LLM-optimised content replacer, which elegantly circumvents escaping and which
    provides dual modes for maximum flexibility.
    """

    def __init__(self, mode: Literal["literal", "regex"], allow_multiple_occurrences: bool, regex_multiline: bool = True):
        """

        :param mode: the mode indicating whether to the needle in replacements corresponds to a regular expression
            (mode "regex") or to a literal string (mode "literal")
        :param allow_multiple_occurrences: whether it is allowed that the search expression matches multiple occurrences.
            If False, an error will be raised if more than one match is found.
        :param regex_multiline: whether to apply multi-line regex matching, enabling the flags re.DOTALL and re.MULTILINE
        """
        self.mode = mode
        self.allow_multiple_occurrences = allow_multiple_occurrences
        self.regex_multiline = regex_multiline

    @staticmethod
    def _create_replacement_function(
        regex_pattern: str, repl_template: str, regex_flags: int, expand_backrefs: bool
    ) -> Callable[[re.Match], str]:
        """
        Creates a replacement function that validates for ambiguity and handles backreferences.

        :param regex_pattern: The regex pattern being used for matching
        :param repl_template: The replacement template; in regex mode, it may contain $!1, $!2, etc. for
            backreferences; in literal mode, it is used verbatim
        :param regex_flags: The flags to use when searching (e.g., re.DOTALL | re.MULTILINE)
        :param expand_backrefs: Whether $!N backreferences are expanded in the template; false in literal mode,
            mirroring the mode gate in MultiFileContentReplacer.find_occurrences
        :return: A function suitable for use with re.sub() or re.subn()
        """

        def validate_and_replace(match: re.Match) -> str:
            matched_text = match.group(0)

            # For multi-line match, check if the same pattern matches again within the already-matched text,
            # rendering the match ambiguous. Typical pattern in the code:
            #    <start><other-stuff><start><stuff><end>
            # When matching
            #    <start>.*?<end>
            # this will match the entire span above, while only the suffix may have been intended.
            # (See test case for a practical example.)
            # To detect this, we check if the same pattern matches again within the matched text,
            if "\n" in matched_text and re.search(regex_pattern, matched_text[1:], flags=regex_flags):
                raise ValueError(
                    "Match is ambiguous: the search pattern matches multiple overlapping occurrences. "
                    "Please revise the search pattern to be more specific to avoid ambiguity, "
                    "e.g. by matching specific context after the match, or try using the literal mode."
                )

            # in literal mode, the template is the final replacement; $!N sequences need no escaping
            if not expand_backrefs:
                return repl_template

            # Handle backreferences: replace $!1, $!2, etc. with actual matched groups; groups that
            # exist but did not participate in the match expand to the empty string
            def expand_backreference(m: re.Match) -> str:
                group_num = int(m.group(1))
                try:
                    group_value = match.group(group_num)
                except IndexError as e:
                    raise ValueError(f"Backreference $!{group_num} refers to a group that does not exist in the search expression") from e
                return group_value if group_value is not None else ""

            result = re.sub(r"\$!(\d+)", expand_backreference, repl_template)
            return result

        return validate_and_replace

    def replace(
        self,
        content: str,
        needle: str,
        repl: str,
    ) -> str:
        """
        Performs the replacement.

        Raises ValueError if no match is found, or if multiple matches are found while allow_multiple_occurrences is False.

        :param content: the content in which to perform the replacement
        :param needle: the search expression, which is either a literal string or a regular expression, depending on the mode
        :param repl: the replacement string; in regex mode, it may contain backreferences in the form of $!1, $!2, etc.
            to refer to matched groups in the search expression; in literal mode, it is used verbatim
        :return: the updated content after performing the replacement
        """
        if self.mode == "literal":
            regex = re.escape(needle)
        elif self.mode == "regex":
            regex = needle
        else:
            raise ValueError(f"Invalid mode: '{self.mode}', expected 'literal' or 'regex'.")

        regex_flags = (re.MULTILINE | re.DOTALL) if self.regex_multiline else 0

        # create replacement function with ambiguity validation and, in regex mode, backreference handling
        repl_fn = self._create_replacement_function(regex, repl, regex_flags=regex_flags, expand_backrefs=self.mode == "regex")

        # perform replacement
        updated_content, n = re.subn(regex, repl_fn, content, flags=regex_flags)

        if n == 0:
            raise ValueError("Error: No matches of search expression found.")
        if not self.allow_multiple_occurrences and n > 1:
            raise ValueError(
                f"Expression matches {n} occurrences. "
                "Please revise the expression to be more specific or enable allow_multiple_occurrences if this is expected."
            )
        return updated_content


@dataclass
class ReplacementOccurrence:
    """A single prospective replacement of a pattern match within one file."""

    occurrence_id: str
    """stable, content-anchored identifier: '<relative_path>:<index_in_file>@<digest>'"""
    relative_path: str
    index_in_file: int
    """0-based index of this match among the matches within its file (in position order)"""
    start: int
    """character offset of the match start within the file content"""
    end: int
    """character offset of the match end within the file content"""
    matched_text: str
    replacement: str
    """the fully expanded replacement text (backreferences already resolved)"""
    start_line: int
    """0-based line number of the match start"""
    end_line: int
    """0-based line number of the match end"""
    is_ambiguous: bool = False
    """whether the pattern matches again within the matched text (possible over-match)"""


class MultiFileContentReplacer:
    """
    Occurrence-level counterpart of :class:`ContentReplacer` operating on multiple files:
    finds every match of a pattern across a set of file contents, assigns each occurrence a
    stable content-anchored id, renders minimal line diffs for previewing, and computes the
    updated content of a file for a selected subset of occurrences.
    """

    OCCURRENCE_ID_REGEX = re.compile(r"^(?P<path>.+):(?P<index>\d+)@(?P<digest>[0-9a-f]{6})$")
    _DIGEST_LEN = 6

    def __init__(self, mode: Literal["literal", "regex"], regex_multiline: bool = True):
        """
        :param mode: whether the needle is a literal string ("literal") or a regular expression ("regex")
        :param regex_multiline: whether to apply multi-line regex matching, enabling the flags re.DOTALL and re.MULTILINE
        """
        if mode not in ("literal", "regex"):
            raise ValueError(f"Invalid mode: '{mode}', expected 'literal' or 'regex'.")
        self.mode = mode
        self._flags = (re.MULTILINE | re.DOTALL) if regex_multiline else 0

    def _compile(self, needle: str) -> re.Pattern:
        return re.compile(re.escape(needle) if self.mode == "literal" else needle, flags=self._flags)

    @classmethod
    def _digest(cls, matched_text: str) -> str:
        return hashlib.sha1(matched_text.encode("utf-8")).hexdigest()[: cls._DIGEST_LEN]

    @classmethod
    def make_occurrence_id(cls, relative_path: str, index_in_file: int, matched_text: str) -> str:
        return f"{relative_path}:{index_in_file}@{cls._digest(matched_text)}"

    @staticmethod
    def _expand_backreferences(match: re.Match, repl_template: str) -> str:
        """Expands $!1, $!2, ... in the replacement template (same syntax as :class:`ContentReplacer`)."""

        def expand(m: re.Match) -> str:
            group_num = int(m.group(1))
            try:
                group_value = match.group(group_num)
            except IndexError as e:
                raise ValueError(f"Backreference $!{group_num} refers to a group that does not exist in the search expression") from e
            return group_value if group_value is not None else ""

        return re.sub(r"\$!(\d+)", expand, repl_template)

    def find_occurrences(self, files: list[tuple[str, str]], needle: str, repl: str) -> list[ReplacementOccurrence]:
        """
        Finds all matches of the needle in the given files.

        :param files: (relative_path, content) pairs; processed in the given order
        :param needle: the search expression (literal string or regex, depending on the mode)
        :param repl: the replacement template (may contain $!N backreferences in regex mode)
        :return: occurrences in deterministic order (file order, then position within the file)
        """
        pattern = self._compile(needle)
        occurrences: list[ReplacementOccurrence] = []
        for relative_path, content in files:
            for index_in_file, match in enumerate(pattern.finditer(content)):
                matched_text = match.group(0)
                replacement = self._expand_backreferences(match, repl) if self.mode == "regex" else repl
                # same over-match heuristic as ContentReplacer: for a multi-line match, the pattern
                # matching again within the matched text indicates the match may have swallowed
                # more than intended
                is_ambiguous = "\n" in matched_text and pattern.search(matched_text[1:]) is not None
                occurrences.append(
                    ReplacementOccurrence(
                        occurrence_id=self.make_occurrence_id(relative_path, index_in_file, matched_text),
                        relative_path=relative_path,
                        index_in_file=index_in_file,
                        start=match.start(),
                        end=match.end(),
                        matched_text=matched_text,
                        replacement=replacement,
                        start_line=content.count("\n", 0, match.start()),
                        end_line=content.count("\n", 0, match.end()),
                        is_ambiguous=is_ambiguous,
                    )
                )
        return occurrences

    @staticmethod
    def apply_to_content(content: str, occurrences: list[ReplacementOccurrence]) -> str:
        """
        Applies the given occurrences (which must have been derived from exactly this content)
        and returns the updated content.
        """
        for occ in sorted(occurrences, key=lambda o: o.start, reverse=True):
            assert content[occ.start : occ.end] == occ.matched_text, (
                f"Occurrence {occ.occurrence_id} does not match the content it is being applied to"
            )
            content = content[: occ.start] + occ.replacement + content[occ.end :]
        return content

    @staticmethod
    def _format_block(block: str, prefix: str, max_lines: int, max_line_chars: int) -> list[str]:
        lines = block.split("\n")
        shown = lines[:max_lines]
        result = []
        for line in shown:
            if len(line) > max_line_chars:
                line = line[:max_line_chars] + f"… (+{len(line) - max_line_chars} chars)"
            result.append(f"    {prefix} {line}")
        if len(lines) > max_lines:
            result.append(f"    {prefix} … ({len(lines) - max_lines} more lines)")
        return result

    def render_occurrence_diff(
        self, occ: ReplacementOccurrence, content: str, max_lines_per_side: int = 6, max_line_chars: int = 200
    ) -> str:
        """
        Renders a minimal line diff for the occurrence: the full lines spanned by the match,
        before and after the replacement.

        :param occ: the occurrence (must have been derived from exactly this content)
        :param content: the file content the occurrence was found in
        :param max_lines_per_side: cap on the number of displayed lines per diff side
        :param max_line_chars: cap on the number of displayed characters per line
        :return: the rendered diff
        """
        line_start = content.rfind("\n", 0, occ.start) + 1
        line_end = content.find("\n", occ.end)
        if line_end == -1:
            line_end = len(content)
        old_block = content[line_start:line_end]
        new_block = content[line_start : occ.start] + occ.replacement + content[occ.end : line_end]
        location = f"line {occ.start_line}" if occ.start_line == occ.end_line else f"lines {occ.start_line}-{occ.end_line}"
        header = f"  [{occ.occurrence_id}] {location}"
        if occ.is_ambiguous:
            header += "  (WARNING: the pattern matches again inside this match — possible over-match, verify the diff)"
        diff_lines = [header]
        diff_lines += self._format_block(old_block, "-", max_lines_per_side, max_line_chars)
        diff_lines += self._format_block(new_block, "+", max_lines_per_side, max_line_chars)
        return "\n".join(diff_lines)


class ReplacementRejectedError(ValueError):
    """
    Raised when a replacement is not applied because a safety check failed; no changes have been made.
    """

    def __init__(self, message: str, show_prospective_changes: bool) -> None:
        """
        :param message: the reason for the rejection
        :param show_prospective_changes: whether the listing of the prospective changes should be presented along
            with the message (the message refers to it)
        """
        super().__init__(message)
        self.show_prospective_changes = show_prospective_changes


@dataclass
class MultiFileReplacementResult:
    """
    The result of an applied replacement.
    """

    num_occurrences_by_file: dict[str, int]
    """the number of replaced occurrences per file (relative path), in application order"""

    @property
    def num_occurrences(self) -> int:
        return sum(self.num_occurrences_by_file.values())

    def to_display_string(self) -> str:
        per_file = "\n".join(f"  {path}: {n}" for path, n in self.num_occurrences_by_file.items())
        return f"Replaced {self.num_occurrences} occurrence(s) in {len(self.num_occurrences_by_file)} file(s):\n{per_file}"


class MultiFileReplacement:
    """
    A prospective replacement of a pattern across the files of a project within a given scope: holds the
    occurrences found, supports selecting occurrences by their ids, guards blind application against
    unintended replacements, renders a preview listing and applies the replacement via a code editor.
    """

    def __init__(
        self,
        project: "Project",
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        relative_path: str = "",
        paths_include_glob: str = "",
        paths_exclude_glob: str = "",
    ) -> None:
        """
        :param project: the project whose files are to be searched
        :param needle: the string (mode "literal") or regular expression (mode "regex") to search for
        :param repl: the replacement string (may contain $!N backreferences in regex mode)
        :param mode: how `needle` is to be interpreted
        :param relative_path: only consider this file or directory (default: the whole project)
        :param paths_include_glob: optional glob restricting which files are considered
        :param paths_exclude_glob: optional glob of files to exclude; takes precedence over the include glob
        """
        self._replacer = MultiFileContentReplacer(mode=mode)
        self._needle = needle
        self._repl = repl
        files = self._collect_files(project, relative_path.strip(), paths_include_glob.strip(), paths_exclude_glob.strip())
        self._contents = dict(files)
        self.occurrences: list[ReplacementOccurrence] = self._replacer.find_occurrences(files, needle, repl)

    @staticmethod
    def _collect_files(project: "Project", relative_path: str, paths_include_glob: str, paths_exclude_glob: str) -> list[tuple[str, str]]:
        """
        :return: the (relative_path, content) pairs of the readable, non-ignored files in scope, in sorted path order
        """
        if relative_path:
            project.validate_relative_path(relative_path, require_not_ignored=True)
        file_collection = project.create_file_collection(relative_path, code_files_only=False, skip_ignored_files=True).filter_glob(
            paths_include_glob or None, paths_exclude_glob or None
        )
        files: list[tuple[str, str]] = []
        for file_proxy in sorted(file_collection, key=lambda f: f.get_relative_path()):
            try:
                files.append((file_proxy.get_relative_path(), file_proxy.get_contents()))
            except Exception:
                continue  # skip unreadable (e.g. binary) files
        return files

    @property
    def affected_files(self) -> list[str]:
        """
        :return: the relative paths of the files containing occurrences, sorted
        """
        return sorted({o.relative_path for o in self.occurrences})

    def select(self, occurrence_ids: list[str]) -> list[ReplacementOccurrence]:
        """
        Resolves the given occurrence ids (as obtained from a previous listing).

        :param occurrence_ids: the ids of the occurrences to select
        :return: the selected occurrences
        :raises ReplacementRejectedError: if the selection is empty or any id cannot be resolved
        """
        occurrences_by_id = {o.occurrence_id: o for o in self.occurrences}
        indices_by_path: dict[str, set[int]] = {}
        for o in self.occurrences:
            indices_by_path.setdefault(o.relative_path, set()).add(o.index_in_file)

        # resolve each id, diagnosing failures
        selected: dict[str, ReplacementOccurrence] = {}
        problems: list[str] = []
        for oid in occurrence_ids:
            occurrence = occurrences_by_id.get(oid)
            if occurrence is not None:
                selected[oid] = occurrence
                continue
            id_match = MultiFileContentReplacer.OCCURRENCE_ID_REGEX.match(oid)
            if id_match is None:
                problems.append(f"{oid}: malformed id (expected '<path>:<index>@<digest>' as returned by a dry run)")
            elif id_match.group("path") not in indices_by_path:
                problems.append(f"{oid}: the pattern currently has no matches in this file")
            elif int(id_match.group("index")) not in indices_by_path[id_match.group("path")]:
                problems.append(f"{oid}: the file now has fewer matches than at dry-run time (content changed)")
            else:
                problems.append(f"{oid}: the matched text changed since the dry run (content changed)")

        if problems:
            problem_lines = "\n".join(f"  {p}" for p in problems)
            raise ReplacementRejectedError(
                f"{len(problems)} of the given occurrence_ids could not be resolved - NO changes were applied:\n"
                f"{problem_lines}\n"
                "Re-run with dry_run=True to obtain current occurrence ids.",
                show_prospective_changes=False,
            )
        if not selected:
            raise ReplacementRejectedError(
                "occurrence_ids is empty - pass at least one id from a dry run, or omit the parameter to replace all.",
                show_prospective_changes=False,
            )
        return list(selected.values())

    def select_all_guarded(self, expected_count: int = -1) -> list[ReplacementOccurrence]:
        """
        Selects all occurrences for a blind application (without explicit selection), applying safety checks.

        :param expected_count: the number of occurrences expected; -1 disables the check
        :return: all occurrences
        :raises ReplacementRejectedError: if there are no occurrences, the count differs from the expectation
            or any occurrence is ambiguous
        """
        if not self.occurrences:
            raise ReplacementRejectedError(
                "No occurrences of the pattern were found - NO changes were applied. "
                "Check the mode (a literal needle containing regex metacharacters must use mode 'literal'; "
                "wildcards require mode 'regex') and the path/glob restrictions, "
                "or locate the content with search_for_pattern first.",
                show_prospective_changes=False,
            )
        if expected_count >= 0 and len(self.occurrences) != expected_count:
            raise ReplacementRejectedError(
                f"expected_count={expected_count}, but the pattern matches {len(self.occurrences)} occurrence(s) - "
                "NO changes were applied. Review the prospective changes below; re-issue with the corrected "
                "expectation, a refined pattern, or occurrence_ids selecting the intended subset.",
                show_prospective_changes=True,
            )
        num_ambiguous = sum(1 for o in self.occurrences if o.is_ambiguous)
        if num_ambiguous:
            raise ReplacementRejectedError(
                f"{num_ambiguous} occurrence(s) are ambiguous (the pattern matches again inside the matched text, "
                "indicating possible over-matching) - NO changes were applied. Review the prospective changes below "
                "and either refine the pattern or explicitly select occurrences via occurrence_ids.",
                show_prospective_changes=True,
            )
        return list(self.occurrences)

    def render_listing(self, max_answer_chars: int, dry_run: bool) -> str:
        """
        Renders the prospective changes as a list of minimal line diffs with occurrence ids, subject to the given length limit
        (falling back to locations only, per-file counts and finally a summary).

        :param max_answer_chars: the maximum number of characters (must be positive)
        :param dry_run: whether the listing is the result of a dry run (adding instructions on how to proceed)
        :return: the listing
        """
        affected_files = self.affected_files
        header = f"Found {len(self.occurrences)} occurrence(s) in {len(affected_files)} file(s)."
        if dry_run:
            header += (
                " DRY RUN - no changes were applied.\n"
                "Re-issue with dry_run=False to replace all of them, or additionally pass occurrence_ids "
                "with the ids of the occurrences to replace."
            )
        parts = [header]
        for path in affected_files:
            file_occurrences = [o for o in self.occurrences if o.relative_path == path]
            parts.append(f"\n{path} ({len(file_occurrences)} occurrence(s)):")
            for occ in file_occurrences:
                parts.append(self._replacer.render_occurrence_diff(occ, self._contents[path]))
        result = "\n".join(parts)

        # shortened result closures, from least to most aggressive shortening
        def make_locations_only() -> str:
            return "\n".join([header] + [f"  [{o.occurrence_id}] line {o.start_line}" for o in self.occurrences])

        def make_per_file_counts() -> str:
            counts = {path: sum(1 for o in self.occurrences if o.relative_path == path) for path in affected_files}
            return f"{header}\nOccurrence counts per file:\n{TextOutputUtils.to_json(counts)}"

        def make_summary() -> str:
            return header

        shortened_result_factories: list[Callable[[], str]] = [make_locations_only, make_per_file_counts, make_summary]
        return TextOutputUtils.limit_length(result, max_answer_chars, shortened_result_factories)

    def apply(self, code_editor: "CodeEditor", occurrences: list[ReplacementOccurrence]) -> MultiFileReplacementResult:
        """
        Applies the given (selected) occurrences.

        :param code_editor: the code editor through which to modify the files
        :param occurrences: the occurrences to replace (obtained from `select` or `select_all_guarded`)
        :return: the result
        :raises ValueError: if a file's content changed such that a selected occurrence no longer resolves
            (the file is then not modified)
        """
        from serena.code_editor import EditedFileContext

        occurrences_by_file: dict[str, list[ReplacementOccurrence]] = {}
        for occ in occurrences:
            occurrences_by_file.setdefault(occ.relative_path, []).append(occ)

        for path, file_occurrences in occurrences_by_file.items():
            with EditedFileContext(path, code_editor) as context:
                original_content = context.get_original_content()
                if original_content != self._contents[path]:
                    # the editor's view differs from what was scanned (e.g. line-ending normalization);
                    # re-derive the occurrences from the authoritative content and re-validate by id
                    fresh_by_id = {
                        o.occurrence_id: o for o in self._replacer.find_occurrences([(path, original_content)], self._needle, self._repl)
                    }
                    try:
                        file_occurrences = [fresh_by_id[o.occurrence_id] for o in file_occurrences]
                    except KeyError as e:
                        raise ValueError(
                            f"The content of {path} changed while replacing (occurrence {e} no longer resolves); "
                            f"the file was NOT modified. Re-run with dry_run=True for current ids."
                        ) from e
                context.set_updated_content(self._replacer.apply_to_content(original_content, file_occurrences))

        return MultiFileReplacementResult({path: len(occs) for path, occs in occurrences_by_file.items()})


def find_text_coordinates(content: str, regex: str, require_unique: bool = False) -> TextCoordinates | None:
    """
    Finds the line and column number of the first match of a regex pattern in the given content.

    :param content: the text content to search through
    :param regex: the regular expression pattern to search for; it must match part of a single line,
        and contain exactly one group that captures the position of interest (e.g., the exact variable name to find the coordinates of)
    :param require_unique: if True, raises an error if not exactly one match is found;
        if False, returns None if no match is found, and returns the coordinates of the first match if multiple matches are found
    :return: the coordinates of the match or None
    """
    pattern = re.compile(regex, flags=re.MULTILINE | re.DOTALL)
    matches = list(pattern.finditer(content))
    if len(matches) == 0:
        if require_unique:
            raise ValueError(f"No match found for regex: {regex}")
        return None
    else:
        if require_unique and len(matches) > 1:
            raise ValueError(f"Match must be unique; found {len(matches)} matches for regex: {regex}")
        match = matches[0]
        if len(match.groups()) != 1:
            raise ValueError(f"Regex must contain exactly one group to capture the position, but found {len(match.groups())} groups.")
        index_in_content = match.start(1)
        line, col = TextUtils.get_line_col_from_index(content, index_in_content)
        return TextCoordinates(line, col)


class TextOutputUtils:
    @staticmethod
    def to_json(x: Any) -> str:
        return json.dumps(x, ensure_ascii=False)

    @staticmethod
    def limit_length(
        result: str,
        max_answer_chars: int,
        shortened_result_factories: list[Callable[[], str]] | None = None,
    ) -> str:
        """Limit the length of the result string, optionally trying progressively shorter versions.

        :param result: the full result string
        :param max_answer_chars: maximum allowed characters; if exceeded, attempt to use shortened versions
        :param shortened_result_factories: optional list of closures, each producing a progressively shorter
            version of the result. They are tried in order until one fits within ``max_answer_chars``.
        :return: the result string, potentially replaced by a shortened version
        """
        if max_answer_chars <= 0:
            raise ValueError(f"max_answer_chars must be positive; got: {max_answer_chars=}")
        if (n_chars := len(result)) > max_answer_chars:
            too_long_msg = (
                f"The answer is too long ({n_chars} characters). " + "You can adjust your query or raise the max_answer_chars parameter."
            )
            if shortened_result_factories is not None:
                # try each shortening closure in order;
                for make_shorter in shortened_result_factories:
                    shortened = make_shorter()
                    candidate = f"{too_long_msg}\n{shortened}"
                    if len(candidate) <= max_answer_chars:
                        return candidate
            result = too_long_msg
        return result
