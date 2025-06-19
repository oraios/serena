# Suggested Commands

## Development Tasks (using uv and poe)

The following tasks should generally be executed using `uv run poe <task_name>`.

- `format`: This is the **only** allowed command for formatting. Run as `uv run poe format`.
- `type-check`: This is the **only** allowed command for type checking. Run as `uv run poe type-check`.
- `test`: This is the preferred command for running tests (`uv run poe test [args]`). You can select subsets of tests with markers,
   the current markers are
   ```toml
    markers = [
        "python: language server running for Python",
        "go: language server running for Go",
        "java: language server running for Java",
        "rust: language server running for Rust",
        "typescript: language server running for TypeScript",
        "php: language server running for PHP",
        "snapshot: snapshot tests for symbolic editing operations",
        "isolated_process: test runs with process isolated agent",
    ]
   ```
  By default, `uv run poe test` uses the markers set in the env var `PYTEST_MARKERS`, or, if it unset, uses `-m "not java and not rust and not isolated process"`.
  You can override this behavior by simply passing the `-m` option to `uv run poe test`, e.g. `uv run poe test -m "python or go"`.

For finishing a task, make sure format, type-check and test pass! Run them at the end of the task
and if needed fix any issues that come up and run them again until they pass.