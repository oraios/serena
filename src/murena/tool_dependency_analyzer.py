"""
Tool dependency analyzer for parallel execution.

Analyzes tool calls to determine which can run in parallel vs sequentially.
"""

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a single tool invocation."""

    tool_name: str
    params: dict[str, Any]
    index: int  # Position in the original sequence


@dataclass
class DependencyGraph:
    """Represents dependencies between tool calls."""

    # Maps tool index to list of indices it depends on
    dependencies: dict[int, list[int]]

    def get_execution_waves(self) -> list[list[int]]:
        """
        Organize tools into execution waves based on dependencies.

        Wave 1: All tasks with NO dependencies
        Wave 2: Tasks that depend ONLY on Wave 1
        Wave 3: Tasks that depend on Wave 1 or Wave 2
        ...

        Returns:
            List of waves, where each wave is a list of tool indices
            that can execute in parallel

        """
        # Calculate in-degree for each node
        in_degree = dict.fromkeys(self.dependencies.keys(), 0)
        for deps in self.dependencies.values():
            for dep in deps:
                in_degree[dep] = in_degree.get(dep, 0)

        for node, deps in self.dependencies.items():
            in_degree[node] = len(deps)

        waves = []
        completed: set[int] = set()

        while len(completed) < len(self.dependencies):
            # Find all nodes with in_degree 0 (no remaining dependencies)
            current_wave = []
            for node, degree in in_degree.items():
                if degree == 0 and node not in completed:
                    current_wave.append(node)

            if not current_wave:
                # Circular dependency detected
                remaining = set(self.dependencies.keys()) - completed
                log.warning(f"Circular dependency detected in tools: {remaining}")
                # Add remaining as a final wave (will execute sequentially)
                current_wave = list(remaining)

            waves.append(current_wave)

            # Mark as completed and reduce in-degree for dependents
            for node in current_wave:
                completed.add(node)
                in_degree[node] = -1  # Mark as processed

                # Reduce in-degree for nodes that depend on this one
                for other_node, deps in self.dependencies.items():
                    if node in deps and other_node not in completed:
                        in_degree[other_node] -= 1

        return waves


class ToolDependencyAnalyzer:
    """
    Analyzes tool calls to determine dependencies.

    Dependency rules:
    1. Read-after-write (same file): Sequential
    2. Symbol operations (same file): Sequential
    3. Independent operations: Parallel
    """

    # Tools that read files
    READ_TOOLS = {
        "ReadFileTool",
        "read_file",
        "ReadMemoryTool",
        "read_memory",
        "GetSymbolsOverviewTool",
        "get_symbols_overview",
        "FindSymbolTool",
        "find_symbol",
    }

    # Tools that write/modify files
    WRITE_TOOLS = {
        "WriteFileTool",
        "write_file",
        "EditFileTool",
        "edit_file",
        "ReplaceContentTool",
        "replace_content",
        "ReplaceSymbolBodyTool",
        "replace_symbol_body",
        "InsertAfterSymbolTool",
        "insert_after_symbol",
        "InsertBeforeSymbolTool",
        "insert_before_symbol",
        "DeleteSymbolTool",
        "delete_symbol",
        "RenameSymbolTool",
        "rename_symbol",
    }

    # Tools that operate on symbols (may have cross-file dependencies)
    SYMBOL_TOOLS = {
        "FindSymbolTool",
        "find_symbol",
        "FindReferencingSymbolsTool",
        "find_referencing_symbols",
        "ReplaceSymbolBodyTool",
        "replace_symbol_body",
        "InsertAfterSymbolTool",
        "insert_after_symbol",
        "InsertBeforeSymbolTool",
        "insert_before_symbol",
        "RenameSymbolTool",
        "rename_symbol",
    }

    def analyze(self, tool_calls: list[ToolCall]) -> DependencyGraph:
        """
        Analyze tool calls and build dependency graph.

        Args:
            tool_calls: List of tool calls to analyze

        Returns:
            Dependency graph showing which tools depend on which

        """
        dependencies: dict[int, list[int]] = {tc.index: [] for tc in tool_calls}

        # Track file accesses
        file_writes: dict[str, list[int]] = {}  # file_path -> list of tool indices that wrote
        file_reads: dict[str, list[int]] = {}  # file_path -> list of tool indices that read

        for tc in tool_calls:
            file_path = self._get_file_path(tc)

            if file_path:
                # Check for read-after-write dependencies
                if tc.tool_name in self.READ_TOOLS:
                    # This read depends on all previous writes to the same file
                    if file_path in file_writes:
                        dependencies[tc.index].extend(file_writes[file_path])
                    file_reads.setdefault(file_path, []).append(tc.index)

                elif tc.tool_name in self.WRITE_TOOLS:
                    # This write depends on all previous operations on the same file
                    if file_path in file_writes:
                        dependencies[tc.index].extend(file_writes[file_path])
                    if file_path in file_reads:
                        dependencies[tc.index].extend(file_reads[file_path])
                    file_writes.setdefault(file_path, []).append(tc.index)

            # Symbol operations on the same file should be sequential
            if tc.tool_name in self.SYMBOL_TOOLS:
                # Depend on all previous symbol operations on the same file
                for prev_tc in tool_calls[: tc.index]:
                    if prev_tc.tool_name in self.SYMBOL_TOOLS:
                        prev_file = self._get_file_path(prev_tc)
                        if prev_file and prev_file == file_path:
                            if prev_tc.index not in dependencies[tc.index]:
                                dependencies[tc.index].append(prev_tc.index)

        # Remove duplicates and self-dependencies
        for idx in list(dependencies.keys()):
            dependencies[idx] = list(set(dep for dep in dependencies[idx] if dep != idx))

        return DependencyGraph(dependencies)

    def _get_file_path(self, tool_call: ToolCall) -> str | None:
        """
        Extract file path from tool call parameters.

        Args:
            tool_call: The tool call to analyze

        Returns:
            File path if found, None otherwise

        """
        # Common parameter names for file paths
        path_params = [
            "file_path",
            "relative_path",
            "relative_file_path",
            "memory_file_name",
            "path",
        ]

        for param in path_params:
            if param in tool_call.params:
                return str(tool_call.params[param])

        return None
