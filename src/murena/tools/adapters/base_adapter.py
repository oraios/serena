"""
Base class for test framework adapters.

Each language/framework needs an adapter that:
1. Detects if the framework is present (pytest.ini, package.json, etc.)
2. Executes tests with appropriate filtering
3. Parses test output to TestResult format
"""

import json
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Any

from sensai.util import logging

from murena.tools.testing_types import TestResult

log = logging.getLogger(__name__)


class TestFrameworkAdapter(ABC):
    """
    Base class for test framework adapters.

    Subclasses should implement:
    - detect_framework: Check if framework is present
    - run_tests: Execute tests with filtering
    - parse_results: Parse output to TestResult
    """

    def __init__(self, project_root: str):
        """
        Initialize adapter.

        :param project_root: Root directory of the project
        """
        self.project_root = project_root

    @abstractmethod
    def detect_framework(self) -> bool:
        """
        Detect if this test framework is present in the project.

        Examples:
        - pytest: Check for pytest.ini, pyproject.toml with [tool.pytest]
        - jest: Check for package.json with jest config
        - go test: Check for go.mod

        :return: True if framework is detected

        """

    @abstractmethod
    def run_tests(
        self,
        file_path: str | None = None,
        symbol_name: str | None = None,
        coverage: bool = False,
    ) -> TestResult:
        """
        Execute tests with optional filtering.

        :param file_path: Run tests only in this file (relative to project root)
        :param symbol_name: Run only this specific test (e.g., test function name)
        :param coverage: Whether to collect coverage data
        :return: TestResult with execution results
        """

    @abstractmethod
    def parse_results(self, output: str, exit_code: int) -> TestResult:
        """
        Parse test framework output to TestResult.

        :param output: stdout/stderr from test runner
        :param exit_code: Exit code from test runner
        :return: Parsed TestResult
        """

    def _run_command(
        self,
        cmd: list[str],
        cwd: str | None = None,
        timeout: int = 300,
    ) -> tuple[str, int]:
        """
        Run a shell command and return output + exit code.

        :param cmd: Command to run as list of strings
        :param cwd: Working directory (defaults to project_root)
        :param timeout: Timeout in seconds
        :return: Tuple of (combined stdout+stderr, exit code)
        """
        if cwd is None:
            cwd = self.project_root

        log.info(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                check=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout + result.stderr
            return output, result.returncode

        except subprocess.TimeoutExpired:
            log.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
            return f"Error: Test execution timed out after {timeout}s", 1

        except Exception as e:
            log.error(f"Error running command: {e}")
            return f"Error: {e}", 1

    def _file_exists(self, relative_path: str) -> bool:
        """Check if a file exists relative to project root"""
        full_path = os.path.join(self.project_root, relative_path)
        return os.path.isfile(full_path)

    def _parse_json_output(self, output: str) -> dict[str, Any] | None:
        """
        Try to parse JSON from test output.

        Many modern test frameworks support JSON output:
        - pytest --json-report
        - jest --json
        - go test -json

        :param output: Test output string
        :return: Parsed JSON dict or None if parsing fails
        """
        # Try to find JSON in output (may have other text before/after)
        lines = output.split("\n")

        # Look for lines that start with { or [
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith(("{", "[")):
                # Try to parse from this point
                remaining = "\n".join(lines[i:])
                try:
                    return json.loads(remaining)
                except json.JSONDecodeError:
                    # Try just this line
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue

        return None
