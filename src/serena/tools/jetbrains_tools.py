# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from typing import TYPE_CHECKING, Literal

from serena.facades.api.jb import JetBrainsApi
from serena.tools import Tool, ToolMarkerBeta, ToolMarkerOptional, ToolMarkerSymbolicEdit, ToolMarkerSymbolicRead

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

log = logging.getLogger(__name__)


class JetBrainsApiMixin:
    """
    Mixin for tools which delegate to the JetBrains API
    """

    agent: "SerenaAgent"

    def _api(self) -> JetBrainsApi:
        return JetBrainsApi(self.agent)


class JetBrainsFindSymbolTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Performs a global (or local) search for symbols using the JetBrains backend
    """

    symbol_dict_grouper = JetBrainsApi.find_symbol_grouper_

    def apply(
        self,
        name_path_pattern: str,
        depth: int = 0,
        relative_path: str | None = None,
        include_body: bool = False,
        include_info: bool = False,
        search_deps: bool = False,
        max_matches: int = -1,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds symbols and code entities (classes, methods, etc.) based on the given name path pattern.
        The returned symbol information can be used for edits or further queries.
        Specify `depth > 0` to retrieve children (e.g., methods of a class).
        Important: through `search_deps=True` dependencies can be searched, which
        should be preferred to web search or other less sophisticated approaches to analyzing dependencies.
        You will always receive at least quick info for returned symbols (even if `include_info=False`).

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
        In any path component, using `*` will match any sequence of characters (excluding /), e.g. "Class/*substring*" matches a member substring.
        A pattern must not contain only wildcards (e.g. "*" or "/*").

        :param name_path_pattern: the name path matching pattern (see above)
        :param depth: depth up to which descendants shall be retrieved (e.g. use 1 to also retrieve immediate children;
            for the case where the symbol is a class, this will return its methods).
            Ignored if `include_body=True`. Default 0.
        :param relative_path: Optional. Restrict search to this file or directory. If not specified, searches entire codebase.
            Note: for external dependencies, this must be an identifier starting with `<ext` that you have received
            earlier (don't try to guess!).
        :param include_body: If True, include the symbol's full source code.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the symbol.
            Default False; info is never included for child symbols or if include_body is True.
        :param search_deps: If True, also search in project dependencies (e.g., libraries).
        :param max_matches: Maximum number of permitted matches. If exceeded, a shortened result is returned
             which allows refining the search. -1 (default) means no limit. Set to 1 if you search for a single symbol.
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :return: symbols matching the name.
        """
        name_path_pattern = self._sanitize_input_param(name_path_pattern)
        if relative_path:
            relative_path = self._sanitize_input_param(relative_path)

        # for a wildcard-only pattern restricted to a file, delegate to the overview tool
        if name_path_pattern.replace("*", "").replace("/", "") == "" and relative_path:
            if self.project.relative_path_exists(relative_path, require_file=True):
                overview_tool = self.agent.get_tool(JetBrainsGetSymbolsOverviewTool)
                overview_response = overview_tool.apply(relative_path, depth=depth)
                return self._wrapped_tool_response(
                    overview_response, f"Wildcard-only pattern not admitted; used {overview_tool.get_name()} instead"
                )

        return (
            self._api()
            .find_symbol(
                name_path_pattern,
                depth=depth,
                relative_path=relative_path,
                include_body=include_body,
                include_info=include_info,
                search_deps=search_deps,
                max_matches=max_matches,
                max_answer_chars=max_answer_chars,
            )
            .represent()
        )

    @classmethod
    def get_param_aliases(cls) -> dict[str, str]:
        return {"name_path": "name_path_pattern"}


