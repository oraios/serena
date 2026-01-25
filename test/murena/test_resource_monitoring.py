"""
Integration tests for resource monitoring and graceful degradation.

These tests verify memory stability over time and degradation behavior.
"""

import time

import pytest

from murena.util.resource_monitor import ResourceMonitor, ResourceSnapshot, ResourceThresholds

try:
    import psutil  # noqa: F401 - Used for availability check

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil not available")
class TestResourceMonitor:
    """Tests for resource monitoring"""

    def test_resource_monitor_basic(self):
        """Verify resource monitor can start, take snapshots, and stop"""
        monitor = ResourceMonitor(
            sample_interval=0.5,
            thresholds=ResourceThresholds(memory_warning_mb=1000, memory_critical_mb=2000),
        )

        monitor.start()
        assert monitor.is_running()

        # Let it collect a few samples
        time.sleep(1.5)

        # Get snapshots
        snapshots = monitor.get_snapshots()
        assert len(snapshots) >= 2, "Should have at least 2 snapshots"

        # Verify snapshot structure
        snapshot = snapshots[0]
        assert snapshot.memory_rss_mb > 0
        assert snapshot.memory_vms_mb > 0
        assert snapshot.cpu_percent >= 0
        assert snapshot.thread_count > 0

        # Get stats
        stats = monitor.get_stats()
        assert "memory_min_mb" in stats
        assert "memory_max_mb" in stats
        assert "cpu_avg_percent" in stats

        monitor.stop(timeout=2.0)
        assert not monitor.is_running()

    def test_resource_monitor_immediate_snapshot(self):
        """Verify immediate snapshot without background monitoring"""
        monitor = ResourceMonitor(sample_interval=10.0)

        snapshot = monitor.take_immediate_snapshot()
        assert snapshot is not None
        assert snapshot.memory_rss_mb > 0

    def test_resource_monitor_warning_callback(self):
        """Verify warning callback is triggered"""
        warnings = []

        def on_warning(snapshot: ResourceSnapshot):
            warnings.append(snapshot)

        # Set very low threshold to trigger immediately
        monitor = ResourceMonitor(
            sample_interval=0.5,
            thresholds=ResourceThresholds(memory_warning_mb=1, memory_critical_mb=10000),  # 1 MB threshold
            on_warning=on_warning,
        )

        monitor.start()
        time.sleep(1.5)  # Let it sample
        monitor.stop(timeout=2.0)

        # Should have triggered warning (current memory > 1 MB)
        assert len(warnings) >= 1, "Warning callback should have been triggered"

    def test_resource_monitor_critical_callback(self):
        """Verify critical callback is triggered"""
        criticals = []

        def on_critical(snapshot: ResourceSnapshot):
            criticals.append(snapshot)

        # Set very low threshold to trigger immediately
        monitor = ResourceMonitor(
            sample_interval=0.5,
            thresholds=ResourceThresholds(memory_warning_mb=1, memory_critical_mb=2),  # 2 MB threshold
            on_critical=on_critical,
        )

        monitor.start()
        time.sleep(1.5)
        monitor.stop(timeout=2.0)

        # Should have triggered critical (current memory > 2 MB)
        assert len(criticals) >= 1, "Critical callback should have been triggered"


@pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil not available")
@pytest.mark.timeout(120)  # 2 minutes max
class TestMemoryStability:
    """Integration tests for long-running memory stability"""

    def test_memory_stability_short_session(self):
        """Verify memory doesn't grow unbounded in a short session"""
        monitor = ResourceMonitor(sample_interval=1.0)
        monitor.start()

        # Simulate activity for 10 seconds
        snapshots = []
        for _ in range(10):
            snapshot = monitor.take_immediate_snapshot()
            snapshots.append(snapshot)
            time.sleep(1.0)

        monitor.stop(timeout=2.0)

        # Calculate memory growth
        memory_values = [s.memory_rss_mb for s in snapshots]
        min_memory = min(memory_values)
        max_memory = max(memory_values)
        growth_mb = max_memory - min_memory

        # Memory shouldn't grow more than 50 MB in a short idle session
        assert growth_mb < 50, f"Memory grew {growth_mb} MB in 10 seconds (min={min_memory}, max={max_memory})"

    def test_resource_monitor_overhead(self):
        """Verify resource monitor has low CPU overhead"""
        # Measure baseline CPU without monitoring
        time.sleep(0.5)  # Stabilize
        import psutil

        process = psutil.Process()
        baseline_cpu = process.cpu_percent(interval=1.0)

        # Start monitoring
        monitor = ResourceMonitor(sample_interval=1.0)
        monitor.start()

        # Measure CPU with monitoring
        time.sleep(2.0)
        monitored_cpu = process.cpu_percent(interval=1.0)

        monitor.stop(timeout=2.0)

        # Overhead should be < 2% CPU
        overhead = monitored_cpu - baseline_cpu
        assert overhead < 2.0, f"Resource monitor overhead is {overhead}%, expected < 2%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
