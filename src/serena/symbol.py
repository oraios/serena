import logging
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from copy import copy
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Self

from sensai.util.string import ToStringMixin

from multilspy import SyncLanguageServer
from multilspy.multilspy_types import Position, SymbolKind, UnifiedSymbolInformation

if TYPE_CHECKING:
    from .agent import SerenaAgent

log = logging.getLogger(__name__)


@dataclass
class SymbolLocation:
    """
    Represents the (start) location of a symbol identifier
    """

    relative_path: str | None
    """
    the relative path of the file containing the symbol; if None, the symbol is defined outside of the project's scope
    """
    line: int | None
    """
    the line number in which the symbol identifier is defined (if the symbol is a function, class, etc.);
    may be None for some types of symbols (e.g. SymbolKind.File)
    """
    column: int | None
    """
    the column number in which the symbol identifier is defined (if the symbol is a function, class, etc.);
    may be None for some types of symbols (e.g. SymbolKind.File)
    """

    def __post_init__(self) -> None:
        if self.relative_path is not None:
            self.relative_path = self.relative_path.replace("/", os.path.sep)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def has_position_in_file(self) -> bool:
        return self.relative_path is not None and self.line is not None and self.column is not None


class Symbol(ToStringMixin):
    def __init__(self, s: UnifiedSymbolInformation) -> None:
        self.s = s

    def _tostring_includes(self) -> list[str]:
        return []

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return dict(name=self.name, kind=self.kind, num_children=len(self.s["children"]))

    @property
    def name(self) -> str:
        return self.s["name"]

    @property
    def kind(self) -> str:
        return SymbolKind(self.symbol_kind).name

    @property
    def symbol_kind(self) -> SymbolKind:
        return self.s["kind"]

    @property
    def relative_path(self) -> str | None:
        return self.s["location"]["relativePath"]

    @property
    def location(self) -> SymbolLocation:
        """
        :return: the start location of the actual symbol identifier
        """
        return SymbolLocation(relative_path=self.relative_path, line=self.line, column=self.column)

    @property
    def body_start_position(self) -> Position:
        return self.s["location"]["range"]["start"]

    @property
    def body_end_position(self) -> Position | None:
        """
        :return: the end position of the symbol body or None if not available
        """
        try:
            return self.s["location"]["range"]["end"]
        except (KeyError, TypeError):
            return None

    @property
    def line(self) -> int | None:
        if "selectionRange" in self.s:
            return self.s["selectionRange"]["start"]["line"]
        else:
            # line is expected to be undefined for some types of symbols (e.g. SymbolKind.File)
            return None

    @property
    def column(self) -> int | None:
        if "selectionRange" in self.s:
            return self.s["selectionRange"]["start"]["character"]
        else:
            # precise location is expected to be undefined for some types of symbols (e.g. SymbolKind.File)
            return None

    @property
    def body(self) -> str | None:
        return self.s.get("body")

    def iter_children(self) -> Iterator["Symbol"]:
        for c in self.s["children"]:
            yield Symbol(c)

    def find(
        self,
        name: str,
        substring_matching: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list["Symbol"]:
        result = []

        def should_include(s: "Symbol") -> bool:
            if not ((substring_matching and name in s.name) or name == s.name):
                return False
            if include_kinds is not None and s.symbol_kind not in include_kinds:
                return False
            if exclude_kinds is not None and s.symbol_kind in exclude_kinds:
                return False
            return True

        def traverse(s: "Symbol") -> None:
            if should_include(s):
                result.append(s)
            for c in s.iter_children():
                traverse(c)

        traverse(self)
        return result

    def to_dict(
        self, kind: bool = False, location: bool = False, depth: int = 0, include_body: bool = False, include_children_body: bool = False
    ) -> dict[str, Any]:
        """
        Convert the symbol to a dictionary.

        :param kind: whether to include the kind of the symbol
        :param location: whether to include the location of the symbol (will also include end_location if available)
        :param depth: the depth of the symbol
        :param include_body: whether to include the body of the top-level symbol.
        :param include_children_body: whether to also include the body of the children.
            Note that the body of the children is part of the body of the parent symbol,
            so there is usually no need to set this to True unless you want process the output
            and pass the children without passing the parent body to the LM.
        :return: a dictionary representation of the symbol with fields like 'name', 'kind', 'location', 'end_location'
        """
        result: dict[str, Any] = {"name": self.name}

        if kind:
            result["kind"] = self.kind

        if location:
            result["location"] = self.location.to_dict()
            # Add end position information
            end_pos = self.body_end_position
            if end_pos is not None:
                result["end_location"] = {"relative_path": self.relative_path, "line": end_pos["line"], "column": end_pos["character"]}

        if include_body:
            if self.body is None:
                log.warning("Requested body for symbol, but it is not present. The symbol might have been loaded with include_body=False.")
            result["body"] = self.body

        def add_children(s: Self) -> list[dict[str, Any]]:
            children = []
            for c in s.iter_children():
                children.append(
                    c.to_dict(
                        kind=kind,
                        location=location,
                        depth=depth - 1,
                        include_body=include_children_body,
                        include_children_body=include_children_body,
                    )
                )
            return children

        if depth > 0:
            result["children"] = add_children(self)

        return result


class SymbolManager:
    def __init__(self, lang_server: SyncLanguageServer, agent: "SerenaAgent") -> None:
        self.lang_server = lang_server
        self.agent = agent

    def _to_symbols(self, items: list[UnifiedSymbolInformation]) -> list[Symbol]:
        return [Symbol(s) for s in items]

    def find_by_name(
        self,
        name: str,
        within_relative_path: str | None = None,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        substring_matching: bool = False,
    ) -> list[Symbol]:
        """
        Find all symbols that match the given name.

        :param name: the name of the symbol to find
        :param within_relative_path: pass a relative path to only consider symbols within this path.
            If a file is passed, only the symbols within this file will be considered.
            If a directory is passed, all files within this directory will be considered.
            If None, the entire codebase will be considered.
        :param include_body: whether to include the body of all symbols in the result.
            Note: you can filter out the bodies of the children if you set include_children_body=False
            in the to_dict method.
        :param include_kinds: an optional sequence of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :param substring_matching: whether to use substring matching for the symbol name.
            If True, the symbol name will be matched if it contains the given name as a substring.
        :return: a list of symbols that match the given name
        """
        symbols: list[Symbol] = []
        symbol_roots = self.lang_server.request_full_symbol_tree(within_relative_path=within_relative_path, include_body=include_body)
        for root in symbol_roots:
            symbols.extend(
                Symbol(root).find(name, include_kinds=include_kinds, exclude_kinds=exclude_kinds, substring_matching=substring_matching)
            )
        return symbols

    def get_document_symbols(self, relative_path: str) -> list[Symbol]:
        symbol_dicts, roots = self.lang_server.request_document_symbols(relative_path, include_body=False)
        symbols = [Symbol(s) for s in symbol_dicts]
        return symbols

    def find_by_location(self, location: SymbolLocation) -> Symbol | None:
        if location.relative_path is None:
            return None
        symbol_dicts, roots = self.lang_server.request_document_symbols(location.relative_path, include_body=False)
        for symbol_dict in symbol_dicts:
            symbol = Symbol(symbol_dict)
            if symbol.location == location:
                return symbol
        return None

    def find_referencing_symbols(
        self,
        symbol_location: SymbolLocation,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list[Symbol]:
        """
        Find all symbols that reference the symbol at the given location.

        :param symbol_location: the location of the symbol for which to find references
        :param include_body: whether to include the body of all symbols in the result.
            Note: you can filter out the bodies of the children if you set include_children_body=False
            in the to_dict method.
        :param include_kinds: an optional sequence of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
            Takes precedence over include_kinds.
        :return: a list of symbols that reference the given symbol
        """
        if not symbol_location.has_position_in_file():
            raise ValueError("Symbol location does not contain a valid position in a file")
        assert symbol_location.relative_path is not None
        assert symbol_location.line is not None
        assert symbol_location.column is not None
        symbol_dicts = self.lang_server.request_referencing_symbols(
            relative_file_path=symbol_location.relative_path,
            line=symbol_location.line,
            column=symbol_location.column,
            include_imports=False,
            include_self=False,
            include_body=include_body,
        )

        if include_kinds is not None:
            symbol_dicts = [s for s in symbol_dicts if s["kind"] in include_kinds]

        if exclude_kinds is not None:
            symbol_dicts = [s for s in symbol_dicts if s["kind"] not in exclude_kinds]

        return self._to_symbols(symbol_dicts)

    @contextmanager
    def _edited_file(self, relative_path: str) -> Iterator[None]:
        with self.lang_server.open_file(relative_path) as file_buffer:
            yield
            root_path = self.lang_server.language_server.repository_root_path
            abs_path = os.path.join(root_path, relative_path)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(file_buffer.contents)
            self.agent.mark_file_modified(relative_path)

    @contextmanager
    def _edited_symbol_location(self, location: SymbolLocation) -> Iterator[Symbol]:
        symbol = self.find_by_location(location)
        if symbol is None:
            raise ValueError("Symbol not found/has no defined location within a file")
        assert location.relative_path is not None
        with self._edited_file(location.relative_path):
            yield symbol

    def replace_body(self, location: SymbolLocation, body: str) -> None:
        """
        Replace the body of the symbol at the given location with the given body

        :param location: the location of the symbol to replace
        :param body: the new body
        """
        # make sure body always ends with at least one newline
        if not body.endswith("\n"):
            body += "\n"
        with self._edited_symbol_location(location) as symbol:
            assert location.relative_path is not None
            self.lang_server.delete_text_between_positions(location.relative_path, symbol.body_start_position, symbol.body_end_position)
            self.lang_server.insert_text_at_position(
                location.relative_path, symbol.body_start_position["line"], symbol.body_start_position["character"], body
            )

    def insert_after(self, location: SymbolLocation, body: str) -> None:
        """
        Appends content after the given symbol

        :param location: the location of the symbol after which to add new lines
        :param body: the body of the entity to append
        """
        # make sure body always ends with at least one newline
        if not body.endswith("\n"):
            body += "\n"
        with self._edited_symbol_location(location) as symbol:
            pos = symbol.body_end_position
            assert location.relative_path is not None
            self.lang_server.insert_text_at_position(location.relative_path, pos["line"], pos["character"], body)

    def insert_before(self, location: SymbolLocation, body: str) -> None:
        """
        Inserts content before the given symbol

        :param location: the location of the symbol before which to add new lines
        :param body: the body of the entity to insert
        """
        # make sure body always ends with at least one newline
        if not body.endswith("\n"):
            body += "\n"
        with self._edited_symbol_location(location) as symbol:
            pos = copy(symbol.body_start_position)
            assert location.relative_path is not None
            self.lang_server.insert_text_at_position(location.relative_path, pos["line"], pos["character"], body)

    def insert_at_line(self, relative_path: str, line: int, content: str) -> None:
        """
        Inserts content at the given line in the given file.

        :param line: the 0-based index of the line to insert content at
        :param content: the content to insert
        """
        with self._edited_file(relative_path):
            self.lang_server.insert_text_at_position(relative_path, line, 0, content)

    def delete_lines(self, relative_path: str, start_line: int, end_line: int) -> None:
        """
        Deletes lines in the given file.

        :param start_line: the 0-based index of the first line to delete (inclusive)
        :param end_line: the 0-based index of the last line to delete (inclusive)
        """
        with self._edited_file(relative_path):
            start_pos = Position(line=start_line, character=0)
            end_pos = Position(line=end_line + 1, character=0)
            self.lang_server.delete_text_between_positions(relative_path, start_pos, end_pos)