# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of language server (LSP)-backed operations.
"""

import os
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from serena.code_editor import LanguageServerCodeEditor
from serena.lsp.lsp_diagnostics import GroupedDiagnostics
from serena.symbol import (
    LanguageServerSymbol,
    LanguageServerSymbolDictGrouper,
    LanguageServerSymbolRetriever,
    ReferenceInLanguageServerSymbol,
    SymbolDictGrouper,
)
from serena.tools import (
    FindDeclarationTool,
    FindImplementationsTool,
    FindReferencingSymbolsTool,
    FindSymbolTool,
    FindTypeHierarchyTool,
    GetDiagnosticsForFileTool,
    GetDiagnosticsForSymbolTool,
    GetSymbolsOverviewTool,
    RenameSymbolTool,
    RestartLanguageServerTool,
    SafeDeleteSymbol,
)
from serena.util.text_utils import TextOutputUtils, find_text_coordinates
from solidlsp.lsp_protocol_handler.lsp_types import SymbolKind

from ..facade import SUCCESS_RESULT, FacadeApi, ReferencedType, facade_method
from ..representable import Renderer, RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class LspSymbolCollection(RepresentableViaRenderer):
    """
    A collection of symbols (`LanguageServerSymbol`) retrieved via the language server.
    """

    symbols: list[LanguageServerSymbol]

    def __init__(
        self,
        symbols: list[LanguageServerSymbol],
        renderer: "LspSymbolCollectionRenderer",
        info_by_symbol: dict[LanguageServerSymbol, str] | None = None,
    ):
        """
        :param symbols: the list of symbols
        :param renderer: the renderer to use for representing the collection
        :param info_by_symbol: additional (hover-like) info per symbol, if requested
        """
        super().__init__(renderer)
        self.symbols = symbols
        self.info_by_symbol_ = info_by_symbol or {}

    def __len__(self) -> int:
        return len(self.symbols)

    def relative_path_to_name_paths_(self) -> dict[str, list[str]]:
        result: defaultdict[str, list[str]] = defaultdict(list)
        for s in self.symbols:
            result[s.location.relative_path or "unknown"].append(s.get_name_path())
        return result


class LspSymbol(RepresentableViaRenderer):
    """
    A single symbol retrieved via the language server (see `LspSymbolCollection` for the symbol's interface).
    """

    symbol: LanguageServerSymbol

    def __init__(self, symbol: LanguageServerSymbol, renderer: "LspSymbolRenderer", info: str | None = None):
        """
        :param symbol: the symbol
        :param renderer: the renderer to use for representing the symbol
        :param info: additional (hover-like) info on the symbol, if requested
        """
        super().__init__(renderer)
        self.symbol = symbol
        self.info_ = info


@dataclass(kw_only=True)
class SymbolOutputParams:
    name_path: bool = True
    name: bool = False
    kind: bool = False
    location: bool = False
    depth: int = 0
    body_location: bool = False
    children_body: bool = False
    children_name: bool | None = None
    children_name_path: bool | None = None
    relative_path: bool = False
    include_body: bool = False
    include_info: bool = False
    child_inclusion_predicate: Callable[[LanguageServerSymbol], bool] | None = None


class LspSymbolCollectionRenderer(Renderer[LspSymbolCollection]):
    """
    Renders a symbol collection as (optionally grouped) JSON according to the output parameters, falling back
    to a mapping from files to name paths if the length limit is exceeded.
    """

    def __init__(
        self,
        agent: "SerenaAgent",
        max_answer_chars: int,
        output_params: SymbolOutputParams,
        grouper: SymbolDictGrouper | None = None,
    ):
        super().__init__(agent, max_answer_chars)
        self._output_params = output_params
        self._grouper = grouper

    def symbol_dicts_(
        self, symbols: list[LanguageServerSymbol], info_by_symbol: dict[LanguageServerSymbol, str]
    ) -> list[LanguageServerSymbol.OutputDict]:
        """
        :param symbols: the symbols to convert
        :param info_by_symbol: additional info to include per symbol, if any
        :return: the dict representations of the symbols according to the output parameters (including the info)
        """
        p = self._output_params
        symbol_dicts = [
            s.to_dict(
                kind=p.kind,
                name_path=p.name_path,
                name=p.name,
                location=p.location,
                relative_path=p.relative_path,
                body_location=p.body_location,
                depth=p.depth,
                body=p.include_body,
                children_body=p.children_body,
                children_name=p.children_name,
                children_name_path=p.children_name_path,
                child_inclusion_predicate=p.child_inclusion_predicate,
            )
            for s in symbols
        ]
        for s, s_dict in zip(symbols, symbol_dicts, strict=True):
            if symbol_info := info_by_symbol.get(s):
                # In python 3.15 we could specify extra_items=True in the TypedDict definition,
                # https://peps.python.org/pep-0728/
                # If we ever upgrade to 3.15, we can remove the type: ignore[typeddict-unknown-key]
                s_dict["info"] = symbol_info
        return symbol_dicts

    def _group(self, symbol_dicts: list[LanguageServerSymbol.OutputDict]) -> Any:
        return self._grouper.group(symbol_dicts) if self._grouper is not None else symbol_dicts

    def render(self, obj: LspSymbolCollection) -> str:
        def create_short_result_relative_path_to_name_paths() -> str:
            return f"Shortened result:\n{TextOutputUtils.to_json(obj.relative_path_to_name_paths_())}"

        result = self._to_json(self._group(self.symbol_dicts_(obj.symbols, obj.info_by_symbol_)))
        return self._limit_length(result, shortened_result_factories=[create_short_result_relative_path_to_name_paths])


class LspSymbolRenderer(Renderer[LspSymbol]):
    """
    Renders a single symbol as JSON, using a collection renderer for the conversion.
    """

    def __init__(self, agent: "SerenaAgent", max_answer_chars: int, collection_renderer: LspSymbolCollectionRenderer):
        super().__init__(agent, max_answer_chars)
        self._collection_renderer = collection_renderer

    def render(self, obj: LspSymbol) -> str:
        info_by_symbol = {obj.symbol: obj.info_} if obj.info_ else {}
        symbol_dict = self._collection_renderer.symbol_dicts_([obj.symbol], info_by_symbol)[0]
        return self._limit_length(self._to_json(symbol_dict))


class LspSymbolsOverviewRenderer(LspSymbolCollectionRenderer):
    """
    Renders a file's symbol overview, falling back to a depth-0 overview and finally symbol counts by kind
    if the length limit is exceeded.
    """

    def render(self, obj: LspSymbolCollection) -> str:
        symbol_dicts = self.symbol_dicts_(obj.symbols, obj.info_by_symbol_)
        result = self._to_json(self._group(symbol_dicts))

        def make_kind_counts() -> str:
            kind_names = [d.get("kind", "unknown") for d in symbol_dicts]
            return f"Symbol counts by kind:\n{self._to_json(Counter(kind_names))}"

        shortened_results: list[Callable[[], str]] = [make_kind_counts]
        if self._output_params.depth > 0:

            def make_depth_0_result() -> str:
                depth_0_dicts = [d.copy() for d in symbol_dicts]
                for d in depth_0_dicts:
                    d.pop("children", None)
                return "Depth 0 overview:\n" + self._to_json(self._group(depth_0_dicts))

            shortened_results.insert(0, make_depth_0_result)

        return self._limit_length(result, shortened_result_factories=shortened_results)


class LspReferenceCollection(RepresentableViaRenderer):
    """
    The references to a symbol (`ReferenceInLanguageServerSymbol`).
    """

    references: list[ReferenceInLanguageServerSymbol]

    def __init__(
        self,
        references: list[ReferenceInLanguageServerSymbol],
        contents_around_references: list[str],
        renderer: "LspReferenceCollectionRenderer",
    ):
        """
        :param references: the references
        :param contents_around_references: for each reference, the code around it (for display)
        :param renderer: the renderer to use for representing the collection
        """
        super().__init__(renderer)
        self.references = references
        self.contents_around_references_ = contents_around_references

    def __len__(self) -> int:
        return len(self.references)


class LspReferenceCollectionRenderer(Renderer[LspReferenceCollection]):
    """
    Renders references as grouped JSON including the code around each reference, falling back to
    references without code, per-file counts and finally the total count if the length limit is exceeded.
    """

    def __init__(self, agent: "SerenaAgent", max_answer_chars: int, grouper: SymbolDictGrouper):
        super().__init__(agent, max_answer_chars)
        self._grouper = grouper

    def render(self, obj: LspReferenceCollection) -> str:
        reference_dicts = []
        ref_summaries = []
        for ref, content_around_ref in zip(obj.references, obj.contents_around_references_, strict=True):
            ref_dict = dict(ref.symbol.to_dict(kind=True, relative_path=True, depth=0, body=False, body_location=True))
            ref_dict["content_around_reference"] = content_around_ref
            reference_dicts.append(ref_dict)
            ref_summaries.append(
                {
                    "name_path": ref_dict.get("name_path"),
                    "kind": ref_dict.get("kind"),
                    "relative_path": ref_dict.get("relative_path"),
                    "reference_line": ref.line,
                }
            )

        result = self._to_json(self._grouper.group(reference_dicts))

        # shortened result closures, from least to most aggressive shortening
        def make_refs_without_context() -> str:
            return f"References without surrounding lines:\n{self._to_json(self._grouper.group([dict(s) for s in ref_summaries]))}"

        def make_per_file_counts() -> str:
            counts = Counter(str(r["relative_path"]) for r in ref_summaries)
            return f"Reference counts per file:\n{self._to_json(counts)}"

        def make_summary() -> str:
            return f"Found {len(ref_summaries)} references."

        return self._limit_length(result, shortened_result_factories=[make_refs_without_context, make_per_file_counts, make_summary])


class LspDiagnostics(RepresentableViaRenderer):
    """
    Diagnostics grouped as `relative_path -> severity -> name_path -> diagnostics`; see `grouped.get_dict()`.
    """

    grouped: GroupedDiagnostics

    def __init__(self, grouped: GroupedDiagnostics, renderer: "LspDiagnosticsRenderer"):
        """
        :param grouped: the grouped diagnostics
        :param renderer: the renderer to use for representing the diagnostics
        """
        super().__init__(renderer)
        self.grouped = grouped


class LspDiagnosticsRenderer(Renderer[LspDiagnostics]):
    def render(self, obj: LspDiagnostics) -> str:
        return self._limit_length(self._to_json(obj.grouped.get_dict()))


def _is_not_low_level(symbol: LanguageServerSymbol) -> bool:
    return not symbol.is_low_level()


class LspApi(FacadeApi):
    FILE_LEVEL_DIAGNOSTIC_BUCKET = "<file>"
    """the name path under which diagnostics that cannot be mapped to a symbol are grouped"""

    # groupers for the various symbol collections; top-level symbols are grouped by the first key list,
    # children by the second.
    # For find_symbol, we group children by kind, keeping just the name (the parent's name_path makes it unambiguous);
    # we don't group the top-level result list because many tests rely on it being a flat list of symbol dicts
    find_symbol_dict_grouper_ = LanguageServerSymbolDictGrouper([], ["kind"], collapse_singleton=True)
    references_grouper_ = LanguageServerSymbolDictGrouper(["relative_path", "kind"], ["kind"], collapse_singleton=True)
    overview_grouper_ = LanguageServerSymbolDictGrouper(["kind"], ["kind"], collapse_singleton=True)

    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(
            agent,
            name="lsp",
            description="symbol-level operations on the codebase backed by language servers",
            types=[
                ReferencedType(
                    LanguageServerSymbol,
                    members=[
                        "name",
                        "get_name_path",
                        "relative_path",
                        "symbol_kind_name",
                        "line",
                        "column",
                        "body",
                        "get_body_line_numbers",
                        "iter_children",
                        "iter_ancestors",
                        "get_parent",
                    ],
                ),
            ],
        )

    def _create_symbol_retriever(self) -> LanguageServerSymbolRetriever:
        assert self._agent.get_language_backend().is_lsp(), "Language server operations require the language server backend"
        return LanguageServerSymbolRetriever(self._get_project())

    def _create_ls_code_editor(self, symbol_retriever: LanguageServerSymbolRetriever | None = None) -> LanguageServerCodeEditor:
        return LanguageServerCodeEditor(symbol_retriever or self._create_symbol_retriever())

    @staticmethod
    def _request_info(
        symbol_retriever: LanguageServerSymbolRetriever, symbols: list[LanguageServerSymbol], output_params: SymbolOutputParams
    ) -> dict[LanguageServerSymbol, str]:
        """
        :return: additional (hover-like) info per symbol, if the output parameters request it (and not the body, which
            supersedes it); requested eagerly, such that results are self-contained
        """
        if output_params.include_info and not output_params.include_body:
            return {s: info for s, info in symbol_retriever.request_info_for_symbol_batch(symbols).items() if info}
        return {}

    def _retrieve_content_around_reference(self, reference: ReferenceInLanguageServerSymbol) -> str:
        relative_path = reference.symbol.location.relative_path
        assert relative_path is not None, f"Referencing symbol {reference.symbol.name} has no relative path, this is likely a bug."
        content = self._get_project().retrieve_content_around_line(
            relative_file_path=relative_path, line=reference.line, context_lines_before=1, context_lines_after=1
        )
        return content.to_display_string()

    @staticmethod
    def _parse_kinds(kinds: Sequence[int]) -> Sequence[SymbolKind] | None:
        return [SymbolKind(k) for k in kinds] if kinds else None

    def _create_diagnostics(self, grouped: GroupedDiagnostics, max_answer_chars: int) -> LspDiagnostics:
        return LspDiagnostics(grouped, LspDiagnosticsRenderer(self._agent, max_answer_chars))

    # language server management

    @facade_method(uses_project_server=True, optional=True, corresponding_tool=RestartLanguageServerTool)
    def restart_language_server(self) -> str:
        """
        Restarts the language server(s).

        Use this only on explicit user request or after confirmation; it may be necessary if a language server hangs.

        :return: a success message
        """
        self._agent.reset_language_server_manager()
        return SUCCESS_RESULT

    # read operations

    @facade_method(uses_project_server=True, corresponding_tool=GetSymbolsOverviewTool)
    def get_symbols_overview(self, relative_path: str, depth: int = -1, max_answer_chars: int = -1) -> LspSymbolCollection:
        """
        Gets an overview of the symbols defined in the given file (classes, methods, fields, functions, etc.)

        Returns STRUCTURE only, without bodies. This is the cheap, structure-first way to learn what a file
        contains: it costs far less context than reading the whole file.

        :param relative_path: the relative path to the file to get the overview of
        :param depth: depth up to which descendants shall be retrieved.
            Default (-1) results in a language specific choice: 1 for java and kotlin and 0 for other languages
        :return: the top-level symbols of the file
        """
        # Note: file system sync not required (relevant file is opened in the language server explicitly)
        if depth == -1:
            depth = 1 if relative_path.endswith((".java", ".kt")) else 0

        symbol_retriever = self._create_symbol_retriever()

        # the symbol overview is capable of working with both files and directories, but we require a file
        file_path = os.path.join(self._get_project().project_root, relative_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File or directory {relative_path} does not exist in the project.")
        if os.path.isdir(file_path):
            raise ValueError(f"Expected a file path, but got a directory path: {relative_path}. ")
        if not symbol_retriever.can_analyze_file(relative_path):
            raise ValueError(
                f"Cannot extract symbols from file {relative_path}. "
                f"Active language servers: {[l.get_key() for l in self._agent.get_active_language_server_ids()]}"
            )

        symbols = symbol_retriever.get_symbol_overview(relative_path)[relative_path]
        output_params = SymbolOutputParams(
            name_path=False,
            name=True,
            depth=depth,
            kind=True,
            relative_path=False,
            location=False,
            child_inclusion_predicate=_is_not_low_level,
        )
        renderer = LspSymbolsOverviewRenderer(self._agent, max_answer_chars, output_params, grouper=self.overview_grouper_)
        return LspSymbolCollection(symbols, renderer)

    @facade_method(uses_project_server=True, corresponding_tool=FindSymbolTool)
    def find_symbol(
        self,
        name_path_pattern: str,
        depth: int = 0,
        relative_path: str = "",
        include_body: bool = False,
        include_info: bool = False,
        include_kinds: Sequence[int] = (),
        exclude_kinds: Sequence[int] = (),
        substring_matching: bool = False,
        max_matches: int = -1,
        max_answer_chars: int = -1,
    ) -> LspSymbolCollection:
        """
        Finds symbols and code entities (classes, methods, etc.) based on the given name path pattern.

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
        :param relative_path: (optional) restrict search to this file or directory. If None, searches entire codebase.
            If a directory is passed, the search will be restricted to the files in that directory.
            If a file is passed, the search will be restricted to that file.
            If you have some knowledge about the codebase, you should use this parameter, as it will significantly
            speed up the search as well as reduce the number of results.
        :param include_body: If True, include the symbol's source code. Use judiciously.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the symbol (ignored if include_body is True). Info is never included for child symbols.
            Note: Depending on the language, this can be slow (e.g., C/C++).
        :param include_kinds: (optional) limits results to the given LSP symbol kinds (integers, i.e. values of `SymbolKind`)
        :param exclude_kinds: (optional) list of LSP symbol kinds (integers, i.e. values of `SymbolKind`) to exclude.
        :param substring_matching: If True, use substring matching for the last segment of `name_path_pattern`
            (i.e. the name of the symbol, e.g. "foo" in "Class/foo" or "my_method" in "my_method").
        :param max_matches: Maximum number of permitted matches. If exceeded, an error containing a shortened result is raised,
             which allows refining the search. -1 (default) means no limit. Set to 1 to search for a unique symbol.
        :return: the symbols (with locations) matching the name path pattern
        """
        # Note: file system sync not required; the symbol finder opens all relevant source files explicitly in the case of changes

        if include_body:
            depth = 0  # ignore user-specified depth if include_body is True
        assert max_matches != 0, "max_matches must be > 0 or equal to -1."
        symbol_retriever = self._create_symbol_retriever()
        symbols = symbol_retriever.find(
            name_path_pattern,
            include_kinds=self._parse_kinds(include_kinds),
            exclude_kinds=self._parse_kinds(exclude_kinds),
            substring_matching=substring_matching,
            within_relative_path=relative_path,
        )

        output_params = SymbolOutputParams(
            kind=True,
            name_path=True,
            name=False,
            relative_path=True,
            body_location=True,
            depth=depth,
            include_body=include_body,
            children_name=True,
            children_name_path=False,
            include_info=include_info,
        )
        renderer = LspSymbolCollectionRenderer(self._agent, max_answer_chars, output_params, grouper=self.find_symbol_dict_grouper_)
        symbol_collection = LspSymbolCollection(symbols, renderer, self._request_info(symbol_retriever, symbols, output_params))

        # check for max_matches limit exceeded
        n_matches = len(symbols)
        if 0 < max_matches < n_matches:
            raise ValueError(
                f"Matched {n_matches}>{max_matches=} symbols.\n" + TextOutputUtils.to_json(symbol_collection.relative_path_to_name_paths_())
            )

        return symbol_collection

    @facade_method(uses_project_server=True, corresponding_tool=FindReferencingSymbolsTool)
    def find_referencing_symbols(
        self,
        name_path: str,
        relative_path: str,
        include_kinds: Sequence[int] = (),
        exclude_kinds: Sequence[int] = (),
        max_answer_chars: int = -1,
    ) -> LspReferenceCollection:
        """
        Finds references to the symbol at the given `name_path`.

        The result will contain metadata about the referencing symbols as well as a short code snippet around the reference.

        :param name_path: name path of the symbol
        :param relative_path: the relative path to the file containing the symbol for which to find references.
        :param include_kinds: (optional) limits results to the given LSP symbol kinds (integers, i.e. values of `SymbolKind`)
        :param exclude_kinds: optional list of LSP symbol kinds (integers, i.e. values of `SymbolKind`) to exclude.
        :return: the references to the symbol
        """
        # file system sync needed for case where symbol finder does not perform a global search, updating everything
        if relative_path:
            self._get_project().ls_sync_file_system_changes()

        symbol_retriever = self._create_symbol_retriever()
        references = symbol_retriever.find_referencing_symbols(
            name_path,
            relative_file_path=relative_path,
            include_body=False,  # it is probably never a good idea to include the body of the referencing symbols
            include_kinds=self._parse_kinds(include_kinds),
            exclude_kinds=self._parse_kinds(exclude_kinds),
        )
        contents_around_references = [self._retrieve_content_around_reference(ref) for ref in references]
        renderer = LspReferenceCollectionRenderer(self._agent, max_answer_chars, self.references_grouper_)
        return LspReferenceCollection(references, contents_around_references, renderer)

    @facade_method(uses_project_server=True, corresponding_tool=FindImplementationsTool)
    def find_implementations(
        self,
        name_path: str,
        relative_path: str,
        include_info: bool = False,
        include_kinds: Sequence[int] = (),
        exclude_kinds: Sequence[int] = (),
        max_answer_chars: int = -1,
    ) -> LspSymbolCollection:
        """
        Finds implementations of the symbol at the given `name_path`.

        :param name_path: the symbol's name path
        :param relative_path: the relative path to the file containing the symbol for which to find implementations.
            Note that here you can't pass a directory but must pass a file.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the implementing symbols.
        :param include_kinds: (optional) limits results to the given LSP symbol kinds (integers, i.e. values of `SymbolKind`)
        :param exclude_kinds: (optional) list of LSP symbol kinds (integers, i.e. values of `SymbolKind`) to exclude.
        :return: the symbols implementing the given symbol
        """
        self._get_project().ls_sync_file_system_changes()

        symbol_retriever = self._create_symbol_retriever()
        symbols = symbol_retriever.find_implementing_symbols(
            name_path,
            relative_file_path=relative_path,
            include_body=False,
            include_kinds=self._parse_kinds(include_kinds),
            exclude_kinds=self._parse_kinds(exclude_kinds),
        )
        output_params = SymbolOutputParams(kind=True, relative_path=True, body_location=True, include_info=include_info)
        renderer = LspSymbolCollectionRenderer(self._agent, max_answer_chars, output_params)
        return LspSymbolCollection(symbols, renderer, self._request_info(symbol_retriever, symbols, output_params))

    @facade_method(uses_project_server=True, optional=True, corresponding_tool=FindTypeHierarchyTool)
    def find_type_hierarchy(
        self,
        name_path: str,
        relative_path: str,
        direction: Literal["subtypes", "supertypes"] = "subtypes",
        include_info: bool = False,
        include_kinds: Sequence[int] = (),
        exclude_kinds: Sequence[int] = (),
        max_answer_chars: int = -1,
    ) -> LspSymbolCollection:
        """
        Finds the subtypes or the supertypes of the type at the given `name_path` over the language server's
        type hierarchy.

        The direct ones per the LSP specification, though some servers (pyrefly) include the indirect ones too.
        Types defined outside the project are not included, and the result is empty when the server provides no
        type hierarchy.

        :param name_path: the type's name path
        :param relative_path: the relative path to the file containing the type.
            Note that here you can't pass a directory but must pass a file.
        :param direction: "subtypes" (the classes extending it, the types implementing it) or "supertypes"
            (the bases it extends, the interfaces it implements)
        :param include_info: whether to include additional info (hover-like, typically including docstring and
            signature), about the related types.
        :param include_kinds: (optional) limits results to the given LSP symbol kinds (integers, i.e. values of `SymbolKind`)
        :param exclude_kinds: (optional) list of LSP symbol kinds (integers, i.e. values of `SymbolKind`) to exclude.
        :return: the types related to the given type in the requested direction
        """
        self._get_project().ls_sync_file_system_changes()

        symbol_retriever = self._create_symbol_retriever()
        find = symbol_retriever.find_subtype_symbols if direction == "subtypes" else symbol_retriever.find_supertype_symbols
        symbols = find(
            name_path,
            relative_file_path=relative_path,
            include_body=False,
            include_kinds=self._parse_kinds(include_kinds),
            exclude_kinds=self._parse_kinds(exclude_kinds),
        )
        output_params = SymbolOutputParams(kind=True, relative_path=True, body_location=True, include_info=include_info)
        renderer = LspSymbolCollectionRenderer(self._agent, max_answer_chars, output_params)
        return LspSymbolCollection(symbols, renderer, self._request_info(symbol_retriever, symbols, output_params))

    @facade_method(uses_project_server=True, corresponding_tool=FindDeclarationTool)
    def find_declaration(
        self,
        relative_path: str,
        regex: str,
        containing_symbol_name_path: str | None = None,
        include_body: bool = False,
        include_info: bool = False,
    ) -> LspSymbol:
        r"""
        Finds the declaration of a symbol based on an occurrence of the symbol in a source file, specified by a regex.

        :param relative_path: the relative path to the source file containing the symbol for which to find the declaration.
        :param regex: a regular expression with one group, where the group matches the symbol for which to perform the lookup.
            For example, to find the declaration of the `process` method in a call like `obj.process()`,
            pass an expression like "obj\.(process)\(process_input_arg=37\)".
            Prefer regexes with sufficiently large context around the group to render the match unambiguous.
            Uses Python syntax with MULTILINE and DOTALL flags enabled.
        :param containing_symbol_name_path: optional name path of a containing symbol whose body shall be searched instead of the full file.
        :param include_body: whether to include the symbol's body in the result. Default False.
        :param include_info: whether to include additional info (hover-like). Default False.
        :return: the declaring symbol
        """
        self._get_project().ls_sync_file_system_changes()
        symbol_retriever = self._create_symbol_retriever()

        # find relevant location for lookup
        editor = self._create_ls_code_editor(symbol_retriever)
        if not containing_symbol_name_path:
            content = editor.read_file(relative_path)
            coords = find_text_coordinates(content, regex, require_unique=True)
            assert coords is not None
        else:
            symbol = symbol_retriever.find_unique(name_path_pattern=containing_symbol_name_path, within_relative_path=relative_path)
            body_line_numbers = symbol.get_body_line_numbers_or_raise()
            content = editor.read_file(relative_path, lines=body_line_numbers)
            coords = find_text_coordinates(content, regex, require_unique=True)
            assert coords is not None
            coords.line += body_line_numbers[0]

        # retrieve declaration
        defining_symbol = symbol_retriever.find_declaration(
            relative_file_path=relative_path, line=coords.line, column=coords.col, include_body=include_body
        )
        if defining_symbol is None:
            raise ValueError(
                f"No symbol declaration found at the location of the regex match. Location: {relative_path}:{coords.line}:{coords.col}."
            )

        output_params = SymbolOutputParams(
            kind=True, relative_path=True, body_location=True, include_body=include_body, include_info=include_info
        )
        collection_renderer = LspSymbolCollectionRenderer(self._agent, -1, output_params)
        info = self._request_info(symbol_retriever, [defining_symbol], output_params).get(defining_symbol)
        return LspSymbol(defining_symbol, LspSymbolRenderer(self._agent, -1, collection_renderer), info)

    @facade_method(uses_project_server=True, corresponding_tool=GetDiagnosticsForFileTool)
    def get_diagnostics_for_file(
        self, relative_path: str, start_line: int = 0, end_line: int = -1, min_severity: int = 4, max_answer_chars: int = -1
    ) -> LspDiagnostics:
        """
        Gets diagnostics for a file.

        Diagnostics are grouped as `relative_path -> severity -> name_path -> diagnostics_results`.
        If a diagnostic cannot be mapped to a symbol, it is grouped under the special name path `<file>`.

        :param relative_path: the relative path to the file to inspect.
        :param start_line: the first 0-based line to include. Defaults to 0.
        :param end_line: the last 0-based line to include. Defaults to -1, which means until the end of the file.
        :param min_severity: minimum LSP severity to include, where 1=Error, 2=Warning, 3=Information, 4=Hint.
            Diagnostics with lower-or-equal numeric severity are returned.
        :return: the grouped diagnostics for the requested file.
        """
        self._get_project().ls_sync_file_system_changes()

        symbol_retriever = self._create_symbol_retriever()
        diagnostics = symbol_retriever.get_file_diagnostics(
            relative_file_path=relative_path, start_line=start_line, end_line=end_line, min_severity=min_severity
        )

        grouped_diagnostics = GroupedDiagnostics()
        for diagnostic in diagnostics:
            diag_start = diagnostic["range"]["start"]
            owner_symbol = symbol_retriever.find_diagnostic_owner_symbol(
                relative_file_path=relative_path, line=diag_start["line"], column=diag_start["character"]
            )
            name_path = owner_symbol.get_name_path() if owner_symbol is not None else self.FILE_LEVEL_DIAGNOSTIC_BUCKET
            grouped_diagnostics.add(relative_path, name_path, diagnostic)

        return self._create_diagnostics(grouped_diagnostics, max_answer_chars)

    @facade_method(uses_project_server=True, optional=True, corresponding_tool=GetDiagnosticsForSymbolTool)
    def get_diagnostics_for_symbol(
        self,
        name_path: str,
        reference_file: str = "",
        check_symbol_references: bool = False,
        min_severity: int = 4,
        max_answer_chars: int = -1,
    ) -> LspDiagnostics:
        """
        Gets diagnostics for the specified symbol.

        When `check_symbol_references` is true, diagnostics for all referencing symbols are also included.
        The result is grouped as `relative_path -> severity -> name_path -> diagnostics_results`.

        :param name_path: the name path of the symbol to inspect.
        :param reference_file: optional file path used to disambiguate the symbol search.
        :param check_symbol_references: whether to additionally collect diagnostics for symbols that reference the symbol.
        :param min_severity: minimum LSP severity to include, where 1=Error, 2=Warning, 3=Information, 4=Hint.
            Diagnostics with lower-or-equal numeric severity are returned.
        :return: the grouped diagnostics for the requested symbol and, optionally, its referencing symbols.
        """
        self._get_project().ls_sync_file_system_changes()

        symbol_retriever = self._create_symbol_retriever()
        diagnostics_by_symbol = symbol_retriever.get_symbol_diagnostics(
            name_path=name_path,
            reference_file=reference_file or None,
            check_symbol_references=check_symbol_references,
            min_severity=min_severity,
        )

        grouped_diagnostics = GroupedDiagnostics()
        for symbol, diagnostics in diagnostics_by_symbol.items():
            relative_path = symbol.relative_path
            if relative_path is None:
                continue
            for diagnostic in diagnostics:
                grouped_diagnostics.add(relative_path, symbol.get_name_path(), diagnostic)

        return self._create_diagnostics(grouped_diagnostics, max_answer_chars)

    # edit operations

    @facade_method(uses_project_server=True, can_edit=True, corresponding_tool=RenameSymbolTool)
    def rename_symbol(self, name_path: str, relative_path: str, new_name: str) -> str:
        """
        Renames the symbol with the given `name_path` to `new_name` throughout the entire codebase.
        Note: for languages with method overloading, like Java, name_path may have to include a method's
        signature to uniquely identify a method.

        :param name_path: name path of the symbol to rename
        :param relative_path: the relative path to the file containing the symbol to rename
        :param new_name: the new name for the symbol
        :return: a result summary indicating success or failure
        """
        self._get_project().ls_sync_file_system_changes()
        return self._create_ls_code_editor().rename_symbol(name_path, relative_path=relative_path, new_name=new_name)

    @facade_method(uses_project_server=True, can_edit=True, corresponding_tool=SafeDeleteSymbol)
    def safe_delete_symbol(self, name_path_pattern: str, relative_path: str) -> str:
        """
        Deletes the symbol if it is safe to do so (i.e., if there are no references to it)
        or returns a list of references to it.

        :param name_path_pattern: name path of the symbol to delete
        :param relative_path: the relative path to the file containing the symbol to delete
        :return: a success message, or a message listing the references preventing deletion
        """
        self._get_project().ls_sync_file_system_changes()

        symbol_retriever = self._create_symbol_retriever()
        symbol = symbol_retriever.find_unique(name_path_pattern, substring_matching=False, within_relative_path=relative_path)
        symbol_rel_path = symbol.relative_path
        assert symbol_rel_path is not None, f"Symbol {name_path_pattern} has no relative path, this is likely a bug."
        assert symbol_rel_path == relative_path, f"Symbol {name_path_pattern} is not in the expected relative path {relative_path}."
        symbol_name_path = symbol.get_name_path()

        # check for references
        symbol_line = symbol.line
        symbol_col = symbol.column
        assert symbol_line is not None and symbol_col is not None, (
            f"Symbol {name_path_pattern} has no identifier position, this is likely a bug."
        )
        lang_server = symbol_retriever.get_language_server(symbol_rel_path)
        references_locations = lang_server.request_references(symbol_rel_path, symbol_line, symbol_col)
        file_to_lines: dict[str, list[int]] = defaultdict(list)
        for ref_loc in references_locations or []:
            ref_relative_path = ref_loc.get("relativePath")
            if ref_relative_path is None:
                continue
            file_to_lines[ref_relative_path].append(ref_loc["range"]["start"]["line"])
        if file_to_lines:
            return f"Cannot delete, the symbol {symbol_name_path} is referenced in: {TextOutputUtils.to_json(file_to_lines)}"

        self._create_ls_code_editor(symbol_retriever).delete_symbol(symbol_name_path, relative_file_path=symbol_rel_path)
        return SUCCESS_RESULT
