"""
Pytest adapter for running Python tests.

Supports:
- File-level filtering (pytest tests/test_file.py)
- Function-level filtering (pytest tests/test_file.py::test_function)
- Coverage collection (pytest --cov)
- JSON output parsing (pytest-json-report plugin)
"""

import json
import os
import re
from typing import Any

from sensai.util import logging

from murena.tools.adapters.base_adapter import TestFrameworkAdapter
from murena.tools.testing_types import CoverageData, TestFailure, TestResult

log = logging.getLogger(__name__)


class PytestAdapter(TestFrameworkAdapter):
    """
    Pytest test framework adapter.

    Detects pytest via:
    - pytest.ini
    - pyproject.toml with [tool.pytest.ini_options]
    - setup.cfg with [tool:pytest]
    - conftest.py

    Runs tests with:
    - pytest command
    - --json-report for structured output (if available)
    - --cov for coverage (if requested)
    - -v for verbose output
    """

    def detect_framework(self) -> bool:
        """
        Detect if pytest is present in the project.

        Checks for common pytest config files and conftest.py.
        """
        # Check for pytest config files
        config_files = [
            "pytest.ini",
            "pyproject.toml",
            "setup.cfg",
            "conftest.py",
        ]

        for config_file in config_files:
            if self._file_exists(config_file):
                log.debug(f"Found pytest config: {config_file}")
                return True

        # Check if pytest is importable
        try:
            __import__("pytest")
            log.debug("pytest module is importable")
            return True
        except ImportError:
            pass

        return False

    def run_tests(
        self,
        file_path: str | None = None,
        symbol_name: str | None = None,
        coverage: bool = False,
    ) -> TestResult:
        """
        Execute pytest with optional filtering.

        Examples:
        - run_tests() -> pytest (all tests)
        - run_tests("tests/test_foo.py") -> pytest tests/test_foo.py
        - run_tests("tests/test_foo.py", "test_bar") -> pytest tests/test_foo.py::test_bar
        - run_tests(coverage=True) -> pytest --cov

        :param file_path: Run tests only in this file
        :param symbol_name: Run only this specific test function
        :param coverage: Whether to collect coverage data
        :return: TestResult with execution results

        """
        # Build pytest command
        cmd = ["pytest", "-v", "--tb=short"]

        # Add JSON report if plugin is available
        # This gives us structured output that's easy to parse
        cmd.append("--json-report")
        cmd.append("--json-report-file=.pytest_report.json")

        # Add coverage if requested
        if coverage:
            cmd.extend(["--cov", "--cov-report=json"])

        # Add file/symbol filtering
        if file_path:
            test_target = file_path
            if symbol_name:
                # Pytest uses :: to separate file and test name
                test_target = f"{file_path}::{symbol_name}"
            cmd.append(test_target)

        # Run pytest
        output, exit_code = self._run_command(cmd)

        # Try to parse JSON report first (most reliable)
        json_report_path = os.path.join(self.project_root, ".pytest_report.json")
        if os.path.exists(json_report_path):
            try:
                with open(json_report_path) as f:
                    json_data = json.load(f)
                result = self._parse_json_report(json_data, exit_code)

                # Clean up JSON report
                os.remove(json_report_path)

                # Add coverage if available
                if coverage:
                    coverage_data = self._parse_coverage()
                    if coverage_data:
                        result.coverage_percent = coverage_data.overall_percent

                return result
            except Exception as e:
                log.warning(f"Failed to parse JSON report: {e}, falling back to text parsing")

        # Fallback to text parsing
        return self.parse_results(output, exit_code)

    def parse_results(self, output: str, exit_code: int) -> TestResult:
        """
        Parse pytest text output to TestResult.

        Parses the output format:
        ============================= test session starts ==============================
        ...
        tests/test_foo.py::test_bar PASSED                                      [ 50%]
        tests/test_foo.py::test_baz FAILED                                      [100%]
        ...
        =========================== short test summary info ============================
        FAILED tests/test_foo.py::test_baz - AssertionError: ...
        ========================= 1 failed, 1 passed in 0.12s ==========================

        :param output: pytest stdout/stderr
        :param exit_code: pytest exit code
        :return: Parsed TestResult
        """
        # Extract summary line (e.g., "1 failed, 1 passed in 0.12s")
        summary_pattern = r"=+ (.+) in ([\d.]+)s"
        match = re.search(summary_pattern, output)

        passed = 0
        failed = 0
        skipped = 0
        duration = 0.0

        if match:
            summary = match.group(1)
            duration = float(match.group(2))

            # Parse counts from summary
            passed = self._extract_count(summary, "passed")
            failed = self._extract_count(summary, "failed")
            skipped = self._extract_count(summary, "skipped")
        else:
            # Fallback: count individual test results
            passed = output.count(" PASSED")
            failed = output.count(" FAILED")
            skipped = output.count(" SKIPPED")

        total = passed + failed + skipped

        # Parse failures
        failures = self._parse_failures(output)

        return TestResult(
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=total,
            duration=duration,
            failures=failures,
            exit_code=exit_code,
        )

    def _parse_json_report(self, json_data: dict[str, Any], exit_code: int) -> TestResult:
        """
        Parse pytest JSON report to TestResult.

        The pytest-json-report plugin provides structured output:
        {
            "summary": {"passed": 10, "failed": 2, ...},
            "tests": [{"nodeid": "...", "outcome": "passed", ...}],
            "duration": 1.23
        }

        :param json_data: Parsed JSON report
        :param exit_code: pytest exit code
        :return: TestResult
        """
        summary = json_data.get("summary", {})

        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)
        total = summary.get("total", passed + failed + skipped)
        duration = json_data.get("duration", 0.0)

        # Parse failures from tests list
        failures = []
        tests = json_data.get("tests", [])

        for test in tests:
            if test.get("outcome") == "failed":
                # Extract test info
                nodeid = test.get("nodeid", "")
                # nodeid format: tests/test_file.py::TestClass::test_method

                # Split file and test name
                parts = nodeid.split("::")
                file_path = parts[0] if parts else ""
                test_name = parts[-1] if len(parts) > 1 else nodeid

                # Get error info
                call = test.get("call", {})
                longrepr = call.get("longrepr", "")

                # Extract error message (first line usually has the key info)
                error_lines = longrepr.split("\n") if longrepr else []
                error_message = error_lines[-1] if error_lines else "Test failed"

                # Try to extract line number from longrepr
                line_number = None
                for line in error_lines:
                    if file_path in line and ":" in line:
                        try:
                            line_number = int(line.split(":")[-1])
                            break
                        except (ValueError, IndexError):
                            pass

                failure = TestFailure(
                    test_name=test_name,
                    file_path=file_path,
                    line_number=line_number,
                    error_message=error_message,
                    error_type=call.get("crash", {}).get("type"),
                    traceback=longrepr if len(longrepr) < 500 else None,  # Only include short tracebacks
                )
                failures.append(failure)

        return TestResult(
            passed=passed,
            failed=failed,
            skipped=skipped,
            total=total,
            duration=duration,
            failures=failures,
            exit_code=exit_code,
        )

    def _parse_failures(self, output: str) -> list[TestFailure]:
        """
        Parse failure information from pytest text output.

        Looks for "FAILED tests/test_file.py::test_name - Error message" lines.

        :param output: pytest output
        :return: List of TestFailure objects
        """
        failures = []

        # Pattern: FAILED tests/test_file.py::test_name - Error message
        failure_pattern = r"FAILED (.+?)::(.+?) - (.+)"

        for line in output.split("\n"):
            match = re.search(failure_pattern, line)
            if match:
                file_path = match.group(1).strip()
                test_name = match.group(2).strip()
                error_message = match.group(3).strip()

                failure = TestFailure(
                    test_name=test_name,
                    file_path=file_path,
                    line_number=None,
                    error_message=error_message,
                )
                failures.append(failure)

        return failures

    def _parse_coverage(self) -> CoverageData | None:
        """
        Parse coverage data from coverage.json.

        pytest --cov --cov-report=json generates a coverage.json file.

        :return: CoverageData if available, None otherwise
        """
        coverage_file = os.path.join(self.project_root, "coverage.json")

        if not os.path.exists(coverage_file):
            return None

        try:
            with open(coverage_file) as f:
                cov_data = json.load(f)

            # Extract overall percentage
            totals = cov_data.get("totals", {})
            overall_percent = totals.get("percent_covered", 0.0)

            # Extract per-file coverage
            files = cov_data.get("files", {})
            file_coverage = {path: data.get("summary", {}).get("percent_covered", 0.0) for path, data in files.items()}

            # Extract uncovered lines
            uncovered_lines = {}
            for path, data in files.items():
                missing = data.get("missing_lines", [])
                if missing:
                    uncovered_lines[path] = missing

            return CoverageData(
                overall_percent=overall_percent,
                file_coverage=file_coverage,
                uncovered_lines=uncovered_lines if uncovered_lines else None,
            )

        except Exception as e:
            log.warning(f"Failed to parse coverage data: {e}")
            return None

    @staticmethod
    def _extract_count(text: str, keyword: str) -> int:
        """
        Extract count from summary text.

        Examples:
        - "1 failed" -> 1
        - "10 passed" -> 10
        - "no tests" -> 0

        :param text: Summary text
        :param keyword: Keyword to search for ("passed", "failed", etc.)
        :return: Count as integer

        """
        pattern = rf"(\d+) {keyword}"
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0
