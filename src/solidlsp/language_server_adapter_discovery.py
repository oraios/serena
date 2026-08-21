"""Discovers explicitly installed SolidLSP language-server adapters."""

import logging
import threading
from dataclasses import dataclass
from importlib import metadata

from solidlsp.ls_config import _restore_registered_language_servers, _snapshot_registered_language_servers

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "serena.language_servers"


@dataclass
class _DiscoveryState:
    completed: bool = False


_discovery_state = _DiscoveryState()
_discovery_lock = threading.Lock()


def discover_registered_language_server_adapters() -> None:
    """Load installed adapters before project configuration resolves language-server IDs.

    First discovery is serialized because registration and rollback mutate one
    process-global registry. Metadata-enumeration failures leave discovery
    incomplete so a later project load can retry. After successful enumeration,
    each entry point is applied transactionally; a failing adapter is rolled back
    without preventing the remaining installed adapters from registering.
    """
    with _discovery_lock:
        if _discovery_state.completed:
            return

        try:
            entry_points = metadata.entry_points(group=ENTRY_POINT_GROUP)
        except Exception as error:
            log.exception("Failed to discover language server adapter entry points: %s", error)
            return

        for entry_point in entry_points:
            registry_snapshot = _snapshot_registered_language_servers()
            try:
                registration = entry_point.load()
                if not callable(registration):
                    raise TypeError("entry point must resolve to a callable registration function")
                registration()
            except Exception as error:
                _restore_registered_language_servers(registry_snapshot)
                log.exception(
                    "Failed to load language server adapter entry point '%s' from %s: %s",
                    entry_point.name,
                    _get_distribution_name(entry_point),
                    error,
                )

        _discovery_state.completed = True


def _get_distribution_name(entry_point: metadata.EntryPoint) -> str:
    distribution = getattr(entry_point, "dist", None)
    if distribution is None:
        return "unknown distribution"
    return distribution.name or "unknown distribution"


def _reset_language_server_adapter_discovery_for_tests() -> None:
    """Reset discovery state for deterministic in-process tests."""
    with _discovery_lock:
        _discovery_state.completed = False
