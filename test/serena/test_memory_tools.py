import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from serena.agent import SerenaAgent
from serena.memories.memory_manager import MemoryManager
from serena.tools.memory_tools import (
    ListMemoriesTool,
    MemoryAddFrontmatterTool,
    MemoryGetFrontmatterTool,
    ReadMemoryTool,
)

MARKED_PREFIX = '---\nserena_frontmatter_version: 1\ntype: "Serena Memory"\ndescription: "Notes"\n---\n'


@pytest.fixture
def memory_tool_context(tmp_path) -> tuple[MagicMock, MemoryManager]:
    manager = MemoryManager(serena_data_folder=tmp_path)
    agent = MagicMock(spec=SerenaAgent)
    agent.get_active_project_or_raise.return_value = SimpleNamespace(memory_manager=manager)
    agent.get_active_tool_names.return_value = []
    return agent, manager


def test_list_memories_default_response_is_unchanged(memory_tool_context: tuple[MagicMock, MemoryManager]) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("plain", "Body\n", is_tool_context=False)
    manager.save_memory("metadata", MARKED_PREFIX + "Body\n", is_tool_context=False)

    result = json.loads(ListMemoriesTool(agent).apply())

    assert result == {"memories": ["metadata", "plain"]}


def test_list_memories_includes_metadata_without_version_marker_when_get_tool_is_active(
    memory_tool_context: tuple[MagicMock, MemoryManager],
) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("plain", "Body\n", is_tool_context=False)
    manager.save_memory("metadata", MARKED_PREFIX + "Body\n", is_tool_context=False)
    agent.get_active_tool_names.return_value = [MemoryGetFrontmatterTool.get_name_from_cls()]

    result = json.loads(ListMemoriesTool(agent).apply())

    assert result == {
        "memories": ["metadata", "plain"],
        "frontmatter": {"metadata": {"type": "Serena Memory", "description": "Notes"}},
    }


@pytest.mark.parametrize("active_tools", [[], [MemoryGetFrontmatterTool.get_name_from_cls()]])
def test_read_memory_hides_marked_metadata_regardless_of_active_tools(
    memory_tool_context: tuple[MagicMock, MemoryManager], active_tools: list[str]
) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("notes", MARKED_PREFIX + "\n# Body\n", is_tool_context=False)
    agent.get_active_tool_names.return_value = active_tools

    assert ReadMemoryTool(agent).apply("notes") == "\n# Body\n"
    assert manager.get_memory_file_path("notes").read_bytes() == (MARKED_PREFIX + "\n# Body\n").encode()


def test_get_and_add_frontmatter_tools(memory_tool_context: tuple[MagicMock, MemoryManager]) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("notes", "# Body\n", is_tool_context=False)
    add_tool = MemoryAddFrontmatterTool(agent)
    get_tool = MemoryGetFrontmatterTool(agent)

    assert add_tool.apply("notes", "description", 'A "quoted" note: core\\path') == "Memory notes written."
    assert json.loads(get_tool.apply("notes")) == {
        "type": "Serena Memory",
        "description": 'A "quoted" note: core\\path',
    }
    assert "serena_frontmatter_version" not in json.loads(get_tool.apply("notes"))
    assert manager.load_memory("notes") == "# Body\n"


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("description\nowner", "Notes", "single line"),
        ("description", "Notes\nowner: injected", "single line"),
        ("serena_frontmatter_version", "2", "reserved"),
    ],
)
def test_add_frontmatter_rejects_invalid_updates_without_modifying_memory(
    memory_tool_context: tuple[MagicMock, MemoryManager], key: str, value: str, error: str
) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("notes", "# Body\n", is_tool_context=False)
    path = manager.get_memory_file_path("notes")
    before = path.read_bytes()

    with pytest.raises(ValueError, match=error):
        MemoryAddFrontmatterTool(agent).apply("notes", key, value)

    assert path.read_bytes() == before
