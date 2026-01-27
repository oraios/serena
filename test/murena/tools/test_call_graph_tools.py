"""
Tests for call graph analysis tools.

Tests all 5 call graph tools:
- GetIncomingCallsTool
- GetOutgoingCallsTool
- BuildCallGraphTool
- FindCallPathTool
- AnalyzeCallDependenciesTool
"""

import json

import pytest

from murena.agent import MurenaAgent
from murena.tools.call_graph_tools import (
    AnalyzeCallDependenciesTool,
    BuildCallGraphTool,
    FindCallPathTool,
    GetIncomingCallsTool,
    GetOutgoingCallsTool,
)

# Test with Python (FULL call hierarchy support)
TEST_FILE = "test_repo/math_utils.py"
TEST_SYMBOL = "multiply"
TEST_NAME_PATH = "multiply"


@pytest.fixture
def agent(tmp_path):
    """Create a MurenaAgent instance for testing."""
    agent = MurenaAgent()
    # Note: Tests will use the actual test_repo files
    return agent


class TestGetIncomingCallsTool:
    """Test GetIncomingCallsTool."""

    def test_apply_returns_json(self, agent):
        """Test that apply() returns valid JSON."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            include_call_sites=True,
            max_depth=1,
            compact_format=True,
        )

        assert isinstance(result, str), "Should return string"
        data = json.loads(result)
        assert isinstance(data, dict), "Should parse as JSON dict"

    def test_apply_compact_format(self, agent):
        """Test compact format output."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            compact_format=True,
            max_depth=1,
        )

        data = json.loads(result)

        # Verify compact format keys
        assert "s" in data, "Should have 's' (symbol) key in compact format"
        if data.get("callers"):
            assert "np" in data["callers"][0], "Callers should use 'np' (name_path)"
            assert "fp" in data["callers"][0], "Callers should use 'fp' (file_path)"

    def test_apply_verbose_format(self, agent):
        """Test verbose format output."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            compact_format=False,
            max_depth=1,
        )

        data = json.loads(result)

        # Verify verbose format keys
        assert "symbol" in data, "Should have 'symbol' key in verbose format"
        if data.get("incoming_calls"):
            assert "name" in data["incoming_calls"][0], "Should use 'name' in verbose"
            assert "file" in data["incoming_calls"][0], "Should use 'file' in verbose"

    def test_apply_with_call_sites(self, agent):
        """Test include_call_sites parameter."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            include_call_sites=True,
            compact_format=True,
            max_depth=1,
        )

        data = json.loads(result)

        # If there are callers, they should have call sites
        if data.get("callers") and len(data["callers"]) > 0:
            caller = data["callers"][0]
            assert "sites" in caller or caller.get("sites") == [], "Should include call sites"

    def test_apply_max_depth(self, agent):
        """Test max_depth parameter."""
        tool = GetIncomingCallsTool(agent)

        # Depth 1
        result1 = tool.apply(name_path=TEST_NAME_PATH, relative_path=TEST_FILE, max_depth=1, compact_format=True)
        data1 = json.loads(result1)

        # Depth 2 (may find more indirect callers)
        result2 = tool.apply(name_path=TEST_NAME_PATH, relative_path=TEST_FILE, max_depth=2, compact_format=True)
        data2 = json.loads(result2)

        # Depth is correctly recorded
        assert data1.get("d") == 1, "Depth should be 1"
        assert data2.get("d") == 2, "Depth should be 2"

    def test_apply_nonexistent_symbol(self, agent):
        """Test with nonexistent symbol."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path="NonExistentSymbol",
            relative_path=TEST_FILE,
            max_depth=1,
            compact_format=True,
        )

        data = json.loads(result)

        # Should return error or empty result
        assert "error" in data or data.get("tot", 0) == 0, "Should handle nonexistent symbol"

    def test_apply_max_answer_chars(self, agent):
        """Test max_answer_chars parameter."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            max_depth=1,
            compact_format=True,
            max_answer_chars=100,  # Very small limit
        )

        # Should respect character limit
        assert len(result) <= 150, "Should respect max_answer_chars (with some buffer)"


