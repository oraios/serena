"""
File and file system-related tools, specifically for
  * listing directory contents
  * reading files
  * creating files
  * editing at the file level
"""

import os
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path
from typing import Literal

from serena.tools import SUCCESS_RESULT, EditedFileContext, EditingToolWithDiagnostics, Tool, ToolMarkerOptional
from serena.util.file_system import scan_directory
from serena.util.text_utils import (
    ContentReplacer,
    MultiFileContentReplacer,
    ReplacementOccurrence,
    expand_braces,
    glob_match,
    search_files,
)


class ReadFileTool(Tool):
    """
    Reads a file within the project directory.
    """

    def apply(self, relative_path: str, start_line: int = 0, end_line: int | None = None, max_answer_chars: int = -1) -> str:
        """
        Reads the given file or a chunk of it.

        :param relative_path: the relative path to the file to read
        :param start_line: the 0-based index of the first line to be retrieved.
        :param end_line: the 0-based index of the last line to be retrieved (inclusive). If None, read until the end of the file.
        :param max_answer_chars: if the file (chunk) is longer than this number of characters,
            no content will be returned. Don't adjust unless there is really no other way to get the content
            required for the task.
        :return: the full text of the file at the given relative path
        """
        self.project.validate_relative_path(relative_path, require_not_ignored=True)

        result = self.project.read_file(relative_path)
        result_lines = result.splitlines()
        if end_line is None:
            result_lines = result_lines[start_line:]
        else:
            result_lines = result_lines[start_line : end_line + 1]
        result = "\n".join(result_lines)

        return self._limit_length(result, max_answer_chars)


class CreateTextFileTool(EditingToolWithDiagnostics):
    """
    Creates/overwrites a file in the project directory.
    """

    def apply(self, relative_path: str, content: str) -> str:
        """
        Write a new file or overwrite an existing file.

        :param relative_path: the relative path to the file to create
        :param content: the (appropriately encoded) content to write to the file
        :return: a message indicating success or failure
        """
        with self.DiagnosticsContext(self, relative_path) as diagnostics_context:
            # validating the destination path
            project_root = self.get_project_root()
            abs_path = (Path(project_root) / relative_path).resolve()
            will_overwrite_existing = abs_path.exists()

            if will_overwrite_existing:
                self.project.validate_relative_path(relative_path, require_not_ignored=True)
            else:
                assert abs_path.is_relative_to(self.get_project_root()), (
                    f"Cannot create file outside of the project directory, got {relative_path=}"
                )

            # writing the file
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding=self.project.project_config.encoding, newline=self.project.line_ending.newline_str)
            answer = f"File created: {relative_path}."
            if will_overwrite_existing:
                answer += " Overwrote existing file."

            return diagnostics_context.format_result(answer)


class ListDirTool(Tool):
    """
    Lists files and directories in the given directory (optionally with recursion).
    """

    def apply(self, relative_path: str, recursive: bool, skip_ignored_files: bool = False, max_answer_chars: int = -1) -> str:
        """
        Lists files and directories in the given directory (optionally with recursion).

        :param relative_path: the relative path to the directory to list; pass "." to scan the project root
        :param recursive: whether to scan subdirectories recursively
        :param skip_ignored_files: whether to skip files and directories that are ignored
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. -1 means the default value from the config will be used.
            Don't adjust unless there is really no other way to get the content required for the task.
        :return: a JSON object with the names of directories and files within the given directory
        """
        # Check if the directory exists before validation
        if not self.project.relative_path_exists(relative_path):
            error_info = {
                "error": f"Directory not found: {relative_path}",
                "project_root": self.get_project_root(),
                "hint": "Check if the path is correct relative to the project root",
            }
            return self._to_json(error_info)

        self.project.validate_relative_path(relative_path, require_not_ignored=skip_ignored_files)

        dirs, files = scan_directory(
            os.path.join(self.get_project_root(), relative_path),
            relative_to=self.get_project_root(),
            recursive=recursive,
            is_ignored_dir=self.project.is_ignored_path if skip_ignored_files else None,
            is_ignored_file=self.project.is_ignored_path if skip_ignored_files else None,
        )

        result = self._to_json({"dirs": dirs, "files": files})
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
        self.project.validate_relative_path(relative_path, require_not_ignored=True)

        dir_to_scan = os.path.join(self.get_project_root(), relative_path)

        # find the files by ignoring everything that doesn't match
        def is_ignored_file(abs_path: str) -> bool:
            if self.project.is_ignored_path(abs_path):
                return True
            filename = os.path.basename(abs_path)
            return not fnmatch(filename, file_mask)

        _dirs, files = scan_directory(
            path=dir_to_scan,
            recursive=True,
            is_ignored_dir=self.project.is_ignored_path,
            is_ignored_file=is_ignored_file,
            relative_to=self.get_project_root(),
        )

        result = self._to_json({"files": files})
        return result


