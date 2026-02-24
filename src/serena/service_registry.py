"""Registry for managing per-project Serena HTTP services.

Provides a JSON-backed, file-locked registry that tracks which Serena
HTTP services are running, their ports, PIDs, and transport details.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sensai.util import logging

from serena.config.serena_config import SerenaPaths

log = logging.getLogger(__name__)

_PORT_RANGE_START = 24100
_PORT_RANGE_END = 24199


@dataclass
class ServiceEntry:
    """A single registered Serena HTTP service."""

    project_path: str
    port: int
    pid: int
    transport: str = "streamable-http"
    language_backend: str = "LSP"
    started_at: str = field(default="")

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = datetime.now(UTC).isoformat()


class ServiceRegistry:
    """JSON-backed registry for per-project Serena HTTP services.

    Uses file locking (``fcntl.flock``) so multiple processes can safely
    read and write the same registry file concurrently.

    :param registry_path: path to the JSON file; defaults to ``~/.serena/services.json``
    """

    def __init__(self, registry_path: str | None = None) -> None:
        if registry_path is None:
            registry_path = os.path.join(SerenaPaths().serena_user_home_dir, "services.json")
        self._path = registry_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, project_name: str, entry: ServiceEntry) -> None:
        """Add or update a service entry."""

        def _mutate(data: dict) -> None:
            data["services"][project_name] = asdict(entry)

        self._mutate_registry(_mutate)
        log.info(f"Registered service '{project_name}' on port {entry.port} (pid {entry.pid})")

    def unregister(self, project_name: str) -> None:
        """Remove a service entry.  No-op if *project_name* is not registered."""

        def _mutate(data: dict) -> None:
            data["services"].pop(project_name, None)

        self._mutate_registry(_mutate)
        log.info(f"Unregistered service '{project_name}'")

    def list_services(self, clean_stale: bool = False) -> dict[str, ServiceEntry]:
        """Return all registered services.

        :param clean_stale: when *True*, remove entries whose PID is no longer alive
            and persist the cleaned state before returning.
        """
        if clean_stale:

            def _mutate(data: dict) -> None:
                stale_names = [name for name, svc in data["services"].items() if not self._is_pid_alive(svc["pid"])]
                for name in stale_names:
                    log.info(f"Removing stale service '{name}' (pid {data['services'][name]['pid']})")
                    del data["services"][name]

            data = self._mutate_registry(_mutate)
        else:
            data = self._read_locked_shared()

        return {name: self._entry_from_dict(svc) for name, svc in data["services"].items()}

    def get_service(self, project_name: str) -> ServiceEntry | None:
        """Return the entry for *project_name*, or ``None`` if not registered."""
        data = self._read_locked_shared()
        svc = data["services"].get(project_name)
        if svc is None:
            return None
        return self._entry_from_dict(svc)

    def allocate_port(self) -> int:
        """Find the lowest unused port in the configured range.

        :raises RuntimeError: if every port in the range is already taken.
        """
        data = self._read_locked_shared()
        used_ports = {svc["port"] for svc in data["services"].values()}
        for port in range(_PORT_RANGE_START, _PORT_RANGE_END + 1):
            if port not in used_ports:
                return port
        raise RuntimeError(f"No available ports in range {_PORT_RANGE_START}-{_PORT_RANGE_END} ({len(used_ports)} services registered)")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check whether *pid* refers to a running process."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we lack permission to signal it.
            return True
        return True

    @staticmethod
    def _entry_from_dict(d: dict) -> ServiceEntry:
        return ServiceEntry(
            project_path=d["project_path"],
            port=d["port"],
            pid=d["pid"],
            transport=d.get("transport", "streamable-http"),
            language_backend=d.get("language_backend", "LSP"),
            started_at=d.get("started_at", ""),
        )

    @staticmethod
    def _empty_data() -> dict:
        return {"services": {}}

    def _ensure_file(self) -> None:
        path = Path(self._path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._empty_data(), indent=2) + "\n")

    def _read_locked_shared(self) -> dict:
        """Read the registry file with a shared (read) lock."""
        self._ensure_file()
        with open(self._path) as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                content = f.read()
                return json.loads(content) if content.strip() else self._empty_data()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def _mutate_registry(self, mutate_fn: Callable[[dict], None]) -> dict:
        """Atomically read-modify-write the registry under a single exclusive lock.

        Opens the file in ``r+`` mode, acquires ``LOCK_EX``, reads, applies
        *mutate_fn* to the data dict, writes back, and only then releases the lock.
        Returns the (possibly modified) data dict.
        """
        self._ensure_file()
        with open(self._path, "r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                content = f.read()
                data = json.loads(content) if content.strip() else self._empty_data()
                mutate_fn(data)
                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2)
                f.write("\n")
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return data
