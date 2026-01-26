# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Essential Commands (use these exact commands):**
- `uv run poe format` - Format code (BLACK + RUFF) - ONLY allowed formatting command
- `uv run poe type-check` - Run mypy type checking - ONLY allowed type checking command  
- `uv run poe test` - Run tests with default markers (excludes java/rust by default)
- `uv run poe test -m "python or go"` - Run specific language tests
- `uv run poe test -m vue` - Run Vue tests
- `uv run poe lint` - Check code style without fixing

**Test Markers:**
Available pytest markers for selective testing:
- `python`, `go`, `java`, `rust`, `typescript`, `vue`, `php`, `perl`, `powershell`, `csharp`, `elixir`, `terraform`, `clojure`, `swift`, `bash`, `ruby`, `ruby_solargraph`
- `snapshot` - for symbolic editing operation tests

**Project Management:**
- `uv run murena-mcp-server` - Start MCP server from project root
- `uv run index-project` - Index project for faster tool performance

**Always run format, type-check, and test before completing any task.**

## Architecture Overview

Murena is a dual-layer coding agent toolkit:

### Core Components

**1. MurenaAgent (`src/murena/agent.py`)**
- Central orchestrator managing projects, tools, and user interactions
- Coordinates language servers, memory persistence, and MCP server interface
- Manages tool registry and context/mode configurations

**2. SolidLanguageServer (`src/solidlsp/ls.py`)**  
- Unified wrapper around Language Server Protocol (LSP) implementations
- Provides language-agnostic interface for symbol operations
- Handles caching, error recovery, and multiple language server lifecycle

**3. Tool System (`src/murena/tools/`)**
- **file_tools.py** - File system operations, search, regex replacements
- **symbol_tools.py** - Language-aware symbol finding, navigation, editing
- **memory_tools.py** - Project knowledge persistence and retrieval
- **config_tools.py** - Project activation, mode switching
- **workflow_tools.py** - Onboarding and meta-operations

**4. Configuration System (`src/murena/config/`)**
- **Contexts** - Define tool sets for different environments (desktop-app, agent, ide-assistant)
- **Modes** - Operational patterns (planning, editing, interactive, one-shot)
- **Projects** - Per-project settings and language server configs

### Language Support Architecture

Each supported language has:
1. **Language Server Implementation** in `src/solidlsp/language_servers/`
2. **Runtime Dependencies** - Automatic language server downloads when needed
3. **Test Repository** in `test/resources/repos/<language>/`
4. **Test Suite** in `test/solidlsp/<language>/`

### Memory & Knowledge System

- **Markdown-based storage** in `.murena/memories/` directories
- **Project-specific knowledge** persistence across sessions
- **Contextual retrieval** based on relevance
- **Onboarding support** for new projects

## Development Patterns

### Adding New Languages
1. Create language server class in `src/solidlsp/language_servers/`
2. Add to Language enum in `src/solidlsp/ls_config.py` 
3. Update factory method in `src/solidlsp/ls.py`
4. Create test repository in `test/resources/repos/<language>/`
5. Write test suite in `test/solidlsp/<language>/`
6. Add pytest marker to `pyproject.toml`

### Adding New Tools
1. Inherit from `Tool` base class in `src/murena/tools/tools_base.py`
2. Implement required methods and parameter validation
3. Register in appropriate tool registry
4. Add to context/mode configurations

### Testing Strategy
- Language-specific tests use pytest markers
- Symbolic editing operations have snapshot tests
- Integration tests in `test_murena_agent.py`
- Test repositories provide realistic symbol structures

## Configuration Hierarchy

Configuration is loaded from (in order of precedence):
1. Command-line arguments to `murena-mcp-server`
2. Project-specific `.murena/project.yml`
3. User config `~/.murena/murena_config.yml`
4. Active modes and contexts

## Key Implementation Notes

- **Symbol-based editing** - Uses LSP for precise code manipulation
- **Caching strategy** - Reduces language server overhead
- **Error recovery** - Automatic language server restart on crashes
- **Multi-language support** - 19 languages with LSP integration (including Vue)
- **MCP protocol** - Exposes tools to AI agents via Model Context Protocol
- **Async operation** - Non-blocking language server interactions

## Working with the Codebase

- Project uses Python 3.11 with `uv` for dependency management
- Strict typing with mypy, formatted with black + ruff
- Language servers run as separate processes with LSP communication
- Memory system enables persistent project knowledge
- Context/mode system allows workflow customization

## 🚀 Token Optimization: Using Murena MCP Tools

**CRITICAL: This project has Murena MCP server running. You MUST use symbolic tools instead of reading entire files.**

### Tool Selection Rules (MANDATORY)

**❌ NEVER do this:**
```
Read('src/murena/agent.py')  # 800 lines = 3200 tokens WASTED
```