class JetBrainsMoveTool(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, ToolMarkerBeta, JetBrainsApiMixin):
    """
    Moves a symbol, file or directory to a new location using the JetBrains backend, updating all references
    """

    def apply(
        self,
        relative_path: str,
        name_path: str | None = None,
        target_relative_path: str | None = None,
        target_parent_name_path: str | None = None,
    ) -> str:
        """
        Moves a symbol, file or directory to a different location and automatically update all references to affected symbols.
        **Important**: this tool should always be preferred to naive moving (e.g. via file system operations or edits)
        as it is much more reliable and efficient. It is always safe to use this tool. For some symbols, moving may not be applicable,
        and will result in no edits and a suitable error message.
        The target location is the new parent of the symbol,
        i.e. the moved entity is never renamed by the operation, only moved.


        Valid moves:
        - Symbol:
           * (relative_path, name_path) -> new parent symbol (target_relative_path, target_parent_name_path)
           * (relative_path, name_path) -> top level of target file or directory (target_relative_path)
             Always consider the concrete language-specific semantics!
             - target is a file: valid for languages like Python, where files are modules
             - target is a directory: valid for languages like Java, where directories are packages and can contain classes
        - File or directory:
           * relative_path -> new parent directory (target_relative_path)

        :param relative_path: the relative path to the file containing the symbol to move.
        :param name_path: the name path of the symbol to move (empty for moving file or dir).
        :param target_relative_path: the relative path of the target directory or file.
        :param target_parent_name_path: the name path of the target parent symbol.
        """
        relative_path = self._sanitize_input_param(relative_path)
        return self._api().move(relative_path, name_path, target_relative_path, target_parent_name_path).represent()


class JetBrainsSafeDeleteTool(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, ToolMarkerBeta, JetBrainsApiMixin):
    """
    Safely deletes a symbol using the JetBrains backend, checking for remaining usages first
    """

    def apply(
        self,
        relative_path: str,
        name_path: str | None = None,
        delete_even_if_used: bool = False,
        propagate: bool = False,
    ) -> str:
        """
        Safely deletes a symbol, file, or directory, checking for usages first and propagating deletion, if desired.
        Propagation means it is possible to request deleting of usages and cleaning up of unused code.
        Propagation is powerful for cleaning up code but should be used with care, and only when you are sure that
        **Important**: this tool should always be preferred to naive deleting (e.g. via file system operations or edits).
        When using it, you don't have to search for usages first, as the tool will do it for you.

        :param relative_path: the relative path to the file containing the symbol to delete.
        :param name_path: the name path of the symbol to delete.
            A name path identifies a symbol within a source file, e.g. "MyClass/my_method".
            Omit for deleting a file or directory.
        :param delete_even_if_used: whether to force deletion even if the symbol still has usages.
            Default is False (safe mode: will report usages instead of deleting).
        :param propagate: whether to propagate the deletion to usages of the symbol and also
            remove symbols that become unused after the deletion. Default is False.
        """
        relative_path = self._sanitize_input_param(relative_path)
        return self._api().safe_delete(relative_path, name_path, delete_even_if_used, propagate).represent()


