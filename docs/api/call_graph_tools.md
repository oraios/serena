# Call Graph Tools API Reference

Complete API reference for Murena's call hierarchy and dataflow analysis tools.

## Table of Contents

- [GetIncomingCallsTool](#getincomingcallstool)
- [GetOutgoingCallsTool](#getoutgoingcallstool)
- [BuildCallGraphTool](#buildcallgraphtool)
- [FindCallPathTool](#findcallpathtool)
- [AnalyzeCallDependenciesTool](#analyzecalldependenciestool)
- [Output Formats](#output-formats)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)

---

## GetIncomingCallsTool

Find all callers of a function/method (answers "who calls this?").

### MCP Tool Name

```
mcp__murena__get_incoming_calls
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name_path` | string | Yes | - | Symbol name path (e.g., "UserService/authenticate") |
| `relative_path` | string | Yes | - | File path relative to project root |
| `include_call_sites` | boolean | No | true | Include line numbers where function is called |
| `max_depth` | integer | No | 1 | Traversal depth (1-5), higher = more indirect callers |
| `compact_format` | boolean | No | true | Use compact JSON format (70% token savings) |
| `max_answer_chars` | integer | No | -1 | Max characters in response (-1 = unlimited) |

### Returns

**Success (compact format):**
```json
{
  "s": {
    "np": "UserService/authenticate",
    "fp": "services.py",
    "ln": 15,
    "k": "Method"
  },
  "callers": [
    {
      "np": "UserAPI/login",
      "fp": "api.py",
      "ln": 42,
      "k": "Method",
      "sites": [45, 47]
    },
    {
      "np": "AdminAPI/login",
      "fp": "admin.py",
      "ln": 28,
      "k": "Method",
      "sites": [31]
    }
  ],
  "tot": 2,
  "d": 1,
  "more": false
}
```

**Success (verbose format):**
```json
{
  "symbol": {
    "name_path": "UserService/authenticate",
    "file": "services.py",
    "line": 15,
    "kind": "Method"
  },
  "incoming_calls": [
    {
      "name": "UserAPI/login",
      "file": "api.py",
      "line": 42,
      "kind": "Method",
      "call_sites": [
        {"line": 45, "column": 12},
        {"line": 47, "column": 8}
      ]
    }
  ],
  "total_callers": 2,
  "max_depth": 1,
  "has_more": false
}
```

**Error:**
```json
{
  "error": "Symbol not found: UserService/authenticate in services.py",
  "fallback": "Use find_referencing_symbols for broader search"
}
```

### Example Usage

```python
# Find direct callers
result = mcp__murena__get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    max_depth=1
)

# Find indirect callers (multi-level)
result = mcp__murena__get_incoming_calls(
    name_path="Database/query",
    relative_path="src/db.py",
    max_depth=3,  # Find callers of callers
    include_call_sites=True
)
```

### Notes

- **Language support**: FULL support for 11 languages, PARTIAL for 4, FALLBACK for 27
- **Cross-file**: Yes, finds callers across all project files
- **Performance**: P50 <300ms for depth=1, P95 <500ms
- **Precision**: 95-100% (only actual calls, not references)
- **Cache**: Results cached with 60s TTL

---

## GetOutgoingCallsTool

Find all functions/methods called by a symbol (answers "what does this call?").

### MCP Tool Name

```
mcp__murena__get_outgoing_calls
```

### Parameters

Same as [GetIncomingCallsTool](#getincomingcallstool).

### Returns

**Success (compact format):**
```json
{
  "s": {
    "np": "UserService/authenticate",
    "fp": "services.py",
    "ln": 15,
    "k": "Method"
  },
  "callees": [
    {
      "np": "Database/query",
      "fp": "db.py",
      "ln": 102,
      "k": "Method",
      "sites": [18, 22]
    },
    {
      "np": "Logger/info",
      "fp": "logger.py",
      "ln": 45,
      "k": "Method",
      "sites": [16]
    }
  ],
  "tot": 2,
  "d": 1,
  "more": false
}
```

**Success (verbose format):**
```json
{
  "symbol": {
    "name_path": "UserService/authenticate",
    "file": "services.py",
    "line": 15,
    "kind": "Method"
  },
  "outgoing_calls": [
    {
      "name": "Database/query",
      "file": "db.py",
      "line": 102,
      "kind": "Method",
      "call_sites": [
        {"line": 18, "column": 8},
        {"line": 22, "column": 8}
      ]
    }
  ],
  "total_callees": 2,
  "max_depth": 1,
  "has_more": false
}
```

### Example Usage

```python
# Find direct dependencies
result = mcp__murena__get_outgoing_calls(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    max_depth=1
)

# Find transitive dependencies (multi-level)
result = mcp__murena__get_outgoing_calls(
    name_path="UserAPI/login",
    relative_path="src/api.py",
    max_depth=3,  # Find what the callees call
    compact_format=True
)
```

### Notes

- **Use case**: Understanding dependencies, dataflow analysis
- **Performance**: Same as GetIncomingCalls
- **Tip**: Use `max_depth=2-3` for transitive dependency analysis

---

## BuildCallGraphTool

Build a multi-level call graph showing both incoming and outgoing calls.

### MCP Tool Name

```
mcp__murena__build_call_graph
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name_path` | string | Yes | - | Symbol name path |
| `relative_path` | string | Yes | - | File path relative to project root |
| `direction` | string | No | "both" | "incoming", "outgoing", or "both" |
| `max_depth` | integer | No | 2 | Traversal depth (1-5) |
| `max_nodes` | integer | No | 50 | Maximum nodes in graph (prevents explosion) |
| `include_call_sites` | boolean | No | true | Include line numbers for calls |
| `compact_format` | boolean | No | true | Use compact JSON format |
| `max_answer_chars` | integer | No | -1 | Max characters in response |

### Returns

**Success (compact format):**
```json
{
  "s": {
    "np": "UserService/authenticate",
    "fp": "services.py",
    "ln": 15
  },
  "nodes": [
    {
      "id": "UserService/authenticate",
      "np": "UserService/authenticate",
      "fp": "services.py",
      "ln": 15,
      "k": "Method"
    },
    {
      "id": "UserAPI/login",
      "np": "UserAPI/login",
      "fp": "api.py",
      "ln": 42,
      "k": "Method"
    },
    {
      "id": "Database/query",
      "np": "Database/query",
      "fp": "db.py",
      "ln": 102,
      "k": "Method"
    }
  ],
  "edges": [
    {"from": "UserAPI/login", "to": "UserService/authenticate", "sites": [45]},
    {"from": "UserService/authenticate", "to": "Database/query", "sites": [18]}
  ],
  "tot_nodes": 3,
  "tot_edges": 2,
  "d": 2,
  "trunc": false
}
```

**Success (verbose format):**
```json
{
  "root_symbol": {
    "name_path": "UserService/authenticate",
    "file": "services.py",
    "line": 15
  },
  "graph": {
    "nodes": [
      {
        "id": "UserService/authenticate",
        "name_path": "UserService/authenticate",
        "file": "services.py",
        "line": 15,
        "kind": "Method"
      }
    ],
    "edges": [
      {
        "from": "UserAPI/login",
        "to": "UserService/authenticate",
        "type": "calls",
        "call_sites": [{"line": 45, "column": 12}]
      }
    ]
  },
  "total_nodes": 3,
  "total_edges": 2,
  "max_depth": 2,
  "truncated": false
}
```

### Example Usage

```python
# Build incoming call graph (who depends on this)
graph = mcp__murena__build_call_graph(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    direction="incoming",
    max_depth=2,
    max_nodes=30
)

# Build complete call graph (dependencies + dependents)
graph = mcp__murena__build_call_graph(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    direction="both",
    max_depth=2,
    max_nodes=50
)

# Build outgoing call graph (what this depends on)
graph = mcp__murena__build_call_graph(
    name_path="UserAPI/login",
    relative_path="src/api.py",
    direction="outgoing",
    max_depth=3,
    max_nodes=40
)
```

### Notes

- **Token cost**: ~1,000 tokens for 20 nodes at depth=2 (compact)
- **Performance**: P50 <800ms, P95 <1500ms for depth=2
- **Tip**: Set `max_nodes` to prevent token explosion on large graphs
- **Truncation**: If graph exceeds `max_nodes`, `truncated` flag is set

---

## FindCallPathTool

Find execution path(s) between two symbols (answers "how do I get from A to Z?").

### MCP Tool Name

```
mcp__murena__find_call_path
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `from_name_path` | string | Yes | - | Starting symbol name path |
| `from_file` | string | Yes | - | Starting symbol file path |
| `to_name_path` | string | Yes | - | Target symbol name path |
| `to_file` | string | Yes | - | Target symbol file path |
| `max_depth` | integer | No | 5 | Maximum path length (1-10) |
| `find_all_paths` | boolean | No | false | Find all paths or just first one |
| `compact_format` | boolean | No | true | Use compact JSON format |
| `max_answer_chars` | integer | No | -1 | Max characters in response |

### Returns

**Success (compact format):**
```json
{
  "from": {
    "np": "UserAPI/login",
    "fp": "api.py",
    "ln": 42
  },
  "to": {
    "np": "Database/query",
    "fp": "db.py",
    "ln": 102
  },
  "paths": [
    {
      "len": 2,
      "hops": [
        {"np": "UserAPI/login", "fp": "api.py", "ln": 42},
        {"np": "UserService/authenticate", "fp": "services.py", "ln": 15},
        {"np": "Database/query", "fp": "db.py", "ln": 102}
      ]
    },
    {
      "len": 3,
      "hops": [
        {"np": "UserAPI/login", "fp": "api.py", "ln": 42},
        {"np": "UserService/validate", "fp": "services.py", "ln": 8},
        {"np": "Validator/check", "fp": "validator.py", "ln": 25},
        {"np": "Database/query", "fp": "db.py", "ln": 102}
      ]
    }
  ],
  "tot": 2,
  "d": 5
}
```

**No path found:**
```json
{
  "from": {...},
  "to": {...},
  "paths": [],
  "tot": 0,
  "msg": "No call path found between symbols (max depth: 5)"
}
```

### Example Usage

```python
# Find shortest path
path = mcp__murena__find_call_path(
    from_name_path="UserAPI/create_user",
    from_file="src/api.py",
    to_name_path="Database/insert",
    to_file="src/db.py",
    max_depth=5,
    find_all_paths=False  # First path only
)

# Find all possible paths (dataflow analysis)
paths = mcp__murena__find_call_path(
    from_name_path="UserAPI/login",
    from_file="src/api.py",
    to_name_path="Database/query",
    to_file="src/db.py",
    max_depth=5,
    find_all_paths=True  # All paths
)
```

### Notes

- **Use case**: Dataflow tracing, understanding execution paths
- **Performance**: P50 <2000ms, P95 <3000ms for depth=5
- **Tip**: Use `find_all_paths=False` for faster results
- **Limitation**: Only finds paths via direct function calls (not indirect via callbacks)

---

## AnalyzeCallDependenciesTool

Analyze dependencies and impact of changing a symbol.

### MCP Tool Name

```
mcp__murena__analyze_call_dependencies
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name_path` | string | Yes | - | Symbol name path to analyze |
| `relative_path` | string | Yes | - | File path relative to project root |
| `analysis_type` | string | No | "impact" | "impact", "usage", or "hotspots" |
| `max_depth` | integer | No | 3 | Traversal depth for analysis |
| `include_tests` | boolean | No | true | Include test callers in analysis |
| `compact_format` | boolean | No | true | Use compact JSON format |
| `max_answer_chars` | integer | No | -1 | Max characters in response |

### Returns

**Success (impact analysis):**
```json
{
  "s": {
    "np": "UserService/authenticate",
    "fp": "services.py",
    "ln": 15
  },
  "type": "impact",
  "direct_callers": 3,
  "indirect_callers": 8,
  "tot_callers": 11,
  "test_callers": 2,
  "hotspots": [
    {
      "np": "UserAPI/login",
      "fp": "api.py",
      "freq": 5,
      "importance": "high"
    }
  ],
  "risk": "medium",
  "msg": "11 callers across 3 modules. 2 test files provide coverage."
}
```

**Success (hotspots analysis):**
```json
{
  "s": {...},
  "type": "hotspots",
  "hotspots": [
    {
      "np": "UserService/authenticate",
      "fp": "services.py",
      "calls_in": 15,
      "calls_out": 8,
      "importance": "critical"
    }
  ],
  "tot": 1
}
```

### Analysis Types

**1. impact** (default)
- Direct and indirect callers
- Test coverage
- Risk assessment
- Hotspot identification

**2. usage**
- How symbol is used across codebase
- Call frequency
- Common usage patterns

**3. hotspots**
- Most-called functions
- Bottlenecks
- Critical dependencies

### Example Usage

```python
# Impact analysis before refactoring
impact = mcp__murena__analyze_call_dependencies(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    analysis_type="impact",
    max_depth=3
)

# Find hotspots for optimization
hotspots = mcp__murena__analyze_call_dependencies(
    name_path="Database/query",
    relative_path="src/db.py",
    analysis_type="hotspots",
    max_depth=2
)

# Usage pattern analysis
usage = mcp__murena__analyze_call_dependencies(
    name_path="Logger/log",
    relative_path="src/logger.py",
    analysis_type="usage",
    include_tests=False
)
```

### Notes

- **Use case**: Safe refactoring, impact analysis, performance optimization
- **Risk levels**: "low" (<5 callers), "medium" (5-20), "high" (>20)
- **Tip**: Review `hotspots` array for critical dependencies

---

## Output Formats

### Compact Format (Default)

**Benefits:**
- 70% token savings vs verbose
- Faster parsing
- Better for large results

**Field abbreviations:**
- `np` = name_path
- `fp` = file_path (relative)
- `ln` = line
- `k` = kind
- `s` = symbol
- `tot` = total
- `d` = depth
- `trunc` = truncated

### Verbose Format

**Benefits:**
- Human-readable
- Self-documenting
- Better for debugging

**When to use:**
- Small result sets
- Human review needed
- Debugging issues

---

## Error Handling

### Common Errors

**1. Symbol not found**
```json
{
  "error": "Symbol not found: MyClass/my_method in file.py",
  "suggestion": "Check name_path format (ClassName/method_name)",
  "fallback": "Use find_symbol() to locate symbol"
}
```

**2. Language not supported**
```json
{
  "error": "Call hierarchy not supported for language: Perl",
  "fallback": "Using find_referencing_symbols instead",
  "support_level": "FALLBACK"
}
```

**3. Max depth exceeded**
```json
{
  "error": "max_depth must be between 1 and 5 (got: 10)",
  "corrected": "Using max_depth=5"
}
```

**4. Timeout**
```json
{
  "error": "Operation timeout after 10s",
  "partial_results": [...],
  "suggestion": "Reduce max_depth or max_nodes"
}
```

### Fallback Behavior

For languages without call hierarchy support (FALLBACK level):
- Automatically uses `find_referencing_symbols` instead
- Precision drops to 70-85% (includes non-call references)
- Response includes `"fallback": true` flag

---

## Performance Considerations

### Latency Targets

| Operation | P50 | P95 | Notes |
|-----------|-----|-----|-------|
| prepare_call_hierarchy | <100ms | <200ms | Cached after first call |
| get_incoming_calls (d=1) | <300ms | <500ms | Single level |
| get_outgoing_calls (d=1) | <300ms | <500ms | Single level |
| build_call_graph (d=2) | <800ms | <1500ms | Multi-level |
| find_call_path (d=5) | <2000ms | <3000ms | Deep search |

### Cache Behavior

**Call hierarchy items**: 60s TTL, >80% hit rate
- First call: Full LSP request
- Cached: Near-instant response

**Invalidation**: Automatic on file changes

### Token Costs

| Operation | Depth | Results | Compact | Verbose |
|-----------|-------|---------|---------|---------|
| get_incoming_calls | 1 | 10 | 400 | 1,400 |
| get_outgoing_calls | 1 | 5 | 300 | 1,000 |
| build_call_graph | 2 | 20 nodes | 1,000 | 3,500 |
| find_call_path | 5 | 3 paths | 600 | 1,800 |

**Optimization tips:**
1. Start with `max_depth=1`, increase gradually
2. Use `compact_format=True` (default)
3. Set `max_nodes` for large graphs
4. Use `find_all_paths=False` for first path only

### Scalability

**Small codebases (<1000 files):**
- All tools performant
- Can use higher `max_depth` (3-5)
- Minimal caching needed

**Medium codebases (1000-10,000 files):**
- Use `max_depth=2-3`
- Set `max_nodes=30-50`
- Cache hit rate critical

**Large codebases (>10,000 files):**
- Start with `max_depth=1-2`
- Always set `max_nodes=20-30`
- Consider breaking into modules

---

## Language Support Reference

See [language_support_matrix.md](language_support_matrix.md) for:
- Complete list of 42 supported languages
- Support levels (FULL, PARTIAL, FALLBACK, UNKNOWN)
- LSP server capabilities
- Cross-file support details
- Fallback strategies

---

## See Also

- [CLAUDE.md - Call Graph Section](../../CLAUDE.md#-call-graph--dataflow-analysis)
- [Language Support Matrix](language_support_matrix.md)
- [Call Graph Tutorial](../tutorials/call_graph_tutorial.md)
- [Semantic Search Integration](../tutorials/semantic_search.md)
