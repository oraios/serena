# Multi-Project Support for Murena MCP

This guide explains how to configure and use Murena MCP with multiple projects simultaneously in Claude Code.

## Overview

Murena MCP supports running multiple independent instances, one for each project. This allows you to work seamlessly across multiple codebases (e.g., `serena`, `spec-kit`, `my-app`) without having to switch projects manually.

### Architecture

Each project gets its own MCP server instance:

```
Claude Code
  ├─ murena-serena      → /path/to/serena
  ├─ murena-spec-kit    → /path/to/spec-kit
  └─ murena-my-app      → /path/to/my-app
```

Each instance maintains:
- **Isolated language servers** - No interference between projects
- **Independent memory** - Project-specific knowledge and context
- **Separate caches** - Symbol caches for fast lookups

### Benefits

- ✅ **Work across projects** - Use tools from different projects in the same conversation
- ✅ **No context switching** - All projects available simultaneously
- ✅ **Perfect isolation** - Changes in one project don't affect others
- ✅ **Memory efficient** - Only active projects consume resources (150-200MB per project)

## Quick Start

### Automatic Setup (Recommended)

The easiest way to set up multi-project support:

```bash
# Discover and configure all Murena projects
murena multi-project setup-claude-code

# By default, searches ~/Documents/projects
# Use --search-root to specify a different directory
murena multi-project setup-claude-code --search-root ~/code
```

This command will:
1. Scan for Murena projects (directories with `.murena/project.yml`, `.git` + code files, or `pyproject.toml` with murena)
2. Generate MCP configurations for Claude Code
3. Save to `~/.claude/mcp_servers_murena.json`

**Next step:** Restart Claude Code to load the new MCP servers.

### Manual Setup

If you prefer manual control:

#### 1. Discover Projects

```bash
murena multi-project discover-projects
```

Output:
```
Found 3 Murena project(s):

  • serena
    Path: /Users/you/Documents/projects/serena
    Languages: python

  • spec-kit
    Path: /Users/you/Documents/projects/spec-kit
    Languages: python

  • my-app
    Path: /Users/you/code/my-app
    Languages: typescript, python
```

#### 2. Generate MCP Configs

```bash
murena multi-project generate-mcp-configs
```

This creates `~/.claude/mcp_servers_murena.json`:

```json
{
  "murena-serena": {
    "command": "uvx",
    "args": ["murena", "start-mcp-server", "--project", "/Users/you/Documents/projects/serena", "--auto-name"],
    "env": {}
  },
  "murena-spec-kit": {
    "command": "uvx",
    "args": ["murena", "start-mcp-server", "--project", "/Users/you/Documents/projects/spec-kit", "--auto-name"],
    "env": {}
  },
  "murena-my-app": {
    "command": "uvx",
    "args": ["murena", "start-mcp-server", "--project", "/Users/you/code/my-app", "--auto-name"],
    "env": {}
  }
}
```

#### 3. Restart Claude Code

```bash
# Stop Claude Code if running
# Then start it again to load new MCP servers
claude
```

## Managing Projects

### Add a Single Project

```bash
murena multi-project add-project /path/to/new-project
```

### Remove a Project

```bash
murena multi-project remove-project project-name
```

Note: Use the project **directory name**, not the full path. For example:
- ✅ `murena multi-project remove-project serena`
- ❌ `murena multi-project remove-project /Users/you/Documents/projects/serena`

### List Configured Projects

```bash
murena multi-project list-projects

# Show detailed configurations
murena multi-project list-projects --verbose
```

## Using Multi-Project Tools

Once configured, you can use MCP tools with project-specific namespaces:

### Tool Naming Convention

Tools are namespaced by project:
```
mcp__murena-{project-name}__{tool-name}
```

### Examples

#### Working with serena project:

```python
# Get symbols overview
mcp__murena-serena__get_symbols_overview(
    relative_path="src/murena/agent.py"
)

# Find a symbol
mcp__murena-serena__find_symbol(
    name_path_pattern="MurenaAgent",
    include_body=True
)

# Search for pattern
mcp__murena-serena__search_for_pattern(
    substring_pattern="def create_agent",
    restrict_search_to_code_files=True
)
```

#### Working with spec-kit project:

```python
# Get symbols in spec-kit
mcp__murena-spec-kit__get_symbols_overview(
    relative_path="templates/commands/specify.md"
)

# Find references in spec-kit
mcp__murena-spec-kit__find_referencing_symbols(
    name_path="SpecKitManager",
    relative_path="src/spec_kit/manager.py"
)
```

#### Cross-Project Workflow

You can work with multiple projects in a single Claude Code session:

```
User: "Update the MCP integration in serena to match the pattern used in spec-kit"

Claude:
1. mcp__murena-spec-kit__find_symbol("MCPIntegration")
   → Understands spec-kit pattern

2. mcp__murena-serena__find_symbol("MurenaMCPFactory")
   → Locates serena implementation

3. mcp__murena-serena__replace_symbol_body(...)
   → Updates serena code
```

