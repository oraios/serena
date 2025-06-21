"""Tests for the mcp.py module in serena."""

import pytest
from mcp.server.fastmcp.tools.base import Tool as MCPTool

from serena.agent import Tool, ToolRegistry
from serena.mcp import SerenaMCPFactory

make_tool = SerenaMCPFactory.make_mcp_tool


class BaseMockTool(Tool):
    """A mock Tool class for testing."""

    def __init__(self) -> None:
        pass


class BasicTool(BaseMockTool):
    """A mock Tool class for testing."""

    def apply(self, name: str, age: int = 0) -> str:
        """This is a test function.

        :param name: The person's name
        :param age: The person's age
        :return: A greeting message
        """
        return f"Hello {name}, you are {age} years old!"

    def apply_ex(
        self,
        log_call: bool = True,
        catch_exceptions: bool = True,
        **kwargs,
    ) -> str:
        """Mock implementation of apply_ex."""
        return self.apply(**kwargs)


def test_make_tool_basic() -> None:
    """Test that make_tool correctly creates an MCP tool from a Tool object."""
    mock_tool = BasicTool()

    mcp_tool = make_tool(mock_tool)

    # Test that the MCP tool has the correct properties
    assert isinstance(mcp_tool, MCPTool)
    assert mcp_tool.name == "basic"
    assert "This is a test function. Returns A greeting message." in mcp_tool.description

    # Test that the parameters were correctly processed
    parameters = mcp_tool.parameters
    assert "properties" in parameters
    assert "name" in parameters["properties"]
    assert "age" in parameters["properties"]
    assert parameters["properties"]["name"]["description"] == "The person's name."
    assert parameters["properties"]["age"]["description"] == "The person's age."


def test_make_tool_execution() -> None:
    """Test that the execution function created by make_tool works correctly."""
    mock_tool = BasicTool()
    mcp_tool = make_tool(mock_tool)

    # Execute the MCP tool function
    result = mcp_tool.fn(name="Alice", age=30)

    assert result == "Hello Alice, you are 30 years old!"


def test_make_tool_no_params() -> None:
    """Test make_tool with a function that has no parameters."""

    class NoParamsTool(BaseMockTool):
        def apply(self) -> str:
            """This is a test function with no parameters.

            :return: A simple result
            """
            return "Simple result"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply()

    tool = NoParamsTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.name == "no_params"
    assert "This is a test function with no parameters. Returns A simple result." in mcp_tool.description
    assert mcp_tool.parameters["properties"] == {}


def test_make_tool_no_return_description() -> None:
    """Test make_tool with a function that has no return description."""

    class NoReturnTool(BaseMockTool):
        def apply(self, param: str) -> str:
            """This is a test function.

            :param param: The parameter
            """
            return f"Processed: {param}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = NoReturnTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.name == "no_return"
    assert mcp_tool.description == "This is a test function."
    assert mcp_tool.parameters["properties"]["param"]["description"] == "The parameter."


def test_make_tool_parameter_not_in_docstring() -> None:
    """Test make_tool when a parameter in properties is not in the docstring."""

    class MissingParamTool(BaseMockTool):
        def apply(self, name: str, missing_param: str = "") -> str:
            """This is a test function.

            :param name: The person's name
            """
            return f"Hello {name}! Missing param: {missing_param}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = MissingParamTool()
    mcp_tool = make_tool(tool)

    assert "name" in mcp_tool.parameters["properties"]
    assert "missing_param" in mcp_tool.parameters["properties"]
    assert mcp_tool.parameters["properties"]["name"]["description"] == "The person's name."
    assert "description" not in mcp_tool.parameters["properties"]["missing_param"]