class JetBrainsInlineSymbol(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, ToolMarkerBeta, JetBrainsApiMixin):
    """
    Inlines a symbol using the JetBrains backend, replacing all call sites with the symbol's body
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        keep_definition: bool = False,
    ) -> str:
        """
        Inlines a symbol (usually a method/function, but also classes may be amenable to inlining,
        which turns invocation into anonymous class creation),
        replacing all call sites with the symbol's body.
        **Important**: this tool should always be preferred to naive inlining (e.g. via searching for references and
        editing them).

        :param name_path: the name path of the symbol to inline.
        :param relative_path: the relative path to the file containing the symbol to inline.
        :param keep_definition: whether to keep the original method definition after inlining all call sites.
            May be ignored in some cases (e.g. when inlining a class).
        """
        relative_path = self._sanitize_input_param(relative_path)
        return self._api().inline_symbol(name_path, relative_path, keep_definition).represent()


class JetBrainsFindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Finds symbols that reference the given symbol using the JetBrains backend
    """

    symbol_dict_grouper = JetBrainsApi.references_grouper_

    def apply(
        self,
        name_path: str,
        relative_path: str,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds all symbols that reference the given symbol — its callers / usages / dependents, i.e. the
        symbols whose own definition (e.g. a method body) contains a reference to it. For each, returns its
        name path, file, and the surrounding line of code.

        :param name_path: name path of the symbol for which to find references
        :param relative_path: the relative path to the file containing the symbol (must be a file, not a directory)
            Note: for external dependencies, this must be an identifier starting with `<ext` that you have received
            earlier (don't try to guess!).
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        """
        relative_path = self._sanitize_input_param(relative_path)
        return self._api().find_referencing_symbols(name_path, relative_path, max_answer_chars).represent()


class JetBrainsGetSymbolsOverviewTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Retrieves an overview of the top-level symbols within a specified file using the JetBrains backend
    """

    symbol_dict_grouper = JetBrainsApi.overview_grouper_

    def apply(
        self,
        relative_path: str,
        depth: int = -1,
        max_answer_chars: int = -1,
        include_file_documentation: bool = False,
    ) -> str:
        """
        Gets an overview of the top-level symbols defined in the given file (classes, methods, fields) — its
        STRUCTURE, without their bodies. This is the cheap, structure-first way to learn what a file
        contains: it costs far less context than reading the whole file.

        :param relative_path: the relative path to the file to get the overview of
        :param depth: depth up to which descendants shall be retrieved.
            Default (-1) results in a language specific choice: 1 for java and kotlin and 0 for other languages
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :param include_file_documentation: whether to include the file's docstring. Default False.
        """
        relative_path = self._sanitize_input_param(relative_path)
        return self._api().get_symbols_overview(relative_path, depth, max_answer_chars, include_file_documentation).represent()


class JetBrainsTypeHierarchyTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Retrieves the type hierarchy (supertypes and/or subtypes) of a symbol using the JetBrains backend
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        hierarchy_type: Literal["super", "sub", "both"] = "both",
        depth: int | None = 1,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Gets the type hierarchy of a symbol (supertypes, subtypes, or both).

        :param name_path: name path of the symbol for which to get the type hierarchy.
        :param relative_path: the relative path to the file containing the symbol.
        :param hierarchy_type: which hierarchy to retrieve: "super" for parent classes/interfaces,
            "sub" for subclasses/implementations, or "both" for both directions. Default is "both".
        :param depth: depth limit for hierarchy traversal (None or 0 for unlimited). Default is 1.
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: Compact JSON with file-grouped hierarchy. Error string if not applicable.
        """
        relative_path = self._sanitize_input_param(relative_path)
        return self._api().get_type_hierarchy(name_path, relative_path, hierarchy_type, depth, max_answer_chars).represent()


class JetBrainsFindDeclarationTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Finds the declaration of a symbol using the JetBrains backend
    """

    def apply(self, relative_path: str, regex: str, include_body: bool = False) -> str:
        r"""
        Finds the declaration of a symbol.

        :param relative_path: the relative path to the source file containing the symbol for which to find the declaration.
        :param regex: a regular expression with one group, where the group matches the symbol for which to perform the lookup.
            For example, to find the declaration of the `process` method in a call like `obj.process()`,
            pass an expression like "obj\.(process)\(process_input_arg=37\)".
            Prefer regexes with sufficiently large context around the group to render the match unambiguous.
            Uses Python syntax with MULTILINE and DOTALL flags enabled.
        :param include_body: whether to include the symbol's body in the result. Default False.
        """
        relative_path = self._sanitize_input_param(relative_path)
        regex = self._sanitize_input_param(regex)
        return self._api().find_declaration(relative_path, regex, include_body).represent()


class JetBrainsFindImplementationsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Finds the implementations of a symbol using the JetBrains backend
    """

    def apply(self, relative_path: str, name_path: str) -> str:
        """
        Finds the implementations of a symbol.

        :param relative_path: the relative path to the source file containing the symbol for which to find implementations.
        :param name_path: name path of the symbol for which to find implementations
        """
        return self._api().find_implementations(relative_path, name_path).represent()


class JetBrainsRenameTool(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Renames a symbol, file or directory throughout the codebase using the JetBrains backend.
    """

    def apply(
        self,
        relative_path: str,
        new_name: str,
        name_path: str | None = None,
        rename_in_comments: bool = False,
        rename_in_text_occurrences: bool = False,
    ) -> str:
        """
        Renames a symbol, file or directory throughout the codebase.
        Note: renaming in comments/text is on a best-effort basis by the IDE; if the symbol name is non-unique, further
        verification is recommended.

        :param relative_path: if `name_path` is passed, the relative path of the file containing the symbol.
            Otherwise, the path to the directory or file to rename.
        :param new_name: the new name
        :param name_path: the name path of the symbol to rename or None if renaming a file or directory.
        :param rename_in_comments: whether to also rename occurrences in comments. Default True.
        :param rename_in_text_occurrences: whether to also rename occurrences in text. Default True.
        :return: a status message
        """
        return self._api().rename(relative_path, new_name, name_path, rename_in_comments, rename_in_text_occurrences).represent()


class JetBrainsDebugTool(Tool, ToolMarkerOptional, ToolMarkerBeta, JetBrainsApiMixin):
    """
    Provides debugging functionality (run configs, breakpoints, stepping, inspection, and evaluation)
    via a persistent debug REPL connected to the JetBrains IDE.
    """

    def apply(
        self,
        expression: str,
        repl_key: str = "default",
    ) -> str:
        """
        Debug code by evaluating Groovy/Java expressions in a persistent REPL attached to the IDE's
        debugger (run configs, breakpoints, stepping, inspection of live state).

        Use the `serena_info` tool with topic `jet_brains_debug_repl` for usage information.

        :param expression: a Groovy/Java expression/statement to evaluate in the REPL.
            If empty/null, closes the REPL with the given key.
        :param repl_key: identifier for the REPL instance. State persists across calls with the same key.
        :return: string representation of the result
        """
        return self._api().debug_eval(expression, repl_key)


class JetBrainsRunInspectionsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Runs JetBrains IDE inspections on a file and returns the results.
    """

    def apply(
        self,
        relative_path: str,
        min_severity: str | None = None,
        inspection_names: list[str] | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Runs IDE inspections (code analysis) on the given file and returns the problems found.
        This leverages the full power of JetBrains' static analysis engine, including language-specific
        inspections, type checking, potential bugs, code style issues, and more.

        :param relative_path: the relative path to the file to inspect.
        :param min_severity: minimum severity level to include in results (e.g. "ERROR", "WARNING", "WEAK_WARNING", "INFO").
            If not specified, all severities are returned.
        :param inspection_names: optional list of specific inspection names to run (e.g. ["UnusedImport", "TypeMismatch"]).
            If not specified, all applicable inspections are run.
        :param start_line: optional 1-based start line to restrict the inspection range.
        :param end_line: optional 1-based end line to restrict the inspection range.
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: JSON string with inspection results including severity, message, and location.
        """
        return (
            self._api().run_inspections(relative_path, min_severity, inspection_names, start_line, end_line, max_answer_chars).represent()
        )


class JetBrainsListInspectionsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional, JetBrainsApiMixin):
    """
    Lists available JetBrains IDE inspections, optionally filtered by language or group.
    """

    def apply(
        self,
        language: str | None = None,
        group_path_contains: str | None = None,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Lists the available IDE inspections. Use this to discover which inspections can be passed
        to the run_inspections tool's `inspection_names` parameter.

        :param language: optional language to filter by (e.g. "Java", "Python", "Kotlin").
        :param group_path_contains: optional substring to match against the inspection group path
            (e.g. "probable bugs", "code style").
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: JSON string with the list of available inspections including name, group path, and language.
        """
        return self._api().list_inspections(language, group_path_contains, max_answer_chars).represent()
