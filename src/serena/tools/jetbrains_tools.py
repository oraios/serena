import logging
from collections import Counter
from typing import Any, Literal

import serena.jetbrains.jetbrains_types as jb
from serena.code_editor import JetBrainsCodeEditor
from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClient
from serena.jetbrains.jetbrains_types import SymbolDTO, SymbolDTOUtil
from serena.symbol import JetBrainsSymbolDictGrouper
from serena.tools import Tool, ToolMarkerBeta, ToolMarkerOptional, ToolMarkerSymbolicEdit, ToolMarkerSymbolicRead
from serena.util.text_utils import find_text_coordinates

log = logging.getLogger(__name__)


class JetBrainsFindSymbolTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Performs a global (or local) search for symbols using the JetBrains backend
    """

    # groups top-level symbols only; children are grouped separately by _group_children_by_type
    symbol_dict_grouper = JetBrainsSymbolDictGrouper(
        ["relative_path", "type"], ["type"], collapse_singleton=True, map_name_path_to_name=True
    )

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
        Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given name path pattern.
        The returned symbol information can be used for edits or further queries.
        Specify `depth > 0` to retrieve children (e.g., methods of a class).
        Important: through `search_deps=True` dependencies can be searched, which
        should be preferred to web search or other less sophisticated approaches to analyzing dependencies.

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
        :param relative_path: Optional. Restrict search to this file or directory. If not specified, searches entire codebase.
            Note: for external dependencies, this must be an identifier starting with `<ext` that you have received
            earlier (don't try to guess!).
        :param include_body: If True, include the symbol's source code. Use judiciously.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the symbol.
            Default False; info is never included for child symbols or if include_body is True.
        :param search_deps: If True, also search in project dependencies (e.g., libraries).
        :param max_matches: Maximum number of permitted matches. If exceeded, a shortened result is returned
             which allows refining the search. -1 (default) means no limit. Set to 1 if you search for a single symbol.
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :return: symbols matching the name.
        """
        if include_body:
            depth = 0  # ignore user-specified depth if body is requested

        name_path_pattern = self._sanitize_input_param(name_path_pattern)

        if relative_path:
            relative_path = self._sanitize_input_param(relative_path)
        if relative_path == ".":
            relative_path = None

        if relative_path is not None and relative_path.startswith(jb.JB_EXTERNAL_FILE_PREFIX):
            search_deps = True

        with JetBrainsPluginClient.from_project(self.project) as client:
            if include_body:
                include_quick_info = False
                include_documentation = False
            else:
                if include_info:
                    include_documentation = True
                    include_quick_info = False
                else:
                    # If no additional information is requested, we still include the quick info (type signature)
                    include_documentation = False
                    include_quick_info = True
            symbol_collection_response = client.find_symbol(
                name_path=name_path_pattern,
                relative_path=relative_path,
                depth=depth,
                include_body=include_body,
                include_documentation=include_documentation,
                include_quick_info=include_quick_info,
                search_deps=search_deps,
            )
        symbols = symbol_collection_response["symbols"]

        def create_shortened_result() -> str:
            """Shortened results containing symbol types and identifiers (path + name_path) only, without children"""
            dicts: list[SymbolDTO] = [
                {"name_path": s["name_path"], "type": s["type"], "relative_path": s["relative_path"]} for s in symbols
            ]
            grouped = self.symbol_dict_grouper.group(dicts)
            return f"Names with paths:\n{self._to_json(grouped)}"

        n_matches = len(symbols)
        if 0 < max_matches < n_matches:
            return f"Matched {n_matches}>{max_matches=} symbols.\n" + create_shortened_result()

        grouped_symbols = self.symbol_dict_grouper.group(symbols)
        result = self._to_json(grouped_symbols)
        return self._limit_length(result, max_answer_chars, shortened_result_factories=[create_shortened_result])


class JetBrainsMoveTool(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, ToolMarkerBeta):
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
        name_path = name_path or None
        target_relative_path = target_relative_path or None
        target_parent_name_path = target_parent_name_path or None
        relative_path = self._sanitize_input_param(relative_path)
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.move(
                name_path=name_path,
                relative_path=relative_path,
                target_parent_name_path=target_parent_name_path,
                target_relative_path=target_relative_path,
            )
        return self._to_json(response_dict)


class JetBrainsSafeDeleteTool(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, ToolMarkerBeta):
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
        name_path = name_path or None
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.safe_delete(
                name_path=name_path,
                relative_path=relative_path,
                delete_even_if_used=delete_even_if_used,
                propagate=propagate,
            )
        return self._to_json(response_dict)


class JetBrainsInlineSymbol(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional, ToolMarkerBeta):
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
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.inline_symbol(
                name_path=name_path,
                relative_path=relative_path,
                keep_definition=keep_definition,
            )
        return self._to_json(response_dict)


class JetBrainsFindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds symbols that reference the given symbol using the JetBrains backend
    """

    symbol_dict_grouper = JetBrainsSymbolDictGrouper(["relative_path", "type"], ["type"], collapse_singleton=True)

    # TODO: (maybe) - add content snippets showing the references like in LS based version?
    def apply(
        self,
        name_path: str,
        relative_path: str,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds symbols that reference the symbol at the specified symbol, i.e. returns symbols whose definitions (e.g. a function body) contain a reference to the given symbol.
        The result will contain metadata about the referencing symbols.

        :param name_path: name path of the symbol for which to find references
        :param relative_path: the relative path to the file containing the symbol (must be a file, not a directory)
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        """
        relative_path = self._sanitize_input_param(relative_path)
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.find_references(
                name_path=name_path,
                relative_path=relative_path,
                include_quick_info=False,
            )
        symbol_dicts = response_dict["symbols"]

        # replace reference line number (if present) by actual line/context
        for symbol_dict in symbol_dicts:
            if "reference_line_no" in symbol_dict:
                ref_line = symbol_dict["reference_line_no"]
                ref_relative_path = symbol_dict["relative_path"]
                if not SymbolDTOUtil.is_external_symbol(symbol_dict) and ref_line is not None and ref_line >= 0:
                    content_around_ref = self.project.retrieve_content_around_line(
                        relative_file_path=ref_relative_path, line=ref_line, context_lines_before=1, context_lines_after=1
                    )
                    symbol_dict["context"] = content_around_ref.to_display_string()
                    del symbol_dict["reference_line_no"]

        # capture file paths before grouping
        ref_paths = [s.get("relative_path", "unknown") for s in symbol_dicts]

        result = self.symbol_dict_grouper.group(symbol_dicts)

        def create_shortened_result_counts_per_file() -> str:
            return f"Reference counts per file:\n{self._to_json(Counter(ref_paths))}"

        def create_shortened_result_num_results() -> str:
            return f"Found {len(ref_paths)} references."

        result_json = self._to_json(result)
        return self._limit_length(
            result_json,
            max_answer_chars,
            shortened_result_factories=[create_shortened_result_counts_per_file, create_shortened_result_num_results],
        )


class JetBrainsGetSymbolsOverviewTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Retrieves an overview of the top-level symbols within a specified file using the JetBrains backend
    """

    USE_COMPACT_FORMAT = True
    symbol_dict_grouper = JetBrainsSymbolDictGrouper(["type"], ["type"], collapse_singleton=True, map_name_path_to_name=True)

    def apply(
        self,
        relative_path: str,
        depth: int = 0,
        max_answer_chars: int = -1,
        include_file_documentation: bool = False,
    ) -> str:
        """
        Gets an overview of the top-level symbols in the given file.
        Calling this is often a good idea before more targeted reading, searching or editing operations on the code symbols.
        Before requesting a symbol overview, it is usually a good idea to narrow down the scope of the overview
        by first understanding the basic directory structure of the repository that you can get from memories
        or by using the `list_dir` and `find_file` tools (or similar).

        :param relative_path: the relative path to the file to get the overview of
        :param depth: depth up to which descendants shall be retrieved (e.g., use 1 to also retrieve immediate children).
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :param include_file_documentation: whether to include the file's docstring. Default False.
        """
        relative_path = self._sanitize_input_param(relative_path)
        with JetBrainsPluginClient.from_project(self.project) as client:
            symbol_overview = client.get_symbols_overview(
                relative_path=relative_path, depth=depth, include_file_documentation=include_file_documentation
            )

        if self.USE_COMPACT_FORMAT:
            symbols = symbol_overview["symbols"]

            grouped_symbols = self.symbol_dict_grouper.group(symbols)

            shortened_result_factories = []

            # create full result
            result: dict[str, Any] = {"symbols": grouped_symbols}
            documentation = symbol_overview.pop("documentation", None)
            if documentation:
                result["docstring"] = documentation
                shortened_result_factories.append(lambda: self._to_json(grouped_symbols))  # shortened result without docstring
            json_result = self._to_json(result)

            if depth > 0:

                def create_short_result_depth_0() -> str:
                    depth_0_symbols = [d.copy() for d in symbols]
                    for d in depth_0_symbols:
                        d.pop("children", None)
                    compact_depth_0_result = self.symbol_dict_grouper.group(depth_0_symbols)
                    return "Depth 0 overview:\n" + self._to_json(compact_depth_0_result)

                shortened_result_factories.append(create_short_result_depth_0)

            def create_short_result_type_counts() -> str:
                type_names = [d.get("type", "unknown") for d in symbols]
                return f"Symbol counts by type:\n{self._to_json(Counter(type_names))}"

            shortened_result_factories.append(create_short_result_type_counts)
        else:
            # this path is currently abandoned, consider introducing shortened results if ever needed
            shortened_result_factories = None
            json_result = self._to_json(symbol_overview)

        return self._limit_length(json_result, max_answer_chars, shortened_result_factories=shortened_result_factories)


class JetBrainsTypeHierarchyTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Retrieves the type hierarchy (supertypes and/or subtypes) of a symbol using the JetBrains backend
    """

    @staticmethod
    def _transform_hierarchy_nodes(nodes: list[jb.TypeHierarchyNodeDTO] | None) -> dict[str, list]:
        """
        Transform a list of TypeHierarchyNode into a file-grouped compact format.

        Returns a dict where keys are relative_paths and values are lists of either:
        - "SymbolNamePath" (leaf node)
        - {"SymbolNamePath": {nested_file_grouped_children}} (node with children)
        """
        if not nodes:
            return {}

        result: dict[str, list] = {}

        for node in nodes:
            symbol = node["symbol"]
            name_path = symbol["name_path"]
            rel_path = symbol["relative_path"]
            children = node.get("children", [])

            if rel_path not in result:
                result[rel_path] = []

            if children:
                # Node with children - recurse
                nested = JetBrainsTypeHierarchyTool._transform_hierarchy_nodes(children)
                result[rel_path].append({name_path: nested})
            else:
                # Leaf node
                result[rel_path].append(name_path)

        return result

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
            "sub" for subclasses/implementations, or "both" for both directions. Default is "sub".
        :param depth: depth limit for hierarchy traversal (None or 0 for unlimited). Default is 1.
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: Compact JSON with file-grouped hierarchy. Error string if not applicable.
        """
        relative_path = self._sanitize_input_param(relative_path)
        with JetBrainsPluginClient.from_project(self.project) as client:
            subtypes = None
            supertypes = None
            levels_not_included = {}

            if hierarchy_type in ("super", "both"):
                supertypes_response = client.get_supertypes(
                    name_path=name_path,
                    relative_path=relative_path,
                    depth=depth,
                )
                if "num_levels_not_included" in supertypes_response:
                    levels_not_included["supertypes"] = supertypes_response["num_levels_not_included"]
                supertypes = self._transform_hierarchy_nodes(supertypes_response.get("hierarchy"))

            if hierarchy_type in ("sub", "both"):
                subtypes_response = client.get_subtypes(
                    name_path=name_path,
                    relative_path=relative_path,
                    depth=depth,
                )
                if "num_levels_not_included" in subtypes_response:
                    levels_not_included["subtypes"] = subtypes_response["num_levels_not_included"]
                subtypes = self._transform_hierarchy_nodes(subtypes_response.get("hierarchy"))

            result_dict: dict[str, dict | list] = {}
            if supertypes is not None:
                result_dict["supertypes"] = supertypes
            if subtypes is not None:
                result_dict["subtypes"] = subtypes
            if levels_not_included:
                result_dict["levels_not_included"] = levels_not_included

            result = self._to_json(result_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsFindDeclarationTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
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

        editor = self.create_code_editor()
        content = editor.read_file(relative_path)
        coords = find_text_coordinates(content, regex, require_unique=True)
        assert coords is not None
        with JetBrainsPluginClient.from_project(self.project) as client:
            symbol_collection = client.find_declaration(
                relative_path=relative_path, line=coords.line, col=coords.col, include_quick_info=False, include_body=include_body
            )
        result = self._to_json(symbol_collection)
        return result


class JetBrainsFindImplementationsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds the implementations of a symbol using the JetBrains backend
    """

    def apply(self, relative_path: str, name_path: str) -> str:
        """
        Finds the implementations of a symbol.

        :param relative_path: the relative path to the source file containing the symbol for which to find implementations.
        :param name_path: name path of the symbol for which to find implementations
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            symbol_collection = client.find_implementations(
                relative_path=relative_path,
                name_path=name_path,
                include_quick_info=False,
            )
        result = self._to_json(symbol_collection)
        return result


class JetBrainsRenameTool(Tool, ToolMarkerSymbolicEdit, ToolMarkerOptional):
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
        code_editor = JetBrainsCodeEditor(self.project)
        result = code_editor.rename_symbol(
            name_path=name_path,
            relative_path=relative_path,
            new_name=new_name,
            rename_in_comments=rename_in_comments,
            rename_in_text_occurrences=rename_in_text_occurrences,
        )
        return self._to_json(result)


class JetBrainsDebugTool(Tool, ToolMarkerOptional, ToolMarkerBeta):
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
        Debug code interactively by evaluating Groovy expressions in a persistent REPL.
        Important: Debugging should only be applied if the user has requested it!

        Use the `serena_info` tool with topic `jet_brains_debug_repl` for usage information.

        :param expression: a Groovy/Java expression/statement to evaluate in the REPL.
            If empty/null, closes the REPL with the given key.
        :param repl_key: identifier for the REPL instance. State persists across calls with the same key.
        :return: string representation of the result
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            if expression:
                response = client.debug_eval(repl_key=repl_key, expression=expression)
            else:
                response = client.debug_close(repl_key=repl_key)
            return response.get("result", str(response))


class JetBrainsRunInspectionsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
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
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.run_inspections(
                relative_path=relative_path,
                min_severity=min_severity,
                inspection_names=inspection_names,
                start_line=start_line,
                end_line=end_line,
            )
        result = self._to_json(response_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsListInspectionsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
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
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.list_inspections(
                language=language,
                group_path_contains=group_path_contains,
            )
        result = self._to_json(response_dict)
        return self._limit_length(result, max_answer_chars)
