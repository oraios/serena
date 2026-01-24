"""
Built-in workflows shipped with Murena.

These workflows provide common patterns:
- test-fix-commit: Run tests, analyze failures, iterate until passing, commit
- review-pr: Lint, test, and validate PR changes
- refactor-safe: Rename symbol with test validation

All workflows use token-optimized tools for minimal context usage.
"""

BUILTIN_WORKFLOWS = [
    # test-fix-commit: Run tests, fix failures, commit
    {
        "name": "test-fix-commit",
        "description": "Run tests, analyze failures, and commit when all pass",
        "author": "Murena",
        "version": "1.0",
        "steps": [
            {
                "name": "run_tests_initial",
                "tool": "run_tests",
                "args": {"file_path": "${file}", "coverage": False},
                "description": "Run tests to establish baseline",
                "on_failure": "continue",
            },
            {
                "name": "check_tests_passed",
                "tool": "run_tests",
                "args": {"file_path": "${file}"},
                "description": "Check if tests pass after any fixes",
                "on_failure": "abort",
            },
        ],
    },
    # review-pr: Comprehensive PR review workflow
    {
        "name": "review-pr",
        "description": "Lint, test, and validate PR changes",
        "author": "Murena",
        "version": "1.0",
        "steps": [
            {
                "name": "run_tests",
                "tool": "run_tests",
                "args": {"coverage": True},
                "description": "Run all tests with coverage",
                "on_failure": "abort",
            },
        ],
    },
    # refactor-safe: Rename with test validation
    {
        "name": "refactor-safe",
        "description": "Rename symbol with automatic test validation",
        "author": "Murena",
        "version": "1.0",
        "steps": [
            {
                "name": "run_tests_before",
                "tool": "run_tests",
                "args": {},
                "description": "Establish test baseline before refactoring",
                "on_failure": "abort",
            },
            {
                "name": "rename_symbol",
                "tool": "rename_symbol",
                "args": {
                    "name_path": "${symbol}",
                    "relative_path": "${file}",
                    "new_name": "${new_name}",
                },
                "description": "Perform the rename operation",
                "on_failure": "abort",
            },
            {
                "name": "run_tests_after",
                "tool": "run_tests",
                "args": {},
                "description": "Verify tests still pass after rename",
                "on_failure": "abort",
            },
        ],
    },
    # quick-test: Just run tests with compact output
    {
        "name": "quick-test",
        "description": "Run tests with token-optimized output",
        "author": "Murena",
        "version": "1.0",
        "steps": [
            {
                "name": "run_tests",
                "tool": "run_tests",
                "args": {"file_path": "${file}", "verbose": False},
                "description": "Run tests in compact mode",
            }
        ],
    },
]
