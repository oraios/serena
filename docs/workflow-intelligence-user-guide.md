# Workflow Intelligence User Guide

Welcome to Murena's Workflow Intelligence System! This guide will help you get the most out of the enhanced workflow capabilities in Claude Code.

## Table of Contents

1. [What's New](#whats-new)
2. [Getting Started](#getting-started)
3. [Using Composite Tools](#using-composite-tools)
4. [Workflow Discovery](#workflow-discovery)
5. [Token Optimization](#token-optimization)
6. [Troubleshooting](#troubleshooting)
7. [FAQ](#faq)

---

## What's New

The Workflow Intelligence system brings three major improvements to your Murena experience:

### 🚀 **Composite Tools** - Do More with Less
Instead of running 5-10 individual commands, use single composite tools that handle entire workflows:
- **Before**: `find_symbol` → `read_file` → `find_referencing_symbols` → `read_file` (again) → edit
- **After**: `RefactorSymbol` (one command, automatic test validation)
- **Result**: 70-90% fewer steps, 60-80% token savings

### 🎯 **Workflow Discovery** - Smart Suggestions
Claude now suggests workflows based on what you're trying to do:
- You: "Find and refactor the authentication code"
- Claude: "This looks like **refactor-with-tests** workflow. Use it? [Y/n]"
- **Result**: Guided navigation, no need to remember complex sequences

### 💡 **Progressive Guidance** - Context-Aware Help
After each operation, Claude suggests logical next steps:
- After `find_symbol` → suggests "Get body | Find references | Check tests"
- After refactoring → suggests "Run tests | Review changes"
- **Result**: Less cognitive load, faster task completion

---

## Getting Started

### Prerequisites

**Check if Murena MCP is Running:**
```bash
# From your project directory
murena-mcp-server
```

**Verify Workflow Intelligence is Active:**
When you open Claude Code in a Murena project, you should see:
```
✓ murena-intelligence skill loaded
✓ 15 workflows discovered
✓ Token budget: 200,000 (healthy)
```

### First Steps

1. **Ask for an overview** of available workflows:
   ```
   What workflows are available?
   ```

2. **Try a composite tool** with a simple task:
   ```
   Use NavigateToSymbol to find the authentication handler
   ```

3. **Let workflow discovery help** with a natural request:
   ```
   I want to safely rename UserService to AccountService
   ```
   Claude will suggest the `refactor-with-tests` workflow.

---

## Using Composite Tools

### What are Composite Tools?

Composite tools combine multiple operations into a single, optimized workflow. Think of them as "macros" that execute complex sequences intelligently.

### Available Composite Tools

#### 1. **NavigateToSymbol** - Smart Code Navigation

**What it does:** Finds symbols (classes, functions, methods) intelligently without reading entire files.

**When to use:**
- "Find the login handler in this codebase"
- "Locate the User class"
- "Show me the authentication logic"

**Example:**
```
User: Find the authentication handler
Claude: Using NavigateToSymbol...
        ✓ Searched pattern 'authentication' in 50 files
        ✓ Found 3 candidate files
        ✓ Analyzed symbols in auth/handler.py
        ✓ Located: AuthHandler.handle_request (line 45)
```

**Token savings:** 75% compared to manual search + read operations

---

#### 2. **RefactorSymbol** - Safe Refactoring

**What it does:** Renames or modifies symbols across your codebase with LSP-based accuracy and automatic test validation.

**When to use:**
- "Rename UserService to AccountService"
- "Refactor the login method"
- "Move helper functions to utils module"

**Example:**
```
User: Rename getUserProfile to fetchUserProfile
Claude: Using RefactorSymbol...
        ✓ Found symbol definition in services/user.py
        ✓ Found 12 references across 5 files
        ✓ Renamed using LSP (codebase-wide accuracy)
        ✓ Running tests for validation...
        ✓ All 45 tests passed
```

**Token savings:** 80-90% compared to manual find + edit operations

**Safety:** Automatic test validation prevents broken code from being committed.

---

#### 3. **ExtractDocSection** - Documentation Navigation

**What it does:** Finds and extracts specific sections from documentation files (README, API docs, guides).

**When to use:**
- "Show me the installation instructions from README"
- "Extract the API authentication section"
- "Find the troubleshooting guide in the docs"

**Example:**
```
User: Show me the Quick Start section from README
Claude: Using ExtractDocSection...
        ✓ Analyzed README.md structure (650 lines)
        ✓ Found heading: Quick Start (line 45)
        ✓ Extracted section (35 lines)

        # Quick Start
        [Section content displayed here]
```

**Token savings:** 90% compared to reading entire documentation files

**How it works:** Uses Marksman LSP to navigate markdown headings like code symbols.

---

#### 4. **AnalyzeModule** - Architecture Overview

**What it does:** Provides a comprehensive overview of a module's structure, dependencies, and key symbols.

**When to use:**
- "Give me an overview of the authentication module"
- "Understand the structure of the API layer"
- "What's in the utils package?"

**Example:**
```
User: Analyze the auth module
Claude: Using AnalyzeModule...
        ✓ Scanned 12 files in auth/
        ✓ Found 8 classes, 34 functions
        ✓ Identified 5 external dependencies

        ## Structure
        - AuthHandler (core)
        - TokenManager (JWT operations)
        - UserValidator (validation logic)
        [...]
```

**Token savings:** 70% compared to reading multiple files

---

#### 5. **CrossProjectSearch** - Multi-Project Operations

**What it does:** Searches for patterns across multiple projects, aggregates results, and deduplicates findings.

**When to use:**
- "Check if pattern X exists in all my projects"
- "Find similar authentication implementations"
- "Search for security vulnerabilities across projects"

**Example:**
```
User: Search for JWT token usage in all projects
Claude: Using CrossProjectSearch...
        ✓ Searched 3 projects (serena, spec-kit, api-gateway)
        ✓ Found 8 matches across projects
        ✓ Deduplicated similar results

        ## Results by Project
        serena: 3 matches
        spec-kit: 2 matches
        api-gateway: 3 matches
```

**Token savings:** 60% compared to manual per-project searches

---

### How to Use Composite Tools

**Direct Invocation:**
```
Use <ToolName> to <task>
```

**Natural Language (Recommended):**
Just describe what you want, and Claude will suggest the right composite tool:
```
"I need to find and understand the authentication logic"
→ Claude suggests: NavigateToSymbol

"Rename UserService to AccountService safely"
→ Claude suggests: RefactorSymbol
```

---

## Workflow Discovery

### What is Workflow Discovery?

Workflow discovery analyzes your natural language requests and suggests pre-built workflows that match your intent.

### How It Works

1. **You describe your task naturally**
2. **Claude analyzes keywords and patterns**
3. **Claude suggests matching workflows**
4. **You approve or adjust**
5. **Workflow executes with progress updates**

### Example Interactions

#### Example 1: Code Navigation

```
User: I want to understand how authentication works in this codebase

Claude: 🎯 This looks like the **navigate-codebase** workflow.

        This workflow will:
        1. Search for authentication-related files
        2. Analyze module structure
        3. Find key symbols (classes, functions)
        4. Map dependencies

        Use this workflow? [Y/n]

User: y

Claude: ✓ Running navigate-codebase workflow...
        [Step 1/4] Searching for pattern 'authentication'...
        [Step 2/4] Analyzing auth/ module...
        [Step 3/4] Finding key symbols...
        [Step 4/4] Mapping dependencies...

        ✅ Workflow complete! Found:
        - AuthHandler class (core)
        - 5 authentication methods
        - 3 external dependencies (JWT, bcrypt, redis)
```

**Token savings:** 80% compared to manual exploration

---

#### Example 2: Safe Refactoring

```
User: Rename UserService to AccountService throughout the codebase

Claude: 🎯 This looks like the **refactor-with-tests** workflow.

        This workflow will:
        1. Find the UserService symbol
        2. Find all references (codebase-wide)
        3. Rename using LSP (accurate)
        4. Run tests to verify no breakage

        Use this workflow? [Y/n]

User: y

Claude: ✓ Running refactor-with-tests workflow...
        [Step 1/4] Finding UserService definition...
        [Step 2/4] Finding 15 references across 7 files...
        [Step 3/4] Renaming to AccountService...
        [Step 4/4] Running tests...

        ✅ Workflow complete!
        - Renamed 15 references
        - All 52 tests passed
        - No broken imports
```

**Token savings:** 85% compared to manual refactoring

---

#### Example 3: Documentation Extraction

```
User: Extract the API authentication documentation

Claude: 🎯 This looks like the **document-api** workflow.

        This workflow will:
        1. Search markdown files for 'authentication'
        2. Navigate to API docs using headings
        3. Extract relevant sections
        4. Link to related code

        Use this workflow? [Y/n]

User: y

Claude: ✓ Running document-api workflow...
        [Step 1/3] Searching docs/ for authentication...
        [Step 2/3] Navigating to API.md → Authentication section...
        [Step 3/3] Linking to auth/ module code...

        ✅ Workflow complete!

        # API Authentication
        [Documentation content]

        Related code:
        - auth/handler.py:45 (AuthHandler.authenticate)
        - auth/tokens.py:12 (TokenManager.verify)
```

**Token savings:** 90% compared to reading full documentation files

---

### Built-in Workflows

| Workflow | Trigger Keywords | Use Case |
|----------|------------------|----------|
| **navigate-codebase** | "find", "understand", "explore", "show" | Code exploration |
| **refactor-with-tests** | "rename", "refactor", "restructure", "move" | Safe code changes |
| **document-api** | "extract", "documentation", "API", "guide" | Doc extraction |
| **cross-project-refactor** | "all projects", "multi-project", "workspace" | Cross-project ops |

### Customizing Workflow Suggestions

**Disable workflow suggestions:**
```
Don't suggest workflows for this session
```

**Force a specific workflow:**
```
Use the refactor-with-tests workflow for this task
```

**See all available workflows:**
```
List all workflows
```

---

## Token Optimization

### Understanding Token Budgets

Each Claude Code session has a token budget (default: 200,000 tokens). The workflow intelligence system helps you stay within budget.

### Automatic Token Monitoring

**Healthy (0-75%):**
```
✓ Token budget healthy: 35.2% (70,400/200,000)
```

**Warning (75-90%):**
```
⚠️  WARNING: Token budget at 78.5%
Optimization suggestions:
  - Use get-cached-symbols for repeated file access
  - Enable compact_format=True for large results
  - Prefer composite tools over manual sequences
```

**Critical (90%+):**
```
🚨 CRITICAL: Token budget at 92.3%
Auto-optimizations enabled:
  - Switching to compact_format=True
  - Using context_mode='line_only' for references
  - Enabling aggressive caching
```

### Token Optimization Tips

#### 1. **Use Symbolic Tools for Large Files**

**❌ Don't:**
```
Read the entire user_service.py file (1200 lines)
→ 50,000 tokens
```

**✅ Do:**
```
Get symbols overview of user_service.py
→ 1,000 tokens (98% savings)

Then read specific symbols:
Find UserService.authenticate method
→ 500 tokens
```

---

#### 2. **Leverage Caching for Repeated Access**

**❌ Don't:**
```
Turn 1: Read user_service.py → 50,000 tokens
Turn 2: Read user_service.py again → 50,000 tokens
Turn 3: Read user_service.py again → 50,000 tokens
Total: 150,000 tokens
```

**✅ Do:**
```
Turn 1: Get symbols overview → 1,000 tokens (cached)
Turn 2: Use cached symbols → 100 tokens (99% savings)
Turn 3: Use cached symbols → 100 tokens (99% savings)
Total: 1,200 tokens (99.2% savings)
```

---

#### 3. **Use Composite Tools Instead of Manual Sequences**

**❌ Manual approach:**
```
1. Search for 'auth' → 5,000 tokens
2. Read 3 candidate files → 30,000 tokens
3. Find symbol in each → 3,000 tokens
4. Read symbol bodies → 5,000 tokens
Total: 43,000 tokens
```

**✅ Composite approach:**
```
NavigateToSymbol('auth handler')
→ 8,000 tokens (81% savings)
```

---

#### 4. **Use Markdown Symbolic Tools**

**❌ Don't:**
```
Read entire README.md (650 lines)
→ 25,000 tokens
```

**✅ Do:**
```
Get symbols overview of README.md
→ 1,000 tokens (heading structure)

Extract specific section:
Find symbol 'Installation' in README.md
→ 1,500 tokens (specific section only)

Total: 2,500 tokens (90% savings)
```

---

### Token Budget Recommendations by Project Size

| Project Size | Budget | Conservative Usage | Aggressive Usage |
|--------------|--------|-------------------|------------------|
| **Small** (<50 files) | 50,000 | Basic operations only | Composite tools, caching |
| **Medium** (50-200 files) | 100,000 | Symbolic tools preferred | Aggressive caching, workflows |
| **Large** (200-500 files) | 150,000 | Always use symbolic | Composite tools mandatory |
| **Very Large** (500+ files) | 200,000 | Composite tools only | Auto-optimization enabled |

---

## Troubleshooting

### Issue 1: Workflow Not Suggested

**Symptom:** You describe a task, but Claude doesn't suggest a workflow.

**Possible Causes:**
1. Keywords don't match workflow patterns
2. Workflow discovery threshold too high
3. Request is too vague

**Solutions:**

**Be more explicit:**
```
❌ "Help with code"
✅ "Find and refactor the authentication code"
```

**Use trigger keywords:**
```
For navigation: "find", "explore", "show", "locate"
For refactoring: "rename", "refactor", "restructure"
For docs: "extract", "documentation", "guide"
```

**Force a workflow:**
```
Use the navigate-codebase workflow to find authentication code
```

---

### Issue 2: Composite Tool Fails

**Symptom:** Composite tool execution fails midway.

**Possible Causes:**
1. File not found (incorrect path)
2. Symbol doesn't exist
3. Language server not running

**Solutions:**

**Check file existence:**
```
List files matching pattern *.py in src/auth/
```

**Verify symbol exists:**
```
Get symbols overview of src/auth/handler.py
```

**Restart language server:**
```bash
murena-mcp-server --restart
```

**Use manual operations as fallback:**
```
If NavigateToSymbol fails:
1. Search for pattern manually
2. Get symbols overview of candidate files
3. Find specific symbol
```

---

### Issue 3: Token Budget Exceeded

**Symptom:** Session reaches critical token budget (90%+).

**Immediate Actions:**

**1. Enable auto-optimization:**
```
Enable aggressive token optimization
```

**2. Clear cache (if stale):**
```
Clear symbol cache
```

**3. Use haiku model for simple operations:**
```
Use haiku model for file searches
```

**4. Start new session:**
If budget is exhausted, start a fresh session for new tasks.

**Prevention:**

- ✅ Always use symbolic tools for files >100 lines
- ✅ Enable caching for repeated access
- ✅ Use composite tools instead of manual sequences
- ✅ Prefer workflows for complex tasks
- ✅ Monitor budget throughout session

---

### Issue 4: Workflow Suggestions Too Frequent

**Symptom:** Claude suggests workflows for every request, even simple ones.

**Solutions:**

**Adjust threshold:**
```
Only suggest workflows when confidence >80%
```

**Disable for this session:**
```
Don't suggest workflows for this session
```

**Provide explicit instructions:**
```
Just search for 'auth' without suggesting workflows
```

---

### Issue 5: Composite Tool Slower Than Expected

**Symptom:** Composite tool takes longer than manual operations.

**Possible Causes:**
1. Language server starting up (first operation)
2. Large codebase (many files to scan)
3. Network latency (if remote LSP)

**Solutions:**

**Pre-warm language server:**
```bash
murena-mcp-server --pre-index
```

**Use thoroughness parameter:**
```
Use NavigateToSymbol with thoroughness='quick'
```

**Restrict search scope:**
```
NavigateToSymbol for 'AuthHandler' in src/auth/ directory only
```

---

## FAQ

### Q: What's the difference between composite tools and workflows?

**A:**
- **Composite tools** are single MCP tools that execute multi-step operations (e.g., `NavigateToSymbol`)
- **Workflows** are YAML-defined sequences that can call multiple tools and other workflows (e.g., `refactor-with-tests.yml`)

Both reduce friction, but workflows are more flexible and customizable.

---

### Q: Can I create my own workflows?

**A:** Yes! Create YAML files in `~/.murena/workflows/` or `.murena/workflows/` in your project.

**Example workflow:**
```yaml
name: my-custom-workflow
description: My custom workflow for X task
steps:
  - tool: find_symbol
    args:
      name_path_pattern: ${symbol_name}

  - tool: find_referencing_symbols
    args:
      name_path: ${symbol_name}
      context_mode: line_only
```

See [Developer Guide](workflow-intelligence-developer-guide.md) for details.

---

### Q: How do I know which composite tool to use?

**A:** Just describe your task naturally. Claude will suggest the best tool:

```
"Find authentication code" → NavigateToSymbol
"Rename UserService" → RefactorSymbol
"Extract API docs" → ExtractDocSection
```

You can also ask: `Which composite tool should I use for <task>?`

---

### Q: Can I disable workflow intelligence?

**A:** Yes, but you'll lose token savings and guidance. To disable:

```
Disable workflow intelligence for this session
```

Or edit `~/.claude/config.yaml`:
```yaml
skills:
  murena-intelligence:
    enabled: false
```

---

### Q: How much token savings can I expect?

**A:** Depends on your workflow:

| Operation Type | Token Savings |
|----------------|---------------|
| Navigation (composite tools) | 70-85% |
| Refactoring (workflows) | 80-90% |
| Documentation (symbolic) | 90-95% |
| Caching (repeated access) | 99% |

**Average:** 60-70% token savings across common tasks.

---

### Q: What languages are supported?

**A:** Murena MCP supports 19 languages via LSP:

Python, JavaScript, TypeScript, Go, Java, Rust, Ruby, PHP, C/C++, C#, Swift, Kotlin, Scala, Elixir, Clojure, Perl, PowerShell, Bash, Vue

Markdown documentation is also fully supported with symbolic navigation.

---

### Q: Can workflow intelligence work across multiple projects?

**A:** Yes! Use the `CrossProjectSearch` composite tool or multi-project workflows.

**Setup:**
```bash
murena multi-project setup-claude-code
```

**Usage:**
```
Search for 'authentication' across all my projects
→ Claude uses CrossProjectSearch composite tool
```

---

### Q: How do I see workflow execution progress?

**A:** Workflows show step-by-step progress:

```
✓ Running refactor-with-tests workflow...
[Step 1/4] Finding UserService definition... ✓
[Step 2/4] Finding references... ✓ (15 found)
[Step 3/4] Renaming to AccountService... ✓
[Step 4/4] Running tests... ✓ (52 passed)

✅ Workflow complete!
```

---

### Q: What if a workflow fails midway?

**A:** Workflows include error recovery:

1. **Automatic retry** for transient errors (language server restart)
2. **Fallback strategies** for tool failures
3. **Partial results** returned even if some steps fail
4. **Error messages** explain what went wrong and suggest fixes

**Example:**
```
[Step 3/4] Renaming to AccountService... ❌
Error: LSP server not responding

Retrying with fallback strategy...
[Step 3/4] Using regex-based rename... ✓

⚠️  Warning: Used fallback. Review changes manually.
```

---

### Q: How do I learn what workflows are available?

**A:** Ask Claude:

```
List all available workflows
```

Or check:
- Built-in workflows: See this guide above
- User workflows: `~/.murena/workflows/`
- Project workflows: `.murena/workflows/` in your project

---

### Q: Can I contribute new composite tools or workflows?

**A:** Yes! See the [Developer Guide](workflow-intelligence-developer-guide.md) for:
- Creating custom composite tools
- Writing reusable workflows
- Contributing to Murena repository

---

## Getting Help

**Documentation:**
- **This guide** - User-focused workflow intelligence usage
- [Developer Guide](workflow-intelligence-developer-guide.md) - Technical implementation details
- [Murena README](../README.md) - General Murena documentation

**Support:**
- Ask Claude: "How do I use workflow intelligence for <task>?"
- Check logs: `~/.murena/logs/` for debugging
- GitHub issues: Report bugs or request features

**Quick Tips:**
1. Use natural language - Claude understands intent
2. Let workflows guide you - accept suggestions
3. Monitor token budget - optimize when warned
4. Use symbolic tools - massive token savings
5. Enable caching - 99% savings on repeated access

---

## Summary

**Workflow Intelligence** transforms how you work with code in Claude:

✅ **70-90% fewer manual steps** - Composite tools automate sequences
✅ **60-80% token savings** - Symbolic operations and caching
✅ **Smart guidance** - Contextual next-step suggestions
✅ **Workflow discovery** - Auto-suggests optimal approaches
✅ **Safe refactoring** - LSP-based accuracy + test validation

**Start using it today:**
1. Describe tasks naturally
2. Accept workflow suggestions
3. Let Claude optimize token usage automatically

**Questions?** Just ask Claude: "How do I use workflow intelligence for <your task>?"

---

**Last updated:** 2026-01-26
**Version:** 1.0
**For Murena version:** 0.3.0+
