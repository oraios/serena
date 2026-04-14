"""
Unit tests for cursor-based code navigation (CursorManager, CursorState, EdgeType, NeighborSymbol).

These tests mock the LSP layer to test cursor logic in isolation.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from serena.cursor import (
    ALL_EDGE_TYPES,
    DEFAULT_EDGE_TYPES,
    CursorManager,
    CursorState,
    EdgeType,
    NeighborSymbol,
)
from serena.symbol import LanguageServerSymbol, LanguageServerSymbolLocation
from solidlsp.ls_exceptions import SolidLSPException
from solidlsp.ls_utils import PathUtils

# ── Cross-platform test root ────────────────────────────────────────────
# Use the real temp directory so that file URIs resolve on all platforms
# (on Windows, /tmp is a UNC path on a different mount than D:).
_TEST_PROJECT_ROOT = os.path.join(tempfile.gettempdir(), "test_project")

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_file_uri(relative_path: str) -> str:
    """Build a file:// URI for a path relative to the test project root."""
    return PathUtils.path_to_uri(os.path.join(_TEST_PROJECT_ROOT, relative_path))


def _make_symbol(
    name: str = "MyClass",
    kind_name: str = "Class",
    rel_path: str | None = "src/module.py",
    line: int | None = 10,
    col: int | None = 0,
    name_path: str | None = None,
    children: list | None = None,
    body: str | None = None,
) -> MagicMock:
    """Create a minimal mock LanguageServerSymbol."""
    sym = MagicMock(spec=LanguageServerSymbol)
    sym.name = name
    sym.symbol_kind_name = kind_name
    sym.relative_path = rel_path
    sym.line = line
    sym.column = col
    sym.body = body
    sym.get_name_path.return_value = name_path or name
    sym.location = LanguageServerSymbolLocation(relative_path=rel_path, line=line, column=col)

    child_mocks = []
    for c in children or []:
        child_mocks.append(_make_symbol(**c))
    sym.iter_children.return_value = iter(child_mocks)
    return sym


def _make_project(project_root: str = _TEST_PROJECT_ROOT) -> MagicMock:
    """Create a minimal mock Project."""
    project = MagicMock()
    project.project_root = project_root
    return project


def _make_manager(project_root: str = _TEST_PROJECT_ROOT) -> CursorManager:
    return CursorManager(_make_project(project_root))


# ── EdgeType / NeighborSymbol ────────────────────────────────────────────


class TestEdgeType:
    def test_all_edge_types_contains_all_members(self):
        assert frozenset(EdgeType) == ALL_EDGE_TYPES

    def test_default_edge_types_subset_of_all(self):
        assert DEFAULT_EDGE_TYPES <= ALL_EDGE_TYPES

    def test_edge_type_values(self):
        assert EdgeType.CONTAINS.value == "contains"
        assert EdgeType.REFERENCES.value == "references"
        assert EdgeType.REFERENCED_BY.value == "referenced-by"
        assert EdgeType.CALLS.value == "calls"
        assert EdgeType.CALLED_BY.value == "called-by"
        assert EdgeType.INHERITS.value == "inherits"
        assert EdgeType.INHERITED_BY.value == "inherited-by"

    def test_seven_edge_types(self):
        assert len(EdgeType) == 7


class TestNeighborSymbol:
    def test_location_str_with_path_and_line(self):
        n = NeighborSymbol(name="foo", kind="Function", relative_path="src/a.py", line=9, column=4, edge_type=EdgeType.CONTAINS)
        assert n.location_str == "src/a.py:10"  # 0-indexed line displayed as 1-indexed

    def test_location_str_with_path_no_line(self):
        n = NeighborSymbol(name="foo", kind="Module", relative_path="src/a.py", line=None, column=None, edge_type=EdgeType.CONTAINS)
        assert n.location_str == "src/a.py"

    def test_location_str_without_path(self):
        n = NeighborSymbol(name="foo", kind="Function", relative_path=None, line=None, column=None, edge_type=EdgeType.REFERENCES)
        assert n.location_str == "?"

    def test_format_compact_basic(self):
        n = NeighborSymbol(name="bar", kind="Method", relative_path="x.py", line=5, column=0, edge_type=EdgeType.CALLS)
        formatted = n.format_compact()
        assert "bar" in formatted
        assert "(Method)" in formatted
        assert "[x.py:6]" in formatted

    def test_format_compact_with_detail(self):
        n = NeighborSymbol(
            name="bar", kind="Method", relative_path="x.py", line=5, column=0, edge_type=EdgeType.CALLS, detail="returns int"
        )
        assert "— returns int" in n.format_compact()


