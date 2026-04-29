# Cursor-Based Code Navigation and Editing

Serena provides a cursor-based interface for incrementally exploring and editing code
structure through LSP graph edges. Instead of jumping directly to a symbol, you place
a **cursor** on a symbol and then **move** it along relationships like containment,
references, calls, and type hierarchy. Edits (replace body, insert before/after,
rename) are issued at the cursor's current position.

The cursor is the full MCP-exposed interface for LSP-addressable (symbol-level)
activity: search, navigation, overview, read, and edit. The older path-and-name-path
symbol tools (`find_symbol`, `get_symbols_overview`, `find_referencing_symbols`,
`replace_symbol_body`, `insert_before_symbol`, `insert_after_symbol`, `rename_symbol`)
are still available as Python classes for direct CLI / API use, but are no longer
surfaced as default MCP tools — the cursor primitives cover all of their uses.

## Concepts

### Cursor
A cursor is a named position in the code graph. You start it at a symbol, then move
it to neighboring symbols. Each cursor maintains a **trail** of every position it has
visited, giving you a breadcrumb path through the code.

### Edge Types
Cursors navigate along seven types of edges:

| Edge Type | Direction | Description |
|---|---|---|
| `contains` | Parent -> Children | Symbols defined inside the current symbol (e.g. methods of a class) |
| `references` | Outgoing | Definitions that the current symbol points to |
| `referenced-by` | Incoming | Symbols that reference the current symbol |
| `calls` | Outgoing | Functions/methods called by the current symbol |
| `called-by` | Incoming | Functions/methods that call the current symbol |
| `inherits` | Upward | Supertypes of the current symbol |
| `inherited-by` | Downward | Subtypes of the current symbol |

All edge types are enabled by default. You can configure which edges a cursor follows
to focus on specific relationships.

```{note}
Not all language servers support all edge types. For example, some Python language
servers do not support type hierarchy queries (`inherits`/`inherited-by`). The cursor
will gracefully skip unavailable edges.
```

## Tools

Cursor tools are enabled by default and cover search, navigation, overview, and edit.

### cursor_start
Start a new cursor at a symbol identified by an exact (unique) name path. Returns the
symbol's neighborhood showing all reachable symbols via active edge types.

**Parameters:**
- `name_path` (required): name path of the symbol (e.g. `MyClass/my_method`).
- `relative_path` (optional): file path to narrow the symbol search.
- `cursor_id` (optional): explicit cursor ID. Auto-generated if omitted.

### cursor_find
Pattern / substring search for symbols (multi-match variant of `cursor_start`). If the
pattern matches exactly one symbol a cursor is started there; otherwise the candidate
list is returned so you can refine your pattern.

**Parameters:**
- `name_path_pattern` (required): name path matching pattern.
- `relative_path` (optional): file or directory to restrict the search.
- `depth` (optional): depth of descendants to include for each match.
- `include_body` (optional): include each match's body.
- `include_kinds` / `exclude_kinds` (optional): LSP symbol-kind filters.
- `substring_matching` (optional): substring-match the last segment of the pattern.
- `max_matches` (optional): cap the match count.
- `cursor_id` (optional): ID to use if the match is unique.
- `max_answer_chars` (optional): cap the returned payload size.

### cursor_overview
List the top-level symbols in a file. Cursor-first replacement for the old
`get_symbols_overview` tool.

**Parameters:**
- `relative_path` (required): path to the source file.
- `cursor_id` (optional): ID for the cursor (currently informational).
- `max_answer_chars` (optional): cap output size.

### cursor_move
Move the cursor to an adjacent symbol. The target should be visible in the cursor's
current neighborhood.

**Parameters:**
- `cursor_id` (required): the cursor to move.
- `target_name` (required): name of the target symbol from the neighborhood.
- `target_relative_path` (optional): file path to disambiguate.

### cursor_look
Re-examine the cursor's current position and neighborhood without moving.

### cursor_configure
Configure which edge types a cursor follows and whether the symbol body is shown.

**Parameters:**
- `cursor_id` (required).
- `edge_types` (optional): list of edge type names; empty = all.
- `include_body` (optional).

### cursor_history
Show the trail of symbols visited by a cursor, from start to current position.

### cursor_close
Close a cursor and free its resources.

### cursor_replace_body
Replace the body of the symbol at the cursor. The cursor remains on the same symbol
and its stored location is refreshed.

**Parameters:**
- `cursor_id` (required).
- `body` (required): the new body text. Does NOT include preceding docstrings /
  comments / imports.

### cursor_insert_before
Insert content immediately before the symbol at the cursor. The cursor stays on the
target symbol.

**Parameters:**
- `cursor_id` (required).
- `body` (required): content to insert.

### cursor_insert_after
Insert content immediately after the symbol at the cursor. The cursor stays on the
target symbol.

**Parameters:**
- `cursor_id` (required).
- `body` (required): content to insert.

### cursor_rename
Rename the symbol at the cursor throughout the codebase using the language server's
refactoring support. The cursor re-anchors to the renamed symbol.

**Parameters:**
- `cursor_id` (required).
- `new_name` (required).

## Usage Patterns

### Exploring a Class
1. `cursor_start` at the class name (or `cursor_find` if you only know a substring).
2. `cursor_move` into a method of interest.
3. `cursor_configure` with `edge_types: ["calls"]` to see what the method calls.
4. `cursor_move` to follow a call chain.
5. `cursor_history` to review your exploration path.

### Tracing References
1. `cursor_start` at a symbol you want to trace.
2. `cursor_configure` with `edge_types: ["referenced-by"]` to see all usage sites.
3. `cursor_move` to a reference to inspect the calling context.

### Editing at the Cursor
1. `cursor_start` (or `cursor_find`) to place the cursor on the symbol to edit.
2. Optionally `cursor_configure` with `include_body=True` to review the current body.
3. `cursor_replace_body`, `cursor_insert_before`, `cursor_insert_after`, or
   `cursor_rename` to perform the edit.

## Migration from the Old Symbol Tools

| Old tool | Cursor equivalent |
|---|---|
| `find_symbol` | `cursor_find` |
| `get_symbols_overview` | `cursor_overview` |
| `find_referencing_symbols` | `cursor_start` + `cursor_configure edge_types=["referenced-by"]` + `cursor_look` |
| `replace_symbol_body` | `cursor_start` / `cursor_find` + `cursor_replace_body` |
| `insert_before_symbol` | `cursor_start` / `cursor_find` + `cursor_insert_before` |
| `insert_after_symbol` | `cursor_start` / `cursor_find` + `cursor_insert_after` |
| `rename_symbol` | `cursor_start` / `cursor_find` + `cursor_rename` |

The old tools are marked `ToolMarkerOptional` and remain available as Python classes
for direct CLI / API use, and can be re-enabled over MCP by adding their names to
`included_optional_tools` in your context or mode configuration.

## Multiple Cursors
You can have multiple cursors active simultaneously. Each cursor maintains independent
state (position, trail, edge-type configuration). This is useful for comparing
different parts of the code or maintaining context while exploring a call chain.

## Disabling Cursor Tools
Cursor tools are enabled by default. To disable them, add the cursor tool names to
the `excluded_tools` list in your project / mode / context configuration.