**✅ ALWAYS do this instead:**
```
mcp__murena__get_symbols_overview(relative_path='src/murena/agent.py')  # 200 tokens
mcp__murena__find_symbol(name_path_pattern='MurenaAgent', relative_path='src/murena/agent.py', include_body=False)  # 150 tokens
```

### Decision Matrix (Use This Every Time)

| Your Goal | Built-in Tool ❌ | Murena MCP Tool ✅ | Token Savings |
|-----------|------------------|-------------------|---------------|
| "Understand file structure" | Read() | `get_symbols_overview()` | 80-90% |
| "Find a class/function" | Read() + search | `find_symbol()` | 70-85% |
| "See method implementation" | Read() | `find_symbol(include_body=True)` | 60-80% |
| "Find usage of X" | Grep() + Read() | `find_referencing_symbols()` | 70-85% |
| "Search for pattern" | Grep() + Read() | `search_for_pattern()` | 50-70% |
| "Edit a function" | Read() + Edit() | `replace_symbol_body()` | 70-80% |

### Workflow Examples

**Example 1: Understanding a new file**
```python
# ❌ BAD (3000 tokens):
Read('src/murena/ls_manager.py')

# ✅ GOOD (300 tokens):
mcp__murena__get_symbols_overview(
    relative_path='src/murena/ls_manager.py',
    depth=1  # Get classes and their methods
)
# Then read only specific symbols you need:
mcp__murena__find_symbol(
    name_path_pattern='LanguageServerManager/from_languages',
    relative_path='src/murena/ls_manager.py',
    include_body=True
)
```

**Example 2: Finding where something is used**
```python
# ❌ BAD (10000+ tokens):
Grep('ResourceMonitor', output_mode='content')
# Then Read() each file...

# ✅ GOOD (500 tokens):
mcp__murena__find_symbol(
    name_path_pattern='ResourceMonitor',
    relative_path='src/murena/util/resource_monitor.py'
)
mcp__murena__find_referencing_symbols(
    name_path='ResourceMonitor',
    relative_path='src/murena/util/resource_monitor.py',
    context_mode='line_only'  # Minimal context
)
```

**Example 3: Editing a method**
```python
# ❌ BAD (2000 tokens):
Read('src/murena/agent.py')  # Read whole file
Edit('src/murena/agent.py', old_string='...', new_string='...')

# ✅ GOOD (400 tokens):
mcp__murena__find_symbol(
    name_path_pattern='MurenaAgent/shutdown',
    relative_path='src/murena/agent.py',
    include_body=True  # Only this method
)
mcp__murena__replace_symbol_body(
    name_path='MurenaAgent/shutdown',
    relative_path='src/murena/agent.py',
    body='new implementation'
)
```

### Pre-Check Before ANY File Operation

**Before using Read(), Glob(), or Grep(), ask yourself:**

1. ☐ Can I use `get_symbols_overview()` instead? (usually YES)
2. ☐ Can I use `find_symbol()` to find specific code? (usually YES)
3. ☐ Can I use `search_for_pattern()` for text search? (usually YES)
4. ☐ Do I really need the ENTIRE file? (usually NO)

**If you answer YES to questions 1-3, you MUST use Murena MCP tools.**

### Common Patterns

**Pattern: "I need to understand what's in this file"**
```python
# Step 1: Get overview
mcp__murena__get_symbols_overview(relative_path='file.py', depth=1)
# Step 2: Read only interesting symbols
mcp__murena__find_symbol(name_path_pattern='InterestingClass', include_body=True)
```

**Pattern: "I need to find all files with X"**
```python
# Step 1: Find symbol
mcp__murena__find_symbol(name_path_pattern='X', substring_matching=True)
# Step 2: Find references
mcp__murena__find_referencing_symbols(name_path='X', relative_path='...', context_mode='line_only')
```

**Pattern: "I need to modify a function"**
```python
# Step 1: Find it
mcp__murena__find_symbol(name_path_pattern='function_name', include_body=True)
# Step 2: Replace it
mcp__murena__replace_symbol_body(name_path='Class/function_name', relative_path='...', body='...')
```

### Performance Impact

Using Murena MCP tools vs built-in tools:

| Operation | Built-in Tools | Murena MCP | Savings |
|-----------|----------------|------------|---------|
| Explore 1 file (500 lines) | 2000 tokens | 200 tokens | **90%** |
| Find 1 method | 2000 tokens | 300 tokens | **85%** |
| Edit 1 method | 2500 tokens | 400 tokens | **84%** |
| Find all usages | 8000 tokens | 600 tokens | **92%** |

**In a typical session with 20 file operations: 40,000 tokens → 5,000 tokens = 87.5% savings**

### Emergency Override

Only use built-in Read() if:
- File is < 100 lines
- File is not code (markdown, JSON, config)
- Murena MCP server is not running
- You've tried symbolic tools and they failed

**Otherwise, ALWAYS use Murena MCP symbolic tools first.**