## Advanced Configuration

### Custom Search Directory

By default, discovery searches `~/Documents/projects`. To use a different directory:

```bash
murena multi-project setup-claude-code --search-root ~/work/projects
```

### Merge vs. Overwrite Configs

When generating configs, you can choose to merge with existing configurations or overwrite:

```bash
# Merge with existing (default)
murena multi-project generate-mcp-configs --merge

# Overwrite existing
murena multi-project generate-mcp-configs --no-merge
```

### Custom Output Path

```bash
murena multi-project generate-mcp-configs --output ~/custom/path/mcp_servers.json
```

## Troubleshooting

### Servers Not Showing Up

1. **Check the config file exists:**
   ```bash
   cat ~/.claude/mcp_servers_murena.json
   ```

2. **Verify projects are listed:**
   ```bash
   murena multi-project list-projects
   ```

3. **Restart Claude Code** - MCP servers are loaded at startup

### Server Start Failures

Check MCP server logs:
```bash
# Logs are typically in:
~/.murena/logs/mcp_*.log

# Check recent errors:
tail -50 ~/.murena/logs/mcp_*.log
```

Common issues:
- **Project not found** - Verify project path in config
- **Language server errors** - Run `murena project health-check /path/to/project`
- **Port conflicts** - Each server needs a unique dashboard port (auto-incremented)

### High Memory Usage

Each MCP instance uses 150-200MB typically. If you have many projects (7+):

1. **Remove unused projects:**
   ```bash
   murena multi-project remove-project unused-project
   ```

2. **Use selective activation** - Only keep active projects in config

3. **Monitor resource usage:**
   ```bash
   # Check running MCP servers
   ps aux | grep murena

   # View memory usage
   ps aux | grep murena | awk '{sum+=$4} END {print sum"%"}'
   ```

### Tools Not Working

1. **Verify server name** - Use `murena multi-project list-projects` to see exact names
2. **Check namespace** - Ensure using `mcp__murena-{project-name}__` prefix
3. **Test basic tool:**
   ```python
   mcp__murena-serena__list_memories()
   ```

## Resource Management

### Memory Usage by Project Count

| Projects | Total Memory | Per Project |
|----------|-------------|-------------|
| 1 | 150MB | 150MB |
| 2 | 300MB | 150MB |
| 5 | 750MB | 150MB |
| 10 | 1500MB | 150MB |

**Recommendation:** For typical development (2-5 active projects), multi-project support uses less memory than expected.

### When to Use Multi-Project

**Good use cases:**
- Working on related projects (library + application)
- Cross-project refactoring
- Comparing implementations
- Maintaining multiple services

**Not recommended:**
- 10+ projects simultaneously (high memory)
- Unrelated projects you rarely switch between
- Projects you access only occasionally

## Migration from Single Project

If you previously used a single `murena` MCP server:

### Option 1: Keep Both (Recommended)

Keep your existing single-project setup and add multi-project support:

```bash
# Your existing config still works:
{
  "murena": { "command": "uvx", "args": [...] }
}

# Add multi-project configs:
murena multi-project setup-claude-code
```

Result: Both `murena` (your default project) and `murena-{project-name}` servers will be available.

### Option 2: Full Migration

Remove the old config and use only multi-project:

1. Backup old config:
   ```bash
   cp ~/.claude/claude_desktop_config.json ~/.claude/claude_desktop_config.json.backup
   ```

2. Remove old `murena` entry from config

3. Run setup:
   ```bash
   murena multi-project setup-claude-code
   ```

## Best Practices

1. **Use descriptive project names** - Directory names become part of tool namespace
2. **Keep configs in sync** - Re-run `setup-claude-code` when adding/removing projects
3. **Index projects** - Run `murena project index` for better performance
4. **Monitor memory** - Remove unused projects if memory is constrained
5. **Restart Claude Code** - After config changes, restart for changes to take effect

## Next Steps

- **Explore tool usage** - See [Tool Reference](../README.md#tools)
- **Optimize workflows** - Check [CLAUDE.md](../CLAUDE.md) for multi-project patterns
- **Report issues** - [GitHub Issues](https://github.com/oraios/serena/issues)

## FAQ

**Q: Can I have different language configurations per project?**
A: Yes! Each MCP instance loads its own `project.yml` with language-specific settings.

**Q: Do all projects need to be Python projects?**
A: No. Murena supports 19+ languages. Each project can use different languages.

**Q: How do I update configurations after changing project.yml?**
A: Re-run `murena multi-project generate-mcp-configs` and restart Claude Code.

**Q: Can I run custom commands per project?**
A: Yes. Each MCP server is independent and can have different configurations.

**Q: What happens if two projects have the same directory name?**
A: The last one wins. Use unique directory names or manually edit configs with custom server names.
