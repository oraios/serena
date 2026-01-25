"""Multi-tenant registry for managing multiple Murena MCP server instances.

This module provides a centralized registry for tracking all configured and active tenants
(Murena projects), maintaining their state, health, and resource usage information.
"""

import fcntl
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class TenantStatus(str, Enum):
    """Status of a tenant in the registry."""

    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class TenantMetadata:
    """Complete metadata for a tenant (Murena project)."""

    tenant_id: str
    server_name: str
    project_root: str
    pid: Optional[int] = None
    status: TenantStatus = TenantStatus.STOPPED
    last_health_check: Optional[str] = None
    memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    last_activity: Optional[str] = None
    registered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    startup_time_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TenantMetadata":
        """Create from dictionary."""
        return cls(**data)

    def is_running(self) -> bool:
        """Check if tenant is in running or idle state."""
        return self.status in (TenantStatus.RUNNING, TenantStatus.IDLE)

    def is_active(self) -> bool:
        """Check if tenant is running or starting."""
        return self.status in (TenantStatus.RUNNING, TenantStatus.STARTING)


class TenantRegistry:
    """Thread-safe registry for managing tenant metadata."""

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize registry with optional custom path.

        Args:
            registry_path: Path to tenants.json. Defaults to ~/.murena/tenants.json

        """
        if registry_path is None:
            registry_path = Path.home() / ".murena" / "tenants.json"

        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize empty registry if it doesn't exist
        if not self.registry_path.exists():
            self._write_registry({})

    def _get_lock_path(self) -> Path:
        """Get path to lock file."""
        return self.registry_path.with_suffix(".lock")

    def _acquire_lock(self, timeout: float = 10.0) -> int:
        """Acquire file lock for registry access.

        Args:
            timeout: Maximum time to wait for lock in seconds

        Returns:
            File descriptor for locked file

        Raises:
            RuntimeError: If lock cannot be acquired within timeout

        """
        lock_path = self._get_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o644)
        start_time = time.time()

        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_fd
            except OSError:
                if time.time() - start_time > timeout:
                    os.close(lock_fd)
                    raise RuntimeError(f"Could not acquire lock on {lock_path} within {timeout}s")
                time.sleep(0.1)

    def _release_lock(self, lock_fd: int) -> None:
        """Release file lock."""
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)

    def _read_registry(self) -> dict:
        """Read current registry from disk."""
        try:
            with open(self.registry_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_registry(self, data: dict) -> None:
        """Write registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2)

    def register_tenant(self, metadata: TenantMetadata) -> None:
        """Register a new tenant in the registry.

        Args:
            metadata: Tenant metadata to register

        """
        lock_fd = self._acquire_lock()
        try:
            data = self._read_registry()
            data[metadata.tenant_id] = metadata.to_dict()
            self._write_registry(data)
            log.debug(f"Registered tenant: {metadata.tenant_id}")
        finally:
            self._release_lock(lock_fd)

    def unregister_tenant(self, tenant_id: str) -> None:
        """Remove a tenant from the registry.

        Args:
            tenant_id: ID of tenant to remove

        """
        lock_fd = self._acquire_lock()
        try:
            data = self._read_registry()
            if tenant_id in data:
                del data[tenant_id]
                self._write_registry(data)
                log.debug(f"Unregistered tenant: {tenant_id}")
        finally:
            self._release_lock(lock_fd)

    def update_status(self, tenant_id: str, status: TenantStatus) -> None:
        """Update status of a tenant.

        Args:
            tenant_id: ID of tenant
            status: New status

        """
        lock_fd = self._acquire_lock()
        try:
            data = self._read_registry()
            if tenant_id in data:
                data[tenant_id]["status"] = status.value
                self._write_registry(data)
                log.debug(f"Updated tenant {tenant_id} status to {status.value}")
        finally:
            self._release_lock(lock_fd)

    def update_health(self, tenant_id: str, memory_mb: float, cpu_percent: float) -> None:
        """Update health metrics for a tenant.

        Args:
            tenant_id: ID of tenant
            memory_mb: Memory usage in MB
            cpu_percent: CPU usage percentage

        """
        lock_fd = self._acquire_lock()
        try:
            data = self._read_registry()
            if tenant_id in data:
                data[tenant_id]["memory_mb"] = memory_mb
                data[tenant_id]["cpu_percent"] = cpu_percent
                data[tenant_id]["last_health_check"] = datetime.now().isoformat()
                self._write_registry(data)
        finally:
            self._release_lock(lock_fd)

    def mark_activity(self, tenant_id: str) -> None:
        """Mark tenant as having recent activity.

        Args:
            tenant_id: ID of tenant

        """
        lock_fd = self._acquire_lock()
        try:
            data = self._read_registry()
            if tenant_id in data:
                data[tenant_id]["last_activity"] = datetime.now().isoformat()
                self._write_registry(data)
        finally:
            self._release_lock(lock_fd)

    def get_tenant(self, tenant_id: str) -> Optional[TenantMetadata]:
        """Get metadata for a specific tenant.

        Args:
            tenant_id: ID of tenant

        Returns:
            TenantMetadata if found, None otherwise

        """
        data = self._read_registry()
        if tenant_id in data:
            return TenantMetadata.from_dict(data[tenant_id])
        return None

    def list_all_tenants(self) -> list[TenantMetadata]:
        """Get list of all registered tenants.

        Returns:
            List of all tenant metadata

        """
        data = self._read_registry()
        return [TenantMetadata.from_dict(v) for v in data.values()]

    def list_running_tenants(self) -> list[TenantMetadata]:
        """Get list of all running tenants.

        Returns:
            List of running tenant metadata

        """
        return [t for t in self.list_all_tenants() if t.is_running()]

    def cleanup_stale_entries(self) -> int:
        """Remove entries for processes that no longer exist.

        Returns:
            Number of entries removed

        """
        import psutil

        lock_fd = self._acquire_lock()
        try:
            data = self._read_registry()
            removed_count = 0

            for tenant_id, tenant_data in list(data.items()):
                pid = tenant_data.get("pid")
                if pid and not psutil.pid_exists(pid):
                    log.debug(f"Removing stale entry for {tenant_id} (PID {pid} not found)")
                    del data[tenant_id]
                    removed_count += 1

            if removed_count > 0:
                self._write_registry(data)

            return removed_count
        finally:
            self._release_lock(lock_fd)

    def clear_all(self) -> None:
        """Clear all entries from registry (use with caution)."""
        lock_fd = self._acquire_lock()
        try:
            self._write_registry({})
            log.warning("Cleared all tenant registry entries")
        finally:
            self._release_lock(lock_fd)
