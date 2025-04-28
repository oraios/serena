from serena.agent import CreateTextFileTool, ReadFileTool, Tool


class TestEditMarker:
    def test_tool_can_edit_method(self):
        """Test that Tool.can_edit() method works correctly"""
        # Non-editing tool should return False
        assert issubclass(ReadFileTool, Tool)
        assert not ReadFileTool.can_edit()

        # Editing tool should return True
        assert issubclass(CreateTextFileTool, Tool)
        assert CreateTextFileTool.can_edit()
