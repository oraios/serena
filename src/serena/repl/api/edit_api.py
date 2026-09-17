# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of editing operations, which are independent of the language backend.
"""

from typing import TYPE_CHECKING, Literal

from serena.code_editor import EditedFileContext
from serena.tools import (
    DeleteLinesTool,
    InsertAfterSymbolTool,
    InsertAtLineTool,
    InsertBeforeSymbolTool,
    ReplaceContentTool,
    ReplaceInFilesTool,
    ReplaceLinesTool,
    ReplaceSymbolBodyTool,
)
from serena.util.text_utils import ContentReplacer, MultiFileReplacement, ReplacementOccurrence, ReplacementRejectedError

from ..facade import SUCCESS_RESULT, FacadeApi, ReferencedType, facade_method
from ..representable import Renderer, RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class ReplacementPreview(RepresentableViaRenderer):
    """
    The prospective changes of a multi-file replacement (nothing has been modified).
    Each entry of `occurrences` (`ReplacementOccurrence`) has an `occurrence_id` (to be passed to `replace_in_files`
    in order to apply exactly that occurrence), `relative_path`, `start_line`, `end_line`, `matched_text`, `replacement`
    and `is_ambiguous`.
    """

    def __init__(self, replacement: MultiFileReplacement, renderer: "ReplacementPreviewRenderer"):
        """
        :param replacement: the replacement
        :param renderer: the renderer to use for representing the preview
        """
        super().__init__(renderer)
        self.replacement_ = replacement

    @property
    def occurrences(self) -> list[ReplacementOccurrence]:
        return self.replacement_.occurrences

    @property
    def affected_files(self) -> list[str]:
        return self.replacement_.affected_files


class ReplacementPreviewRenderer(Renderer[ReplacementPreview]):
    """
    Renders the listing of prospective changes (minimal line diffs with occurrence ids), subject to the length limit.
    """

    def __init__(self, agent: "SerenaAgent", max_answer_chars: int, dry_run: bool):
        """
        :param agent: the agent
        :param max_answer_chars: the maximum number of characters; -1 for the configured default
        :param dry_run: whether the listing is the result of a dry run (adding instructions on how to proceed)
        """
        super().__init__(agent, max_answer_chars)
        self._dry_run = dry_run

    def render(self, obj: ReplacementPreview) -> str:
        return obj.replacement_.render_listing(self._get_max_answer_chars(), dry_run=self._dry_run)


class EditApi(FacadeApi):
    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(
            agent,
            name="edit",
            description="modifying content within existing files (independent of the language backend)",
            types=[
                ReferencedType(
                    ReplacementOccurrence,
                    members=["occurrence_id", "relative_path", "start_line", "end_line", "matched_text", "replacement", "is_ambiguous"],
                ),
            ],
        )

    # file-level operations

    @facade_method(can_edit=True, corresponding_tool=ReplaceContentTool)
    def replace_content(
        self,
        relative_path: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool = False,
    ) -> str:
        r"""
        Replaces one or more occurrences of a given pattern in a file with new content.

        VERY IMPORTANT: The "regex" mode allows very large sections of code to be replaced WITHOUT
        quoting them fully: use a needle of the form "beginning.*?end-of-text-to-be-replaced" with
        wildcards instead of pasting the exact original text — shorter, cheaper, and you cannot make
        mistakes, because an ambiguous match returns an error you can refine, so wildcards are safe.
        Prefer regex mode with suitable wildcards for long multi-line replacements; use the
        symbol-level editors when replacing a whole method/class.

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
            If false and multiple occurrences are found, an error will be raised
        :return: a success message
        """
        self._get_project().validate_relative_path(relative_path)
        with EditedFileContext(relative_path, self._create_code_editor()) as context:
            replacer = ContentReplacer(mode=mode, allow_multiple_occurrences=allow_multiple_occurrences)
            context.set_updated_content(replacer.replace(context.get_original_content(), needle, repl))
        return SUCCESS_RESULT

    @facade_method(can_edit=True, corresponding_tool=ReplaceInFilesTool)
    def replace_in_files(
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
    ) -> ReplacementPreview | str:
        r"""
        Replaces occurrences of a pattern across multiple files in ONE call.

        This is the preferred operation for repeated small edits (renames, import swaps, annotation changes,
        path prefixes) spanning several files or many places in one file: one call with a SHORT pattern
        replaces many single-file replacements with long disambiguating needles.

        Recommended protocol whenever there is ANY risk of unintended replacements:
        1. Call with dry_run=True: every prospective change is returned as a minimal line diff with an
           occurrence id; nothing is modified.
        2. Call again with dry_run=False, passing the ids you want in occurrence_ids (omit it to apply
           all). You pick the desired replacements from the list - no counting, no needle-crafting.

        For clearly unambiguous bulk replacements you may skip the dry run; pass expected_count as a
        guard. If the actual number of matches differs, NOTHING is changed and an error containing the
        prospective changes is raised, so a failed guard costs one call and gives you the dry-run output to select from.

        :param needle: the string (mode "literal") or regular expression (mode "regex"; Python `re`
            syntax with DOTALL and MULTILINE) to search for
        :param repl: the replacement string. In regex mode, backreferences to matched groups can be
            specified as $!1, $!2, etc.
        :param mode: either "literal" or "regex", specifying how `needle` is to be interpreted
        :param relative_path: only consider this file or directory (default: the whole project)
        :param paths_include_glob: optional glob (relative to the project root, e.g. "src/**/*.java")
            restricting which files are considered
        :param paths_exclude_glob: optional glob of files to exclude; takes precedence over the include glob
        :param dry_run: if True, do not modify anything; return the prospective changes with occurrence ids
        :param occurrence_ids: optional list of occurrence ids (obtained from a dry run) to which the
            replacement is restricted; if any id is unknown or stale, NOTHING is changed. If omitted,
            all occurrences are replaced.
        :param expected_count: optional guard for calls without occurrence_ids: the number of
            occurrences you expect to be replaced. If the actual count differs, nothing is changed and
            an error containing the prospective changes is raised. -1 disables the guard.
        :return: in a dry run, the prospective changes (`ReplacementPreview`); otherwise a summary of the applied replacements
        """
        replacement = MultiFileReplacement(
            self._get_project(),
            needle,
            repl,
            mode,
            relative_path=relative_path,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
        )
        if dry_run:
            return ReplacementPreview(replacement, ReplacementPreviewRenderer(self._agent, max_answer_chars, dry_run=True))

        # select the occurrences to replace
        try:
            if occurrence_ids is not None:
                occurrences = replacement.select(occurrence_ids)
            else:
                occurrences = replacement.select_all_guarded(expected_count)
        except ReplacementRejectedError as e:
            message = str(e)
            if e.show_prospective_changes:
                preview = ReplacementPreview(replacement, ReplacementPreviewRenderer(self._agent, max_answer_chars, dry_run=False))
                message += "\n" + preview.represent()
            raise ValueError(message) from e

        return replacement.apply(self._create_code_editor(), occurrences).to_display_string()

    # line-level operations

    @facade_method(optional=True, can_edit=True, corresponding_tool=DeleteLinesTool)
    def delete_lines(self, relative_path: str, start_line: int, end_line: int) -> str:
        """
        Deletes the given lines in the file.
        Requires that the same range of lines was previously read to verify correctness of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be deleted
        :param end_line: the 0-based index of the last line to be deleted
        :return: a success message
        """
        self._create_code_editor().delete_lines(relative_path, start_line, end_line)
        return SUCCESS_RESULT

    @facade_method(optional=True, can_edit=True, corresponding_tool=ReplaceLinesTool)
    def replace_lines(self, relative_path: str, start_line: int, end_line: int, content: str) -> str:
        """
        Replaces the given range of lines in the given file.
        Requires that the same range of lines was previously read to verify correctness of the operation.

        :param relative_path: the relative path to the file
        :param start_line: the 0-based index of the first line to be replaced
        :param end_line: the 0-based index of the last line to be replaced
        :param content: the content to insert
        :return: a success message
        """
        code_editor = self._create_code_editor()
        code_editor.delete_lines(relative_path, start_line, end_line)
        code_editor.insert_at_line(relative_path, start_line, self._normalize_inserted_content(content))
        return SUCCESS_RESULT

    @facade_method(optional=True, can_edit=True, corresponding_tool=InsertAtLineTool)
    def insert_at_line(self, relative_path: str, line: int, content: str) -> str:
        """
        Inserts the given content at the given line in the file, pushing existing content of the line down.
        In general, symbolic insert operations like insert_after_symbol or insert_before_symbol should be preferred if you know which
        symbol you are looking for.
        However, this can also be useful for small targeted edits of the body of a longer symbol (without replacing the entire body).

        :param relative_path: the relative path to the file
        :param line: the 0-based index of the line to insert content at
        :param content: the content to be inserted
        :return: a success message
        """
        self._create_code_editor().insert_at_line(relative_path, line, self._normalize_inserted_content(content))
        return SUCCESS_RESULT

    @staticmethod
    def _normalize_inserted_content(content: str) -> str:
        return content if content.endswith("\n") else content + "\n"

    # symbol-level operations

    @facade_method(can_edit=True, corresponding_tool=ReplaceSymbolBodyTool)
    def replace_symbol_body(self, name_path: str, relative_path: str, body: str) -> str:
        """
        Replaces the body of the given symbol.

        IMPORTANT: Only replace symbol bodies if you have previously made a retrieval with include_body=True and thus know what
        constitutes the body!

        :param name_path: name path of the symbol whose body to replace
        :param relative_path: the relative path to the file containing the symbol
        :param body: the new symbol body. The symbol body is the definition of a symbol
            in the programming language, including e.g. the signature line for functions.
            Depending on the language, it may or may not include a preceding docstring or other preceding annotations.
        :return: a success message
        """
        self._create_code_editor().replace_body(name_path, relative_file_path=relative_path, body=body)
        return SUCCESS_RESULT

    @facade_method(can_edit=True, corresponding_tool=InsertAfterSymbolTool)
    def insert_after_symbol(self, name_path: str, relative_path: str, body: str) -> str:
        """
        Inserts code after a class/method/function definition.
        Don't use this to insert after assignments (constants, fields).

        :param name_path: name path of the symbol after which to insert content
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted. The inserted code shall begin with the next line after
            the symbol.
        :return: a success message
        """
        self._create_code_editor().insert_after_symbol(name_path, relative_file_path=relative_path, body=body)
        return SUCCESS_RESULT

    @facade_method(can_edit=True, corresponding_tool=InsertBeforeSymbolTool)
    def insert_before_symbol(self, name_path: str, relative_path: str, body: str) -> str:
        """
        Inserts the given content before the beginning of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment; or
        a new import statement before the first symbol in the file.

        :param name_path: name path of the symbol before which to insert content
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted before the line in which the referenced symbol is defined
        :return: a success message
        """
        self._create_code_editor().insert_before_symbol(name_path, relative_file_path=relative_path, body=body)
        return SUCCESS_RESULT