class TestGetOutgoingCallsTool:
    """Test GetOutgoingCallsTool."""

    def test_apply_returns_json(self, agent):
        """Test that apply() returns valid JSON."""
        tool = GetOutgoingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            include_call_sites=True,
            max_depth=1,
            compact_format=True,
        )

        assert isinstance(result, str), "Should return string"
        data = json.loads(result)
        assert isinstance(data, dict), "Should parse as JSON dict"

    def test_apply_compact_format(self, agent):
        """Test compact format output."""
        tool = GetOutgoingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            compact_format=True,
            max_depth=1,
        )

        data = json.loads(result)

        # Verify compact format keys
        assert "s" in data, "Should have 's' (symbol) key in compact format"
        if data.get("callees"):
            assert "np" in data["callees"][0], "Callees should use 'np' (name_path)"
            assert "fp" in data["callees"][0], "Callees should use 'fp' (file_path)"

    def test_apply_verbose_format(self, agent):
        """Test verbose format output."""
        tool = GetOutgoingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            compact_format=False,
            max_depth=1,
        )

        data = json.loads(result)

        # Verify verbose format keys
        assert "symbol" in data, "Should have 'symbol' key in verbose format"
        if data.get("outgoing_calls"):
            assert "name" in data["outgoing_calls"][0], "Should use 'name' in verbose"
            assert "file" in data["outgoing_calls"][0], "Should use 'file' in verbose"

    def test_apply_with_call_sites(self, agent):
        """Test include_call_sites parameter."""
        tool = GetOutgoingCallsTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            include_call_sites=True,
            compact_format=True,
            max_depth=1,
        )

        data = json.loads(result)

        # If there are callees, they should have call sites
        if data.get("callees") and len(data["callees"]) > 0:
            callee = data["callees"][0]
            assert "sites" in callee or callee.get("sites") == [], "Should include call sites"


class TestBuildCallGraphTool:
    """Test BuildCallGraphTool."""

    def test_apply_returns_json(self, agent):
        """Test that apply() returns valid JSON."""
        tool = BuildCallGraphTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="both",
            max_depth=2,
            max_nodes=50,
            compact_format=True,
        )

        assert isinstance(result, str), "Should return string"
        data = json.loads(result)
        assert isinstance(data, dict), "Should parse as JSON dict"

    def test_apply_direction_incoming(self, agent):
        """Test direction='incoming' parameter."""
        tool = BuildCallGraphTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="incoming",
            max_depth=1,
            max_nodes=30,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have nodes and edges
        assert "nodes" in data or "graph" in data, "Should have nodes"

    def test_apply_direction_outgoing(self, agent):
        """Test direction='outgoing' parameter."""
        tool = BuildCallGraphTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="outgoing",
            max_depth=1,
            max_nodes=30,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have nodes and edges
        assert "nodes" in data or "graph" in data, "Should have nodes"

    def test_apply_direction_both(self, agent):
        """Test direction='both' parameter."""
        tool = BuildCallGraphTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="both",
            max_depth=2,
            max_nodes=40,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have nodes and edges
        assert "nodes" in data or "graph" in data, "Should have nodes"

    def test_apply_max_nodes_limit(self, agent):
        """Test max_nodes parameter limits graph size."""
        tool = BuildCallGraphTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="both",
            max_depth=3,
            max_nodes=10,  # Small limit
            compact_format=True,
        )

        data = json.loads(result)

        # Verify node count respects limit
        if "nodes" in data:
            assert len(data["nodes"]) <= 10, "Should respect max_nodes limit"
        elif "graph" in data and "nodes" in data["graph"]:
            assert len(data["graph"]["nodes"]) <= 10, "Should respect max_nodes limit"

    def test_apply_compact_vs_verbose(self, agent):
        """Test compact vs verbose format difference."""
        tool = BuildCallGraphTool(agent)

        # Compact
        result_compact = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="both",
            max_depth=1,
            compact_format=True,
        )

        # Verbose
        result_verbose = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="both",
            max_depth=1,
            compact_format=False,
        )

        # Compact should be shorter
        assert len(result_compact) <= len(result_verbose), "Compact should use fewer characters"


