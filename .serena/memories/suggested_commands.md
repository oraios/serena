# Suggested Commands for Serena

## Essential Development Commands
- **Formatting**: `uv run poe format` (Runs Black + Ruff)
- **Type Checking**: `uv run poe type-check` (Runs Mypy)
- **Linting**: `uv run poe lint` (Checks style without fixing)
- **Testing**: `uv run poe test` (Runs default tests)

## Selective Testing
- **Specific Language**: `uv run poe test -m "<language_marker>"` (e.g., `uv run poe test -m python`)
- **Snapshot Tests**: `uv run poe test -m snapshot`

## Project Execution
- **MCP Server**: `uv run serena-mcp-server`
- **Indexing**: `uv run index-project` (Index current project for better tool performance)

## Utility Commands
- **Docs Build**: `uv run poe doc-build`
- **Clean Docs**: `uv run poe doc-clean`
