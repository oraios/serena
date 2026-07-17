import logging
from typing import Literal

from serena.tools import Tool, ToolMarkerCanEdit

log = logging.getLogger(__name__)


class WriteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Write some information (utf-8-encoded) about this project that can be useful for future tasks to a memory in md format.
    The memory name should be meaningful.
    """

    def apply(self, memory_name: str, content: str, max_chars: int = -1) -> str:
        """
        Write information about this project that can be useful for future tasks in md format.
        The name should be meaningful and can include "/" to organize into topics.
        If explicitly instructed, use the "global/" prefix for writing a memory that is shared across projects.
        References to other memories should be inside backticks and prefixed with mem:,
        e.g., `mem:auth`.

        :param memory_name: memory name
        :param content: memory content, utf8-encoded
        :param max_chars: see other tools
        """
        # NOTE: utf-8 encoding is configured in the MemoriesManager
        if max_chars == -1:
            max_chars = self.agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_chars:
            raise ValueError(
                f"Content for {memory_name} is too long. Max length is {max_chars} characters. " + "Please make the content shorter."
            )

        return self.memory_manager.save_memory(memory_name, content, is_tool_context=True)


class ReadMemoryTool(Tool):
    """
    Reads the content of a memory file.
    """

    def apply(self, memory_name: str) -> str:
        """
        Use to read a memory that is likely to be relevant to the current task, inferring relevance e.g. from the name.
        """
        return self.memory_manager.load_memory(memory_name)


class ListMemoriesTool(Tool):
    """
    Lists available memories.
    """

    def apply(self, topic: str = "") -> str:
        """
        Lists available memories, optionally filtered by topic.
        """
        return self._to_json(self.memory_manager.list_memories(topic).to_dict())


class DeleteMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Delete a memory file.
    """

    def apply(self, memory_name: str) -> str:
        """
        Delete a memory, only call if instructed explicitly or permission was granted by the user.
        """
        return self.memory_manager.delete_memory(memory_name, is_tool_context=True)


class RenameMemoryTool(Tool, ToolMarkerCanEdit):
    """
    Renames or moves a memory, updating references that are marked with the `mem:` prefix.
    """

    def apply(self, old_name: str, new_name: str) -> str:
        """
        Rename or move a memory, use "/" in the name to organize into topics.
        The "global" topic should only be used if explicitly instructed.
        References to other memories that are marked with the `mem:` prefix will be updated accordingly.
        References in read-only memories are not affected.
        """
        renaming_message, n_references_updated = self.memory_manager.rename_memory_and_propagate_references(
            old_name, new_name, is_tool_context=True
        )
        if n_references_updated > 0:
            log.info(f"Updated {n_references_updated} references to memory {old_name} to {new_name}")
        return renaming_message


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
        allow_multiple_occurrences: bool = False,
    ) -> str:
        r"""
        Replace content matching a regular expression in a memory.

        :param memory_name: the name of the memory
        :param needle: the string or regex pattern to search for. In regex mode, be careful to not replace too much!
            If `mode` is "literal", this string will be matched exactly.
            If `mode` is "regex", this string will be treated as a regular expression (syntax of Python's `re` module,
            with the MULTILINE and DOTALL flags enabled).
        :param repl: the replacement string (verbatim).
        :param mode: either "literal" or "regex", specifying how the `needle` parameter is to be interpreted.
        :param allow_multiple_occurrences: whether to allow matching and replacing multiple occurrences.
            If false and multiple occurrences are found, an error will be returned.
        """
        return self.memory_manager.edit_memory(
            memory_name, needle, repl, mode, allow_multiple_occurrences, is_tool_context=True, regex_multiline=True
        )
