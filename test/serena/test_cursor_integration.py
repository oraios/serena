"""
Integration tests for cursor-based code navigation using the Python test repository.

These tests start a real language server against the Python test repo and exercise
the full cursor lifecycle: start, navigate, configure, trail, and close.
"""

import pytest

from serena.cursor import CursorManager, EdgeType
from serena.symbol import LanguageServerSymbolRetriever
from solidlsp.ls_config import Language
from test.conftest import project_with_ls_context

pytestmark = pytest.mark.python


@pytest.fixture(scope="module")
def cursor_manager():
    """Create a CursorManager backed by the real Python test repo with a live LSP server."""
    with project_with_ls_context(Language.PYTHON) as project:
        yield CursorManager(project)


class TestCursorStartAndLook:
    def test_start_cursor_at_class(self, cursor_manager: CursorManager):
        """Start a cursor at the UserService class and verify position."""
        cid, state = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            assert state.cursor_id == cid
            assert state.current_symbol.name == "UserService"
            assert state.trail == []
            assert state.current_location.relative_path is not None
            assert "services.py" in state.current_location.relative_path
        finally:
            cursor_manager.close_cursor(cid)

    def test_start_cursor_at_function(self, cursor_manager: CursorManager):
        """Start a cursor at a standalone function."""
        cid, state = cursor_manager.start_cursor("create_user_object", relative_path="test_repo/models.py")
        try:
            assert state.current_symbol.name == "create_user_object"
        finally:
            cursor_manager.close_cursor(cid)


class TestContainsEdge:
    def test_class_contains_methods(self, cursor_manager: CursorManager):
        """A class cursor should see its methods via the contains edge."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            neighbors = cursor_manager.resolve_neighbors(cid)
            contains = [n for n in neighbors if n.edge_type == EdgeType.CONTAINS]
            names = {n.name for n in contains}
            # UserService has __init__, create_user, get_user, list_users, delete_user
            assert "create_user" in names
            assert "get_user" in names
        finally:
            cursor_manager.close_cursor(cid)

    def test_outer_class_contains_nested(self, cursor_manager: CursorManager):
        """OuterClass should contain NestedClass via contains edge."""
        cid, _ = cursor_manager.start_cursor("OuterClass", relative_path="test_repo/nested.py")
        try:
            neighbors = cursor_manager.resolve_neighbors(cid)
            contains = [n for n in neighbors if n.edge_type == EdgeType.CONTAINS]
            names = {n.name for n in contains}
            assert "NestedClass" in names
        finally:
            cursor_manager.close_cursor(cid)


class TestNavigationAndTrail:
    def test_move_to_child_method(self, cursor_manager: CursorManager):
        """Navigate from a class to one of its methods."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            state = cursor_manager.move_cursor(cid, "create_user")
            assert state.current_symbol.name == "create_user"
            assert len(state.trail) == 1  # UserService position recorded
        finally:
            cursor_manager.close_cursor(cid)

    def test_multi_step_trail(self, cursor_manager: CursorManager):
        """Navigate multiple hops and verify the trail records each step.

        Navigate from OuterClass -> NestedClass -> find_me to avoid ambiguity
        issues with 'user' substring matching in the services module.
        """
        cid, _ = cursor_manager.start_cursor("OuterClass", relative_path="test_repo/nested.py")
        try:
            cursor_manager.move_cursor(cid, "NestedClass")
            cursor_manager.move_cursor(cid, "find_me")

            state = cursor_manager.get_cursor(cid)
            assert len(state.trail) == 2
            assert state.current_symbol.name == "find_me"
        finally:
            cursor_manager.close_cursor(cid)

    def test_format_trail_after_moves(self, cursor_manager: CursorManager):
        """The formatted trail should show visited locations."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            cursor_manager.move_cursor(cid, "create_user")
            trail_text = cursor_manager.format_trail(cid)
            assert "1 steps" in trail_text
            assert "services.py" in trail_text
            assert "(current)" in trail_text
        finally:
            cursor_manager.close_cursor(cid)


class TestEdgeTypeConfiguration:
    def test_restrict_to_contains_only(self, cursor_manager: CursorManager):
        """When only CONTAINS is active, only children should appear."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            state = cursor_manager.get_cursor(cid)
            state.active_edge_types = frozenset({EdgeType.CONTAINS})

            neighbors = cursor_manager.resolve_neighbors(cid)
            assert all(n.edge_type == EdgeType.CONTAINS for n in neighbors)
            assert len(neighbors) > 0
        finally:
            cursor_manager.close_cursor(cid)

    def test_disable_all_edges_yields_no_neighbors(self, cursor_manager: CursorManager):
        """With no active edge types, resolve_neighbors returns empty."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            state = cursor_manager.get_cursor(cid)
            state.active_edge_types = frozenset()

            neighbors = cursor_manager.resolve_neighbors(cid)
            assert neighbors == []
        finally:
            cursor_manager.close_cursor(cid)


class TestFormatCursorView:
    def test_view_contains_symbol_info(self, cursor_manager: CursorManager):
        """format_cursor_view should include the symbol name, kind, and location."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            view = cursor_manager.format_cursor_view(cid)
            assert "UserService" in view
            assert "services.py" in view
            assert f"cursor: {cid}" in view
        finally:
            cursor_manager.close_cursor(cid)

    def test_view_lists_neighbors(self, cursor_manager: CursorManager):
        """The cursor view should show neighbors grouped by edge type."""
        cid, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        try:
            view = cursor_manager.format_cursor_view(cid)
            # Should at least show contains section with methods
            assert "contains:" in view
            assert "create_user" in view
        finally:
            cursor_manager.close_cursor(cid)


