import json

from serena.tools import Tool, ToolMarkerOptional, ToolMarkerSymbolicRead
from serena.tools.jetbrains_plugin_client import JetBrainsPluginClient


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
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: JSON string: a list of symbols (with locations) matching the name.
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.find_symbol(
                name_path=name_path_pattern,
                relative_path=relative_path,
                depth=depth,
                include_body=include_body,
            )
            result = json.dumps(response_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsFindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds symbols that reference the given symbol using the JetBrains backend
    """

    def apply(
        self,
        name_path: str,
        relative_path: str,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Finds symbols that reference the symbol at the given `name_path`.
        The result will contain metadata about the referencing symbols.

        :param name_path: name path of the symbol for which to find references; matching logic as described in find symbol tool.
        :param relative_path: the relative path to the file containing the symbol for which to find references.
            Note that here you can't pass a directory but must pass a file.
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned. -1 means the
            default value from the config will be used.
        :return: a list of JSON objects with the symbols referencing the requested symbol
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.find_references(
                name_path=name_path,
                relative_path=relative_path,
            )
            result = json.dumps(response_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsGetSymbolsOverviewTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Retrieves an overview of the top-level symbols within a specified file using the JetBrains backend
    """

    def apply(
        self,
        relative_path: str,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Gets an overview of the top-level symbols in the given file.
        Calling this is often a good idea before more targeted reading, searching or editing operations on the code symbols.
        Before requesting a symbol overview, it is usually a good idea to narrow down the scope of the overview
        by first understanding the basic directory structure of the repository that you can get from memories
        or by using the `list_dir` and `find_file` tools (or similar).

        :param relative_path: the relative path to the file to get the overview of
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: a JSON object containing the symbols
        """
        with JetBrainsPluginClient.from_project(self.project) as client:
            response_dict = client.get_symbols_overview(
                relative_path=relative_path,
            )
            result = json.dumps(response_dict)
        return self._limit_length(result, max_answer_chars)
