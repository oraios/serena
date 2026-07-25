import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from serena.agent import SerenaAgent
from serena.memories.memory_manager import MemoryManager
from serena.tools.memory_tools import ListMemoriesTool, MemoryAddFrontmatterTool, MemoryGetFrontmatterTool


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
    manager.save_memory("metadata", "---\nsummary: Notes\n---\nBody\n", is_tool_context=False)

    result = json.loads(ListMemoriesTool(agent).apply())

    assert result == {"memories": ["metadata", "plain"]}


def test_list_memories_includes_metadata_when_get_tool_is_active(
    memory_tool_context: tuple[MagicMock, MemoryManager],
) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("plain", "Body\n", is_tool_context=False)
    manager.save_memory("metadata", "---\nsummary: Notes\n---\nBody\n", is_tool_context=False)
    agent.get_active_tool_names.return_value = [MemoryGetFrontmatterTool.get_name_from_cls()]

    result = json.loads(ListMemoriesTool(agent).apply())

    assert result == {
        "memories": ["metadata", "plain"],
        "frontmatter": {"metadata": {"summary": "Notes"}},
    }


def test_get_and_add_frontmatter_tools(memory_tool_context: tuple[MagicMock, MemoryManager]) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("notes", "# Body\n", is_tool_context=False)
    add_tool = MemoryAddFrontmatterTool(agent)
    get_tool = MemoryGetFrontmatterTool(agent)

    assert add_tool.apply("notes", "summary", "Notes") == "Memory notes written."
    assert json.loads(get_tool.apply("notes")) == {"summary": "Notes"}
    assert manager.load_memory("notes") == "# Body\n"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("summary\nowner", "Notes"),
        ("summary", "Notes\nowner: injected"),
    ],
)
def test_add_frontmatter_rejects_line_injection(memory_tool_context: tuple[MagicMock, MemoryManager], key: str, value: str) -> None:
    agent, manager = memory_tool_context
    manager.save_memory("notes", "# Body\n", is_tool_context=False)

    with pytest.raises(ValueError, match="single line"):
        MemoryAddFrontmatterTool(agent).apply("notes", key, value)

    assert manager.load_memory("notes") == "# Body\n"
