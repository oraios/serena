"""Health monitoring system for Murena MCP tenant instances.

Provides health status collection, monitoring, and auto-restart capabilities
for managing multiple tenant processes.
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import psutil

from murena.multi_project.tenant_registry import TenantRegistry, TenantStatus

log = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health status information for a tenant."""

    status: str  # "healthy", "degraded", "unhealthy"
    uptime_seconds: float
    memory_mb: float
    cpu_percent: float
    language_servers: dict[str, str] = field(default_factory=dict)
    last_tool_execution: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def is_healthy(self) -> bool:
        """Check if status indicates health."""
        return self.status == "healthy"

    def is_degraded(self) -> bool:
        """Check if status indicates degradation."""
        return self.status == "degraded"

    def is_unhealthy(self) -> bool:
        """Check if status indicates failure."""
        return self.status == "unhealthy"


class HealthMonitor:
    """Monitors health of a Murena tenant instance."""

    def __init__(self, tenant_id: str, pid: int, registry: Optional[TenantRegistry] = None):
        """Initialize health monitor for a tenant.

        Args:
            tenant_id: ID of the tenant to monitor
            pid: Process ID of the MCP server
            registry: Optional TenantRegistry instance

        """
        self.tenant_id = tenant_id
        self.pid = pid
        self.registry = registry or TenantRegistry()
        self.process = None
        self.uptime_start = time.time()

        try:
            self.process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            log.warning(f"Process {pid} not found for tenant {tenant_id}")

    def collect_health_status(self) -> HealthStatus:
        """Collect current health status for the tenant.

        Returns:
            HealthStatus with current metrics

        """
        if not self.process or not psutil.pid_exists(self.pid):
            return HealthStatus(
                status="unhealthy",
                uptime_seconds=0,
                memory_mb=0,
                cpu_percent=0,
                warnings=["Process not running"],
            )

        try:
            # Collect memory usage
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # Collect CPU usage
            cpu_percent = self.process.cpu_percent(interval=0.5)

            # Calculate uptime
            create_time = self.process.create_time()
            uptime_seconds = time.time() - create_time

            # Check memory thresholds
            warnings = []
            status = "healthy"

            if memory_mb > 600:
                warnings.append(f"Critical memory usage: {memory_mb:.0f}MB")
                status = "unhealthy"
            elif memory_mb > 400:
                warnings.append(f"High memory usage: {memory_mb:.0f}MB")
                status = "degraded"

            if cpu_percent > 80:
                warnings.append(f"High CPU usage: {cpu_percent:.1f}%")
                if status == "healthy":
                    status = "degraded"

            # Get last activity from registry
            tenant = self.registry.get_tenant(self.tenant_id)
            last_activity = tenant.last_activity if tenant else None

            return HealthStatus(
                status=status,
                uptime_seconds=uptime_seconds,
                memory_mb=memory_mb,
                cpu_percent=cpu_percent,
                last_tool_execution=last_activity,
                warnings=warnings,
            )

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            log.error(f"Failed to collect health status for {self.tenant_id}: {e}")
            return HealthStatus(
                status="unhealthy",
                uptime_seconds=0,
                memory_mb=0,
                cpu_percent=0,
                warnings=[f"Failed to collect metrics: {e!s}"],
            )

    def check_lsp_responsiveness(self, timeout: float = 5.0) -> dict[str, str]:
        """Check if language servers are responsive.

        Args:
            timeout: Timeout in seconds for LSP checks

        Returns:
            Dictionary mapping LSP name to status ("ok" or error message)

        """
        # This would require communication with the MCP server
        # For now, return placeholder
        return {}

    def report_health(self) -> None:
        """Report health metrics to the registry."""
        health = self.collect_health_status()
        self.registry.update_health(
            self.tenant_id,
            memory_mb=health.memory_mb,
            cpu_percent=health.cpu_percent,
        )

        if health.is_unhealthy():
            self.registry.update_status(self.tenant_id, TenantStatus.ERROR)
            log.error(f"Tenant {self.tenant_id} marked as unhealthy: {health.warnings}")
        elif health.is_degraded():
            log.warning(f"Tenant {self.tenant_id} degraded: {health.warnings}")


