"""
Language server-related tools
"""

import os
import re
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from serena.code_editor import EditedFilePath
from serena.symbol import LanguageServerSymbol, LanguageServerSymbolDictGrouper
from serena.tools import (
    SUCCESS_RESULT,
    Tool,
    ToolMarkerSymbolicEdit,
    ToolMarkerSymbolicRead,
)
from serena.tools.tools_base import ToolMarkerOptional
from solidlsp import ls_types
from solidlsp.ls_types import SymbolKind
from solidlsp.lsp_protocol_handler.lsp_types import DiagnosticSeverity

FILE_LEVEL_DIAGNOSTIC_BUCKET = "<file>"


def _diagnostic_severity_name(severity: int | None) -> str:
    if severity is None:
        return "Unknown"
    try:
        return DiagnosticSeverity(severity).name
    except ValueError:
        return f"Severity_{severity}"


def _diagnostic_output_dict(diagnostic: ls_types.Diagnostic) -> dict[str, Any]:
    result: dict[str, Any] = {
        "message": diagnostic["message"],
        "range": diagnostic["range"],
    }
    if "code" in diagnostic:
        result["code"] = diagnostic["code"]
    if "source" in diagnostic:
        result["source"] = diagnostic["source"]
    return result


def _add_grouped_diagnostic(
    grouped_result: dict[str, dict[str, dict[str, list[dict[str, Any]]]]],
    relative_path: str,
    severity_name: str,
    name_path: str,
    diagnostic: ls_types.Diagnostic,
) -> None:
    grouped_result.setdefault(relative_path, {}).setdefault(severity_name, {}).setdefault(name_path, []).append(
        _diagnostic_output_dict(diagnostic)
    )


def _offset_to_line_and_column(text: str, offset: int) -> tuple[int, int]:
    if offset < 0 or offset > len(text):
        raise ValueError(f"Offset out of range: {offset}")
    prefix = text[:offset]
    line = prefix.count("\n")
    previous_newline_offset = prefix.rfind("\n")
    column = offset if previous_newline_offset == -1 else offset - previous_newline_offset - 1
    return line, column


def _line_and_column_to_offset(text: str, line: int, column: int) -> int:
    if line < 0 or column < 0:
        raise ValueError(f"Line and column must be non-negative, got {line=}, {column=}")

    line_start_offsets = [0]
    for match in re.finditer("\n", text):
        line_start_offsets.append(match.end())

    if line >= len(line_start_offsets):
        raise ValueError(f"Line out of range: {line}")

    line_start_offset = line_start_offsets[line]
    line_end_offset = line_start_offsets[line + 1] - 1 if line + 1 < len(line_start_offsets) else len(text)
    if column > line_end_offset - line_start_offset:
        raise ValueError(f"Column out of range for line {line}: {column}")
    return line_start_offset + column


class RestartLanguageServerTool(Tool, ToolMarkerOptional):
    """Restarts the language server, may be necessary when edits not through Serena happen."""

    def apply(self) -> str:
        """Use this tool only on explicit user request or after confirmation.
        It may be necessary to restart the language server if it hangs.
        """
        self.agent.reset_language_server_manager()
        return SUCCESS_RESULT


