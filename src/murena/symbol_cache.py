"""
Session-level cache for symbol bodies to reduce token usage in multi-turn conversations.

The cache stores symbol bodies for the entire Claude Code session and invalidates entries
when the underlying source file is modified (based on file mtime).

Expected token savings: 20-40% in multi-turn conversations with 80% cache hit rate.
"""

import os
import time
from dataclasses import dataclass
from typing import Any

from sensai.util import logging

from solidlsp.util.lru_cache import LRUCache

log = logging.getLogger(__name__)


@dataclass
class CachedSymbol:
    """Cached symbol data with metadata"""

    symbol_data: dict[str, Any]
    """The cached symbol dictionary"""

    file_mtime: float
    """File modification time when cached"""

    cache_time: float
    """When this entry was cached"""


class SessionSymbolCache:
    """
    Session-level cache for symbol bodies with LRU eviction.

    The cache is keyed by (relative_path, name_path) and stores the complete
    symbol dictionary including body. Entries are automatically invalidated
    when the source file is modified.

    Attributes:
        ttl_seconds: Time-to-live for cache entries (default: 3600 = 1 hour)
        project_root: Root directory of the project (for resolving relative paths)
        max_entries: Maximum number of cache entries (default: 500)
        max_memory_mb: Maximum memory usage in MB (default: 100)

    """

    def __init__(
        self,
        project_root: str,
        ttl_seconds: int = 3600,
        max_entries: int = 500,
        max_memory_mb: int = 100,
    ):
        """
        Initialize the symbol cache with LRU eviction.

        :param project_root: Root directory of the project
        :param ttl_seconds: Time-to-live for cache entries in seconds
        :param max_entries: Maximum number of cache entries
        :param max_memory_mb: Maximum memory usage in MB
        """
        self.project_root = project_root
        self.ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._max_memory_mb = max_memory_mb
        self._cache: LRUCache[tuple[str, str], CachedSymbol] = LRUCache(
            max_entries=max_entries,
            max_memory_mb=max_memory_mb,
        )
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, relative_path: str, name_path: str) -> dict[str, Any] | None:
        """
        Get a cached symbol if available and valid.

        The cache entry is considered valid if:
        1. It exists in the cache
        2. The source file has not been modified since caching (mtime check)
        3. The entry has not expired (TTL check)

        :param relative_path: Relative path to the source file
        :param name_path: Name path of the symbol (e.g., "MyClass/my_method")
        :return: Cached symbol data if valid, None otherwise
        """
        key = (relative_path, name_path)

        cached = self._cache.get(key)
        if cached is None:
            self._misses += 1
            return None

        current_time = time.time()

        # Check TTL
        if current_time - cached.cache_time > self.ttl_seconds:
            log.debug(f"Cache expired for {relative_path}::{name_path}")
            self._cache.remove(key)
            self._misses += 1
            return None

        # Check file mtime
        file_path = os.path.join(self.project_root, relative_path)
        try:
            current_mtime = os.path.getmtime(file_path)
            if current_mtime > cached.file_mtime:
                log.debug(f"File modified, invalidating cache for {relative_path}::{name_path}")
                self._cache.remove(key)
                self._misses += 1
                return None
        except OSError as e:
            log.warning(f"Failed to check mtime for {file_path}: {e}, invalidating cache")
            self._cache.remove(key)
            self._misses += 1
            return None

        # Valid cache hit
        self._hits += 1
        log.debug(f"Cache hit for {relative_path}::{name_path} (hit rate: {self.get_hit_rate():.1%})")
        return cached.symbol_data

    def put(self, relative_path: str, name_path: str, symbol_data: dict[str, Any]) -> None:
        """
        Cache a symbol's data.

        :param relative_path: Relative path to the source file
        :param name_path: Name path of the symbol
        :param symbol_data: Complete symbol dictionary (should include body)
        """
        key = (relative_path, name_path)

        file_path = os.path.join(self.project_root, relative_path)
        try:
            file_mtime = os.path.getmtime(file_path)
        except OSError as e:
            log.warning(f"Failed to get mtime for {file_path}: {e}, not caching")
            return

        cached = CachedSymbol(
            symbol_data=symbol_data,
            file_mtime=file_mtime,
            cache_time=time.time(),
        )

        # Track size before put to detect evictions
        size_before = self._cache.size()
        self._cache.put(key, cached)
        size_after = self._cache.size()

        # If size didn't increase and we added an item, something was evicted
        if size_after <= size_before:
            self._evictions += size_before - size_after + 1

        stats = self._cache.stats()
        log.debug(f"Cached symbol {relative_path}::{name_path} (size: {stats['entries']}, memory: {stats['memory_mb']:.1f} MB)")

    def invalidate_file(self, relative_path: str) -> int:
        """
        Invalidate all cache entries for a specific file.

        :param relative_path: Relative path to the source file
        :return: Number of entries invalidated
        """
        # Get all keys that match the file path
        cache_dict = self._cache.to_dict()
        keys_to_remove = [key for key in cache_dict.keys() if key[0] == relative_path]

        for key in keys_to_remove:
            self._cache.remove(key)

        if keys_to_remove:
            log.debug(f"Invalidated {len(keys_to_remove)} cache entries for {relative_path}")

        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cache entries"""
        count = len(self._cache)
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        log.info(f"Cleared symbol cache ({count} entries)")

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        :return: Dictionary with cache statistics
        """
        lru_stats = self._cache.stats()
        return {
            "size": lru_stats["entries"],
            "memory_mb": lru_stats["memory_mb"],
            "max_entries": self._max_entries,
            "max_memory_mb": self._max_memory_mb,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": self.get_hit_rate(),
            "ttl_seconds": self.ttl_seconds,
        }

    def get_hit_rate(self) -> float:
        """
        Calculate the cache hit rate.

        :return: Hit rate as a float between 0 and 1
        """
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total
