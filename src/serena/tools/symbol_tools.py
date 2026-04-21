"""
Language server-related tools
"""

import copy
import os
from collections import Counter, defaultdict
from collections.abc import Sequence

from serena.symbol import LanguageServerSymbol, LanguageServerSymbolDictGrouper
from serena.tools import (
    SUCCESS_RESULT,
    Tool,
    ToolMarkerSymbolicEdit,
    ToolMarkerSymbolicRead,
)
from serena.tools.tools_base import ToolMarkerOptional
from solidlsp.ls_types import SymbolKind


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

        # capture kind names and depth-0 snapshots before grouping, which mutates the dicts
        kind_names = [d.get("kind", "unknown") for d in result]
        if depth > 0:
            depth_0_result = [d.copy() for d in result]
            for d in depth_0_result:
                d.pop("children", None)

        compact_result = self.symbol_dict_grouper.group(result)
        result_json_str = self._to_json(compact_result)

        # shortened result closures
        def make_kind_counts() -> str:
            return f"Symbol counts by kind:\n{self._to_json(Counter(kind_names))}"

        if depth == 0:
            shortened_results = [make_kind_counts]
        else:

            def make_depth_0_result() -> str:
                compact_depth_0_result = self.symbol_dict_grouper.group(depth_0_result)
                return "Depth 0 overview:\n" + self._to_json(compact_depth_0_result)

            shortened_results = [make_depth_0_result, make_kind_counts]

        return self._limit_length(result_json_str, max_answer_chars, shortened_result_factories=shortened_results)

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

    # group children by kind, keeping just the name (the parent's name_path makes it unambiguous);
    # we don't group the top-level result list because many tests rely on it being a flat list of symbol dicts
    symbol_dict_grouper = LanguageServerSymbolDictGrouper([], ["kind"], collapse_singleton=True)

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
        max_matches: int = -1,
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
            for the case where the symbol is a class, this will return its methods).
            Ignored if `include_body=True`. Default 0.
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
        :param max_matches: Maximum number of permitted matches. If exceeded, a shortened result is returned
             which allows refining the search. -1 (default) means no limit. Set to 1 if you search for a single symbol.
        :param max_answer_chars: Max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: symbols (with locations) matching the name.
        """
        if include_body:
            depth = 0  # ignore user-specified depth if include_body is True
        assert max_matches != 0, "max_matches must be > 0 or equal to -1."
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
        n_matches = len(symbols)

        def create_short_result_relative_path_to_name_paths() -> str:
            relative_path_to_name_paths: defaultdict[str, list[str]] = defaultdict(list)
            for s in symbols:
                relative_path_to_name_paths[s.location.relative_path or "unknown"].append(s.get_name_path())
            return f"Shortened result:\n{self._to_json(relative_path_to_name_paths)}"

        if 0 < max_matches < n_matches:
            return f"Matched {n_matches}>{max_matches=} symbols.\n" + create_short_result_relative_path_to_name_paths()

        symbol_dicts = [
            s.to_dict(
                kind=True,
                name_path=True,
                name=False,
                relative_path=True,
                body_location=True,
                depth=depth,
                body=include_body,
                children_name=True,
                children_name_path=False,
            )
            for s in symbols
        ]
        if not include_body and include_info:
            info_by_symbol = symbol_retriever.request_info_for_symbol_batch(symbols)
            for s, s_dict in zip(symbols, symbol_dicts, strict=True):
                if symbol_info := info_by_symbol.get(s):
                    # In python 3.15 we could specify extra_items=True in the TypedDict definition,
                    # https://peps.python.org/pep-0728/
                    # If we ever upgrade to 3.15, we can remove the type: ignore[typeddict-unknown-key]
                    s_dict["info"] = symbol_info  # type: ignore[typeddict-unknown-key]

        grouped_symbol_dicts = self.symbol_dict_grouper.group(symbol_dicts)
        result = self._to_json(grouped_symbol_dicts)
        return self._limit_length(result, max_answer_chars, shortened_result_factories=[create_short_result_relative_path_to_name_paths])


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
            Note: for external dependencies, this must be an identifier starting with `<ext` that you have received
            earlier (don't try to guess!).
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

        # capture lightweight reference data before grouping
        ref_summaries = []
        for ref, d in zip(references_in_symbols, reference_dicts, strict=True):
            ref_summaries.append(
                {
                    "name_path": d.get("name_path"),
                    "kind": d.get("kind"),
                    "relative_path": d.get("relative_path"),
                    "reference_line": ref.line,
                }
            )

        result = self.symbol_dict_grouper.group(reference_dicts)  # type: ignore

        # shortened result closures, from least to most aggressive shortening
        def make_refs_without_context() -> str:
            """References with name_path and reference line, without surrounding code lines"""
            grouped = self.symbol_dict_grouper.group(copy.deepcopy(ref_summaries))  # type: ignore
            return f"References without surrounding lines:\n{self._to_json(grouped)}"

        def make_per_file_counts() -> str:
            counts = Counter(str(r["relative_path"]) for r in ref_summaries)
            return f"Reference counts per file:\n{self._to_json(counts)}"

        def make_summary() -> str:
            return f"Found {len(ref_summaries)} references."

        shortened_results = [make_refs_without_context, make_per_file_counts, make_summary]

        result_json = self._to_json(result)
        return self._limit_length(result_json, max_answer_chars, shortened_result_factories=shortened_results)


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
        code_editor = self.create_code_editor()
        code_editor.replace_body(
            name_path,
            relative_file_path=relative_path,
            body=body,
        )
        return SUCCESS_RESULT


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
        Use this to insert code after a class/method/function definition.
        Don't use to insert after assignments (constants, fields).

        :param name_path: name path of the symbol after which to insert content (definitions in the `find_symbol` tool apply)
        :param relative_path: the relative path to the file containing the symbol
        :param body: the body/content to be inserted. The inserted code shall begin with the next line after
            the symbol.
        """
        code_editor = self.create_code_editor()
        code_editor.insert_after_symbol(name_path, relative_file_path=relative_path, body=body)
        return SUCCESS_RESULT


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
        code_editor = self.create_code_editor()
        code_editor.insert_before_symbol(name_path, relative_file_path=relative_path, body=body)
        return SUCCESS_RESULT


class RenameSymbolTool(Tool, ToolMarkerSymbolicEdit):
    """
    Renames a symbol throughout the codebase using language server refactoring capabilities.
    For JB, we use a separate tool.
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
        code_editor = self.create_ls_code_editor()
        status_message = code_editor.rename_symbol(name_path, relative_path=relative_path, new_name=new_name)
        return status_message


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
