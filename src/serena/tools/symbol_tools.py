"""
Language server-related tools
"""

import os
from collections.abc import Sequence
from copy import copy
from typing import Any

from serena.tools import (
    SUCCESS_RESULT,
    Tool,
    ToolMarkerSymbolicEdit,
    ToolMarkerSymbolicRead,
)
from serena.tools.tools_base import ToolMarkerOptional
from solidlsp.ls_types import SymbolKind
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler import lsp_types


def _sanitize_symbol_dict(symbol_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize a symbol dictionary inplace by removing unnecessary information.
    """
    # We replace the location entry, which repeats line information already included in body_location
    # and has unnecessary information on column, by just the relative path.
    symbol_dict = copy(symbol_dict)
    s_relative_path = symbol_dict.get("location", {}).get("relative_path")
    if s_relative_path is not None:
        symbol_dict["relative_path"] = s_relative_path
    symbol_dict.pop("location", None)
    # also remove name, name_path should be enough
    symbol_dict.pop("name")
    return symbol_dict


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
        :return: a JSON object containing info about top-level symbols in the file
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        file_path = os.path.join(self.project.project_root, relative_path)

        # The symbol overview is capable of working with both files and directories,
        # but we want to ensure that the user provides a file path.
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File or directory {relative_path} does not exist in the project.")
        if os.path.isdir(file_path):
            raise ValueError(f"Expected a file path, but got a directory path: {relative_path}. ")
        result = symbol_retriever.get_symbol_overview(relative_path, depth=depth)[relative_path]
        result_json_str = self._to_json(result)
        return self._limit_length(result_json_str, max_answer_chars)


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
            for the case where the symbol is a class, this will return its methods).
            Default 0.
        :param relative_path: Optional. Restrict search to this file or directory. If None, searches entire codebase.
            If a directory is passed, the search will be restricted to the files in that directory.
            If a file is passed, the search will be restricted to that file.
            If you have some knowledge about the codebase, you should use this parameter, as it will significantly
            speed up the search as well as reduce the number of results.
        :param include_body: If True, include the symbol's source code. Use judiciously.
        :param include_kinds: Optional. List of LSP symbol kind integers to include. (e.g., 5 for Class, 12 for Function).
            Valid kinds: 1=file, 2=module, 3=namespace, 4=package, 5=class, 6=method, 7=property, 8=field, 9=constructor, 10=enum,
            11=interface, 12=function, 13=variable, 14=constant, 15=string, 16=number, 17=boolean, 18=array, 19=object,
            20=key, 21=null, 22=enum member, 23=struct, 24=event, 25=operator, 26=type parameter.
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
        symbol_dicts = [_sanitize_symbol_dict(s.to_dict(kind=True, location=True, depth=depth, include_body=include_body)) for s in symbols]
        result = self._to_json(symbol_dicts)
        return self._limit_length(result, max_answer_chars)


class FindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead):
    """
    Finds symbols that reference the given symbol using the language server backend
    """

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
            ref_dict = ref.symbol.to_dict(kind=True, location=True, depth=0, include_body=include_body)
            ref_dict = _sanitize_symbol_dict(ref_dict)
            if not include_body:
                ref_relative_path = ref.symbol.location.relative_path
                assert ref_relative_path is not None, f"Referencing symbol {ref.symbol.name} has no relative path, this is likely a bug."
                content_around_ref = self.project.retrieve_content_around_line(
                    relative_file_path=ref_relative_path, line=ref.line, context_lines_before=1, context_lines_after=1
                )
                ref_dict["content_around_reference"] = content_around_ref.to_display_string()
            reference_dicts.append(ref_dict)
        result = self._to_json(reference_dicts)
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
        Inserts the given body/content after the end of the definition of the given symbol (via the symbol's location).
        A typical use case is to insert a new class, function, method, field or variable assignment.

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
        code_editor = self.create_code_editor()
        status_message = code_editor.rename_symbol(name_path, relative_file_path=relative_path, new_name=new_name)
        return status_message


class CompletionTool(Tool, ToolMarkerSymbolicRead):
    """Get code completion suggestions at a cursor position."""

    def apply(
        self,
        relative_path: str,
        line: int,
        character: int,
        trigger_character: str = "",
        max_answer_chars: int = -1,
    ) -> str:
        """
        Request code completion suggestions at a specific position in a file.
        Use this before writing code to discover available methods, variables, or types.

        :param relative_path: the relative path to the file
        :param line: 0-indexed line number where completion is requested
        :param character: 0-indexed character position on the line
        :param trigger_character: optional trigger character (e.g., ".", "(") that initiated completion
        :param max_answer_chars: if result is longer than this, no content returned.
            -1 means default from config. Don't adjust unless necessary.
        :return: JSON array of completion items with label, kind, detail, documentation
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        file_path = os.path.join(self.project.project_root, relative_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {relative_path} does not exist in the project.")
        if os.path.isdir(file_path):
            raise ValueError(f"Expected a file path, but got a directory: {relative_path}")

        ls = symbol_retriever.get_language_server(relative_path)
        file_uri = PathUtils.path_to_uri(file_path)

        params = lsp_types.CompletionParams(textDocument={"uri": file_uri}, position={"line": line, "character": character})

        if trigger_character:
            params["context"] = {"triggerKind": lsp_types.CompletionTriggerKind.TriggerCharacter, "triggerCharacter": trigger_character}

        with ls.open_file(relative_path):
            ls.completions_available.wait()
            result = ls.server.send.completion(params)

        if result is None:
            return self._to_json({"message": "No completions available"})

        # Handle both CompletionList and list[CompletionItem]
        if isinstance(result, dict) and "items" in result:
            items = result["items"]
        else:
            items = result

        # Extract relevant fields
        simplified_items = []
        for item in items:
            simplified = {
                "label": item.get("label", ""),
                "kind": item.get("kind"),
                "detail": item.get("detail"),
                "documentation": item.get("documentation"),
                "insertText": item.get("insertText"),
            }
            simplified_items.append(simplified)

        result_json = self._to_json(simplified_items)
        return self._limit_length(result_json, max_answer_chars)


class HoverTool(Tool, ToolMarkerSymbolicRead):
    """Get type information and documentation at a cursor position."""

    def apply(self, relative_path: str, line: int, character: int, max_answer_chars: int = -1) -> str:
        """
        Request hover information (type, documentation) at a specific position in a file.
        Use this before editing to understand what a symbol is and what it does.

        :param relative_path: the relative path to the file
        :param line: 0-indexed line number
        :param character: 0-indexed character position on the line
        :param max_answer_chars: if result is longer than this, no content returned.
            -1 means default from config. Don't adjust unless necessary.
        :return: JSON object with hover contents and optional range
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        file_path = os.path.join(self.project.project_root, relative_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {relative_path} does not exist in the project.")
        if os.path.isdir(file_path):
            raise ValueError(f"Expected a file path, but got a directory: {relative_path}")

        ls = symbol_retriever.get_language_server(relative_path)
        file_uri = PathUtils.path_to_uri(file_path)

        params = lsp_types.HoverParams(textDocument={"uri": file_uri}, position={"line": line, "character": character})

        with ls.open_file(relative_path):
            ls.completions_available.wait()
            result = ls.server.send.hover(params)

        if result is None:
            return self._to_json({"message": "No hover information available"})

        result_json = self._to_json(result)
        return self._limit_length(result_json, max_answer_chars)


class InlayHintsTool(Tool, ToolMarkerSymbolicRead):
    """Get type hints and parameter names for a code range."""

    def apply(
        self,
        relative_path: str,
        start_line: int = 0,
        end_line: int = -1,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Request inlay hints (type annotations, parameter names) for a range of lines.
        Use this to understand implicit types and parameter names in existing code.

        :param relative_path: the relative path to the file
        :param start_line: 0-indexed start line (default: 0)
        :param end_line: 0-indexed end line (default: -1 for end of file)
        :param max_answer_chars: if result is longer than this, no content returned.
            -1 means default from config. Don't adjust unless necessary.
        :return: JSON array of inlay hints with position, label, kind, tooltip
        """
        symbol_retriever = self.create_language_server_symbol_retriever()
        file_path = os.path.join(self.project.project_root, relative_path)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {relative_path} does not exist in the project.")
        if os.path.isdir(file_path):
            raise ValueError(f"Expected a file path, but got a directory: {relative_path}")

        # Determine end_line if not specified
        if end_line == -1:
            with open(file_path) as f:
                end_line = len(f.readlines())

        ls = symbol_retriever.get_language_server(relative_path)
        file_uri = PathUtils.path_to_uri(file_path)

        params = lsp_types.InlayHintParams(
            textDocument={"uri": file_uri},
            range={
                "start": {"line": start_line, "character": 0},
                "end": {"line": end_line, "character": 0},
            },
        )

        with ls.open_file(relative_path):
            ls.completions_available.wait()
            result = ls.server.send.inlay_hint(params)

        if result is None:
            return self._to_json({"message": "No inlay hints available"})

        result_json = self._to_json(result)
        return self._limit_length(result_json, max_answer_chars)


class GetDiagnosticsTool(Tool, ToolMarkerSymbolicRead):
    """Get compiler/linter diagnostics (errors, warnings) for files."""

    _SEVERITY_NAMES = ["Error", "Warning", "Info", "Hint"]

    def apply(
        self,
        relative_path: str = "",
        min_severity: int = 2,
        max_results: int = 50,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Get diagnostics (errors, warnings, hints) from the language server.
        Diagnostics are automatically collected when files are opened.

        :param relative_path: File to get diagnostics for. Empty string = all files with diagnostics.
        :param min_severity: Minimum severity to include (1=Error, 2=Warning, 3=Info, 4=Hint).
                            Default 2 includes errors and warnings.
        :param max_results: Maximum number of diagnostics to return.
        :param max_answer_chars: Max output length. -1 = default from config.
        :return: JSON with diagnostics grouped by file.
        """
        symbol_retriever = self.create_language_server_symbol_retriever()

        if relative_path:
            file_path = os.path.join(self.project.project_root, relative_path)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File {relative_path} does not exist.")
            if os.path.isdir(file_path):
                raise ValueError(f"Path {relative_path} is a directory, not a file.")
            ls = symbol_retriever.get_language_server(relative_path)
            with ls.open_file(relative_path):
                ls.completions_available.wait()
                # Wait a bit for diagnostics to be published
                import time

                time.sleep(0.5)
                raw_diagnostics = ls.get_diagnostics(relative_path)
        else:
            raw_diagnostics = {}
            for ls in symbol_retriever.get_all_language_servers():
                raw_diagnostics.update(ls.get_diagnostics())

        result = []
        for uri, diagnostics in raw_diagnostics.items():
            diag_file_path = PathUtils.uri_to_path(uri)
            rel_path = os.path.relpath(diag_file_path, self.project.project_root)

            for diag in diagnostics:
                severity = diag.get("severity", 1)
                if severity > min_severity:
                    continue

                diag_range = diag.get("range", {})
                start_pos = diag_range.get("start", {})
                result.append(
                    {
                        "file": rel_path,
                        "line": start_pos.get("line", 0) + 1,
                        "character": start_pos.get("character", 0),
                        "severity": self._SEVERITY_NAMES[severity - 1] if 1 <= severity <= 4 else str(severity),
                        "message": diag.get("message", ""),
                        "source": diag.get("source", ""),
                        "code": diag.get("code", ""),
                    }
                )

                if len(result) >= max_results:
                    break
            if len(result) >= max_results:
                break

        output = {"total": len(result), "diagnostics": result}
        result_json = self._to_json(output)
        return self._limit_length(result_json, max_answer_chars)
