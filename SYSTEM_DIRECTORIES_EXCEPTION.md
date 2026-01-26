# System Directories Exception - Global Rules Update

**Date:** 2026-01-25
**Scope:** `~/.claude/CLAUDE.md` - Exception for system directories

## Summary

Added explicit exception for **system directories** to global Claude Code optimization rules. These directories should use **built-in tools** instead of Murena MCP for speed and practicality.

## Why This Exception

### Problem Identified

User noticed Claude Code using built-in tools (Grep, Search, Read) for `~/.claude` directory instead of Murena MCP symbolic tools, which seemed to contradict the newly added markdown optimization rules.

### Root Cause

**Murena MCP operates at PROJECT scope:**

```bash
# Murena works here (active project):
/Users/dmitry.lazarenko/Documents/projects/serena/
  → mcp__murena__* tools available

# Murena does NOT work here (system directory):
~/.claude/
  → Outside project scope
  → No active project context
```

### Why Built-in Tools Are Correct for System Directories

**Technical reasons:**

1. **No LSP context** - System directories are not activated Murena projects
2. **Speed** - Direct file access faster than LSP initialization
3. **File characteristics** - Typically small config files (<100 lines)
4. **No symbolic structure** - Config files don't have classes/functions
5. **Different purpose** - System configs vs project code

**Practical reasons:**

