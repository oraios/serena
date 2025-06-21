"""Tests for make_tool consistency between regular tools and ProcessIsolatedTool."""

import pytest
from mcp.server.fastmcp.tools.base import Tool as MCPTool

from serena.agent import SerenaAgent, ToolRegistry
from serena.mcp import SerenaMCPFactory
from serena.process_isolated_agent import ProcessIsolatedSerenaAgent, ProcessIsolatedTool
from test.serena.test_serena_agent import SerenaConfigForTests

make_tool = SerenaMCPFactory.make_mcp_tool


@pytest.fixture
def in_memory_config():
    """Create an in-memory configuration for tests."""
    return SerenaConfigForTests()


@pytest.fixture
def regular_agent(in_memory_config):
    """Create a regular SerenaAgent for comparison."""
    return SerenaAgent(serena_config=in_memory_config)


@pytest.fixture
def process_isolated_agent(in_memory_config):
    """Create a ProcessIsolatedSerenaAgent for comparison."""
    agent = ProcessIsolatedSerenaAgent(serena_config=in_memory_config)
    agent.start()
    yield agent
    agent.stop()


class TestMakeToolProcessIsolation:
    """Test that make_tool produces identical metadata for regular and process-isolated tools."""

    @pytest.mark.parametrize("tool_name", ToolRegistry.get_tool_names())
    def test_make_tool_metadata_consistency(
        self, tool_name: str, regular_agent: SerenaAgent, process_isolated_agent: ProcessIsolatedSerenaAgent
    ):
        """Test that make_tool produces identical metadata for regular and process-isolated tools."""
        # Get regular tool instance
        tool_class = ToolRegistry.get_tool_class_by_name(tool_name)
        regular_tool = regular_agent.get_tool(tool_class)

        # Get ProcessIsolatedTool instance
        isolated_tool = ProcessIsolatedTool(process_isolated_agent, tool_name)

        # Create MCP tools from both
        regular_mcp_tool = make_tool(regular_tool)
        isolated_mcp_tool = make_tool(isolated_tool)

        # Verify both are MCPTool instances
        assert isinstance(regular_mcp_tool, MCPTool)
        assert isinstance(isolated_mcp_tool, MCPTool)

        # Test name consistency
        assert regular_mcp_tool.name == isolated_mcp_tool.name
        assert regular_mcp_tool.name == tool_name

        # Test description consistency
        assert regular_mcp_tool.description == isolated_mcp_tool.description, (
            f"Tool {tool_name}: descriptions differ\n"
            f"Regular: {regular_mcp_tool.description}\n"
            f"Isolated: {isolated_mcp_tool.description}"
        )

        # Test parameters schema consistency
        assert regular_mcp_tool.parameters == isolated_mcp_tool.parameters, (
            f"Tool {tool_name}: parameter schemas differ\n"
            f"Regular: {regular_mcp_tool.parameters}\n"
            f"Isolated: {isolated_mcp_tool.parameters}"
        )

        # Test function metadata consistency (compare schemas, not class objects)
        regular_schema = regular_mcp_tool.fn_metadata.arg_model.model_json_schema()
        isolated_schema = isolated_mcp_tool.fn_metadata.arg_model.model_json_schema()
        assert (
            regular_schema == isolated_schema
        ), f"Tool {tool_name}: function metadata schemas differ\nRegular: {regular_schema}\nIsolated: {isolated_schema}"

        # Test async flag consistency
        assert regular_mcp_tool.is_async == isolated_mcp_tool.is_async

        # Test context kwarg consistency
        assert regular_mcp_tool.context_kwarg == isolated_mcp_tool.context_kwarg

    @pytest.mark.parametrize("tool_name", ToolRegistry.get_tool_names()[:5])  # Test first 5 tools for faster execution
    def test_tool_protocol_methods_consistency(
        self, tool_name: str, regular_agent: SerenaAgent, process_isolated_agent: ProcessIsolatedSerenaAgent
    ):
        """Test that Tool methods return identical results for regular and process-isolated tools."""
        # Get regular tool instance
        tool_class = ToolRegistry.get_tool_class_by_name(tool_name)
        regular_tool = regular_agent.get_tool(tool_class)

        # Get ProcessIsolatedTool instance
        isolated_tool = ProcessIsolatedTool(process_isolated_agent, tool_name)

        # Test get_name()
        assert regular_tool.get_name_from_cls() == isolated_tool.get_name()
        assert regular_tool.get_name_from_cls() == tool_name

        # Test get_apply_docstring()
        regular_docstring = regular_tool.get_apply_docstring()
        isolated_docstring = isolated_tool.get_apply_docstring()
        assert (
            regular_docstring == isolated_docstring
        ), f"Tool {tool_name}: docstrings differ\nRegular: {regular_docstring}\nIsolated: {isolated_docstring}"

        # Test get_apply_fn_metadata()
        regular_metadata = regular_tool.get_apply_fn_metadata()
        isolated_metadata = isolated_tool.get_apply_fn_metadata()

        # Compare metadata properties (compare schemas, not class objects)
        regular_schema = regular_metadata.arg_model.model_json_schema()
        isolated_schema = isolated_metadata.arg_model.model_json_schema()
        assert (
            regular_schema == isolated_schema
        ), f"Tool {tool_name}: metadata schemas differ\nRegular: {regular_schema}\nIsolated: {isolated_schema}"

    def test_process_isolated_tool_uses_tool_registry(self, process_isolated_agent: ProcessIsolatedSerenaAgent):
        """Test that ProcessIsolatedTool correctly uses ToolRegistry for metadata."""
        tool_name = ToolRegistry.get_tool_names()[0]  # Use first available tool
        isolated_tool = ProcessIsolatedTool(process_isolated_agent, tool_name)

        # Verify that the tool uses ToolRegistry
        assert isolated_tool._tool_class == ToolRegistry.get_tool_class_by_name(tool_name)

        # Verify that metadata comes from the tool class
        expected_docstring = isolated_tool._tool_class.get_apply_docstring_from_cls()
        expected_metadata = isolated_tool._tool_class.get_apply_fn_metadata_from_cls()

        assert isolated_tool.get_apply_docstring() == expected_docstring
        # Compare schemas, not class objects
        isolated_schema = isolated_tool.get_apply_fn_metadata().arg_model.model_json_schema()
        expected_schema = expected_metadata.arg_model.model_json_schema()
        assert isolated_schema == expected_schema

    def test_tool_registry_completeness(self, regular_agent: SerenaAgent, process_isolated_agent: ProcessIsolatedSerenaAgent):
        """Test that all tools are available in both agents and the registry."""
        # Get tool names from both agents
        regular_active_tools = set(regular_agent.get_active_tool_names())
        regular_all_tools = set(tool.get_name_from_cls() for tool in regular_agent.get_exposed_tool_instances())
        isolated_tool_names = set(process_isolated_agent.get_exposed_tool_names())

        # The process isolated agent should have all tools (exposed, not just active)
        assert regular_all_tools == isolated_tool_names, (
            f"Tool sets differ:\n"
            f"Regular exposed only: {regular_all_tools - isolated_tool_names}\n"
            f"Isolated only: {isolated_tool_names - regular_all_tools}"
        )

        # Active tools should be a subset of all tools
        assert regular_active_tools.issubset(
            regular_all_tools
        ), f"Some active tools not in exposed tools: {regular_active_tools - regular_all_tools}"

        # All tools should be in the registry
        registry_tool_names = set(ToolRegistry.get_tool_names())
        assert regular_all_tools.issubset(registry_tool_names), f"Some tools not in registry: {regular_all_tools - registry_tool_names}"
