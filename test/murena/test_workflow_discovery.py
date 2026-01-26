"""
Unit tests for workflow discovery system.
"""

import pytest

from murena.discovery.pattern_detector import PatternDetector
from murena.discovery.workflow_matcher import WorkflowMatcher


class TestWorkflowMatcher:
    """Test the WorkflowMatcher class."""

    @pytest.fixture
    def matcher(self):
        """Create a workflow matcher for each test."""
        return WorkflowMatcher()

    def test_match_navigation_workflow(self, matcher):
        """Test matching navigation-related requests."""
        request = "Find the authentication handler in the codebase"
        matches = matcher.match_workflows(request, threshold=0.2)

        assert len(matches) > 0
        assert matches[0].workflow_name == "navigate-codebase"

    def test_match_refactoring_workflow(self, matcher):
        """Test matching refactoring-related requests."""
        request = "Rename UserService to AccountService"
        matches = matcher.match_workflows(request, threshold=0.2)

        assert len(matches) > 0
        assert matches[0].workflow_name == "refactor-with-tests"

    def test_match_documentation_workflow(self, matcher):
        """Test matching documentation-related requests."""
        request = "Extract the API documentation from the README"
        matches = matcher.match_workflows(request, threshold=0.2)

        assert len(matches) > 0
        assert any(m.workflow_name == "document-api" for m in matches)

    def test_suggest_best_workflow(self, matcher):
        """Test suggesting the best workflow."""
        request = "Search for login functionality"
        suggestion = matcher.suggest_workflow(request)

        assert suggestion is not None
        assert suggestion.workflow_name in ["navigate-codebase", "refactor-with-tests", "document-api"]

    def test_no_match_below_threshold(self, matcher):
        """Test that unrelated requests don't match."""
        request = "What's the weather like today?"
        matches = matcher.match_workflows(request, threshold=0.5)

        # Should have no matches or very low similarity
        assert len(matches) == 0 or matches[0].similarity < 0.3

    def test_similarity_sorting(self, matcher):
        """Test that matches are sorted by similarity."""
        request = "Find and refactor the authentication code"
        matches = matcher.match_workflows(request, threshold=0.1)

        # Check that similarities are in descending order
        for i in range(len(matches) - 1):
            assert matches[i].similarity >= matches[i + 1].similarity


class TestPatternDetector:
    """Test the PatternDetector class."""

    @pytest.fixture
    def detector(self):
        """Create a pattern detector for each test."""
        return PatternDetector(min_occurrences=2, min_sequence_length=2)

    def test_detect_simple_pattern(self, detector):
        """Test detecting a simple repetitive pattern."""
        # Simulate multiple sessions with same pattern
        for _ in range(3):
            detector.add_tool_call("find_symbol", {"name": "test"})
            detector.add_tool_call("find_referencing_symbols", {"name": "test"})
            detector.end_session()

        patterns = detector.detect_patterns()

        assert len(patterns) > 0
        # Should detect the find_symbol → find_referencing_symbols pattern
        assert any("find_symbol" in p.tool_sequence and "find_referencing_symbols" in p.tool_sequence for p in patterns)

    def test_minimum_occurrences(self, detector):
        """Test that patterns below minimum occurrences are not detected."""
        # Only one occurrence
        detector.add_tool_call("tool1", {})
        detector.add_tool_call("tool2", {})
        detector.end_session()

        patterns = detector.detect_patterns()

        # Should not detect pattern with only 1 occurrence (min is 2)
        assert len(patterns) == 0

    def test_workflow_name_suggestion(self, detector):
        """Test workflow name suggestion."""
        # Create a pattern
        for _ in range(2):
            detector.add_tool_call("find_symbol", {})
            detector.add_tool_call("replace_symbol_body", {})
            detector.end_session()

        patterns = detector.detect_patterns()

        assert len(patterns) > 0
        # Should suggest a name based on the sequence
        assert "find_symbol" in patterns[0].suggested_workflow_name.lower()

    def test_clear_patterns(self, detector):
        """Test clearing recorded patterns."""
        detector.add_tool_call("tool1", {})
        detector.add_tool_call("tool2", {})
        detector.end_session()

        detector.clear()

        patterns = detector.detect_patterns()
        assert len(patterns) == 0
