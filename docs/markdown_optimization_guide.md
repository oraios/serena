# Markdown Optimization Guide

**Comprehensive guide to efficient markdown documentation handling with Murena MCP**

## Table of Contents

- [Overview](#overview)
- [Why Symbolic Operations Matter](#why-symbolic-operations-matter)
- [Quick Start](#quick-start)
- [Common Workflows](#common-workflows)
- [Advanced Patterns](#advanced-patterns)
- [Token Efficiency Examples](#token-efficiency-examples)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

Murena MCP uses Marksman LSP to treat markdown files like source code, enabling symbolic navigation and extraction. This approach delivers **70-90% token savings** compared to traditional full-file reading.

### Key Benefits

- 📊 **90% token reduction** for large documentation files
- 🎯 **Precision targeting** - extract only needed sections
- ⚡ **Fast navigation** - hierarchical structure without loading content
- 💾 **Caching support** - reuse structure across queries
- 🔄 **Auto-detection** - works automatically on .md files

### How It Works

Marksman LSP exposes markdown headings as "symbols" (similar to classes/functions in code), enabling:

1. **Structure extraction** - Get document outline without reading content
2. **Section-level access** - Load specific sections on demand
3. **Cross-file navigation** - Follow links between documents
4. **Hierarchical queries** - Navigate heading levels (H1 > H2 > H3...)

## Why Symbolic Operations Matter

### The Token Problem

**Traditional approach:**
```python
# Read entire README (800 lines)
content = Read("README.md")
# Cost: ~25,000 tokens
# Problem: Entire file loaded into context for the whole conversation
```

**Symbolic approach:**
```python
# Phase 1: Get structure
overview = get_symbols_overview(relative_path="README.md", depth=2)
# Cost: ~1,000 tokens

# Phase 2: Extract needed section
section = find_symbol("Installation", relative_path="README.md", include_body=True)
# Cost: ~1,500 tokens

# Total: ~2,500 tokens (90% savings)
```

### Real-World Impact

For a typical documentation-heavy project:

| Scenario | Traditional | Symbolic | Savings |
|----------|-------------|----------|---------|
| Browse 5 docs to find info | 100,000 tokens | 5,000 tokens | 95% |
| Read specific API section | 25,000 tokens | 2,000 tokens | 92% |
| Navigate project wiki | 200,000 tokens | 20,000 tokens | 90% |
| Repeated documentation access | 25,000 tokens/read | 100 tokens (cached) | 99.6% |

## Quick Start

### Basic Pattern: Two-Phase Access

**Step 1: Get overview**
```python
overview = get_symbols_overview(
    relative_path="docs/api-reference.md",
    depth=2  # Include H1, H2, H3 levels
)

# Returns hierarchical structure:
# {
#   "String": [
#     {"name": "API Reference", "location": {...}},
#     {"name": "Authentication", "location": {...}},
#     {"name": "Endpoints", "location": {...}},
#     ...
#   ]
# }
```

**Step 2: Extract specific section**
```python
auth_section = find_symbol(
    name_path_pattern="Authentication",
    relative_path="docs/api-reference.md",
    include_body=True
)

# Returns only the Authentication section content
```

### Searching Across Documentation

```python
# Find all mentions of "authentication" in docs
results = search_for_pattern(
    substring_pattern="authentication",
    paths_include_glob="docs/**/*.md",
    context_lines_after=2,
    context_lines_before=1
)
```

## Common Workflows

### Workflow 1: Working with Large README

**Scenario:** Need to understand how to install a project from its 800-line README.

```python
# Step 1: See what's in the README
overview = get_symbols_overview(relative_path="README.md", depth=1)

# Output shows major sections:
# - Introduction
# - Features
# - Installation
# - Usage
# - Configuration
# - Contributing

# Step 2: Read only the Installation section
install_guide = find_symbol(
    name_path_pattern="Installation",
    relative_path="README.md",
    include_body=True
)

# Token cost: ~1,500 instead of 25,000 (94% savings)
```

### Workflow 2: Navigating API Documentation

**Scenario:** Find documentation for a specific API endpoint.

```python
# Step 1: Find all API documentation files
api_files = find_file(
    file_mask="*api*.md",
    relative_path="docs"
)

# Step 2: Get overview of main API doc
overview = get_symbols_overview(
    relative_path="docs/api-reference.md",
    depth=3  # Deep hierarchy for detailed API docs
)

# Step 3: Extract specific endpoint documentation
endpoint_docs = find_symbol(
    name_path_pattern="POST /users",
    relative_path="docs/api-reference.md",
    include_body=True,
    substring_matching=True  # Allow partial matches
)
```

### Workflow 3: Searching Documentation

**Scenario:** Find all documentation related to "authentication".

```python
# Step 1: Search for relevant files
auth_files = search_for_pattern(
    substring_pattern="authentication",
    paths_include_glob="**/*.md",
    restrict_search_to_code_files=False,  # Include all .md files
    head_limit=10  # Limit to top 10 matches
)

# Step 2: For each relevant file, get its structure
for file in auth_files:
    overview = get_symbols_overview(
        relative_path=file,
        depth=2
    )
    # Quickly scan headings to find most relevant section

# Step 3: Extract the specific section you need
auth_section = find_symbol(
    name_path_pattern="Authentication",
    relative_path="docs/security.md",
    include_body=True
)
```

### Workflow 4: Cross-File Documentation

**Scenario:** Navigate between related documentation files.

```python
# Step 1: Start with main guide
guide = get_symbols_overview(relative_path="docs/guide.md", depth=1)

# Step 2: Find cross-references using Marksman's link tracking
# (Marksman automatically tracks links between markdown files)

# Step 3: Load related documents on-demand
related = find_symbol(
    name_path_pattern="Advanced Configuration",
    relative_path="docs/advanced.md",
    include_body=True
)
```

## Advanced Patterns

### Pattern 1: Progressive Disclosure

Load documentation incrementally as needed:

```python
# Level 1: Project overview (top-level headings only)
overview = get_symbols_overview(relative_path="README.md", depth=0)
# Cost: ~500 tokens

# Level 2: Section structure (include subsections)
section_detail = get_symbols_overview(
    relative_path="README.md",
    depth=2
)
# Additional cost: ~500 tokens

# Level 3: Specific content (load actual section)
content = find_symbol(
    name_path_pattern="Quick Start",
    relative_path="README.md",
    include_body=True
)
# Additional cost: ~1,000 tokens

# Total: ~2,000 tokens vs. 25,000 for full read (92% savings)
```

### Pattern 2: Cached Navigation

Reuse structure across multiple queries:

```python
# First access: Full structure query
overview = get_symbols_overview(
    relative_path="docs/api.md",
    depth=2,
    use_cache=True  # Enable caching
)
# Cost: ~1,000 tokens

# Subsequent accesses: Cache hit
overview2 = get_symbols_overview(
    relative_path="docs/api.md",
    depth=2,
    use_cache=True
)
# Cost: ~100 tokens (90% savings over first access)
```

### Pattern 3: Hierarchical Search

Navigate deep documentation structures efficiently:

```python
# Find a subsection within a section
subsection = find_symbol(
    name_path_pattern="Advanced Configuration/Database Settings",
    relative_path="docs/config.md",
    include_body=True
)

# Substring matching for fuzzy search
methods = find_symbol(
    name_path_pattern="get",
    relative_path="docs/api.md",
    substring_matching=True,  # Match "getUserData", "getProfile", etc.
    include_body=False  # Metadata only
)
```

### Pattern 4: Bulk Documentation Analysis

Analyze multiple documentation files efficiently:

```python
# Get structure of all markdown files in parallel
doc_files = ["README.md", "CONTRIBUTING.md", "docs/api.md", "docs/guide.md"]

# Single message with parallel tool calls
overviews = []
for doc in doc_files:
    overview = get_symbols_overview(relative_path=doc, depth=1)
    overviews.append(overview)

# Total cost: ~4,000 tokens
# vs. reading all files: ~100,000 tokens (96% savings)
```

## Token Efficiency Examples

### Example 1: Large README Navigation

**File:** README.md (650 lines, ~25,000 tokens)

**Traditional approach:**
```python
Read("README.md")  # 25,000 tokens
# All 650 lines loaded into context
```

**Symbolic approach:**
```python
# Phase 1: Structure
get_symbols_overview("README.md", depth=2)  # 1,000 tokens

# Phase 2: Specific section
find_symbol("Installation", "README.md", include_body=True)  # 1,500 tokens

# Total: 2,500 tokens
# Savings: 22,500 tokens (90%)
```

### Example 2: API Documentation Search

**Scenario:** Find authentication endpoint docs in 300-line API reference

**Traditional:**
```python
content = Read("docs/api.md")  # 12,000 tokens
# Manual search through content
```

**Symbolic:**
```python
# Structure overview
get_symbols_overview("docs/api.md", depth=2)  # 600 tokens

# Direct section access
find_symbol("Authentication API", "docs/api.md", include_body=True)  # 800 tokens

# Total: 1,400 tokens
# Savings: 10,600 tokens (88%)
```

### Example 3: Multi-File Documentation Search

**Scenario:** Find error handling info across 5 documentation files

**Traditional:**
```python
for doc in docs:
    Read(doc)  # 5 × 15,000 = 75,000 tokens
```

**Symbolic:**
```python
# Search pattern
search_for_pattern(
    "error handling",
    paths_include_glob="docs/**/*.md",
    context_mode="line_only"
)  # 2,000 tokens

# Then load only relevant sections: ~3,000 tokens
# Total: 5,000 tokens
# Savings: 70,000 tokens (93%)
```

## Best Practices

### 1. Always Start with Structure

```python
# ❌ DON'T: Read entire file immediately
content = Read("docs/guide.md")  # 20,000 tokens wasted

# ✅ DO: Get structure first
overview = get_symbols_overview("docs/guide.md", depth=2)  # 800 tokens
# Then decide what you need
```

### 2. Use Appropriate Depth

```python
# For quick overview (top-level sections only)
get_symbols_overview("README.md", depth=0)  # ~500 tokens

# For moderate detail (include subsections)
get_symbols_overview("README.md", depth=2)  # ~1,000 tokens

# For deep documentation (all levels)
get_symbols_overview("docs/api.md", depth=4)  # ~2,000 tokens
```

### 3. Enable Caching for Repeated Access

```python
# First access
get_symbols_overview("docs/api.md", use_cache=True)  # 1,000 tokens

# Subsequent accesses
get_symbols_overview("docs/api.md", use_cache=True)  # 100 tokens (cached)
```

### 4. Restrict Search Scope

```python
# ❌ DON'T: Search entire project
search_for_pattern("config", paths_include_glob="**/*")

# ✅ DO: Narrow to documentation
search_for_pattern("config", paths_include_glob="docs/**/*.md")
```

### 5. Use Context Modes Wisely

```python
# For quick scanning (minimal context)
find_referencing_symbols(
    "MyClass",
    "src/module.py",
    context_mode="line_only"  # 75 tokens/reference
)

# For detailed analysis (full context)
find_referencing_symbols(
    "MyClass",
    "src/module.py",
    context_mode="full"  # 150 tokens/reference
)
```

## Troubleshooting

### Issue: Symbol Overview Returns Empty

**Symptom:** `get_symbols_overview()` returns no symbols for a markdown file.

**Possible causes:**
1. Marksman LSP not running
2. File has no headings
3. File not detected as markdown

**Solutions:**
```python
# 1. Verify file extension
assert file.endswith('.md') or file.endswith('.markdown')

# 2. Check if file has headings
# Markdown headings start with # characters

# 3. Verify Marksman is configured
# Check project.yml or murena_config.yml
```

### Issue: Section Not Found

**Symptom:** `find_symbol()` doesn't find expected section.

**Possible causes:**
1. Exact name mismatch
2. Section is nested deeper than expected
3. Typo in section name

**Solutions:**
```python
# Use substring matching for fuzzy search
find_symbol(
    "Install",  # Matches "Installation", "Install Guide", etc.
    "README.md",
    substring_matching=True
)

# Check actual section names first
overview = get_symbols_overview("README.md", depth=3)
print([s["name"] for s in overview])
```

### Issue: High Token Usage

**Symptom:** Symbolic operations still using many tokens.

**Possible causes:**
1. Including body when not needed
2. Too much depth
3. Not using cache

**Solutions:**
```python
# ❌ DON'T: Include body for navigation
find_symbol("Section", "file.md", include_body=True)  # Expensive

# ✅ DO: Get metadata first, body later
symbols = find_symbol("Section", "file.md", include_body=False)
# Then load body only if needed

# Enable caching
get_symbols_overview("file.md", use_cache=True)

# Use appropriate depth
get_symbols_overview("file.md", depth=1)  # Instead of depth=4
```

## Configuration

### Project-Level Configuration

Add to `.murena/project.yml`:

```yaml
language_servers:
  markdown:
    enabled: true
    command: "marksman"
    args: ["server"]
    ls_specific_settings: {}
```

### Global Configuration

Add to `~/.murena/murena_config.yml`:

```yaml
language_servers:
  markdown:
    enabled: true
```

### Disable Auto-Detection (if needed)

If you want to prevent markdown files from using symbolic operations:

```yaml
language_servers:
  markdown:
    enabled: false
```

## Summary

### Quick Reference

| Task | Tool | Token Cost | Use When |
|------|------|------------|----------|
| Get document outline | `get_symbols_overview(depth=1)` | ~500 | First look at any doc |
| Get detailed structure | `get_symbols_overview(depth=2-3)` | ~1,000 | Need subsection info |
| Read specific section | `find_symbol(..., include_body=True)` | ~1,500 | Know what you need |
| Search across docs | `search_for_pattern(..., glob='**/*.md')` | ~2,000 | Find relevant docs |
| Navigate hierarchy | `find_symbol(name_path='A/B/C')` | ~500 | Deep doc structures |

### Token Savings Formula

```
Traditional cost: file_lines × 4 tokens/line × 3 (formatting overhead)
Symbolic cost: num_headings × 25 tokens/heading + section_size

Savings = 70-95% for files >200 lines
```

### When to Use Symbolic Operations

- ✅ Files > 100 lines
- ✅ Structured documentation (with headings)
- ✅ Need specific sections only
- ✅ Repeated access to same docs
- ✅ Cross-file documentation navigation

### When to Use Traditional Read

- ❌ Small files (< 100 lines)
- ❌ Unstructured content (no headings)
- ❌ Need to see exact formatting
- ❌ One-time quick scan of tiny file

---

**For more information:**
- Main project CLAUDE.md: Markdown optimization section
- Murena MCP documentation: Symbol tools reference
- Marksman LSP: https://github.com/artempyanykh/marksman
