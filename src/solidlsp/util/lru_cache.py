"""
Thread-safe LRU cache with memory and entry limits.

This module provides an LRU (Least Recently Used) cache implementation that
bounds both the number of entries and total memory consumption.
"""

import logging
import sys
import threading
from collections import OrderedDict
from typing import Any, Generic, TypeVar

log = logging.getLogger(__name__)

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """
    Thread-safe LRU cache with configurable entry and memory limits.

    Features:
    - Automatic eviction of least recently used items when limits are exceeded
    - Memory usage tracking (approximate, based on sys.getsizeof)
    - Thread-safe operations using a reentrant lock
    - Efficient O(1) get/put operations

    Example:
        >>> cache = LRUCache(max_entries=1000, max_memory_mb=200)
        >>> cache.put("key1", large_object)
        >>> value = cache.get("key1")
        >>> cache.clear()

    """

    def __init__(self, max_entries: int = 1000, max_memory_mb: int = 200):
        """
        Initialize the LRU cache.

        Args:
            max_entries: Maximum number of entries before eviction starts
            max_memory_mb: Maximum memory usage in MB before eviction starts

        """
        self._max_entries = max_entries
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._memory_usage = 0
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

        log.debug(f"LRUCache initialized: max_entries={max_entries}, max_memory_mb={max_memory_mb}")

    def get(self, key: K) -> V | None:
        """
        Get a value from the cache, moving it to the end (most recently used).

        Args:
            key: The key to look up

        Returns:
            The cached value if found, None otherwise

        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

    def put(self, key: K, value: V) -> None:
        """
        Put a value in the cache, evicting LRU items if necessary.

        Args:
            key: The key to store
            value: The value to cache

        """
        with self._lock:
            # If key exists, remove it first to update size
            if key in self._cache:
                old_value = self._cache.pop(key)
                self._memory_usage -= sys.getsizeof(old_value)

            # Add new value
            self._cache[key] = value
            self._memory_usage += sys.getsizeof(value)

            # Move to end (most recently used)
            self._cache.move_to_end(key)

            # Evict if necessary
            self._evict_if_necessary()

    def _evict_if_necessary(self) -> None:
        """
        Evict least recently used items if limits are exceeded.

        This method assumes the lock is already held.
        """
        evicted_count = 0

        # Evict until both limits are satisfied
        while len(self._cache) > 0 and (len(self._cache) > self._max_entries or self._memory_usage > self._max_memory_bytes):
            # Pop the first item (least recently used)
            key, value = self._cache.popitem(last=False)
            self._memory_usage -= sys.getsizeof(value)
            evicted_count += 1

        if evicted_count > 0:
            log.debug(
                f"LRU evicted {evicted_count} items. "
                f"New size: {len(self._cache)} entries, "
                f"{self._memory_usage / (1024 * 1024):.2f} MB"
            )

    def contains(self, key: K) -> bool:
        """
        Check if a key exists in the cache without updating access order.

        Args:
            key: The key to check

        Returns:
            True if the key exists, False otherwise

        """
        with self._lock:
            return key in self._cache

    def remove(self, key: K) -> bool:
        """
        Remove a key from the cache.

        Args:
            key: The key to remove

        Returns:
            True if the key was found and removed, False otherwise

        """
        with self._lock:
            if key in self._cache:
                value = self._cache.pop(key)
                self._memory_usage -= sys.getsizeof(value)
                return True
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self._lock:
            self._cache.clear()
            self._memory_usage = 0
            log.debug("LRU cache cleared")

    def size(self) -> int:
        """
        Get the current number of entries in the cache.

        Returns:
            Number of cached entries

        """
        with self._lock:
            return len(self._cache)

    def memory_usage_mb(self) -> float:
        """
        Get the current memory usage in MB.

        Returns:
            Approximate memory usage in megabytes

        """
        with self._lock:
            return self._memory_usage / (1024 * 1024)

    def hit_rate(self) -> float:
        """
        Calculate the cache hit rate.

        Returns:
            Hit rate as a float between 0 and 1, or 0 if no requests yet

        """
        with self._lock:
            total = self._hits + self._misses
            if total == 0:
                return 0.0
            return self._hits / total

    def stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats

        """
        with self._lock:
            return {
                "entries": len(self._cache),
                "memory_mb": self.memory_usage_mb(),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self.hit_rate(),
                "max_entries": self._max_entries,
                "max_memory_mb": self._max_memory_bytes / (1024 * 1024),
            }

    def to_dict(self) -> dict[K, V]:
        """
        Export all cache entries as a dictionary.

        Useful for persistence/serialization.

        Returns:
            Dictionary containing all cached entries

        """
        with self._lock:
            return dict(self._cache)

    def load_from_dict(self, data: dict[K, V]) -> None:
        """
        Load multiple entries from a dictionary.

        Useful for restoring from persistence.
        Clears existing cache before loading.

        Args:
            data: Dictionary of entries to load

        """
        with self._lock:
            self.clear()
            for key, value in data.items():
                self.put(key, value)

    def __len__(self) -> int:
        """Get the number of entries in the cache."""
        return self.size()

    def __contains__(self, key: K) -> bool:
        """Check if a key exists in the cache."""
        return self.contains(key)
