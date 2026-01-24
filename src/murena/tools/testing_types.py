"""
Data types for test execution and reporting.

Defines compact, token-optimized representations for test results,
failures, and coverage data.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TestStatus(Enum):
    """Test execution status"""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestFailure:
    """
    Represents a single test failure with minimal token footprint.

    Expected token usage: ~100-150 tokens per failure
    """

    test_name: str
    """Name of the failed test (e.g., 'test_login')"""

    file_path: str
    """Relative path to test file"""

    line_number: int | None
    """Line number where test is defined"""

    error_message: str
    """Short error message (e.g., 'AssertionError: got 5, expected 10')"""

    error_type: str | None = None
    """Type of error (e.g., 'AssertionError', 'TypeError')"""

    traceback: str | None = None
    """Full traceback (only included if explicitly requested)"""

    def to_compact_dict(self) -> dict[str, Any]:
        """
        Convert to compact dictionary format for minimal token usage.

        Format: {"test": "test_foo", "file": "test_bar.py:23", "msg": "..."}
        """
        result = {
            "test": self.test_name,
            "file": f"{self.file_path}:{self.line_number}" if self.line_number else self.file_path,
            "msg": self.error_message,
        }

        if self.error_type:
            result["type"] = self.error_type

        # Only include traceback if present (it's verbose)
        if self.traceback:
            result["trace"] = self.traceback

        return result


@dataclass
class TestResult:
    """
    Compact representation of test execution results.

    Token-optimized format uses symbols: ✓ ✗ ⊘ ⏱
    Expected token usage: ~100-200 tokens per test run (vs 1000+ for raw pytest output)
    """

    passed: int
    """Number of tests that passed"""

    failed: int
    """Number of tests that failed"""

    skipped: int
    """Number of tests that were skipped"""

    total: int
    """Total number of tests executed"""

    duration: float
    """Total execution time in seconds"""

    failures: list[TestFailure]
    """List of test failures (only populated if tests failed)"""

    coverage_percent: float | None = None
    """Code coverage percentage if available"""

    exit_code: int = 0
    """Exit code from test runner (0 = success)"""

    @property
    def success(self) -> bool:
        """True if all tests passed"""
        return self.failed == 0 and self.exit_code == 0

    def to_compact_dict(self) -> dict[str, Any]:
        """
        Convert to ultra-compact dictionary format.

        Example output:
        {
            "✓": 45,
            "✗": 2,
            "⊘": 1,
            "⏱": "1.2s",
            "failures": [...]
        }

        Token savings: ~70% vs full pytest output
        """
        result = {
            "✓": self.passed,
            "✗": self.failed,
            "⊘": self.skipped,
            "⏱": f"{self.duration:.1f}s",
        }

        if self.failures:
            result["failures"] = [f.to_compact_dict() for f in self.failures]

        if self.coverage_percent is not None:
            result["cov"] = f"{self.coverage_percent:.1f}%"

        return result

    def to_verbose_dict(self) -> dict[str, Any]:
        """
        Convert to verbose dictionary format for detailed analysis.

        Use this when debugging or when full details are needed.
        """
        return {
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "total": self.total,
            "duration": self.duration,
            "success": self.success,
            "exit_code": self.exit_code,
            "failures": [f.to_compact_dict() for f in self.failures],
            "coverage_percent": self.coverage_percent,
        }


@dataclass
class CoverageData:
    """
    Code coverage information.

    Provides insights into which lines/functions were covered by tests.
    """

    overall_percent: float
    """Overall coverage percentage"""

    file_coverage: dict[str, float]
    """Per-file coverage percentages"""

    uncovered_lines: dict[str, list[int]] | None = None
    """Lines not covered by tests (per file)"""

    def to_compact_dict(self) -> dict[str, Any]:
        """Compact representation for token efficiency"""
        result = {
            "total": f"{self.overall_percent:.1f}%",
            "files": {path: f"{pct:.1f}%" for path, pct in self.file_coverage.items()},
        }

        if self.uncovered_lines:
            # Only include files with uncovered lines
            uncovered = {path: lines for path, lines in self.uncovered_lines.items() if lines}
            if uncovered:
                result["uncovered"] = uncovered

        return result


@dataclass
class TestSymbol:
    """
    Represents a test function/method discovered via LSP.

    Used by LSP-powered semantic test discovery.
    """

    name: str
    """Test name (e.g., 'test_login')"""

    file_path: str
    """Relative path to test file"""

    line_number: int
    """Line number where test is defined"""

    name_path: str
    """LSP name path (e.g., 'TestUserAuth/test_login')"""

    related_symbols: list[str] | None = None
    """Symbols that this test references (e.g., functions it tests)"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "name": self.name,
            "file": self.file_path,
            "line": self.line_number,
            "path": self.name_path,
        }

        if self.related_symbols:
            result["tests"] = self.related_symbols

        return result
