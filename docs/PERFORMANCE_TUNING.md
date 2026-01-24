# Performance Tuning Guide

Language-specific tuning, optimization tips, and performance benchmarks for Murena.

---

## Quick Start

### Settings by Project Size

**Small (<1000 files, <10 MB):**
```yaml
cache:
  lru:
    max_raw_symbols_entries: 500
    max_raw_symbols_memory_mb: 100
parallel_execution:
  max_workers: 10
```

**Medium (1000-10000 files, 10-100 MB):**
```yaml
cache:
  lru:
    max_raw_symbols_entries: 1000
    max_raw_symbols_memory_mb: 200
parallel_execution:
  max_workers: 10
token_optimization:
  reference_context_mode: "line_only"
```

**Large (>10000 files, >100 MB):**
```yaml
cache:
  lru:
    max_raw_symbols_entries: 2000
    max_raw_symbols_memory_mb: 400
parallel_execution:
  max_workers: 15
token_optimization:
  reference_context_mode: "none"
```

---

## Per-Language Tuning

### TypeScript / JavaScript

**Characteristics:** Fast, stable, handles concurrency well

**Settings:**
```yaml
language_servers:
  typescript:
    parallel_execution:
      max_workers: 15
    cache:
      lru:
        max_raw_symbols_entries: 2000
        max_raw_symbols_memory_mb: 300
    indexing:
      exclude_patterns:
        - "**/node_modules/**"
        - "**/dist/**"
```

**Performance:** Symbol tree (1000 files): 8-12s, Cache hit rate: >85%

---

### Python

**Characteristics:** Pyright fast and stable, type hints improve performance

**Settings:**
```yaml
language_servers:
  python:
    server: "pyright"  # Prefer over pylance
    parallel_execution:
      max_workers: 12
    cache:
      lru:
        max_raw_symbols_entries: 1500
        max_raw_symbols_memory_mb: 250
    indexing:
      exclude_patterns:
        - "**/.venv/**"
        - "**/__pycache__/**"
```

**Tips:** Use type hints, create pyrightconfig.json

**Performance:** Symbol tree (1000 files): 10-15s, Cache hit rate: >80%

---

### Go

**Characteristics:** gopls stable but memory-hungry

**Settings:**
```yaml
language_servers:
  go:
    parallel_execution:
      max_workers: 10
    cache:
      lru:
        max_raw_symbols_entries: 1000
        max_raw_symbols_memory_mb: 300  # Higher memory
    server_config:
      env:
        GOMODCACHE: "/path/to/cache"
```

**Tips:** Enable module caching, use go.work for workspaces

**Performance:** Symbol tree (1000 files): 12-18s, Cache hit rate: >75%

---

### Java

**Characteristics:** jdtls slow to start (JVM warmup), high memory

**Settings:**
```yaml
language_servers:
  java:
    parallel_execution:
      max_workers: 5  # Conservative
    cache:
      lru:
        max_raw_symbols_entries: 1000
        max_raw_symbols_memory_mb: 400  # Memory-heavy
    server_config:
      jvm_args:
        - "-Xmx4G"
        - "-XX:+UseG1GC"
```

**Tips:** Use Gradle/Maven caching, let jdtls warm up (30-60s)

**Performance:** Symbol tree (1000 files): 25-40s (including warmup), Cache hit rate: >70%

---

### Rust

**Characteristics:** rust-analyzer powerful but unstable with concurrency

**Settings:**
```yaml
language_servers:
  rust:
    parallel_execution:
      enabled: false  # CRITICAL: Disable for stability
    cache:
      lru:
        max_raw_symbols_entries: 800
        max_raw_symbols_memory_mb: 500  # High memory usage
```

**Tips:** Use cargo check caching, exclude target/, DO NOT enable parallel execution

**Performance:** Symbol tree (1000 files): 30-50s (sequential), Cache hit rate: >65%

---

### C/C++

**Characteristics:** clangd fast and stable, handles concurrency well

