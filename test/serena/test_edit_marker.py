from serena.generated.tool_capabilities import EDIT_CAPABLE_TOOL_NAMES
from serena.tools import CreateTextFileTool, ReadFileTool, Tool, ToolRegistry


class TestEditMarker:
    def test_tool_can_edit_method(self):
        """Test that Tool.can_edit() method works correctly"""
        # Non-editing tool should return False
        assert issubclass(ReadFileTool, Tool)
        assert not ReadFileTool.can_edit()

        # Editing tool should return True
        assert issubclass(CreateTextFileTool, Tool)
        assert CreateTextFileTool.can_edit()

    def test_generated_edit_capabilities_match_tool_metadata(self):
        registry = ToolRegistry()
        expected_edit_capabilities = frozenset(
            tool_class.get_name_from_cls() for tool_class in registry.get_all_tool_classes() if tool_class.can_edit()
        )

        assert expected_edit_capabilities == EDIT_CAPABLE_TOOL_NAMES