class BackgroundHealthMonitor:
    """Background health monitoring thread for a tenant."""

    def __init__(
        self,
        tenant_id: str,
        pid: int,
        interval_seconds: float = 30.0,
        enabled: bool = True,
    ):
        """Initialize background health monitor.

        Args:
            tenant_id: ID of tenant to monitor
            pid: Process ID of MCP server
            interval_seconds: Interval between health checks
            enabled: Whether monitoring is enabled

        """
        self.tenant_id = tenant_id
        self.pid = pid
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.monitor = HealthMonitor(tenant_id, pid)

    def start(self) -> None:
        """Start background health monitoring."""
        if not self.enabled:
            return

        if self.running:
            log.warning(f"Health monitor for {self.tenant_id} already running")
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._monitoring_loop,
            name=f"HealthMonitor-{self.tenant_id}",
            daemon=True,
        )
        self.thread.start()
        log.debug(f"Started health monitoring for {self.tenant_id}")

    def stop(self) -> None:
        """Stop background health monitoring."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        log.debug(f"Stopped health monitoring for {self.tenant_id}")

    def _monitoring_loop(self) -> None:
        """Main health monitoring loop."""
        while self.running:
            try:
                self.monitor.report_health()
            except Exception as e:
                log.error(f"Health monitoring error for {self.tenant_id}: {e}")

            time.sleep(self.interval_seconds)

    def __del__(self) -> None:
        """Cleanup on deletion."""
        if self.running:
            self.stop()


class AutoRestarter:
    """Handles auto-restart logic for failed tenants."""

    def __init__(self, max_retries: int = 3, retry_delay_seconds: float = 10.0):
        """Initialize auto-restarter.

        Args:
            max_retries: Maximum number of restart attempts
            retry_delay_seconds: Delay between restart attempts

        """
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.restart_attempts: dict[str, int] = {}

    def can_restart(self, tenant_id: str) -> bool:
        """Check if a tenant can be restarted.

        Args:
            tenant_id: ID of tenant

        Returns:
            True if restart attempts remaining

        """
        attempts = self.restart_attempts.get(tenant_id, 0)
        return attempts < self.max_retries

    def get_remaining_attempts(self, tenant_id: str) -> int:
        """Get remaining restart attempts.

        Args:
            tenant_id: ID of tenant

        Returns:
            Number of remaining attempts

        """
        attempts = self.restart_attempts.get(tenant_id, 0)
        return max(0, self.max_retries - attempts)

    def record_attempt(self, tenant_id: str) -> None:
        """Record a restart attempt.

        Args:
            tenant_id: ID of tenant

        """
        self.restart_attempts[tenant_id] = self.restart_attempts.get(tenant_id, 0) + 1

    def reset_attempts(self, tenant_id: str) -> None:
        """Reset restart attempt counter.

        Args:
            tenant_id: ID of tenant

        """
        if tenant_id in self.restart_attempts:
            del self.restart_attempts[tenant_id]

    def restart_tenant(self, tenant_id: str, project_root: str) -> bool:
        """Attempt to restart a tenant.

        Args:
            tenant_id: ID of tenant to restart
            project_root: Root path of the project

        Returns:
            True if restart succeeded

        """
        if not self.can_restart(tenant_id):
            log.error(f"Maximum restart attempts exceeded for {tenant_id}")
            return False

        self.record_attempt(tenant_id)
        attempts_left = self.get_remaining_attempts(tenant_id)

        try:
            log.info(f"Attempting to restart {tenant_id} ({attempts_left} attempts left)")

            # Use subprocess to start new MCP server
            cmd = [
                "uvx",
                "murena",
                "start-mcp-server",
                "--project",
                project_root,
                "--auto-name",
                "--transport",
                "stdio",
            ]

            subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            time.sleep(self.retry_delay_seconds)

            # Check if restart was successful
            registry = TenantRegistry()
            tenant = registry.get_tenant(tenant_id)

            if tenant and tenant.is_running():
                log.info(f"Successfully restarted {tenant_id}")
                self.reset_attempts(tenant_id)
                return True
            else:
                log.warning(f"Restart of {tenant_id} did not become ready")
                return False

        except Exception as e:
            log.error(f"Failed to restart {tenant_id}: {e}")
            return False
