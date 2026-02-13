from typing import Literal

from serena.tools import Tool, ToolMarkerCanEdit, ToolMarkerDoesNotRequireActiveProject


class WriteMemoryTool(Tool, ToolMarkerCanEdit, ToolMarkerDoesNotRequireActiveProject):
    """
    Writes a named memory (for future reference) to Serena's memory store.
    """

    def apply(
        self,
        memory_file_name: str,
        content: str,
        max_answer_chars: int = -1,
        scope: Literal["project", "global"] = "project",
    ) -> str:
        """
        Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
        The memory name should be meaningful.

        :param memory_file_name: the name of the memory file (without .md extension)
        :param content: the content to write to the memory file
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. -1 means the default value from the config will be used.
            Don't adjust unless there is really no other way to get the content required for the task.
        :param scope: "project" to write to project-specific memory (default), "global" to write to
            global memory shared across all projects (stored in ~/.serena/memories/).
        """
        # NOTE: utf-8 encoding is configured in the MemoriesManager
        if max_answer_chars == -1:
            max_answer_chars = self.agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_answer_chars:
            raise ValueError(
                f"Content for {memory_file_name} is too long. Max length is {max_answer_chars} characters. "
                + "Please make the content shorter."
            )

        manager = self._get_memories_manager_for_scope(scope)
        return manager.save_memory(memory_file_name, content)


class ReadMemoryTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Reads the memory with the given name from Serena's memory store.
    """

    def apply(
        self,
        memory_file_name: str,
        max_answer_chars: int = -1,
        scope: Literal["project", "global"] = "project",
    ) -> str:
        """
        Read the content of a memory file. This tool should only be used if the information
        is relevant to the current task. You can infer whether the information
        is relevant from the memory file name.
        You should not read the same memory file multiple times in the same conversation.

        :param memory_file_name: the name of the memory file (without .md extension)
        :param max_answer_chars: if the output is longer than this number of characters,
            no content will be returned. -1 means the default value from the config will be used.
            Don't adjust unless there is really no other way to get the content required for the task.
        :param scope: "project" to read from project-specific memory (default), "global" to read from
            global memory shared across all projects (stored in ~/.serena/memories/).
        """
        manager = self._get_memories_manager_for_scope(scope)
        return manager.load_memory(memory_file_name)


class ListMemoriesTool(Tool, ToolMarkerDoesNotRequireActiveProject):
    """
    Lists memories in Serena's memory store.
    """

    def apply(self, scope: Literal["project", "global", "all"] = "project") -> str:
        """
        List available memories. Any memory can be read using the `read_memory` tool.

        :param scope: "project" to list project-specific memories (default), "global" to list
            global memories shared across all projects, or "all" to list both scopes with clear labeling.
        """
        if scope == "all":
            result: dict[str, list[str]] = {}
            project = self.agent.get_active_project()
            if project is not None:
                result["project"] = project.memories_manager.list_memories()
            else:
                result["project"] = []
            result["global"] = self.global_memories_manager.list_memories()
            return self._to_json(result)
        manager = self._get_memories_manager_for_scope(scope)
        return self._to_json(manager.list_memories())


class DeleteMemoryTool(Tool, ToolMarkerCanEdit, ToolMarkerDoesNotRequireActiveProject):
    """
    Deletes a memory from Serena's memory store.
    """

    def apply(self, memory_file_name: str, scope: Literal["project", "global"] = "project") -> str:
        """
        Delete a memory file. Should only happen if a user asks for it explicitly,
        for example by saying that the information retrieved from a memory file is no longer correct
        or no longer relevant for the project.

        :param memory_file_name: the name of the memory file (without .md extension)
        :param scope: "project" to delete from project-specific memory (default), "global" to delete from
            global memory shared across all projects (stored in ~/.serena/memories/).
        """
        manager = self._get_memories_manager_for_scope(scope)
        return manager.delete_memory(memory_file_name)


class EditMemoryTool(Tool, ToolMarkerCanEdit, ToolMarkerDoesNotRequireActiveProject):
    def apply(
        self,
        memory_file_name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        scope: Literal["project", "global"] = "project",
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
        :param scope: "project" to edit project-specific memory (default), "global" to edit
            global memory shared across all projects (stored in ~/.serena/memories/).
        """
        manager = self._get_memories_manager_for_scope(scope)
        return manager.edit_memory(memory_file_name, needle, repl, mode)
