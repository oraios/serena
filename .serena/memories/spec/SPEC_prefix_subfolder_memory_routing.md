# SPEC: Prefix-Based Additional Folder Routing

## Overview

Enhance memory write operations to automatically route memories with ALL CAPS
prefixes to matching **additional folders** loaded from CLI. The folder name
(lowercase) is matched against the prefix (lowercase). For example, if
`--additional-folders ".serena/memories/feature"` is configured, then
`FEATURE_user_auth` writes to `.serena/memories/feature/FEATURE_user_auth.md`
and similarly if `--additional-folders "anotherfolder/memories/spec"` is
configured, then `SPEC_new_doc` writes to
`anotherfolder/memories/spec/SPEC_new_doc.md`.

## Configuration Context

Additional folders are configured via CLI:

```json
{
    "args": [
        "--additional-folders",
        ".serena/memories/feature,.serena/memories/spec"
    ]
}
```

These are loaded into `MemoriesManager._additional_folders` as a list of `Path`
objects.

## Behavior

### Prefix Detection

A valid prefix is:

- The first segment before an underscore
- All uppercase letters (A-Z only)
- Example: `FEATURE_something` has prefix `FEATURE` → matches folder named
  `feature`
- Example: `Feature_something` has NO valid prefix (not all caps)

### Multi-Segment Prefix Matching

When multiple ALL CAPS segments exist (e.g., `FEATURE_BUILDER_widget`):

1. Check `_additional_folders` for longest matching folder name:
   - If folder named `feature_builder` exists in additional folders → write
     there
   - Else if folder named `feature` exists in additional folders → write there
2. If no matching additional folder → write to primary folder
   (`.serena/memories/`)

**Important:** This feature does NOT create folders. It only routes to existing
additional folders.

### Write Operations

| Memory Name         | Additional Folders                   | Result                                           |
| ------------------- | ------------------------------------ | ------------------------------------------------ |
| `FEATURE_auth`      | `[.../feature]`                      | Writes to `.../feature/FEATURE_auth.md`          |
| `FEATURE_auth`      | `[]` (none configured)               | Writes to primary folder                         |
| `FEATURE_BUILDER_x` | `[.../feature_builder, .../feature]` | Writes to `.../feature_builder/` (longest match) |
| `FEATURE_BUILDER_x` | `[.../feature]`                      | Writes to `.../feature/`                         |
| `SPEC_new_doc`      | `[.../spec]`                         | Writes to `.../spec/SPEC_new_doc.md`             |
| `regular_name`      | any                                  | Writes to primary folder (no prefix)             |
| `edit_memory(...)`  | any                                  | Finds existing file, edits in-place              |

### Read Operations

No changes required - existing `_find_memory()` already searches all additional
folders.

## Files to Modify

### 1. `src/serena/project.py`

**Add helper method to `MemoriesManager`:**

```python
def _find_matching_additional_folder(self, name: str) -> Path | None:
    """Find additional folder whose name matches longest ALL CAPS prefix sequence."""
    name = name.replace(".md", "")
    parts = name.split("_")
    # Try longest prefix first, then shorter
    for i in range(len(parts), 0, -1):
        candidate_parts = parts[:i]
        # All parts must be ALL CAPS
        if not all(p.isupper() and p.isalpha() for p in candidate_parts):
            continue
        # Match folder name (case-insensitive)
        target_name = "_".join(candidate_parts).lower()
        for folder in self._additional_folders:
            if folder.name.lower() == target_name:
                return folder
    return None
```

**Modify `get_memory_file_path()` (lines 54-57):**

Current:

```python
def get_memory_file_path(self, name: str) -> Path:
    # strip .md from the name...
    name = name.replace(".md", "")
    return self._memory_dir / f"{name}.md"
```

New:

```python
def get_memory_file_path(self, name: str) -> Path:
    # strip .md from the name...
    name = name.replace(".md", "")
    # Route to matching additional folder if prefix matches
    matching_folder = self._find_matching_additional_folder(name)
    if matching_folder is not None:
        return matching_folder / f"{name}.md"
    return self._memory_dir / f"{name}.md"
```

### 2. `src/serena/tools/memory_tools.py`

**Fix `EditMemoryTool.apply()` (line 89):**

Current (bug - doesn't find existing files):

```python
rel_path = self.memories_manager.get_memory_file_path(memory_file_name).relative_to(...)
```

Fixed:

```python
memory_path = self.memories_manager._find_memory(memory_file_name)
if memory_path is None:
    return f"Memory file {memory_file_name} not found."
rel_path = memory_path.relative_to(self.get_project_root())
```

## Code Style Rules

**IMPORTANT: These rules MUST be followed for all changes:**

1. **Do NOT rename existing variables** - Keep original names (e.g.,
   `memory_file_path`)
2. **Preserve all existing inline comments** - Keep the `.md` stripping comment
3. **Do NOT add unnecessary docstrings** - Keep code minimal
4. **Follow existing patterns** - Match surrounding code style
5. **Minimal changes only** - Only change what is strictly necessary

## Verification

1. `uv run poe format`
2. `uv run poe type-check`
3. `uv run poe test -m python`
4. Manual testing:
   - Configure `--additional-folders ".serena/memories/feature"`
   - Create memory `FEATURE_test` → verify writes to `feature/` folder
   - Create memory `regular_test` → verify writes to primary folder
   - Edit existing memory → verify updates in-place
   - List memories → verify shows all from additional folders
