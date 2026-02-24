from typing import Literal

from serena.project import MemoriesManager
from serena.tools import Tool, ToolMarkerCanEdit

GLOBAL_TOPIC = MemoriesManager.GLOBAL_TOPIC


def _check_global_edit_allowed(tool: Tool, memory_name: str) -> None:
    """Raise ValueError if editing a global memory is not allowed by config."""
    if memory_name.startswith(GLOBAL_TOPIC + "/") and not tool.agent.serena_config.edit_global_memories:
        raise ValueError("Editing global memories is disabled (edit_global_memories: false in serena_config.yml).")


class WriteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
    The memory name should be meaningful.
    """

    def apply(self, memory_name: str, content: str, max_chars: int = -1) -> str:
        """
        Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
        The memory name should be meaningful and can include "/" to organize into topics (e.g., "auth/login/logic").
        Use the "global/" prefix to write a memory shared across all projects (e.g., "global/my_memory").

        :param max_chars: the maximum number of characters to write. By default, determined by the config,
            change only if instructed to do so.
        """
        _check_global_edit_allowed(self, memory_name)
        # NOTE: utf-8 encoding is configured in the MemoriesManager
        if max_chars == -1:
            max_chars = self.agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_chars:
            raise ValueError(
                f"Content for {memory_name} is too long. Max length is {max_chars} characters. " + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_name, content)


class ReadMemoryTool(Tool):
    """
    Read the content of a memory file. This tool should only be used if the information
    is relevant to the current task. You can infer whether the information
    is relevant from the memory file name.
    You should not read the same memory file multiple times in the same conversation.
    """

    def apply(self, memory_name: str) -> str:
        """
        Read the content of a memory. Should only be used if the information
        is relevant to the current task, with relevance inferred from the memory name.
        You should not read the same memory file multiple times in the same conversation.
        Use the "global/" prefix to read a memory shared across all projects (e.g., "global/my_memory").
        """
        return self.memories_manager.load_memory(memory_name)


class ListMemoriesTool(Tool):
    """
    List available memories. Any memory can be read using the `read_memory` tool.
    """

    def apply(self, topic: str = "") -> str:
        """
        List available memories, optionally filtered by topic.
        Use topic="global" to list only global (cross-project) memories.
        """
        return self._to_json(self.memories_manager.list_memories(topic))


class DeleteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Delete a memory file. Should only happen if a user asks for it explicitly,
    for example by saying that the information retrieved from a memory file is no longer correct
    or no longer relevant for the project.
    """

    def apply(self, memory_name: str) -> str:
        """
        Delete a memory, only call if instructed explicitly or permission was granted by the user.
        Use the "global/" prefix to delete a memory shared across all projects.
        """
        _check_global_edit_allowed(self, memory_name)
        return self.memories_manager.delete_memory(memory_name)


class RenameMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Renames or moves a memory. Moving between project and global scope is supported
    (e.g., renaming "global/foo" to "bar" moves it from global to project scope).
    """

    def apply(self, old_name: str, new_name: str) -> str:
        """
        Rename or move a memory, use "/" in the name to organize into topics.
        Use the "global/" prefix for global (cross-project) memories.
        """
        _check_global_edit_allowed(self, old_name)
        _check_global_edit_allowed(self, new_name)
        return self.memories_manager.rename_memory(old_name, new_name)


class EditMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Replaces content matching a regular expression in a memory.
    """

    def apply(
        self,
        memory_name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
    ) -> str:
        r"""
        Replaces content matching a regular expression in a memory.

        :param memory_name: the name of the memory
        :param needle: the string or regex pattern to search for.
            If `mode` is "literal", this string will be matched exactly.
            If `mode` is "regex", this string will be treated as a regular expression (syntax of Python's `re` module,
            with flags DOTALL and MULTILINE enabled).
        :param repl: the replacement string (verbatim).
        :param mode: either "literal" or "regex", specifying how the `needle` parameter is to be interpreted.
        """
        _check_global_edit_allowed(self, memory_name)
        return self.memories_manager.edit_memory(memory_name, needle, repl, mode)
