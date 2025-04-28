# Suggested Commands

## Development Tasks (using uv and poe)

The following tasks should generally be executed using `uv run poe <task_name>`.

- `lint`: This is the **only** allowed command for linting. Run as `uv run poe lint`.
- `format`: This is the **only** allowed command for formatting. Run as `uv run poe format`.
- `type-check`: This is the **only** allowed command for type checking. Run as `uv run poe type-check`.
- `test`: This is the preferred command for running tests (`uv run poe test [args]`). However, running tests directly with `uv run pytest [args]` is also permitted.

For finishing a task, make sure format, type-check and test pass! Run them at the end of the task
and if needed fix any issues that come up and run them again until they pass.