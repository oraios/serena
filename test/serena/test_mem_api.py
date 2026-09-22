"""
Tests for the memory facade API.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from serena.config.serena_config import SerenaConfig
from serena.project import Project
from serena.repl.api.mem_api import MemoryApi
from serena.repl.facade import ApiScope, Facade


@pytest.fixture
def api(tmp_path: Path) -> MemoryApi:
    project = Project.load(str(tmp_path), serena_config=SerenaConfig(gui_log_window=False, web_dashboard=False))
    agent = MagicMock()
    agent.get_active_project_or_raise.return_value = project
    agent.serena_config.default_max_tool_answer_chars = 10000
    return MemoryApi(agent)


def test_facade_exposes_memory_operations(api: MemoryApi) -> None:
    facade = Facade.from_api(api, ApiScope())
    assert facade.name == "mem"
    assert set(facade.enabled_method_names) == {
        "list_memories",
        "read_memory",
        "write_memory",
        "edit_memory",
        "rename_memory",
        "delete_memory",
        "onboarding",
    }
    assert {name for name in facade.enabled_method_names if facade.get_method(name).info.can_edit} == {
        "write_memory",
        "edit_memory",
        "rename_memory",
        "delete_memory",
    }


def test_memory_lifecycle(api: MemoryApi) -> None:
    api.write_memory("topic/first", "# First\nhello")
    api.write_memory("second", "see `mem:topic/first`")

    # listing exposes the names to code and renders as JSON (global memories of the machine may be present, too)
    memory_list = api.list_memories()
    assert {"second", "topic/first"} <= set(memory_list.memories)
    assert api.list_memories("topic").memories == ["topic/first"]
    assert '"memories"' in memory_list.represent()

    # reading, editing, renaming (with reference propagation) and deleting
    assert api.read_memory("topic/first") == "# First\nhello"
    api.edit_memory("topic/first", "hello", "world", mode="literal")
    assert api.read_memory("topic/first") == "# First\nworld"
    api.rename_memory("topic/first", "topic/renamed")
    assert "mem:topic/renamed" in api.read_memory("second")
    api.delete_memory("second")
    assert "second" not in api.list_memories().memories
    assert api.list_memories("topic").memories == ["topic/renamed"]


def test_write_memory_rejects_overlong_content(api: MemoryApi) -> None:
    with pytest.raises(ValueError, match="too long"):
        api.write_memory("big", "x" * 100, max_chars=10)
