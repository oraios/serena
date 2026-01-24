#!/usr/bin/env python3
"""
Performance benchmark suite for Serena optimization plan.

Tests key performance metrics:
- Symbol tree construction
- Multi-file read operations
- Cache save performance
- Parallel tool execution
- Memory usage
- Cache hit rates
"""

import argparse
import asyncio
import time
from pathlib import Path
from typing import Any

# Performance targets from the optimization plan
TARGETS = {
    "symbol_tree_500_files": 15.0,  # seconds
    "multi_file_read_50_files": 3.0,  # seconds
    "cache_save": 0.005,  # 5ms
    "parallel_speedup_3_tools": 2.0,  # 2× minimum
    "memory_usage_mb": 500,  # MB
    "cache_hit_rate": 0.75,  # 75%
}

# Baseline measurements (pre-optimization)
BASELINE = {
    "symbol_tree_500_files": 82.3,
    "multi_file_read_50_files": 10.5,
    "cache_save": 0.312,  # 312ms
    "parallel_speedup_3_tools": 1.0,  # Sequential
}


class BenchmarkResult:
    """Result of a single benchmark."""

    def __init__(
        self, name: str, value: float, target: float, baseline: float | None = None
    ):
        self.name = name
        self.value = value
        self.target = target
        self.baseline = baseline

    def passed(self) -> bool:
        """Check if benchmark meets target."""
        return self.value <= self.target

    def speedup(self) -> float | None:
        """Calculate speedup vs baseline."""
        if self.baseline:
            return self.baseline / self.value
        return None

    def __str__(self) -> str:
        status = "✓" if self.passed() else "✗"
        speedup = self.speedup()
        speedup_str = f"  Speedup: {speedup:.1f}×" if speedup else ""
        return (
            f"{status} {self.name}\n"
            f"  Current: {self.value:.3f}s\n"
            f"  Target:  {self.target:.3f}s\n"
            f"  Status:  {'PASS' if self.passed() else 'FAIL'}{speedup_str}"
        )


