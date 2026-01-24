# Performance Benchmarks

This directory contains performance benchmarks for Murena's optimization layer.

## Running Benchmarks

### Quick Start

```bash
# Run all benchmarks
uv run python benchmarks/performance_suite.py

# Compare against baseline (pre-optimization)
uv run python benchmarks/performance_suite.py --compare-baseline
```

### What Gets Tested

1. **LRU Cache Performance**
   - Put/Get operations speed
   - Memory bounds enforcement
   - Hit rate tracking

2. **Async Cache Persistence**
   - Schedule write latency (<1ms target)
   - Speedup vs synchronous saves (300× target)

3. **Dependency Analysis**
   - Tool dependency detection speed
   - Wave generation accuracy
   - Independent vs sequential detection

4. **Parallel Execution**
   - Parallel vs sequential speedup (2-5× target)
   - Wave-based execution correctness

5. **Memory Usage**
   - LRU eviction correctness
   - Memory bounds (<500 MB target)
   - Entry limit enforcement

## Performance Targets

| Metric | Target | Status |
|--------|--------|--------|
| Cache save latency | <5ms | ✓ PASS (0.00ms) |
| Parallel speedup (3 tools) | >2× | ✓ PASS (3.0×) |
| Memory usage | <500 MB | ✓ PASS |
| Cache hit rate | >75% | ✓ PASS (100%) |

## Interpreting Results

### Success Criteria

All benchmarks should display `✓ PASS`. Example:

```
✓ Cache Save (async schedule)
  Current: 0.000s
  Target:  0.005s
  Status:  PASS  Speedup: 1006633.0×
```

### Failure Investigation

If a benchmark fails (shows `✗ FAIL`):

1. **Cache Save Failure** - Check if async persistence is enabled
2. **Parallel Execution Failure** - Verify max_workers configuration
3. **Memory Failure** - Check LRU limits in configuration

### Baseline Comparison

Use `--compare-baseline` to see improvements over pre-optimization code:

```
Speedup: 6.8×  # 6.8× faster than baseline
```

## Adding New Benchmarks

To add a new benchmark:

1. Create a method in `PerformanceBenchmarkSuite` class
2. Add target value to `TARGETS` dict
3. Add baseline value to `BASELINE` dict (optional)
4. Call method in `run_all()`

Example:

```python
def benchmark_new_feature(self) -> None:
    """Benchmark new optimization feature."""
    print("\n=== Benchmarking New Feature ===")

    start = time.time()
    # ... run benchmark code ...
    elapsed = time.time() - start

    self.add_result(
        "New Feature",
        elapsed,
        TARGETS["new_feature"],
        BASELINE.get("new_feature")
    )
```

## Continuous Integration

Add to CI pipeline:

```yaml
- name: Run performance benchmarks
  run: uv run python benchmarks/performance_suite.py
```

## Related Documentation

- **Architecture**: `docs/ARCHITECTURE.md`
- **Performance Tuning**: `docs/PERFORMANCE_TUNING.md`
- **Migration Guide**: `docs/MIGRATION_GUIDE.md`

---

**Last Updated:** 2025-01-24
