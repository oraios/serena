"""
Asynchronous cache persistence with debouncing.

This module provides background cache writing to eliminate blocking I/O
during tool execution. Cache writes are debounced and executed in a
background thread.

Note: This module uses sensai.util.pickle for serialization, which is the
standard cache serialization mechanism used throughout the Serena codebase
for internal LSP cache data.
"""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sensai.util.pickle import dump_pickle, load_pickle

log = logging.getLogger(__name__)


class AsyncCachePersister:
    """
    Background cache writer with debouncing.

    Features:
    - Non-blocking cache write scheduling
    - Debouncing to batch multiple rapid writes
    - Background thread for I/O operations
    - Graceful shutdown with flush
    - Thread-safe operations

    Example:
        >>> persister = AsyncCachePersister(debounce_interval=5.0)
        >>> persister.schedule_write("cache_key", cache_data, save_function)
        >>> persister.flush_all(timeout=10.0)
        >>> persister.shutdown()

    """

    def __init__(self, debounce_interval: float = 5.0, enabled: bool = True):
        """
        Initialize the async cache persister.

        Args:
            debounce_interval: Minimum time (in seconds) between writes for the same key
            enabled: Whether async persistence is enabled (if False, writes synchronously)

        """
        self._debounce_interval = debounce_interval
        self._enabled = enabled
        self._pending_writes: dict[str, tuple[Any, Callable[[Any], None], float]] = {}
        self._lock = threading.RLock()
        self._shutdown_flag = threading.Event()
        self._flush_requested = threading.Event()
        self._worker_thread: threading.Thread | None = None

        if self._enabled:
            self._start_worker()

        log.debug(f"AsyncCachePersister initialized: debounce_interval={debounce_interval}s, enabled={enabled}")

    def _start_worker(self) -> None:
        """Start the background worker thread."""
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="AsyncCachePersister")
        self._worker_thread.start()
        log.debug("AsyncCachePersister worker thread started")

    def _worker_loop(self) -> None:
        """
        Background worker that periodically flushes pending writes.

        Runs until shutdown is requested or thread is interrupted.
        """
        try:
            while not self._shutdown_flag.is_set():
                # Sleep for a short interval, checking for shutdown
                self._shutdown_flag.wait(timeout=0.5)

                # Check if flush was requested
                if self._flush_requested.is_set():
                    self._execute_pending_writes(force=True)
                    self._flush_requested.clear()
                else:
                    # Execute writes whose debounce interval has elapsed
                    self._execute_pending_writes(force=False)

        except Exception as e:
            log.exception(f"AsyncCachePersister worker thread encountered an error: {e}")
        finally:
            log.debug("AsyncCachePersister worker thread terminating")

    def _execute_pending_writes(self, force: bool = False) -> None:
        """
        Execute pending writes that are ready.

        Args:
            force: If True, execute all pending writes regardless of debounce interval

        """
        current_time = time.time()
        writes_to_execute: list[tuple[str, Any, Callable[[Any], None]]] = []

        with self._lock:
            keys_to_remove = []

            for key, (data, save_fn, scheduled_time) in self._pending_writes.items():
                if force or (current_time - scheduled_time >= self._debounce_interval):
                    writes_to_execute.append((key, data, save_fn))
                    keys_to_remove.append(key)

            # Remove executed writes
            for key in keys_to_remove:
                del self._pending_writes[key]

        # Execute writes outside the lock to avoid blocking
        for key, data, save_fn in writes_to_execute:
            try:
                save_fn(data)
                log.debug(f"Async cache write completed: {key}")
            except Exception as e:
                log.exception(f"Error writing cache for {key}: {e}")

    def schedule_write(self, key: str, data: Any, save_function: Callable[[Any], None]) -> None:
        """
        Schedule a cache write to be executed in the background.

        If async persistence is disabled, writes immediately and synchronously.

        Args:
            key: Unique identifier for this cache entry
            data: The data to persist
            save_function: Function to call with data to perform the save

        """
        if not self._enabled:
            # Synchronous write if async is disabled
            try:
                save_function(data)
            except Exception as e:
                log.exception(f"Error in synchronous cache write for {key}: {e}")
            return

        with self._lock:
            # Update or add pending write with current timestamp
            self._pending_writes[key] = (data, save_function, time.time())

        log.debug(f"Cache write scheduled: {key}")

    def flush_all(self, timeout: float = 10.0) -> bool:
        """
        Flush all pending writes immediately.

        Args:
            timeout: Maximum time to wait for flush to complete (in seconds)

        Returns:
            True if all writes completed successfully, False if timeout occurred

        """
        if not self._enabled:
            return True

        log.debug(f"Flushing all pending cache writes (timeout={timeout}s)")

        # Request flush
        self._flush_requested.set()

        # Wait for worker to process
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                if len(self._pending_writes) == 0:
                    log.debug("All pending cache writes flushed")
                    return True
            time.sleep(0.1)

        # Timeout occurred
        with self._lock:
            remaining = len(self._pending_writes)

        log.warning(f"Flush timeout: {remaining} pending writes not completed")
        return False

    def shutdown(self, timeout: float = 10.0) -> None:
        """
        Shutdown the persister, flushing all pending writes.

        Args:
            timeout: Maximum time to wait for shutdown (in seconds)

        """
        if not self._enabled or self._worker_thread is None:
            return

        log.debug(f"Shutting down AsyncCachePersister (timeout={timeout}s)")

        # Flush all pending writes
        self.flush_all(timeout=timeout / 2)

        # Signal shutdown
        self._shutdown_flag.set()

        # Wait for worker thread to terminate
        self._worker_thread.join(timeout=timeout / 2)

        if self._worker_thread.is_alive():
            log.warning("AsyncCachePersister worker thread did not terminate in time")
        else:
            log.debug("AsyncCachePersister shutdown complete")

    def pending_count(self) -> int:
        """
        Get the number of pending writes.

        Returns:
            Number of writes waiting to be executed

        """
        with self._lock:
            return len(self._pending_writes)

    def is_enabled(self) -> bool:
        """
        Check if async persistence is enabled.

        Returns:
            True if enabled, False if synchronous mode

        """
        return self._enabled


def save_cache_to_file(cache_path: Path, data: Any) -> None:
    """
    Helper function to save cache data to a file.

    Uses sensai.util.pickle, which is the standard serialization mechanism
    for internal LSP cache data in the Serena codebase.

    Args:
        cache_path: Path to the cache file
        data: Data to save

    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    dump_pickle(data, str(cache_path))
    log.debug(f"Cache saved to {cache_path}")


def load_cache_from_file(cache_path: Path) -> Any | None:
    """
    Helper function to load cache data from a file.

    Uses sensai.util.pickle, which is the standard serialization mechanism
    for internal LSP cache data in the Serena codebase.

    Args:
        cache_path: Path to the cache file

    Returns:
        Loaded data if successful, None otherwise

    """
    if not cache_path.exists():
        return None

    try:
        data = load_pickle(str(cache_path))
        log.debug(f"Cache loaded from {cache_path}")
        return data
    except Exception as e:
        log.warning(f"Failed to load cache from {cache_path}: {e}")
        return None
