import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, NotRequired, Self, TypedDict, Union

from sensai.util.string import ToStringMixin

from solidlsp import SolidLanguageServer
from solidlsp.ls import ReferenceInSymbol as LSPReferenceInSymbol
from solidlsp.ls_types import Position, SymbolKind, UnifiedSymbolInformation

from .project import Project

if TYPE_CHECKING:
    from .agent import SerenaAgent

log = logging.getLogger(__name__)


@dataclass
class LanguageServerSymbolLocation:
    """
    Represents the (start) location of a symbol identifier, which, within Serena, uniquely identifies the symbol.
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

    def to_dict(self, include_relative_path: bool = True) -> dict[str, Any]:
        result = asdict(self)
        if not include_relative_path:
            result.pop("relative_path", None)
        return result

    def has_position_in_file(self) -> bool:
        return self.relative_path is not None and self.line is not None and self.column is not None


@dataclass
class PositionInFile:
    """
    Represents a character position within a file
    """

    line: int
    """
    the 0-based line number in the file
    """
    col: int
    """
    the 0-based column
    """

    def to_lsp_position(self) -> Position:
        """
        Convert to LSP Position.
        """
        return Position(line=self.line, character=self.col)


class Symbol(ToStringMixin, ABC):
    @abstractmethod
    def get_body_start_position(self) -> PositionInFile | None:
        pass

    @abstractmethod
    def get_body_end_position(self) -> PositionInFile | None:
        pass

    def get_body_start_position_or_raise(self) -> PositionInFile:
        """
        Get the start position of the symbol body, raising an error if it is not defined.
        """
        pos = self.get_body_start_position()
        if pos is None:
            raise ValueError(f"Body start position is not defined for {self}")
        return pos

    def get_body_end_position_or_raise(self) -> PositionInFile:
        """
        Get the end position of the symbol body, raising an error if it is not defined.
        """
        pos = self.get_body_end_position()
        if pos is None:
            raise ValueError(f"Body end position is not defined for {self}")
        return pos

    @abstractmethod
    def is_neighbouring_definition_separated_by_empty_line(self) -> bool:
        """
        :return: whether a symbol definition of this symbol's kind is usually separated from the
            previous/next definition by at least one empty line.
        """


class LanguageServerSymbol(Symbol, ToStringMixin):
    _NAME_PATH_SEP = "/"

    @staticmethod
    def match_name_path(
        name_path: str,
        symbol_name_path_parts: list[str],
        substring_matching: bool,
    ) -> bool:
        """
        Checks if a given `name_path` matches a symbol's qualified name parts.
        See docstring of `Symbol.find` for more details.
        """
        assert name_path, "name_path must not be empty"
        assert symbol_name_path_parts, "symbol_name_path_parts must not be empty"
        name_path_sep = LanguageServerSymbol._NAME_PATH_SEP

        is_absolute_pattern = name_path.startswith(name_path_sep)
        pattern_parts = name_path.lstrip(name_path_sep).rstrip(name_path_sep).split(name_path_sep)

        # filtering based on ancestors
        if len(pattern_parts) > len(symbol_name_path_parts):
            # can't possibly match if pattern has more parts than symbol
            return False
        if is_absolute_pattern and len(pattern_parts) != len(symbol_name_path_parts):
            # for absolute patterns, the number of parts must match exactly
            return False
        if symbol_name_path_parts[-len(pattern_parts) : -1] != pattern_parts[:-1]:
            # ancestors must match
            return False

        # matching the last part of the symbol name
        name_to_match = pattern_parts[-1]
        symbol_name = symbol_name_path_parts[-1]
        if substring_matching:
            return name_to_match in symbol_name
        else:
            return name_to_match == symbol_name

    def __init__(self, symbol_root_from_ls: UnifiedSymbolInformation) -> None:
        self.symbol_root = symbol_root_from_ls

    def _tostring_includes(self) -> list[str]:
        return []

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return dict(name=self.name, kind=self.kind, num_children=len(self.symbol_root["children"]))

    @property
    def name(self) -> str:
        return self.symbol_root["name"]

    @property
    def kind(self) -> str:
        return SymbolKind(self.symbol_kind).name

    @property
    def symbol_kind(self) -> SymbolKind:
        return self.symbol_root["kind"]

    def is_neighbouring_definition_separated_by_empty_line(self) -> bool:
        return self.symbol_kind in (SymbolKind.Function, SymbolKind.Method, SymbolKind.Class, SymbolKind.Interface, SymbolKind.Struct)

    @property
    def relative_path(self) -> str | None:
        location = self.symbol_root.get("location")
        if location:
            return location.get("relativePath")
        return None

    @property
    def location(self) -> LanguageServerSymbolLocation:
        """
        :return: the start location of the actual symbol identifier
        """
        return LanguageServerSymbolLocation(relative_path=self.relative_path, line=self.line, column=self.column)

    @property
    def body_start_position(self) -> Position | None:
        location = self.symbol_root.get("location")
        if location:
            range_info = location.get("range")
            if range_info:
                start_pos = range_info.get("start")
                if start_pos:
                    return start_pos
        return None

    @property
    def body_end_position(self) -> Position | None:
        location = self.symbol_root.get("location")
        if location:
            range_info = location.get("range")
            if range_info:
                end_pos = range_info.get("end")
                if end_pos:
                    return end_pos
        return None

    def get_body_start_position(self) -> PositionInFile | None:
        start_pos = self.body_start_position
        if start_pos is None:
            return None
        return PositionInFile(line=start_pos["line"], col=start_pos["character"])

    def get_body_end_position(self) -> PositionInFile | None:
        end_pos = self.body_end_position
        if end_pos is None:
            return None
        return PositionInFile(line=end_pos["line"], col=end_pos["character"])

    def get_body_line_numbers(self) -> tuple[int | None, int | None]:
        start_pos = self.body_start_position
        end_pos = self.body_end_position
        start_line = start_pos["line"] if start_pos else None
        end_line = end_pos["line"] if end_pos else None
        return start_line, end_line

    @property
    def line(self) -> int | None:
        """
        :return: the line in which the symbol identifier is defined.
        """
        if "selectionRange" in self.symbol_root:
            return self.symbol_root["selectionRange"]["start"]["line"]
        else:
            # line is expected to be undefined for some types of symbols (e.g. SymbolKind.File)
            return None

    @property
    def column(self) -> int | None:
        if "selectionRange" in self.symbol_root:
            return self.symbol_root["selectionRange"]["start"]["character"]
        else:
            # precise location is expected to be undefined for some types of symbols (e.g. SymbolKind.File)
            return None

    @property
    def body(self) -> str | None:
        return self.symbol_root.get("body")

    def get_name_path(self) -> str:
        """
        Get the name path of the symbol (e.g. "class/method/inner_function").
        """
        return self._NAME_PATH_SEP.join(self.get_name_path_parts())

    def get_name_path_parts(self) -> list[str]:
        """
        Get the parts of the name path of the symbol (e.g. ["class", "method", "inner_function"]).
        """
        ancestors_within_file = list(self.iter_ancestors(up_to_symbol_kind=SymbolKind.File))
        ancestors_within_file.reverse()
        return [a.name for a in ancestors_within_file] + [self.name]

    def iter_children(self) -> Iterator[Self]:
        for c in self.symbol_root["children"]:
            yield self.__class__(c)

    def iter_ancestors(self, up_to_symbol_kind: SymbolKind | None = None) -> Iterator[Self]:
        """
        Iterate over all ancestors of the symbol, starting with the parent and going up to the root or
        the given symbol kind.

        :param up_to_symbol_kind: if provided, iteration will stop *before* the first ancestor of the given kind.
            A typical use case is to pass `SymbolKind.File` or `SymbolKind.Package`.
        """
        parent = self.get_parent()
        if parent is not None:
            if up_to_symbol_kind is None or parent.symbol_kind != up_to_symbol_kind:
                yield parent
                yield from parent.iter_ancestors(up_to_symbol_kind=up_to_symbol_kind)

    def get_parent(self) -> Self | None:
        parent_root = self.symbol_root.get("parent")
        if parent_root is None:
            return None
        return self.__class__(parent_root)

    def find(
        self,
        name_path: str,
        substring_matching: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list[Self]:
        """
        Find all symbols within the symbol's subtree that match the given `name_path`.
        The matching behavior is determined by the structure of `name_path`, which can
        either be a simple name (e.g. "method") or a name path like "class/method" (relative name path)
        or "/class/method" (absolute name path).

        Key aspects of the name path matching behavior:
        - Trailing slashes in `name_path` play no role and are ignored.
        - The name of the retrieved symbols will match (either exactly or as a substring)
          the last segment of `name_path`, while other segments will restrict the search to symbols that
          have a desired sequence of ancestors.
        - If there is no starting or intermediate slash in `name_path`, there is no
          restriction on the ancestor symbols. For example, passing `method` will match
          against symbols with name paths like `method`, `class/method`, `class/nested_class/method`, etc.
        - If `name_path` contains a `/` but doesn't start with a `/`, the matching is restricted to symbols
          with the same ancestors as the last segment of `name_path`. For example, passing `class/method` will match against
          `class/method` as well as `nested_class/class/method` but not `method`.
        - If `name_path` starts with a `/`, it will be treated as an absolute name path pattern, meaning
          that the first segment of it must match the first segment of the symbol's name path.
          For example, passing `/class` will match only against top-level symbols like `class` but not against `nested_class/class`.
          Passing `/class/method` will match against `class/method` but not `nested_class/class/method` or `method`.

        :param name_path: the name path to match against
        :param substring_matching: whether to use substring matching (as opposed to exact matching)
            of the last segment of `name_path` against the symbol name.
        :param include_kinds: an optional sequence of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
        """
        result = []

        def should_include(s: "LanguageServerSymbol") -> bool:
            if include_kinds is not None and s.symbol_kind not in include_kinds:
                return False
            if exclude_kinds is not None and s.symbol_kind in exclude_kinds:
                return False
            return LanguageServerSymbol.match_name_path(
                name_path=name_path,
                symbol_name_path_parts=s.get_name_path_parts(),
                substring_matching=substring_matching,
            )

        def traverse(s: "LanguageServerSymbol") -> None:
            if should_include(s):
                result.append(s)
            for c in s.iter_children():
                traverse(c)

        traverse(self)
        return result

    def to_dict(
        self,
        kind: bool = False,
        location: bool = False,
        depth: int = 0,
        include_body: bool = False,
        include_children_body: bool = False,
        include_relative_path: bool = True,
    ) -> dict[str, Any]:
        """
        Converts the symbol to a dictionary.

        :param kind: whether to include the kind of the symbol
        :param location: whether to include the location of the symbol
        :param depth: the depth of the symbol
        :param include_body: whether to include the body of the top-level symbol.
        :param include_children_body: whether to also include the body of the children.
            Note that the body of the children is part of the body of the parent symbol,
            so there is usually no need to set this to True unless you want process the output
            and pass the children without passing the parent body to the LM.
        :param include_relative_path: whether to include the relative path of the symbol in the location
            entry. Relative paths of the symbol's children are always excluded.
        :return: a dictionary representation of the symbol
        """
        result: dict[str, Any] = {"name": self.name, "name_path": self.get_name_path()}

        if kind:
            result["kind"] = self.kind

        if location:
            result["location"] = self.location.to_dict(include_relative_path=include_relative_path)
            body_start_line, body_end_line = self.get_body_line_numbers()
            result["body_location"] = {"start_line": body_start_line, "end_line": body_end_line}

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
                        # all children have the same relative path as the parent
                        include_relative_path=False,
                    )
                )
            return children

        if depth > 0:
            result["children"] = add_children(self)

        return result


@dataclass
class ReferenceInLanguageServerSymbol(ToStringMixin):
    """
    Represents the location of a reference to another symbol within a symbol/file.

    The contained symbol is the symbol within which the reference is located,
    not the symbol that is referenced.
    """

    symbol: LanguageServerSymbol
    """
    the symbol within which the reference is located
    """
    line: int
    """
    the line number in which the reference is located (0-based)
    """
    character: int
    """
    the column number in which the reference is located (0-based)
    """

    @classmethod
    def from_lsp_reference(cls, reference: LSPReferenceInSymbol) -> Self:
        return cls(symbol=LanguageServerSymbol(reference.symbol), line=reference.line, character=reference.character)

    def get_relative_path(self) -> str | None:
        return self.symbol.location.relative_path


class LanguageServerSymbolRetriever:
    def __init__(self, lang_server: SolidLanguageServer, agent: Union["SerenaAgent", None] = None) -> None:
        """
        :param lang_server: the language server to use for symbol retrieval as well as editing operations.
        :param agent: the agent to use (only needed for marking files as modified). You can pass None if you don't
            need an agent to be aware of file modifications performed by the symbol manager.
        """
        self._lang_server = lang_server
        self.agent = agent

    def set_language_server(self, lang_server: SolidLanguageServer) -> None:
        """
        Set the language server to use for symbol retrieval and editing operations.
        This is useful if you want to change the language server after initializing the SymbolManager.
        """
        self._lang_server = lang_server

    def get_language_server(self) -> SolidLanguageServer:
        return self._lang_server

    def find_by_name(
        self,
        name_path: str,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        substring_matching: bool = False,
        within_relative_path: str | None = None,
    ) -> list[LanguageServerSymbol]:
        """
        Find all symbols that match the given name. See docstring of `Symbol.find` for more details.
        The only parameter not mentioned there is `within_relative_path`, which can be used to restrict the search
        to symbols within a specific file or directory.
        """
        symbols: list[LanguageServerSymbol] = []
        symbol_roots = self._lang_server.request_full_symbol_tree(within_relative_path=within_relative_path, include_body=include_body)
        for root in symbol_roots:
            symbols.extend(
                LanguageServerSymbol(root).find(
                    name_path, include_kinds=include_kinds, exclude_kinds=exclude_kinds, substring_matching=substring_matching
                )
            )
        return symbols

    def get_document_symbols(self, relative_path: str) -> list[LanguageServerSymbol]:
        symbol_dicts, _roots = self._lang_server.request_document_symbols(relative_path, include_body=False)
        symbols = [LanguageServerSymbol(s) for s in symbol_dicts]
        return symbols

    def find_by_location(self, location: LanguageServerSymbolLocation) -> LanguageServerSymbol | None:
        if location.relative_path is None:
            return None
        symbol_dicts, _roots = self._lang_server.request_document_symbols(location.relative_path, include_body=False)
        for symbol_dict in symbol_dicts:
            symbol = LanguageServerSymbol(symbol_dict)
            if symbol.location == location:
                return symbol
        return None

    def find_referencing_symbols(
        self,
        name_path: str,
        relative_file_path: str,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list[ReferenceInLanguageServerSymbol]:
        """
        Find all symbols that reference the symbol with the given name.
        If multiple symbols fit the name (e.g. for variables that are overwritten), will use the first one.

        :param name_path: the name path of the symbol to find
        :param relative_file_path: the relative path of the file in which the referenced symbol is defined.
        :param include_body: whether to include the body of all symbols in the result.
            Not recommended, as the referencing symbols will often be files, and thus the bodies will be very long.
        :param include_kinds: which kinds of symbols to include in the result.
        :param exclude_kinds: which kinds of symbols to exclude from the result.
        """
        symbol_candidates = self.find_by_name(name_path, substring_matching=False, within_relative_path=relative_file_path)
        if len(symbol_candidates) == 0:
            log.warning(f"No symbol with name {name_path} found in file {relative_file_path}")
            return []
        if len(symbol_candidates) > 1:
            log.error(
                f"Found {len(symbol_candidates)} symbols with name {name_path} in file {relative_file_path}."
                f"May be an overwritten variable, in which case you can ignore this error. Proceeding with the first one. "
                f"Found symbols for {name_path=} in {relative_file_path=}: \n"
                f"{json.dumps([s.location.to_dict() for s in symbol_candidates], indent=2)}"
            )
        symbol = symbol_candidates[0]
        return self.find_referencing_symbols_by_location(
            symbol.location, include_body=include_body, include_kinds=include_kinds, exclude_kinds=exclude_kinds
        )

    def find_referencing_symbols_by_location(
        self,
        symbol_location: LanguageServerSymbolLocation,
        include_body: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list[ReferenceInLanguageServerSymbol]:
        """
        Find all symbols that reference the symbol at the given location.

        :param symbol_location: the location of the symbol for which to find references.
            Does not need to include an end_line, as it is unused in the search.
        :param include_body: whether to include the body of all symbols in the result.
            Not recommended, as the referencing symbols will often be files, and thus the bodies will be very long.
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
        references = self._lang_server.request_referencing_symbols(
            relative_file_path=symbol_location.relative_path,
            line=symbol_location.line,
            column=symbol_location.column,
            include_imports=False,
            include_self=False,
            include_body=include_body,
            include_file_symbols=True,
        )

        if include_kinds is not None:
            references = [s for s in references if s.symbol["kind"] in include_kinds]

        if exclude_kinds is not None:
            references = [s for s in references if s.symbol["kind"] not in exclude_kinds]

        return [ReferenceInLanguageServerSymbol.from_lsp_reference(r) for r in references]

    @dataclass
    class SymbolOverviewElement:
        name_path: str
        kind: int

        @classmethod
        def from_symbol(cls, symbol: LanguageServerSymbol) -> Self:
            return cls(name_path=symbol.get_name_path(), kind=int(symbol.symbol_kind))

    def get_symbol_overview(self, relative_path: str) -> dict[str, list[SymbolOverviewElement]]:
        path_to_unified_symbols = self._lang_server.request_overview(relative_path)
        result = {}
        for file_path, unified_symbols in path_to_unified_symbols.items():
            # TODO: maybe include not just top-level symbols? We could filter by kind to exclude variables
            #  The language server methods would need to be adjusted for this.
            result[file_path] = [self.SymbolOverviewElement.from_symbol(LanguageServerSymbol(s)) for s in unified_symbols]
        return result


