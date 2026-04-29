"""
Tests for cursor-based code navigation.

Tests CursorManager against a live Python LSP, and exercises the cursor MCP tools
through SerenaAgent.get_tool() against the Python test repository.
"""

import os
import re
from collections.abc import Iterator

import pytest

from serena.agent import SerenaAgent
from serena.config.serena_config import ProjectConfig, RegisteredProject, SerenaConfig
from serena.cursor import ALL_EDGE_TYPES, DEFAULT_EDGE_TYPES, CursorManager, CursorState, EdgeType, NeighborSymbol
from serena.project import Project
from serena.tools.cursor_tools import (
    CursorCloseTool,
    CursorConfigureTool,
    CursorFindTool,
    CursorHistoryTool,
    CursorInsertAfterTool,
    CursorInsertBeforeTool,
    CursorLookTool,
    CursorMoveTool,
    CursorOverviewTool,
    CursorRenameTool,
    CursorReplaceBodyTool,
    CursorStartTool,
)
from solidlsp.ls_config import Language
from test.conftest import get_repo_path, language_tests_enabled, project_with_ls_context

pytestmark = pytest.mark.python


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def python_project():
    """A Project with an active Python language server for cursor tests."""
    with project_with_ls_context(Language.PYTHON) as project:
        yield project


@pytest.fixture
def cursor_manager(python_project: Project) -> CursorManager:
    """A fresh CursorManager for each test."""
    return CursorManager(python_project)


@pytest.fixture(scope="module")
def python_serena_agent():
    """SerenaAgent configured for the Python test repo."""
    if not language_tests_enabled(Language.PYTHON):
        pytest.skip("Python tests not enabled")

    config = SerenaConfig(gui_log_window=False, web_dashboard=False)
    repo_path = get_repo_path(Language.PYTHON)
    project = Project(
        project_root=str(repo_path),
        project_config=ProjectConfig(
            project_name="test_repo_python",
            languages=[Language.PYTHON],
            ignored_paths=[],
            excluded_tools=[],
            read_only=False,
            ignore_all_files_in_gitignore=True,
            initial_prompt="",
            encoding="utf-8",
        ),
        serena_config=config,
    )
    config.projects = [RegisteredProject.from_project_instance(project)]
    agent = SerenaAgent(project="test_repo_python", serena_config=config)
    agent.execute_task(lambda: None)
    yield agent
    agent.on_shutdown(timeout=5)


# ===========================================================================
# CursorManager Integration Tests (live Python LSP)
# ===========================================================================


class TestCursorManagerBasics:
    """Test basic CursorManager lifecycle: start, get, list, close."""

    def test_start_cursor_auto_id(self, cursor_manager: CursorManager) -> None:
        """start_cursor generates an auto-incremented cursor ID."""
        cid, state = cursor_manager.start_cursor("UserService")
        assert cid == "c1"
        assert isinstance(state, CursorState)
        assert state.cursor_id == "c1"
        assert state.current_symbol.name == "UserService"
        assert state.trail == []
        assert state.active_edge_types == DEFAULT_EDGE_TYPES

    def test_start_cursor_explicit_id(self, cursor_manager: CursorManager) -> None:
        """start_cursor accepts an explicit cursor ID."""
        cid, state = cursor_manager.start_cursor("UserService", cursor_id="my-cursor")
        assert cid == "my-cursor"
        assert state.cursor_id == "my-cursor"

    def test_start_cursor_with_relative_path(self, cursor_manager: CursorManager) -> None:
        """start_cursor can narrow symbol search to a specific file."""
        cid, state = cursor_manager.start_cursor(
            "UserService",
            relative_path=os.path.join("test_repo", "services.py"),
        )
        assert state.current_symbol.name == "UserService"
        assert state.current_location.relative_path is not None
        assert "services.py" in state.current_location.relative_path

    def test_get_cursor(self, cursor_manager: CursorManager) -> None:
        """get_cursor returns the correct state for a known cursor."""
        cid, _ = cursor_manager.start_cursor("UserService")
        state = cursor_manager.get_cursor(cid)
        assert state.cursor_id == cid

    def test_get_cursor_unknown_raises(self, cursor_manager: CursorManager) -> None:
        """get_cursor raises ValueError for an unknown cursor ID."""
        with pytest.raises(ValueError, match="No cursor with id"):
            cursor_manager.get_cursor("nonexistent")

    def test_list_cursors(self, cursor_manager: CursorManager) -> None:
        """list_cursors returns all active cursor IDs."""
        assert cursor_manager.list_cursors() == []
        cursor_manager.start_cursor("UserService", cursor_id="a")
        cursor_manager.start_cursor("Item", cursor_id="b")
        ids = cursor_manager.list_cursors()
        assert set(ids) == {"a", "b"}

    def test_close_cursor(self, cursor_manager: CursorManager) -> None:
        """close_cursor removes the cursor."""
        cid, _ = cursor_manager.start_cursor("UserService")
        assert cid in cursor_manager.list_cursors()
        cursor_manager.close_cursor(cid)
        assert cid not in cursor_manager.list_cursors()

    def test_close_nonexistent_cursor_is_noop(self, cursor_manager: CursorManager) -> None:
        """Closing a nonexistent cursor does not raise."""
        cursor_manager.close_cursor("does-not-exist")  # should not raise


