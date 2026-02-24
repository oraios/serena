"""Tests for the cross-project query tool."""

from serena.tools.remote_tools import ALLOWED_REMOTE_TOOLS


class TestQueryRemoteProjectAllowlist:
    def test_only_read_only_tools_allowed(self) -> None:
        """All allowed remote tools should be read-only (not editing tools)."""
        editing_tools = {
            "replace_content",
            "replace_symbol_body",
            "insert_after_symbol",
            "insert_before_symbol",
            "rename_symbol",
            "create_text_file",
            "write_memory",
            "delete_memory",
            "edit_memory",
            "rename_memory",
        }
        for tool_name in ALLOWED_REMOTE_TOOLS:
            assert tool_name not in editing_tools

    def test_expected_tools_present(self) -> None:
        """Key read-only tools should be in the allowlist."""
        expected = {"find_symbol", "get_symbols_overview", "search_for_pattern", "read_file", "list_dir"}
        for tool_name in expected:
            assert tool_name in ALLOWED_REMOTE_TOOLS