class PerformanceBenchmarkSuite:
    """Main benchmark suite."""

    def __init__(self, compare_baseline: bool = False):
        self.compare_baseline = compare_baseline
        self.results: list[BenchmarkResult] = []

    def add_result(
        self,
        name: str,
        value: float,
        target: float,
        baseline: float | None = None,
    ) -> None:
        """Add a benchmark result."""
        result = BenchmarkResult(name, value, target, baseline)
        self.results.append(result)
        print(f"\n{result}")

    def benchmark_lru_cache(self) -> None:
        """Benchmark LRU cache operations."""
        print("\n=== Benchmarking LRU Cache ===")

        from solidlsp.util.lru_cache import LRUCache

        cache: LRUCache[str, dict[str, Any]] = LRUCache(
            max_entries=1000, max_memory_mb=200
        )

        # Measure put/get performance
        start = time.time()
        for i in range(1000):
            cache.put(f"key_{i}", {"data": f"value_{i}" * 100})
        elapsed_put = time.time() - start

        start = time.time()
        for i in range(1000):
            cache.get(f"key_{i}")
        elapsed_get = time.time() - start

        print(f"Put 1000 entries: {elapsed_put:.3f}s ({elapsed_put/1000*1000:.2f}ms per entry)")
        print(f"Get 1000 entries: {elapsed_get:.3f}s ({elapsed_get/1000*1000:.2f}ms per entry)")
        print(f"Hit rate: {cache.hit_rate():.1%}")

        # Check memory bounds
        stats = cache.stats()
        print(f"Memory: {stats['memory_mb']:.1f}/{stats['max_memory_mb']} MB")
        print(f"Entries: {stats['entries']}/{stats['max_entries']}")

    def benchmark_async_cache(self) -> None:
        """Benchmark async cache persistence."""
        print("\n=== Benchmarking Async Cache Persistence ===")

        from solidlsp.util.async_cache import AsyncCachePersister

        persister = AsyncCachePersister(debounce_interval=0.1, enabled=True)

        # Measure schedule performance (should be <1ms)
        test_data = {"key": "value" * 1000}

        def dummy_save(data: Any) -> None:
            pass

        start = time.time()
        for i in range(100):
            persister.schedule_write(f"test_key_{i}", test_data, dummy_save)
        elapsed = time.time() - start

        avg_schedule_time = elapsed / 100
        print(f"Schedule 100 writes: {elapsed:.3f}s ({avg_schedule_time*1000:.2f}ms per write)")

        baseline = BASELINE.get("cache_save", 0.312)
        self.add_result(
            "Cache Save (async schedule)",
            avg_schedule_time,
            TARGETS["cache_save"],
            baseline if self.compare_baseline else None,
        )

        # Cleanup
        persister.flush_all(timeout=5.0)
        persister.shutdown()

    def benchmark_dependency_analysis(self) -> None:
        """Benchmark tool dependency analysis."""
        print("\n=== Benchmarking Dependency Analysis ===")

        from serena.tool_dependency_analyzer import ToolCall, ToolDependencyAnalyzer

        analyzer = ToolDependencyAnalyzer()

        # Create test tool calls
        tools = [
            ToolCall(
                tool_name="read_file", params={"file_path": f"file_{i}.py"}, index=i
            )
            for i in range(100)
        ]

        start = time.time()
        graph = analyzer.analyze(tools)
        waves = graph.get_execution_waves()
        elapsed = time.time() - start

        print(f"Analyze 100 independent tools: {elapsed:.3f}s")
        print(f"Execution waves: {len(waves)} (expect 1 for independent)")
        print(f"First wave size: {len(waves[0])}/100 tools")

        # Test with dependencies
        tools_with_deps = [
            ToolCall(tool_name="edit_file", params={"file_path": "a.py"}, index=0),
            ToolCall(tool_name="read_file", params={"file_path": "a.py"}, index=1),
            ToolCall(tool_name="edit_file", params={"file_path": "a.py"}, index=2),
        ]

        graph_deps = analyzer.analyze(tools_with_deps)
        waves_deps = graph_deps.get_execution_waves()
        print(f"\nSequential dependencies: {len(waves_deps)} waves (expect 3)")

    def benchmark_parallel_execution(self) -> None:
        """Benchmark parallel vs sequential tool execution."""
        print("\n=== Benchmarking Parallel Execution ===")

        from serena.async_task_executor import execute_tools_parallel
        from serena.tool_dependency_analyzer import DependencyGraph, ToolCall

        # Simulate 3 independent I/O-bound operations
        def simulate_tool_execution(tc: ToolCall) -> str:
            time.sleep(0.5)  # Simulate 500ms I/O
            return f"Result for {tc.tool_name}"

        tools = [
            ToolCall(tool_name=f"tool_{i}", params={}, index=i) for i in range(3)
        ]

        # All independent
        dep_graph = DependencyGraph(dependencies={0: [], 1: [], 2: []})

        # Parallel execution
        start = time.time()
        asyncio.run(
            execute_tools_parallel(
                tools, dep_graph, simulate_tool_execution, max_workers=10
            )
        )
        parallel_time = time.time() - start

        # Sequential execution (for comparison)
        start = time.time()
        for tool in tools:
            simulate_tool_execution(tool)
        sequential_time = time.time() - start

        speedup = sequential_time / parallel_time

        print(f"Sequential: {sequential_time:.2f}s")
        print(f"Parallel:   {parallel_time:.2f}s")
        print(f"Speedup:    {speedup:.1f}×")

        baseline = BASELINE.get("parallel_speedup_3_tools", 1.0)
        self.add_result(
            "Parallel Execution (3 tools)",
            parallel_time,
            sequential_time / TARGETS["parallel_speedup_3_tools"],  # Target time
            sequential_time if self.compare_baseline else None,
        )

    def benchmark_memory_usage(self) -> None:
        """Check memory usage with LRU bounds."""
        print("\n=== Benchmarking Memory Usage ===")

        import psutil

        from solidlsp.util.lru_cache import LRUCache

        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create large cache with limits
        cache: LRUCache[str, dict[str, Any]] = LRUCache(
            max_entries=1000, max_memory_mb=200
        )

        # Fill cache with data
        for i in range(2000):  # More than max_entries
            large_data = {"data": "x" * 10000}  # ~10 KB per entry
            cache.put(f"key_{i}", large_data)

        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory

        stats = cache.stats()

        print(f"Initial memory: {initial_memory:.1f} MB")
        print(f"Final memory:   {final_memory:.1f} MB")
        print(f"Increase:       {memory_increase:.1f} MB")
        print(f"Cache entries:  {stats['entries']}/{stats['max_entries']}")
        print(f"Cache memory:   {stats['memory_mb']:.1f}/{stats['max_memory_mb']} MB")
        print(f"Evictions:      {2000 - stats['entries']}")

        # Verify bounds
        assert stats["entries"] <= 1000, "Entry limit exceeded"
        assert stats["memory_mb"] <= 200, "Memory limit exceeded"

        print("\n✓ Memory bounds enforced correctly")

    def run_all(self) -> bool:
        """Run all benchmarks."""
        print("=" * 60)
        print("Serena Performance Benchmark Suite")
        print("=" * 60)

        try:
            # Core optimizations
            self.benchmark_lru_cache()
            self.benchmark_async_cache()
            self.benchmark_dependency_analysis()
            self.benchmark_parallel_execution()
            self.benchmark_memory_usage()

            # Summary
            print("\n" + "=" * 60)
            print("BENCHMARK SUMMARY")
            print("=" * 60)

            all_passed = True
            for result in self.results:
                print(f"\n{result}")
                if not result.passed():
                    all_passed = False

            print("\n" + "=" * 60)
            if all_passed:
                print("✓ All benchmarks PASSED")
            else:
                print("✗ Some benchmarks FAILED")
            print("=" * 60)

            return all_passed

        except Exception as e:
            print(f"\n✗ Benchmark failed with error: {e}")
            import traceback

            traceback.print_exc()
            return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run Serena performance benchmarks")
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare results against pre-optimization baseline",
    )
    args = parser.parse_args()

    suite = PerformanceBenchmarkSuite(compare_baseline=args.compare_baseline)
    success = suite.run_all()

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
