# SPEC: Multi-Folder Memory Support (CLI-Based)

## Overview

Add multi-folder memory support to Serena via CLI argument `--additional-folders`. This allows configuring shared memory folders in the MCP server JSON config (e.g., `.claude.json`).

## Configuration

**MCP Server Config (`.claude.json`):**
```json
{
  "serena": {
    "type": "stdio",
    "command": "uvx",
    "args": [
      "--from", "git+https://github.com/oraios/serena",
      "serena", "start-mcp-server",
      "--context", "ide-assistant",
      "--project", "./",
      "--additional-folders", "../shared/.serena/memories,/team/common-memories",
      "--enable-web-dashboard=false"
    ]
  }
}
```

## Behavior

All memory operations work across ALL configured folders:

| Operation | Behavior |
|-----------|----------|
| `list_memories` | Aggregates from primary + additional folders (unique names) |
| `load_memory` | Searches primary first, then additional folders |
| `save_memory` | Writes to existing location, or primary folder if new |
| `delete_memory` | Deletes from wherever memory exists |

**Primary folder:** `.serena/memories/` (always searched first, default for new memories)

## Files to Modify

### 1. `src/serena/cli.py`
- Add `--additional-folders` CLI option (comma-separated string)
- Parse and pass to `create_mcp_server()`

### 2. `src/serena/mcp.py`
- Add `additional_memory_folders` parameter to `create_mcp_server()`
- Pass through to `SerenaAgent`

### 3. `src/serena/agent.py`
- Add `additional_memory_folders` parameter to `__init__`
- Store and pass to `Project` when activating

### 4. `src/serena/project.py`
- Add `additional_folders` parameter to `MemoriesManager.__init__`
- Add `_resolve_additional_folders()` helper
- Add `_find_memory()` helper to search all folders
- Update `load_memory()`, `save_memory()`, `delete_memory()`, `list_memories()`

## Code Style Rules

**IMPORTANT: These rules MUST be followed for all changes:**

1. **Do NOT rename existing variables** - Keep original variable names (e.g., `memory_file_path` not `path`)
2. **Preserve all existing inline comments** - Do not remove helpful comments (e.g., the comment about `.md` extension stripping)
3. **Do NOT add unnecessary docstrings** - Keep code minimal; only add docstrings if strictly needed
4. **Follow existing patterns** - Match the style of surrounding code
5. **Minimal changes only** - Only change what is strictly necessary for the feature

## Implementation Details

### MemoriesManager Changes

```python
class MemoriesManager:
    def __init__(self, project_root: str, additional_folders: list[str] | None = None):
        self._project_root = Path(project_root)
        self._memory_dir = Path(...) / "memories"  # primary
        self._additional_folders = self._resolve_additional_folders(additional_folders or [])

    def _resolve_additional_folders(self, folders: list[str]) -> list[Path]:
        # Resolve relative/absolute paths, filter existing dirs

    def _find_memory(self, name: str) -> Path | None:
        # strip .md from the name. Models tend to get confused...
        # Search primary first, then additional folders
        # Return path if found, None otherwise

    def load_memory(self, name: str) -> str:
        memory_file_path = self._find_memory(name)  # Keep variable name!
        # ...

    def save_memory(self, name: str, content: str) -> str:
        memory_file_path = self._find_memory(name) or self.get_memory_file_path(name)
        # ...

    def delete_memory(self, name: str) -> str:
        memory_file_path = self._find_memory(name)
        # ...

    def list_memories(self) -> list[str]:
        # Aggregate unique names from all folders
```

## Verification

1. `uv run poe format`
2. `uv run poe type-check`
3. `uv run poe test -m python`
4. Manual test with `--additional-folders` CLI arg

## Development Guidelines

- Follow existing code patterns
- Use `pathlib.Path` for all path operations
- Use `SERENA_FILE_ENCODING` constant
- Log warnings for missing folders via `log.warning()`
