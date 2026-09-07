# SPDX-License-Identifier: GPL-3.0-or-later

from typing import TYPE_CHECKING, Literal, cast

from serena.tools import Tool, ToolMarkerCanEdit

if TYPE_CHECKING:
    from serena.repl.api.mem_api import MemoryApi


class MemoryApiMixin:
    """
    Mixin for tools which delegate to the memory API.
    The API is imported locally, since the API module refers to the tools (as corresponding tools).
    """

    def _api(self) -> "MemoryApi":
        from serena.repl.api.mem_api import MemoryApi

        tool = cast(Tool, cast(object, self))
        return MemoryApi(tool.agent)


class WriteMemoryTool(Tool, ToolMarkerCanEdit, MemoryApiMixin):
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
        return self._api().write_memory(memory_name, content, max_chars)


class ReadMemoryTool(Tool, MemoryApiMixin):
    """
    Reads the content of a memory file.
    """

    def apply(self, memory_name: str) -> str:
        """
        Use to read a memory that is likely to be relevant to the current task, inferring relevance e.g. from the name.
        """
        return self._api().read_memory(memory_name)


class ListMemoriesTool(Tool, MemoryApiMixin):
    """
    Lists available memories.
    """

    def apply(self, topic: str = "") -> str:
        """
        Lists available memories, optionally filtered by topic.
        """
        return self._api().list_memories(topic).represent()


class DeleteMemoryTool(Tool, ToolMarkerCanEdit, MemoryApiMixin):
    """
    Delete a memory file.
    """

    def apply(self, memory_name: str) -> str:
        """
        Delete a memory, only call if instructed explicitly or permission was granted by the user.
        """
        return self._api().delete_memory(memory_name)


class RenameMemoryTool(Tool, ToolMarkerCanEdit, MemoryApiMixin):
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
        return self._api().rename_memory(old_name, new_name)


class EditMemoryTool(Tool, ToolMarkerCanEdit, MemoryApiMixin):
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
        return self._api().edit_memory(memory_name, needle, repl, mode, allow_multiple_occurrences)
