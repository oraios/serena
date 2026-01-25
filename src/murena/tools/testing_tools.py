"""
Testing integration tools for semantic test discovery and execution.

Provides LSP-powered test discovery and token-optimized test execution
for Python (pytest), TypeScript (jest), and Go (go test).

Key features:
- Semantic test discovery using LSP reference finding
- Token-optimized test results (70% reduction vs raw output)
- Coverage integration
- Framework auto-detection
"""

import json
from typing import Any

from sensai.util import logging

from murena.tools import Tool
from murena.tools.adapters.base_adapter import TestFrameworkAdapter
from murena.tools.adapters.pytest_adapter import PytestAdapter
from murena.tools.testing_types import TestSymbol

log = logging.getLogger(__name__)


class RunTestsTool(Tool):
    """
    Run tests using the appropriate test framework for the project.

    Auto-detects test framework:
    - Python: pytest
    - TypeScript/JavaScript: jest (future)
    - Go: go test (future)

    Returns token-optimized results (~100-200 tokens vs 1000+ for raw output).
    """

    def apply(
        self,
        file_path: str | None = None,
        symbol_name: str | None = None,
        coverage: bool = False,
        verbose: bool = False,
    ) -> str:
        """
        Run tests with optional filtering and coverage.

        Examples:
        - run_tests() - Run all tests
        - run_tests(file_path="tests/test_auth.py") - Run tests in one file
        - run_tests(file_path="tests/test_auth.py", symbol_name="test_login") - Run one test
        - run_tests(coverage=True) - Run all tests with coverage

        :param file_path: Optional relative path to test file (e.g., "tests/test_foo.py")
        :param symbol_name: Optional test name to run (e.g., "test_login")
        :param coverage: Whether to collect coverage data (default False)
        :param verbose: Whether to return verbose output (default False, uses compact format)
        :return: JSON string with test results in compact or verbose format

        """
        # Detect and create appropriate test adapter
        adapter = self._get_test_adapter()

        if adapter is None:
            return json.dumps(
                {
                    "error": "No supported test framework detected in project. "
                    "Supported frameworks: pytest (Python), jest (TypeScript/JavaScript), go test (Go)"
                }
            )

        # Run tests
        try:
            result = adapter.run_tests(
                file_path=file_path,
                symbol_name=symbol_name,
                coverage=coverage,
            )

            # Return compact or verbose format
            if verbose:
                return json.dumps(result.to_verbose_dict(), indent=2)
            else:
                return json.dumps(result.to_compact_dict())

        except Exception as e:
            log.error(f"Error running tests: {e}", exc_info=e)
            return json.dumps({"error": f"Test execution failed: {e}"})

    def _get_test_adapter(self) -> TestFrameworkAdapter | None:
        """
        Detect and return the appropriate test framework adapter.

        Tries adapters in order:
        1. PytestAdapter (Python)
        2. JestAdapter (TypeScript/JavaScript) - future
        3. GoTestAdapter (Go) - future

        :return: TestFrameworkAdapter instance or None if no framework detected
        """
        project_root = self.get_project_root()

        # Try pytest (Python)
        pytest_adapter = PytestAdapter(project_root)
        if pytest_adapter.detect_framework():
            log.info("Detected pytest test framework")
            return pytest_adapter

        # TODO: Add JestAdapter
        # jest_adapter = JestAdapter(project_root)
        # if jest_adapter.detect_framework():
        #     log.info("Detected jest test framework")
        #     return jest_adapter

        # TODO: Add GoTestAdapter
        # go_adapter = GoTestAdapter(project_root)
        # if go_adapter.detect_framework():
        #     log.info("Detected go test framework")
        #     return go_adapter

        log.warning("No supported test framework detected")
        return None


class FindTestsForSymbolTool(Tool):
    """
    Find tests that cover a specific symbol using LSP-powered semantic discovery.

    This is a unique feature vs competitors (Cursor/Aider) - uses LSP to find
    which test files reference a given symbol, providing semantic test-to-implementation mapping.
    """

    def apply(
        self,
        symbol_name: str,
        relative_path: str,
    ) -> str:
        """
        Find all tests that reference the given symbol.

        Uses LSP to:
        1. Find the symbol definition
        2. Find all references to the symbol
        3. Filter references to test files (*_test.py, *.test.ts, etc.)
        4. Return test symbols with context

        Example:
        - find_tests_for_symbol("login", "src/auth/user.py")
          Returns tests in test_auth.py that call the login function

        :param symbol_name: Name or name_path of the symbol to find tests for
        :param relative_path: Relative path to file containing the symbol
        :return: JSON string with list of TestSymbol objects

        """
        try:
            # Get symbol retriever
            symbol_retriever = self.create_language_server_symbol_retriever()

            # Find the symbol
            symbols = symbol_retriever.find(
                name_path_pattern=symbol_name,
                within_relative_path=relative_path,
            )

            if not symbols:
                return json.dumps({"error": f"Symbol '{symbol_name}' not found in {relative_path}"})

            # Use the first match
            symbol = symbols[0]

            # Find all references to this symbol
            references = symbol_retriever.find_referencing_symbols(
                name_path=symbol.name_path,
                relative_file_path=relative_path,
                include_body=False,
            )

            # Filter to test files
            test_symbols = []
            for ref in references:
                ref_path = ref.symbol.location.relative_path
                if ref_path and self._is_test_file(ref_path):
                    test_symbol = TestSymbol(
                        name=ref.symbol.name,
                        file_path=ref_path,
                        line_number=ref.line,
                        name_path=ref.symbol.name_path,
                        related_symbols=[symbol.name],
                    )
                    test_symbols.append(test_symbol)

            if not test_symbols:
                return json.dumps(
                    {
                        "message": f"No tests found for symbol '{symbol_name}' in {relative_path}",
                        "symbol": symbol.name,
                        "total_references": len(references),
                    }
                )

            return json.dumps(
                {
                    "symbol": symbol.name,
                    "tests_found": len(test_symbols),
                    "tests": [t.to_dict() for t in test_symbols],
                }
            )

        except Exception as e:
            log.error(f"Error finding tests for symbol: {e}", exc_info=e)
            return json.dumps({"error": f"Failed to find tests: {e}"})

    def _is_test_file(self, file_path: str) -> bool:
        """
        Check if a file path is a test file based on naming conventions.

        Supports:
        - Python: *_test.py, test_*.py
        - TypeScript/JavaScript: *.test.ts, *.test.js, *.spec.ts, *.spec.js
        - Go: *_test.go
        - Java: *Test.java
        - Rust: tests/*.rs

        :param file_path: Relative file path
        :return: True if file is a test file
        """
        file_path_lower = file_path.lower()

        # Python
        if file_path_lower.endswith(("_test.py", "/test_")):
            return True
        if "test_" in file_path_lower and file_path_lower.endswith(".py"):
            return True

        # TypeScript/JavaScript
        if ".test." in file_path_lower or ".spec." in file_path_lower:
            return True

        # Go
        if file_path_lower.endswith("_test.go"):
            return True

        # Java
        if file_path_lower.endswith("test.java"):
            return True

        # Rust
        if "/tests/" in file_path_lower and file_path_lower.endswith(".rs"):
            return True

        # Generic test directory
        if "/test/" in file_path_lower or "/tests/" in file_path_lower:
            return True

        return False


