import json

from serena.tools import ReplaceRegexTool, Tool


class WriteMemoryTool(Tool):
    """
    Writes a named memory (for future reference) to Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str, content: str, max_answer_chars: int = -1) -> str:
        """
        Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
        The memory name should be meaningful.
        """
        # NOTE: utf-8 encoding is configured in the MemoriesManager
        if max_answer_chars == -1:
            max_answer_chars = self.agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_file_name} is too long. Max length is {max_answer_chars} characters. "
                + "Please make the content shorter."
            )

        return self.memories_manager.save_memory(memory_file_name, content)


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
        """
        return self.memories_manager.load_memory(memory_file_name)


class ListMemoriesTool(Tool):
    """
    Lists memories in Serena's project-specific memory store.
    """

    def apply(self) -> str:
        """
        List available memories. Any memory can be read using the `read_memory` tool.
        """
        return json.dumps(self.memories_manager.list_memories())


class DeleteMemoryTool(Tool):
    """
    Deletes a memory from Serena's project-specific memory store.
    """

    def apply(self, memory_file_name: str) -> str:
        """
        Delete a memory file. Should only happen if a user asks for it explicitly,
        for example by saying that the information retrieved from a memory file is no longer correct
        or no longer relevant for the project.
        """
        return self.memories_manager.delete_memory(memory_file_name)


class EditMemoryTool(Tool):
    def apply(
        self,
        memory_file_name: str,
        regex: str,
        repl: str,
    ) -> str:
        r"""
        Replaces content matching a regular expression in a memory.

        :param memory_file_name: the name of the memory
        :param regex: a Python-style regular expression (flags DOTALL and MULTILINE enabled, i.e.
            '.' matches all characters, multi-line matching is enabled).
            Apply the usual escaping as needed for reserved characters in Python-style regex.
        :param repl: the string to replace the matched content with, which may contain
            backreferences like \1, \2, etc. for groups matched by the regex.
            Insert new content verbatim, except for backslashes, which have to be escaped.
        """
        replace_regex_tool = self.agent.get_tool(ReplaceRegexTool)
        rel_path = self.memories_manager.get_memory_file_path(memory_file_name).relative_to(self.get_project_root())
        return replace_regex_tool.replace_regex(str(rel_path), regex, repl, require_not_ignored=False)
