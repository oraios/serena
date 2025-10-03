import json

from serena.tools import Tool, ToolMarkerOptional, ToolMarkerSymbolicRead
from serena.tools.jetbrains_plugin_client import JetBrainsPluginClient


class JetBrainsFindSymbolTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Performs a global (or local) search for symbols with/containing a given name/substring (optionally filtered by type).
    """

    def apply(
        self,
        name_path: str,
        depth: int = 0,
        relative_path: str | None = None,
        include_body: bool = False,
        max_answer_chars: int = -1,
    ) -> str:
        """
        Retrieves information on all symbols/code entities (classes, methods, etc.) based on the given `name_path`,
        which represents a pattern for the symbol's path within the symbol tree of a single file.
        The returned symbol location can be used for edits or further queries.
        Specify `depth > 0` to retrieve children (e.g., methods of a class).

        The matching behavior is determined by the structure of `name_path`, which can
        either be a simple name (e.g. "method") or a name path like "class/method" (relative name path)
        or "/class/method" (absolute name path).
        Note that the name path is not a path in the file system but rather a path in the symbol tree
        **within a single file**. Thus, file or directory names should never be included in the `name_path`.
        For restricting the search to a single file or directory, pass the `relative_path` parameter.
        The retrieved symbols' `name_path` attribute will always be composed of symbol names, never file
        or directory names.

        Key aspects of the name path matching behavior:
        - The name of the retrieved symbols will match the last segment of `name_path`, while preceding segments
          will restrict the search to symbols that have a desired sequence of ancestors.
        - If there is no `/` in `name_path`, there is no restriction on the ancestor symbols.
          For example, passing `method` will match against all symbols with name paths like `method`,
          `class/method`, `class/nested_class/method`, etc.
        - If `name_path` contains at least one `/`, the matching is restricted to symbols
          with the respective ancestors. For example, passing `class/method` will match against
          `class/method` as well as `nested_class/class/method` but not `other_class/method`.
        - If `name_path` starts with a `/`, it will be treated as an absolute name path pattern, i.e.
          all ancestors are provided and must match.
          For example, passing `/class` will match only against top-level symbols named `class` but
          will not match `nested_class/class`. Passing `/class/method` will match `class/method` but
          not `outer_class/class/method`.

        :param name_path: The name path pattern to search for, see above for details.
        :param depth: Depth to retrieve descendants (e.g., 1 for class methods/attributes).
        :param relative_path: Optional. Restrict search to this file or directory.
            If None, searches entire codebase.
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
                name_path=name_path,
                relative_path=relative_path,
                depth=depth,
                include_body=include_body,
            )
            result = json.dumps(response_dict)
        return self._limit_length(result, max_answer_chars)


class JetBrainsFindReferencingSymbolsTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Finds symbols that reference the given symbol
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
    Retrieves an overview of the top-level symbols within a specified file
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
