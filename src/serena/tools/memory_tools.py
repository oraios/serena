from typing import Literal

from serena.tools import ReplaceContentTool, Tool, ToolMarkerCanEdit


class WriteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Writes a named memory (for future reference) to Serena's project-specific memory store.
    """

    def apply(self, memory_name: str, content: str, max_chars: int = -1) -> str:
        """
        Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
        The memory name should be meaningful and can include "/" to organize into topics (e.g., "auth/login/logic").

        :param max_chars: the maximum number of characters to write. By default, determined by the config,
            change only if instructed to do so.
        """
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
    Reads the memory with the given name from Serena's project-specific memory store.
    """

    def apply(self, memory_name: str) -> str:
        """
        Read the content of a memory. Should only be used if the information
        is relevant to the current task, with relevance inferred from the memory name.
        You should not read the same memory file multiple times in the same conversation.
        """
        return self.memories_manager.load_memory(memory_name)


class ListMemoriesTool(Tool):
    """
    Lists memories in Serena's project-specific memory store.
    """

    def apply(self, topic: str = "") -> str:
        """
        List available memories, optionally filtered by topic.
        """
        return self._to_json(self.memories_manager.list_memories(topic))


class DeleteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Deletes a memory from Serena's project-specific memory store.
    """

    def apply(self, memory_name: str) -> str:
        """
        Delete a memory, only call if instructed explicitly or permission was granted by the user.
        """
        return self.memories_manager.delete_memory(memory_name)


class RenameMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Renames or moves a memory in Serena's project-specific memory store.
    """

    def apply(self, old_name: str, new_name: str) -> str:
        """
        Rename or move a memory, use "/" in the name to organize into topics.
        """
        return self.memories_manager.rename_memory(old_name, new_name)


class EditMemoryTool(Tool, ToolMarkerCanEdit):
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
        replace_content_tool = self.agent.get_tool(ReplaceContentTool)
        rel_path = self.memories_manager.get_memory_file_path(memory_name).relative_to(self.get_project_root())
        return replace_content_tool.replace_content(str(rel_path), needle, repl, mode=mode, require_not_ignored=False)
