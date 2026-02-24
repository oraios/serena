"""Tests for the service registry."""

import os

import pytest

from serena.service_registry import ServiceEntry, ServiceRegistry


@pytest.fixture
def registry(tmp_path) -> ServiceRegistry:
    """Create a ServiceRegistry backed by a temp file."""
    return ServiceRegistry(registry_path=str(tmp_path / "services.json"))


class TestServiceRegistry:
    def test_empty_registry(self, registry: ServiceRegistry) -> None:
        """A new registry has no services."""
        services = registry.list_services()
        assert services == {}

    def test_register_service(self, registry: ServiceRegistry) -> None:
        """Register a service and retrieve it."""
        entry = ServiceEntry(
            project_path="/home/user/project",
            port=24100,
            pid=os.getpid(),
            transport="streamable-http",
            language_backend="LSP",
        )
        registry.register("my-project", entry)

        retrieved = registry.get_service("my-project")
        assert retrieved is not None
        assert retrieved.project_path == "/home/user/project"
        assert retrieved.port == 24100
        assert retrieved.pid == os.getpid()
        assert retrieved.transport == "streamable-http"
        assert retrieved.language_backend == "LSP"
        assert retrieved.started_at != ""  # auto-filled

    def test_unregister_service(self, registry: ServiceRegistry) -> None:
        """Register and then unregister a service."""
        entry = ServiceEntry(
            project_path="/home/user/project",
            port=24100,
            pid=os.getpid(),
        )
        registry.register("my-project", entry)
        assert registry.get_service("my-project") is not None

        registry.unregister("my-project")
        assert registry.get_service("my-project") is None

    def test_persistence_across_instances(self, tmp_path) -> None:
        """Two registry instances using the same file see the same data."""
        path = str(tmp_path / "services.json")
        reg1 = ServiceRegistry(registry_path=path)
        entry = ServiceEntry(
            project_path="/home/user/project",
            port=24100,
            pid=os.getpid(),
        )
        reg1.register("my-project", entry)

        reg2 = ServiceRegistry(registry_path=path)
        retrieved = reg2.get_service("my-project")
        assert retrieved is not None
        assert retrieved.port == 24100

    def test_stale_pid_cleanup(self, registry: ServiceRegistry) -> None:
        """A service with a dead PID is removed when clean_stale=True."""
        entry = ServiceEntry(
            project_path="/home/user/project",
            port=24100,
            pid=999999999,  # almost certainly not alive
        )
        registry.register("stale-project", entry)
        assert registry.get_service("stale-project") is not None

        services = registry.list_services(clean_stale=True)
        assert "stale-project" not in services

        # Verify it was actually removed from the file
        assert registry.get_service("stale-project") is None

    def test_alive_pid_preserved(self, registry: ServiceRegistry) -> None:
        """A service with a live PID (our own) survives cleanup."""
        entry = ServiceEntry(
            project_path="/home/user/project",
            port=24100,
            pid=os.getpid(),
        )
        registry.register("alive-project", entry)

        services = registry.list_services(clean_stale=True)
        assert "alive-project" in services
        assert services["alive-project"].pid == os.getpid()

    def test_allocate_port(self, registry: ServiceRegistry) -> None:
        """Returns the lowest free port in the range."""
        port = registry.allocate_port()
        assert port == 24100

    def test_allocate_port_skips_used(self, registry: ServiceRegistry) -> None:
        """Skips ports already in use by registered services."""
        # Register services on the first two ports
        for i, name in enumerate(["proj-a", "proj-b"]):
            entry = ServiceEntry(
                project_path=f"/home/user/{name}",
                port=24100 + i,
                pid=os.getpid(),
            )
            registry.register(name, entry)

        port = registry.allocate_port()
        assert port == 24102

    def test_allocate_port_exhausted(self, registry: ServiceRegistry) -> None:
        """Raises RuntimeError when all ports in the range are used."""
        for i in range(100):
            entry = ServiceEntry(
                project_path=f"/home/user/proj-{i}",
                port=24100 + i,
                pid=os.getpid(),
            )
            registry.register(f"proj-{i}", entry)

        with pytest.raises(RuntimeError, match="No available ports"):
            registry.allocate_port()
