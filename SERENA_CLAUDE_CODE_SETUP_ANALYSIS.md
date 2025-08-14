# Serena Setup Analysis for Claude Code Integration

## Executive Summary

This document provides a comprehensive analysis of Serena's setup procedure when used as a local installation dedicated exclusively to Claude Code. The analysis covers installation requirements, configuration specifics, MCP server integration details, and optimal setup recommendations.

## Core Architecture Overview

Serena operates as a Model Context Protocol (MCP) server that provides semantic code analysis and editing capabilities through Language Server Protocol (LSP) integration. When used with Claude Code, it functions as a subprocess managed by the Claude Code client, communicating via stdio or SSE transport protocols.

### Key Components

1. **SerenaAgent** (`src/serena/agent.py`): Central orchestrator managing projects, tools, and user interactions
2. **SolidLanguageServer** (`src/solidlsp/ls.py`): Unified wrapper around LSP implementations
3. **MCP Server** (`src/serena/mcp.py`): FastMCP-based server implementation
4. **Tool System** (`src/serena/tools/`): Comprehensive toolset for code analysis and manipulation

## Installation Requirements

### System Prerequisites

1. **Python Version**: 3.11 (strictly required, as specified in `pyproject.toml`)
   ```
   requires-python = ">=3.11, <3.12"
   ```

2. **Package Manager**: UV (required for dependency management)
   - Installation: `curl -LsSf https://astral.sh/uv/install.sh | sh`

3. **Dependencies** (automatically managed by UV):
   - mcp==1.12.3 (Model Context Protocol)
   - pyright, overrides, python-dotenv
   - flask (for web dashboard)
   - pydantic, pyyaml, jinja2
   - Language-specific servers (downloaded on demand)

### Language Server Requirements

Serena supports 13+ programming languages with varying installation requirements:

**Out-of-the-box support** (no additional installation):
- Python (via Pyright)
- TypeScript/JavaScript
- PHP
- Rust
- C#
- Java
- Elixir (requires Elixir/NextLS separately)
- Clojure
- C/C++
- Lean 4 (requires separate Lean installation)

**Requires manual installation**:
- Go (requires `go` and `gopls`)
- Ruby, Kotlin, Dart (untested)

## Claude Code Integration Specifics

### 1. MCP Server Configuration

Claude Code requires specific configuration in its MCP settings:

```bash
claude mcp add serena -- <serena-mcp-server-command> --context ide-assistant --project $(pwd)
```

### 2. Context Selection: `ide-assistant`

The `ide-assistant` context is specifically designed for Claude Code integration:

```yaml
# src/serena/resources/config/contexts/ide-assistant.yml
description: Non-symbolic editing tools and general shell tool are excluded
excluded_tools:
  - create_text_file
  - read_file
  - delete_lines
  - replace_lines
  - insert_at_line
  - execute_shell_command
  - prepare_for_new_conversation
  - summarize_changes
  - get_current_config
```

**Rationale**: Claude Code has its own file I/O and shell execution capabilities, so Serena focuses exclusively on semantic/symbolic operations to avoid tool conflicts.

### 3. Transport Protocol

- **Default**: stdio (standard input/output communication)
- **Alternative**: SSE (Server-Sent Events) for HTTP-based communication

For Claude Code, stdio is recommended as it's the native transport mechanism.

### 4. Startup Command Structure

The complete startup command for local installation:

```bash
# Using local installation
claude mcp add serena -- uv run --directory /path/to/serena serena start-mcp-server --context ide-assistant --project $(pwd)

# Using uvx (remote installation)
claude mcp add serena -- uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project $(pwd)
```

## Configuration Hierarchy

1. **Command-line arguments** (highest precedence)
2. **Project settings** (`.serena/project.yml`)
3. **User settings** (`~/.serena/serena_config.yml`)
4. **Default settings**

### Essential Configuration Options

```yaml
# ~/.serena/serena_config.yml
gui_log_window: False  # Not recommended for Claude Code
web_dashboard: True    # Recommended for monitoring
web_dashboard_open_on_launch: True
log_level: 20  # INFO level
trace_lsp_communication: False  # Enable for debugging
tool_timeout: 240  # 4 minutes default
record_tool_usage_stats: True  # For dashboard analytics
```

## MCP Server Implementation Details

### 1. Tool Registration

Serena dynamically converts its tools to MCP-compatible format:

```python
# src/serena/mcp.py:60-100
@staticmethod
def make_mcp_tool(tool: Tool) -> MCPTool:
    # Extracts function metadata
    # Parses docstrings for descriptions
    # Creates parameter schemas
    # Wraps execution with error handling
```

### 2. Logging Configuration

- **Never uses stdout** (reserved for MCP communication)
- Logs to stderr, memory buffer, and file
- Web dashboard accessible at `http://localhost:24282/dashboard/`

### 3. Process Lifecycle

- Started by Claude Code as subprocess
- Maintains persistent state across tool calls
- Automatic language server management
- Graceful shutdown via dashboard or client termination

## Optimization for Claude Code

### 1. Memory Management

- Persistent project knowledge in `.serena/memories/`
- Automatic onboarding process for new projects
- Context-aware memory retrieval

### 2. Token Efficiency

- Symbolic operations minimize token usage
- Targeted code reading vs. full file access
- Intelligent caching of language server results

### 3. Tool Selection

With `ide-assistant` context, Serena provides:
- **Symbolic navigation**: `find_symbol`, `find_referencing_symbols`
- **Code overview**: `get_symbols_overview`
- **Semantic editing**: `replace_symbol_body`, `insert_before_symbol`
- **Pattern search**: `search_for_pattern`
- **Memory operations**: Read/write project knowledge

### 4. Project Activation

Two methods:
1. **Startup parameter**: `--project /path/to/project`
2. **Runtime activation**: Via `activate_project` tool

## Best Practices for Claude Code Integration

### 1. Initial Setup

1. Install UV package manager
2. Clone Serena repository locally
3. Configure Claude Code with appropriate command
4. Enable web dashboard for monitoring
5. Set `--context ide-assistant` always

### 2. Project Workflow

1. Start with clean git state
2. Index large projects: `uv run serena project index`
3. Allow onboarding process to complete
4. Use memories for persistent knowledge
5. Monitor tool usage via dashboard

### 3. Performance Optimization

- Disable GUI log window (use web dashboard)
- Set appropriate tool timeout
- Enable tool usage statistics
- Use project-specific configurations

### 4. Troubleshooting

- Check dashboard at `http://localhost:24282/dashboard/`
- Enable `trace_lsp_communication` for LSP issues
- Verify language server installations
- Monitor memory usage in dashboard

## Security Considerations

1. **Tool Execution**: All tools require explicit permission in Claude Code
2. **File Access**: Limited to project directory and configured paths
3. **Shell Commands**: Disabled in `ide-assistant` context
4. **Network Access**: Only for language server downloads

## Unique Advantages for Claude Code

1. **Free Tier Compatibility**: Works with Claude's free tier
2. **Semantic Understanding**: LSP-based operations vs. text-based
3. **Token Efficiency**: Minimal context usage through symbolic operations
4. **Persistent Knowledge**: Project-specific memory system
5. **Multi-Language Support**: 13+ languages out-of-the-box

## Conclusion

Serena's integration with Claude Code represents a powerful combination of semantic code understanding and AI assistance. The local installation approach, combined with the `ide-assistant` context, provides optimal performance while avoiding tool conflicts. The MCP server architecture ensures reliable communication, while the LSP integration enables precise, context-aware code operations that significantly enhance Claude Code's capabilities without additional API costs.