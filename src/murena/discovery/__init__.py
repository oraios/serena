"""
Workflow discovery and pattern detection system.

This module provides semantic matching and pattern learning to automatically
suggest workflows based on user requests and detect repetitive patterns in
conversation logs.
"""

from murena.discovery.pattern_detector import PatternDetector
from murena.discovery.workflow_matcher import WorkflowMatcher

__all__ = ["PatternDetector", "WorkflowMatcher"]
