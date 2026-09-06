# SPDX-License-Identifier: GPL-3.0-or-later

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from serena.symbol import LanguageServerSymbol, LanguageServerSymbolDictGrouper, LanguageServerSymbolRetriever, SymbolDictGrouper
from solidlsp.lsp_protocol_handler.lsp_types import SymbolKind

from ...util.text_utils import TextOutputUtils
from ..facade import FacadeApi
from ..representable import Renderer, RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent


class LspSymbolCollection(RepresentableViaRenderer):
    def __init__(self, symbols: list[LanguageServerSymbol], renderer: "LspSymbolCollectionRenderer"):
        """
        :param symbols: the list of symbols
        :param renderer: the renderer to use for representing the collection
        """
        super().__init__(renderer)
        self.symbols = symbols

    def __len__(self):
        return len(self.symbols)

    def relative_path_to_name_paths_(self) -> dict[str, list[str]]:
        result: defaultdict[str, list[str]] = defaultdict(list)
        for s in self.symbols:
            result[s.location.relative_path or "unknown"].append(s.get_name_path())
        return result


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


class LspSymbolCollectionRenderer(Renderer[LspSymbolCollection]):
    def __init__(
        self,
        agent: "SerenaAgent",
        max_answer_chars: int,
        symbol_retriever: LanguageServerSymbolRetriever,
        output_params: SymbolOutputParams,
        grouper: SymbolDictGrouper | None = None,
    ):
        super().__init__(agent, max_answer_chars)
        self._symbol_retriever = symbol_retriever
        self._output_params = output_params
        self._grouper = grouper

    def set_grouper(self, grouper: SymbolDictGrouper) -> None:
        self._grouper = grouper

    def render(self, obj: LspSymbolCollection) -> str:
        symbols = obj.symbols
        symbol_dicts = [
            s.to_dict(
                kind=self._output_params.kind,
                name_path=self._output_params.name_path,
                name=self._output_params.name,
                relative_path=self._output_params.relative_path,
                body_location=self._output_params.body_location,
                depth=self._output_params.depth,
                body=self._output_params.include_body,
                children_name=self._output_params.children_name,
                children_name_path=self._output_params.children_name_path,
            )
            for s in symbols
        ]
        if not self._output_params.include_body and self._output_params.include_info:
            info_by_symbol = self._symbol_retriever.request_info_for_symbol_batch(symbols)
            for s, s_dict in zip(symbols, symbol_dicts, strict=True):
                if symbol_info := info_by_symbol.get(s):
                    # In python 3.15 we could specify extra_items=True in the TypedDict definition,
                    # https://peps.python.org/pep-0728/
                    # If we ever upgrade to 3.15, we can remove the type: ignore[typeddict-unknown-key]
                    s_dict["info"] = symbol_info

        def create_short_result_relative_path_to_name_paths() -> str:
            relative_path_to_name_paths = obj.relative_path_to_name_paths_()
            return f"Shortened result:\n{TextOutputUtils.to_json(relative_path_to_name_paths)}"

        if self._grouper is not None:
            objects = self._grouper.group(symbol_dicts)
        else:
            objects = symbol_dicts
        result = self._to_json(objects)
        return self._limit_length(result, shortened_result_factories=[create_short_result_relative_path_to_name_paths])


class LspApi(FacadeApi):
    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(agent, name="lsp", description="LSP-backed operations on the codebase (finding symbols, etc.)")

    def _create_symbol_retriever(self) -> LanguageServerSymbolRetriever:
        assert self._agent.get_language_backend().is_lsp(), "Symbolic read operations require the language server backend"
        return LanguageServerSymbolRetriever(self._get_project())

    # group children by kind, keeping just the name (the parent's name_path makes it unambiguous);
    # we don't group the top-level result list because many tests rely on it being a flat list of symbol dicts
    find_symbol_dict_grouper_ = LanguageServerSymbolDictGrouper([], ["kind"], collapse_singleton=True)

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
        :param include_body: whether to include the symbol's source code. Use judiciously.
        :param include_info: whether to include additional info (hover-like, typically including docstring and signature),
            about the symbol (ignored if include_body is True). Info is never included for child symbols.
            Note: Depending on the language, this can be slow (e.g., C/C++).
        :param include_kinds: (optional) limits results to the given LSP symbol kinds (integers)
        :param exclude_kinds: (optional) list of LSP symbol kinds (integers) to exclude.
        :param substring_matching: If True, use substring matching for the last element of the pattern, such that
            "Foo/get" would match "Foo/getValue" and "Foo/getData".
        :param max_matches: maximum number of permitted matches. If exceeded, a shortened result is returned
             which allows refining the search. -1 (default) means no limit. Set to 1 to search for a unique symbol.
        :param max_answer_chars: max result length; -1 for default
        :return: collection of matching symbols
        """
        # Note: file system sync not required; the symbol finder opens all relevant source files explicitly in the case of changes

        if include_body:
            depth = 0  # ignore user-specified depth if include_body is True
        assert max_matches != 0, "max_matches must be > 0 or equal to -1."
        parsed_include_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in include_kinds] if include_kinds else None
        parsed_exclude_kinds: Sequence[SymbolKind] | None = [SymbolKind(k) for k in exclude_kinds] if exclude_kinds else None
        symbol_retriever = self._create_symbol_retriever()
        symbols = symbol_retriever.find(
            name_path_pattern,
            include_kinds=parsed_include_kinds,
            exclude_kinds=parsed_exclude_kinds,
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
        renderer = LspSymbolCollectionRenderer(
            self._agent, max_answer_chars, symbol_retriever, output_params, grouper=self.find_symbol_dict_grouper_
        )
        symbol_collection = LspSymbolCollection(symbols, renderer)

        # check for max_matches limit exceeded
        n_matches = len(symbols)
        if 0 < max_matches < n_matches:
            raise ValueError(
                f"Matched {n_matches}>{max_matches=} symbols.\n" + TextOutputUtils.to_json(symbol_collection.relative_path_to_name_paths_())
            )

        return symbol_collection
