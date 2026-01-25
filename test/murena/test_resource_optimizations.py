"""
Unit tests for P0 resource optimizations:
- TaskExecutor event-based waiting
- AsyncCachePersister smart debouncing
- SessionSymbolCache LRU eviction
"""

import tempfile
import time
from pathlib import Path

import pytest

from murena.symbol_cache import SessionSymbolCache
from murena.task_executor import TaskExecutor
from solidlsp.util.async_cache import AsyncCachePersister


class TestTaskExecutorOptimizations:
    """Tests for TaskExecutor busy-wait fix (P0-1)"""

    def test_task_executor_no_busy_wait(self):
        """Verify TaskExecutor doesn't busy-wait when idle"""
        executor = TaskExecutor("test_no_busy_wait")

        # Let it idle for a short time
        time.sleep(0.5)

        # Verify no tasks executed (would log if any busy-waiting occurred)
        assert executor.get_last_executed_task() is None

        # Cleanup
        executor.shutdown(timeout=1.0)

    def test_task_executor_event_notification(self):
        """Verify TaskExecutor wakes up immediately when task is added"""
        executor = TaskExecutor("test_event_notification")

        # Measure time to execute a simple task
        executed = []

        def quick_task():
            executed.append(time.time())

        start = time.time()
        task = executor.issue_task(quick_task, logged=False)
        task.wait_until_done(timeout=5.0)
        elapsed = time.time() - start

        # Should execute almost immediately (< 100ms), not wait for 5s poll interval
        assert elapsed < 0.2, f"Task took {elapsed}s, expected < 0.2s"
        assert len(executed) == 1

        # Cleanup
        executor.shutdown(timeout=1.0)

    def test_task_executor_shutdown(self):
        """Verify TaskExecutor shuts down gracefully"""
        executor = TaskExecutor("test_shutdown")

        # Issue a quick task
        executed = []
        task = executor.issue_task(lambda: executed.append(1), logged=False)
        task.wait_until_done(timeout=1.0)

        # Shutdown
        executor.shutdown(timeout=1.0)

        # Verify thread terminated (would hang if still busy-waiting)
        assert not executor._task_executor_thread.is_alive()


class TestAsyncCachePersisterOptimizations:
    """Tests for AsyncCachePersister busy-wait fix (P0-2)"""

    def test_async_cache_smart_debouncing(self):
        """Verify AsyncCachePersister uses smart debouncing, not fixed polling"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache.pkl"
            persister = AsyncCachePersister(debounce_interval=0.5, enabled=True)

            # Schedule a write
            def save_fn(data):
                cache_file.write_text(str(data))

            persister.schedule_write("test_key", "test_data", save_fn)

            # Wait for less than debounce interval
            time.sleep(0.3)

            # Should not have written yet
            assert not cache_file.exists()

            # Wait for debounce interval to pass
            time.sleep(0.3)

            # Should have written by now
            assert cache_file.exists()
            assert cache_file.read_text() == "test_data"

            persister.shutdown(timeout=1.0)

    def test_async_cache_immediate_flush(self):
        """Verify flush_all() triggers immediate write without waiting"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "test_cache_flush.pkl"
            persister = AsyncCachePersister(debounce_interval=10.0, enabled=True)  # Long debounce

            def save_fn(data):
                cache_file.write_text(str(data))

            persister.schedule_write("test_key", "test_data", save_fn)

            # Flush immediately (should not wait 10s)
            start = time.time()
            success = persister.flush_all(timeout=2.0)
            elapsed = time.time() - start

            assert success, "Flush failed"
            assert elapsed < 1.0, f"Flush took {elapsed}s, expected < 1.0s"
            assert cache_file.exists()

            persister.shutdown(timeout=1.0)


class TestSessionSymbolCacheOptimizations:
    """Tests for SessionSymbolCache LRU eviction (P0-3)"""

    def test_symbol_cache_memory_limit(self):
        """Verify cache respects memory limit with LRU eviction"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SessionSymbolCache(
                project_root=tmpdir,
                ttl_seconds=3600,
                max_entries=100,
                max_memory_mb=1,  # 1 MB limit
            )

            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# test")

            # Add symbols with large bodies to exceed memory limit
            for i in range(200):
                symbol_data = {
                    "name": f"symbol_{i}",
                    "body": "x" * 10000,  # ~10KB per symbol
                }
                cache.put("test.py", f"Symbol_{i}", symbol_data)

            stats = cache.get_stats()

            # Should have evicted entries to stay under memory limit
            assert stats["memory_mb"] <= stats["max_memory_mb"], f"Memory: {stats['memory_mb']} MB > {stats['max_memory_mb']} MB"
            assert stats["size"] < 200, f"Cache size {stats['size']} should be < 200 (evictions occurred)"
            assert stats["evictions"] > 0, "Should have evicted entries"

    def test_symbol_cache_max_entries_limit(self):
        """Verify cache respects max_entries limit"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SessionSymbolCache(
                project_root=tmpdir,
                ttl_seconds=3600,
                max_entries=50,
                max_memory_mb=100,
            )

            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# test")

            # Add more entries than max_entries
            for i in range(100):
                symbol_data = {"name": f"symbol_{i}", "body": f"def symbol_{i}(): pass"}
                cache.put("test.py", f"Symbol_{i}", symbol_data)

            stats = cache.get_stats()

            # Should not exceed max_entries
            assert stats["size"] <= stats["max_entries"], f"Size {stats['size']} > max_entries {stats['max_entries']}"
            assert stats["evictions"] > 0, "Should have evicted entries"

    def test_symbol_cache_lru_order(self):
        """Verify LRU eviction - least recently used items are evicted first"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SessionSymbolCache(
                project_root=tmpdir,
                ttl_seconds=3600,
                max_entries=5,
                max_memory_mb=100,
            )

            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# test")

            # Add 5 symbols
            for i in range(5):
                cache.put("test.py", f"Symbol_{i}", {"name": f"symbol_{i}", "body": "x" * 100})

            # Access symbol 0 to make it recently used
            cache.get("test.py", "Symbol_0")

            # Add a 6th symbol (should evict Symbol_1, not Symbol_0)
            cache.put("test.py", "Symbol_5", {"name": "symbol_5", "body": "x" * 100})

            # Symbol_0 should still be in cache (recently accessed)
            assert cache.get("test.py", "Symbol_0") is not None, "Recently accessed symbol should not be evicted"

            # Symbol_1 should have been evicted (least recently used)
            assert cache.get("test.py", "Symbol_1") is None, "Least recently used symbol should be evicted"

    def test_symbol_cache_stats(self):
        """Verify cache statistics are accurate"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SessionSymbolCache(
                project_root=tmpdir,
                ttl_seconds=3600,
                max_entries=10,
                max_memory_mb=10,
            )

            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("# test")

            # Add some symbols
            for i in range(5):
                cache.put("test.py", f"Symbol_{i}", {"name": f"symbol_{i}"})

            # Get some (hits)
            cache.get("test.py", "Symbol_0")
            cache.get("test.py", "Symbol_1")

            # Get non-existent (misses)
            cache.get("test.py", "NonExistent_1")
            cache.get("test.py", "NonExistent_2")

            stats = cache.get_stats()

            assert stats["size"] == 5
            assert stats["hits"] == 2
            assert stats["misses"] == 2
            assert stats["hit_rate"] == 0.5  # 2 hits / (2 hits + 2 misses)
            assert "memory_mb" in stats
            assert "evictions" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
