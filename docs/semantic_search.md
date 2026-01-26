# Semantic Search Guide

Murena's semantic search enables you to search codebases using natural language queries, finding relevant code based on meaning rather than exact keyword matches. This guide covers installation, usage, and best practices.

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Indexing Projects](#indexing-projects)
4. [Search Modes](#search-modes)
5. [Tool Reference](#tool-reference)
6. [Examples](#examples)
7. [Performance](#performance)
8. [Troubleshooting](#troubleshooting)

---

## Installation

Semantic search requires additional dependencies. Install them with:

```bash
uv pip install "murena-agent[semantic]"
```

**Dependencies installed:**
- `chromadb` - Vector database for embeddings storage
- `sentence-transformers` - Embedding models (Jina Code V2)
- `numpy` - Numerical operations

**Disk space:** ~500MB for embedding models + variable index size (typically 1-5MB per 1000 LOC)

---

## Quick Start

### 1. Index Your Project

```bash
# Via CLI
murena index-project --semantic

# Via MCP tool
mcp__murena__index_project_semantic(
    incremental=False,
    rebuild=False,
    skip_tests=True,
    skip_generated=True
)
```

**Output:**
```json
{
  "success": true,
  "total_files": 287,
  "indexed_files": 245,
  "total_symbols": 1847,
  "duration_seconds": 42.3,
  "embedding_model": "jinaai/jina-embeddings-v2-base-code"
}
```

### 2. Search Your Code

```python
# Natural language query
mcp__murena__semantic_search(
    query="find all authentication logic",
    max_results=10,
    min_score=0.5
)
```

**Output:**
```json
{
  "query": "find all authentication logic",
  "results": [
    {
      "sc": 0.92,
      "fp": "src/auth/user.py",
      "np": "UserService/authenticate",
      "k": "Method",
      "ln": 45,
      "t": "symbol"
    }
  ],
  "total_results": 8
}
```

### 3. Intelligent Search (Auto-Routing)

```python
# Automatically routes to LSP, vector, or hybrid
mcp__murena__intelligent_search(
    query="login method with JWT validation",
    max_results=10
)
```

---

## Indexing Projects

### Full Indexing

Index entire project from scratch:

```python
mcp__murena__index_project_semantic(
    incremental=False,
    rebuild=False,
    skip_tests=True,
    skip_generated=True,
    max_file_size=10000
)
```

**Parameters:**
- `incremental` (bool): Only index changed files (default: False)
- `rebuild` (bool): Clear existing index and rebuild (default: False)
- `skip_tests` (bool): Skip test files (default: True)
- `skip_generated` (bool): Skip generated files (default: True)
- `max_file_size` (int): Max file size in lines (default: 10000)

### Incremental Indexing

Re-index only changed files (10x faster):

```python
mcp__murena__index_project_semantic(incremental=True)
```

**How it works:**
- Computes SHA256 hash of each file
- Compares with stored hash in index
- Only re-indexes files with different hashes
- Removes old embeddings before re-indexing

### Rebuild Index

Clear and rebuild from scratch:

```python
mcp__murena__index_project_semantic(rebuild=True)
```

**When to rebuild:**
- After upgrading semantic search dependencies
- After changing embedding model
- Index corruption or errors

---

## Search Modes

Murena semantic search supports three modes with automatic routing:

### 1. LSP (Structural Search)

**When used:**
- Exact symbol names: `UserService`, `authenticate`
- Symbol paths: `UserService/authenticate`
- Short queries without semantic keywords

**Characteristics:**
- Exact matches only
- Fast (no embedding computation)
- Perfect scores (1.0)

**Example:**
```python
mcp__murena__intelligent_search(query="UserService")
# → Routes to LSP automatically
```

### 2. Vector (Semantic Search)

**When used:**
- Natural language: "find all authentication logic"
- Exploratory queries: "where is error handling"
- Multiple semantic keywords

**Characteristics:**
- Semantic similarity matching
- Embedding-based (0.0-1.0 scores)
- Finds conceptually similar code

**Example:**
```python
mcp__murena__intelligent_search(
    query="find all authentication logic"
)
# → Routes to vector automatically
```

### 3. Hybrid (LSP + Vector)

**When used:**
- Mixed queries: "login method with JWT validation"
- Structural + semantic keywords
- Queries with "method", "class", "function" + descriptions

**Characteristics:**
- Combines LSP and vector results
- Reciprocal Rank Fusion (RRF) merging
- Best of both worlds

**Example:**
```python
mcp__murena__intelligent_search(
    query="login method with JWT validation"
)
# → Routes to hybrid automatically
```

### Manual Mode Override

Override automatic routing:

```python
mcp__murena__intelligent_search(
    query="UserService",
    mode="vector"  # Force vector search
)
```

**Modes:** `"lsp"`, `"vector"`, `"hybrid"`, `"auto"` (default)

---

## Tool Reference

### IndexProjectSemanticTool

**Purpose:** Index project for semantic search

**Parameters:**
```python
def apply(
    incremental: bool = False,
    rebuild: bool = False,
    skip_tests: bool = True,
    skip_generated: bool = True,
    max_file_size: int = 10000,
) -> str
```

**Returns:** JSON with indexing statistics

---

### SemanticSearchTool

**Purpose:** Semantic search over indexed codebase

**Parameters:**
```python
def apply(
    query: str,
    max_results: int = 10,
    min_score: float = 0.5,
    file_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
    compact_format: bool = True,
) -> str
```

**Returns:** JSON with search results

**Filters:**
- `file_filter`: Glob pattern (e.g., "src/auth/**")
- `language_filter`: Language (e.g., "python", "typescript")
- `type_filter`: Result type ("symbol", "file_metadata", "chunk")

---

### IntelligentSearchTool

**Purpose:** Auto-routing intelligent search

**Parameters:**
```python
def apply(
    query: str,
    max_results: int = 10,
    min_score: float = 0.5,
    mode: Optional[str] = None,
    file_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
    compact_format: bool = True,
) -> str
```

**Returns:** JSON with search results + routing info

---

### FindSimilarCodeTool

**Purpose:** Find code similar to a snippet

**Parameters:**
```python
def apply(
    code_snippet: str,
    max_results: int = 5,
    min_score: float = 0.7,
    file_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
    compact_format: bool = True,
) -> str
```

**Returns:** JSON with similar code locations

**Use cases:**
- Code duplication detection
- Finding similar implementations
- Refactoring opportunities

---

### GetSemanticIndexStatusTool

**Purpose:** Check index status

**Parameters:**
```python
def apply() -> str
```

**Returns:** JSON with index statistics

---

## Examples

### Example 1: Find Authentication Code

```python
# Natural language query
result = mcp__murena__semantic_search(
    query="find all authentication and authorization logic",
    max_results=15,
    min_score=0.6,
    file_filter="src/**"
)
```

### Example 2: Detect Code Duplication

```python
# Find similar code to a snippet
result = mcp__murena__find_similar_code(
    code_snippet="""
    def validate_email(email: str) -> bool:
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    """,
    max_results=5,
    min_score=0.75
)
```

### Example 3: Incremental Updates

```python
# Index new project
mcp__murena__index_project_semantic()

# ... edit some files ...

# Re-index only changed files
mcp__murena__index_project_semantic(incremental=True)
```

### Example 4: Multi-Language Search

```python
# Search across Python and TypeScript
result = mcp__murena__semantic_search(
    query="database connection pooling",
    max_results=10,
    file_filter="src/**",
    # No language filter - searches all languages
)
```

---

## Performance

### Indexing Speed

| Project Size | Files | Symbols | Duration | Index Size |
|--------------|-------|---------|----------|------------|
| Small (1K LOC) | 10 | 150 | ~5s | 0.5 MB |
| Medium (10K LOC) | 100 | 1,500 | ~30s | 5 MB |
| Large (100K LOC) | 1,000 | 15,000 | ~5min | 50 MB |
| Very Large (1M LOC) | 10,000 | 150,000 | ~45min | 500 MB |

**Optimization tips:**
- Use `skip_tests=True` to reduce indexing time
- Use `max_file_size` to skip very large files
- Use incremental indexing for updates

### Search Latency

| Search Type | Latency | Notes |
|-------------|---------|-------|
| LSP | 50-200ms | Fast, exact matches |
| Vector | 200-500ms | Embedding computation + DB query |
| Hybrid | 300-700ms | Combined latency |

**Optimization tips:**
- Use `max_results` to limit result set
- Use `min_score` to filter low-quality results
- Use `file_filter` to narrow search scope

### Token Efficiency

Semantic search uses compact JSON format for 70% token savings:

**Standard format (150 tokens/result):**
```json
{
  "symbol_name": "UserService",
  "name_path": "UserService/authenticate",
  "file_path": "src/services/user_service.py",
  "similarity_score": 0.92,
  "code_snippet": "def authenticate(...)...",
  "line_range": {"start": 45, "end": 67}
}
```

**Compact format (45 tokens/result):**
```json
{
  "np": "UserService/authenticate",
  "fp": "src/services/user_service.py",
  "sc": 0.92,
  "ln": 45
}
```

**Savings:** 70% fewer tokens per result

---

## Troubleshooting

### Dependencies Not Installed

**Error:**
```json
{
  "error": "Semantic search dependencies not installed",
  "message": "Install with: uv pip install 'murena-agent[semantic]'"
}
```

**Solution:**
```bash
uv pip install "murena-agent[semantic]"
```

---

### No Index Found

**Error:**
```json
{
  "indexed": false,
  "message": "No semantic index found"
}
```

**Solution:**
```python
mcp__murena__index_project_semantic()
```

---

### Out of Memory During Indexing

**Error:**
```
MemoryError: Unable to allocate array
```

**Solutions:**
1. Reduce `max_file_size`:
   ```python
   mcp__murena__index_project_semantic(max_file_size=5000)
   ```

2. Enable file filters:
   ```python
   mcp__murena__index_project_semantic(
       skip_tests=True,
       skip_generated=True
   )
   ```

3. Index in batches (manually filter directories)

---

### Low Search Quality

**Problem:** Search returns irrelevant results

**Solutions:**
1. Increase `min_score`:
   ```python
   mcp__murena__semantic_search(query="...", min_score=0.7)
   ```

2. Use more specific queries
3. Use file/language filters
4. Try hybrid search instead of pure vector

---

### Slow Indexing

**Problem:** Indexing takes too long

**Solutions:**
1. Skip test files: `skip_tests=True`
2. Skip large files: `max_file_size=5000`
3. Use incremental indexing: `incremental=True`

---

## Best Practices

### Query Writing

**Good queries:**
- "find all authentication logic"
- "error handling for database operations"
- "user input validation methods"

**Poor queries:**
- "auth" (too vague)
- "find code" (no semantic content)
- Very long queries (>50 words)

### Indexing Strategy

**Initial setup:**
1. Full index with defaults
2. Verify with `get_semantic_index_status()`
3. Test with sample queries

**Ongoing maintenance:**
1. Use incremental indexing for daily updates
2. Full rebuild monthly or after major refactors
3. Monitor index size

### Search Strategy

**For known symbols:**
- Use LSP mode or let auto-routing choose
- Example: "UserService"

**For exploratory tasks:**
- Use vector mode
- Example: "find authentication logic"

**For mixed tasks:**
- Use hybrid mode or intelligent search
- Example: "login method with JWT validation"

---

## Architecture

### Components

```
┌─────────────────────────────────────────────┐
│      MURENA INTELLIGENT SEARCH              │
├─────────────────────────────────────────────┤
│                                             │
│  USER QUERY                                 │
│      ↓                                      │
│  QUERY ROUTER (auto-classify)              │
│      ↓                                      │
│  ┌─────────┬──────────┬──────────┐         │
│  │   LSP   │  Vector  │  Hybrid  │         │
│  │ (exact) │ (semantic)│ (merged) │         │
│  └─────────┴──────────┴──────────┘         │
│      ↓                                      │
│  RESULTS (compact JSON, 70% savings)       │
└─────────────────────────────────────────────┘
```

### Storage

**ChromaDB** (embedded vector database):
- Location: `.murena/semantic_index/`
- Format: Persistent storage on disk
- Isolation: Per-project (multi-project support)

**Embedding Model:**
- Primary: `jinaai/jina-embeddings-v2-base-code` (768D, ~400MB)
- Fallback: `sentence-transformers/all-MiniLM-L6-v2` (80MB)

**Index Structure:**
- File metadata embeddings
- Symbol embeddings (functions, classes, methods)
- Code chunk embeddings (for large functions)

---

## Future Enhancements

Planned features for future releases:

- **Cross-encoder reranking:** +15-20% relevance improvement
- **Background indexing:** Index in the background while working
- **GPU acceleration:** Faster embedding computation
- **Custom embeddings:** Fine-tuned models for specific domains
- **Incremental updates:** Real-time indexing on file save

---

## Feedback

Found a bug or have a feature request? Please report at:
https://github.com/oraios/murena/issues
