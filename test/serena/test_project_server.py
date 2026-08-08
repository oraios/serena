import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from serena.project_server import ProjectServer, QueryProjectRequest


@pytest.fixture
def project_server() -> ProjectServer:
    server = ProjectServer.__new__(ProjectServer)
    server._agent = MagicMock()
    server._loaded_projects_by_root = {}
    server._project_load_locks_by_root = {}
    server._active_project_lock = threading.Lock()
    server._loaded_projects_lock = threading.Lock()
    return server


def test_cached_project_lookup_is_not_blocked_by_unrelated_cold_load(project_server: ProjectServer) -> None:
    cached_root = Path("/cached")
    cold_root = Path("/cold")
    cached_project = MagicMock()
    cold_project = MagicMock()
    cold_load_started = threading.Event()
    allow_cold_load_to_finish = threading.Event()

    cached_registration = MagicMock(project_root=cached_root)
    cold_registration = MagicMock(project_root=cold_root)

    def block_cold_load() -> None:
        cold_load_started.set()
        assert allow_cold_load_to_finish.wait(timeout=5)

    cold_registration.get_project_instance.return_value = cold_project
    cold_project.create_language_server_manager.side_effect = block_cold_load
    project_server._loaded_projects_by_root[str(cached_root)] = cached_project
    serena_config = cast(Any, project_server._agent.serena_config)
    serena_config.get_registered_project.side_effect = {
        "cached": cached_registration,
        "cold": cold_registration,
    }.get

    with ThreadPoolExecutor(max_workers=2) as executor:
        cold_future = executor.submit(project_server._get_project, "cold")
        assert cold_load_started.wait(timeout=1)

        cached_future = executor.submit(project_server._get_project, "cached")
        try:
            assert cached_future.result(timeout=1) is cached_project
        finally:
            allow_cold_load_to_finish.set()

        assert cold_future.result(timeout=1) is cold_project


def test_cold_loads_for_different_projects_can_run_concurrently(project_server: ProjectServer) -> None:
    first_root = Path("/first")
    second_root = Path("/second")
    first_project = MagicMock()
    second_project = MagicMock()
    first_load_started = threading.Event()
    allow_first_load_to_finish = threading.Event()

    first_registration = MagicMock(project_root=first_root)
    second_registration = MagicMock(project_root=second_root)

    def block_first_load() -> None:
        first_load_started.set()
        assert allow_first_load_to_finish.wait(timeout=5)

    first_registration.get_project_instance.return_value = first_project
    first_project.create_language_server_manager.side_effect = block_first_load
    second_registration.get_project_instance.return_value = second_project
    serena_config = cast(Any, project_server._agent.serena_config)
    serena_config.get_registered_project.side_effect = {
        "first": first_registration,
        "second": second_registration,
    }.get

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(project_server._get_project, "first")
        assert first_load_started.wait(timeout=1)

        second_future = executor.submit(project_server._get_project, "second")
        try:
            assert second_future.result(timeout=1) is second_project
        finally:
            allow_first_load_to_finish.set()

        assert first_future.result(timeout=1) is first_project


def test_concurrent_lookups_load_each_project_only_once(project_server: ProjectServer) -> None:
    project_root = Path("/project")
    project = MagicMock()
    load_started = threading.Event()
    second_lookup_started = threading.Event()
    allow_load_to_finish = threading.Event()
    registration = MagicMock(project_root=project_root)
    lookup_count = 0
    lookup_count_lock = threading.Lock()

    def block_load() -> None:
        load_started.set()
        assert allow_load_to_finish.wait(timeout=5)

    registration.get_project_instance.return_value = project
    project.create_language_server_manager.side_effect = block_load
    serena_config = cast(Any, project_server._agent.serena_config)

    def get_registration(project_name: str) -> MagicMock:
        nonlocal lookup_count
        assert project_name == "project"
        with lookup_count_lock:
            lookup_count += 1
            if lookup_count == 2:
                second_lookup_started.set()
        return registration

    serena_config.get_registered_project.side_effect = get_registration

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(project_server._get_project, "project")
        assert load_started.wait(timeout=1)
        second_future = executor.submit(project_server._get_project, "project")
        assert second_lookup_started.wait(timeout=1)
        allow_load_to_finish.set()

        assert first_future.result(timeout=1) is project
        assert second_future.result(timeout=1) is project

    registration.get_project_instance.assert_called_once_with(serena_config)
    project.create_language_server_manager.assert_called_once_with()


def test_concurrent_queries_serialize_active_project_context(project_server: ProjectServer) -> None:
    first_query_started = threading.Event()
    second_lookup_finished = threading.Event()
    allow_first_query_to_finish = threading.Event()
    state_lock = threading.Lock()
    state: dict[str, str | None] = {"active_project": None}

    def get_project(project_name: str) -> str:
        if project_name == "second":
            second_lookup_finished.set()
        return project_name

    @contextmanager
    def active_project_context(project: str) -> Iterator[None]:
        with state_lock:
            assert state["active_project"] is None
            state["active_project"] = project
        try:
            yield
        finally:
            with state_lock:
                state["active_project"] = None

    def apply_tool(hold: bool = False) -> str:
        if hold:
            first_query_started.set()
            assert allow_first_query_to_finish.wait(timeout=5)
        with state_lock:
            active_project = state["active_project"]
        assert active_project is not None
        return active_project

    tool = MagicMock()
    tool.is_readonly.return_value = True
    tool.apply_ex.side_effect = apply_tool
    server = cast(Any, project_server)
    server._get_project = MagicMock(side_effect=get_project)
    agent = cast(Any, project_server._agent)
    agent.active_project_context.side_effect = active_project_context
    agent.get_tool_by_name.return_value = tool
    first_request = QueryProjectRequest(project_name="first", tool_name="read_file", tool_params_json='{"hold": true}')
    second_request = QueryProjectRequest(project_name="second", tool_name="read_file", tool_params_json="{}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(project_server._query_project, first_request)
        assert first_query_started.wait(timeout=1)
        second_future = executor.submit(project_server._query_project, second_request)
        assert second_lookup_finished.wait(timeout=1)

        try:
            with pytest.raises(FutureTimeoutError):
                second_future.result(timeout=0.1)
        finally:
            allow_first_query_to_finish.set()

        assert first_future.result(timeout=1) == "first"
        assert second_future.result(timeout=1) == "second"
