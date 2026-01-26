"""
Unit tests for composite tools.
"""

from murena.tools.composite.base import CompositeResult, CompositeStep, CompositeTool


class MockTool:
    """Mock tool for testing."""

    def __init__(self, return_value):
        self.return_value = return_value
        self.calls = []

    def apply_ex(self, **kwargs):
        self.calls.append(kwargs)
        return self.return_value


class MockAgent:
    """Mock agent for testing."""

    def __init__(self):
        self.tools = {}

    def add_tool(self, name, tool):
        self.tools[name] = tool

    def get_tool_by_name(self, name):
        return self.tools.get(name)


class TestCompositeStep:
    """Test the CompositeStep dataclass."""

    def test_create_step(self):
        """Test creating a composite step."""
        step = CompositeStep(
            tool_name="test_tool",
            params={"arg1": "value1"},
            result_key="test_result",
        )

        assert step.tool_name == "test_tool"
        assert step.params == {"arg1": "value1"}
        assert step.result_key == "test_result"
        assert step.condition is None
        assert step.error_handler is None


class TestCompositeResult:
    """Test the CompositeResult dataclass."""

    def test_create_result(self):
        """Test creating a composite result."""
        result = CompositeResult(
            success=True,
            results={"step1": "result1"},
            final_result="final",
            steps_executed=1,
        )

        assert result.success is True
        assert result.results == {"step1": "result1"}
        assert result.final_result == "final"
        assert result.steps_executed == 1
        assert result.error is None


class SimpleCompositeTool(CompositeTool):
    """Simple composite tool for testing."""

    @staticmethod
    def get_name_from_cls():
        return "simple_composite"

    def get_steps(self, **kwargs):
        return [
            CompositeStep(tool_name="tool1", params={"input": kwargs.get("input")}, result_key="step1"),
            CompositeStep(tool_name="tool2", params={"input": "${step1}"}, result_key="step2"),
        ]

    def format_result(self, composite_result):
        return f"Success: {composite_result.results.get('step2')}"


class TestCompositeTool:
    """Test the CompositeTool base class."""

    def test_execute_composite_success(self):
        """Test successful composite execution."""
        agent = MockAgent()
        agent.add_tool("tool1", MockTool("result1"))
        agent.add_tool("tool2", MockTool("result2"))

        tool = SimpleCompositeTool(agent)
        result = tool.execute_composite(input="test")

        assert "Success: result2" in result

    def test_parameter_interpolation(self):
        """Test parameter interpolation between steps."""
        agent = MockAgent()
        tool1 = MockTool("interpolated_value")
        tool2 = MockTool("final_result")

        agent.add_tool("tool1", tool1)
        agent.add_tool("tool2", tool2)

        tool = SimpleCompositeTool(agent)
        tool.execute_composite(input="test")

        # Check that tool2 received interpolated parameter
        assert tool2.calls[0]["input"] == "interpolated_value"

    def test_error_handling(self):
        """Test error handling in composite execution."""
        agent = MockAgent()
        agent.add_tool("tool1", MockTool("result1"))

        # tool2 will fail because it doesn't exist
        tool = SimpleCompositeTool(agent)
        result = tool.execute_composite(input="test")

        assert "Error" in result

    def test_conditional_step(self):
        """Test conditional step execution."""

        class ConditionalTool(CompositeTool):
            @staticmethod
            def get_name_from_cls():
                return "conditional"

            def get_steps(self, **kwargs):
                return [
                    CompositeStep(tool_name="tool1", params={}, result_key="step1"),
                    CompositeStep(
                        tool_name="tool2",
                        params={},
                        result_key="step2",
                        condition=lambda ctx: ctx.get("execute_step2", False),
                    ),
                ]

            def format_result(self, composite_result):
                return str(composite_result.results)

        agent = MockAgent()
        agent.add_tool("tool1", MockTool("result1"))
        agent.add_tool("tool2", MockTool("result2"))

        tool = ConditionalTool(agent)

        # Without condition met
        result1 = tool.execute_composite(execute_step2=False)
        assert "step2" not in result1

        # With condition met
        result2 = tool.execute_composite(execute_step2=True)
        assert "step2" in result2
