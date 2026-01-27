# Call Graph Analysis Tutorial

Interactive tutorial for using Murena's call hierarchy and dataflow analysis tools.

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Tutorial 1: Impact Analysis Before Refactoring](#tutorial-1-impact-analysis-before-refactoring)
4. [Tutorial 2: Understanding Data Flow](#tutorial-2-understanding-data-flow)
5. [Tutorial 3: Finding Code Hotspots](#tutorial-3-finding-code-hotspots)
6. [Tutorial 4: Natural Language Queries](#tutorial-4-natural-language-queries)
7. [Tutorial 5: Multi-Language Support](#tutorial-5-multi-language-support)
8. [Common Patterns](#common-patterns)
9. [Troubleshooting](#troubleshooting)
10. [Best Practices](#best-practices)

---

## Introduction

Call graph analysis helps you understand:
- **Dependencies**: What does this code depend on?
- **Impact**: What breaks if I change this?
- **Data flow**: How does data move through the system?
- **Architecture**: How are components connected?

Murena provides 5 specialized tools for call graph analysis, all accessible via MCP protocol from Claude Code.

### Prerequisites

- Murena MCP server running (`uv run murena-mcp-server`)
- Project with source code in a supported language
- Basic familiarity with your codebase structure

---

## Quick Start

### Example Project Structure

```
my-project/
├── src/
│   ├── api.py          # API endpoints
│   ├── services.py     # Business logic
│   ├── db.py          # Database queries
│   └── validator.py   # Input validation
└── tests/
    └── test_api.py    # Tests
```

### Your First Call Graph Query

**Natural language approach:**
```python
# Ask Claude Code a natural language question
mcp__murena__intelligent_search(
    query="who calls the authenticate function?",
    max_results=10
)
```

**Direct tool approach:**
```python
# Use the specific tool
mcp__murena__get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    max_depth=1
)
```

Both approaches find who calls `authenticate()`, but the second is more explicit and provides more control.

---

## Tutorial 1: Impact Analysis Before Refactoring

**Scenario:** You need to change the signature of `UserService.authenticate()` from:
```python
def authenticate(username, password):
```

to:
```python
def authenticate(credentials: dict):
```

**Question:** What will break?

### Step 1: Find Direct Callers

```python
# Find everything that calls authenticate()
direct_callers = mcp__murena__get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    max_depth=1,
    include_call_sites=True,
    compact_format=True
)
```

**Result:**
```json
{
  "s": {"np": "UserService/authenticate", "fp": "services.py", "ln": 45},
  "callers": [
    {"np": "UserAPI/login", "fp": "api.py", "ln": 23, "sites": [28, 35]},
    {"np": "AdminAPI/login", "fp": "admin.py", "ln": 15, "sites": [20]},
    {"np": "test_authenticate", "fp": "tests/test_auth.py", "ln": 10, "sites": [12, 15, 18]}
  ],
  "tot": 3,
  "d": 1,
  "more": false
}
```

**Analysis:**
- ✅ **3 direct callers** found
- ✅ **2 production files** to update: `api.py`, `admin.py`
- ✅ **1 test file** to update: `tests/test_auth.py`
- ✅ **Call sites** show exact lines: `api.py:28, api.py:35, admin.py:20`

### Step 2: Find Indirect Callers

```python
# Who calls the callers? (2-level analysis)
indirect_callers = mcp__murena__get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    max_depth=2,  # Go 2 levels deep
    compact_format=True
)
```

**Result:**
```json
{
  "callers": [
    {"np": "UserAPI/login", "fp": "api.py", "sites": [28, 35]},
    {"np": "Router/handle_login", "fp": "router.py", "sites": [42]},
    ...
  ],
  "tot": 5,
  "d": 2
}
```

**Analysis:**
- ⚠️ **5 total callers** (2 more indirect)
- ⚠️ `Router/handle_login` also affected (calls `UserAPI/login`)
- ✅ Now you have complete impact picture

### Step 3: Analyze Full Impact

```python
# Get comprehensive impact analysis
impact = mcp__murena__analyze_call_dependencies(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    analysis_type="impact",
    max_depth=3
)
```

**Result:**
```json
{
  "direct_callers": 3,
  "indirect_callers": 5,
  "tot_callers": 8,
  "test_callers": 1,
  "risk": "medium",
  "msg": "8 callers across 4 modules. 1 test file provides coverage.",
  "hotspots": [
    {"np": "UserAPI/login", "freq": 5, "importance": "high"}
  ]
}
```

**Action Plan:**
1. ✅ Update 3 direct call sites in `api.py`, `admin.py`
2. ✅ Verify `Router/handle_login` still works
3. ✅ Update test in `test_auth.py`
4. ⚠️ Focus on `UserAPI/login` (high frequency hotspot)

### Step 4: Safe Refactoring

Now you know:
- **What to update**: 8 call sites across 4 files
- **Risk level**: Medium (manageable)
- **Test coverage**: 1 test file (add more tests if needed)
- **Hotspots**: `UserAPI/login` is critical (test thoroughly)

---

## Tutorial 2: Understanding Data Flow

**Scenario:** You need to trace how user input flows from API to database.

**Question:** What's the path from `UserAPI.create_user()` to `Database.insert()`?

### Step 1: Find the Path

```python
# Find execution path
path = mcp__murena__find_call_path(
    from_name_path="UserAPI/create_user",
    from_file="src/api.py",
    to_name_path="Database/insert",
    to_file="src/db.py",
    max_depth=5,
    find_all_paths=True  # Show all possible paths
)
```

**Result:**
```json
{
  "from": {"np": "UserAPI/create_user", "fp": "api.py", "ln": 15},
  "to": {"np": "Database/insert", "fp": "db.py", "ln": 102},
  "paths": [
    {
      "len": 2,
      "hops": [
        {"np": "UserAPI/create_user", "fp": "api.py", "ln": 15},
        {"np": "UserService/create", "fp": "services.py", "ln": 50},
        {"np": "Database/insert", "fp": "db.py", "ln": 102}
      ]
    },
    {
      "len": 3,
      "hops": [
        {"np": "UserAPI/create_user", "fp": "api.py", "ln": 15},
        {"np": "UserService/validate_and_create", "fp": "services.py", "ln": 65},
        {"np": "Validator/check_user_data", "fp": "validator.py", "ln": 30},
        {"np": "Database/insert", "fp": "db.py", "ln": 102}
      ]
    }
  ],
  "tot": 2,
  "d": 5
}
```

**Analysis:**
- ✅ **2 execution paths** found
- 📍 **Path 1** (short): `API → Service → DB` (2 hops)
- 📍 **Path 2** (validated): `API → Service → Validator → DB` (3 hops)

**Insight:** Some requests go directly to DB, others validate first!

### Step 2: Trace Path 2 in Detail

```python
# Build detailed call graph for validation path
graph = mcp__murena__build_call_graph(
    name_path="UserService/validate_and_create",
    relative_path="src/services.py",
    direction="outgoing",  # What does it call?
    max_depth=2,
    max_nodes=20
)
```

**Result:**
```json
{
  "nodes": [
    {"id": "UserService/validate_and_create", ...},
    {"id": "Validator/check_user_data", ...},
    {"id": "Validator/check_email", ...},
    {"id": "Validator/check_password_strength", ...},
    {"id": "Database/insert", ...}
  ],
  "edges": [
    {"from": "UserService/validate_and_create", "to": "Validator/check_user_data"},
    {"from": "Validator/check_user_data", "to": "Validator/check_email"},
    {"from": "Validator/check_user_data", "to": "Validator/check_password_strength"},
    {"from": "UserService/validate_and_create", "to": "Database/insert"}
  ],
  "tot_nodes": 5,
  "tot_edges": 4
}
```

**Visualization:**
```
UserService/validate_and_create
    ├─> Validator/check_user_data
    │       ├─> Validator/check_email
    │       └─> Validator/check_password_strength
    └─> Database/insert
```

**Security Finding:** Data flows through validators before reaching DB! ✅

### Step 3: Check Path 1 (Non-Validated)

```python
# Check the short path
graph = mcp__murena__build_call_graph(
    name_path="UserService/create",
    relative_path="src/services.py",
    direction="outgoing",
    max_depth=2
)
```

**Result:** Direct call to `Database/insert` without validation! ⚠️

**Action:** Consider adding validation to `UserService/create` too.

---

## Tutorial 3: Finding Code Hotspots

**Scenario:** System is slow, need to find performance bottlenecks.

**Question:** What are the most-called functions?

### Step 1: Analyze Database Query Function

```python
# Find who calls the database query function
hotspots = mcp__murena__analyze_call_dependencies(
    name_path="Database/query",
    relative_path="src/db.py",
    analysis_type="hotspots",
    max_depth=2
)
```

**Result:**
```json
{
  "type": "hotspots",
  "hotspots": [
    {
      "np": "Database/query",
      "fp": "db.py",
      "calls_in": 42,
      "calls_out": 3,
      "importance": "critical"
    }
  ],
  "tot": 1,
  "msg": "42 callers found. Critical hotspot."
}
```

**Analysis:**
- 🔴 **42 callers** → Very high usage
- 🔴 **Importance: Critical** → Bottleneck!
- ✅ **Action:** Optimize `Database/query` (add caching, connection pooling)

### Step 2: Find Top Callers

```python
# Who calls it the most?
callers = mcp__murena__get_incoming_calls(
    name_path="Database/query",
    relative_path="src/db.py",
    max_depth=1,
    include_call_sites=True,
    compact_format=False  # Verbose for analysis
)
```

**Result:**
```json
{
  "incoming_calls": [
    {
      "name": "UserService/authenticate",
      "file": "services.py",
      "call_sites": [
        {"line": 18}, {"line": 22}, {"line": 28}, {"line": 32}, {"line": 40}
      ]
    },
    {
      "name": "ProductService/search",
      "file": "products.py",
      "call_sites": [
        {"line": 15}, {"line": 20}, {"line": 25}, {"line": 30}
      ]
    }
  ],
  "total_callers": 8
}
```

**Analysis:**
- 🔴 `UserService/authenticate` calls 5 times (hot loop!)
- 🔴 `ProductService/search` calls 4 times
- ✅ **Action:** Add caching to these services first

### Step 3: Optimization Impact

After adding cache to `UserService/authenticate`:
```python
# Re-check hotspots
hotspots_after = mcp__murena__analyze_call_dependencies(
    name_path="Database/query",
    relative_path="src/db.py",
    analysis_type="hotspots"
)
```

**Result:** `calls_in: 37` (down from 42) → 12% reduction! ✅

---

## Tutorial 4: Natural Language Queries

### Example 1: "Who calls this function?"

```python
# Natural language
results = mcp__murena__intelligent_search(
    query="who calls the authenticate function?",
    max_results=10
)
```

**What happens:**
1. QueryRouter detects "who calls" → Routes to CALL_GRAPH mode
2. Extracts symbol name: "authenticate"
3. Calls `get_incoming_calls()` automatically
4. Returns results with LTR ranking

**Benefits:**
- ✅ No need to know exact name_path format
- ✅ Fuzzy matching finds `authenticate` in multiple files
- ✅ LTR ranking prioritizes important callers

### Example 2: "Find authentication validators"

```python
results = mcp__murena__intelligent_search(
    query="find authentication validators",
    max_results=15
)
```

**What happens:**
1. Semantic search finds validator functions
2. Returns results ranked by relevance
3. Includes call graph features in ranking

**Benefits:**
- ✅ Finds related functions even if name doesn't match exactly
- ✅ Understands "authentication" → "auth", "user", "login"

### Example 3: "What depends on the login function?"

```python
results = mcp__murena__intelligent_search(
    query="what depends on the login function?",
    max_results=20
)
```

**What happens:**
1. Detects "depends on" → Call graph query
2. Finds incoming calls to `login` functions
3. Ranks by dependency importance

### When to Use Natural Language

✅ **Good for:**
- Exploration (don't know exact symbol names)
- Broad questions ("find all validators")
- Quick checks

❌ **Better to use direct tools:**
- Known symbol name/path
- Need specific depth control
- Performance-critical operations

---

## Tutorial 5: Multi-Language Support

### Supported Languages

**FULL support (11 languages):**
- Python, Go, TypeScript/JavaScript, Java, Rust
- C#, Kotlin, C/C++, Swift, Vue, Scala

**PARTIAL support (4 languages):**
- PHP, Ruby, Elixir, Dart

**FALLBACK (27 languages):**
- Uses `find_referencing_symbols` instead

### Example: Python Project

```python
# Python (FULL support)
callers = mcp__murena__get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="src/services.py",
    max_depth=2
)
# → Uses LSP call hierarchy (95-100% precision)
```

### Example: Go Project

```python
# Go (FULL support)
callers = mcp__murena__get_incoming_calls(
    name_path="UserService.Authenticate",  # Note: Go uses dot notation
    relative_path="services.go",
    max_depth=2
)
# → Uses gopls call hierarchy (excellent cross-package support)
```

### Example: PHP Project

```python
# PHP (PARTIAL support)
callers = mcp__murena__get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="src/UserService.php",
    max_depth=1  # Keep depth low
)
# → Uses intelephense (may miss dynamic calls)
```

### Example: Perl Project (Fallback)

```python
# Perl (FALLBACK - no call hierarchy)
callers = mcp__murena__get_incoming_calls(
    name_path="authenticate",
    relative_path="lib/UserService.pm",
    max_depth=1
)
# → Automatically falls back to find_referencing_symbols
# → Result includes "fallback": true flag
# → Precision: 70-85% (includes non-call references)
```

### Language-Specific Tips

**Python:**
- ✅ Full support for classes, methods, functions
- ✅ Excellent cross-file support
- ✅ Use `ClassName/method_name` format

**Go:**
- ✅ Use dot notation: `PackageName.FunctionName`
- ✅ Cross-package calls work perfectly
- ✅ High precision

**TypeScript/JavaScript:**
- ✅ Supports both TS and JS
- ✅ Vue `<script>` sections included
- ✅ Use `ClassName/methodName` or `functionName`

**Java:**
- ✅ Full support across packages
- ✅ Use `ClassName/methodName` format
- ⚠️ May need workspace build first

**PHP:**
- ⚠️ PARTIAL support - basic call hierarchy
- ⚠️ May miss dynamic method calls
- ✅ Static calls work well

---

## Common Patterns

### Pattern 1: Pre-Refactoring Checklist

```python
# Step 1: Find all callers
callers = get_incoming_calls(name_path=..., max_depth=2)

# Step 2: Analyze impact
impact = analyze_call_dependencies(name_path=..., analysis_type="impact")

# Step 3: Check test coverage
if impact["test_callers"] == 0:
    print("⚠️ No test coverage! Add tests first.")

# Step 4: Proceed with refactoring
```

### Pattern 2: Architecture Documentation

```python
# Build complete module call graph
graph = build_call_graph(
    name_path="ModuleEntryPoint",
    relative_path="src/module.py",
    direction="both",
    max_depth=3,
    max_nodes=100
)

# Export to visualization tool
# (nodes + edges can be rendered in graphviz, mermaid, etc.)
```

### Pattern 3: Dead Code Detection

```python
# Find functions with no callers
def find_dead_code(file_path):
    symbols = get_symbols_overview(relative_path=file_path, depth=1)

    for symbol in symbols["functions"]:
        callers = get_incoming_calls(
            name_path=symbol["name_path"],
            relative_path=file_path,
            max_depth=1
        )

        if callers["tot"] == 0:
            print(f"⚠️ Potentially dead: {symbol['name_path']}")
```

### Pattern 4: Cyclic Dependency Detection

```python
# Check if A calls B and B calls A
path_a_to_b = find_call_path(
    from_name_path="ServiceA/method",
    from_file="service_a.py",
    to_name_path="ServiceB/method",
    to_file="service_b.py"
)

path_b_to_a = find_call_path(
    from_name_path="ServiceB/method",
    from_file="service_b.py",
    to_name_path="ServiceA/method",
    to_file="service_a.py"
)

if path_a_to_b["tot"] > 0 and path_b_to_a["tot"] > 0:
    print("⚠️ Cyclic dependency detected!")
```

---

## Troubleshooting

### Issue 1: "Symbol not found"

**Error:**
```json
{"error": "Symbol not found: UserService/authenticate"}
```

**Solutions:**
1. Check name_path format: `ClassName/method_name`
2. Verify file path is relative to project root
3. Use `find_symbol()` first to locate symbol:
   ```python
   symbol = find_symbol(
       name_path_pattern="authenticate",
       relative_path="src/services.py",
       substring_matching=True
   )
   ```

### Issue 2: Empty Results

**Result:**
```json
{"callers": [], "tot": 0}
```

**Possible causes:**
1. Function truly has no callers (dead code?)
2. Language has FALLBACK support (check support level)
3. Cross-file calls not indexed yet (restart language server)

**Solutions:**
1. Use `find_referencing_symbols()` as fallback
2. Check language support matrix
3. Restart MCP server: `uv run murena-mcp-server --project .`

### Issue 3: Slow Performance

**Symptom:** Queries taking >5 seconds

**Solutions:**
1. Reduce `max_depth` (start with 1, increase gradually)
2. Set `max_nodes` limit for graphs:
   ```python
   graph = build_call_graph(..., max_nodes=30)
   ```
3. Use `compact_format=True` (70% faster parsing)
4. Cache results in conversation (don't re-query same symbol)

### Issue 4: Token Budget Exceeded

**Symptom:** "Output truncated" message

**Solutions:**
1. Use `compact_format=True` (70% savings)
2. Reduce `max_depth` or `max_nodes`
3. Use `max_answer_chars` to limit output:
   ```python
   callers = get_incoming_calls(..., max_answer_chars=5000)
   ```

---

## Best Practices

### 1. Progressive Disclosure

✅ **Start shallow, go deep as needed:**
```python
# Step 1: Quick overview (depth=1)
callers = get_incoming_calls(..., max_depth=1)

# Step 2: If interesting, go deeper (depth=2)
if callers["tot"] > 5:
    deep_callers = get_incoming_calls(..., max_depth=2)
```

### 2. Use Compact Format for Exploration

✅ **Compact for initial exploration:**
```python
overview = get_incoming_calls(..., compact_format=True)  # 400 tokens
```

❌ **Don't use verbose for large results:**
```python
overview = get_incoming_calls(..., compact_format=False)  # 1,400 tokens!
```

### 3. Cache in Conversation

✅ **Reuse results in conversation:**
```python
# First query
callers = get_incoming_calls(...)

# Later: Reference the cached result
"Based on the 8 callers we found earlier..."
```

❌ **Don't re-query unnecessarily:**
```python
# Bad: Queries same thing twice
callers1 = get_incoming_calls(...)
callers2 = get_incoming_calls(...)  # Waste of tokens!
```

### 4. Set Limits on Large Graphs

✅ **Always set max_nodes for graphs:**
```python
graph = build_call_graph(..., max_nodes=50, max_depth=2)
```

❌ **Don't build unlimited graphs:**
```python
graph = build_call_graph(..., max_depth=5)  # Could return 1000s of nodes!
```

### 5. Check Language Support First

✅ **Verify support level for critical operations:**
```python
# Check language_support_matrix.md first
# Python → FULL support ✅
# Perl → FALLBACK ⚠️
```

### 6. Use Natural Language for Exploration

✅ **Natural language for broad questions:**
```python
results = intelligent_search(query="find authentication logic")
```

✅ **Direct tools for specific analysis:**
```python
callers = get_incoming_calls(name_path="exact/path", ...)
```

### 7. Include Tests in Impact Analysis

✅ **Always check test coverage:**
```python
impact = analyze_call_dependencies(
    ...,
    include_tests=True  # Don't skip tests!
)

if impact["test_callers"] == 0:
    print("⚠️ Add tests before refactoring!")
```

---

## Next Steps

1. **Try it yourself:** Pick a function in your codebase and explore its call graph
2. **Read API reference:** [call_graph_tools.md](../api/call_graph_tools.md) for detailed parameter docs
3. **Check language support:** [language_support_matrix.md](../api/language_support_matrix.md) for your language
4. **Integrate with semantic search:** Natural language queries automatically use call graph

---

## Migration from find_referencing_symbols

If you've been using `find_referencing_symbols`, here's how to migrate:

**Old approach:**
```python
# find_referencing_symbols returns ALL references
refs = find_referencing_symbols(
    name_path="authenticate",
    relative_path="services.py"
)
# → Includes: actual calls, imports, type hints, documentation, etc.
# → Precision: 70-85%
```

**New approach:**
```python
# get_incoming_calls returns ONLY actual calls
callers = get_incoming_calls(
    name_path="UserService/authenticate",
    relative_path="services.py",
    max_depth=1
)
# → Only actual function calls
# → Precision: 95-100%
# → Includes call sites (line numbers)
```

**When to still use find_referencing_symbols:**
- Need ALL references (not just calls)
- Language has FALLBACK support only
- Finding usages for refactoring variable names

---

## Feedback

Found a bug or have a suggestion? Please report issues at:
https://github.com/murena-intelligence/murena/issues

Happy call graph exploring! 🚀