class ReplaceContentTool(EditingToolWithDiagnostics):
    """
    Replaces content in a file (optionally using regular expressions).
    """

    def apply(
        self,
        relative_path: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool = False,
    ) -> str:
        r"""
        Replaces one or more occurrences of a given pattern in a file with new content.

        This is the preferred way to replace content in a file whenever the symbol-level
        tools are not appropriate.

        VERY IMPORTANT: The "regex" mode allows very large sections of code to be replaced without fully quoting them!
        Use a regex of the form "beginning.*?end-of-text-to-be-replaced" to be faster and more economical!
        ALWAYS try to use wildcards to avoid specifying the exact content to be replaced,
        especially if it spans several lines. Note that you cannot make mistakes, because if the regex should match
        multiple occurrences while you disabled `allow_multiple_occurrences`, an error will be returned, and you can retry
        with a revised regex.
        Therefore, using regex mode with suitable wildcards is usually the best choice!

        :param relative_path: the relative path to the file
        :param needle: the string or regex pattern to search for.
            If `mode` is "literal", this string will be matched exactly.
            If `mode` is "regex", this string will be treated as a regular expression (syntax of Python's `re` module,
            with flags DOTALL and MULTILINE enabled).
        :param repl: the replacement string (verbatim).
            If mode is "regex", the string can contain backreferences to matched groups in the needle regex,
            specified using the syntax $!1, $!2, etc. for groups 1, 2, etc.
        :param mode: either "literal" or "regex", specifying how the `needle` parameter is to be interpreted.
        :param allow_multiple_occurrences: whether to allow matching and replacing multiple occurrences.
            If false and multiple occurrences are found, an error will be returned
        """
        return self.replace_content(
            relative_path, needle, repl, mode=mode, allow_multiple_occurrences=allow_multiple_occurrences, require_not_ignored=True
        )

    def replace_content(
        self,
        relative_path: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool = False,
        require_not_ignored: bool = True,
    ) -> str:
        """
        Performs the replacement, with additional options not exposed in the tool.
        This function can be used internally by other tools.
        """
        with self.DiagnosticsContext(self, relative_path) as diagnostics_context:
            self.project.validate_relative_path(relative_path, require_not_ignored=require_not_ignored)
            with EditedFileContext(relative_path, self.create_code_editor()) as context:
                original_content = context.get_original_content()
                replacer = ContentReplacer(mode=mode, allow_multiple_occurrences=allow_multiple_occurrences)
                updated_content = replacer.replace(original_content, needle, repl)
                context.set_updated_content(updated_content)
            return diagnostics_context.format_result(SUCCESS_RESULT)