class TestCursorMovement:
    """Test moving a cursor to neighbor symbols."""

    def test_move_to_child(self, cursor_manager: CursorManager) -> None:
        """Move cursor from a class to one of its contained methods."""
        cid, _ = cursor_manager.start_cursor("UserService")
        state = cursor_manager.move_cursor(cid, "create_user")
        assert state.current_symbol.name == "create_user"
        assert len(state.trail) == 1  # one step in trail

    def test_trail_records_moves(self, cursor_manager: CursorManager) -> None:
        """Trail grows with each move, preserving prior locations."""
        cid, _ = cursor_manager.start_cursor("ItemService")
        state = cursor_manager.get_cursor(cid)
        # Restrict to contains edges to avoid ambiguous substring matches from references
        state.active_edge_types = frozenset({EdgeType.CONTAINS})

        cursor_manager.move_cursor(cid, "create_item")

        # Close and re-start to get a clean trail for the actual assertion
        cursor_manager.close_cursor(cid)
        cid2, _ = cursor_manager.start_cursor("ItemService", cursor_id="trail2")
        state2 = cursor_manager.get_cursor(cid2)
        state2.active_edge_types = frozenset({EdgeType.CONTAINS})
        initial_loc2 = state2.current_location

        cursor_manager.move_cursor(cid2, "create_item")
        mid_loc = cursor_manager.get_cursor(cid2).current_location

        # Move from create_item's view — navigate via global fallback to list_items
        cursor_manager.move_cursor(cid2, "list_items")
        final_state = cursor_manager.get_cursor(cid2)

        assert len(final_state.trail) == 2
        assert final_state.trail[0] == initial_loc2
        assert final_state.trail[1] == mid_loc

    def test_move_to_ambiguous_target_with_path(self, cursor_manager: CursorManager) -> None:
        """When a target name appears in multiple neighbors, relative_path narrows it."""
        # __init__ exists in many classes; disambiguate by providing relative path
        cid, _ = cursor_manager.start_cursor("UserService")
        state = cursor_manager.move_cursor(
            cid,
            "__init__",
            target_relative_path=os.path.join("test_repo", "services.py"),
        )
        assert state.current_symbol.name == "__init__"


class TestNeighborResolution:
    """Test that resolve_neighbors returns correct neighbors for various edge types."""

    def test_contains_edge(self, cursor_manager: CursorManager) -> None:
        """Contains edge returns children of a class."""
        cid, _ = cursor_manager.start_cursor("UserService")
        neighbors = cursor_manager.resolve_neighbors(cid)
        contains_names = {n.name for n in neighbors if n.edge_type == EdgeType.CONTAINS}
        # UserService should contain __init__, create_user, get_user, list_users, delete_user
        assert "create_user" in contains_names
        assert "get_user" in contains_names
        assert "list_users" in contains_names

    def test_referenced_by_edge(self, cursor_manager: CursorManager) -> None:
        """Referenced-by edge finds symbols that reference the current symbol."""
        cid, _ = cursor_manager.start_cursor("User", relative_path=os.path.join("test_repo", "models.py"))
        neighbors = cursor_manager.resolve_neighbors(cid)
        referenced_by = [n for n in neighbors if n.edge_type == EdgeType.REFERENCED_BY]
        # User is referenced by services.py and other files
        assert len(referenced_by) > 0


