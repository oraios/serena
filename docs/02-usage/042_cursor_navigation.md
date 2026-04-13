# Cursor-Based Code Navigation

Serena provides a cursor-based navigation system for incrementally exploring code structure
through LSP graph edges. Instead of jumping directly to a symbol, you place a **cursor** on
a symbol and then **move** it along relationships like containment, references, calls, and
type hierarchy.

## Concepts

### Cursor
A cursor is a named position in the code graph. You start it at a symbol, then move it to
neighboring symbols. Each cursor maintains a **trail** of every position it has visited,
giving you a breadcrumb path through the code.

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
Not all language servers support all edge types. For example, some Python language servers
do not support type hierarchy queries (`inherits`/`inherited-by`). The cursor will
gracefully skip unavailable edges.
```

## Tools

Cursor navigation is available through six MCP tools. These tools are **optional** and
must be enabled in your project configuration.

### cursor_start
Start a new cursor at a symbol. Returns the symbol's neighborhood showing all reachable
symbols via active edge types.

**Parameters:**
- `name_path` (required): Name path of the symbol (e.g. `MyClass/my_method`). See `find_symbol` for pattern syntax.
- `relative_path` (optional): File path to narrow the symbol search.
- `cursor_id` (optional): Explicit cursor ID. Auto-generated if omitted.

**Example output:**
```
@ UserService (Class) [test_repo/services.py:11]
  cursor: c1 | trail: 0 steps

  contains:
    __init__ (Method) [test_repo/services.py:13]
    create_user (Method) [test_repo/services.py:16]
    get_user (Method) [test_repo/services.py:25]
    list_users (Method) [test_repo/services.py:29]
    delete_user (Method) [test_repo/services.py:33]

  referenced-by:
    user_service (Variable) [test_repo/services.py:77]

Use cursor_move to navigate to a neighbor, cursor_look to re-examine.
```

### cursor_move
Move the cursor to an adjacent symbol. The target should be visible in the cursor's
current neighborhood.

**Parameters:**
- `cursor_id` (required): The cursor to move.
- `target_name` (required): Name of the target symbol from the neighborhood.
- `target_relative_path` (optional): File path to disambiguate when multiple neighbors share the same name.

### cursor_look
Re-examine the cursor's current position and neighborhood without moving. Useful after
changing edge type configuration.

**Parameters:**
- `cursor_id` (required): The cursor to look from.

### cursor_configure
Configure which edge types a cursor follows and what information is shown.

**Parameters:**
- `cursor_id` (required): The cursor to configure.
- `edge_types` (optional): List of edge type names to enable. If empty, all are enabled.
- `include_body` (optional): Whether to include the symbol's source code body.

### cursor_history
Show the trail of symbols visited by a cursor, from start to current position.

**Parameters:**
- `cursor_id` (required): The cursor to show history for.

**Example output:**
```
Cursor c1 trail (2 steps):
  1. test_repo/services.py:11
  2. test_repo/services.py:16
  -> test_repo/services.py:25 (current)
```

### cursor_close
Close a cursor and free its resources.

**Parameters:**
- `cursor_id` (required): The cursor to close.

## Usage Patterns

### Exploring a Class
1. `cursor_start` at the class name to see its methods and references.
2. `cursor_move` into a method of interest.
3. `cursor_configure` with `edge_types: ["calls"]` to see what the method calls.
4. `cursor_move` to follow a call chain.
5. `cursor_history` to review your exploration path.

### Tracing References
1. `cursor_start` at a symbol you want to trace.
2. `cursor_configure` with `edge_types: ["referenced-by"]` to see all usage sites.
3. `cursor_move` to a reference to inspect the calling context.

### Navigating Type Hierarchies
1. `cursor_start` at a class.
2. `cursor_configure` with `edge_types: ["inherits", "inherited-by"]` to focus on inheritance.
3. `cursor_move` up to supertypes or down to subtypes.

## Multiple Cursors
You can have multiple cursors active simultaneously. Each cursor maintains independent
state (position, trail, edge type configuration). This is useful for comparing different
parts of the code or maintaining context while exploring a call chain.

## Enabling Cursor Tools
Cursor tools are optional and not enabled by default. To enable them, ensure your project
configuration does not exclude them. The tools are marked with `ToolMarkerOptional`, so they
will appear in the tool list only when explicitly included.
