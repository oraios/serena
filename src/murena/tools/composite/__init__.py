"""
Composite tools for chaining multiple operations.

Composite tools provide high-level operations that combine multiple atomic tools
into cohesive workflows. They reduce token consumption by batching operations and
minimize the number of round-trips required for common patterns.

Key Features:
    - Result chaining: Output from one step becomes input to the next
    - Error handling: Automatic rollback and recovery
    - Token optimization: Batch operations to reduce context
    - Integration with MCP: Exposed as first-class tools

Examples:
    >>> # Navigate to a symbol by description
    >>> tool = NavigateToSymbol(agent)
    >>> result = tool.apply(description="authentication handler")

    >>> # Extract documentation section
    >>> tool = ExtractDocSection(agent)
    >>> result = tool.apply(topic="API authentication")

"""

from murena.tools.composite.base import CompositeResult, CompositeStep, CompositeTool
from murena.tools.composite.documentation import ExtractDocSection
from murena.tools.composite.navigation import AnalyzeModule, NavigateDocumentation, NavigateToSymbol

__all__ = [
    "AnalyzeModule",
    "CompositeResult",
    "CompositeStep",
    "CompositeTool",
    "ExtractDocSection",
    "NavigateDocumentation",
    "NavigateToSymbol",
]