# ── CursorState ──────────────────────────────────────────────────────────


class TestCursorState:
    def test_initial_state_has_empty_trail(self):
        sym = _make_symbol()
        loc = sym.location
        state = CursorState(cursor_id="c1", current_symbol=sym, current_location=loc)
        assert state.trail == []
        assert state.cursor_id == "c1"
        assert state.active_edge_types == DEFAULT_EDGE_TYPES
        assert state.include_body is False

    def test_record_move_appends_to_trail(self):
        sym1 = _make_symbol(name="A", line=1)
        sym2 = _make_symbol(name="B", line=20)
        state = CursorState(cursor_id="c1", current_symbol=sym1, current_location=sym1.location)

        state.record_move(sym2, sym2.location)

        assert len(state.trail) == 1
        assert state.trail[0].line == 1
        assert state.current_symbol is sym2
        assert state.current_location is sym2.location

    def test_record_multiple_moves_builds_trail(self):
        syms = [_make_symbol(name=f"S{i}", line=i * 10) for i in range(4)]
        state = CursorState(cursor_id="c1", current_symbol=syms[0], current_location=syms[0].location)

        for s in syms[1:]:
            state.record_move(s, s.location)

        assert len(state.trail) == 3
        assert state.current_symbol is syms[3]

    def test_custom_edge_types(self):
        sym = _make_symbol()
        edges = frozenset({EdgeType.CONTAINS, EdgeType.CALLS})
        state = CursorState(cursor_id="c1", current_symbol=sym, current_location=sym.location, active_edge_types=edges)
        assert state.active_edge_types == edges


# ── CursorManager: start / get / list / close ────────────────────────────