class JetBrainsSymbol(Symbol):
    class SymbolDict(TypedDict):
        name_path: str
        relative_path: str
        type: str
        text_range: NotRequired[dict]
        body: NotRequired[str]
        children: NotRequired[list["JetBrainsSymbol.SymbolDict"]]

    def __init__(self, symbol_dict: SymbolDict, project: Project) -> None:
        """
        :param symbol_dict: dictionary as returned by the JetBrains plugin client.
        """
        self._project = project
        self._dict = symbol_dict
        self._cached_file_content: str | None = None
        self._cached_body_start_position: PositionInFile | None = None
        self._cached_body_end_position: PositionInFile | None = None

    def _tostring_includes(self) -> list[str]:
        return []

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return dict(name_path=self.get_name_path(), relative_path=self.get_relative_path(), type=self._dict["type"])

    def get_name_path(self) -> str:
        return self._dict["name_path"]

    def get_relative_path(self) -> str:
        return self._dict["relative_path"]

    def get_file_content(self) -> str:
        if self._cached_file_content is None:
            path = os.path.join(self._project.project_root, self.get_relative_path())
            with open(path, encoding=self._project.project_config.encoding) as f:
                self._cached_file_content = f.read()
        return self._cached_file_content

    def is_position_in_file_available(self) -> bool:
        return "text_range" in self._dict

    def get_body_start_position(self) -> PositionInFile | None:
        if not self.is_position_in_file_available():
            return None
        if self._cached_body_start_position is None:
            pos = self._dict["text_range"]["start_pos"]
            line, col = pos["line"], pos["col"]
            self._cached_body_start_position = PositionInFile(line=line, col=col)
        return self._cached_body_start_position

    def get_body_end_position(self) -> PositionInFile | None:
        if not self.is_position_in_file_available():
            return None
        if self._cached_body_end_position is None:
            pos = self._dict["text_range"]["end_pos"]
            line, col = pos["line"], pos["col"]
            self._cached_body_end_position = PositionInFile(line=line, col=col)
        return self._cached_body_end_position

    def is_neighbouring_definition_separated_by_empty_line(self) -> bool:
        # NOTE: Symbol types cannot really be differentiated, because types are not handled in a language-agnostic way.
        return False
