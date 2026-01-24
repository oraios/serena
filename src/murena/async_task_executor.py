"""
Async task executor for parallel tool execution.

Executes tools in parallel based on dependency analysis.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from murena.tool_dependency_analyzer import DependencyGraph, ToolCall

log = logging.getLogger(__name__)


class AsyncTaskExecutor:
    """
    Executes tools in parallel based on dependency analysis.

    Features:
    - Dependency-aware execution (respects read-after-write, etc.)
    - Wave-based execution (maximizes parallelism within constraints)
    - Error handling and tool_timeout support
    - Performance tracking
    """

    def __init__(self, max_workers: int = 10):
        """
        Initialize the executor.

        Args:
            max_workers: Maximum number of concurrent tool executions

        """
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ToolExec")

    async def execute_tools(
        self,
        tool_calls: list[ToolCall],
        dependency_graph: DependencyGraph,
        execute_func: Callable[[ToolCall], Any],
        timeout_per_tool: float | None = None,
    ) -> list[Any]:
        """
        Execute tools in parallel based on dependency graph.

        Args:
            tool_calls: List of tools to execute
            dependency_graph: Dependency relationships
            execute_func: Function to execute each tool (should be thread-safe)
            timeout_per_tool: Optional timeout for each tool execution in seconds

        Returns:
            List of results in the same order as tool_calls

        """
        start_time = time.time()
        waves = dependency_graph.get_execution_waves()

        log.info(f"Executing {len(tool_calls)} tools in {len(waves)} waves")

        # Track results by tool index
        results: dict[int, Any] = {}
        errors: dict[int, Exception] = {}

        # Execute each wave
        for wave_num, wave_indices in enumerate(waves, 1):
            wave_start = time.time()
            log.debug(f"Wave {wave_num}/{len(waves)}: Executing {len(wave_indices)} tools in parallel")

            # Create tasks for this wave
            wave_tasks = []
            for idx in wave_indices:
                tool_call = tool_calls[idx]
                task = self._execute_tool_async(tool_call, execute_func, timeout_per_tool)
                wave_tasks.append((idx, task))

            # Execute wave in parallel
            wave_results = await asyncio.gather(*[task for _, task in wave_tasks], return_exceptions=True)

            # Store results
            for (idx, _), result in zip(wave_tasks, wave_results, strict=False):
                if isinstance(result, Exception):
                    errors[idx] = result
                    log.error(f"Tool {tool_calls[idx].tool_name} (index {idx}) failed: {result}")
                else:
                    results[idx] = result

            wave_elapsed = time.time() - wave_start
            log.debug(f"Wave {wave_num} completed in {wave_elapsed:.2f}s")

        # Build final results list in original order
        final_results = []
        for tc in tool_calls:
            if tc.index in errors:
                # Propagate error
                raise errors[tc.index]
            if tc.index in results:
                final_results.append(results[tc.index])
            else:
                # Should never happen
                raise RuntimeError(f"No result for tool {tc.tool_name} at index {tc.index}")

        total_elapsed = time.time() - start_time
        log.info(
            f"Parallel execution complete: {len(tool_calls)} tools in {total_elapsed:.2f}s "
            f"({len(waves)} waves, avg {total_elapsed/len(waves):.2f}s/wave)"
        )

        return final_results

    async def _execute_tool_async(
        self,
        tool_call: ToolCall,
        execute_func: Callable[[ToolCall], Any],
        timeout_per_tool: float | None = None,
    ) -> Any:
        """
        Execute a single tool asynchronously.

        Args:
            tool_call: The tool to execute
            execute_func: Function to execute the tool
            timeout_per_tool: Optional timeout in seconds

        Returns:
            Tool execution result

        """
        loop = asyncio.get_event_loop()

        # Run in thread pool to avoid blocking
        try:
            if timeout_per_tool:
                result = await asyncio.wait_for(loop.run_in_executor(self._executor, execute_func, tool_call), timeout=timeout_per_tool)
            else:
                result = await loop.run_in_executor(self._executor, execute_func, tool_call)

            log.debug(f"Tool {tool_call.tool_name} completed successfully")
            return result

        except TimeoutError:
            log.error(f"Tool {tool_call.tool_name} timed out after {timeout_per_tool}s")
            raise
        except Exception as e:
            log.error(f"Tool {tool_call.tool_name} failed: {e}")
            raise

    def shutdown(self) -> None:
        """Shutdown the executor and clean up resources."""
        self._executor.shutdown(wait=True)
        log.debug("AsyncTaskExecutor shut down")


async def execute_tools_parallel(
    tool_calls: list[ToolCall],
    dependency_graph: DependencyGraph,
    execute_func: Callable[[ToolCall], Any],
    max_workers: int = 10,
    timeout_per_tool: float | None = None,
) -> list[Any]:
    """
    Convenience function to execute tools in parallel.

    Args:
        tool_calls: List of tools to execute
        dependency_graph: Dependency relationships
        execute_func: Function to execute each tool
        max_workers: Maximum concurrent executions
        timeout_per_tool: Optional timeout per tool in seconds

    Returns:
        List of results in original order

    """
    executor = AsyncTaskExecutor(max_workers=max_workers)
    try:
        return await executor.execute_tools(tool_calls, dependency_graph, execute_func, timeout_per_tool)
    finally:
        executor.shutdown()