class TestCursorManagerLifecycle:
    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_start_cursor_auto_id(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid, state = manager.start_cursor("MyClass")

        assert cid == "c1"
        assert state.cursor_id == "c1"
        assert state.current_symbol is sym
        assert state.trail == []
        mock_retriever_cls.return_value.find_unique.assert_called_once_with("MyClass", within_relative_path=None)

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_start_cursor_explicit_id(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid, state = manager.start_cursor("MyClass", cursor_id="custom")

        assert cid == "custom"
        assert state.cursor_id == "custom"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_start_cursor_with_relative_path(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        manager.start_cursor("MyClass", relative_path="src/module.py")

        mock_retriever_cls.return_value.find_unique.assert_called_once_with("MyClass", within_relative_path="src/module.py")

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_auto_id_increments(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid1, _ = manager.start_cursor("A")
        cid2, _ = manager.start_cursor("B")
        cid3, _ = manager.start_cursor("C")

        assert cid1 == "c1"
        assert cid2 == "c2"
        assert cid3 == "c3"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_get_cursor_success(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid, _ = manager.start_cursor("MyClass")
        state = manager.get_cursor(cid)

        assert state.cursor_id == cid

    def test_get_cursor_nonexistent_raises(self):
        manager = _make_manager()
        with pytest.raises(ValueError, match="No cursor with id"):
            manager.get_cursor("nonexistent")

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_list_cursors(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        assert manager.list_cursors() == []

        manager.start_cursor("A")
        manager.start_cursor("B")

        assert sorted(manager.list_cursors()) == ["c1", "c2"]

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_close_cursor(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid, _ = manager.start_cursor("A")
        assert cid in manager.list_cursors()

        manager.close_cursor(cid)
        assert cid not in manager.list_cursors()

    def test_close_nonexistent_cursor_is_noop(self):
        manager = _make_manager()
        manager.close_cursor("nope")  # should not raise


# ── CursorManager: move ──────────────────────────────────────────────────


class TestCursorManagerMove:
    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_move_cursor_to_neighbor(self, mock_retriever_cls):
        """Move cursor to a symbol by name, falling back to global lookup when not in neighbors."""
        manager = _make_manager()

        sym_a = _make_symbol(name="ClassA", line=10)
        sym_b = _make_symbol(name="method_b", line=20)
        mock_retriever = mock_retriever_cls.return_value
        mock_retriever.find_unique.return_value = sym_a

        cid, _ = manager.start_cursor("ClassA")

        # Now set up for move: find_unique returns sym_b for the fallback path
        mock_retriever.find_unique.return_value = sym_b

        state = manager.move_cursor(cid, "method_b")

        assert state.current_symbol is sym_b
        assert len(state.trail) == 1
        assert state.trail[0].line == 10  # original position

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_move_cursor_records_trail(self, mock_retriever_cls):
        """Each move appends the previous location to trail."""
        manager = _make_manager()
        mock_retriever = mock_retriever_cls.return_value

        syms = [_make_symbol(name=f"S{i}", line=i * 10) for i in range(4)]
        mock_retriever.find_unique.side_effect = syms

        cid, _ = manager.start_cursor("S0")
        manager.move_cursor(cid, "S1")
        manager.move_cursor(cid, "S2")
        manager.move_cursor(cid, "S3")

        state = manager.get_cursor(cid)
        assert len(state.trail) == 3
        assert state.current_symbol is syms[3]


# ── CursorManager: resolve_neighbors (mocked LSP) ───────────────────────


class TestResolveNeighbors:
    def _setup_manager_with_cursor(self, mock_retriever_cls, sym=None, children=None):
        """Helper that creates a manager, starts a cursor, and returns (manager, cursor_id, mock_ls)."""
        manager = _make_manager()
        if sym is None:
            child_specs = children or []
            sym = _make_symbol(name="MyClass", line=10, col=0, children=child_specs)
        mock_retriever = mock_retriever_cls.return_value
        mock_retriever.find_unique.return_value = sym

        mock_ls = MagicMock()
        mock_retriever.get_language_server.return_value = mock_ls

        # Default: all LSP methods return empty
        mock_ls.request_definition.return_value = []
        mock_ls.request_referencing_symbols.return_value = []
        mock_ls.request_call_hierarchy_outgoing.return_value = []
        mock_ls.request_call_hierarchy_incoming.return_value = []
        mock_ls.request_type_hierarchy_supertypes.return_value = []
        mock_ls.request_type_hierarchy_subtypes.return_value = []

        cid, _ = manager.start_cursor("MyClass")
        return manager, cid, mock_ls

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_contains_edge_resolves_children(self, mock_retriever_cls):
        children = [
            {"name": "method_a", "kind_name": "Method", "line": 12, "col": 4},
            {"name": "method_b", "kind_name": "Method", "line": 20, "col": 4},
        ]
        manager, cid, _ = self._setup_manager_with_cursor(mock_retriever_cls, children=children)

        neighbors = manager.resolve_neighbors(cid)
        contains_neighbors = [n for n in neighbors if n.edge_type == EdgeType.CONTAINS]

        assert len(contains_neighbors) == 2
        names = {n.name for n in contains_neighbors}
        assert names == {"method_a", "method_b"}

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_references_edge(self, mock_retriever_cls):
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls)

        mock_ls.request_definition.return_value = [
            {
                "relativePath": "src/other.py",
                "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 10}},
            }
        ]
        # Stub _symbol_name_at to return a name
        manager._symbol_name_at = MagicMock(return_value="OtherClass")

        neighbors = manager.resolve_neighbors(cid)
        ref_neighbors = [n for n in neighbors if n.edge_type == EdgeType.REFERENCES]

        assert len(ref_neighbors) == 1
        assert ref_neighbors[0].name == "OtherClass"
        assert ref_neighbors[0].relative_path == "src/other.py"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_referenced_by_edge(self, mock_retriever_cls):
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls)

        ref_mock = MagicMock()
        ref_mock.symbol = {
            "name": "caller_func",
            "kind": 12,  # SymbolKind.Function
            "location": {"relativePath": "src/caller.py"},
            "selectionRange": {"start": {"line": 30, "character": 4}},
        }
        mock_ls.request_referencing_symbols.return_value = [ref_mock]

        neighbors = manager.resolve_neighbors(cid)
        refby = [n for n in neighbors if n.edge_type == EdgeType.REFERENCED_BY]

        assert len(refby) == 1
        assert refby[0].name == "caller_func"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_calls_edge(self, mock_retriever_cls):
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls)

        mock_ls.request_call_hierarchy_outgoing.return_value = [
            {
                "to": {
                    "name": "helper",
                    "kind": 12,
                    "uri": _make_file_uri("src/utils.py"),
                    "selectionRange": {"start": {"line": 5, "character": 0}},
                    "range": {"start": {"line": 5, "character": 0}, "end": {"line": 10, "character": 0}},
                }
            }
        ]

        neighbors = manager.resolve_neighbors(cid)
        calls = [n for n in neighbors if n.edge_type == EdgeType.CALLS]

        assert len(calls) == 1
        assert calls[0].name == "helper"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_called_by_edge(self, mock_retriever_cls):
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls)

        mock_ls.request_call_hierarchy_incoming.return_value = [
            {
                "from": {
                    "name": "main",
                    "kind": 12,
                    "uri": _make_file_uri("src/main.py"),
                    "selectionRange": {"start": {"line": 1, "character": 0}},
                    "range": {"start": {"line": 1, "character": 0}, "end": {"line": 20, "character": 0}},
                }
            }
        ]

        neighbors = manager.resolve_neighbors(cid)
        called_by = [n for n in neighbors if n.edge_type == EdgeType.CALLED_BY]

        assert len(called_by) == 1
        assert called_by[0].name == "main"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_inherits_edge(self, mock_retriever_cls):
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls)

        mock_ls.request_type_hierarchy_supertypes.return_value = [
            {
                "name": "BaseClass",
                "kind": 5,
                "uri": _make_file_uri("src/base.py"),
                "selectionRange": {"start": {"line": 3, "character": 0}},
                "range": {"start": {"line": 3, "character": 0}, "end": {"line": 30, "character": 0}},
            }
        ]

        neighbors = manager.resolve_neighbors(cid)
        inherits = [n for n in neighbors if n.edge_type == EdgeType.INHERITS]

        assert len(inherits) == 1
        assert inherits[0].name == "BaseClass"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_inherited_by_edge(self, mock_retriever_cls):
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls)

        mock_ls.request_type_hierarchy_subtypes.return_value = [
            {
                "name": "ChildClass",
                "kind": 5,
                "uri": _make_file_uri("src/child.py"),
                "selectionRange": {"start": {"line": 1, "character": 0}},
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 15, "character": 0}},
            }
        ]

        neighbors = manager.resolve_neighbors(cid)
        inherited_by = [n for n in neighbors if n.edge_type == EdgeType.INHERITED_BY]

        assert len(inherited_by) == 1
        assert inherited_by[0].name == "ChildClass"

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_edge_type_filtering(self, mock_retriever_cls):
        """Only active edge types are resolved."""
        children = [{"name": "child", "kind_name": "Method", "line": 12, "col": 4}]
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls, children=children)

        mock_ls.request_call_hierarchy_outgoing.return_value = [
            {
                "to": {
                    "name": "helper",
                    "kind": 12,
                    "uri": _make_file_uri("src/utils.py"),
                    "selectionRange": {"start": {"line": 5, "character": 0}},
                    "range": {"start": {"line": 5, "character": 0}, "end": {"line": 10, "character": 0}},
                }
            }
        ]

        # Restrict to only CALLS
        state = manager.get_cursor(cid)
        state.active_edge_types = frozenset({EdgeType.CALLS})

        neighbors = manager.resolve_neighbors(cid)
        assert all(n.edge_type == EdgeType.CALLS for n in neighbors)
        assert len(neighbors) == 1
        # Contains should NOT appear despite having children
        assert not any(n.edge_type == EdgeType.CONTAINS for n in neighbors)

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_lsp_error_is_swallowed(self, mock_retriever_cls):
        """LSP errors for individual edge types are caught; other edges still resolve."""
        children = [{"name": "child", "kind_name": "Method", "line": 12, "col": 4}]
        manager, cid, mock_ls = self._setup_manager_with_cursor(mock_retriever_cls, children=children)

        mock_ls.request_definition.side_effect = SolidLSPException("LSP error")
        mock_ls.request_referencing_symbols.side_effect = SolidLSPException("LSP error")

        # Should still get contains neighbors despite reference errors
        neighbors = manager.resolve_neighbors(cid)
        assert any(n.edge_type == EdgeType.CONTAINS for n in neighbors)

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_incomplete_location_returns_empty(self, mock_retriever_cls):
        """Cursor with None location fields returns no neighbors."""
        manager = _make_manager()
        sym = _make_symbol(name="Orphan", rel_path=None, line=None, col=None)
        # Override the location to have None fields
        sym.location = LanguageServerSymbolLocation(relative_path=None, line=None, column=None)
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid, _ = manager.start_cursor("Orphan")
        neighbors = manager.resolve_neighbors(cid)
        assert neighbors == []