class GetSymbolsOverviewTool(Tool, ToolMarkerSymbolicRead):
    """
    Gets an overview of the top-level symbols defined in a given file.
    """

    symbol_dict_grouper = LanguageServerSymbolDictGrouper(["kind"], ["kind"], collapse_singleton=True)

    def apply(self, relative_path: str, depth: int = 0, max_answer_chars: int = -1) -> str:
        """
        Use this tool to get a high-level understanding of the code symbols in a file.
        This should be the first tool to call when you want to understand a new file, unless you already know
        what you are looking for.

        :param relative_path: the relative path to the file to get the overview of
        :param depth: depth up to which descendants of top-level symbols shall be retrieved
            (e.g. 1 retrieves immediate children). Default 0.
        :param max_answer_chars: if the overview is longer than this number of characters,
            no content will be returned. -1 means the default value from the config will be used.
            Don't adjust unless there is really no other way to get the content required for the task.
        :return: a JSON object containing symbols grouped by kind in a compact format.
        """
        result = self.get_symbol_overview(relative_path, depth=depth)
        compact_result = self.symbol_dict_grouper.group(result)
        result_json_str = self._to_json(compact_result)
        return self._limit_length(result_json_str, max_answer_chars)

    def get_symbol_overview(self, relative_path: str, depth: int = 0) -> list[LanguageServerSymbol.OutputDict]:
        """
        :param relative_path: relative path to a source file
        :param depth: the depth up to which descendants shall be retrieved
        :return: a list of symbol dictionaries representing the symbol overview of the file
        """
        symbol_retriever = self.create_language_server_symbol_retriever()

        # The symbol overview is capable of working with both files and directories,
        # but we want to ensure that the user provides a file path.
        file_path = os.path.join(self.project.project_root, relative_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File or directory {relative_path} does not exist in the project.")
        if os.path.isdir(file_path):
            raise ValueError(f"Expected a file path, but got a directory path: {relative_path}. ")
        if not symbol_retriever.can_analyze_file(relative_path):
            raise ValueError(
                f"Cannot extract symbols from file {relative_path}. Active languages: {[l.value for l in self.agent.get_active_lsp_languages()]}"
            )

        symbols = symbol_retriever.get_symbol_overview(relative_path)[relative_path]

        def child_inclusion_predicate(s: LanguageServerSymbol) -> bool:
            return not s.is_low_level()

        symbol_dicts = []
        for symbol in symbols:
            symbol_dicts.append(
                symbol.to_dict(
                    name_path=False,
                    name=True,
                    depth=depth,
                    kind=True,
                    relative_path=False,
                    location=False,
                    child_inclusion_predicate=child_inclusion_predicate,
                )
            )
        return symbol_dicts


class FindSymbolTool(Tool, ToolMarkerSymbolicRead):
    """
    Performs a global (or local) search using the language server backend.
    """

    # noinspection PyDefaultArgument
    def apply(
        self,
        name_path_pattern: str,
        depth: int = 0,
        relative_path: str = "",
        include_body: bool = False,
        include_info: bool = False,
        include_kinds: list[int] = [],  # noqa: B006
        exclude_kinds: list[int] = [],  # noqa: B006
        substring_matching: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given name path pattern.
        The returned symbol information can be used for edits or further queries.
        Specify `depth > 0` to also retrieve children/descendants (e.g., methods of a class).

        A name path is a path in the symbol tree *within a source file*.
        For example, the method `my_method` defined in class `MyClass` would have the name path `MyClass/my_method`.
        If a symbol is overloaded (e.g., in Java), a 0-based index is appended (e.g. "MyClass/my_method[0]") to
        uniquely identify it.

        To search for a symbol, you provide a name path pattern that is used to match against name paths.
        It can be
         * a simple name (e.g. "method"), which will match any symbol with that name
         * a relative path like "class/method", which will match any symbol with that name path suffix
         * an absolute name path "/class/method" (absolute name path), which requires an exact match of the full name path within the source file.
        Append an index `[i]` to match a specific overload only, e.g. "MyClass/my_method[1]".

        :param name_path_pattern: the name path matching pattern (see above)
        :param depth: depth up to which descendants shall be retrieved (e.g. use 1 to also retrieve immediate children;
            for the case where the symbol is a class, this will return its methods). Default 0.
        :param relative_path: Optional. Restrict search to this file or directory. If None, searches entire codebase.
            If a directory is passed, the search will be restricted to the files in that directory.
            If a file is passed, the search will be restricted to that file.
            If you have some knowledge about the codebase, you should use this parameter, as it will significantly
            speed up the search as well as reduce the number of results.
        :param include_body: whether to include the symbol's source code. Use judiciously.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the symbol (ignored if include_body is True). Info is never included for child symbols.
            Note: Depending on the language, this can be slow (e.g., C/C++).
        :param include_kinds: List of LSP symbol kind integers to include.
            If not provided, all kinds are included.
        :param exclude_kinds: Optional. List of LSP symbol kind integers to exclude. Takes precedence over `include_kinds`.
            If not provided, no kinds are excluded.
        :param substring_matching: If True, use substring matching for the last element of the pattern, such that
            "Foo/get" would match "Foo/getValue" and "Foo/getData".
        :param max_answer_chars: Max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: a list of symbols (with locations) matching the name.
        """
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbol_retriever = self.create_language_server_symbol_retriever()
        symbols = symbol_retriever.find(
            name_path_pattern,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
            substring_matching=substring_matching,
            within_relative_path=relative_path,
        )
        symbol_dicts = [dict(s.to_dict(kind=True, relative_path=True, body_location=True, depth=depth, body=include_body)) for s in symbols]
        if not include_body and include_info:
            info_by_symbol = symbol_retriever.request_info_for_symbol_batch(symbols)
            for s, s_dict in zip(symbols, symbol_dicts, strict=True):
                if symbol_info := info_by_symbol.get(s):
                    s_dict["info"] = symbol_info
                    s_dict.pop("name", None)  # name is included in the info
        result = self._to_json(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead):
    """
    Finds symbols that reference the given symbol using the language server backend
    """

    symbol_dict_grouper = LanguageServerSymbolDictGrouper(["relative_path", "kind"], ["kind"], collapse_singleton=True)

    # noinspection PyDefaultArgument
    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_kinds: list[int] = [],  # noqa: B006
        exclude_kinds: list[int] = [],  # noqa: B006
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds references to the symbol at the given `name_path`. The result will contain metadata about the referencing symbols
        as well as a short code snippet around the reference.

        :param name_path: for finding the symbol to find references for, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol for which to find references.
            Note that here you can't pass a directory but must pass a file.
        :param include_kinds: same as in the `find_symbol` tool.
        :param exclude_kinds: same as in the `find_symbol` tool.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        include_body = False  # It is probably never a good idea to include the body of the referencing symbols
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbol_retriever = self.create_language_server_symbol_retriever()

        references_in_symbols = symbol_retriever.find_referencing_symbols(
            name_path,
            relative_file_path=relative_path,
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
        )

        reference_dicts = []
        for ref in references_in_symbols:
            ref_dict_orig = ref.symbol.to_dict(kind=True, relative_path=True, depth=0, body=include_body, body_location=True)
            ref_dict = dict(ref_dict_orig)
            if not include_body:
                ref_relative_path = ref.symbol.location.relative_path
                assert ref_relative_path is not None, f"Referencing symbol {ref.symbol.name} has no relative path, this is likely a bug."
                content_around_ref = self.project.retrieve_content_around_line(
                    relative_file_path=ref_relative_path, line=ref.line, context_lines_before=1, context_lines_after=1
                )
                ref_dict["content_around_reference"] = content_around_ref.to_display_string()
            reference_dicts.append(ref_dict)

        result = self.symbol_dict_grouper.group(reference_dicts)  # type: ignore

        result_json = self._to_json(result)
        return self._limit_length(result_json, max_answer_chars)


class FindImplementationsTool(Tool, ToolMarkerSymbolicRead):
    """
    Finds symbols that implement the given symbol using the language server backend.
    """

    # noinspection PyDefaultArgument
    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_info: bool = False,
        include_kinds: list[int] = [],  # noqa: B006
        exclude_kinds: list[int] = [],  # noqa: B006
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds implementations of the symbol at the given `name_path`.

        :param name_path: for finding the symbol to find implementations for, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol for which to find implementations.
            Note that here you can't pass a directory but must pass a file.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the implementing symbols.
        :param include_kinds: same as in the `find_symbol` tool.
        :param exclude_kinds: same as in the `find_symbol` tool.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: a list of JSON objects with the symbols implementing the requested symbol
        """
        include_body = False
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbol_retriever = self.create_language_server_symbol_retriever()

        implementing_symbols = symbol_retriever.find_implementing_symbols(
            name_path,
            relative_file_path=relative_path,
            include_body=include_body,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
        )

        symbol_dicts = [
            dict(s.to_dict(kind=True, relative_path=True, depth=0, body=include_body, body_location=True)) for s in implementing_symbols
        ]
        if include_info:
            info_by_symbol = symbol_retriever.request_info_for_symbol_batch(implementing_symbols)
            for s, s_dict in zip(implementing_symbols, symbol_dicts, strict=True):
                if symbol_info := info_by_symbol.get(s):
                    s_dict["info"] = symbol_info
                    s_dict.pop("name", None)  # name is included in the info

        result = self._to_json(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindDefiningSymbolAtLocationTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds the symbol that defines the symbol at the given file position using the language server backend.
    """

    @staticmethod
    def _defining_symbol_to_result_dict(
        symbol_retriever: Any,
        defining_symbol: LanguageServerSymbol | None,
        include_body: bool,
        include_info: bool,
    ) -> dict[str, Any] | None:
        if defining_symbol is None:
            return None

        symbol_dict = dict(defining_symbol.to_dict(kind=True, relative_path=True, depth=0, body=include_body, body_location=True))
        if not include_body and include_info:
            if symbol_info := symbol_retriever.request_info_for_symbol(defining_symbol):
                symbol_dict["info"] = symbol_info
                symbol_dict.pop("name", None)
        return symbol_dict

    # noinspection PyDefaultArgument
    def apply(
        self,
        relative_path: str,
        line: int,
        column: int,
        include_body: bool = False,
        include_info: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds the defining symbol for the symbol at the given position.

        :param relative_path: the relative path to the file containing the symbol usage.
        :param line: the 0-based line number of the symbol usage.
        :param column: the 0-based column number of the symbol usage.
        :param include_body: whether to include the source code of the defining symbol.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature)
            about the defining symbol. Ignored if no defining symbol is found.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: a JSON object representing the defining symbol, or `null` if no definition was found.
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        defining_symbol = symbol_retriever.find_defining_symbol(
            relative_file_path=relative_path,
            line=line,
            column=column,
            include_body=include_body,
        )

        if defining_symbol is None:
            result = self._to_json(None)
            return self._limit_length(result, max_answer_chars)

        symbol_dict = self._defining_symbol_to_result_dict(symbol_retriever, defining_symbol, include_body, include_info)
        assert symbol_dict is not None
        result = self._to_json(symbol_dict)
        return self._limit_length(result, max_answer_chars)


class FindDefiningSymbolTool(Tool, ToolMarkerSymbolicRead):
    """
    Finds the symbol that defines a uniquely captured regex match in a file or containing symbol body.
    """

    @staticmethod
    def _describe_search_scope(relative_path: str, containing_symbol_name_path: str | None) -> str:
        if containing_symbol_name_path:
            return f"symbol body '{containing_symbol_name_path}' in file '{relative_path}'"
        return f"file '{relative_path}'"

    @classmethod
    def _format_match_preview(cls, match: re.Match[str]) -> str:
        matched_text = match.group(0).replace("\n", "\\n")
        return matched_text[:120]

    @classmethod
    def _get_unique_captured_span(cls, match: re.Match[str], regex: str, search_scope_description: str) -> tuple[int, int] | str:
        if match.re.groups == 0:
            return (
                f"Error: Regex '{regex}' must contain exactly one capturing group that identifies the symbol usage in "
                f"{search_scope_description}."
            )

        matched_capture_spans = [span for span in match.regs[1:] if span != (-1, -1)]
        if len(matched_capture_spans) != 1:
            return (
                f"Error: Regex '{regex}' must produce exactly one matched capture in {search_scope_description}, "
                f"but produced {len(matched_capture_spans)} for match '{cls._format_match_preview(match)}'."
            )

        capture_start_offset, capture_end_offset = matched_capture_spans[0]
        if capture_start_offset == capture_end_offset:
            return (
                f"Error: Regex '{regex}' produced an empty capture in {search_scope_description}; "
                "the capture must select the referenced symbol text."
            )
        return capture_start_offset, capture_end_offset

    def _find_unique_captured_location(
        self,
        relative_path: str,
        regex: str,
        containing_symbol_name_path: str | None,
    ) -> tuple[int, int] | str:
        # retrieving the search region
        file_content = self.project.read_file(relative_path)
        symbol_retriever = self.create_language_server_symbol_retriever()
        search_scope_description = self._describe_search_scope(relative_path, containing_symbol_name_path)
        search_start_offset = 0
        search_text = file_content

        if containing_symbol_name_path:
            try:
                containing_symbol = symbol_retriever.find_unique(containing_symbol_name_path, within_relative_path=relative_path)
            except Exception as e:
                return f"Error: Could not resolve containing symbol '{containing_symbol_name_path}' in file '{relative_path}': {e}"

            body_start_position = containing_symbol.get_body_start_position_or_raise()
            body_end_position = containing_symbol.get_body_end_position_or_raise()
            search_start_offset = _line_and_column_to_offset(file_content, body_start_position.line, body_start_position.col)
            search_end_offset = _line_and_column_to_offset(file_content, body_end_position.line, body_end_position.col)
            search_text = file_content[search_start_offset:search_end_offset]

        # finding regex matches
        try:
            compiled_regex = re.compile(regex, re.MULTILINE)
        except re.error as e:
            return f"Error: Invalid regex '{regex}': {e}"

        if compiled_regex.groups == 0:
            return (
                f"Error: Regex '{regex}' must contain exactly one capturing group that identifies the symbol usage in "
                f"{search_scope_description}."
            )

        matches = list(compiled_regex.finditer(search_text))
        if len(matches) != 1:
            match_previews = [self._format_match_preview(match) for match in matches[:3]]
            preview_suffix = f" Matches: {match_previews}" if match_previews else ""
            return (
                f"Error: Expected exactly one regex match for '{regex}' in {search_scope_description}, "
                f"but found {len(matches)}.{preview_suffix}"
            )

        capture_span_or_error = self._get_unique_captured_span(matches[0], regex, search_scope_description)
        if isinstance(capture_span_or_error, str):
            return capture_span_or_error

        capture_start_offset, _ = capture_span_or_error
        absolute_capture_start_offset = search_start_offset + capture_start_offset
        return _offset_to_line_and_column(file_content, absolute_capture_start_offset)

    # noinspection PyDefaultArgument
    def apply(
        self,
        regex: str,
        relative_path: str,
        containing_symbol_name_path: str = "",
        include_body: bool = False,
        include_info: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        r"""
        Finds the defining symbol for a uniquely captured regex match in a file.

        The regex must contain exactly one capturing group, and exactly one overall match must be found.
        The capture identifies the symbol usage whose definition should be resolved.

        The regex is compiled with ``re.MULTILINE`` enabled and ``re.DOTALL`` disabled. This keeps common
        single-symbol matches predictable. If cross-line matching is needed, opt in explicitly with ``(?s)``
        or ``[\\s\\S]*?``.

        :param regex: a Python regular expression containing exactly one capturing group.
        :param relative_path: the relative path to the file containing the symbol usage.
        :param containing_symbol_name_path: optional name path of a containing symbol whose body shall be searched instead of the full file.
        :param include_body: whether to include the source code of the defining symbol.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature)
            about the defining symbol. Ignored if no defining symbol is found.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: a JSON object representing the defining symbol, or ``null`` if no definition was found.
            If the regex does not identify a unique captured match, an informative error string is returned.
        """
        captured_location_or_error = self._find_unique_captured_location(
            relative_path=relative_path,
            regex=regex,
            containing_symbol_name_path=containing_symbol_name_path or None,
        )
        if isinstance(captured_location_or_error, str):
            return captured_location_or_error

        line, column = captured_location_or_error
        symbol_retriever = self.create_language_server_symbol_retriever()
        defining_symbol = symbol_retriever.find_defining_symbol(
            relative_file_path=relative_path,
            line=line,
            column=column,
            include_body=include_body,
        )
        symbol_dict = FindDefiningSymbolAtLocationTool._defining_symbol_to_result_dict(
            symbol_retriever,
            defining_symbol,
            include_body,
            include_info,
        )
        result = self._to_json(symbol_dict)
        return self._limit_length(result, max_answer_chars)


class GetDiagnosticsForFileTool(Tool, ToolMarkerSymbolicRead):
    """
    Gets diagnostics for a file, optionally restricted to a line range, grouped by file, severity, and containing symbol.
    """

    def apply(
        self,
        relative_path: str,
        start_line: int = 0,
        end_line: int = -1,
        min_severity: int = 4,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Gets diagnostics for a file. Diagnostics are grouped as `relative_path -> severity -> name_path -> diagnostics_results`.
        If a diagnostic cannot be mapped to a symbol, it is grouped under the special name path `<file>`.

        :param relative_path: the relative path to the file to inspect.
        :param start_line: the first 0-based line to include. Defaults to 0.
        :param end_line: the last 0-based line to include. Defaults to -1, which means until the end of the file.
        :param min_severity: minimum LSP severity to include, where 1=Error, 2=Warning, 3=Information, 4=Hint.
            Diagnostics with lower-or-equal numeric severity are returned.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: grouped diagnostics for the requested file.
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        diagnostics = symbol_retriever.get_file_diagnostics(
            relative_file_path=relative_path,
            start_line=start_line,
            end_line=end_line,
            min_severity=min_severity,
        )

        grouped_result: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
        for diagnostic in diagnostics:
            diag_range = diagnostic["range"]["start"]
            name_path = FILE_LEVEL_DIAGNOSTIC_BUCKET
            owner_symbol = symbol_retriever.find_diagnostic_owner_symbol(
                relative_file_path=relative_path,
                line=diag_range["line"],
                column=diag_range["character"],
            )
            if owner_symbol is not None:
                name_path = owner_symbol.get_name_path()
            _add_grouped_diagnostic(
                grouped_result,
                relative_path=relative_path,
                severity_name=_diagnostic_severity_name(diagnostic.get("severity")),
                name_path=name_path,
                diagnostic=diagnostic,
            )

        result = self._to_json(grouped_result)
        return self._limit_length(result, max_answer_chars)


class GetDiagnosticsForSymbolTool(Tool, ToolMarkerSymbolicRead):
    """
    Gets diagnostics for a symbol and, optionally, for symbols that reference it.
    """

    def apply(
        self,
        name_path: str,
        reference_file: str = "",
        check_symbol_references: bool = False,
        min_severity: int = 4,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Gets diagnostics for the specified symbol. When `check_symbol_references` is true, diagnostics for all
        referencing symbols are also included. The result is grouped as
        `relative_path -> severity -> name_path -> diagnostics_results`.

        :param name_path: the name path of the symbol to inspect.
        :param reference_file: optional file path used to disambiguate the symbol search.
        :param check_symbol_references: whether to additionally collect diagnostics for symbols that reference the symbol.
        :param min_severity: minimum LSP severity to include, where 1=Error, 2=Warning, 3=Information, 4=Hint.
            Diagnostics with lower-or-equal numeric severity are returned.
        :param max_answer_chars: same as in the `find_symbol` tool.
        :return: grouped diagnostics for the requested symbol and, optionally, its referencing symbols.
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        diagnostics_by_symbol = symbol_retriever.get_symbol_diagnostics(
            name_path=name_path,
            reference_file=reference_file or None,
            check_symbol_references=check_symbol_references,
            min_severity=min_severity,
        )

        grouped_result: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
        for symbol, diagnostics in diagnostics_by_symbol.items():
            relative_path = symbol.relative_path
            if relative_path is None:
                continue
            symbol_name_path = symbol.get_name_path()
            for diagnostic in diagnostics:
                _add_grouped_diagnostic(
                    grouped_result,
                    relative_path=relative_path,
                    severity_name=_diagnostic_severity_name(diagnostic.get("severity")),
                    name_path=symbol_name_path,
                    diagnostic=diagnostic,
                )

        result = self._to_json(grouped_result)
        return self._limit_length(result, max_answer_chars)


class ReplaceSymbolBodyTool(Tool, ToolMarkerSymbolicEdit):
    """
    Replaces the full definition of a symbol using the language server backend.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        r"""
        Replaces the body of the symbol with the given `name_path`.

        The tool shall be used to replace symbol bodies that have been previously retrieved
        (e.g. via `find_symbol`).
        IMPORTANT: Do not use this tool if you do not know what exactly constitutes the body of the symbol.

        :param name_path: for finding the symbol to replace, same logic as in the `find_symbol` tool.
        :param relative_path: the relative path to the file containing the symbol
        :param body: the new symbol body. The symbol body is the definition of a symbol
            in the programming language, including e.g. the signature line for functions.
            IMPORTANT: The body does NOT include any preceding docstrings/comments or imports, in particular.
        """
        # capturing diagnostics before the edit
        edited_file_paths = [EditedFilePath(relative_path, relative_path)]
        diagnostics_snapshot = self._capture_published_lsp_diagnostics_snapshot(edited_file_paths)

        # applying the symbol replacement
        code_editor = self.create_code_editor()
        code_editor.replace_body(
            name_path,
            relative_file_path=relative_path,
            body=body,
        )

        return self._format_lsp_edit_result_with_new_diagnostics(SUCCESS_RESULT, edited_file_paths, diagnostics_snapshot)


class InsertAfterSymbolTool(Tool, ToolMarkerSymbolicEdit):
    """
    Inserts content after the end of the definition of a given symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        """
        Inserts the given body/content after the end of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.

        :param name_path: name path of the symbol after which to insert content (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted. The inserted code shall begin with the next line after
            the symbol.
        """
        # capturing diagnostics before the edit
        edited_file_paths = [EditedFilePath(relative_path, relative_path)]
        diagnostics_snapshot = self._capture_published_lsp_diagnostics_snapshot(edited_file_paths)

        # applying the insertion
        code_editor = self.create_code_editor()
        code_editor.insert_after_symbol(name_path, relative_file_path=relative_path, body=body)

        return self._format_lsp_edit_result_with_new_diagnostics(SUCCESS_RESULT, edited_file_paths, diagnostics_snapshot)


class InsertBeforeSymbolTool(Tool, ToolMarkerSymbolicEdit):
    """
    Inserts content before the beginning of the definition of a given symbol.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        body: str,
    ) -> str:
        """
        Inserts the given content before the beginning of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment; or
        a new import statement before the first symbol in the file.

        :param name_path: name path of the symbol before which to insert content (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted before the line in which the referenced symbol is defined
        """
        # capturing diagnostics before the edit
        edited_file_paths = [EditedFilePath(relative_path, relative_path)]
        diagnostics_snapshot = self._capture_published_lsp_diagnostics_snapshot(edited_file_paths)

        # applying the insertion
        code_editor = self.create_code_editor()
        code_editor.insert_before_symbol(name_path, relative_file_path=relative_path, body=body)

        return self._format_lsp_edit_result_with_new_diagnostics(SUCCESS_RESULT, edited_file_paths, diagnostics_snapshot)


class RenameSymbolTool(Tool, ToolMarkerSymbolicEdit):
    """
    Renames a symbol throughout the codebase using language server refactoring capabilities.
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        new_name: str,
    ) -> str:
        """
        Renames the symbol with the given `name_path` to `new_name` throughout the entire codebase.
        Note: for languages with method overloading, like Java, name_path may have to include a method's
        signature to uniquely identify a method.

        :param name_path: name path of the symbol to rename (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol to rename
        :param new_name: the new name for the symbol
        :return: result summary indicating success or failure
        """
        # capturing diagnostics before the edit
        code_editor = self.create_code_editor()
        diagnostics_snapshot = self._capture_published_lsp_diagnostics_snapshot([EditedFilePath(relative_path, relative_path)])

        # applying the rename
        status_message = code_editor.rename_symbol(name_path, relative_file_path=relative_path, new_name=new_name)

        return self._format_lsp_edit_result_with_new_diagnostics(
            status_message, code_editor.get_last_edited_file_paths(), diagnostics_snapshot
        )


class SafeDeleteSymbol(Tool, ToolMarkerSymbolicEdit):
    def apply(
        self,
        name_path_pattern: str,
        relative_path: str,
    ) -> str:
        """
        Deletes the symbol if it is safe to do so (i.e., if there are no references to it)
        or returns a list of references to it.

        :param name_path_pattern: name path of the symbol to delete (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol to delete
        """
        ls_symbol_retriever = self.create_language_server_symbol_retriever()
        symbol = ls_symbol_retriever.find_unique(name_path_pattern, substring_matching=False, within_relative_path=relative_path)
        symbol_rel_path = symbol.relative_path
        assert symbol_rel_path is not None, f"Symbol {name_path_pattern} has no relative path, this is likely a bug."
        assert symbol_rel_path == relative_path, f"Symbol {name_path_pattern} is not in the expected relative path {relative_path}."
        symbol_name_path = symbol.get_name_path()

        symbol_line = symbol.line
        symbol_col = symbol.column
        assert symbol_line is not None and symbol_col is not None, (
            f"Symbol {name_path_pattern} has no identifier position, this is likely a bug."
        )
        lang_server = ls_symbol_retriever.get_language_server(symbol_rel_path)
        references_locations = lang_server.request_references(symbol_rel_path, symbol_line, symbol_col)
        file_to_lines: dict[str, list[int]] = defaultdict(list)
        if references_locations:
            for ref_loc in references_locations:
                ref_relative_path = ref_loc.get("relativePath")
                if ref_relative_path is None:
                    continue
                file_to_lines[ref_relative_path].append(ref_loc["range"]["start"]["line"])
        if file_to_lines:
            return f"Cannot delete, the symbol {symbol_name_path} is referenced in: {self._to_json(file_to_lines)}"
        code_editor = self.create_ls_code_editor()
        code_editor.delete_symbol(symbol_name_path, relative_file_path=symbol_rel_path)
        return SUCCESS_RESULT
