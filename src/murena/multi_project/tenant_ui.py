"""UI components for tenant management and monitoring.

Provides rich table formatting, real-time monitoring, and log display for
managing multiple Murena MCP tenant instances.
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from murena.multi_project.tenant_registry import TenantRegistry, TenantStatus

log = logging.getLogger(__name__)


class TenantUI:
    """Provides UI rendering for tenant information."""

    def __init__(self, registry: Optional[TenantRegistry] = None):
        """Initialize UI renderer.

        Args:
            registry: Optional TenantRegistry instance

        """
        self.registry = registry or TenantRegistry()

    def format_memory(self, memory_mb: Optional[float]) -> str:
        """Format memory value for display.

        Args:
            memory_mb: Memory in MB or None

        Returns:
            Formatted memory string

        """
        if memory_mb is None:
            return "-"
        if memory_mb > 1000:
            return f"{memory_mb / 1024:.1f}GB"
        return f"{memory_mb:.0f}MB"

    def format_uptime(self, seconds: float) -> str:
        """Format uptime duration.

        Args:
            seconds: Uptime in seconds

        Returns:
            Formatted uptime string

        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def get_status_symbol(self, status: TenantStatus) -> str:
        """Get symbol for status display.

        Args:
            status: TenantStatus enum value

        Returns:
            Status symbol string

        """
        symbols = {
            TenantStatus.RUNNING: "🟢",
            TenantStatus.IDLE: "⏸️",
            TenantStatus.STARTING: "🟡",
            TenantStatus.STOPPED: "⬜",
            TenantStatus.ERROR: "🔴",
        }
        return symbols.get(status, "❓")

    def print_tenant_status_simple(self) -> None:
        """Print simple status of all tenants using basic formatting."""
        tenants = self.registry.list_all_tenants()

        if not tenants:
            print("No tenants registered")
            return

        print("\nTenant Status:")
        print("-" * 100)
        print(f"{'Tenant':<20} {'Status':<12} {'Memory':<12} {'CPU':<8} {'LSPs':<8} {'Last Activity':<20}")
        print("-" * 100)

        for tenant in tenants:
            status_symbol = self.get_status_symbol(tenant.status)
            status_str = f"{status_symbol} {tenant.status.value:<8}"
            memory_str = self.format_memory(tenant.memory_mb)
            cpu_str = f"{tenant.cpu_percent or 0:.1f}%" if tenant.cpu_percent else "-"
            last_activity_str = self._format_last_activity(tenant.last_activity)

            print(f"{tenant.tenant_id:<20} {status_str:<20} {memory_str:<12} {cpu_str:<8} {'-':<8} {last_activity_str:<20}")

        print("-" * 100)
        print(
            f"Total: {len([t for t in tenants if t.is_running()])} running, "
            f"{len([t for t in tenants if t.status == TenantStatus.IDLE])} idle, "
            f"{len([t for t in tenants if t.status == TenantStatus.STOPPED])} stopped"
        )

    def print_tenant_status_detailed(self, tenant_id: str) -> None:
        """Print detailed status for a specific tenant.

        Args:
            tenant_id: ID of tenant to display

        """
        tenant = self.registry.get_tenant(tenant_id)

        if not tenant:
            print(f"Tenant '{tenant_id}' not found in registry")
            return

        print(f"\nTenant: {tenant.tenant_id} ({tenant.server_name})")
        print("=" * 80)
        print(f"Status:         {self.get_status_symbol(tenant.status)} {tenant.status.value}")
        print(f"Project Root:   {tenant.project_root}")

        if tenant.pid:
            print(f"PID:            {tenant.pid}")

        if tenant.registered_at:
            print(f"Registered:     {tenant.registered_at}")

        if tenant.startup_time_seconds:
            print(f"Startup Time:   {tenant.startup_time_seconds:.2f}s")

        print("\nResources:")
        print(f"  Memory:       {self.format_memory(tenant.memory_mb)}")
        print(f"  CPU:          {tenant.cpu_percent or 0:.1f}%")

        if tenant.last_activity:
            last_activity = self._format_last_activity(tenant.last_activity, detailed=True)
            print("\nActivity:")
            print(f"  Last Tool:    {last_activity}")

        print("=" * 80)

    def print_process_list(self) -> None:
        """Print process list similar to `ps aux`."""
        import psutil

        tenants = self.registry.list_all_tenants()

        if not tenants:
            print("No tenants registered")
            return

        print("\nMurena Tenant Processes:")
        print("-" * 120)
        print(f"{'PID':<8} {'Tenant':<20} {'Status':<12} {'Memory':<12} {'CPU':<8} {'Uptime':<12} {'Command':<60}")
        print("-" * 120)

        for tenant in tenants:
            if not tenant.pid:
                print(f"{'N/A':<8} {tenant.tenant_id:<20} {tenant.status.value:<12} {'-':<12} {'-':<8} {'-':<12} {'-':<60}")
                continue

            try:
                proc = psutil.Process(tenant.pid)
                memory_mb = proc.memory_info().rss / 1024 / 1024
                cpu = proc.cpu_percent(interval=0.1)
                uptime_seconds = datetime.now().timestamp() - proc.create_time()
                uptime_str = self.format_uptime(uptime_seconds)
                cmd = " ".join(proc.cmdline()[:3])

                print(
                    f"{tenant.pid:<8} {tenant.tenant_id:<20} {tenant.status.value:<12} "
                    f"{self.format_memory(memory_mb):<12} {cpu:.1f}%{'':<4} {uptime_str:<12} {cmd:<60}"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                print(
                    f"{tenant.pid:<8} {tenant.tenant_id:<20} {tenant.status.value:<12} "
                    f"'{'-':<11} {'-':<8} {'-':<12} (process not accessible)"
                )

        print("-" * 120)

    def print_resource_stats(self, sort_by: str = "memory") -> None:
        """Print resource usage statistics.

        Args:
            sort_by: Sort key - 'memory', 'cpu', or 'name'

        """
        import psutil

        tenants = self.registry.list_running_tenants()

        if not tenants:
            print("No running tenants")
            return

        # Sort tenants
        if sort_by == "memory":
            tenants = sorted(tenants, key=lambda t: t.memory_mb or 0, reverse=True)
        elif sort_by == "cpu":
            tenants = sorted(tenants, key=lambda t: t.cpu_percent or 0, reverse=True)
        else:
            tenants = sorted(tenants, key=lambda t: t.tenant_id)

        print(f"\nResource Usage (sorted by {sort_by}):")
        print("-" * 80)
        print(f"{'Tenant':<20} {'Memory':<15} {'CPU':<10} {'Status':<12}")
        print("-" * 80)

        total_memory = 0.0
        for tenant in tenants:
            memory_str = self.format_memory(tenant.memory_mb)
            cpu_str = f"{tenant.cpu_percent or 0:.1f}%" if tenant.cpu_percent else "-"
            status_symbol = self.get_status_symbol(tenant.status)
            status_str = f"{status_symbol} {tenant.status.value}"

            print(f"{tenant.tenant_id:<20} {memory_str:<15} {cpu_str:<10} {status_str:<12}")

            if tenant.memory_mb:
                total_memory += tenant.memory_mb

        print("-" * 80)
        print(f"Total Memory: {self.format_memory(total_memory)}")

        # System memory
        memory = psutil.virtual_memory()
        print(f"System Memory: {self.format_memory(memory.used)} / {self.format_memory(memory.total)} ({memory.percent:.1f}%)")

    def print_tenant_logs(self, tenant_id: str, lines: int = 50, follow: bool = False) -> None:
        """Print or follow tenant logs.

        Args:
            tenant_id: ID of tenant
            lines: Number of lines to show
            follow: If True, follow logs in real-time

        """
        log_path = Path.home() / ".murena" / "logs" / f"tenant-{tenant_id}.log"

        if not log_path.exists():
            print(f"Log file not found: {log_path}")
            return

        if follow:
            # Use tail -f for real-time following
            print(f"Following logs for {tenant_id} (press Ctrl+C to stop)...")
            print("-" * 80)
            try:
                subprocess.run(["tail", "-f", str(log_path)], check=False)
            except KeyboardInterrupt:
                print("\nLog following stopped")
        else:
            # Show last N lines
            print(f"Last {lines} lines of {tenant_id} logs:")
            print("-" * 80)
            try:
                subprocess.run(["tail", "-n", str(lines), str(log_path)], check=False)
            except FileNotFoundError:
                print("tail command not found")
            except Exception as e:
                print(f"Error reading logs: {e}")
            print("-" * 80)

    def _format_last_activity(self, activity_time: Optional[str], detailed: bool = False) -> str:
        """Format last activity timestamp.

        Args:
            activity_time: ISO format timestamp or None
            detailed: If True, show full time string

        Returns:
            Formatted activity string

        """
        if not activity_time:
            return "Never"

        try:
            activity_dt = datetime.fromisoformat(activity_time)
            now = datetime.now()
            delta = now - activity_dt

            if delta.total_seconds() < 60:
                return "< 1 min ago"
            elif delta.total_seconds() < 3600:
                minutes = int(delta.total_seconds() // 60)
                return f"{minutes} min{'s' if minutes > 1 else ''} ago"
            elif delta.total_seconds() < 86400:
                hours = int(delta.total_seconds() // 3600)
                return f"{hours} hour{'s' if hours > 1 else ''} ago"
            else:
                days = int(delta.total_seconds() // 86400)
                return f"{days} day{'s' if days > 1 else ''} ago"
        except ValueError:
            return "Unknown"


class HealthUI:
    """Provides UI for health status display."""

    @staticmethod
    def print_health_report(tenant_id: Optional[str] = None) -> None:
        """Print health report for tenants.

        Args:
            tenant_id: Optional specific tenant ID

        """
        from murena.multi_project.health_monitor import HealthMonitor

        registry = TenantRegistry()

        if tenant_id:
            tenant = registry.get_tenant(tenant_id)
            if not tenant:
                print(f"Tenant '{tenant_id}' not found")
                return

            tenants = [tenant]
        else:
            tenants = registry.list_all_tenants()

        print("\nHealth Report:")
        print("-" * 100)

        for tenant in tenants:
            if not tenant.pid:
                print(f"❌ {tenant.tenant_id}: Process not running")
                continue

            monitor = HealthMonitor(tenant.tenant_id, tenant.pid, registry)
            health = monitor.collect_health_status()

            status_emoji = "✅" if health.is_healthy() else "⚠️" if health.is_degraded() else "❌"
            print(f"{status_emoji} {tenant.tenant_id}: {health.status.upper()}")

            if health.warnings:
                for warning in health.warnings:
                    print(f"   ⚠️  {warning}")

        print("-" * 100)