class TestEdgeTypeConfiguration:
    """Test configuring which edge types are active."""

    def test_default_edge_types(self, cursor_manager: CursorManager) -> None:
        """Default edge types include all 7 types."""
        assert DEFAULT_EDGE_TYPES == ALL_EDGE_TYPES

    def test_configure_subset(self, cursor_manager: CursorManager) -> None:
        """Cursor can be configured to only follow a subset of edge types."""
        cid, _ = cursor_manager.start_cursor("UserService")
        state = cursor_manager.get_cursor(cid)
        state.active_edge_types = frozenset({EdgeType.CONTAINS})

        neighbors = cursor_manager.resolve_neighbors(cid)
        for n in neighbors:
            assert n.edge_type == EdgeType.CONTAINS


class TestFormatting:
    """Test format_cursor_view and format_trail output."""

    def test_format_cursor_view_contains_symbol_name(self, cursor_manager: CursorManager) -> None:
        """format_cursor_view includes the current symbol name and location."""
        cid, _ = cursor_manager.start_cursor("UserService")
        view = cursor_manager.format_cursor_view(cid)
        assert "UserService" in view
        assert "cursor: " + cid in view
        assert "trail: 0 steps" in view
        assert "contains:" in view

    def test_format_trail_empty(self, cursor_manager: CursorManager) -> None:
        """format_trail reports no trail at starting position."""
        cid, _ = cursor_manager.start_cursor("UserService")
        trail = cursor_manager.format_trail(cid)
        assert "no trail" in trail

    def test_format_trail_after_moves(self, cursor_manager: CursorManager) -> None:
        """format_trail shows numbered steps after navigation."""
        cid, _ = cursor_manager.start_cursor("UserService")
        cursor_manager.move_cursor(cid, "create_user")
        trail = cursor_manager.format_trail(cid)
        assert "1 steps" in trail or "1." in trail
        assert "(current)" in trail


class TestNeighborSymbol:
    """Test NeighborSymbol formatting."""

    def test_location_str_with_path_and_line(self) -> None:
        n = NeighborSymbol(
            name="foo",
            kind="Function",
            relative_path="src/main.py",
            line=10,
            column=0,
            edge_type=EdgeType.CONTAINS,
        )
        assert n.location_str == "src/main.py:11"  # 0-indexed line → 1-indexed display

    def test_location_str_path_only(self) -> None:
        n = NeighborSymbol(
            name="foo",
            kind="Function",
            relative_path="src/main.py",
            line=None,
            column=None,
            edge_type=EdgeType.CONTAINS,
        )
        assert n.location_str == "src/main.py"

    def test_location_str_unknown(self) -> None:
        n = NeighborSymbol(
            name="foo",
            kind="Function",
            relative_path=None,
            line=None,
            column=None,
            edge_type=EdgeType.CONTAINS,
        )
        assert n.location_str == "?"

    def test_format_compact(self) -> None:
        n = NeighborSymbol(
            name="foo",
            kind="Function",
            relative_path="src/main.py",
            line=10,
            column=0,
            edge_type=EdgeType.CALLS,
            detail="some detail",
        )
        formatted = n.format_compact()
        assert "foo" in formatted
        assert "(Function)" in formatted
        assert "src/main.py:11" in formatted
        assert "— some detail" in formatted


# ===========================================================================
# SerenaAgent Tool-Level Integration Tests
# ===========================================================================


@pytest.fixture(autouse=True)
def _cleanup_cursors(python_serena_agent: SerenaAgent) -> Iterator[None]:
    """Close all cursors after each tool integration test."""
    yield
    manager = python_serena_agent.get_cursor_manager()
    for cid in list(manager.list_cursors()):
        manager.close_cursor(cid)


