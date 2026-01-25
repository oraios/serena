"""
Token bucket rate limiter for LSP operations.

Prevents CPU spikes from excessive LSP calls by smoothing request rates.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)


class RateLimiter:
    """
    Thread-safe token bucket rate limiter.

    Features:
    - Configurable rate (tokens/second) and burst capacity
    - Non-blocking try_acquire() and blocking acquire()
    - Token refill in background
    - Low overhead

    Example:
        >>> limiter = RateLimiter(rate=50, burst=100)
        >>> if limiter.try_acquire():
        ...     # Proceed with operation
        ...     pass
        >>> limiter.acquire()  # Blocks until token available

    """

    def __init__(self, rate: float, burst: int | None = None):
        """
        Initialize the rate limiter.

        Args:
            rate: Maximum operations per second
            burst: Maximum burst capacity (default: 2 * rate)

        """
        self._rate = rate
        self._burst = burst or int(2 * rate)
        self._tokens = float(self._burst)
        self._last_refill = time.time()
        self._lock = threading.Lock()

        log.debug(f"RateLimiter initialized: rate={rate} ops/sec, burst={self._burst}")

    def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens without blocking.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens acquired, False otherwise

        """
        with self._lock:
            self._refill()

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: int = 1, timeout: float | None = None) -> bool:
        """
        Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum wait time in seconds (None = wait forever)

        Returns:
            True if tokens acquired, False if timeout

        """
        start_time = time.time()

        while True:
            if self.try_acquire(tokens):
                return True

            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

            # Calculate wait time until next token
            with self._lock:
                needed = tokens - self._tokens
                wait_time = needed / self._rate

            # Sleep for a portion of wait time
            sleep_time = min(wait_time / 2, 0.1)
            time.sleep(sleep_time)

    def _refill(self) -> None:
        """
        Refill tokens based on elapsed time.

        Must be called with lock held.
        """
        now = time.time()
        elapsed = now - self._last_refill

        # Add tokens based on elapsed time
        new_tokens = elapsed * self._rate
        self._tokens = min(self._burst, self._tokens + new_tokens)
        self._last_refill = now

    def get_available_tokens(self) -> float:
        """
        Get current number of available tokens.

        Returns:
            Number of tokens currently available

        """
        with self._lock:
            self._refill()
            return self._tokens

    def reset(self) -> None:
        """Reset the rate limiter to full capacity."""
        with self._lock:
            self._tokens = float(self._burst)
            self._last_refill = time.time()
            log.debug("RateLimiter reset")

    def get_stats(self) -> dict[str, float]:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with current state

        """
        with self._lock:
            self._refill()
            return {
                "rate": self._rate,
                "burst": self._burst,
                "available_tokens": self._tokens,
                "utilization": 1.0 - (self._tokens / self._burst),
            }
