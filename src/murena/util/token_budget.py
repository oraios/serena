"""
Token budget tracking and optimization.

This module tracks token consumption across operations and provides
warnings and automatic optimizations when approaching budget limits.
"""

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """Token budget configuration and tracking.

    Attributes:
        max_tokens: Maximum token budget for the session
        current_usage: Current token usage
        warning_threshold: Threshold to warn user (0.0 to 1.0, e.g., 0.75 for 75%)
        critical_threshold: Threshold for automatic optimization (e.g., 0.90)

    """

    max_tokens: int = 200000
    current_usage: int = 0
    warning_threshold: float = 0.75
    critical_threshold: float = 0.90

    def add_usage(self, tokens: int) -> None:
        """Add token usage and check thresholds.

        Args:
            tokens: Number of tokens to add

        """
        self.current_usage += tokens

        if self.is_critical():
            log.warning(f"Token budget CRITICAL: {self.usage_percentage():.1f}% ({self.current_usage}/{self.max_tokens})")
        elif self.is_warning():
            log.info(f"Token budget warning: {self.usage_percentage():.1f}% ({self.current_usage}/{self.max_tokens})")

    def usage_percentage(self) -> float:
        """Calculate current usage as percentage.

        Returns:
            Usage percentage (0.0 to 100.0)

        """
        return (self.current_usage / self.max_tokens) * 100

    def is_warning(self) -> bool:
        """Check if warning threshold exceeded.

        Returns:
            True if at or above warning threshold

        """
        return self.current_usage >= (self.max_tokens * self.warning_threshold)

    def is_critical(self) -> bool:
        """Check if critical threshold exceeded.

        Returns:
            True if at or above critical threshold

        """
        return self.current_usage >= (self.max_tokens * self.critical_threshold)

    def remaining_tokens(self) -> int:
        """Calculate remaining tokens in budget.

        Returns:
            Number of tokens remaining

        """
        return max(0, self.max_tokens - self.current_usage)

    def get_optimization_suggestions(self) -> list[str]:
        """Get suggestions for token optimization based on current usage.

        Returns:
            List of optimization suggestions

        """
        suggestions = []

        if self.is_critical():
            suggestions.extend([
                f"🚨 CRITICAL: Token budget at {self.usage_percentage():.1f}%",
                "Auto-optimizations enabled:",
                "  - Switching to compact_format=True for all operations",
                "  - Using context_mode='line_only' for references",
                "  - Enabling aggressive caching",
                "  - Consider using haiku model for simple operations",
            ])
        elif self.is_warning():
            suggestions.extend([
                f"⚠️  WARNING: Token budget at {self.usage_percentage():.1f}%",
                "Optimization suggestions:",
                "  - Use get-cached-symbols for repeated file access",
                "  - Enable compact_format=True for large results",
                "  - Use context_mode='line_only' instead of 'full'",
                "  - Prefer composite tools over manual sequences",
            ])
        else:
            suggestions.append(f"✓ Token budget healthy: {self.usage_percentage():.1f}% ({self.current_usage}/{self.max_tokens})")

        return suggestions

    def reset(self) -> None:
        """Reset token usage counter."""
        self.current_usage = 0


class TokenBudgetManager:
    """Manages token budgets for Murena operations."""

    def __init__(self, max_tokens: int = 200000):
        """Initialize token budget manager.

        Args:
            max_tokens: Maximum token budget for session

        """
        self._budget = TokenBudget(max_tokens=max_tokens)
        self._auto_optimize = False

    def track_operation(self, operation_name: str, estimated_tokens: int) -> None:
        """Track tokens for an operation.

        Args:
            operation_name: Name of the operation
            estimated_tokens: Estimated token cost

        """
        self._budget.add_usage(estimated_tokens)
        log.debug(f"Operation '{operation_name}': {estimated_tokens} tokens (total: {self._budget.current_usage})")

        # Enable auto-optimization if critical
        if self._budget.is_critical() and not self._auto_optimize:
            self._auto_optimize = True
            log.warning("Auto-optimization enabled due to critical token usage")

    def get_optimization_params(self) -> dict:
        """Get recommended parameters for token optimization.

        Returns:
            Dictionary of recommended parameter values

        """
        if self._auto_optimize:
            return {
                "compact_format": True,
                "context_mode": "line_only",
                "use_cache": True,
                "max_results": 10,  # Limit results
            }
        elif self._budget.is_warning():
            return {
                "compact_format": True,
                "use_cache": True,
            }
        else:
            return {}

    def get_status(self) -> str:
        """Get current budget status.

        Returns:
            Status message with suggestions

        """
        suggestions = self._budget.get_optimization_suggestions()
        return "\n".join(suggestions)

    @property
    def budget(self) -> TokenBudget:
        """Get the current budget object.

        Returns:
            TokenBudget instance

        """
        return self._budget
