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

## 📝 Markdown Documentation Optimization

Murena MCP provides 70-90% token savings when working with documentation files through Marksman LSP integration.

### Pattern: Two-Phase Documentation Reading

**Problem:** Reading large documentation files (500+ lines) wastes 20,000+ tokens per file.

**Solution:** Use symbolic operations to navigate documentation like code.

```python
# Phase 1: Get document structure (metadata only) - ~1,000 tokens
overview = get_symbols_overview(relative_path="docs/API.md", depth=2)
# Returns: Hierarchical list of headings

# Phase 2: Load specific section - ~500-1,500 tokens
section = find_symbol(
    name_path_pattern="Authentication",
    relative_path="docs/API.md",
    include_body=True
)
# Returns: Only the Authentication section content

# Total: ~1,500-2,500 tokens instead of 20,000+ for full file
# Savings: 87.5-92.5%
```

### Common Use Cases

**1. Find relevant documentation:**
```python
# Search across all markdown files
search_for_pattern(
    substring_pattern="authentication",
    paths_include_glob="**/*.md",
    context_lines_after=2
)
```

**2. Navigate document structure:**
```python
# See the outline without reading content
get_symbols_overview(relative_path="docs/user-guide.md", depth=2)
# Returns all headings in hierarchical format
```

**3. Extract specific sections:**
```python
# Read only what you need
find_symbol(
    name_path_pattern="Installation Guide",
    relative_path="README.md",
    include_body=True
)
```

### Supported Features

