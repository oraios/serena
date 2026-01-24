import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Self, Union

from sensai.util.string import ToStringMixin

import murena.tools.jetbrains_types as jb
from solidlsp import SolidLanguageServer
from solidlsp.ls import ReferenceInSymbol as LSPReferenceInSymbol
from solidlsp.ls_types import Position, SymbolKind, UnifiedSymbolInformation

from .ls_manager import LanguageServerManager
from .project import Project

if TYPE_CHECKING:
    from .agent import MurenaAgent

log = logging.getLogger(__name__)
NAME_PATH_SEP = "/"


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


class NamePathComponent:
    def __init__(self, name: str, overload_idx: int | None = None) -> None:
        self.name = name
        self.overload_idx = overload_idx

    def __repr__(self) -> str:
        if self.overload_idx is not None:
            return f"{self.name}[{self.overload_idx}]"
        else:
            return self.name


class NamePathMatcher(ToStringMixin):
    """
    Matches name paths of symbols against search patterns.

    A name path is a path in the symbol tree *within a source file*.
    For example, the method `my_method` defined in class `MyClass` would have the name path `MyClass/my_method`.
    If a symbol is overloaded (e.g., in Java), a 0-based index is appended (e.g. "MyClass/my_method[0]") to
    uniquely identify it.

    A matching pattern can be:
     * a simple name (e.g. "method"), which will match any symbol with that name
     * a relative path like "class/method", which will match any symbol with that name path suffix
     * an absolute name path "/class/method" (absolute name path), which requires an exact match of the full name path within the source file.
    Append an index `[i]` to match a specific overload only, e.g. "MyClass/my_method[1]".
    """

    class PatternComponent(NamePathComponent):
        @classmethod
        def from_string(cls, component_str: str) -> Self:
            overload_idx = None
            if component_str.endswith("]") and "[" in component_str:
                bracket_idx = component_str.rfind("[")
                index_part = component_str[bracket_idx + 1 : -1]
                if index_part.isdigit():
                    component_str = component_str[:bracket_idx]
                    overload_idx = int(index_part)
            return cls(name=component_str, overload_idx=overload_idx)

        def matches(self, name_path_component: NamePathComponent, substring_matching: bool) -> bool:
            if substring_matching:
                if self.name not in name_path_component.name:
                    return False
            else:
                if self.name != name_path_component.name:
                    return False
            if self.overload_idx is not None and self.overload_idx != name_path_component.overload_idx:
                return False
            return True

    def __init__(self, name_path_pattern: str, substring_matching: bool) -> None:
        """
        :param name_path_pattern: the name path expression to match against
        :param substring_matching: whether to use substring matching for the last segment
        """
        assert name_path_pattern, "name_path must not be empty"
        self._expr = name_path_pattern
        self._substring_matching = substring_matching
        self._is_absolute_pattern = name_path_pattern.startswith(NAME_PATH_SEP)
        self._components = [
            self.PatternComponent.from_string(x) for x in name_path_pattern.lstrip(NAME_PATH_SEP).rstrip(NAME_PATH_SEP).split(NAME_PATH_SEP)
        ]

    def _tostring_includes(self) -> list[str]:
        return ["_expr"]

    def matches_ls_symbol(self, symbol: "LanguageServerSymbol") -> bool:
        return self.matches_reversed_components(symbol.iter_name_path_components_reversed())

    def matches_reversed_components(self, components_reversed: Iterator[NamePathComponent]) -> bool:
        for i, pattern_component in enumerate(reversed(self._components)):
            try:
                symbol_component = next(components_reversed)
            except StopIteration:
                return False
            use_substring_matching = self._substring_matching and (i == 0)
            if not pattern_component.matches(symbol_component, use_substring_matching):
                return False
        if self._is_absolute_pattern:
            # ensure that there are no more components in the symbol
            try:
                next(components_reversed)
                return False
            except StopIteration:
                pass
        return True


