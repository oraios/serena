import logging
from collections import defaultdict
from typing import Any, Literal

import serena.tools.jetbrains_types as jb
from serena.tools import Tool, ToolMarkerOptional, ToolMarkerSymbolicRead
from serena.tools.jetbrains_plugin_client import JetBrainsPluginClient

log = logging.getLogger(__name__)


class JetBrainsFindSymbolTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Performs a global (or local) search for symbols using the JetBrains backend
    """

    def apply(
        self,
        name_path_pattern: str,
        depth: int = 0,
        relative_path: str | None = None,
        include_body: bool = False,
        include_info: bool = False,
        search_deps: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given name path pattern.
        The returned symbol information can be used for edits or further queries.
        Specify `depth > 0` to retrieve children (e.g., methods of a class).

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
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the symbol (ignored if include_body is True).
            Default False; info is never included for child symbols and is not included when body is requested.
        :param search_deps: If True, also search in project dependencies (e.g., libraries).
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: JSON string: a list of symbols (with locations) matching the name.
        """
        if relative_path == ".":
            relative_path = None
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
            response_dict = client.find_symbol(
                name_path=name_path_pattern,
                relative_path=relative_path,
                depth=depth,
                include_body=include_body,
                include_documentation=include_documentation,
                include_quick_info=include_quick_info,
                search_deps=search_deps,
            )
            result = self._to_json(response_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsFindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds symbols that reference the given symbol using the JetBrains backend
    """

    # TODO: (maybe) - add content snippets showing the references like in LS based version?
    def apply(
        self,
        name_path: str,
        relative_path: str,
        include_info: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds symbols that reference the symbol at the given `name_path`.
        The result will contain metadata about the referencing symbols.

        :param name_path: name path of the symbol for which to find references; matching logic as described in find symbol tool.
        :param relative_path: the relative path to the file containing the symbol for which to find references.
            Note that here you can't pass a directory but must pass a file.
        :param include_info: whether to include info (hover-like, typically including docstring and signature)
            about the referencing symbols. Default False.
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned. -1 means the
            default value from the config will be used.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.find_references(
                name_path=name_path,
                relative_path=relative_path,
                include_quick_info=False,  # TODO: Hotfix for serena-jetbrains-plugin/issues/13; revert once fixed
            )
            result = self._to_json(response_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsGetSymbolsOverviewTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Retrieves an overview of the top-level symbols within a specified file using the JetBrains backend
    """

    USE_COMPACT_FORMAT = True

    @staticmethod
    def _transform_symbols_to_compact_format(symbols: list[jb.SymbolDTO]) -> dict[str, list]:
        """
        Transform symbol overview from verbose format to compact grouped format.

        Groups symbols by kind and uses names instead of full symbol objects.
        For symbols with children, creates nested dictionaries.

        The name_path can be inferred from the hierarchical structure:
        - Top-level symbols: name_path = name
        - Nested symbols: name_path = parent_name + "/" + name
        For example, "convert" under class "ProjectType" has name_path "ProjectType/convert".
        """
        result = defaultdict(list)

        for symbol in symbols:
            kind = symbol.get("type", "Unknown")
            name_path = symbol["name_path"]
            name = name_path.split("/")[-1]
            children = symbol.get("children", [])

            if children:
                # Symbol has children: create nested dict {name: children_dict}
                children_dict = JetBrainsGetSymbolsOverviewTool._transform_symbols_to_compact_format(children)
                result[kind].append({name: children_dict})
            else:
                # Symbol has no children: just add the name
                result[kind].append(name)  # type: ignore

        return result

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
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :param include_file_documentation: whether to include the file's docstring. Default False.
        :return: a JSON object containing the symbols grouped by kind in a compact format.
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            symbol_overview = client.get_symbols_overview(
                relative_path=relative_path, depth=depth, include_file_documentation=include_file_documentation
            )
        if self.USE_COMPACT_FORMAT:
            symbols = symbol_overview["symbols"]
            result: dict[str, Any] = {"symbols": self._transform_symbols_to_compact_format(symbols)}
            documentation = symbol_overview.pop("documentation", None)
            if documentation:
                result["docstring"] = documentation
            json_result = self._to_json(result)
        else:
            json_result = self._to_json(symbol_overview)
        return self._limit_length(json_result, max_answer_chars)


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
