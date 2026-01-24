# Claude Code Integration for Murena

This guide explains how to integrate Murena with Claude Code as an MCP server.

## Prerequisites

- Claude Code CLI installed (`claude`)
- Murena installed in development mode from this repository
- Python 3.11+ with `uv` package manager

## Installation Steps

### 1. Remove Old Serena Plugin (if exists)

If you previously had Serena installed as an MCP plugin:

```bash
# Remove old plugin directory
rm -rf ~/.claude/plugins/cache/claude-plugins-official/serena
```

### 2. Add Murena as Global MCP Server

From your Murena repository directory:

```bash
claude mcp add murena -- uvx --from $(pwd) murena-mcp-server --context claude-code --project-from-cwd
```

**Command breakdown:**
- `murena` - MCP server name in Claude Code
- `uvx` - Use uvx to run from local directory
- `--from $(pwd)` - Path to this Murena repository
- `murena-mcp-server` - Entry point command
- `--context claude-code` - Use claude-code context (excludes file tools already in Claude Code)
- `--project-from-cwd` - Auto-detect project from current working directory

### 3. Verify Installation

The MCP config should be created at:
```
~/.claude/plugins/cache/claude-plugins-official/murena.json
```

Expected content:
```json
{
  "command": "uvx",
  "args": [
    "--from",
    "/path/to/murena",
    "murena-mcp-server",
    "--context",
    "claude-code",
    "--project-from-cwd"
  ]
}
```

### 4. Test in Claude Code

Start Claude Code in any project directory:

```bash
cd /path/to/your/project
claude
```

In the Claude Code session, verify Murena tools are available:

```
User: "What Murena tools are available?"
```

Expected tools (with claude-code context):
- `find_symbol` - Find code symbols by name
- `get_symbols_overview` - Get file structure overview
- `find_referencing_symbols` - Find symbol references
- `search_for_pattern` - Search code patterns
- `replace_symbol_body` - Edit symbol definitions
- `insert_after_symbol` / `insert_before_symbol` - Add code around symbols
- `rename_symbol` - Rename symbols across codebase
- Memory tools (read/write/list/delete)
- Configuration tools (activate_project, switch_modes, etc.)

**Note:** File tools like `read_file`, `create_text_file` are excluded in claude-code context since Claude Code provides them natively.

### 5. Test a Tool

```
User: "Use Murena to find all classes in the current project"
```

Murena should execute `find_symbol` or `get_symbols_overview` to show class definitions.

## Alternative: Project-Specific Configuration

For project-specific MCP configuration (instead of global):

```bash
cd /path/to/your/project

# Create .claude directory
mkdir -p .claude

# Add MCP config
cat > .claude/mcp.json <<EOF
{
  "murena": {
    "command": "uvx",
    "args": [
      "--from",
      "/path/to/murena/repo",
      "murena-mcp-server",
      "--context",
      "claude-code",
      "--project",
      "$(pwd)"
    ]
  }
}
EOF
```

## Troubleshooting

### MCP Server Not Loading

Check logs:
```bash
tail -f ~/.murena/logs/*/mcp_*.txt
```

Common issues:
- **Import errors:** Run `uv pip install -e .` in Murena repo
- **Tool not found:** Verify `murena-mcp-server` is in `.venv/bin/`
- **Permission errors:** Check file permissions on Murena repo

### Tools Not Appearing

1. Verify MCP config exists:
   ```bash
   cat ~/.claude/plugins/cache/claude-plugins-official/murena.json
   ```

2. Check Claude Code loaded the plugin:
   ```
   User: "List all available MCP servers"
   ```

3. Restart Claude Code session

### Wrong Context

If you see duplicate tools (e.g., both Claude's `read_file` and Murena's), you may be using the wrong context. Ensure `--context claude-code` is in the MCP config.

## Migration from Serena

If you were using Serena before:

1. **Config migration:** Murena automatically migrates `~/.serena/` to `~/.murena/`
2. **Project directories:** Existing `.serena/` folders work but new ones use `.murena/`
3. **Commands:** Replace `serena` with `murena`, `serena-mcp-server` with `murena-mcp-server`
4. **MCP plugin:** Remove old Serena plugin and add Murena (see steps above)

## Advanced Configuration

### Custom Contexts

Create custom tool sets by defining contexts in:
```
~/.murena/contexts/my-context.yml
```

Then use:
```bash
claude mcp add murena -- uvx --from $(pwd) murena-mcp-server --context my-context --project-from-cwd
```

### Multiple Projects

Register multiple projects for fast switching:

```bash
# From Murena CLI
murena project create --path /path/to/project1 --language python
murena project create --path /path/to/project2 --language typescript
```

Then in Claude Code:
```
User: "Activate project project1"
```

## Resources

- **Murena Documentation:** See `docs/` directory
- **MCP Protocol:** https://modelcontextprotocol.io
- **Claude Code Guide:** https://docs.anthropic.com/claude-code
- **Issue Tracker:** https://github.com/oraios/murena/issues
