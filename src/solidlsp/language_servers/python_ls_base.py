"""
Provides the base class shared by all Python language server implementations.
"""
# SPDX-License-Identifier: MIT

import ast
import logging
import re
import sys
from collections.abc import Hashable
from dataclasses import dataclass

from overrides import override

from solidlsp import ls_types
from solidlsp.ls import DocumentSymbols, LSPFileBuffer, SolidLanguageServer, SymbolBodyFactory

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _SourcePosition:
    """
    Zero-based position in a source file, where the column is a code point offset within the line.
    """

    line: int
    column: int

    def to_lsp_position(self) -> ls_types.Position:
        return ls_types.Position(line=self.line, character=self.column)


@dataclass(frozen=True)
class _SourceRange:
    """
    Range in a source file, from a start position (inclusive) to an end position (exclusive).
    """

    start: _SourcePosition
    end: _SourcePosition

    def to_lsp_range(self) -> ls_types.Range:
        """
        :return: a new LSP range object (with new position objects)
        """
        return ls_types.Range(start=self.start.to_lsp_position(), end=self.end.to_lsp_position())


class _AssignmentStatementIndex:
    """
    Index of the assignment statements in a Python source file, which maps the start position of each
    name bound by such a statement to the range of the entire statement.

    Covered statements are assignments (including chained assignments and tuple unpacking), annotated
    assignments and declarations, and ``type`` alias statements.
    A statement's range ends with the end of its last expression, i.e. it includes multi-line
    expressions and line continuations but excludes trailing comments.
    A source that cannot be parsed by the running Python interpreter results in an empty index.
    """

    _LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")
    """
    the line breaks recognised by the Python tokenizer, to which the line numbers provided by `ast` refer
    """

    def __init__(self, source: str):
        """
        :param source: the source code of the Python file
        """
        self._lines = self._LINE_BREAK_RE.split(source)
        self._statement_ranges: dict[_SourcePosition, _SourceRange] = {}

        # parse the source
        try:
            module = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError) as e:
            log.debug("Python source could not be parsed, assignment statement ranges are unavailable: %s", e)
            return

        # map the start position of each bound name to the range of its statement
        for node in ast.walk(module):
            if not isinstance(node, ast.stmt):
                continue
            bound_names = self._get_bound_names(node)
            if not bound_names:
                continue
            assert node.end_lineno is not None and node.end_col_offset is not None
            statement_range = _SourceRange(
                start=self._to_source_position(node.lineno, node.col_offset),
                end=self._to_source_position(node.end_lineno, node.end_col_offset),
            )
            for name in bound_names:
                self._statement_ranges[self._to_source_position(name.lineno, name.col_offset)] = statement_range

    @classmethod
    def _get_bound_names(cls, statement: ast.stmt) -> list[ast.Name]:
        """
        :param statement: a statement
        :return: the names bound by the statement if it is an assignment statement, otherwise an empty list
        """
        targets: list[ast.expr]
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        elif sys.version_info >= (3, 12) and isinstance(statement, ast.TypeAlias):
            targets = [statement.name]
        else:
            return []
        return [name for target in targets for name in cls._get_names_in_target(target)]

    @classmethod
    def _get_names_in_target(cls, target: ast.expr) -> list[ast.Name]:
        """
        :param target: an assignment target
        :return: the plain names bound by the target, descending into tuple/list unpacking and starred targets;
            attribute and subscript targets bind no names
        """
        if isinstance(target, ast.Name):
            return [target]
        if isinstance(target, ast.Tuple | ast.List):
            return [name for element in target.elts for name in cls._get_names_in_target(element)]
        if isinstance(target, ast.Starred):
            return cls._get_names_in_target(target.value)
        return []

    def _to_source_position(self, lineno: int, utf8_col_offset: int) -> _SourcePosition:
        """
        :param lineno: a one-based line number, as provided by `ast`
        :param utf8_col_offset: a UTF-8 byte offset within the line, as provided by `ast`
        :return: the corresponding source position
        """
        line_index = lineno - 1
        line = self._lines[line_index]
        if line.isascii():
            return _SourcePosition(line_index, utf8_col_offset)
        return _SourcePosition(line_index, len(line.encode("utf-8")[:utf8_col_offset].decode("utf-8", errors="ignore")))

    def find_statement_range(self, name_position: ls_types.Position) -> _SourceRange | None:
        """
        :param name_position: the start position of a name
        :return: the range of the assignment statement binding the name at the given position,
            or None if no assignment statement binds a name at this position
        """
        return self._statement_ranges.get(_SourcePosition(name_position["line"], name_position["character"]))