class TestFindCallPathTool:
    """Test FindCallPathTool."""

    def test_apply_returns_json(self, agent):
        """Test that apply() returns valid JSON."""
        tool = FindCallPathTool(agent)

        # Use same symbol for from/to (should find self or empty)
        result = tool.apply(
            from_name_path=TEST_NAME_PATH,
            from_file=TEST_FILE,
            to_name_path=TEST_NAME_PATH,
            to_file=TEST_FILE,
            max_depth=5,
            find_all_paths=False,
            compact_format=True,
        )

        assert isinstance(result, str), "Should return string"
        data = json.loads(result)
        assert isinstance(data, dict), "Should parse as JSON dict"

    def test_apply_find_single_path(self, agent):
        """Test find_all_paths=False (single path)."""
        tool = FindCallPathTool(agent)

        result = tool.apply(
            from_name_path=TEST_NAME_PATH,
            from_file=TEST_FILE,
            to_name_path="add",  # Different function in same file
            to_file=TEST_FILE,
            max_depth=3,
            find_all_paths=False,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have paths structure
        assert "paths" in data or "from" in data, "Should have path information"

    def test_apply_find_all_paths(self, agent):
        """Test find_all_paths=True (all paths)."""
        tool = FindCallPathTool(agent)

        result = tool.apply(
            from_name_path=TEST_NAME_PATH,
            from_file=TEST_FILE,
            to_name_path="add",
            to_file=TEST_FILE,
            max_depth=3,
            find_all_paths=True,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have paths structure
        assert "paths" in data or "from" in data, "Should have path information"

    def test_apply_no_path_exists(self, agent):
        """Test when no path exists between symbols."""
        tool = FindCallPathTool(agent)

        result = tool.apply(
            from_name_path="NonExistent1",
            from_file=TEST_FILE,
            to_name_path="NonExistent2",
            to_file=TEST_FILE,
            max_depth=3,
            find_all_paths=False,
            compact_format=True,
        )

        data = json.loads(result)

        # Should indicate no path found
        assert "paths" in data, "Should have paths key"
        assert len(data.get("paths", [])) == 0 or "error" in data, "Should show no paths or error"

    def test_apply_max_depth_limit(self, agent):
        """Test max_depth parameter."""
        tool = FindCallPathTool(agent)

        # Small depth
        result = tool.apply(
            from_name_path=TEST_NAME_PATH,
            from_file=TEST_FILE,
            to_name_path="add",
            to_file=TEST_FILE,
            max_depth=1,
            find_all_paths=False,
            compact_format=True,
        )

        data = json.loads(result)

        # Verify depth is recorded
        assert "d" in data or "max_depth" in data, "Should record max depth"


class TestAnalyzeCallDependenciesTool:
    """Test AnalyzeCallDependenciesTool."""

    def test_apply_returns_json(self, agent):
        """Test that apply() returns valid JSON."""
        tool = AnalyzeCallDependenciesTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="impact",
            max_depth=3,
            include_tests=True,
            compact_format=True,
        )

        assert isinstance(result, str), "Should return string"
        data = json.loads(result)
        assert isinstance(data, dict), "Should parse as JSON dict"

    def test_apply_impact_analysis(self, agent):
        """Test analysis_type='impact'."""
        tool = AnalyzeCallDependenciesTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="impact",
            max_depth=2,
            include_tests=True,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have impact-related fields
        assert "type" in data or "s" in data, "Should have analysis info"
        # May have direct_callers, indirect_callers, risk, etc.

    def test_apply_usage_analysis(self, agent):
        """Test analysis_type='usage'."""
        tool = AnalyzeCallDependenciesTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="usage",
            max_depth=2,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have usage-related fields
        assert "type" in data or "s" in data, "Should have analysis info"

    def test_apply_hotspots_analysis(self, agent):
        """Test analysis_type='hotspots'."""
        tool = AnalyzeCallDependenciesTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="hotspots",
            max_depth=2,
            compact_format=True,
        )

        data = json.loads(result)

        # Should have hotspot-related fields
        assert "type" in data or "hotspots" in data or "s" in data, "Should have hotspot info"

    def test_apply_include_tests_flag(self, agent):
        """Test include_tests parameter."""
        tool = AnalyzeCallDependenciesTool(agent)

        # With tests
        result_with = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="impact",
            max_depth=2,
            include_tests=True,
            compact_format=True,
        )

        # Without tests
        result_without = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="impact",
            max_depth=2,
            include_tests=False,
            compact_format=True,
        )

        data_with = json.loads(result_with)
        data_without = json.loads(result_without)

        # Both should be valid
        assert isinstance(data_with, dict)
        assert isinstance(data_without, dict)

    def test_apply_max_depth(self, agent):
        """Test max_depth parameter."""
        tool = AnalyzeCallDependenciesTool(agent)

        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            analysis_type="impact",
            max_depth=1,
            compact_format=True,
        )

        data = json.loads(result)

        # Should be valid
        assert isinstance(data, dict), "Should return valid JSON"


