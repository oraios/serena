"""Tests for LRUCache."""

import pytest

from solidlsp.util.lru_cache import LRUCache


class TestLRUCache:
    """Test the LRU cache implementation."""

    def test_basic_operations(self):
        """Test basic get/put operations."""
        cache = LRUCache[str, int](max_entries=3, max_memory_mb=10)

        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)

        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") is None

    def test_lru_eviction_by_count(self):
        """Test that LRU eviction works based on entry count."""
        cache = LRUCache[str, str](max_entries=2, max_memory_mb=1000)

        cache.put("a", "value_a")
        cache.put("b", "value_b")
        cache.put("c", "value_c")  # Should evict "a"

        assert cache.get("a") is None  # Evicted
        assert cache.get("b") == "value_b"
        assert cache.get("c") == "value_c"

    def test_lru_order_maintained(self):
        """Test that accessing an item moves it to most recent."""
        cache = LRUCache[str, str](max_entries=2, max_memory_mb=1000)

        cache.put("a", "value_a")
        cache.put("b", "value_b")

        # Access "a" to make it most recent
        assert cache.get("a") == "value_a"

        # Add "c", should evict "b" (least recently used)
        cache.put("c", "value_c")

        assert cache.get("a") == "value_a"
        assert cache.get("b") is None  # Evicted
        assert cache.get("c") == "value_c"

    def test_update_existing_key(self):
        """Test updating an existing key."""
        cache = LRUCache[str, int](max_entries=3, max_memory_mb=10)

        cache.put("a", 1)
        cache.put("a", 2)  # Update

        assert cache.get("a") == 2
        assert cache.size() == 1

    def test_contains(self):
        """Test the contains method."""
        cache = LRUCache[str, int](max_entries=3, max_memory_mb=10)

        cache.put("a", 1)

        assert cache.contains("a")
        assert not cache.contains("b")

    def test_remove(self):
        """Test removing entries."""
        cache = LRUCache[str, int](max_entries=3, max_memory_mb=10)

        cache.put("a", 1)
        cache.put("b", 2)

        assert cache.remove("a")
        assert not cache.remove("c")  # Doesn't exist

        assert cache.get("a") is None
        assert cache.get("b") == 2

    def test_clear(self):
        """Test clearing the cache."""
        cache = LRUCache[str, int](max_entries=3, max_memory_mb=10)

        cache.put("a", 1)
        cache.put("b", 2)

        cache.clear()

        assert cache.size() == 0
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_hit_rate(self):
        """Test cache hit rate tracking."""
        cache = LRUCache[str, int](max_entries=3, max_memory_mb=10)

        cache.put("a", 1)

        cache.get("a")  # Hit
        cache.get("b")  # Miss
        cache.get("a")  # Hit

        assert cache.hit_rate() == pytest.approx(2 / 3)

    def test_stats(self):
        """Test stats collection."""
        cache = LRUCache[str, int](max_entries=100, max_memory_mb=50)

        cache.put("a", 1)
        cache.get("a")  # Hit
        cache.get("b")  # Miss

        stats = cache.stats()

        assert stats["entries"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["max_entries"] == 100
        assert stats["max_memory_mb"] == 50

    def test_to_dict_and_load_from_dict(self):
        """Test exporting and loading cache."""
        cache = LRUCache[str, int](max_entries=10, max_memory_mb=10)

        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)

        # Export
        data = cache.to_dict()
        assert data == {"a": 1, "b": 2, "c": 3}

        # Load into new cache
        new_cache = LRUCache[str, int](max_entries=10, max_memory_mb=10)
        new_cache.load_from_dict(data)

        assert new_cache.get("a") == 1
        assert new_cache.get("b") == 2
        assert new_cache.get("c") == 3