def test_make_tool_multiline_docstring() -> None:
    """Test make_tool with a complex multi-line docstring."""

    class ComplexDocTool(BaseMockTool):
        def apply(self, project_file_path: str, host: str, port: int) -> str:
            """Create an MCP server.

            This function creates and configures a Model Context Protocol server
            with the specified settings.

            :param project_file_path: The path to the project file, or None
            :param host: The host to bind to
            :param port: The port to bind to
            :return: A configured FastMCP server instance
            """
            return f"Server config: {project_file_path}, {host}:{port}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = ComplexDocTool()
    mcp_tool = make_tool(tool)

    assert "Create an MCP server" in mcp_tool.description
    assert "Returns A configured FastMCP server instance" in mcp_tool.description
    assert mcp_tool.parameters["properties"]["project_file_path"]["description"] == "The path to the project file, or None."
    assert mcp_tool.parameters["properties"]["host"]["description"] == "The host to bind to."
    assert mcp_tool.parameters["properties"]["port"]["description"] == "The port to bind to."


def test_make_tool_capitalization_and_periods() -> None:
    """Test that make_tool properly handles capitalization and periods in descriptions."""

    class FormatTool(BaseMockTool):
        def apply(self, param1: str, param2: str, param3: str) -> str:
            """Test function.

            :param param1: lowercase description
            :param param2: description with period.
            :param param3: description with Capitalized word.
            """
            return f"Formatted: {param1}, {param2}, {param3}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    tool = FormatTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.parameters["properties"]["param1"]["description"] == "Lowercase description."
    assert mcp_tool.parameters["properties"]["param2"]["description"] == "Description with period."
    assert mcp_tool.parameters["properties"]["param3"]["description"] == "Description with Capitalized word."


def test_make_tool_missing_apply() -> None:
    """Test make_tool with a tool that doesn't have an apply method."""

    class BadTool(BaseMockTool):
        pass

    tool = BadTool()

    with pytest.raises(AttributeError):
        make_tool(tool)


@pytest.mark.parametrize(
    "docstring, expected_description",
    [
        (
            """This is a test function.

            :param param: The parameter
            :return: A result
            """,
            "This is a test function. Returns A result.",
        ),
        (
            """
            :param param: The parameter
            :return: A result
            """,
            "Returns A result.",
        ),
        (
            """
            :param param: The parameter
            """,
            "",
        ),
        ("Description without params.", "Description without params."),
    ],
)
def test_make_tool_descriptions(docstring, expected_description) -> None:
    """Test make_tool with various docstring formats."""

    class TestTool(BaseMockTool):
        def apply(self, param: str) -> str:
            return f"Result: {param}"

        def apply_ex(self, *args, **kwargs) -> str:
            return self.apply(**kwargs)

    # Dynamically set the docstring
    TestTool.apply.__doc__ = docstring

    tool = TestTool()
    mcp_tool = make_tool(tool)

    assert mcp_tool.name == "test"
    assert mcp_tool.description == expected_description


def is_test_mock_class(tool_class: type) -> bool:
    """Check if a class is a test mock class."""
    # Check if the class is defined in a test module
    module_name = tool_class.__module__
    return (
        module_name.startswith(("test.", "tests."))
        or "test_" in module_name
        or tool_class.__name__
        in [
            "BaseMockTool",
            "BasicTool",
            "BadTool",
            "NoParamsTool",
            "NoReturnTool",
            "MissingParamTool",
            "ComplexDocTool",
            "FormatTool",
            "NoDescriptionTool",
        ]
    )


@pytest.mark.parametrize("tool_class", ToolRegistry.get_all_tool_classes())
def test_make_tool_all_tools(tool_class) -> None:
    """Test that make_tool works for all tools in the codebase."""

    # Create a mock agent for tool initialization
    class MockAgent:
        def __init__(self):
            self.project_config = None
            self.serena_config = None

    # Create an instance of the tool
    tool_instance = tool_class(MockAgent())

    # Try to create an MCP tool from it
    mcp_tool = make_tool(tool_instance)

    # Basic validation
    assert isinstance(mcp_tool, MCPTool)
    assert mcp_tool.name == tool_class.get_name_from_cls()

    # The description should be a string (either from docstring or default)
    assert isinstance(mcp_tool.description, str)
