"""Lifecycle management for Murena MCP tenants.

Handles starting, stopping, and monitoring of tenant processes
with support for auto-start on demand and auto-stop on idle.
"""

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import psutil

from murena.multi_project.tenant_registry import TenantRegistry, TenantStatus

log = logging.getLogger(__name__)


@dataclass
class LifecycleConfig:
    """Configuration for lifecycle management."""

    auto_start_enabled: bool = True
    auto_start_on_first_tool_call: bool = True
    prestart_recent_projects: int = 3

    auto_stop_enabled: bool = True
    idle_timeout_minutes: int = 30
    preserve_pinned_projects: bool = True

    max_concurrent_tenants: int = 7
    total_memory_limit_mb: int = 1800
    memory_pressure_threshold_percent: int = 80

    pinned_projects: list[str] = field(default_factory=list)


class LifecycleManager:
    """Manages lifecycle of Murena MCP tenant processes."""

    def __init__(self, config: Optional[LifecycleConfig] = None):
        """Initialize lifecycle manager.

        Args:
            config: LifecycleConfig instance

        """
        self.config = config or LifecycleConfig()
        self.registry = TenantRegistry()

    def start_tenant(self, tenant_id: str) -> bool:
        """Start a tenant MCP server.

        Args:
            tenant_id: ID of tenant to start

        Returns:
            True if start succeeded

        """
        tenant = self.registry.get_tenant(tenant_id)

        if not tenant:
            log.error(f"Tenant {tenant_id} not found in registry")
            return False

        if tenant.status == TenantStatus.RUNNING:
            log.debug(f"Tenant {tenant_id} already running")
            return True

        if tenant.status == TenantStatus.STARTING:
            log.debug(f"Tenant {tenant_id} already starting")
            return True

        # Update status to STARTING
        self.registry.update_status(tenant_id, TenantStatus.STARTING)

        try:
            # Start MCP server subprocess
            cmd = [
                "uvx",
                "murena",
                "start-mcp-server",
                "--project",
                tenant.project_root,
                "--auto-name",
                "--transport",
                "stdio",
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

            log.info(f"Started MCP server for {tenant_id} (PID {proc.pid})")

            # Wait for server to register itself (up to 10 seconds)
            start_time = time.time()
            while time.time() - start_time < 10:
                time.sleep(0.5)
                updated_tenant = self.registry.get_tenant(tenant_id)
                if updated_tenant and updated_tenant.status == TenantStatus.RUNNING:
                    log.info(f"Tenant {tenant_id} started successfully (PID {updated_tenant.pid})")
                    return True

            log.warning(f"Tenant {tenant_id} did not reach RUNNING state within 10s")
            return False

        except Exception as e:
            log.error(f"Failed to start tenant {tenant_id}: {e}")
            self.registry.update_status(tenant_id, TenantStatus.ERROR)
            return False

    def stop_tenant(self, tenant_id: str, graceful: bool = True) -> bool:
        """Stop a tenant MCP server.

        Args:
            tenant_id: ID of tenant to stop
            graceful: If True, use SIGTERM; if False, use SIGKILL

        Returns:
            True if stop succeeded

        """
        tenant = self.registry.get_tenant(tenant_id)

        if not tenant:
            log.warning(f"Tenant {tenant_id} not found in registry")
            return True

        if tenant.status == TenantStatus.STOPPED:
            log.debug(f"Tenant {tenant_id} already stopped")
            return True

        if not tenant.pid:
            log.warning(f"Tenant {tenant_id} has no PID, removing from registry")
            self.registry.unregister_tenant(tenant_id)
            return True

        try:
            process = psutil.Process(tenant.pid)

            if graceful:
                # Send SIGTERM for graceful shutdown
                process.terminate()
                try:
                    process.wait(timeout=10)
                except psutil.TimeoutExpired:
                    log.warning(f"Tenant {tenant_id} did not stop gracefully, force killing")
                    process.kill()
            else:
                # Force kill
                process.kill()

            log.info(f"Stopped tenant {tenant_id}")
            self.registry.unregister_tenant(tenant_id)
            return True

        except psutil.NoSuchProcess:
            log.debug(f"Tenant {tenant_id} process not found, cleaning registry")
            self.registry.unregister_tenant(tenant_id)
            return True
        except Exception as e:
            log.error(f"Failed to stop tenant {tenant_id}: {e}")
            return False

    def restart_tenant(self, tenant_id: str) -> bool:
        """Restart a tenant (stop then start).

        Args:
            tenant_id: ID of tenant to restart

        Returns:
            True if restart succeeded

        """
        log.info(f"Restarting tenant {tenant_id}")
        self.stop_tenant(tenant_id, graceful=True)
        time.sleep(1)  # Give process time to terminate
        return self.start_tenant(tenant_id)

    def auto_stop_idle_tenants(self) -> list[str]:
        """Stop tenants idle for longer than configured timeout.

        Returns:
            List of tenant IDs that were stopped

        """
        if not self.config.auto_stop_enabled:
            return []

        stopped = []
        tenants = self.registry.list_running_tenants()
        now = datetime.now()

        for tenant in tenants:
            # Skip pinned projects
            if self.config.preserve_pinned_projects and tenant.tenant_id in self.config.pinned_projects:
                continue

            # Check idle time
            if tenant.last_activity:
                try:
                    last_activity = datetime.fromisoformat(tenant.last_activity)
                    idle_duration = now - last_activity
                    idle_minutes = idle_duration.total_seconds() / 60

                    if idle_minutes > self.config.idle_timeout_minutes:
                        log.info(
                            f"Stopping idle tenant {tenant.tenant_id} "
                            f"(idle {idle_minutes:.1f}m, limit {self.config.idle_timeout_minutes}m)"
                        )
                        self.stop_tenant(tenant.tenant_id)
                        stopped.append(tenant.tenant_id)
                except ValueError as e:
                    log.error(f"Failed to parse activity time for {tenant.tenant_id}: {e}")

        return stopped

    def handle_memory_pressure(self) -> list[str]:
        """Handle high system memory usage by stopping least-used tenants.

        Returns:
            List of tenant IDs that were stopped

        """
        import psutil

        # Check system memory
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        if memory_percent < self.config.memory_pressure_threshold_percent:
            return []

        log.warning(f"Memory pressure detected: {memory_percent:.1f}% used")

        stopped = []
        tenants = self.registry.list_running_tenants()

        # Sort by last activity (least recent first)
        tenants_by_activity = sorted(
            tenants,
            key=lambda t: (
                datetime.fromisoformat(t.last_activity)
                if t.last_activity
                else datetime.fromisoformat("1970-01-01T00:00:00")
            ),
        )

        # Stop least-used tenants until memory is under threshold
        for tenant in tenants_by_activity:
            if tenant.tenant_id in self.config.pinned_projects:
                continue

            log.info(f"Stopping {tenant.tenant_id} due to memory pressure")
            self.stop_tenant(tenant.tenant_id)
            stopped.append(tenant.tenant_id)

            # Re-check memory
            memory = psutil.virtual_memory()
            if memory.percent < self.config.memory_pressure_threshold_percent:
                break

        return stopped

    def prestart_recent_projects(self, project_names: list[str]) -> int:
        """Pre-start the most recently used projects.

        Args:
            project_names: List of project names to consider

        Returns:
            Number of projects started

        """
        if not self.config.auto_start_enabled:
            return 0

        # Get most recent projects
        recent = project_names[: self.config.prestart_recent_projects]
        started_count = 0

        for project_name in recent:
            if self.start_tenant(project_name):
                started_count += 1

        return started_count

    def get_running_tenant_count(self) -> int:
        """Get count of currently running tenants.

        Returns:
            Number of running tenants

        """
        return len(self.registry.list_running_tenants())

    def get_total_memory_usage(self) -> float:
        """Get total memory used by all running tenants.

        Returns:
            Total memory in MB

        """
        total = 0.0
        for tenant in self.registry.list_running_tenants():
            if tenant.memory_mb:
                total += tenant.memory_mb
        return total

    def should_start_new_tenant(self) -> bool:
        """Check if a new tenant can be started based on resource limits.

        Returns:
            True if new tenant can be started

        """
        running_count = self.get_running_tenant_count()
        total_memory = self.get_total_memory_usage()

        can_start_by_count = running_count < self.config.max_concurrent_tenants
        can_start_by_memory = total_memory < self.config.total_memory_limit_mb

        return can_start_by_count and can_start_by_memory


class LifecycleService:
    """Background service for lifecycle management."""

    def __init__(self, config: Optional[LifecycleConfig] = None, check_interval: float = 300.0):
        """Initialize lifecycle service.

        Args:
            config: LifecycleConfig instance
            check_interval: Interval between checks in seconds (default 5 minutes)

        """
        self.config = config or LifecycleConfig()
        self.manager = LifecycleManager(self.config)
        self.check_interval = check_interval
        self.running = False

    def start(self) -> None:
        """Start the lifecycle service."""
        import threading

        if self.running:
            log.warning("Lifecycle service already running")
            return

        self.running = True
        thread = threading.Thread(target=self._service_loop, daemon=True)
        thread.start()
        log.info("Started lifecycle service")

    def stop(self) -> None:
        """Stop the lifecycle service."""
        self.running = False
        log.info("Stopped lifecycle service")

    def _service_loop(self) -> None:
        """Main service loop."""
        while self.running:
            try:
                # Auto-stop idle tenants
                if self.config.auto_stop_enabled:
                    stopped = self.manager.auto_stop_idle_tenants()
                    if stopped:
                        log.info(f"Auto-stopped {len(stopped)} idle tenants: {stopped}")

                # Handle memory pressure
                memory_stopped = self.manager.handle_memory_pressure()
                if memory_stopped:
                    log.info(f"Stopped {len(memory_stopped)} tenants due to memory pressure")

            except Exception as e:
                log.error(f"Error in lifecycle service loop: {e}")

            time.sleep(self.check_interval)
