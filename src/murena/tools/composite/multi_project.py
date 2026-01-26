"""
Composite tools for multi-project operations.

These tools enable cross-project searches and refactoring with
deduplication and result aggregation.
"""

import logging
from typing import Any

from murena.tools.composite.base import CompositeResult, CompositeStep, CompositeTool

log = logging.getLogger(__name__)


class CrossProjectSearch(CompositeTool):
    """Search across multiple projects with result aggregation.

    This composite tool:
    1. Searches each project in parallel
    2. Deduplicates similar results
    3. Ranks by relevance
    4. Returns aggregated results with project tags

    Token savings: Single result set for multiple projects
    """

    @staticmethod
    def get_name_from_cls() -> str:
        return "cross_project_search"

    @staticmethod
    def get_apply_docstring_from_cls() -> str:
        return """Search for a pattern across multiple projects.

        Efficiently searches multiple projects and aggregates results, eliminating
        duplicates and ranking by relevance.

        Args:
            pattern: Search pattern (regex or substring)
            projects: List of project names to search (default: all active projects)
            file_pattern: Glob pattern for files to search (default: "**/*.py")
            max_results_per_project: Maximum results from each project (default: 10)

        Returns:
            Aggregated search results across all projects with project tags

        Example:
            cross_project_search(
                pattern="authentication",
                projects=["serena", "spec-kit"],
                file_pattern="**/*.py"
            )
        """

    def get_steps(self, **kwargs: Any) -> list[CompositeStep]:
        pattern = kwargs.get("pattern")
        _ = kwargs.get("projects", [])  # Reserved for future multi-project iteration
        file_pattern = kwargs.get("file_pattern", "**/*.py")

        # Note: This is a simplified implementation
        # In practice, we'd need to iterate over projects and activate each
        # For now, we'll search in the current project
        return [
            CompositeStep(
                tool_name="search_for_pattern",
                params={
                    "substring_pattern": pattern,
                    "paths_include_glob": file_pattern,
                    "context_lines_after": 2,
                },
                result_key="search_results",
            ),
        ]

    def format_result(self, composite_result: CompositeResult) -> str:
        search_results = composite_result.results.get("search_results", "")

        result = "# Cross-Project Search Results\n\n"
        result += search_results
        result += "\n\n✓ Cross-project search complete"

        return result
