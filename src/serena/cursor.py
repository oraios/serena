"""
Cursor-based code navigation for Serena.

Provides a stateful cursor that can be positioned on a symbol and moved along LSP graph edges
(contains, references, calls, type hierarchy) for incremental exploration.
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum

from serena.project import Project
from serena.symbol import LanguageServerSymbol, LanguageServerSymbolLocation, LanguageServerSymbolRetriever
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils
from solidlsp.lsp_protocol_handler.lsp_types import (
    CallHierarchyItem,
    SymbolKind,
    TypeHierarchyItem,
)

log = logging.getLogger(__name__)


class EdgeType(Enum):
    """Types of edges available for cursor navigation."""

    CONTAINS = "contains"
    REFERENCES = "references"
    REFERENCED_BY = "referenced-by"
    CALLS = "calls"
    CALLED_BY = "called-by"
    INHERITS = "inherits"
    INHERITED_BY = "inherited-by"


ALL_EDGE_TYPES = frozenset(EdgeType)

# Edge types that are enabled by default (the most commonly useful ones)
DEFAULT_EDGE_TYPES = frozenset(
    {
        EdgeType.CONTAINS,
        EdgeType.REFERENCES,
        EdgeType.REFERENCED_BY,
        EdgeType.CALLS,
        EdgeType.CALLED_BY,
        EdgeType.INHERITS,
        EdgeType.INHERITED_BY,
    }
)


@dataclass
class NeighborSymbol:
    """A symbol reachable from the current cursor position via a specific edge type."""

    name: str
    kind: str
    relative_path: str | None
    line: int | None
    column: int | None
    edge_type: EdgeType
    detail: str | None = None

    @property
    def location_str(self) -> str:
        if self.relative_path and self.line is not None:
            return f"{self.relative_path}:{self.line + 1}"
        elif self.relative_path:
            return self.relative_path
        return "?"

    def format_compact(self) -> str:
        parts = [self.name]
        if self.kind:
            parts.append(f"({self.kind})")
        parts.append(f"[{self.location_str}]")
        if self.detail:
            parts.append(f"— {self.detail}")
        return " ".join(parts)


@dataclass
class CursorState:
    """The state of a single navigation cursor."""

    cursor_id: str
    current_symbol: LanguageServerSymbol
    current_location: LanguageServerSymbolLocation
    trail: list[LanguageServerSymbolLocation] = field(default_factory=list)
    active_edge_types: frozenset[EdgeType] = DEFAULT_EDGE_TYPES
    include_body: bool = False

    def record_move(self, new_symbol: LanguageServerSymbol, new_location: LanguageServerSymbolLocation) -> None:
        """Record moving the cursor to a new symbol."""
        self.trail.append(self.current_location)
        self.current_symbol = new_symbol
        self.current_location = new_location


class CursorManager:
    """
    Manages cursor state and resolves LSP graph edges for navigation.

    Each cursor is identified by a string ID and tracks its current symbol,
    trail of visited symbols, and configured edge types.
    """

    def __init__(self, project: Project) -> None:
        self._project = project
        self._cursors: dict[str, CursorState] = {}
        self._next_cursor_id = 1

    @property
    def _retriever(self) -> LanguageServerSymbolRetriever:
        return LanguageServerSymbolRetriever(self._project)

    def _generate_cursor_id(self) -> str:
        cursor_id = f"c{self._next_cursor_id}"
        self._next_cursor_id += 1
        return cursor_id

    def get_cursor(self, cursor_id: str) -> CursorState:
        if cursor_id not in self._cursors:
            raise ValueError(f"No cursor with id '{cursor_id}'. Active cursors: {list(self._cursors.keys())}")
        return self._cursors[cursor_id]

    def list_cursors(self) -> list[str]:
        return list(self._cursors.keys())

    def start_cursor(
        self,
        name_path: str,
        relative_path: str | None = None,
        cursor_id: str | None = None,
    ) -> tuple[str, CursorState]:
        """
        Start a new cursor at a symbol identified by name_path.

        :param name_path: the name path of the symbol (e.g. "MyClass/my_method")
        :param relative_path: optional file path to narrow the search
        :param cursor_id: optional explicit cursor ID; auto-generated if None
        :return: tuple of (cursor_id, cursor_state)
        """
        retriever = self._retriever
        symbol = retriever.find_unique(name_path, within_relative_path=relative_path)
        location = symbol.location

        if cursor_id is None:
            cursor_id = self._generate_cursor_id()
        elif cursor_id in self._cursors:
            raise ValueError(
                f"Cursor '{cursor_id}' already exists. Close it first or use a different ID. "
                f"Active cursors: {list(self._cursors.keys())}"
            )

        state = CursorState(
            cursor_id=cursor_id,
            current_symbol=symbol,
            current_location=location,
        )
        self._cursors[cursor_id] = state
        return cursor_id, state

    def move_cursor(
        self,
        cursor_id: str,
        target_name: str,
        target_relative_path: str | None = None,
    ) -> CursorState:
        """
        Move a cursor to a neighboring symbol by name.

        The target must be reachable from the current position via one of the active edge types.
        If target_relative_path is provided, it narrows the match.

        :param cursor_id: the cursor to move
        :param target_name: name (or name_path) of the target symbol
        :param target_relative_path: optional file path to disambiguate
        :return: updated cursor state
        """
        state = self.get_cursor(cursor_id)

        # First, try to find the target among current neighbors
        neighbors = self.resolve_neighbors(cursor_id)
        candidates = [n for n in neighbors if target_name in n.name or n.name in target_name]
        if target_relative_path:
            candidates = [n for n in candidates if n.relative_path and target_relative_path in n.relative_path]

        if not candidates:
            # Fall back to global symbol search
            retriever = self._retriever
            symbol = retriever.find_unique(target_name, within_relative_path=target_relative_path)
            location = symbol.location
        elif len(candidates) == 1:
            candidate = candidates[0]
            retriever = self._retriever
            if candidate.relative_path and candidate.line is not None and candidate.column is not None:
                symbol_location = LanguageServerSymbolLocation(
                    relative_path=candidate.relative_path,
                    line=candidate.line,
                    column=candidate.column,
                )
                found = retriever.find_by_location(symbol_location)
                if found:
                    symbol = found
                    location = symbol.location
                else:
                    symbol = retriever.find_unique(candidate.name, within_relative_path=candidate.relative_path)
                    location = symbol.location
            else:
                symbol = retriever.find_unique(candidate.name, within_relative_path=candidate.relative_path)
                location = symbol.location
        else:
            # Multiple candidates — try exact name match
            exact = [n for n in candidates if n.name == target_name]
            if len(exact) == 1:
                candidate = exact[0]
            else:
                names = [f"  {n.name} ({n.kind}) [{n.location_str}]" for n in candidates]
                raise ValueError(f"Ambiguous target '{target_name}'. Candidates:\n" + "\n".join(names))
            retriever = self._retriever
            symbol = retriever.find_unique(candidate.name, within_relative_path=candidate.relative_path)
            location = symbol.location

        state.record_move(symbol, location)
        return state

    def close_cursor(self, cursor_id: str) -> None:
        """Close and remove a cursor."""
        if cursor_id in self._cursors:
            del self._cursors[cursor_id]

    def resolve_neighbors(self, cursor_id: str, depth: int = 1) -> list[NeighborSymbol]:
        """
        Resolve all neighbors of the cursor's current symbol via active edge types.

        :param cursor_id: the cursor whose neighborhood to resolve
        :param depth: traversal depth (currently only 1 is supported)
        :return: list of neighbor symbols with their edge types
        """
        state = self.get_cursor(cursor_id)
        symbol = state.current_symbol
        location = state.current_location
        neighbors: list[NeighborSymbol] = []

        if location.relative_path is None or location.line is None or location.column is None:
            log.warning(f"Cursor {cursor_id} symbol has incomplete location, cannot resolve neighbors")
            return neighbors

        rel_path = location.relative_path
        line = location.line
        col = location.column

        # Contains: children of the current symbol
        if EdgeType.CONTAINS in state.active_edge_types:
            for child in symbol.iter_children():
                neighbors.append(
                    NeighborSymbol(
                        name=child.name,
                        kind=child.symbol_kind_name,
                        relative_path=child.relative_path or rel_path,
                        line=child.line,
                        column=child.column,
                        edge_type=EdgeType.CONTAINS,
                    )
                )

        retriever = self._retriever
        ls = retriever.get_language_server(rel_path)
        failed_edge_types: list[EdgeType] = []

        # References: symbols that THIS symbol references (definitions it points to)
        if EdgeType.REFERENCES in state.active_edge_types:
            try:
                definitions = ls.request_definition(rel_path, line, col)
                for defn in definitions:
                    defn_rel_path = defn.get("relativePath")
                    defn_range = defn.get("range", {})
                    defn_start = defn_range.get("start", {})
                    if defn_rel_path:
                        # Try to get the symbol name at this location
                        defn_line = defn_start.get("line", 0)
                        defn_col = defn_start.get("character", 0)
                        name = self._symbol_name_at(defn_rel_path, defn_line, defn_col)
                        neighbors.append(
                            NeighborSymbol(
                                name=name,
                                kind="",
                                relative_path=defn_rel_path,
                                line=defn_line,
                                column=defn_col,
                                edge_type=EdgeType.REFERENCES,
                            )
                        )
            except SolidLSPException as e:
                log.debug(f"Failed to resolve definitions for cursor: {e}")
                failed_edge_types.append(EdgeType.REFERENCES)

        # Referenced-by: symbols that reference THIS symbol
        if EdgeType.REFERENCED_BY in state.active_edge_types:
            try:
                ref_symbols = ls.request_referencing_symbols(rel_path, line, col, include_imports=False, include_self=False)
                for ref in ref_symbols:
                    ref_sym = ref.symbol
                    ref_rel_path = ref_sym["location"].get("relativePath", "")
                    sel_range = ref_sym.get("selectionRange", {})
                    sel_start = sel_range.get("start", {})
                    neighbors.append(
                        NeighborSymbol(
                            name=ref_sym["name"],
                            kind=SymbolKind(ref_sym["kind"]).name,
                            relative_path=ref_rel_path,
                            line=sel_start.get("line"),
                            column=sel_start.get("character"),
                            edge_type=EdgeType.REFERENCED_BY,
                        )
                    )
            except SolidLSPException as e:
                log.debug(f"Failed to resolve referencing symbols for cursor: {e}")
                failed_edge_types.append(EdgeType.REFERENCED_BY)

        # Calls: symbols that this symbol calls (outgoing calls)
        if EdgeType.CALLS in state.active_edge_types:
            try:
                outgoing = ls.request_call_hierarchy_outgoing(rel_path, line, col)
                for outgoing_call in outgoing:
                    target = outgoing_call["to"]
                    neighbors.append(self._neighbor_from_hierarchy_item(target, EdgeType.CALLS))
            except SolidLSPException as e:
                log.debug(f"Failed to resolve outgoing calls for cursor: {e}")
                failed_edge_types.append(EdgeType.CALLS)

        # Called-by: symbols that call this symbol (incoming calls)
        if EdgeType.CALLED_BY in state.active_edge_types:
            try:
                incoming = ls.request_call_hierarchy_incoming(rel_path, line, col)
                for incoming_call in incoming:
                    caller = incoming_call["from"]
                    neighbors.append(self._neighbor_from_hierarchy_item(caller, EdgeType.CALLED_BY))
            except SolidLSPException as e:
                log.debug(f"Failed to resolve incoming calls for cursor: {e}")
                failed_edge_types.append(EdgeType.CALLED_BY)

        # Inherits: supertypes of the current symbol
        if EdgeType.INHERITS in state.active_edge_types:
            try:
                supertypes = ls.request_type_hierarchy_supertypes(rel_path, line, col)
                for item in supertypes:
                    neighbors.append(self._neighbor_from_type_hierarchy_item(item, EdgeType.INHERITS))
            except SolidLSPException as e:
                log.debug(f"Failed to resolve supertypes for cursor: {e}")
                failed_edge_types.append(EdgeType.INHERITS)

        # Inherited-by: subtypes of the current symbol
        if EdgeType.INHERITED_BY in state.active_edge_types:
            try:
                subtypes = ls.request_type_hierarchy_subtypes(rel_path, line, col)
                for item in subtypes:
                    neighbors.append(self._neighbor_from_type_hierarchy_item(item, EdgeType.INHERITED_BY))
            except SolidLSPException as e:
                log.debug(f"Failed to resolve subtypes for cursor: {e}")
                failed_edge_types.append(EdgeType.INHERITED_BY)

        if failed_edge_types:
            names = ", ".join(e.value for e in failed_edge_types)
            log.warning(f"Cursor {cursor_id}: {len(failed_edge_types)} edge type(s) failed to resolve: {names}")

        return neighbors

    def _symbol_name_at(self, relative_path: str, line: int, col: int) -> str:
        """Try to find the symbol name at a location, falling back to file:line."""
        try:
            retriever = self._retriever
            location = LanguageServerSymbolLocation(relative_path=relative_path, line=line, column=col)
            found = retriever.find_by_location(location)
            if found:
                return found.name
        except Exception as e:
            log.debug(f"Could not resolve symbol name at {relative_path}:{line + 1}: {e}")
        return f"{os.path.basename(relative_path)}:{line + 1}"

    def _neighbor_from_hierarchy_item(
        self,
        item: CallHierarchyItem,
        edge_type: EdgeType,
    ) -> NeighborSymbol:
        """Create a NeighborSymbol from a CallHierarchyItem."""
        uri = item["uri"]
        rel_path = PathUtils.get_relative_path(PathUtils.uri_to_path(uri), self._project.project_root)
        sel_start = item["selectionRange"]["start"]
        try:
            kind_name = SymbolKind(item["kind"]).name
        except ValueError:
            kind_name = str(item["kind"])
        return NeighborSymbol(
            name=item["name"],
            kind=kind_name,
            relative_path=rel_path if rel_path else None,
            line=sel_start.get("line"),
            column=sel_start.get("character"),
            edge_type=edge_type,
            detail=item.get("detail"),
        )

    def _neighbor_from_type_hierarchy_item(
        self,
        item: TypeHierarchyItem,
        edge_type: EdgeType,
    ) -> NeighborSymbol:
        """Create a NeighborSymbol from a TypeHierarchyItem."""
        # TypeHierarchyItem and CallHierarchyItem share the same relevant fields
        return self._neighbor_from_hierarchy_item(item, edge_type)  # type: ignore[arg-type]

    def format_cursor_view(self, cursor_id: str) -> str:
        """
        Format the current cursor position and its neighborhood as structured text.

        :param cursor_id: the cursor to format
        :return: human-readable text representation
        """
        state = self.get_cursor(cursor_id)
        symbol = state.current_symbol
        location = state.current_location

        lines: list[str] = []

        # Header: current symbol
        loc_str = ""
        if location.relative_path and location.line is not None:
            loc_str = f" [{location.relative_path}:{location.line + 1}]"
        lines.append(f"@ {symbol.get_name_path()} ({symbol.symbol_kind_name}){loc_str}")
        lines.append(f"  cursor: {state.cursor_id} | trail: {len(state.trail)} steps")

        # Body (if configured)
        if state.include_body and symbol.body:
            lines.append("")
            lines.append("--- body ---")
            lines.append(symbol.body)
            lines.append("--- end body ---")

        # Neighbors grouped by edge type
        neighbors = self.resolve_neighbors(cursor_id)
        neighbors_by_edge: dict[EdgeType, list[NeighborSymbol]] = {}
        for n in neighbors:
            neighbors_by_edge.setdefault(n.edge_type, []).append(n)

        if neighbors_by_edge:
            lines.append("")
            for edge_type in EdgeType:
                edge_neighbors = neighbors_by_edge.get(edge_type)
                if edge_neighbors:
                    lines.append(f"  {edge_type.value}:")
                    for n in edge_neighbors:
                        lines.append(f"    {n.format_compact()}")
        else:
            lines.append("")
            lines.append("  (no neighbors found)")

        lines.append("")
        lines.append("Use cursor_move to navigate to a neighbor, cursor_look to re-examine.")

        return "\n".join(lines)

    def format_trail(self, cursor_id: str) -> str:
        """Format the cursor's visited trail as text."""
        state = self.get_cursor(cursor_id)
        if not state.trail:
            return f"Cursor {cursor_id}: no trail (at starting position)"

        lines = [f"Cursor {cursor_id} trail ({len(state.trail)} steps):"]
        for i, loc in enumerate(state.trail):
            loc_str = ""
            if loc.relative_path and loc.line is not None:
                loc_str = f"{loc.relative_path}:{loc.line + 1}"
            else:
                loc_str = str(loc.relative_path or "?")
            lines.append(f"  {i + 1}. {loc_str}")

        # Current position
        cur = state.current_location
        if cur.relative_path and cur.line is not None:
            lines.append(f"  -> {cur.relative_path}:{cur.line + 1} (current)")

        return "\n".join(lines)