class PythonLanguageServerBase(SolidLanguageServer):
    """
    Base class for Python language servers, which unifies the body ranges of symbols across implementations.

    The body range of a variable whose definition is an assignment statement covers the entire statement
    (e.g. ``x: Annotated[int, Field(...)] = 1``), regardless of whether the language server reports only
    the name (Pyright, BasedPyright), the statement without a leading ``type`` keyword (Jedi) or the
    entire statement.
    The identifier location of a symbol (its selection range) is unaffected.
    """

    @override
    def _document_symbols_cache_fingerprint(self) -> Hashable | None:
        # the interpreter version determines which sources `ast` can parse (e.g. `type` statements require 3.12+)
        assignment_statement_ranges_version = 1
        return assignment_statement_ranges_version, sys.version_info[:2]

    @override
    def _build_document_symbols_from_raw_symbols(self, relative_file_path: str, file_buffer: LSPFileBuffer) -> DocumentSymbols:
        # IMPORTANT: Update _document_symbols_cache_fingerprint() when changing this method.
        document_symbols = super()._build_document_symbols_from_raw_symbols(relative_file_path, file_buffer=file_buffer)
        if not document_symbols.root_symbols:
            return document_symbols

        assignment_index = _AssignmentStatementIndex(file_buffer.contents)
        body_factory = SymbolBodyFactory(file_buffer)

        # extend ranges recursively, operating on copies so the cached symbols are not mutated;
        # see Gopls._build_document_symbols_from_raw_symbols for why child `parent` back-pointers are left aimed
        # at the original (un-extended) nodes
        def extend_symbol_and_children(symbol: ls_types.UnifiedSymbolInformation) -> ls_types.UnifiedSymbolInformation:
            extended = self._extend_range_to_assignment_statement(symbol, assignment_index, body_factory)
            children = symbol.get("children")
            if children:
                if extended is symbol:
                    extended = symbol.copy()
                extended["children"] = [extend_symbol_and_children(child) for child in children]
            return extended

        return DocumentSymbols([extend_symbol_and_children(symbol) for symbol in document_symbols.root_symbols])

    @staticmethod
    def _extend_range_to_assignment_statement(
        symbol: ls_types.UnifiedSymbolInformation,
        assignment_index: _AssignmentStatementIndex,
        body_factory: SymbolBodyFactory,
    ) -> ls_types.UnifiedSymbolInformation:
        """
        :param symbol: the symbol whose range may be extended
        :param assignment_index: the index of assignment statements in the symbol's file
        :param body_factory: the factory with which to recompute the symbol body
        :return: a copy of the symbol whose range is the range of the assignment statement that binds the symbol's
            name, or the original symbol if its name is not bound by an assignment statement
        """
        statement_range = assignment_index.find_statement_range(symbol["selectionRange"]["start"])
        if statement_range is None:
            return symbol

        # replace both the symbol range and its location range, using new objects, since the selection range
        # may share its range object with them
        extended = symbol.copy()
        if "range" in extended:
            extended["range"] = statement_range.to_lsp_range()
        location = extended["location"].copy()
        location["range"] = statement_range.to_lsp_range()
        extended["location"] = location

        # recompute the body from the new location range; the stale body must be removed first, since the
        # factory returns an existing body as-is
        extended.pop("body", None)
        extended["body"] = body_factory.create_symbol_body(extended)
        return extended
