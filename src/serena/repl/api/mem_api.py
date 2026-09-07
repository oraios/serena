# SPDX-License-Identifier: GPL-3.0-or-later
"""
The implementation of memory operations (and onboarding, which creates the initial memories).
"""

import logging
import platform
from typing import TYPE_CHECKING, Literal

from serena.memories.memory_manager import MemoryManager

from ..facade import FacadeApi, facade_method
from ..representable import Renderer, RepresentableViaRenderer

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

log = logging.getLogger(__name__)


class MemoryList(RepresentableViaRenderer):
    """
    The available memories: `memories` (writable) and `read_only_memories` (e.g. global memories), each a list of names.
    """

    def __init__(self, memories_list: MemoryManager.MemoriesList, renderer: "MemoryListRenderer"):
        """
        :param memories_list: the list of memories
        :param renderer: the renderer to use for representing the list
        """
        super().__init__(renderer)
        self.memories_list_ = memories_list

    @property
    def memories(self) -> list[str]:
        return sorted(self.memories_list_.memories)

    @property
    def read_only_memories(self) -> list[str]:
        return sorted(self.memories_list_.read_only_memories)


class MemoryListRenderer(Renderer[MemoryList]):
    def render(self, obj: MemoryList) -> str:
        return self._limit_length(self._to_json(obj.memories_list_.to_dict()))


class MemoryApi(FacadeApi):
    def __init__(self, agent: "SerenaAgent") -> None:
        super().__init__(
            agent,
            name="mem",
            description="project memories, i.e. persistent notes for future tasks",
        )

    def _get_memory_manager(self) -> MemoryManager:
        return self._get_project().memory_manager

    @facade_method()
    def list_memories(self, topic: str = "") -> MemoryList:
        """
        Lists the available memories, optionally filtered by topic.

        :param topic: the topic (prefix of the memory name, e.g. "frontend") to restrict the listing to; empty for all memories
        :return: the memories
        """
        return MemoryList(self._get_memory_manager().list_memories(topic), MemoryListRenderer(self._agent, -1))

    @facade_method()
    def read_memory(self, memory_name: str) -> str:
        """
        Reads a memory that is likely to be relevant to the current task, inferring relevance e.g. from the name.

        :param memory_name: the name of the memory
        :return: the memory's content
        """
        return self._get_memory_manager().load_memory(memory_name)

    @facade_method(can_edit=True)
    def write_memory(self, memory_name: str, content: str, max_chars: int = -1) -> str:
        """
        Writes information about this project that can be useful for future tasks in md format.
        The name should be meaningful and can include "/" to organize into topics.
        If explicitly instructed, use the "global/" prefix for writing a memory that is shared across projects.
        References to other memories should be inside backticks and prefixed with mem:,
        e.g., `mem:auth`.

        :param memory_name: the memory name
        :param content: the memory content (utf-8-encoded markdown)
        :param max_chars: the maximum content length; -1 for the configured default
        :return: a message indicating the result
        """
        if max_chars == -1:
            max_chars = self._agent.serena_config.default_max_tool_answer_chars
        if len(content) > max_chars:
            raise ValueError(
                f"Content for {memory_name} is too long. Max length is {max_chars} characters. Please make the content shorter."
            )
        return self._get_memory_manager().save_memory(memory_name, content, is_tool_context=True)

    @facade_method(can_edit=True)
    def edit_memory(
        self,
        memory_name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool = False,
    ) -> str:
        """
        Replaces content matching a pattern in a memory.

        :param memory_name: the name of the memory
        :param needle: the string or regex pattern to search for. In regex mode, be careful to not replace too much!
            If `mode` is "literal", this string will be matched exactly.
            If `mode` is "regex", this string will be treated as a regular expression (syntax of Python's `re` module,
            with the MULTILINE and DOTALL flags enabled).
        :param repl: the replacement string (verbatim).
        :param mode: either "literal" or "regex", specifying how the `needle` parameter is to be interpreted.
        :param allow_multiple_occurrences: whether to allow matching and replacing multiple occurrences.
            If false and multiple occurrences are found, an error will be raised.
        :return: a message indicating the result
        """
        return self._get_memory_manager().edit_memory(
            memory_name, needle, repl, mode, allow_multiple_occurrences, is_tool_context=True, regex_multiline=True
        )

    @facade_method(can_edit=True)
    def rename_memory(self, old_name: str, new_name: str) -> str:
        """
        Renames or moves a memory; use "/" in the name to organize into topics.
        The "global" topic should only be used if explicitly instructed.
        References to other memories that are marked with the `mem:` prefix will be updated accordingly.
        References in read-only memories are not affected.

        :param old_name: the current name of the memory
        :param new_name: the new name of the memory
        :return: a message indicating the result
        """
        renaming_message, n_references_updated = self._get_memory_manager().rename_memory_and_propagate_references(
            old_name, new_name, is_tool_context=True
        )
        if n_references_updated > 0:
            log.info(f"Updated {n_references_updated} references to memory {old_name} to {new_name}")
        return renaming_message

    @facade_method(can_edit=True)
    def delete_memory(self, memory_name: str) -> str:
        """
        Deletes a memory; only call this if instructed explicitly or permission was granted by the user.

        :param memory_name: the name of the memory
        :return: a message indicating the result
        """
        return self._get_memory_manager().delete_memory(memory_name, is_tool_context=True)

    @facade_method()
    def onboarding(self) -> str:
        """
        Provides the instructions for performing onboarding (identifying the project structure and essential tasks,
        e.g. for testing or building, and recording the findings in memories).
        Call this if onboarding was not performed yet, at most once per conversation.

        :return: the instructions on how to create the onboarding information
        """
        # seed the project-local memory-maintenance memory (or detect a global override) so
        # the prompt can point the agent at the conventions before it writes anything
        memory_maintenance_name = self._get_memory_manager().ensure_memory_maintenance_memory()
        return self._agent.prompt_factory.create_onboarding_prompt(
            system=platform.system(), memory_maintenance_name=memory_maintenance_name
        )