**Settings:**
```yaml
language_servers:
  cpp:
    parallel_execution:
      max_workers: 12
    cache:
      lru:
        max_raw_symbols_entries: 1500
        max_raw_symbols_memory_mb: 300
    server_config:
      compile_commands_path: "build/compile_commands.json"
      background_index: true
```

**Tips:** Generate compile_commands.json, use precompiled headers

**Performance:** Symbol tree (1000 files): 15-25s, Cache hit rate: >75%

---

## Cache Optimization

### Cache Layers

1. **Raw LSP Symbols** (1000 entries, 200 MB) - Direct server responses
2. **Processed Symbols** (500 entries, 100 MB) - Murena Symbol objects
3. **Full Symbol Trees** (100 entries, 50 MB) - Complete directory trees

### Tuning by Memory

**Memory-Constrained (<8 GB RAM):**
```yaml
cache:
  lru:
    max_raw_symbols_memory_mb: 100
    max_document_symbols_memory_mb: 50
    max_symbol_tree_memory_mb: 25
```

**High-Memory (>32 GB RAM):**
```yaml
cache:
  lru:
    max_raw_symbols_memory_mb: 500
    max_document_symbols_memory_mb: 250
    max_symbol_tree_memory_mb: 150
```

### Hit Rate Analysis

**Check hit rates:**
```python
stats = ls._raw_document_symbols_cache.stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")
```

**Target hit rates:**
- >85%: Excellent (optimal cache size)
- 70-85%: Good (consider increasing)
- <70%: Poor (increase cache or reduce working set)

---

## Parallel Execution Tuning

### Optimal Worker Count

**Formula:**
```
max_workers = min(
    2 × CPU_cores,
    LSP_stability_limit,
    memory_limit / avg_task_memory
)
```

**Examples:**

8-core system, stable LSP (TypeScript):
```yaml
parallel_execution:
  max_workers: 15  # 2 × 8 = 16, rounded
```

8-core system, unstable LSP (Rust):
```yaml
parallel_execution:
  max_workers: 1  # Stability limit
```

Memory-constrained (4 GB RAM):
```yaml
parallel_execution:
  max_workers: 5  # Avoid memory pressure
```

### Measuring Effectiveness

**Enable logging:**
```python
import logging
logging.getLogger("murena.async_task_executor").setLevel(logging.DEBUG)
```

**Check logs:**
```
INFO: Executing 10 tools in 3 waves
DEBUG: Wave 1/3: Executing 5 tools in parallel (0.5s)
DEBUG: Wave 2/3: Executing 3 tools in parallel (0.3s)
DEBUG: Wave 3/3: Executing 2 tools in parallel (0.2s)
INFO: Total: 1.0s (vs 2.5s sequential) = 2.5× speedup
```

**Metrics:**
- Wave efficiency: >70% of tools in first wave = good
- Speedup factor: Close to number of parallel tools = optimal
- Dependency depth: Fewer waves = better

---

## Token Optimization

### Context Mode Selection

| Task | Mode | Tokens/Ref | Use Case |
|------|------|------------|----------|
| Symbol search | `none` | 50 | Finding usage locations |
| Code review | `full` | 150 | Understanding patterns |
| Debugging | `line_only` | 75 | Tracking execution |
| Refactoring | `full` | 150 | Ensuring compatibility |

**Per-call override:**
```python
# Minimal tokens for search
refs = find_referencing_symbols(..., context_mode="none")

# Full context for review
refs = find_referencing_symbols(..., context_mode="full")
```

### Output Limiting Strategy

**Hierarchical approach:**

1. **Overview (minimal tokens):**
   ```python
   overview = find_symbol("MyClass", depth=1, include_body=False)
   # Tokens: ~1,000
   ```

2. **Selective deep dive:**
   ```python
   for method in overview.children:
       if method.name == "critical_method":
           body = find_symbol(f"MyClass/{method.name}", include_body=True)
   # Tokens: ~2,000 (vs 20,000 for full class)
   ```

---

## Benchmarking

### Run Performance Suite

