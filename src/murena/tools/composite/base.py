"""
Base classes for composite tools.

Composite tools combine multiple atomic operations into cohesive workflows,
reducing token consumption and round-trips for common patterns.
"""

import logging
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from murena.tools.tools_base import Tool

log = logging.getLogger(__name__)


@dataclass
class CompositeStep:
    """A single step in a composite tool workflow.

    Attributes:
        tool_name: Name of the tool to execute
        params: Parameters for the tool (can reference previous results)
        result_key: Key to store the result under (for use in later steps)
        condition: Optional condition function (receives context, returns bool)
        error_handler: Optional error handler function

    """

    tool_name: str
    params: dict[str, Any]
    result_key: str
    condition: Optional[Callable[[dict[str, Any]], bool]] = None
    error_handler: Optional[Callable[[Exception, dict[str, Any]], Any]] = None


@dataclass
class CompositeResult:
    """Result from a composite tool execution.

    Attributes:
        success: Whether the composite operation succeeded
        results: Dictionary of results from each step (keyed by result_key)
        final_result: The final result to return to the user
        steps_executed: Number of steps successfully executed
        error: Exception if the operation failed

    """

    success: bool
    results: dict[str, Any]
    final_result: str
    steps_executed: int = 0
    error: Optional[Exception] = None


class CompositeTool(Tool):
    """Base class for composite tools that chain multiple operations.

    Composite tools provide high-level operations by combining multiple atomic tools.
    They handle:
    - Sequential execution with result chaining
    - Error handling and recovery
    - Token optimization through batching
    - Parameter interpolation (${result_key} syntax)

    Subclasses should implement:
    - get_steps(): Return the list of steps to execute
    - format_result(): Format the final result for the user
    """

    def __init__(self, agent: "MurenaAgent"):  # type: ignore
        super().__init__(agent)
        self._context: dict[str, Any] = {}

    @abstractmethod
    def get_steps(self, **kwargs) -> list[CompositeStep]:
        """Get the list of steps to execute for this composite tool.

        Args:
            **kwargs: User-provided parameters

        Returns:
            List of CompositeStep objects defining the workflow

        """

    @abstractmethod
    def format_result(self, composite_result: CompositeResult) -> str:
        """Format the final result for the user.

        Args:
            composite_result: The composite result object

        Returns:
            Formatted string to return to the user

        """

    def execute_composite(self, **kwargs) -> str:
        """Execute the composite workflow.

        This is the main entry point. It:
        1. Gets the steps from the subclass
        2. Executes each step in sequence
        3. Chains results between steps
        4. Handles errors and recovery
        5. Formats the final result

        Args:
            **kwargs: User-provided parameters

        Returns:
            Formatted result string

        """
        # Initialize context with user parameters
        self._context = {**kwargs}

        # Get steps from subclass
        try:
            steps = self.get_steps(**kwargs)
        except Exception as e:
            log.error(f"Error getting steps for {self.get_name()}: {e}", exc_info=True)
            return f"Error: Failed to plan composite operation: {e}"

        # Execute steps
        results: dict[str, Any] = {}
        steps_executed = 0

        for i, step in enumerate(steps):
            # Check condition (if any)
            if step.condition and not step.condition(self._context):
                log.debug(f"Skipping step {i+1}/{len(steps)}: condition not met")
                continue

            # Interpolate parameters with results from previous steps
            try:
                params = self._interpolate_params(step.params, results)
            except Exception as e:
                error_msg = f"Error interpolating parameters for step {i+1}: {e}"
                log.error(error_msg)
                if step.error_handler:
                    result = step.error_handler(e, self._context)
                    results[step.result_key] = result
                    continue
                return self._create_error_result(error_msg, results, steps_executed)

            # Execute the tool
            try:
                log.info(f"Executing step {i+1}/{len(steps)}: {step.tool_name}")
                tool = self.agent.get_tool_by_name(step.tool_name)
                result = tool.apply_ex(**params)
                results[step.result_key] = result
                self._context[step.result_key] = result
                steps_executed += 1
                log.debug(f"Step {i+1} completed successfully")
            except Exception as e:
                error_msg = f"Error executing step {i+1} ({step.tool_name}): {e}"
                log.error(error_msg, exc_info=True)

                # Try error handler
                if step.error_handler:
                    try:
                        result = step.error_handler(e, self._context)
                        results[step.result_key] = result
                        self._context[step.result_key] = result
                        steps_executed += 1
                        continue
                    except Exception as handler_error:
                        log.error(f"Error handler failed: {handler_error}")

                # No handler or handler failed - abort
                return self._create_error_result(error_msg, results, steps_executed)

        # Create composite result
        composite_result = CompositeResult(
            success=True,
            results=results,
            final_result="",  # Will be set by format_result
            steps_executed=steps_executed,
        )

        # Format final result
        try:
            final_result = self.format_result(composite_result)
            composite_result.final_result = final_result
            return final_result
        except Exception as e:
            log.error(f"Error formatting result: {e}", exc_info=True)
            return f"Error: Composite operation completed but failed to format result: {e}\n\nRaw results: {results}"

    def _interpolate_params(self, params: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
        """Interpolate parameter values with results from previous steps.

        Supports ${result_key} syntax to reference previous results.

        Args:
            params: Parameter dictionary (may contain ${...} references)
            results: Dictionary of results from previous steps

        Returns:
            Interpolated parameters

        """
        interpolated = {}

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                # Extract result key
                result_key = value[2:-1]
                if result_key in results:
                    interpolated[key] = results[result_key]
                else:
                    raise ValueError(f"Result key '{result_key}' not found in previous results")
            else:
                interpolated[key] = value

        return interpolated

    def _create_error_result(self, error_msg: str, results: dict[str, Any], steps_executed: int) -> str:
        """Create an error result message.

        Args:
            error_msg: Error message
            results: Partial results from executed steps
            steps_executed: Number of steps that executed successfully

        Returns:
            Formatted error message

        """
        msg = f"Error: {error_msg}\n\n"
        if steps_executed > 0:
            msg += f"Partial results from {steps_executed} completed step(s):\n"
            for key, value in results.items():
                msg += f"  {key}: {str(value)[:200]}...\n" if len(str(value)) > 200 else f"  {key}: {value}\n"
        return msg