- **Heading hierarchy** - All heading levels (# through ######) become navigable symbols
- **Cross-file links** - Marksman tracks relationships between documents
- **Section extraction** - Read individual sections without loading full files
- **Auto-detection** - All .md files automatically use symbolic tools (no configuration needed)
- **Caching** - Structure cached for fast repeated access

### Token Savings Examples

| Operation | Traditional Approach | Symbolic Approach | Savings |
|-----------|---------------------|-------------------|---------|
| Get document structure | Read (20,000 tokens) | get_symbols_overview (1,000) | 95% |
| Find specific section | Read + grep (20,000) | find_symbol (500) | 97.5% |
| Read one section | Read full file (20,000) | get_symbol_body (1,500) | 92.5% |
| Repeated access | Read again (20,000) | Use cache (100) | 99.5% |

**Real-world example:** For a 650-line README:
- Traditional read: ~25,000 tokens
- Symbolic navigation: ~2,500 tokens
- **Savings: 90%**

### Best Practices

1. **Always check file size first** - Use symbolic tools for files >100 lines
2. **Get overview before reading** - Understand structure before loading content
3. **Use caching** - Enable session cache for repeated access to same files
4. **Restrict search scope** - Use `relative_path` parameter to narrow searches
5. **Progressive disclosure** - Load only the sections you need, when you need them

## 🚀 Token Optimization: Using Murena MCP Tools

**CRITICAL: This project has Murena MCP server running.**

### Quick Rules

1. **ALWAYS use Murena MCP symbolic tools** (`mcp__murena-serena__*` namespace) for code files
2. **NEVER use Read() for Python files in `src/`** - use `get_symbols_overview()` first
3. **Emergency override:** Only use Read() if file < 100 lines or Murena MCP unavailable

### File Size Decision Rules

| File Size | Action |
|-----------|--------|
| **< 100 lines** | Prefer symbolic, Read() acceptable |
| **100-200 lines** | MUST use `get_symbols_overview()` first |
| **> 200 lines** | FORBIDDEN to use Read(), use symbolic tools ONLY |

### Tool Categories (What to Use)

**Use These - Massive Token Savings (70-95%):**
- `mcp__murena-serena__get_symbols_overview()` - File structure
- `mcp__murena-serena__find_symbol()` - Find specific function/class
- `mcp__murena-serena__find_referencing_symbols()` - Find usage
- `mcp__murena-serena__replace_symbol_body()` - Edit code safely
- `mcp__murena-serena__insert_after_symbol()` - Add code after symbol

**Don't Use (Claude has built-in equivalents):**
- `mcp__murena-serena__read_file` → Use Claude's Read() tool instead
- `mcp__murena-serena__create_text_file` → Use Claude's Write() tool instead
- `mcp__murena-serena__execute_shell_command` → Use Claude's Bash() tool instead

### Cache-First Pattern (99% Savings on Repeated Access)

```python
# First access to file
overview = mcp__murena-serena__get_symbols_overview(relative_path="src/murena/agent.py", depth=2)
# → ~1,000 tokens

# Later in conversation: same file
# ❌ DON'T: Re-fetch from disk
overview2 = mcp__murena-serena__get_symbols_overview(relative_path="src/murena/agent.py")
# → 1,000 tokens (wasted, already loaded)

# ✅ DO: Use cache
get_cached_symbols("src/murena/agent.py")
# → ~100 tokens (99% savings!)
```

**Real-world savings in 5-turn conversation about same file:**
- Without cache: 1,000 + 1,000 + 1,000 + 1,000 + 500 = 4,500 tokens
- With cache: 1,000 + 100 + 100 + 100 + 500 = 1,800 tokens
- **Savings: 60%**

### Real-World Example

**Task:** Read function "start_mcp_server" and make an edit

```python
# ✅ OPTIMAL (92.5% savings)

# Step 1: Get file structure
mcp__murena-serena__get_symbols_overview(relative_path="src/murena/cli.py", depth=1)
# → 800 tokens (not 25,000 for full file read)

# Step 2: Find the function
mcp__murena-serena__find_symbol(
    name_path_pattern="start_mcp_server",
    relative_path="src/murena/cli.py",
    include_body=True
)
# → 500 tokens (specific function, not full file)

# Step 3: Edit the function
mcp__murena-serena__replace_symbol_body(
    name_path="start_mcp_server",
    body="...new implementation..."
)
# → 300 tokens (symbolic editing, precise)

# Total: 1,600 tokens vs 25,000+ for Read() approach
# Savings: 93.6%
```

**Quick reference:** Full token optimization rules in [Global CLAUDE.md § TOKEN OPTIMIZATION RULES](/Users/dmitry.lazarenko/.claude/CLAUDE.md)

## 🔄 Alternative Workflows for Phase 5 Token Optimization

**Context:** Phase 5 of the token optimization removed 7 low-risk tools to save ~420 tokens (17% additional reduction). Below are the alternatives to use.

### Removed Tools & Alternatives

| Removed Tool | Alternative Workflow | Example |
|--------------|---------------------|---------|
| **`list_dir`** | Use `Bash("ls -la <dir>")` | `Bash("ls -la src/murena/tools/")` |
| **`delete_lines`** | Use Claude's `Edit()` tool | `Edit(file_path="...", old_string="lines to delete", new_string="")` |
| **`replace_lines`** | Use Claude's `Edit()` tool | `Edit(file_path="...", old_string="old lines", new_string="new lines")` |
| **`insert_at_line`** | Use `Edit()` or symbolic tools | `insert_after_symbol()` for code, `Edit()` for other cases |
| **`update_changelog`** | Use `Edit()`/`Write()` directly | `Edit("CHANGELOG.md", old_string="## Unreleased", new_string="## Unreleased\n- New change")` |
| **`edit_memory`** | Use `delete_memory()` + `write_memory()` | Two-step: delete old, write new |
| **`summarize_changes`** | Use git commands | `Bash("git diff --stat")` or `Bash("git log --oneline -5")` |

### Best Practices

1. **Directory Listing:** `Bash("ls -la")` is Claude's native feature and works identically to `list_dir`
2. **Line Editing:** `Edit()` is more flexible than line-specific tools and works with exact string matching
3. **Symbolic Editing:** For code changes, prefer symbolic tools (`replace_symbol_body()`, `insert_after_symbol()`) over line-based editing
4. **Memory Operations:** Two-step workflow (delete + write) is acceptable for infrequent memory edits
5. **Git Operations:** Native git commands provide richer output than `summarize_changes`

**Impact:** Zero quality loss - all alternatives are equivalent or superior to removed tools.

## 🔀 Multi-Project Support

Murena MCP supports running multiple independent instances for working with multiple projects simultaneously.

### CLI Commands

**Setup and discovery:**
```bash
# Auto-discover and configure all projects
murena multi-project setup-claude-code

# Discover projects without configuring
murena multi-project discover-projects

# Generate MCP configurations
murena multi-project generate-mcp-configs

# Automatic discovery with MCP registration (NEW)
murena multi-project auto-discover
murena multi-project auto-discover --workspace-root /path/to/workspace
murena multi-project auto-discover --max-depth 2 --auto-register
murena multi-project auto-discover --no-auto-register  # Discover only
```

**Project management:**
```bash
# Add a specific project
murena multi-project add-project /path/to/project

# Remove a project
murena multi-project remove-project project-name

# List configured projects
murena multi-project list-projects
murena multi-project list-projects --verbose
```

### Tool Usage

When multiple projects are configured, tools are namespaced by project:

```python
# serena project tools
mcp__murena-serena__get_symbols_overview(relative_path="src/murena/agent.py")
mcp__murena-serena__find_symbol(name_path_pattern="MurenaAgent")

# spec-kit project tools
mcp__murena-spec-kit__get_symbols_overview(relative_path="templates/commands/specify.md")
mcp__murena-spec-kit__find_symbol(name_path_pattern="SpecKitManager")
```

### Server Naming

- **Auto-naming:** Server names follow the pattern `murena-{project-directory-name}`
- **Example:** `/Users/you/projects/serena` → `murena-serena`
- **Backward compatible:** Old `murena` server continues to work

### Architecture

Each MCP server instance maintains:
- **Isolated language servers** - No cross-project interference
- **Independent memory** - Project-specific `.murena/memories/`
- **Separate caches** - Symbol caches per project
- **Memory usage:** ~150-200MB per active project

### Configuration File

MCP configurations are stored in `~/.claude/mcp_servers_murena.json`:

```json
{
  "murena-serena": {
    "command": "uvx",
    "args": ["murena", "start-mcp-server", "--project", "/path/to/serena", "--auto-name"],
    "env": {}
  },
  "murena-spec-kit": {
    "command": "uvx",
    "args": ["murena", "start-mcp-server", "--project", "/path/to/spec-kit", "--auto-name"],
    "env": {}
  }
}
```

### Automatic Project Discovery

Murena can automatically discover and register Murena projects in a workspace directory.

**Features:**
- Recursive project discovery up to specified depth (default: 3 levels)
- Excludes common non-project directories (node_modules, venv, .git, etc.)
- Automatic MCP server registration in Claude Code
- Batch operations for efficient setup

**Auto-Discovery Workflow:**

```bash
# Quick auto-discovery with automatic registration
murena multi-project auto-discover

# Control discovery scope
murena multi-project auto-discover --workspace-root ~/projects --max-depth 2

# Discover without registering (manual review first)
murena multi-project auto-discover --no-auto-register

# View results before committing to registration
murena multi-project auto-discover --no-auto-register --workspace-root /path/to/workspace
# Then review output and run:
murena multi-project auto-discover --workspace-root /path/to/workspace
```

**What Auto-Discovery Does:**
1. Scans workspace for `.murena/project.yml` marker files
2. Identifies valid Murena projects by directory structure
3. Generates MCP server configurations automatically
4. Registers projects in `~/.claude/mcp_servers_murena.json`
5. Provides detailed status report with success/failure counts

**Output Example:**
```
🔍 Auto-discovering Murena projects in: /Users/you/projects

✓ Found 5 project(s):

  • serena
    Path: /Users/you/projects/serena
    Marker: /Users/you/projects/serena/.murena/project.yml

  • spec-kit
    Path: /Users/you/projects/spec-kit
    Marker: /Users/you/projects/spec-kit/.murena/project.yml

📝 Registering projects in MCP...

Registration Results:
  Total: 5
  Registered: 5
  Failed: 0

✅ All projects registered successfully!

📋 Next steps:
  1. Restart Claude Code to load the new MCP servers
  2. Verify servers are running in Claude Code
  3. Start using multi-project tools!
```

**📖 Full documentation:** See [docs/multi_project_setup.md](docs/multi_project_setup.md)