class LanguageServerSymbol(Symbol, ToStringMixin):
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

    def is_low_level(self) -> bool:
        """
        :return: whether the symbol is a low-level symbol (variable, constant, etc.), which typically represents data
            rather than structure and therefore is not relevant in a high-level overview of the code.
        """
        return self.symbol_kind >= SymbolKind.Variable.value

    @property
    def overload_idx(self) -> int | None:
        return self.symbol_root.get("overload_idx")

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
        body = self.symbol_root.get("body")
        if body is None:
            return None
        else:
            return body.get_text()

    def get_name_path(self) -> str:
        """
        Get the name path of the symbol, e.g. "class/method/inner_function" or
        "class/method[1]" (overloaded method with identifying index).
        """
        name_path = NAME_PATH_SEP.join(reversed([str(x) for x in self.iter_name_path_components_reversed()]))
        return name_path

    def iter_name_path_components_reversed(self) -> Iterator[NamePathComponent]:
        yield NamePathComponent(self.name, self.overload_idx)
        for ancestor in self.iter_ancestors(up_to_symbol_kind=SymbolKind.File):
            yield NamePathComponent(ancestor.name, ancestor.overload_idx)

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
        name_path_pattern: str,
        substring_matching: bool = False,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
    ) -> list[Self]:
        """
        Find all symbols within the symbol's subtree that match the given name path pattern.

        :param name_path_pattern: the name path pattern to match against (see class :class:`NamePathMatcher` for details)
        :param substring_matching: whether to use substring matching (as opposed to exact matching)
            of the last segment of `name_path` against the symbol name.
        :param include_kinds: an optional sequence of ints representing the LSP symbol kind.
            If provided, only symbols of the given kinds will be included in the result.
        :param exclude_kinds: If provided, symbols of the given kinds will be excluded from the result.
        """
        result = []
        name_path_matcher = NamePathMatcher(name_path_pattern, substring_matching)

        def should_include(s: "LanguageServerSymbol") -> bool:
            if include_kinds is not None and s.symbol_kind not in include_kinds:
                return False
            if exclude_kinds is not None and s.symbol_kind in exclude_kinds:
                return False
            return name_path_matcher.matches_ls_symbol(s)

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
        child_inclusion_predicate: Callable[[Self], bool] | None = None,
    ) -> dict[str, Any]:
        """
        Converts the symbol to a dictionary.

        :param kind: whether to include the kind of the symbol
        :param location: whether to include the location of the symbol
        :param depth: the depth up to which to include child symbols (0 = do not include children)
        :param include_body: whether to include the body of the top-level symbol.
        :param include_children_body: whether to also include the body of the children.
            Note that the body of the children is part of the body of the parent symbol,
            so there is usually no need to set this to True unless you want process the output
            and pass the children without passing the parent body to the LM.
        :param include_relative_path: whether to include the relative path of the symbol in the location
            entry. Relative paths of the symbol's children are always excluded.
        :param child_inclusion_predicate: an optional predicate that decides whether a child symbol
            should be included.
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
            body = self.body
            if body is None:
                log.warning("Requested body for symbol, but it is not present. The symbol might have been loaded with include_body=False.")
            result["body"] = body

        if child_inclusion_predicate is None:
            child_inclusion_predicate = lambda s: True

        def included_children(s: Self) -> list[dict[str, Any]]:
            children = []
            for c in s.iter_children():
                if not child_inclusion_predicate(c):
                    continue
                children.append(
                    c.to_dict(
                        kind=kind,
                        location=location,
                        depth=depth - 1,
                        child_inclusion_predicate=child_inclusion_predicate,
                        include_body=include_children_body,
                        include_children_body=include_children_body,
                        # all children have the same relative path as the parent
                        include_relative_path=False,
                    )
                )
            return children

        if depth > 0:
            children = included_children(self)
            if len(children) > 0:
                result["children"] = included_children(self)

        return result

    def to_dict_compact(
        self,
        kind: bool = False,
        location: bool = False,
        depth: int = 0,
        include_body: bool = False,
        include_children_body: bool = False,
        include_relative_path: bool = True,
        child_inclusion_predicate: Callable[[Self], bool] | None = None,
    ) -> dict[str, Any]:
        """
        Converts the symbol to a compact dictionary with abbreviated field names.
        This reduces token consumption by ~40% compared to to_dict().

        Field name mappings:
        - name_path → np
        - kind → k
        - location → loc
        - body_location → bloc
        - body → b
        - children → ch

        Omits redundant fields: name, body_location (redundant with location)

        Parameters are the same as to_dict().
        """
        result: dict[str, Any] = {"np": self.get_name_path()}

        if kind:
            result["k"] = self.kind

        if location:
            loc_dict = self.location.to_dict(include_relative_path=include_relative_path)
            # Compact location fields: relative_path → rp, line → l, column → c
            compact_loc = {}
            if "relative_path" in loc_dict:
                compact_loc["rp"] = loc_dict["relative_path"]
            if "line" in loc_dict:
                compact_loc["l"] = loc_dict["line"]
            if "column" in loc_dict:
                compact_loc["c"] = loc_dict["column"]
            result["loc"] = compact_loc

            # Only include body_location if it's different from location (for methods/classes with multi-line definitions)
            body_start_line, body_end_line = self.get_body_line_numbers()
            if body_start_line != self.line or body_end_line != self.line:
                result["bloc"] = {"sl": body_start_line, "el": body_end_line}

        if include_body:
            body = self.body
            if body is None:
                log.warning("Requested body for symbol, but it is not present. The symbol might have been loaded with include_body=False.")
            result["b"] = body

        if child_inclusion_predicate is None:
            child_inclusion_predicate = lambda s: True

        def included_children(s: Self) -> list[dict[str, Any]]:
            children = []
            for c in s.iter_children():
                if not child_inclusion_predicate(c):
                    continue
                children.append(
                    c.to_dict_compact(
                        kind=kind,
                        location=location,
                        depth=depth - 1,
                        child_inclusion_predicate=child_inclusion_predicate,
                        include_body=include_children_body,
                        include_children_body=include_children_body,
                        # all children have the same relative path as the parent
                        include_relative_path=False,
                    )
                )
            return children

        if depth > 0:
            children = included_children(self)
            if len(children) > 0:
                result["ch"] = children

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
    def __init__(self, ls: SolidLanguageServer | LanguageServerManager, agent: Union["MurenaAgent", None] = None) -> None:
        """
        :param ls: the language server or language server manager to use for symbol retrieval and editing operations.
        :param agent: the agent to use (only needed for marking files as modified). You can pass None if you don't
            need an agent to be aware of file modifications performed by the symbol manager.
        """
        if isinstance(ls, SolidLanguageServer):
            ls_manager = LanguageServerManager({ls.language: ls})
        else:
            ls_manager = ls
        assert isinstance(ls_manager, LanguageServerManager)
        self._ls_manager: LanguageServerManager = ls_manager
        self.agent = agent

    def _request_info(self, relative_file_path: str, line: int, column: int) -> str | None:
        """Retrieves information (in a sanitized format) about the symbol at the desired location,
        typically containing the docstring and signature.

        Returns None if no information is available.
        """
        lang_server = self.get_language_server(relative_file_path)
        hover_info = lang_server.request_hover(relative_file_path=relative_file_path, line=line, column=column)
        if hover_info is None:
            return None
        contents = hover_info["contents"]
        # Handle various response formats
        if isinstance(contents, list):
            # Array format: extract all parts and join them
            stripped_parts = []
            for part in contents:
                if isinstance(part, str) and (stripped_part := part.strip()):
                    stripped_parts.append(stripped_part)
                else:
                    # should be a dict with "value" key
                    stripped_parts.append(part["value"].strip())  # type: ignore
            return "\n".join(stripped_parts) if stripped_parts else None
        if isinstance(contents, dict) and (stripped_contents := contents.get("value", "").strip()):
            return stripped_contents
        if isinstance(contents, str) and (stripped_contents := contents.strip()):
            return stripped_contents
        return None

    def request_info_for_symbol(self, symbol: LanguageServerSymbol) -> str | None:
        if None in [symbol.relative_path, symbol.line, symbol.column]:
            return None
        return self._request_info(relative_file_path=symbol.relative_path, line=symbol.line, column=symbol.column)  # type: ignore[arg-type]

    def get_root_path(self) -> str:
        return self._ls_manager.get_root_path()

    def get_language_server(self, relative_path: str) -> SolidLanguageServer:
        return self._ls_manager.get_language_server(relative_path)

    def find(
        self,
        name_path_pattern: str,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        substring_matching: bool = False,
        within_relative_path: str | None = None,
    ) -> list[LanguageServerSymbol]:
        """
        Finds all symbols that match the given name path pattern (see class :class:`NamePathMatcher` for details),
        optionally limited to a specific file and filtered by kind.
        """
        symbols: list[LanguageServerSymbol] = []
        for lang_server in self._ls_manager.iter_language_servers():
            symbol_roots = lang_server.request_full_symbol_tree(within_relative_path=within_relative_path)
            for root in symbol_roots:
                symbols.extend(
                    LanguageServerSymbol(root).find(
                        name_path_pattern, include_kinds=include_kinds, exclude_kinds=exclude_kinds, substring_matching=substring_matching
                    )
                )
        return symbols

    def find_unique(
        self,
        name_path_pattern: str,
        include_kinds: Sequence[SymbolKind] | None = None,
        exclude_kinds: Sequence[SymbolKind] | None = None,
        substring_matching: bool = False,
        within_relative_path: str | None = None,
    ) -> LanguageServerSymbol:
        symbol_candidates = self.find(
            name_path_pattern,
            include_kinds=include_kinds,
            exclude_kinds=exclude_kinds,
            substring_matching=substring_matching,
            within_relative_path=within_relative_path,
        )
        if len(symbol_candidates) == 1:
            return symbol_candidates[0]
        elif len(symbol_candidates) == 0:
            raise ValueError(f"No symbol matching '{name_path_pattern}' found")
        else:
            # There are multiple candidates.
            # If only one of the candidates has the given pattern as its exact name path, return that one
            exact_matches = [s for s in symbol_candidates if s.get_name_path() == name_path_pattern]
            if len(exact_matches) == 1:
                return exact_matches[0]
            # otherwise, raise an error
            include_rel_path = within_relative_path is not None
            raise ValueError(
                f"Found multiple {len(symbol_candidates)} symbols matching '{name_path_pattern}'. "
                "They are: \n"
                + json.dumps([s.to_dict(kind=True, include_relative_path=include_rel_path) for s in symbol_candidates], indent=2)
            )

    def find_by_location(self, location: LanguageServerSymbolLocation) -> LanguageServerSymbol | None:
        if location.relative_path is None:
            return None
        lang_server = self.get_language_server(location.relative_path)
        document_symbols = lang_server.request_document_symbols(location.relative_path)
        for symbol_dict in document_symbols.iter_symbols():
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
        Find all symbols that reference the specified symbol, which is assumed to be unique.

        :param name_path: the name path of the symbol to find. (While this can be a matching pattern, it should
            usually be the full path to ensure uniqueness.)
        :param relative_file_path: the relative path of the file in which the referenced symbol is defined.
        :param include_body: whether to include the body of all symbols in the result.
            Not recommended, as the referencing symbols will often be files, and thus the bodies will be very long.
        :param include_kinds: which kinds of symbols to include in the result.
        :param exclude_kinds: which kinds of symbols to exclude from the result.
        """
        symbol = self.find_unique(name_path, substring_matching=False, within_relative_path=relative_file_path)
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
        lang_server = self.get_language_server(symbol_location.relative_path)
        references = lang_server.request_referencing_symbols(
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

    def get_symbol_overview(self, relative_path: str, depth: int = 0) -> dict[str, list[dict]]:
        """
        :param relative_path: the path of the file or directory for which to get the symbol overview
        :param depth: the depth up to which to include child symbols (0 = only top-level symbols)
        :return: a mapping from file paths to lists of symbol dictionaries.
            For the case where a file is passed, the mapping will contain a single entry.
        """
        lang_server = self.get_language_server(relative_path)
        path_to_unified_symbols = lang_server.request_overview(relative_path)

        def child_inclusion_predicate(s: LanguageServerSymbol) -> bool:
            return not s.is_low_level()

        result = {}
        for file_path, unified_symbols in path_to_unified_symbols.items():
            symbols_in_file = []
            for us in unified_symbols:
                symbol = LanguageServerSymbol(us)
                symbols_in_file.append(
                    symbol.to_dict(
                        depth=depth,
                        kind=True,
                        include_relative_path=False,
                        location=False,
                        child_inclusion_predicate=child_inclusion_predicate,
                    )
                )
            result[file_path] = symbols_in_file

        return result


class JetBrainsSymbol(Symbol):
    def __init__(self, symbol_dict: jb.SymbolDTO, project: Project) -> None:
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
