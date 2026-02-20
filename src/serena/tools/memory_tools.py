from typing import Literal, Optional

from serena.tools import ReplaceContentTool, Tool, ToolMarkerCanEdit


class WriteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Writes a named memory (for future reference) to Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, content: str, summary: Optional[str] = None, max_answer_chars: int = -1) -> str:
        """
        Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
        The memory name should be meaningful and can include "/" to organize into subdirectories (e.g., "auth/login_logic").
        
        :param memory_file_name: the name of the memory (can include "/" for subdirectories)
        :param content: the content to write in markdown format
        :param summary: optional summary for frontmatter (helps with memory discovery)
        :param max_answer_chars: maximum characters allowed (default from config)
        """
        # NOTE: utf-8 encoding is configured in the MemoriesManager
        if max_answer_chars == -1:
            max_answer_chars = self.agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_file_name} is too long. Max length is {max_answer_chars} characters. "
                + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_file_name, content, summary)


class ReadMemoryTool(Tool):
    """
    Reads the memory with the given name from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, max_answer_chars: int = -1) -> str:
        """
        Read the content of a memory file. This tool should only be used if the information
        is relevant to the current task. You can infer whether the information
        is relevant from the memory file name.
        You should not read the same memory file multiple times in the same conversation.
        
        :param memory_file_name: the name of the memory (can include "/" for subdirectories)
        :param max_answer_chars: maximum characters to return (default from config)
        """
        return self.memories_manager.load_memory(memory_file_name)


class ListMemoriesTool(Tool):
    """
    Lists memories in Serena's project-specific memory store.
    """

    def apply(self, topic: str = "") -> str:
        """
        List available memories. Any memory can be read using the `read_memory` tool.
        
        Organize memories into meaningful subdirectories (e.g., "auth/login_logic", 
        "database/schema"). Add a summary to the frontmatter for important memories.
        
        :param topic: optional topic/subdirectory filter (e.g., "auth" to list only auth memories)
        """
        return self._to_json(self.memories_manager.list_memories(topic))


class DeleteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Deletes a memory from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str) -> str:
        """
        Delete a memory file. Should only happen if a user asks for it explicitly,
        for example by saying that the information retrieved from a memory file is no longer correct
        or no longer relevant for the project.
        
        :param memory_file_name: the name of the memory to delete
        """
        return self.memories_manager.delete_memory(memory_file_name)


class RenameMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Renames or moves a memory in Serena's project-specific memory store.
    """

    def apply(self, old_name: str, new_name: str) -> str:
        """
        Rename or move a memory file. Use "/" in the name to organize memories into subdirectories.
        
        Example: "auth/login" will create auth/login.md
        
        This tool is useful for reorganizing existing memories into a better structure.
        
        :param old_name: current memory name
        :param new_name: new memory name (can include "/" for subdirectories)
        """
        return self.memories_manager.rename_memory(old_name, new_name)


class EditMemoryTool(Tool, ToolMarkerCanEdit):
    def apply(
        self,
        memory_file_name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
    ) -> str:
        r"""
        Replaces content matching a regular expression in a memory.

        :param memory_file_name: the name of the memory
        :param needle: the string or regex pattern to search for.
            If `mode` is "literal", this string will be matched exactly.
            If `mode` is "regex", this string will be treated as a regular expression (syntax of Python's `re` module,
            with flags DOTALL and MULTILINE enabled).
        :param repl: the replacement string (verbatim).
        :param mode: either "literal" or "regex", specifying how the `needle` parameter is to be interpreted.
        """
        replace_content_tool = self.agent.get_tool(ReplaceContentTool)
        rel_path = self.memories_manager.get_memory_file_path(memory_file_name).relative_to(self.get_project_root())
        return replace_content_tool.replace_content(str(rel_path), needle, repl, mode=mode, require_not_ignored=False)