# ── CursorManager: format_cursor_view / format_trail ─────────────────────


class TestFormatting:
    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_format_cursor_view_header(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol(name="MyClass", kind_name="Class", rel_path="src/m.py", line=10, name_path="MyClass")
        mock_retriever = mock_retriever_cls.return_value
        mock_retriever.find_unique.return_value = sym
        mock_retriever.get_language_server.return_value = MagicMock(
            request_definition=MagicMock(return_value=[]),
            request_referencing_symbols=MagicMock(return_value=[]),
            request_call_hierarchy_outgoing=MagicMock(return_value=[]),
            request_call_hierarchy_incoming=MagicMock(return_value=[]),
            request_type_hierarchy_supertypes=MagicMock(return_value=[]),
            request_type_hierarchy_subtypes=MagicMock(return_value=[]),
        )

        cid, _ = manager.start_cursor("MyClass")
        view = manager.format_cursor_view(cid)

        assert "@ MyClass (Class)" in view
        assert "m.py:11" in view  # 0-indexed line 10 → displayed as 11
        assert f"cursor: {cid}" in view
        assert "trail: 0 steps" in view

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_format_trail_empty(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol()
        mock_retriever_cls.return_value.find_unique.return_value = sym

        cid, _ = manager.start_cursor("MyClass")
        trail = manager.format_trail(cid)

        assert "no trail" in trail

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_format_trail_with_moves(self, mock_retriever_cls):
        manager = _make_manager()
        mock_retriever = mock_retriever_cls.return_value

        sym_a = _make_symbol(name="A", rel_path="a.py", line=5)
        sym_b = _make_symbol(name="B", rel_path="b.py", line=15)
        mock_retriever.find_unique.side_effect = [sym_a, sym_b]

        cid, _ = manager.start_cursor("A")
        manager.move_cursor(cid, "B")

        trail = manager.format_trail(cid)
        assert "1 steps" in trail
        assert "a.py:6" in trail  # trail entry (0-indexed 5 → display 6)
        assert "b.py:16" in trail  # current position
        assert "(current)" in trail

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_format_cursor_view_with_body(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol(name="func", kind_name="Function", line=10, body="def func(): pass")
        mock_retriever = mock_retriever_cls.return_value
        mock_retriever.find_unique.return_value = sym
        mock_retriever.get_language_server.return_value = MagicMock(
            request_definition=MagicMock(return_value=[]),
            request_referencing_symbols=MagicMock(return_value=[]),
            request_call_hierarchy_outgoing=MagicMock(return_value=[]),
            request_call_hierarchy_incoming=MagicMock(return_value=[]),
            request_type_hierarchy_supertypes=MagicMock(return_value=[]),
            request_type_hierarchy_subtypes=MagicMock(return_value=[]),
        )

        cid, _ = manager.start_cursor("func")
        state = manager.get_cursor(cid)
        state.include_body = True
        view = manager.format_cursor_view(cid)

        assert "--- body ---" in view
        assert "def func(): pass" in view

    @patch("serena.cursor.LanguageServerSymbolRetriever")
    def test_format_cursor_view_no_neighbors_message(self, mock_retriever_cls):
        manager = _make_manager()
        sym = _make_symbol(name="Leaf", children=[])
        mock_retriever = mock_retriever_cls.return_value
        mock_retriever.find_unique.return_value = sym
        mock_retriever.get_language_server.return_value = MagicMock(
            request_definition=MagicMock(return_value=[]),
            request_referencing_symbols=MagicMock(return_value=[]),
            request_call_hierarchy_outgoing=MagicMock(return_value=[]),
            request_call_hierarchy_incoming=MagicMock(return_value=[]),
            request_type_hierarchy_supertypes=MagicMock(return_value=[]),
            request_type_hierarchy_subtypes=MagicMock(return_value=[]),
        )

        cid, _ = manager.start_cursor("Leaf")
        view = manager.format_cursor_view(cid)

        assert "(no neighbors found)" in view
