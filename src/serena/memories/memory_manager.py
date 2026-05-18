import logging
import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from serena.config.serena_config import (
    SerenaPaths,
)
from serena.constants import SERENA_FILE_ENCODING
from serena.util.text_utils import ContentReplacer

from .memory_reference_analysis import (
    MEMORY_REF_PREFIX,
    AutofixReport,
    MemoryReferenceAnalyzer,
    ReferentialIntegrityReport,
)

log = logging.getLogger(__name__)


class MemoryManager:
    GLOBAL_TOPIC = "global"
    _global_memory_dir = SerenaPaths().global_memories_path
    _MEMORY_REF_PREFIX = MEMORY_REF_PREFIX

    def __init__(
        self,
        serena_data_folder: str | Path | None,
        read_only_memory_patterns: Sequence[str] = (),
        ignored_memory_patterns: Sequence[str] = (),
    ):
        """
        :param serena_data_folder: the absolute path to the project's .serena data folder
        :param read_only_memory_patterns: whether to allow writing global memories in tool execution contexts
        :param ignored_memory_patterns: regex patterns for memories to completely exclude from listing, reading, and writing.
            Matching memories will not appear in list_memories or activate_project output and cannot be accessed
            via read_memory or write_memory. Use read_file on the raw path to access ignored memory files.
        """
        self._project_memory_dir: Path | None = None
        if serena_data_folder is not None:
            self._project_memory_dir = Path(serena_data_folder) / "memories"
            self._project_memory_dir.mkdir(parents=True, exist_ok=True)
        self._encoding = SERENA_FILE_ENCODING
        self._read_only_memory_patterns = [re.compile(pattern) for pattern in set(read_only_memory_patterns)]
        self._ignored_memory_patterns = [re.compile(pattern) for pattern in set(ignored_memory_patterns)]

    def _is_read_only_memory(self, name: str) -> bool:
        for pattern in self._read_only_memory_patterns:
            if pattern.fullmatch(name):
                return True
        return False

    def _is_ignored_memory(self, name: str) -> bool:
        for pattern in self._ignored_memory_patterns:
            if pattern.fullmatch(name):
                return True
        return False

    def _check_not_ignored(self, name: str) -> None:
        if self._is_ignored_memory(name):
            raise ValueError(
                f"Memory '{name}' matches an ignored_memory_patterns pattern and cannot be accessed. "
                f"Use the read_file tool on the raw file path instead."
            )

    def _is_global(self, name: str) -> bool:
        return name == self.GLOBAL_TOPIC or name.startswith(self.GLOBAL_TOPIC + "/")

    @classmethod
    def _sanitize_name(cls, name: str) -> str:
        """Corrects the name for common mistakes made by LLMs (``mem:`` prefix, ``.md`` suffix, OS-specific separators)."""
        name = name.removeprefix(cls._MEMORY_REF_PREFIX)
        if name.endswith(".md"):
            name = name[:-3]
        return name.replace(os.sep, "/")

    @classmethod
    def _add_reference_prefix(cls, name: str) -> str:
        name = cls._sanitize_name(name)
        return cls._MEMORY_REF_PREFIX + name

    MEMORY_MAINTENANCE_NAME: str = "memory_maintenance"
    _MEMORY_MAINTENANCE_TEMPLATE_PATH: Path = SerenaPaths().serena_resources_path / "memory_maintenance.md"

    def ensure_memory_maintenance_memory(self) -> str:
        """
        Ensures a memory describing how memories should be maintained exists for this project,
        and returns the name to reference it by.

        Precedence:

        1. If a global copy exists at ``global/memory_maintenance``, return that name; no
           project copy is created (the global version takes precedence).
        2. Else if a project copy already exists, return its name unchanged.
        3. Else seed a project copy from the package-shipped template and return that name.

        Existing memory files are never overwritten; users may have customized them. To
        refresh from the shipped template, delete the existing memory first.

        :return: the bare name to reference the maintenance memory by (without the ``mem:``
            prefix); either ``"global/memory_maintenance"`` or ``"memory_maintenance"``.
        :raises FileNotFoundError: if the shipped template is missing on disk.
        :raises AssertionError: if this manager has no associated project directory.
        """
        global_name = f"{self.GLOBAL_TOPIC}/{self.MEMORY_MAINTENANCE_NAME}"
        if self.get_memory_file_path(global_name).exists():
            return global_name
        if self.get_memory_file_path(self.MEMORY_MAINTENANCE_NAME).exists():
            return self.MEMORY_MAINTENANCE_NAME

        # seed a project copy from the shipped template
        template_path = self._MEMORY_MAINTENANCE_TEMPLATE_PATH
        if not template_path.exists():
            raise FileNotFoundError(f"Memory maintenance template not found at {template_path}")
        content = template_path.read_text(encoding=self._encoding)
        self.save_memory(self.MEMORY_MAINTENANCE_NAME, content, is_tool_context=False)
        return self.MEMORY_MAINTENANCE_NAME

    def rename_references_to_memory(self, content: str, old_name: str, new_name: str) -> tuple[str, int]:
        r"""
        Replaces all occurrences of a memory reference (e.g. ``mem:foo``) in ``content`` with
        the reference to ``new_name``.

        Matches only references whose name is exactly ``old_name``: the match must not be
        embedded in a longer memory name. A memory name consists of the character class
        ``[A-Za-z0-9_\\-/]`` (alphanumerics, underscore, hyphen, slash for topic separation),
        which determines the boundary of the match. The surrounding delimiters (backticks,
        quotes, parentheses, whitespace, etc.) are intentionally unconstrained.

        :param content: the text to search through
        :param old_name: the memory name being renamed away from (without the ``mem:`` prefix)
        :param new_name: the memory name being renamed to (without the ``mem:`` prefix)
        :return: a tuple of (updated content, number of replacements made)
        """
        # define the character class that constitutes a memory name; matches inside such a run are not real references
        name_char = r"[A-Za-z0-9_\-/]"
        ref_old = self._add_reference_prefix(old_name)
        ref_new = self._add_reference_prefix(new_name)

        # build a pattern that anchors the reference on both sides so it cannot be embedded inside a longer name
        pattern = rf"(?<!{name_char}){re.escape(ref_old)}(?!{name_char})"

        # use a callable replacement to avoid backreference interpretation of characters in ref_new
        return re.subn(pattern, lambda _m: ref_new, content)

    def get_memory_file_path(self, name: str) -> Path:
        name = self._sanitize_name(name)
        parts = name.split("/")
        if ".." in parts:
            raise ValueError(f"Memory name cannot contain '..' segments for security reasons. Got: {name}")

        if self._is_global(name):
            if name == self.GLOBAL_TOPIC:
                raise ValueError(
                    f'Bare "{self.GLOBAL_TOPIC}" is not a valid memory name. Use "{self.GLOBAL_TOPIC}/<name>" to address a global memory.'
                )
            # Strip "global/" prefix and resolve against global dir
            sub_name = name[len(self.GLOBAL_TOPIC) + 1 :]
            parts = sub_name.split("/")
            filename = f"{parts[-1]}.md"
            if len(parts) > 1:
                subdir = self._global_memory_dir / "/".join(parts[:-1])
                subdir.mkdir(parents=True, exist_ok=True)
                return subdir / filename
            return self._global_memory_dir / filename

        # Project-local memory
        assert self._project_memory_dir is not None, "Project dir was not passed at initialization"

        filename = f"{parts[-1]}.md"

        if len(parts) > 1:
            # Create subdirectory path
            subdir = self._project_memory_dir / "/".join(parts[:-1])
            subdir.mkdir(parents=True, exist_ok=True)
            return subdir / filename

        return self._project_memory_dir / filename

    def _check_write_access(self, name: str, is_tool_context: bool) -> None:
        # in tool context, memories can be read-only
        if is_tool_context and self._is_read_only_memory(name):
            raise PermissionError(f"Attempted to write to read_only memory: '{name}')")

    def load_memory(self, name: str) -> str:
        name = self._sanitize_name(name)
        self._check_not_ignored(name)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory file {name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding=self._encoding) as f:
            return f.read()

    def save_memory(self, name: str, content: str, is_tool_context: bool) -> str:
        name = self._sanitize_name(name)
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        with open(memory_file_path, "w", encoding=self._encoding) as f:
            f.write(content)
        return f"Memory {name} written."

    class MemoriesList:
        def __init__(self) -> None:
            self.memories: list[str] = []
            self.read_only_memories: list[str] = []

        def __len__(self) -> int:
            return len(self.memories) + len(self.read_only_memories)

        def add(self, memory_name: str, is_read_only: bool) -> None:
            if is_read_only:
                self.read_only_memories.append(memory_name)
            else:
                self.memories.append(memory_name)

        def extend(self, other: "MemoryManager.MemoriesList") -> None:
            self.memories.extend(other.memories)
            self.read_only_memories.extend(other.read_only_memories)

        def to_dict(self) -> dict[str, list[str]]:
            result = {}
            if self.memories:
                result["memories"] = sorted(self.memories)
            if self.read_only_memories:
                result["read_only_memories"] = sorted(self.read_only_memories)
            return result

        def get_full_list(self) -> list[str]:
            return sorted(self.memories + self.read_only_memories)

    def _list_memories(self, search_dir: Path, base_dir: Path, prefix: str = "") -> MemoriesList:
        result = self.MemoriesList()
        if not search_dir.exists():
            return result
        for md_file in search_dir.rglob("*.md"):
            rel = str(md_file.relative_to(base_dir).with_suffix("")).replace(os.sep, "/")
            memory_name = prefix + rel
            if self._is_ignored_memory(memory_name):
                continue
            result.add(memory_name, is_read_only=self._is_read_only_memory(memory_name))
        return result

    def list_global_memories(self, subtopic: str = "") -> MemoriesList:
        dir_path = self._global_memory_dir
        if subtopic:
            dir_path = dir_path / subtopic.replace("/", os.sep)
        return self._list_memories(dir_path, self._global_memory_dir, self.GLOBAL_TOPIC + "/")

    def list_project_memories(self, topic: str = "") -> MemoriesList:
        assert self._project_memory_dir is not None, "Project dir was not passed at initialization"
        dir_path = self._project_memory_dir
        if topic:
            dir_path = dir_path / topic.replace("/", os.sep)
        return self._list_memories(dir_path, self._project_memory_dir)

    def list_memories(self, topic: str = "") -> MemoriesList:
        """
        Lists all memories, optionally filtered by topic.
        If the topic is omitted, both global and project-specific memories are returned.
        """
        memories: MemoryManager.MemoriesList

        if topic:
            if self._is_global(topic):
                topic_parts = topic.split("/")
                subtopic = "/".join(topic_parts[1:])
                memories = self.list_global_memories(subtopic=subtopic)
            else:
                memories = self.list_project_memories(topic=topic)
        else:
            memories = self.list_project_memories()
            memories.extend(self.list_global_memories())

        return memories

    def delete_memory(self, name: str, is_tool_context: bool) -> str:
        name = self._sanitize_name(name)
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory {name} not found."
        memory_file_path.unlink()
        return f"Memory {name} deleted."

    def move_memory(self, old_name: str, new_name: str, is_tool_context: bool) -> str:
        """
        Rename or move a memory file.
        Moving between global and project scope (e.g. "global/foo" -> "bar") is supported.
        """
        old_name = self._sanitize_name(old_name)
        new_name = self._sanitize_name(new_name)
        self._check_not_ignored(old_name)
        self._check_not_ignored(new_name)
        self._check_write_access(new_name, is_tool_context)

        old_path = self.get_memory_file_path(old_name)
        new_path = self.get_memory_file_path(new_name)

        if not old_path.exists():
            raise FileNotFoundError(f"Memory {old_name} not found.")
        if new_path.exists():
            raise FileExistsError(f"Memory {new_name} already exists.")

        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(old_path, new_path)

        return f"Memory renamed from {old_name} to {new_name}."

    def rename_memory_and_propagate_references(self, old_name: str, new_name: str, is_tool_context: bool) -> tuple[str, int]:
        """
        Renames a memory and updates every ``mem:OLD_NAME`` reference across all memories.

        Memories whose content does not contain a reference to ``old_name`` are left
        untouched (no spurious mtime changes). Memories that do are rewritten via
        :meth:`save_memory`.

        :param old_name: the current memory name (the source of the rename)
        :param new_name: the target memory name
        :param is_tool_context: forwarded to :meth:`save_memory` for read-only enforcement
        :return: a tuple of (rename message returned by :meth:`move_memory`, total number of
            ``mem:`` reference occurrences rewritten across all memories).
        """
        renaming_message = self.move_memory(old_name, new_name, is_tool_context=is_tool_context)

        total_updates = 0
        for memory_name in self.list_memories().get_full_list():
            content = self.load_memory(memory_name)
            updated_content, n_replacements = self.rename_references_to_memory(content, old_name, new_name)
            if n_replacements > 0:
                self.save_memory(memory_name, updated_content, is_tool_context=is_tool_context)
                total_updates += n_replacements
        return renaming_message, total_updates

    def edit_memory(
        self,
        name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool,
        is_tool_context: bool,
        regex_multiline: bool = True,
    ) -> str:
        """
        Edit a memory by replacing content matching a pattern.

        :param name: the memory name
        :param needle: the string or regex to search for
        :param repl: the replacement string
        :param mode: "literal" or "regex"
        :param allow_multiple_occurrences:
        :param is_tool_context: whether the call originates from a tool invocation (affects write-access checks)
        :param regex_multiline: whether to apply multi-line regex matching, enabling the flags re.DOTALL and re.MULTILINE
        """
        name = self._sanitize_name(name)
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            raise FileNotFoundError(f"Memory {name} not found.")
        with open(memory_file_path, encoding=self._encoding) as f:
            original_content = f.read()
        replacer = ContentReplacer(mode=mode, allow_multiple_occurrences=allow_multiple_occurrences, regex_multiline=regex_multiline)
        updated_content = replacer.replace(original_content, needle, repl)
        with open(memory_file_path, "w", encoding=self._encoding) as f:
            f.write(updated_content)
        return f"Memory {name} edited successfully."

    def validate_referential_integrity(
        self, include_unmarked: bool = True, include_fuzzy_matching: bool = True
    ) -> ReferentialIntegrityReport:
        """
        Validates referential integrity across this manager's memories.

        Thin wrapper around :meth:`MemoryReferenceAnalyzer.validate_referential_integrity`;
        see that method for the full description of behavior and parameters.
        """
        return MemoryReferenceAnalyzer(self).validate_referential_integrity(
            include_unmarked=include_unmarked,
            include_fuzzy_matching=include_fuzzy_matching,
        )

    def auto_prefix_bare_references(
        self,
        include_flat_names: bool = False,
        include_read_only: bool = False,
        include_global: bool = False,
        dry_run: bool = False,
    ) -> AutofixReport:
        """
        Rewrites bare occurrences of existing memory names to include the ``mem:`` prefix.

        Thin wrapper around :meth:`MemoryReferenceAnalyzer.auto_prefix_bare_references`;
        see that method for the full description of behavior and parameters.
        """
        return MemoryReferenceAnalyzer(self).auto_prefix_bare_references(
            include_flat_names=include_flat_names,
            include_read_only=include_read_only,
            include_global=include_global,
            dry_run=dry_run,
        )