class TestInheritanceEdges:
    def test_inherits_edge_does_not_crash(self, cursor_manager: CursorManager):
        """Type hierarchy edges should resolve without error, even if the LSP returns empty.

        Note: Pyright (Python LSP) does not support textDocument/typeHierarchy, so these
        edges typically return empty for Python. The test validates that the edge resolution
        completes gracefully.
        """
        cid, _ = cursor_manager.start_cursor("User", relative_path="test_repo/models.py")
        try:
            state = cursor_manager.get_cursor(cid)
            state.active_edge_types = frozenset({EdgeType.INHERITS, EdgeType.INHERITED_BY})

            neighbors = cursor_manager.resolve_neighbors(cid)
            # We don't assert specific results — Pyright may not support type hierarchy.
            # Just verify no crash and that returned neighbors (if any) have correct edge types.
            for n in neighbors:
                assert n.edge_type in (EdgeType.INHERITS, EdgeType.INHERITED_BY)
        finally:
            cursor_manager.close_cursor(cid)


class TestMultipleCursors:
    def test_independent_cursors(self, cursor_manager: CursorManager):
        """Multiple cursors can coexist and track independent state."""
        cid1, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        cid2, _ = cursor_manager.start_cursor("ItemService", relative_path="test_repo/services.py")
        try:
            assert cid1 != cid2
            assert set(cursor_manager.list_cursors()) >= {cid1, cid2}

            # Move one cursor, the other should be unaffected
            cursor_manager.move_cursor(cid1, "create_user")
            state1 = cursor_manager.get_cursor(cid1)
            state2 = cursor_manager.get_cursor(cid2)

            assert state1.current_symbol.name == "create_user"
            assert state2.current_symbol.name == "ItemService"
            assert len(state1.trail) == 1
            assert len(state2.trail) == 0
        finally:
            cursor_manager.close_cursor(cid1)
            cursor_manager.close_cursor(cid2)

    def test_close_one_preserves_other(self, cursor_manager: CursorManager):
        """Closing one cursor should not affect another."""
        cid1, _ = cursor_manager.start_cursor("UserService", relative_path="test_repo/services.py")
        cid2, _ = cursor_manager.start_cursor("ItemService", relative_path="test_repo/services.py")
        try:
            cursor_manager.close_cursor(cid1)
            assert cid1 not in cursor_manager.list_cursors()
            # cid2 should still be accessible
            state2 = cursor_manager.get_cursor(cid2)
            assert state2.current_symbol.name == "ItemService"
        finally:
            cursor_manager.close_cursor(cid2)
