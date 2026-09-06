# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of JetBrains IDE-backed operations.
"""

from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

import serena.jetbrains.jetbrains_types as jb
from serena.code_editor import JetBrainsCodeEditor
from serena.jetbrains.jetbrains_plugin_client import JetBrainsPluginClient
from serena.jetbrains.jetbrains_types import SymbolDTO, SymbolDTOUtil
from serena.symbol import JetBrainsSymbolDictGrouper
from serena.util.text_utils import find_text_coordinates

from ..facade import FacadeApi, facade_method
from ..representable import JsonObject, JsonObjectRenderer, Renderer, RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class JetBrainsSymbolCollection(RepresentableViaRenderer):
    """
    A collection of symbols retrieved via the JetBrains backend.
    Each symbol is a dict with keys such as `name_path`, `relative_path` and `type`, and optionally
    `children`, `body`, `quick_info`, `documentation` and (for references) `context`.
    """

    def __init__(self, symbols: list[SymbolDTO], renderer: "JetBrainsSymbolCollectionRenderer"):
        """
        :param symbols: the symbols
        :param renderer: the renderer to use for representing the collection
        """
        super().__init__(renderer)
        self.symbols = symbols

    def __len__(self) -> int:
        return len(self.symbols)

    def relative_paths_(self) -> list[str]:
        return [s.get("relative_path", "unknown") for s in self.symbols]

    def identifiers_(self) -> list[SymbolDTO]:
        """
        :return: dicts containing only the identifying information (name_path, type, relative_path) of the symbols
        """
        return [{"name_path": s["name_path"], "type": s["type"], "relative_path": s["relative_path"]} for s in self.symbols]


class JetBrainsSymbolCollectionRenderer(Renderer[JetBrainsSymbolCollection]):
    """
    Renders a symbol collection as (optionally grouped) JSON, falling back to a listing of symbol identifiers
    if the length limit is exceeded.
    """

    def __init__(self, agent: "SerenaAgent", max_answer_chars: int, grouper: JetBrainsSymbolDictGrouper | None = None):
        super().__init__(agent, max_answer_chars)
        self._grouper = grouper

    def _group(self, symbols: list[SymbolDTO]) -> Any:
        return self._grouper.group(symbols) if self._grouper is not None else symbols

    def render_identifiers(self, obj: JetBrainsSymbolCollection) -> str:
        """
        :return: a shortened representation containing symbol types and identifiers (path + name_path) only, without children
        """
        return f"Names with paths:\n{self._to_json(self._group(obj.identifiers_()))}"

    def render(self, obj: JetBrainsSymbolCollection) -> str:
        result = self._to_json(self._group(obj.symbols))
        return self._limit_length(result, shortened_result_factories=[lambda: self.render_identifiers(obj)])


class JetBrainsReferencesRenderer(JetBrainsSymbolCollectionRenderer):
    """
    Renders a collection of referencing symbols, falling back to per-file counts and finally the total count
    if the length limit is exceeded.
    """

    def render(self, obj: JetBrainsSymbolCollection) -> str:
        ref_paths = obj.relative_paths_()
        result = self._to_json(self._group(obj.symbols))
        return self._limit_length(
            result,
            shortened_result_factories=[
                lambda: f"Reference counts per file:\n{self._to_json(Counter(ref_paths))}",
                lambda: f"Found {len(ref_paths)} references.",
            ],
        )


class JetBrainsSymbolsOverview(RepresentableViaRenderer):
    """
    The overview of the symbols defined in a file, i.e. the top-level symbols (each a dict with keys such as
    `name_path` and `type`, optionally with `children`) and, if requested, the file's documentation.
    """

    def __init__(self, symbols: list[SymbolDTO], documentation: str | None, renderer: "JetBrainsSymbolsOverviewRenderer"):
        """
        :param symbols: the top-level symbols
        :param documentation: the file's documentation, if requested and present
        :param renderer: the renderer to use for representing the overview
        """
        super().__init__(renderer)
        self.symbols = symbols
        self.documentation = documentation


class JetBrainsSymbolsOverviewRenderer(Renderer[JetBrainsSymbolsOverview]):
    """
    Renders an overview in the compact grouped format, dropping (in order) the documentation, the children
    and finally everything but symbol counts by type if the length limit is exceeded.
    """

    def __init__(self, agent: "SerenaAgent", max_answer_chars: int, grouper: JetBrainsSymbolDictGrouper, depth: int):
        super().__init__(agent, max_answer_chars)
        self._grouper = grouper
        self._depth = depth

    def render(self, obj: JetBrainsSymbolsOverview) -> str:
        grouped_symbols = self._grouper.group(obj.symbols)
        shortened_result_factories = []

        # create the full result
        result: dict[str, Any] = {"symbols": grouped_symbols}
        if obj.documentation:
            result["docstring"] = obj.documentation
            shortened_result_factories.append(lambda: self._to_json(grouped_symbols))  # shortened result without docstring
        json_result = self._to_json(result)

        # create shortened results
        if self._depth > 0:

            def create_short_result_depth_0() -> str:
                depth_0_symbols = [d.copy() for d in obj.symbols]
                for d in depth_0_symbols:
                    d.pop("children", None)
                return "Depth 0 overview:\n" + self._to_json(self._grouper.group(depth_0_symbols))

            shortened_result_factories.append(create_short_result_depth_0)

        def create_short_result_type_counts() -> str:
            type_names = [d.get("type", "unknown") for d in obj.symbols]
            return f"Symbol counts by type:\n{self._to_json(Counter(type_names))}"

        shortened_result_factories.append(create_short_result_type_counts)

        return self._limit_length(json_result, shortened_result_factories=shortened_result_factories)


class JetBrainsApi(FacadeApi):
    # groupers for the various symbol collections; top-level symbols are grouped by the first key list,
    # children by the second
    find_symbol_grouper_ = JetBrainsSymbolDictGrouper(
        ["relative_path", "type"], ["type"], collapse_singleton=True, map_name_path_to_name=True
    )
    references_grouper_ = JetBrainsSymbolDictGrouper(["relative_path", "type"], ["type"], collapse_singleton=True)
    overview_grouper_ = JetBrainsSymbolDictGrouper(["type"], ["type"], collapse_singleton=True, map_name_path_to_name=True)

    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(
            agent,
            name="jb",
            description="JetBrains IDE-backed operations (symbol search, references, type hierarchies, refactorings, "
            "inspections, debugging)",
        )

    @contextmanager
    def _client(self) -> Iterator[JetBrainsPluginClient]:
        with JetBrainsPluginClient.from_project(self._get_project()) as client:
            yield client

    def _json_object(self, data: Any, max_answer_chars: int = -1) -> JsonObject:
        return JsonObject(data, JsonObjectRenderer(self._agent, max_answer_chars))

    # read operations

    @facade_method()
    def find_symbol(
        self,
        name_path_pattern: str,
        depth: int = 0,
        relative_path: str | None = None,
        include_body: bool = False,
        include_info: bool = False,
        search_deps: bool = False,
        max_matches: int = -1,
        max_answer_chars: int = -1,
    ) -> JetBrainsSymbolCollection:
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
        A pattern must not contain only wildcards (e.g. "*" or "/*"); use `get_symbols_overview` to list a file's symbols.

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
        :param max_matches: Maximum number of permitted matches. If exceeded, an error containing a shortened result is raised,
             which allows refining the search. -1 (default) means no limit. Set to 1 if you search for a single symbol.
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :return: the symbols matching the pattern
        """
        if name_path_pattern.replace("*", "").replace("/", "") == "":
            raise ValueError("name_path_pattern must not be empty or contain only wildcards; consider using get_symbols_overview")

        if include_body:
            depth = 0  # ignore user-specified depth if body is requested
        if relative_path == ".":
            relative_path = None
        if relative_path is not None and relative_path.startswith(jb.JB_EXTERNAL_FILE_PREFIX):
            search_deps = True

        # determine which additional information to request: if no additional information is requested,
        # we still include the quick info (type signature)
        include_documentation = include_info and not include_body
        include_quick_info = not include_info and not include_body

        with self._client() as client:
            response = client.find_symbol(
                name_path=name_path_pattern,
                relative_path=relative_path,
                depth=depth,
                include_body=include_body,
                include_documentation=include_documentation,
                include_quick_info=include_quick_info,
                search_deps=search_deps,
            )
        renderer = JetBrainsSymbolCollectionRenderer(self._agent, max_answer_chars, grouper=self.find_symbol_grouper_)
        collection = JetBrainsSymbolCollection(response["symbols"], renderer)

        n_matches = len(collection)
        if 0 < max_matches < n_matches:
            raise ValueError(f"Matched {n_matches}>{max_matches=} symbols.\n" + renderer.render_identifiers(collection))
        return collection

    @facade_method()
    def find_referencing_symbols(self, name_path: str, relative_path: str, max_answer_chars: int = -1) -> JetBrainsSymbolCollection:
        """
        Finds all symbols that reference the given symbol — its callers / usages / dependents, i.e. the
        symbols whose own definition (e.g. a method body) contains a reference to it. For each, returns its
        name path, file, and the surrounding line of code.

        :param name_path: name path of the symbol for which to find references
        :param relative_path: the relative path to the file containing the symbol (must be a file, not a directory)
            Note: for external dependencies, this must be an identifier starting with `<ext` that you have received
            earlier (don't try to guess!).
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :return: the referencing symbols
        """
        with self._client() as client:
            response = client.find_references(name_path=name_path, relative_path=relative_path, include_quick_info=False)
        symbol_dicts = response["symbols"]

        # replace reference line number (if present) by actual line/context
        project = self._get_project()
        for symbol_dict in symbol_dicts:
            if "reference_line_no" in symbol_dict:
                ref_line = symbol_dict["reference_line_no"]
                if not SymbolDTOUtil.is_external_symbol(symbol_dict) and ref_line is not None and ref_line >= 0:
                    content_around_ref = project.retrieve_content_around_line(
                        relative_file_path=symbol_dict["relative_path"], line=ref_line, context_lines_before=1, context_lines_after=1
                    )
                    symbol_dict["context"] = content_around_ref.to_display_string()
                    del symbol_dict["reference_line_no"]

        renderer = JetBrainsReferencesRenderer(self._agent, max_answer_chars, grouper=self.references_grouper_)
        return JetBrainsSymbolCollection(symbol_dicts, renderer)

    @facade_method()
    def get_symbols_overview(
        self, relative_path: str, depth: int = -1, max_answer_chars: int = -1, include_file_documentation: bool = False
    ) -> JetBrainsSymbolsOverview:
        """
        Gets an overview of the top-level symbols defined in the given file (classes, methods, fields) — its
        STRUCTURE, without their bodies. This is the cheap, structure-first way to learn what a file
        contains: it costs far less context than reading the whole file.

        :param relative_path: the relative path to the file to get the overview of
        :param depth: depth up to which descendants shall be retrieved.
            Default (-1) results in a language specific choice: 1 for java and kotlin and 0 for other languages
        :param max_answer_chars: max characters for the result (-1 for default). If exceeded, no content/a shortened result is returned.
        :param include_file_documentation: whether to include the file's docstring. Default False.
        :return: the overview
        """
        if depth == -1:
            depth = 1 if relative_path.endswith((".java", ".kt")) else 0

        with self._client() as client:
            response = client.get_symbols_overview(
                relative_path=relative_path, depth=depth, include_file_documentation=include_file_documentation
            )
        renderer = JetBrainsSymbolsOverviewRenderer(self._agent, max_answer_chars, grouper=self.overview_grouper_, depth=depth)
        return JetBrainsSymbolsOverview(response["symbols"], response.get("documentation"), renderer)

    @staticmethod
    def _transform_hierarchy_nodes(nodes: list[jb.TypeHierarchyNodeDTO] | None) -> dict[str, list]:
        """
        Transforms a list of hierarchy nodes into a file-grouped compact format.

        :return: a dict where keys are relative paths and values are lists of either a name path (for a leaf node)
            or a dict mapping the name path to the (recursively transformed) children
        """
        result: defaultdict[str, list] = defaultdict(list)
        for node in nodes or []:
            symbol = node["symbol"]
            name_path = symbol["name_path"]
            rel_path = symbol["relative_path"]
            children = node.get("children", [])
            if children:
                result[rel_path].append({name_path: JetBrainsApi._transform_hierarchy_nodes(children)})
            else:
                result[rel_path].append(name_path)
        return dict(result)

    @facade_method()
    def get_type_hierarchy(
        self,
        name_path: str,
        relative_path: str,
        hierarchy_type: Literal["super", "sub", "both"] = "both",
        depth: int | None = 1,
        max_answer_chars: int = -1,
    ) -> JsonObject:
        """
        Gets the type hierarchy of a symbol (supertypes, subtypes, or both).

        :param name_path: name path of the symbol for which to get the type hierarchy.
        :param relative_path: the relative path to the file containing the symbol.
        :param hierarchy_type: which hierarchy to retrieve: "super" for parent classes/interfaces,
            "sub" for subclasses/implementations, or "both" for both directions. Default is "both".
        :param depth: depth limit for hierarchy traversal (None or 0 for unlimited). Default is 1.
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: the file-grouped hierarchy, with keys "supertypes" and/or "subtypes" (and "levels_not_included"
            if the depth limit truncated the hierarchy)
        """
        result: dict[str, dict | list] = {}
        levels_not_included = {}
        with self._client() as client:
            if hierarchy_type in ("super", "both"):
                response = client.get_supertypes(name_path=name_path, relative_path=relative_path, depth=depth)
                if "num_levels_not_included" in response:
                    levels_not_included["supertypes"] = response["num_levels_not_included"]
                result["supertypes"] = self._transform_hierarchy_nodes(response.get("hierarchy"))
            if hierarchy_type in ("sub", "both"):
                response = client.get_subtypes(name_path=name_path, relative_path=relative_path, depth=depth)
                if "num_levels_not_included" in response:
                    levels_not_included["subtypes"] = response["num_levels_not_included"]
                result["subtypes"] = self._transform_hierarchy_nodes(response.get("hierarchy"))
        if levels_not_included:
            result["levels_not_included"] = levels_not_included
        return self._json_object(result, max_answer_chars)

    @facade_method()
    def find_declaration(self, relative_path: str, regex: str, include_body: bool = False) -> JetBrainsSymbolCollection:
        r"""
        Finds the declaration of a symbol.

        :param relative_path: the relative path to the source file containing the symbol for which to find the declaration.
        :param regex: a regular expression with one group, where the group matches the symbol for which to perform the lookup.
            For example, to find the declaration of the `process` method in a call like `obj.process()`,
            pass an expression like "obj\.(process)\(process_input_arg=37\)".
            Prefer regexes with sufficiently large context around the group to render the match unambiguous.
            Uses Python syntax with MULTILINE and DOTALL flags enabled.
        :param include_body: whether to include the symbol's body in the result. Default False.
        :return: the declaring symbol(s)
        """
        content = self._get_project().read_file(relative_path)
        coords = find_text_coordinates(content, regex, require_unique=True)
        assert coords is not None
        with self._client() as client:
            response = client.find_declaration(
                relative_path=relative_path, line=coords.line, col=coords.col, include_quick_info=False, include_body=include_body
            )
        return JetBrainsSymbolCollection(response["symbols"], JetBrainsSymbolCollectionRenderer(self._agent, -1))

    @facade_method()
    def find_implementations(self, relative_path: str, name_path: str) -> JetBrainsSymbolCollection:
        """
        Finds the implementations of a symbol.

        :param relative_path: the relative path to the source file containing the symbol for which to find implementations.
        :param name_path: name path of the symbol for which to find implementations
        :return: the implementing symbols
        """
        with self._client() as client:
            response = client.find_implementations(relative_path=relative_path, name_path=name_path, include_quick_info=False)
        return JetBrainsSymbolCollection(response["symbols"], JetBrainsSymbolCollectionRenderer(self._agent, -1))

    # edit operations

    @facade_method(can_edit=True)
    def rename(
        self,
        relative_path: str,
        new_name: str,
        name_path: str | None = None,
        rename_in_comments: bool = False,
        rename_in_text_occurrences: bool = False,
    ) -> JsonObject:
        """
        Renames a symbol, file or directory throughout the codebase.
        Note: renaming in comments/text is on a best-effort basis by the IDE; if the symbol name is non-unique, further
        verification is recommended.

        :param relative_path: if `name_path` is passed, the relative path of the file containing the symbol.
            Otherwise, the path to the directory or file to rename.
        :param new_name: the new name
        :param name_path: the name path of the symbol to rename or None if renaming a file or directory.
        :param rename_in_comments: whether to also rename occurrences in comments. Default False.
        :param rename_in_text_occurrences: whether to also rename occurrences in text. Default False.
        :return: the result of the operation
        """
        result = JetBrainsCodeEditor(self._get_project()).rename_symbol(
            name_path=name_path,
            relative_path=relative_path,
            new_name=new_name,
            rename_in_comments=rename_in_comments,
            rename_in_text_occurrences=rename_in_text_occurrences,
        )
        return self._json_object(result)

    @facade_method(beta=True, can_edit=True)
    def move(
        self,
        relative_path: str,
        name_path: str | None = None,
        target_relative_path: str | None = None,
        target_parent_name_path: str | None = None,
    ) -> JsonObject:
        """
        Moves a symbol, file or directory to a different location and automatically updates all references to affected symbols.
        **Important**: this should always be preferred to naive moving (e.g. via file system operations or edits)
        as it is much more reliable and efficient. It is always safe to use. For some symbols, moving may not be applicable,
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
        :return: the result of the operation
        """
        with self._client() as client:
            result = client.move(
                name_path=name_path or None,
                relative_path=relative_path,
                target_parent_name_path=target_parent_name_path or None,
                target_relative_path=target_relative_path or None,
            )
        return self._json_object(result)

    @facade_method(beta=True, can_edit=True)
    def safe_delete(
        self, relative_path: str, name_path: str | None = None, delete_even_if_used: bool = False, propagate: bool = False
    ) -> JsonObject:
        """
        Safely deletes a symbol, file, or directory, checking for usages first and propagating deletion, if desired.
        Propagation means it is possible to request deleting of usages and cleaning up of unused code.
        Propagation is powerful for cleaning up code but should be used with care.
        **Important**: this should always be preferred to naive deleting (e.g. via file system operations or edits).
        When using it, you don't have to search for usages first, as the operation will do it for you.

        :param relative_path: the relative path to the file containing the symbol to delete.
        :param name_path: the name path of the symbol to delete.
            A name path identifies a symbol within a source file, e.g. "MyClass/my_method".
            Omit for deleting a file or directory.
        :param delete_even_if_used: whether to force deletion even if the symbol still has usages.
            Default is False (safe mode: will report usages instead of deleting).
        :param propagate: whether to propagate the deletion to usages of the symbol and also
            remove symbols that become unused after the deletion. Default is False.
        :return: the result of the operation
        """
        with self._client() as client:
            result = client.safe_delete(
                name_path=name_path or None, relative_path=relative_path, delete_even_if_used=delete_even_if_used, propagate=propagate
            )
        return self._json_object(result)

    @facade_method(beta=True, can_edit=True)
    def inline_symbol(self, name_path: str, relative_path: str, keep_definition: bool = False) -> JsonObject:
        """
        Inlines a symbol (usually a method/function, but also classes may be amenable to inlining,
        which turns invocation into anonymous class creation),
        replacing all call sites with the symbol's body.
        **Important**: this should always be preferred to naive inlining (e.g. via searching for references and
        editing them).

        :param name_path: the name path of the symbol to inline.
        :param relative_path: the relative path to the file containing the symbol to inline.
        :param keep_definition: whether to keep the original method definition after inlining all call sites.
            May be ignored in some cases (e.g. when inlining a class).
        :return: the result of the operation
        """
        with self._client() as client:
            result = client.inline_symbol(name_path=name_path, relative_path=relative_path, keep_definition=keep_definition)
        return self._json_object(result)

    # inspections

    @facade_method()
    def run_inspections(
        self,
        relative_path: str,
        min_severity: str | None = None,
        inspection_names: list[str] | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        max_answer_chars: int = -1,
    ) -> JsonObject:
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
        :return: the inspection results including severity, message, and location.
        """
        with self._client() as client:
            result = client.run_inspections(
                relative_path=relative_path,
                min_severity=min_severity,
                inspection_names=inspection_names,
                start_line=start_line,
                end_line=end_line,
            )
        return self._json_object(result, max_answer_chars)

    @facade_method()
    def list_inspections(
        self, language: str | None = None, group_path_contains: str | None = None, max_answer_chars: int = -1
    ) -> JsonObject:
        """
        Lists the available IDE inspections. Use this to discover which inspections can be passed
        to `run_inspections` via `inspection_names`.

        :param language: optional language to filter by (e.g. "Java", "Python", "Kotlin").
        :param group_path_contains: optional substring to match against the inspection group path
            (e.g. "probable bugs", "code style").
        :param max_answer_chars: max characters for the JSON result. If exceeded, no content is returned.
            -1 means the default value from the config will be used.
        :return: the list of available inspections including name, group path, and language.
        """
        with self._client() as client:
            result = client.list_inspections(language=language, group_path_contains=group_path_contains)
        return self._json_object(result, max_answer_chars)

    # debugging

    @facade_method(beta=True)
    def debug_eval_info(self) -> str:
        """
        Provides usage information for the debug REPL (method `debug_eval`)

        :return: the usage information
        """
        return self._agent.prompt_factory.create_info_jet_brains_debug_repl()

    @facade_method(beta=True)
    def debug_eval(self, expression: str, repl_key: str = "default") -> str:
        """
        Provides debugging functionality (run configs, breakpoints, stepping, inspection, and evaluation)
        via a persistent debug REPL connected to the JetBrains IDE.

        Call `debug_eval_info()` first for usage information.

        :param expression: a Groovy/Java expression/statement to evaluate in the REPL.
            If empty, closes the REPL with the given key.
        :param repl_key: identifier for the REPL instance. State persists across calls with the same key.
        :return: the string representation of the result
        """
        with self._client() as client:
            if expression:
                response = client.debug_eval(repl_key=repl_key, expression=expression)
            else:
                response = client.debug_close(repl_key=repl_key)
        return response.get("result", str(response))