1. **~/.claude/** - Claude Code configuration (hooks, skills, plugins)
2. **/etc/** - OS configuration files
3. **/usr/** - System binaries and libraries
4. **~/.config/** - Application configs

These are **not coding projects** - symbolic tools don't add value.

## What Changed

### 1. ✅ Exception Cases Section

**Before:**
```markdown
**ONLY use built-in tools when:**
- ✅ File is < 100 lines AND non-critical
- ✅ File is not code AND not markdown (JSON, YAML, config, etc.)
- ✅ Murena MCP server is not configured/available
- ✅ Symbolic tools have failed (fallback)
- ✅ Interactive debugging requiring full file visibility
```

**After:**
```markdown
**ONLY use built-in tools when:**
- ✅ File is < 100 lines AND non-critical
- ✅ File is not code AND not markdown (JSON, YAML, config, etc.)
- ✅ Murena MCP server is not configured/available
- ✅ **System directories** (~/.claude, /etc, /usr, ~/.config) - use built-in for speed
- ✅ Symbolic tools have failed (fallback)
- ✅ Interactive debugging requiring full file visibility

**NOTES**:
- Markdown files (.md, .markdown) are now treated like code files - use symbolic tools!
- **System directories exception**: For Claude Code config directories (~/.claude/*) and OS
  system paths, built-in tools are faster and appropriate since these are typically small
  config files outside project scope
```

### 2. ✅ Pre-Execution Checklist (Murena MCP section)

**Before:**
```markdown
1. ☐ Is Murena MCP server configured for this project?
2. ☐ Is this a code file OR markdown file? (check extension)
3. ☐ Can I use a symbolic Murena tool instead?
4. ☐ If yes to all 3 → **USE MURENA MCP TOOL**
```

**After:**
```markdown
1. ☐ Is this in a system directory (~/.claude, /etc, /usr)? → **Use built-in tools**
2. ☐ Is Murena MCP server configured for this project?
3. ☐ Is this a code file OR markdown file? (check extension)
4. ☐ Can I use a symbolic Murena tool instead?
5. ☐ If yes to 2-4 and NO to 1 → **USE MURENA MCP TOOL**

**System directory exception**: ~/.claude/*, /etc/*, /usr/*, ~/.config/* - use built-in tools for speed
```

### 3. ✅ Validation Checklist (Token Optimization section)

**Before:**
```markdown
1. ☐ Have I checked the file size?
2. ☐ Can I use a symbolic tool instead of Read()?
3. ☐ Is this a markdown file? (Use symbolic tools like code files!)
...
9. ☐ Have I batched independent operations?

**If you answered NO to questions 2-9, STOP and reconsider your approach.**
```

**After:**
```markdown
1. ☐ Is this in a system directory (~/.claude, /etc, /usr)? → **Use built-in tools**
2. ☐ Have I checked the file size?
3. ☐ Can I use a symbolic tool instead of Read()?
4. ☐ Is this a markdown file? (Use symbolic tools like code files!)
...
10. ☐ Have I batched independent operations?

**If you answered YES to question 1, use built-in tools. Otherwise, if you answered NO to
questions 3-10, STOP and reconsider your approach.**

**Special notes:**
- **System directories**: ~/.claude/*, /etc/*, /usr/* - always use built-in tools (faster,
  appropriate for configs)
- **Markdown files**: README >200 lines = use symbolic tools (90% token savings)
```

## System Directories Defined

**Directories where built-in tools are appropriate:**

| Directory | Purpose | Why Built-in |
|-----------|---------|--------------|
| `~/.claude/*` | Claude Code config | Outside project scope, small configs |
| `~/.config/*` | Application configs | System-level settings |
| `/etc/*` | OS configuration | System files, not project code |
| `/usr/*` | System binaries | Read-only system files |
| `~/.local/*` | User-level installs | Not project workspace |
| `~/.murena/*` | Murena MCP config | Config files, not code |

**Directories where Murena MCP applies:**

| Directory | Purpose | Why Murena |
|-----------|---------|------------|
| `~/Documents/projects/*` | Active projects | Project workspace, symbolic structure |
| `~/code/*` | Development work | Source code with classes/functions |
| `/workspace/*` | Container projects | Active development |
| Any git repository | Version-controlled code | Code with symbolic structure |

## Decision Flow

```
File operation requested
    │
    ▼
Is path in system directory?
    │
    ├─ YES → ~/.claude, /etc, /usr, ~/.config
    │         │
    │         ▼
    │    Use built-in tools (Grep, Read, Search)
    │    SKIP Murena MCP
    │
    └─ NO → ~/Documents/projects/*, ~/code/*, git repos
              │
              ▼
         Is Murena MCP available?
              │
              ├─ YES → Use Murena symbolic tools
              │
              └─ NO → Fall back to built-in tools
```

## Examples

### ✅ Correct: System Directory (Built-in Tools)

```python
# Searching Claude Code hooks
Search(pattern="SubagentStart", path="~/.claude/hooks")
# CORRECT - system directory, use built-in

# Reading hook documentation
Read("~/.claude/plugins/.../hook-development/SKILL.md")
# CORRECT - system config, small file

# Finding config files
Bash("find ~/.claude -name '*.yml' -type f")
# CORRECT - system directory exploration
```

### ✅ Correct: Project Directory (Murena MCP)

```python
# Reading project documentation
get_symbols_overview(relative_path="docs/api.md", depth=2)
# CORRECT - project file, use Murena

# Finding code symbols
find_symbol("AuthService", relative_path="src/services/")
# CORRECT - project code, symbolic tools

# Editing project code
replace_symbol_body(
    name_path="MyClass/my_method",
    relative_path="src/module.py",
    body="..."
)
# CORRECT - project code, symbolic editing
```

### ❌ Wrong: System Directory with Murena

```python
# DON'T do this:
get_symbols_overview(relative_path="~/.claude/CLAUDE.md")
# WRONG - outside project scope, won't work

# DON'T do this:
find_symbol("config", relative_path="~/.murena/murena_config.yml")
# WRONG - YAML config, not code with symbols
```

## Impact

### For Claude Code Behavior

**Now explicitly documented and justified:**
- ✅ Using Grep/Search for `~/.claude` is **correct**
- ✅ Using Read for small system configs is **appropriate**
- ✅ Murena MCP tools are for **project files only**

### For Token Optimization

**Still applies where it matters:**
- ✅ Project code: Use Murena MCP (70-90% savings)
- ✅ Project markdown: Use Murena MCP (70-90% savings)
- ✅ System configs: Use built-in (already optimal)

### For Users

**Clear expectations:**
- System directories → Built-in tools (fast, simple)
- Project directories → Murena MCP (efficient, symbolic)
- No confusion about "why isn't it using Murena?"

## File Modified

**Single file updated:**
- `~/.claude/CLAUDE.md`

**Sections modified:** 3 sections
1. Exception Cases (lines ~573-582)
2. Pre-Execution Checklist (lines ~562-571)
3. Validation Checklist (lines ~350-367)

## Verification

To verify the exception is working:

```bash
# This should use built-in tools:
# - Search in ~/.claude
# - Read from ~/.claude
# - Grep in /etc

# This should use Murena MCP:
# - get_symbols_overview for project files
# - find_symbol for project code
# - search_for_pattern within project
```

## Summary

Added pragmatic exception for system directories where:
- Murena MCP is unavailable (outside project scope)
- Built-in tools are faster (no LSP overhead)
- File types don't benefit from symbolic operations (configs, not code)

This resolves the apparent contradiction and documents expected behavior.

**Status:** ✅ System directory exception documented and active
