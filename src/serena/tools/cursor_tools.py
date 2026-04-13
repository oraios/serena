"""
Cursor-based code navigation tools.

These tools provide stateful, incremental navigation through code structure
using LSP graph edges (containment, references, call hierarchy, type hierarchy).
"""

from serena.cursor import EdgeType
from serena.tools.tools_base import Tool, ToolMarkerOptional, ToolMarkerSymbolicRead


class CursorStartTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Start a navigation cursor at a symbol for incremental code exploration.
    The cursor tracks your position and lets you navigate along code relationships
    (containment, references, calls, type hierarchy).
    """

    def apply(
        self,
        name_path: str,
        relative_path: str = "",
        cursor_id: str = "",
    ) -> str:
        """
        Start a new cursor at the specified symbol. Returns the symbol's neighborhood
        showing all reachable symbols via active edge types.

        :param name_path: name path of the symbol to start at (e.g. "MyClass/my_method").
            See find_symbol for name path pattern syntax.
        :param relative_path: optional file path to narrow the symbol search.
        :param cursor_id: optional explicit cursor ID. Auto-generated if empty.
        :return: the cursor view showing the symbol and its neighborhood.
        """
        manager = self.agent.get_cursor_manager()
        cid, _state = manager.start_cursor(
            name_path=name_path,
            relative_path=relative_path or None,
            cursor_id=cursor_id or None,
        )
        return manager.format_cursor_view(cid)


class CursorMoveTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Move a navigation cursor to an adjacent symbol. The target should be
    visible in the cursor's current neighborhood (from cursor_start or cursor_look output).
    """

    def apply(
        self,
        cursor_id: str,
        target_name: str,
        target_relative_path: str = "",
    ) -> str:
        """
        Move the cursor to a neighboring symbol. Returns the new position's neighborhood.

        :param cursor_id: the ID of the cursor to move (shown in cursor output).
        :param target_name: name of the symbol to move to. Must be visible in the current neighborhood.
        :param target_relative_path: optional file path to disambiguate if multiple neighbors share the same name.
        :return: the updated cursor view at the new position.
        """
        manager = self.agent.get_cursor_manager()
        manager.move_cursor(
            cursor_id=cursor_id,
            target_name=target_name,
            target_relative_path=target_relative_path or None,
        )
        return manager.format_cursor_view(cursor_id)


class CursorLookTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Look at the neighborhood of the cursor's current position without moving.
    Useful for re-examining the current position after changing edge type configuration.
    """

    def apply(self, cursor_id: str) -> str:
        """
        Show the current cursor position and its neighborhood.

        :param cursor_id: the ID of the cursor to look from.
        :return: the cursor view showing the symbol and its neighborhood.
        """
        manager = self.agent.get_cursor_manager()
        return manager.format_cursor_view(cursor_id)


class CursorConfigureTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Configure which edge types a cursor follows and what information is shown.
    Edge types: contains, references, referenced-by, calls, called-by, inherits, inherited-by.
    """

    # noinspection PyDefaultArgument
    def apply(
        self,
        cursor_id: str,
        edge_types: list[str] = [],  # noqa: B006
        include_body: bool = False,
    ) -> str:
        """
        Configure the cursor's active edge types and display options.

        :param cursor_id: the ID of the cursor to configure.
        :param edge_types: list of edge type names to enable. If empty, all edge types are enabled.
            Valid values: contains, references, referenced-by, calls, called-by, inherits, inherited-by.
        :param include_body: whether to include the symbol's source code body in the cursor view.
        :return: confirmation of the new configuration and updated cursor view.
        """
        manager = self.agent.get_cursor_manager()
        state = manager.get_cursor(cursor_id)

        if edge_types:
            valid_types: set[EdgeType] = set()
            for name in edge_types:
                try:
                    valid_types.add(EdgeType(name))
                except ValueError:
                    valid_names = [e.value for e in EdgeType]
                    raise ValueError(f"Unknown edge type '{name}'. Valid edge types: {valid_names}")
            state.active_edge_types = frozenset(valid_types)
        else:
            state.active_edge_types = frozenset(EdgeType)

        state.include_body = include_body

        return manager.format_cursor_view(cursor_id)


class CursorHistoryTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Show the trail of symbols visited by a cursor, from start to current position.
    """

    def apply(self, cursor_id: str) -> str:
        """
        Show the navigation trail for a cursor.

        :param cursor_id: the ID of the cursor.
        :return: the formatted trail showing each visited location.
        """
        manager = self.agent.get_cursor_manager()
        return manager.format_trail(cursor_id)


class CursorCloseTool(Tool, ToolMarkerSymbolicRead, ToolMarkerOptional):
    """
    Close a navigation cursor and free its resources.
    """

    def apply(self, cursor_id: str) -> str:
        """
        Close a cursor.

        :param cursor_id: the ID of the cursor to close.
        :return: confirmation that the cursor was closed.
        """
        manager = self.agent.get_cursor_manager()
        manager.close_cursor(cursor_id)
        return f"Cursor {cursor_id} closed."