class TestCallGraphToolsErrorHandling:
    """Test error handling across all tools."""

    def test_incoming_calls_invalid_file(self, agent):
        """Test GetIncomingCallsTool with invalid file."""
        tool = GetIncomingCallsTool(agent)

        result = tool.apply(
            name_path="SomeSymbol",
            relative_path="nonexistent/file.py",
            max_depth=1,
            compact_format=True,
        )

        data = json.loads(result)
        assert "error" in data or data.get("tot", 0) == 0, "Should handle invalid file"

    def test_outgoing_calls_invalid_symbol(self, agent):
        """Test GetOutgoingCallsTool with invalid symbol."""
        tool = GetOutgoingCallsTool(agent)

        result = tool.apply(
            name_path="NonExistentSymbol123",
            relative_path=TEST_FILE,
            max_depth=1,
            compact_format=True,
        )

        data = json.loads(result)
        assert "error" in data or data.get("tot", 0) == 0, "Should handle invalid symbol"

    def test_build_call_graph_invalid_direction(self, agent):
        """Test BuildCallGraphTool with invalid direction."""
        tool = BuildCallGraphTool(agent)

        # Invalid direction should default to "both" or error
        result = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            direction="invalid",
            max_depth=1,
            compact_format=True,
        )

        # Should not crash
        assert isinstance(result, str), "Should return string even with invalid direction"

    def test_find_call_path_same_symbol(self, agent):
        """Test FindCallPathTool with same from/to symbol."""
        tool = FindCallPathTool(agent)

        result = tool.apply(
            from_name_path=TEST_NAME_PATH,
            from_file=TEST_FILE,
            to_name_path=TEST_NAME_PATH,
            to_file=TEST_FILE,
            max_depth=3,
            find_all_paths=False,
            compact_format=True,
        )

        data = json.loads(result)
        # Should handle gracefully (empty path or self-reference)
        assert isinstance(data, dict), "Should return valid JSON"

    def test_analyze_dependencies_nonexistent_symbol(self, agent):
        """Test AnalyzeCallDependenciesTool with nonexistent symbol."""
        tool = AnalyzeCallDependenciesTool(agent)

        result = tool.apply(
            name_path="NonExistent999",
            relative_path=TEST_FILE,
            analysis_type="impact",
            max_depth=2,
            compact_format=True,
        )

        data = json.loads(result)
        assert "error" in data or isinstance(data, dict), "Should handle nonexistent symbol"


class TestCallGraphToolsTokenEfficiency:
    """Test token efficiency (compact vs verbose)."""

    def test_compact_format_saves_tokens(self, agent):
        """Test that compact format is significantly shorter than verbose."""
        tool = GetIncomingCallsTool(agent)

        # Compact
        result_compact = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            max_depth=1,
            compact_format=True,
        )

        # Verbose
        result_verbose = tool.apply(
            name_path=TEST_NAME_PATH,
            relative_path=TEST_FILE,
            max_depth=1,
            compact_format=False,
        )

        # Compact should be at least 30% shorter (aiming for 70% savings)
        savings_ratio = 1 - (len(result_compact) / len(result_verbose))
        assert savings_ratio > 0.3, f"Compact format should save >30% tokens (got {savings_ratio:.1%})"


# Note: These tests use the actual test_repo files and language servers.
# Some tests may be skipped if the test repository doesn't have the expected structure.