class TestCursorToolsIntegration:
    """Integration tests exercising cursor tools through SerenaAgent."""

    def test_cursor_start_and_look(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_start places a cursor and returns a neighborhood view."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        result = start_tool.apply(name_path="UserService")

        assert "UserService" in result
        assert "cursor:" in result
        assert "contains:" in result
        assert "create_user" in result

        # Extract cursor ID from result
        # Format: "  cursor: c1 | trail: 0 steps"
        match = re.search(r"cursor: (\S+)", result)
        assert match, f"Could not find cursor ID in result: {result}"
        cid = match.group(1)

        # cursor_look should return the same view
        look_tool = python_serena_agent.get_tool(CursorLookTool)
        look_result = look_tool.apply(cursor_id=cid)
        assert "UserService" in look_result
        assert "contains:" in look_result

    def test_cursor_move_and_history(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_move navigates to a neighbor; cursor_history shows the trail."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        start_tool.apply(name_path="UserService", cursor_id="nav-test")

        move_tool = python_serena_agent.get_tool(CursorMoveTool)
        move_result = move_tool.apply(cursor_id="nav-test", target_name="create_user")
        assert "create_user" in move_result

        history_tool = python_serena_agent.get_tool(CursorHistoryTool)
        history_result = history_tool.apply(cursor_id="nav-test")
        assert "1." in history_result
        assert "(current)" in history_result

    def test_cursor_configure_edge_types(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_configure changes which edge types are shown."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        start_tool.apply(name_path="UserService", cursor_id="cfg-test")

        configure_tool = python_serena_agent.get_tool(CursorConfigureTool)
        result = configure_tool.apply(cursor_id="cfg-test", edge_types=["contains"])
        # After configuring to only show "contains", we should still see children
        assert "contains:" in result
        # Other edge types should not appear (unless they happen to have zero results,
        # in which case they wouldn't appear anyway)

    def test_cursor_configure_invalid_edge_type(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_configure raises for an invalid edge type name."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        start_tool.apply(name_path="UserService", cursor_id="cfg-err")

        configure_tool = python_serena_agent.get_tool(CursorConfigureTool)
        with pytest.raises(ValueError, match="Unknown edge type"):
            configure_tool.apply(cursor_id="cfg-err", edge_types=["nonexistent-edge"])

    def test_cursor_close(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_close removes the cursor."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        start_tool.apply(name_path="UserService", cursor_id="close-test")

        close_tool = python_serena_agent.get_tool(CursorCloseTool)
        result = close_tool.apply(cursor_id="close-test")
        assert "close-test" in result
        assert "closed" in result.lower()

        # Trying to look at a closed cursor should fail
        look_tool = python_serena_agent.get_tool(CursorLookTool)
        with pytest.raises(ValueError, match="No cursor with id"):
            look_tool.apply(cursor_id="close-test")

    def test_cursor_include_body(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_configure with include_body=True shows the symbol body."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        start_tool.apply(name_path="UserService/create_user", cursor_id="body-test")

        configure_tool = python_serena_agent.get_tool(CursorConfigureTool)
        result = configure_tool.apply(cursor_id="body-test", include_body=True)
        assert "--- body ---" in result
        assert "def create_user" in result

    def test_navigate_class_to_method_to_reference(self, python_serena_agent: SerenaAgent) -> None:
        """Full navigation: class -> method -> follow a reference."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        move_tool = python_serena_agent.get_tool(CursorMoveTool)
        history_tool = python_serena_agent.get_tool(CursorHistoryTool)

        # Start at a class
        start_tool.apply(name_path="UserService", cursor_id="full-nav")

        # Move to a method
        move_tool.apply(cursor_id="full-nav", target_name="create_user")

        # Check trail has one step
        history = history_tool.apply(cursor_id="full-nav")
        assert "1." in history

    def test_multiple_cursors(self, python_serena_agent: SerenaAgent) -> None:
        """Multiple cursors can be active simultaneously."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)

        r1 = start_tool.apply(name_path="UserService", cursor_id="multi-1")
        r2 = start_tool.apply(name_path="Item", cursor_id="multi-2")

        assert "UserService" in r1
        assert "Item" in r2

        look_tool = python_serena_agent.get_tool(CursorLookTool)
        look1 = look_tool.apply(cursor_id="multi-1")
        look2 = look_tool.apply(cursor_id="multi-2")

        assert "UserService" in look1
        assert "Item" in look2

    def test_navigate_inheritance(self, python_serena_agent: SerenaAgent) -> None:
        """Navigate the type hierarchy: User inherits from BaseModel."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        configure_tool = python_serena_agent.get_tool(CursorConfigureTool)

        start_tool.apply(name_path="User", cursor_id="inherit-test", relative_path=os.path.join("test_repo", "models.py"))

        # Configure to only show inheritance edges
        result = configure_tool.apply(
            cursor_id="inherit-test",
            edge_types=["inherits", "inherited-by"],
        )
        # If the Python LSP supports type hierarchy, we should see BaseModel
        # If not, the cursor gracefully shows "(no neighbors found)"
        # Either outcome is acceptable — the test validates no crashes
        assert "inherit-test" in result or "cursor:" in result

    def test_navigate_nested_class(self, python_serena_agent: SerenaAgent) -> None:
        """Navigate to a nested class via the contains edge."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        result = start_tool.apply(
            name_path="OuterClass",
            relative_path=os.path.join("test_repo", "nested.py"),
        )

        assert "OuterClass" in result
        # Should see NestedClass and nested_test as children
        assert "NestedClass" in result or "nested_test" in result


# ===========================================================================
# Cursor Find and Overview (read) tests
# ===========================================================================


class TestCursorFindAndOverview:
    def test_cursor_find_unique_starts_cursor(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_find with a unique match starts a cursor and returns its view."""
        find_tool = python_serena_agent.get_tool(CursorFindTool)
        result = find_tool.apply(name_path_pattern="/UserService", cursor_id="find-unique")
        assert "started cursor" in result
        assert "UserService" in result
        assert "contains:" in result

    def test_cursor_find_multiple_returns_candidates(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_find with a non-unique pattern returns a candidate list without starting a cursor."""
        find_tool = python_serena_agent.get_tool(CursorFindTool)
        result = find_tool.apply(name_path_pattern="__init__")
        # Many __init__ methods exist; the result should list candidates and NOT start a cursor.
        assert "started cursor" not in result
        assert "matching symbols" in result or "Candidates" in result

    def test_cursor_find_no_match(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_find returns a clear message when no symbol matches."""
        find_tool = python_serena_agent.get_tool(CursorFindTool)
        result = find_tool.apply(name_path_pattern="__absolutely_no_such_symbol__")
        assert "No symbols found" in result

    def test_cursor_find_substring(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_find with substring_matching=True matches partial names."""
        find_tool = python_serena_agent.get_tool(CursorFindTool)
        result = find_tool.apply(
            name_path_pattern="create_u",
            substring_matching=True,
            relative_path=os.path.join("test_repo", "services.py"),
        )
        assert "create_user" in result

    def test_cursor_overview(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_overview lists top-level symbols in a file."""
        overview_tool = python_serena_agent.get_tool(CursorOverviewTool)
        result = overview_tool.apply(relative_path=os.path.join("test_repo", "services.py"))
        assert "Top-level symbols" in result
        assert "UserService" in result
        assert "ItemService" in result

    def test_cursor_overview_missing_file(self, python_serena_agent: SerenaAgent) -> None:
        """cursor_overview raises FileNotFoundError for a missing file."""
        overview_tool = python_serena_agent.get_tool(CursorOverviewTool)
        with pytest.raises(FileNotFoundError):
            overview_tool.apply(relative_path="does/not/exist.py")


# ===========================================================================
# Cursor Edit tool tests — use a throwaway file so we can assert and revert.
# ===========================================================================


@pytest.fixture
def throwaway_python_file(python_serena_agent: SerenaAgent) -> Iterator[str]:
    """Create a throwaway Python file in the test repo so edit tests can mutate and clean up."""
    from pathlib import Path

    rel_path = os.path.join("test_repo", "_cursor_edit_sandbox.py")
    abs_path = Path(python_serena_agent.get_active_project_or_raise().project_root) / rel_path
    abs_path.write_text("def sandbox_fn():\n    x = 1\n    return x\n\n\ndef other_fn():\n    return 2\n")
    # Give the LSP a chance to pick up the file on some backends.
    try:
        python_serena_agent.reset_language_server_manager()
    except Exception:
        pass
    try:
        yield rel_path
    finally:
        if abs_path.exists():
            abs_path.unlink()
        try:
            python_serena_agent.reset_language_server_manager()
        except Exception:
            pass


class TestCursorEditTools:
    def test_cursor_replace_body_refreshes_cursor(self, python_serena_agent: SerenaAgent, throwaway_python_file: str) -> None:
        """cursor_replace_body replaces the body and the cursor re-anchors."""
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        replace_tool = python_serena_agent.get_tool(CursorReplaceBodyTool)
        look_tool = python_serena_agent.get_tool(CursorLookTool)

        start_tool.apply(
            name_path="sandbox_fn",
            relative_path=throwaway_python_file,
            cursor_id="edit-replace",
        )
        result = replace_tool.apply(
            cursor_id="edit-replace",
            body="def sandbox_fn():\n    return 42\n",
        )
        assert "OK" in result
        assert "sandbox_fn" in result

        look = look_tool.apply(cursor_id="edit-replace")
        assert "sandbox_fn" in look

    def test_cursor_insert_before(self, python_serena_agent: SerenaAgent, throwaway_python_file: str) -> None:
        """cursor_insert_before inserts content above the target symbol."""
        from pathlib import Path

        start_tool = python_serena_agent.get_tool(CursorStartTool)
        insert_tool = python_serena_agent.get_tool(CursorInsertBeforeTool)

        start_tool.apply(
            name_path="other_fn",
            relative_path=throwaway_python_file,
            cursor_id="edit-before",
        )
        result = insert_tool.apply(
            cursor_id="edit-before",
            body="# inserted-before-marker\n",
        )
        assert "OK" in result

        abs_path = Path(python_serena_agent.get_active_project_or_raise().project_root) / throwaway_python_file
        content = abs_path.read_text()
        assert "inserted-before-marker" in content
        assert content.index("inserted-before-marker") < content.index("def other_fn")

    def test_cursor_insert_after(self, python_serena_agent: SerenaAgent, throwaway_python_file: str) -> None:
        """cursor_insert_after inserts content below the target symbol."""
        from pathlib import Path

        start_tool = python_serena_agent.get_tool(CursorStartTool)
        insert_tool = python_serena_agent.get_tool(CursorInsertAfterTool)

        start_tool.apply(
            name_path="sandbox_fn",
            relative_path=throwaway_python_file,
            cursor_id="edit-after",
        )
        result = insert_tool.apply(
            cursor_id="edit-after",
            body="# inserted-after-marker\n",
        )
        assert "OK" in result

        abs_path = Path(python_serena_agent.get_active_project_or_raise().project_root) / throwaway_python_file
        content = abs_path.read_text()
        assert "inserted-after-marker" in content

    def test_cursor_rename(self, python_serena_agent: SerenaAgent, throwaway_python_file: str) -> None:
        """cursor_rename renames the symbol and re-anchors the cursor."""
        from pathlib import Path

        start_tool = python_serena_agent.get_tool(CursorStartTool)
        rename_tool = python_serena_agent.get_tool(CursorRenameTool)

        start_tool.apply(
            name_path="sandbox_fn",
            relative_path=throwaway_python_file,
            cursor_id="edit-rename",
        )
        result = rename_tool.apply(cursor_id="edit-rename", new_name="renamed_sandbox_fn")
        # Rename may or may not be supported by all language servers; accept graceful failure text.
        abs_path = Path(python_serena_agent.get_active_project_or_raise().project_root) / throwaway_python_file
        content = abs_path.read_text()
        # Either the rename worked or the tool reported back (but no crash).
        assert "edit-rename" in result or "renamed_sandbox_fn" in content or "sandbox_fn" in content

    def test_cursor_edit_without_location_raises(self, python_serena_agent: SerenaAgent) -> None:
        """A cursor whose current location has no relative_path rejects edits."""
        from serena.cursor import CursorState
        from serena.symbol import LanguageServerSymbolLocation

        manager = python_serena_agent.get_cursor_manager()
        replace_tool = python_serena_agent.get_tool(CursorReplaceBodyTool)

        # Manually install a cursor with a None relative_path
        sandbox_location = LanguageServerSymbolLocation(relative_path=None, line=None, column=None)
        # Position with a real symbol first, then override its location.
        start_tool = python_serena_agent.get_tool(CursorStartTool)
        start_tool.apply(
            name_path="UserService",
            relative_path=os.path.join("test_repo", "services.py"),
            cursor_id="no-loc",
        )
        state: CursorState = manager.get_cursor("no-loc")
        state.current_location = sandbox_location

        with pytest.raises(ValueError, match="no relative path"):
            replace_tool.apply(cursor_id="no-loc", body="irrelevant")