```bash
uv run benchmarks/performance_suite.py --compare-baseline
```

**Output:**
```
=== Performance Benchmark Results ===

Symbol Tree (500 files):
  Baseline: 82.3s
  Current:  12.1s
  Speedup:  6.8×  ✓

Multi-file Read (50 files):
  Baseline: 10.5s
  Current:  2.3s
  Speedup:  4.6×  ✓

All benchmarks PASSED ✓
```

### Custom Benchmarks

```python
import time
from murena.agent import MurenaAgent

# Benchmark parallel vs sequential
start = time.time()
results = agent.execute_tools_parallel(
    tool_names=["find_symbol"] * 10,
    tool_params=[{"name_path": f"Class{i}"} for i in range(10)]
)
parallel_time = time.time() - start

# Compare with sequential
start = time.time()
for i in range(10):
    tool = agent.get_tool_by_name("find_symbol")
    tool.apply_ex(name_path=f"Class{i}")
sequential_time = time.time() - start

print(f"Speedup: {sequential_time/parallel_time:.1f}×")
```

### Performance Targets

| Operation | Target | Good | Excellent |
|-----------|--------|------|-----------|
| Symbol tree (500 files) | <15s | <12s | <10s |
| Multi-file read (50 files) | <3s | <2.5s | <2s |
| Cache save | <5ms | <2ms | <1ms |
| Parallel speedup (10 tools) | >3× | >4× | >5× |
| Memory usage | <500 MB | <400 MB | <300 MB |
| Cache hit rate | >75% | >80% | >85% |

---

## Troubleshooting

### Slow Symbol Tree

**Diagnosis:**
```bash
# Enable profiling
uv run python -m cProfile -o profile.stats murena-mcp-server
```

**Solutions:**
1. Enable parallel execution
2. Increase cache sizes
3. Exclude large directories
4. Use SSD storage

### High Memory Usage

**Diagnosis:**
```python
for ls in ls_manager.iter_language_servers():
    stats = ls._raw_document_symbols_cache.stats()
    print(f"{ls.language}: {stats['memory_mb']:.1f} MB")
```

**Solutions:**
1. Reduce LRU limits
2. Clear caches: `rm -rf ~/.murena/cache/*`
3. Exclude large directories

### Poor Cache Hit Rates

**Diagnosis:**
```python
stats = cache.stats()
if stats['entries'] >= stats['max_entries']:
    print("Cache full - increase max_entries")
```

**Solutions:**
1. Increase cache entry limits
2. Increase memory limits
3. Reduce working set size

### Parallel Execution Not Working

**Diagnosis:**
```python
from murena.tool_dependency_analyzer import ToolDependencyAnalyzer

graph = analyzer.analyze(tool_calls)
waves = graph.get_execution_waves()
print(f"Waves: {waves}")
```

**Solutions:**
1. Operate on different files
2. Use batch operations
3. Check language-specific settings

---

## Performance Checklist

**Before deployment:**
- [ ] Set appropriate cache sizes
- [ ] Configure language-specific max_workers
- [ ] Enable async cache persistence
- [ ] Choose optimal context modes
- [ ] Exclude unnecessary directories
- [ ] Run benchmarks
- [ ] Monitor memory usage
- [ ] Check cache hit rates (>80%)
- [ ] Test parallel execution
- [ ] Review LSP stability

**After deployment:**
- [ ] Monitor logs for errors
- [ ] Track performance metrics
- [ ] Adjust worker counts
- [ ] Fine-tune cache sizes
- [ ] Optimize token modes

---

## Useful Commands

```bash
# Benchmark
uv run benchmarks/performance_suite.py

# Cache stats
murena show-cache-stats

# Monitor memory
watch -n 1 'ps aux | grep murena-mcp-server | awk "{print \$6/1024\" MB\"}"'

# LSP resources
ps aux | grep -E "(clangd|pyright|typescript)" | awk '{print $11, $6/1024"MB"}'
```

---

**Last Updated:** 2025-01-24