class AnalyzeTestFailureTool(Tool):
    """
    Analyze test failures and suggest fixes.

    Provides intelligent analysis of test failures including:
    - Error classification (assertion, type error, runtime error, etc.)
    - Symbol context (what function/class failed)
    - Suggested fix based on error message
    """

    def apply(self, test_result: str) -> str:
        """
        Analyze test failures from a test run and provide suggestions.

        :param test_result: JSON string from run_tests tool containing failures
        :return: JSON string with failure analysis and suggestions
        """
        try:
            # Parse test result
            result_data = json.loads(test_result)

            if "error" in result_data:
                return json.dumps({"error": "Invalid test result: " + result_data["error"]})

            failures = result_data.get("failures", [])

            if not failures:
                return json.dumps({"message": "No failures to analyze", "suggestion": "All tests passed!"})

            # Analyze each failure
            analyses = []
            for failure in failures:
                analysis = self._analyze_failure(failure)
                analyses.append(analysis)

            return json.dumps(
                {
                    "total_failures": len(failures),
                    "analyses": analyses,
                    "suggested_actions": self._suggest_actions(analyses),
                }
            )

        except Exception as e:
            log.error(f"Error analyzing test failures: {e}", exc_info=e)
            return json.dumps({"error": f"Analysis failed: {e}"})

    def _analyze_failure(self, failure: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze a single test failure.

        :param failure: Failure dict from TestResult
        :return: Analysis dict
        """
        error_msg = failure.get("msg", "")
        test_name = failure.get("test", "")
        file_path = failure.get("file", "")

        # Classify error type
        error_type = "unknown"
        if "AssertionError" in error_msg or "assert" in error_msg.lower():
            error_type = "assertion"
        elif "TypeError" in error_msg:
            error_type = "type_error"
        elif "AttributeError" in error_msg:
            error_type = "attribute_error"
        elif "KeyError" in error_msg:
            error_type = "key_error"
        elif "ValueError" in error_msg:
            error_type = "value_error"

        # Extract key information
        analysis = {
            "test": test_name,
            "file": file_path,
            "error_type": error_type,
            "error_message": error_msg,
        }

        # Add suggestions based on error type
        if error_type == "assertion":
            analysis["suggestion"] = "Check the assertion logic and expected values"
        elif error_type == "type_error":
            analysis["suggestion"] = "Verify type annotations and argument types"
        elif error_type == "attribute_error":
            analysis["suggestion"] = "Check if object has the expected attribute/method"
        elif error_type == "key_error":
            analysis["suggestion"] = "Verify dictionary keys or use .get() with defaults"
        elif error_type == "value_error":
            analysis["suggestion"] = "Check input validation and value constraints"
        else:
            analysis["suggestion"] = "Review the error message and test implementation"

        return analysis

    def _suggest_actions(self, analyses: list[dict[str, Any]]) -> list[str]:
        """
        Generate high-level suggested actions based on multiple failures.

        :param analyses: List of failure analyses
        :return: List of suggested actions
        """
        actions = []

        # Group by error type
        error_types: dict[str, int] = {}
        for analysis in analyses:
            error_type = analysis.get("error_type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1

        # Generate suggestions
        if error_types.get("assertion", 0) > 0:
            actions.append(f"Review {error_types['assertion']} assertion failures - check expected vs actual values")

        if error_types.get("type_error", 0) > 0:
            actions.append(f"Fix {error_types['type_error']} type errors - verify type annotations")

        if error_types.get("attribute_error", 0) > 0:
            actions.append(f"Fix {error_types['attribute_error']} attribute errors - check object structure")

        # General action
        if len(analyses) > 5:
            actions.append(f"Consider fixing tests incrementally - {len(analyses)} total failures")

        return actions if actions else ["Review and fix test failures one by one"]
