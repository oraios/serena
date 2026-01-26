"""
Semantic workflow matching using embeddings.

This module matches user requests to available workflows using semantic similarity,
enabling intelligent workflow suggestions.
"""

import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class WorkflowMatch:
    """A matched workflow with similarity score.

    Attributes:
        workflow_name: Name of the matched workflow
        similarity: Similarity score (0.0 to 1.0)
        description: Workflow description
        estimated_tokens: Estimated token savings
        estimated_steps: Estimated number of steps

    """

    workflow_name: str
    similarity: float
    description: str
    estimated_tokens: Optional[int] = None
    estimated_steps: Optional[int] = None


class WorkflowMatcher:
    """Matches user requests to available workflows using semantic similarity.

    Uses simple keyword matching for now. Can be enhanced with embeddings
    (sentence-transformers) for more sophisticated semantic matching.
    """

    def __init__(self) -> None:
        """Initialize the workflow matcher."""
        self._workflow_patterns: dict[str, list[str]] = {
            "navigate-codebase": [
                "find",
                "search",
                "locate",
                "where is",
                "show me",
                "navigate",
                "explore",
                "understand",
            ],
            "refactor-with-tests": [
                "refactor",
                "rename",
                "restructure",
                "reorganize",
                "change name",
                "move",
            ],
            "document-api": [
                "document",
                "api",
                "documentation",
                "docs",
                "readme",
                "guide",
            ],
            "cross-project-refactor": [
                "cross-project",
                "multiple projects",
                "all projects",
                "across projects",
            ],
        }

    def match_workflows(self, user_request: str, threshold: float = 0.5) -> list[WorkflowMatch]:
        """Match a user request to available workflows.

        Args:
            user_request: The user's natural language request
            threshold: Minimum similarity threshold (0.0 to 1.0)

        Returns:
            List of WorkflowMatch objects sorted by similarity (highest first)

        """
        matches: list[WorkflowMatch] = []
        user_request_lower = user_request.lower()

        for workflow_name, keywords in self._workflow_patterns.items():
            # Simple keyword matching (can be replaced with embeddings)
            matches_found = sum(1 for keyword in keywords if keyword in user_request_lower)
            similarity = matches_found / len(keywords) if keywords else 0.0

            if similarity >= threshold:
                # Get workflow description
                description = self._get_workflow_description(workflow_name)

                matches.append(
                    WorkflowMatch(
                        workflow_name=workflow_name,
                        similarity=similarity,
                        description=description,
                        estimated_tokens=self._estimate_tokens(workflow_name),
                        estimated_steps=self._estimate_steps(workflow_name),
                    )
                )

        # Sort by similarity (highest first)
        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches

    def _get_workflow_description(self, workflow_name: str) -> str:
        """Get the description for a workflow.

        Args:
            workflow_name: Name of the workflow

        Returns:
            Workflow description

        """
        descriptions = {
            "navigate-codebase": "Efficiently explore codebase to understand components",
            "refactor-with-tests": "Safely refactor code with test validation",
            "document-api": "Extract and analyze API documentation",
            "cross-project-refactor": "Apply refactoring pattern across multiple projects",
        }
        return descriptions.get(workflow_name, "No description available")

    def _estimate_tokens(self, workflow_name: str) -> int:
        """Estimate token savings for a workflow.

        Args:
            workflow_name: Name of the workflow

        Returns:
            Estimated tokens saved (negative means cost)

        """
        estimates = {
            "navigate-codebase": 15000,  # 75% savings vs manual
            "refactor-with-tests": 20000,  # 80% savings
            "document-api": 22000,  # 90% savings
            "cross-project-refactor": 30000,  # Multiple projects
        }
        return estimates.get(workflow_name, 10000)

    def _estimate_steps(self, workflow_name: str) -> int:
        """Estimate number of steps for a workflow.

        Args:
            workflow_name: Name of the workflow

        Returns:
            Estimated number of steps

        """
        estimates = {
            "navigate-codebase": 3,
            "refactor-with-tests": 5,
            "document-api": 3,
            "cross-project-refactor": 6,
        }
        return estimates.get(workflow_name, 4)

    def suggest_workflow(self, user_request: str) -> Optional[WorkflowMatch]:
        """Suggest the best workflow for a user request.

        Args:
            user_request: The user's natural language request

        Returns:
            Best matching WorkflowMatch or None if no good match

        """
        matches = self.match_workflows(user_request, threshold=0.3)
        return matches[0] if matches else None
