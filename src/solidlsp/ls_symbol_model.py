"""
Symbol model (Phase 4 deep module).

This module owns:
- SymbolBody: lightweight representation of a symbol's text body (pickle-stable)
- SymbolBodyFactory: creates SymbolBody instances from file buffers
- DocumentSymbols: high-level unified symbol tree (pickle-stable)
- RawDocumentSymbol type alias
- Conversion helpers that turn raw LSP document symbols into unified form

These classes remain re-exported from solidlsp.ls for backward compatibility
(callers and pickle paths must not change their qualified names).
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Union, cast

from sensai.util.pickle import getstate
from sensai.util.string import ToStringMixin

from solidlsp import ls_types
from solidlsp.ls_types import UnifiedSymbolInformation
from solidlsp.lsp_protocol_handler.lsp_types import DocumentSymbol, SymbolInformation

if TYPE_CHECKING:
    from solidlsp.ls_documents import LSPFileBuffer

RawDocumentSymbol = Union[DocumentSymbol, SymbolInformation]
"""
Type alias for the raw symbol information returned by a language server in response to a
`textDocument/documentSymbol` request.
The `DocumentSymbol` is the preferred type, but the legacy type `SymbolInformation` is also still used.
"""


@dataclasses.dataclass(kw_only=True)
class ReferenceInSymbol:
    """A symbol retrieved when requesting reference to a symbol, together with the location of the reference"""

    symbol: ls_types.UnifiedSymbolInformation
    line: int
    character: int


class SymbolBody(ToStringMixin):
    """
    Representation of the body of a symbol, which allows the extraction of the symbol's text
    from the lines of the file it is defined in.

    Instances that share the same lines buffer are memory-efficient,
    using only 4 integers and a reference to the lines buffer from which the text can be extracted,
    i.e. a core representation of only about 40 bytes per body.
    """

    def __init__(self, lines: list[str], start_line: int, start_col: int, end_line: int, end_col: int) -> None:
        self._lines = lines
        self._start_line = start_line
        self._start_col = start_col
        self._end_line = end_line
        self._end_col = end_col

    def _tostring_excludes(self) -> list[str]:
        return ["_lines"]

    def get_text(self) -> str:
        # extract relevant lines
        symbol_body = "\n".join(self._lines[self._start_line : self._end_line + 1])

        # remove leading content from the first line
        symbol_body = symbol_body[self._start_col :]

        # remove trailing content from the last line
        last_line = self._lines[self._end_line]
        trailing_length = len(last_line) - self._end_col
        if trailing_length > 0:
            symbol_body = symbol_body[: -(len(last_line) - self._end_col)]

        return symbol_body


class SymbolBodyFactory:
    """
    A factory for the creation of SymbolBody instances from symbols dictionaries.
    Instances created from the same factory instance are memory-efficient, as they share
    the same lines buffer.
    """

    def __init__(self, file_buffer: "LSPFileBuffer"):
        self._lines = file_buffer.split_lines()

    def create_symbol_body(self, symbol: UnifiedSymbolInformation) -> SymbolBody:
        existing_body = symbol.get("body", None)
        if existing_body and isinstance(existing_body, SymbolBody):
            return existing_body

        assert "location" in symbol
        start_line = symbol["location"]["range"]["start"]["line"]
        end_line = symbol["location"]["range"]["end"]["line"]
        start_col = symbol["location"]["range"]["start"]["character"]
        end_col = symbol["location"]["range"]["end"]["character"]
        return SymbolBody(self._lines, start_line, start_col, end_line, end_col)


class DocumentSymbols:
    # IMPORTANT: Instances of this class are persisted in the high-level document symbol cache

    def __init__(self, root_symbols: list[ls_types.UnifiedSymbolInformation]):
        self.root_symbols = root_symbols
        self._all_symbols: list[ls_types.UnifiedSymbolInformation] | None = None

    def __getstate__(self) -> dict:
        return getstate(DocumentSymbols, self, transient_properties=["_all_symbols"])

    def iter_symbols(self) -> Iterator[ls_types.UnifiedSymbolInformation]:
        """
        Iterate over all symbols in the document symbol tree.
        Yields symbols in a depth-first manner.
        """
        if self._all_symbols is not None:
            yield from self._all_symbols
            return

        def traverse(s: ls_types.UnifiedSymbolInformation) -> Iterator[ls_types.UnifiedSymbolInformation]:
            yield s
            for child in s.get("children", []):
                yield from traverse(child)

        for root_symbol in self.root_symbols:
            yield from traverse(root_symbol)

    def get_all_symbols_and_roots(self) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """
        This function returns all symbols in the document as a flat list and the root symbols.
        It exists to facilitate migration from previous versions, where this was the return interface of
        the LS method that obtained document symbols.

        :return: A tuple containing a list of all symbols in the document and a list of root symbols.
        """
        if self._all_symbols is None:
            self._all_symbols = list(self.iter_symbols())
        return self._all_symbols, self.root_symbols


def convert_raw_document_symbols_to_unified(
    *,
    root_symbols: list[RawDocumentSymbol],
    relative_file_path: str,
    repository_root_path: str,
    normalize_name: Callable[[RawDocumentSymbol, str], str],
    create_body: Callable[[UnifiedSymbolInformation, SymbolBodyFactory | None], SymbolBody],
    body_factory: SymbolBodyFactory,
) -> list[ls_types.UnifiedSymbolInformation]:
    """
    Convert raw LSP document symbols (DocumentSymbol/SymbolInformation) into the
    unified representation used by SolidLSP.

    This encapsulates the conversion logic that was previously inline in
    SolidLanguageServer.request_document_symbols.

    The callables normalize_name and create_body are supplied by the caller
    (typically the facade) so that language-specific hooks remain on the facade.
    """

    def convert_to_unified_symbol(original_symbol_dict: RawDocumentSymbol) -> ls_types.UnifiedSymbolInformation:
        # noinspection PyInvalidCast
        item = cast(ls_types.UnifiedSymbolInformation, dict(original_symbol_dict))
        absolute_path = os.path.join(repository_root_path, relative_file_path)

        # handle missing location and path entries
        if "location" not in item:
            uri = pathlib.Path(absolute_path).as_uri()
            assert "range" in item
            tree_location = ls_types.Location(
                uri=uri,
                range=item["range"],
                absolutePath=absolute_path,
                relativePath=relative_file_path,
            )
            item["location"] = tree_location
        location = item["location"]
        if "absolutePath" not in location:
            location["absolutePath"] = absolute_path
        if "relativePath" not in location:
            location["relativePath"] = relative_file_path

        item["body"] = create_body(item, body_factory)

        # handle missing selectionRange
        if "selectionRange" not in item:
            if "range" in item:
                item["selectionRange"] = item["range"]
            else:
                item["selectionRange"] = item["location"]["range"]

        return item

    def convert_symbols_with_common_parent(
        symbols: list[RawDocumentSymbol],
        parent: ls_types.UnifiedSymbolInformation | None,
    ) -> list[ls_types.UnifiedSymbolInformation]:
        # apply name normalization and count occurrences of each symbol name
        total_name_counts: dict[str, int] = defaultdict(lambda: 0)
        for symbol in symbols:
            name = normalize_name(symbol, relative_file_path)
            symbol["name"] = name
            total_name_counts[name] += 1

        # convert symbols to the unified representation and
        #  * add overload indices where necessary
        #  * ensure that the "parent" field is set correctly
        name_counts: dict[str, int] = defaultdict(lambda: 0)
        unified_symbols: list[ls_types.UnifiedSymbolInformation] = []
        for symbol in symbols:
            usymbol = convert_to_unified_symbol(symbol)
            if total_name_counts[usymbol["name"]] > 1:
                usymbol["overload_idx"] = name_counts[usymbol["name"]]
            name_counts[usymbol["name"]] += 1
            usymbol["parent"] = parent
            if "children" in usymbol:
                usymbol["children"] = convert_symbols_with_common_parent(usymbol["children"], usymbol)  # type: ignore
            else:
                usymbol["children"] = []
            unified_symbols.append(usymbol)
        return unified_symbols

    return convert_symbols_with_common_parent(root_symbols, None)
