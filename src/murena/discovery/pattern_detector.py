"""
Pattern detection in conversation logs.

This module analyzes conversation history to detect repetitive patterns
and suggest workflow creation.
"""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class DetectedPattern:
    """A detected repetitive pattern in conversation history.

    Attributes:
        pattern_id: Unique identifier for the pattern
        tool_sequence: Sequence of tools in the pattern
        occurrences: Number of times pattern occurred
        confidence: Confidence score (0.0 to 1.0)
        suggested_workflow_name: Suggested name for workflow
        example_params: Example parameters from pattern usage

    """

    pattern_id: str
    tool_sequence: list[str]
    occurrences: int
    confidence: float
    suggested_workflow_name: str
    example_params: dict[str, Any]


class PatternDetector:
    """Detects repetitive patterns in conversation logs.

    Analyzes tool usage sequences to identify patterns that occur 3+ times
    and could be automated as workflows.
    """

    def __init__(self, min_occurrences: int = 3, min_sequence_length: int = 2):
        """Initialize the pattern detector.

        Args:
            min_occurrences: Minimum occurrences to consider a pattern
            min_sequence_length: Minimum length of tool sequences

        """
        self._min_occurrences = min_occurrences
        self._min_sequence_length = min_sequence_length
        self._tool_sequences: list[tuple[str, ...]] = []

    def add_tool_call(self, tool_name: str, params: dict[str, Any]) -> None:
        """Record a tool call for pattern analysis.

        Args:
            tool_name: Name of the tool that was called
            params: Parameters used for the tool call

        """
        # For now, just track tool names in sequence
        # In a full implementation, we'd maintain session context
        if not hasattr(self, "_current_sequence"):
            self._current_sequence: list[str] = []

        self._current_sequence.append(tool_name)

    def end_session(self) -> None:
        """Mark the end of a conversation session.

        Analyzes the current sequence and stores it for pattern detection.
        """
        if hasattr(self, "_current_sequence") and len(self._current_sequence) >= self._min_sequence_length:
            self._tool_sequences.append(tuple(self._current_sequence))
            delattr(self, "_current_sequence")

    def detect_patterns(self) -> list[DetectedPattern]:
        """Detect repetitive patterns in recorded tool sequences.

        Returns:
            List of DetectedPattern objects for frequently occurring sequences

        """
        patterns: list[DetectedPattern] = []

        # Find subsequences that occur multiple times
        subsequence_counts: Counter = Counter()

        for sequence in self._tool_sequences:
            # Generate all subsequences of minimum length
            for i in range(len(sequence)):
                for j in range(i + self._min_sequence_length, len(sequence) + 1):
                    subseq = sequence[i:j]
                    subsequence_counts[subseq] += 1

        # Filter by minimum occurrences
        for subseq, count in subsequence_counts.items():
            if count >= self._min_occurrences:
                # Calculate confidence based on occurrence frequency
                confidence = min(1.0, count / (self._min_occurrences * 2))

                # Generate suggested workflow name
                workflow_name = self._suggest_workflow_name(list(subseq))

                patterns.append(
                    DetectedPattern(
                        pattern_id=str(hash(subseq)),
                        tool_sequence=list(subseq),
                        occurrences=count,
                        confidence=confidence,
                        suggested_workflow_name=workflow_name,
                        example_params={},  # Would contain actual params in full implementation
                    )
                )

        # Sort by occurrences (most frequent first)
        patterns.sort(key=lambda p: p.occurrences, reverse=True)
        return patterns

    def _suggest_workflow_name(self, tool_sequence: list[str]) -> str:
        """Suggest a workflow name based on tool sequence.

        Args:
            tool_sequence: Sequence of tool names

        Returns:
            Suggested workflow name

        """
        # Simple heuristic: combine first and last tool names
        if len(tool_sequence) == 1:
            return f"{tool_sequence[0]}-workflow"
        elif len(tool_sequence) == 2:
            return f"{tool_sequence[0]}-and-{tool_sequence[1]}"
        else:
            return f"{tool_sequence[0]}-to-{tool_sequence[-1]}"

    def clear(self) -> None:
        """Clear all recorded sequences."""
        self._tool_sequences.clear()
        if hasattr(self, "_current_sequence"):
            delattr(self, "_current_sequence")