class ReplaceInFilesTool(EditingToolWithDiagnostics):
    """
    Replaces occurrences of a pattern across multiple files, with dry-run preview and per-occurrence selection.
    """

    def apply(
        self,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        relative_path: str = "",
        paths_include_glob: str = "",
        paths_exclude_glob: str = "",
        dry_run: bool = False,
        occurrence_ids: list[str] | None = None,
        expected_count: int = -1,
        max_answer_chars: int = -1,
    ) -> str:
        r"""
        Replaces occurrences of a pattern across multiple files in ONE call.

        This is the preferred tool for repeated small edits (renames, import swaps, annotation changes,
        path prefixes) spanning several files or many places in one file: one call with a SHORT pattern
        replaces many single-file replacements with long disambiguating needles.

        Recommended protocol whenever there is ANY risk of unintended replacements:
        1. Call with dry_run=True: every prospective change is returned as a minimal line diff with an
           occurrence id; nothing is modified.
        2. Call again with dry_run=False, passing the ids you want in occurrence_ids (omit it to apply
           all). You pick the desired replacements from the list - no counting, no needle-crafting.

        For clearly unambiguous bulk replacements you may skip the dry run; pass expected_count as a
        guard. If the actual number of matches differs, NOTHING is changed and the diff list is
        returned, so a failed guard costs one call and gives you the dry-run output to select from.

        :param needle: the string (mode "literal") or regular expression (mode "regex"; Python `re`
            syntax with DOTALL and MULTILINE) to search for
        :param repl: the replacement string. In regex mode, backreferences to matched groups can be
            specified as $!1, $!2, etc.
        :param mode: either "literal" or "regex", specifying how `needle` is to be interpreted
        :param relative_path: only consider this file or directory (default: the whole project)
        :param paths_include_glob: optional glob (relative to the project root, e.g. "src/**/*.java")
            restricting which files are considered
        :param paths_exclude_glob: optional glob of files to exclude; takes precedence over the include glob
        :param dry_run: if True, do not modify anything; return the prospective changes as a list of
            diffs with occurrence ids
        :param occurrence_ids: optional list of occurrence ids (obtained from a dry run) to which the
            replacement is restricted; if any id is unknown or stale, NOTHING is changed. If omitted,
            all occurrences are replaced.
        :param expected_count: optional guard for calls without occurrence_ids: the number of
            occurrences you expect to be replaced. If the actual count differs, nothing is changed and
            the list of prospective changes is returned. -1 disables the guard.
        :param max_answer_chars: if the output exceeds this many characters, a shortened version is
            returned. -1 uses the configured default.
        :return: in a dry run, the prospective changes; otherwise a summary of the applied replacements
        """
        replacer = MultiFileContentReplacer(mode=mode)
        files = self._collect_files(relative_path, paths_include_glob, paths_exclude_glob)
        occurrences = replacer.find_occurrences(files, needle, repl)
        contents = dict(files)

        if dry_run:
            return self._render_listing(replacer, occurrences, contents, max_answer_chars, dry_run=True)

        if occurrence_ids is not None:
            selected, problems = self._resolve_occurrence_ids(occurrence_ids, occurrences)
            if problems:
                problem_lines = "\n".join(f"  {p}" for p in problems)
                raise ValueError(
                    f"{len(problems)} of the given occurrence_ids could not be resolved - NO changes were applied:\n"
                    f"{problem_lines}\n"
                    "Re-run with dry_run=True to obtain current occurrence ids."
                )
            if not selected:
                raise ValueError("occurrence_ids is empty - pass at least one id from a dry run, or omit the parameter to replace all.")
            return self._apply_occurrences(replacer, selected, contents, needle, repl)

        # blind apply (no ids)
        if not occurrences:
            raise ValueError(
                "No occurrences of the pattern were found - NO changes were applied. "
                "Check the mode (a literal needle containing regex metacharacters must use mode 'literal'; "
                "wildcards require mode 'regex') and the path/glob restrictions, "
                "or locate the content with search_for_pattern first."
            )
        if expected_count >= 0 and len(occurrences) != expected_count:
            listing = self._render_listing(replacer, occurrences, contents, max_answer_chars, dry_run=False)
            raise ValueError(
                f"expected_count={expected_count}, but the pattern matches {len(occurrences)} occurrence(s) - "
                f"NO changes were applied. Review the prospective changes below; re-issue with the corrected "
                f"expectation, a refined pattern, or occurrence_ids selecting the intended subset.\n{listing}"
            )
        ambiguous = [o for o in occurrences if o.is_ambiguous]
        if ambiguous:
            listing = self._render_listing(replacer, occurrences, contents, max_answer_chars, dry_run=False)
            raise ValueError(
                f"{len(ambiguous)} occurrence(s) are ambiguous (the pattern matches again inside the matched text, "
                f"indicating possible over-matching) - NO changes were applied. Review the prospective changes below "
                f"and either refine the pattern or explicitly select occurrences via occurrence_ids.\n{listing}"
            )
        return self._apply_occurrences(replacer, occurrences, contents, needle, repl)

    def _collect_files(self, relative_path: str, paths_include_glob: str, paths_exclude_glob: str) -> list[tuple[str, str]]:
        """Collects (relative_path, content) pairs of the non-ignored files in scope, in sorted path order."""
        relative_path = relative_path.strip()
        if relative_path:
            self.project.validate_relative_path(relative_path, require_not_ignored=True)
        abs_path = os.path.join(self.get_project_root(), relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Relative path {relative_path} does not exist.")
        if os.path.isfile(abs_path):
            rel_paths = [relative_path]
        else:
            _dirs, rel_paths = scan_directory(
                path=abs_path,
                recursive=True,
                is_ignored_dir=self.project.is_ignored_path,
                is_ignored_file=self.project.is_ignored_path,
                relative_to=self.get_project_root(),
            )
        include_patterns = expand_braces(paths_include_glob.strip()) if paths_include_glob.strip() else None
        exclude_patterns = expand_braces(paths_exclude_glob.strip()) if paths_exclude_glob.strip() else None
        files: list[tuple[str, str]] = []
        for path in sorted(rel_paths):
            if include_patterns and not any(glob_match(p, path) for p in include_patterns):
                continue
            if exclude_patterns and any(glob_match(p, path) for p in exclude_patterns):
                continue
            try:
                files.append((path, self.project.read_file(path)))
            except Exception:
                continue  # skip unreadable (e.g. binary) files
        return files

    def _render_listing(
        self,
        replacer: MultiFileContentReplacer,
        occurrences: list[ReplacementOccurrence],
        contents: dict[str, str],
        max_answer_chars: int,
        dry_run: bool,
    ) -> str:
        affected_files = sorted({o.relative_path for o in occurrences})
        header = f"Found {len(occurrences)} occurrence(s) in {len(affected_files)} file(s)."
        if dry_run:
            header += (
                " DRY RUN - no changes were applied.\n"
                "Re-issue with dry_run=False to replace all of them, or additionally pass occurrence_ids "
                "with the ids of the occurrences to replace."
            )
        parts = [header]
        for path in affected_files:
            file_occurrences = [o for o in occurrences if o.relative_path == path]
            parts.append(f"\n{path} ({len(file_occurrences)} occurrence(s)):")
            for occ in file_occurrences:
                parts.append(replacer.render_occurrence_diff(occ, contents[path]))
        result = "\n".join(parts)

        def make_locations_only() -> str:
            lines = [header] + [f"  [{o.occurrence_id}] line {o.start_line}" for o in occurrences]
            return "\n".join(lines)

        def make_per_file_counts() -> str:
            counts = {path: sum(1 for o in occurrences if o.relative_path == path) for path in affected_files}
            return f"{header}\nOccurrence counts per file:\n{self._to_json(counts)}"

        def make_summary() -> str:
            return header

        return self._limit_length(
            result, max_answer_chars, shortened_result_factories=[make_locations_only, make_per_file_counts, make_summary]
        )

    @staticmethod
    def _resolve_occurrence_ids(
        occurrence_ids: list[str], occurrences: list[ReplacementOccurrence]
    ) -> tuple[list[ReplacementOccurrence], list[str]]:
        """Resolves the requested ids against the current occurrences, diagnosing each failure."""
        occurrences_by_id = {o.occurrence_id: o for o in occurrences}
        indices_by_path: dict[str, set[int]] = {}
        for o in occurrences:
            indices_by_path.setdefault(o.relative_path, set()).add(o.index_in_file)
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
        return list(selected.values()), problems

    def _apply_occurrences(
        self,
        replacer: MultiFileContentReplacer,
        occurrences: list[ReplacementOccurrence],
        contents: dict[str, str],
        needle: str,
        repl: str,
    ) -> str:
        occurrences_by_file: dict[str, list[ReplacementOccurrence]] = {}
        for occ in occurrences:
            occurrences_by_file.setdefault(occ.relative_path, []).append(occ)
        with self.DiagnosticsContext(self, *occurrences_by_file.keys()) as diagnostics_context:
            code_editor = self.create_code_editor()
            for path, file_occurrences in occurrences_by_file.items():
                with EditedFileContext(path, code_editor) as context:
                    original_content = context.get_original_content()
                    if original_content != contents[path]:
                        # the editor's view differs from what was scanned (e.g. line-ending normalization);
                        # re-derive the occurrences from the authoritative content and re-validate by id
                        fresh_by_id = {o.occurrence_id: o for o in replacer.find_occurrences([(path, original_content)], needle, repl)}
                        try:
                            file_occurrences = [fresh_by_id[o.occurrence_id] for o in file_occurrences]
                        except KeyError as e:
                            raise ValueError(
                                f"The content of {path} changed while replacing (occurrence {e} no longer resolves); "
                                f"the file was NOT modified. Re-run with dry_run=True for current ids."
                            ) from e
                    context.set_updated_content(replacer.apply_to_content(original_content, file_occurrences))
            per_file = "\n".join(f"  {path}: {len(occs)}" for path, occs in occurrences_by_file.items())
            summary = f"Replaced {len(occurrences)} occurrence(s) in {len(occurrences_by_file)} file(s):\n{per_file}"
            return diagnostics_context.format_result(summary)


class DeleteLinesTool(EditingToolWithDiagnostics, ToolMarkerOptional):
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
        with self.DiagnosticsContext(self, relative_path) as diagnostics_context:
            code_editor = self.create_code_editor()
            code_editor.delete_lines(relative_path, start_line, end_line)
            return diagnostics_context.format_result(SUCCESS_RESULT)


class ReplaceLinesTool(EditingToolWithDiagnostics, ToolMarkerOptional):
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
        # normalizing the replacement content
        if not content.endswith("\n"):
            content += "\n"

        with self.DiagnosticsContext(self, relative_path) as diagnostics_context:
            code_editor = self.create_code_editor()
            code_editor.delete_lines(relative_path, start_line, end_line)
            code_editor.insert_at_line(relative_path, start_line, content)

            return diagnostics_context.format_result(SUCCESS_RESULT)


class InsertAtLineTool(EditingToolWithDiagnostics, ToolMarkerOptional):
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
        # normalizing the inserted content
        if not content.endswith("\n"):
            content += "\n"

        with self.DiagnosticsContext(self, relative_path) as diagnostics_context:
            code_editor = self.create_code_editor()
            code_editor.insert_at_line(relative_path, line, content)

            return diagnostics_context.format_result(SUCCESS_RESULT)


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
        multiline: bool = True,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Searches for a regex pattern across project files, returning whole matched lines (plus optional context).
        Prefer symbolic operations if you know which symbols you are looking for!

        :param substring_pattern: regular expression to search for.
        :param context_lines_before: number of context lines to include before each match.
        :param context_lines_after: number of context lines to include after each match.
        :param paths_include_glob: optional glob (relative to project root, e.g. ``"src/**/*.ts"``) restricting which files are searched.
        :param paths_exclude_glob: optional glob to exclude files; takes precedence over `paths_include_glob`.
        :param relative_path: restricts the search to this file or subdirectory of the project root
        :param restrict_search_to_code_files: whether to search only files containing analyzable code symbols
            (useful when looking for class/method definitions); otherwise also search non-code files.
        :param multiline: whether to apply multi-line matching (default: True), enabling the flags re.DOTALL and re.MULTILINE
        :param max_answer_chars: if the output exceeds this many characters, a progressively shortened summary is returned instead.
            ``-1`` uses the configured default.
        :return: A mapping from file paths to matched consecutive lines (0-based line numbers).
        """
        relative_path = relative_path.strip()
        if relative_path:
            self.project.validate_relative_path(relative_path, require_not_ignored=True)

        abs_path = os.path.join(self.get_project_root(), relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"Relative path {relative_path} does not exist.")

        if restrict_search_to_code_files:
            matches = self.project.search_source_files_for_pattern(
                pattern=substring_pattern,
                relative_path=relative_path,
                context_lines_before=context_lines_before,
                context_lines_after=context_lines_after,
                paths_include_glob=paths_include_glob.strip(),
                paths_exclude_glob=paths_exclude_glob.strip(),
                multiline=multiline,
            )
        else:
            if os.path.isfile(abs_path):
                rel_paths_to_search = [relative_path]
            else:
                _dirs, rel_paths_to_search = scan_directory(
                    path=abs_path,
                    recursive=True,
                    is_ignored_dir=self.project.is_ignored_path,
                    is_ignored_file=self.project.is_ignored_path,
                    relative_to=self.get_project_root(),
                )
            # TODO (maybe): not super efficient to walk through the files again and filter if glob patterns are provided
            #   but it probably never matters and this version required no further refactoring
            matches = search_files(
                rel_paths_to_search,
                substring_pattern,
                context_lines_before=context_lines_before,
                context_lines_after=context_lines_after,
                file_reader=self.project.read_file,
                root_path=self.get_project_root(),
                paths_include_glob=paths_include_glob,
                paths_exclude_glob=paths_exclude_glob,
                multiline=multiline,
            )

        # group matches by file
        file_to_matches: dict[str, list[str]] = defaultdict(list)
        for match in matches:
            assert match.source_file_path is not None
            file_to_matches[match.source_file_path].append(match.to_display_string())

        # capture lightweight match data for shortening before serialization
        match_lines_by_file: dict[str, list[int]] = defaultdict(list)
        for match in matches:
            assert match.source_file_path is not None
            match_lines_by_file[match.source_file_path].append(match.matched_lines[0].line_number)

        # shortened result closures, from least to most aggressive shortening
        def make_lines_only() -> str:
            """Match locations without surrounding context"""
            return f"Match lines per file:\n{self._to_json(match_lines_by_file)}"

        def make_per_file_counts() -> str:
            counts = {path: len(lines) for path, lines in match_lines_by_file.items()}
            return f"Match counts per file:\n{self._to_json(counts)}"

        def make_summary() -> str:
            return f"Found {len(matches)} matches in {len(match_lines_by_file)} files."

        result = self._to_json(file_to_matches)
        return self._limit_length(
            result, max_answer_chars, shortened_result_factories=[make_lines_only, make_per_file_counts, make_summary]
        )
