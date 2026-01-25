"""
Real-time resource monitoring for memory and CPU usage.

This module provides lightweight monitoring with threshold-based alerts
for graceful degradation under resource pressure.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

log = logging.getLogger(__name__)


@dataclass
class ResourceSnapshot:
    """Snapshot of resource usage at a point in time"""

    timestamp: float
    """Unix timestamp when snapshot was taken"""

    memory_rss_mb: float
    """Resident Set Size in MB (physical memory)"""

    memory_vms_mb: float
    """Virtual Memory Size in MB"""

    cpu_percent: float
    """CPU usage percentage (0-100)"""

    thread_count: int
    """Number of active threads"""


@dataclass
class ResourceThresholds:
    """Configuration for resource monitoring thresholds"""

    memory_warning_mb: float = 300.0
    """Memory threshold for warning callbacks (MB)"""

    memory_critical_mb: float = 500.0
    """Memory threshold for critical callbacks (MB)"""

    cpu_warning_percent: float = 80.0
    """CPU threshold for warning callbacks (%)"""

    cpu_critical_percent: float = 95.0
    """CPU threshold for critical callbacks (%)"""


class ResourceMonitor:
    """
    Monitors resource usage in background thread with threshold-based alerts.

    Features:
    - Low overhead (~1% CPU)
    - Real-time memory (RSS/VMS) and CPU tracking
    - Thread count monitoring
    - Configurable thresholds with warning/critical callbacks
    - Automatic snapshot history (last 100 snapshots)

    Example:
        >>> monitor = ResourceMonitor(
        ...     sample_interval=10.0,
        ...     thresholds=ResourceThresholds(memory_warning_mb=300),
        ...     on_warning=lambda s: print(f"Warning: {s.memory_rss_mb} MB"),
        ...     on_critical=lambda s: print(f"Critical: {s.memory_rss_mb} MB"),
        ... )
        >>> monitor.start()
        >>> # ... work ...
        >>> monitor.stop()

    """

    def __init__(
        self,
        sample_interval: float = 10.0,
        thresholds: ResourceThresholds | None = None,
        on_warning: Callable[[ResourceSnapshot], None] | None = None,
        on_critical: Callable[[ResourceSnapshot], None] | None = None,
        max_history: int = 100,
    ):
        """
        Initialize the resource monitor.

        Args:
            sample_interval: Seconds between samples
            thresholds: Resource thresholds for alerts
            on_warning: Callback when warning threshold exceeded
            on_critical: Callback when critical threshold exceeded
            max_history: Maximum number of snapshots to keep in history

        """
        if not PSUTIL_AVAILABLE:
            log.warning("psutil not available, resource monitoring disabled")
            self._enabled = False
            return

        self._enabled = True
        self._sample_interval = sample_interval
        self._thresholds = thresholds or ResourceThresholds()
        self._on_warning = on_warning
        self._on_critical = on_critical
        self._max_history = max_history

        self._shutdown = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._snapshots: list[ResourceSnapshot] = []
        self._lock = threading.Lock()

        # Track alert state to avoid spam
        self._warning_triggered = False
        self._critical_triggered = False

        # Get process handle
        self._process = psutil.Process()

        log.debug(
            f"ResourceMonitor initialized: interval={sample_interval}s, "
            f"thresholds=(warning={self._thresholds.memory_warning_mb}MB, "
            f"critical={self._thresholds.memory_critical_mb}MB)"
        )

    def start(self) -> None:
        """Start the monitoring thread."""
        if not self._enabled:
            return

        if self._worker_thread is not None and self._worker_thread.is_alive():
            log.warning("ResourceMonitor already running")
            return

        self._shutdown.clear()
        self._worker_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ResourceMonitor")
        self._worker_thread.start()
        log.info("ResourceMonitor started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the monitoring thread."""
        if not self._enabled or self._worker_thread is None:
            return

        log.debug("Stopping ResourceMonitor...")
        self._shutdown.set()
        self._worker_thread.join(timeout=timeout)

        if self._worker_thread.is_alive():
            log.warning("ResourceMonitor thread did not terminate in time")
        else:
            log.debug("ResourceMonitor stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        try:
            while not self._shutdown.is_set():
                # Take snapshot
                snapshot = self._take_snapshot()

                # Store in history
                with self._lock:
                    self._snapshots.append(snapshot)
                    if len(self._snapshots) > self._max_history:
                        self._snapshots.pop(0)

                # Check thresholds and trigger callbacks
                self._check_thresholds(snapshot)

                # Wait for next interval
                self._shutdown.wait(timeout=self._sample_interval)

        except Exception as e:
            log.exception(f"ResourceMonitor error: {e}")

    def _take_snapshot(self) -> ResourceSnapshot:
        """Take a snapshot of current resource usage."""
        mem_info = self._process.memory_info()
        cpu_percent = self._process.cpu_percent(interval=0.1)

        return ResourceSnapshot(
            timestamp=time.time(),
            memory_rss_mb=mem_info.rss / (1024 * 1024),
            memory_vms_mb=mem_info.vms / (1024 * 1024),
            cpu_percent=cpu_percent,
            thread_count=self._process.num_threads(),
        )

    def _check_thresholds(self, snapshot: ResourceSnapshot) -> None:
        """Check thresholds and trigger callbacks."""
        # Check critical first
        if snapshot.memory_rss_mb >= self._thresholds.memory_critical_mb or snapshot.cpu_percent >= self._thresholds.cpu_critical_percent:
            if not self._critical_triggered:
                self._critical_triggered = True
                self._warning_triggered = True  # Also mark warning as triggered
                log.warning(f"CRITICAL threshold exceeded: memory={snapshot.memory_rss_mb:.1f}MB, cpu={snapshot.cpu_percent:.1f}%")
                if self._on_critical:
                    try:
                        self._on_critical(snapshot)
                    except Exception as e:
                        log.exception(f"Error in critical callback: {e}")

        # Check warning
        elif snapshot.memory_rss_mb >= self._thresholds.memory_warning_mb or snapshot.cpu_percent >= self._thresholds.cpu_warning_percent:
            if not self._warning_triggered:
                self._warning_triggered = True
                log.warning(f"WARNING threshold exceeded: memory={snapshot.memory_rss_mb:.1f}MB, cpu={snapshot.cpu_percent:.1f}%")
                if self._on_warning:
                    try:
                        self._on_warning(snapshot)
                    except Exception as e:
                        log.exception(f"Error in warning callback: {e}")

        # Reset alerts if back to normal
        else:
            if self._critical_triggered or self._warning_triggered:
                log.info(f"Resource usage back to normal: memory={snapshot.memory_rss_mb:.1f}MB, cpu={snapshot.cpu_percent:.1f}%")
                self._critical_triggered = False
                self._warning_triggered = False

    def take_immediate_snapshot(self) -> ResourceSnapshot | None:
        """
        Take an immediate snapshot outside the monitoring loop.

        Returns:
            Snapshot if monitoring is enabled, None otherwise

        """
        if not self._enabled:
            return None
        return self._take_snapshot()

    def get_snapshots(self, count: int | None = None) -> list[ResourceSnapshot]:
        """
        Get recent snapshots.

        Args:
            count: Number of recent snapshots to return (None = all)

        Returns:
            List of snapshots (most recent last)

        """
        with self._lock:
            if count is None:
                return list(self._snapshots)
            return list(self._snapshots[-count:])

    def get_stats(self) -> dict[str, float]:
        """
        Get summary statistics from snapshot history.

        Returns:
            Dictionary with min/max/avg stats

        """
        with self._lock:
            if not self._snapshots:
                return {}

            memory_values = [s.memory_rss_mb for s in self._snapshots]
            cpu_values = [s.cpu_percent for s in self._snapshots]
            thread_values = [s.thread_count for s in self._snapshots]

            return {
                "memory_min_mb": min(memory_values),
                "memory_max_mb": max(memory_values),
                "memory_avg_mb": sum(memory_values) / len(memory_values),
                "cpu_min_percent": min(cpu_values),
                "cpu_max_percent": max(cpu_values),
                "cpu_avg_percent": sum(cpu_values) / len(cpu_values),
                "thread_min": min(thread_values),
                "thread_max": max(thread_values),
                "thread_avg": sum(thread_values) / len(thread_values),
                "sample_count": len(self._snapshots),
            }

    def is_enabled(self) -> bool:
        """Check if monitoring is enabled."""
        return self._enabled

    def is_running(self) -> bool:
        """Check if monitoring thread is running."""
        return self._enabled and self._worker_thread is not None and self._worker_thread.is_alive()
