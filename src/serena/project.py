import logging
import os
import re
import shutil
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

import pathspec
from sensai.util.logging import LogTime
from sensai.util.string import TextBuilder, ToStringMixin

from serena.config.serena_config import (
    ProjectConfig,
    SerenaConfig,
    SerenaPaths,
)
from serena.constants import SERENA_FILE_ENCODING
from serena.ls_manager import LanguageServerFactory, LanguageServerManager
from serena.util.file_system import GitignoreParser, match_path
from serena.util.text_utils import ContentReplacer, MatchedConsecutiveLines, search_files
from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language
from solidlsp.ls_utils import FileUtils

if TYPE_CHECKING:
    from serena.agent import SerenaAgent

log = logging.getLogger(__name__)


class MemoriesManager:
    GLOBAL_TOPIC = "global"
    _global_memory_dir = SerenaPaths().global_memories_path
    _MEMORY_REF_PREFIX = "mem:"

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
    def _prepare_name(cls, name: str) -> str:
        """Corrects the name for common mistakes made by LLMs (``mem:`` prefix, ``.md`` suffix, OS-specific separators)."""
        name = name.removeprefix(cls._MEMORY_REF_PREFIX)
        if name.endswith(".md"):
            name = name[:-3]
        return name.replace(os.sep, "/")

    @classmethod
    def _add_reference_prefix(cls, name: str) -> str:
        name = cls._prepare_name(name)
        return cls._MEMORY_REF_PREFIX + name

    MEMORY_MAINTENANCE_NAME: str = "memory_maintenance"
    _MEMORY_MAINTENANCE_TEMPLATE_PATH: Path = Path(__file__).parent / "resources" / "memory_maintenance.md"

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

    NAME_SIMILARITY_THRESHOLD: float = 0.55
    _HIGH_CONFIDENCE_NAME_LENGTH: int = 10
    _SHORT_NAME_FLOOR: int = 3
    # For fuzzy bare-text matching (validate_referential_integrity), an additional safeguard:
    # the bare token and the candidate existing name must share at least this fraction of their
    # tokenized name parts. Containment / SequenceMatcher signals alone over-match — e.g. a
    # generic prose word like "repository" is a substring of "serena_repository_structure"
    # but their token Jaccard is only 1/3, so we reject it at this floor.
    _FUZZY_BARE_TOKEN_JACCARD_FLOOR: float = 0.5
    _VERSION_SUFFIX_PATTERN = re.compile(r"_(?:v\d+|old|new|legacy|bak)$", re.IGNORECASE)

    @classmethod
    def _normalize_for_similarity(cls, name: str) -> str:
        """
        :param name: a memory name
        :return: a lowercased copy of ``name`` with version/legacy-style trailing suffixes stripped
            (e.g. ``"auth_v2"`` -> ``"auth"``); used as the canonical form for similarity scoring.
        """
        return cls._VERSION_SUFFIX_PATTERN.sub("", name.lower())

    @classmethod
    def _tokenize_name(cls, name: str) -> set[str]:
        """
        :param name: a memory name
        :return: the set of lowercase tokens extracted by splitting ``name`` on ``/``, ``_``, ``-``
            and at camelCase boundaries; empty tokens are dropped.
        """
        # split on path/word separators and at camelCase boundaries
        parts = re.split(r"[/_\-]|(?<=[a-z])(?=[A-Z])", name)
        return {p.lower() for p in parts if p}

    @classmethod
    def compute_name_similarity(cls, a: str, b: str) -> float:
        """
        Computes a similarity score in ``[0, 1]`` between two memory names. Examples
        (with default threshold ``0.55``)::

            auth/login        == auth/login          -> 1.00   (exact)
            auth_v1           ~  auth_v2             -> 1.00   (version suffix normalized)
            login             ~  auth/login          -> 1.00   (flat <-> topic move)
            auth/login        ~  auth/v2/login       -> 0.75   (shared prefix token + basename)
            auth/login        ~  security/login      -> 0.50   (basename only; disjoint topics)
            auth              ~  authentication      -> 0.64   (substring containment)
            foo               ~  for                 -> 0.00   (short-name floor)

        :param a: first memory name
        :param b: second memory name
        :return: the similarity score
        """
        # normalize: lowercase + strip version/legacy suffixes
        norm_a, norm_b = cls._normalize_for_similarity(a), cls._normalize_for_similarity(b)
        if norm_a == norm_b:
            return 1.0

        # split into prefix / basename
        basename_a = norm_a.rsplit("/", 1)[-1]
        basename_b = norm_b.rsplit("/", 1)[-1]
        prefix_a = norm_a.rsplit("/", 1)[0] if "/" in norm_a else ""
        prefix_b = norm_b.rsplit("/", 1)[0] if "/" in norm_b else ""

        # case 1: basenames match -- score is determined entirely by prefix relationship
        if basename_a == basename_b:
            if not prefix_a or not prefix_b:
                # one side is flat -> canonical topic move, strongly confident
                return 1.0
            # both sides carry a topic prefix -> blend basename match (0.5 floor) with prefix token similarity
            prefix_tokens_a, prefix_tokens_b = cls._tokenize_name(prefix_a), cls._tokenize_name(prefix_b)
            prefix_jaccard = (
                len(prefix_tokens_a & prefix_tokens_b) / len(prefix_tokens_a | prefix_tokens_b)
                if (prefix_tokens_a | prefix_tokens_b)
                else 0.0
            )
            return 0.5 + 0.5 * prefix_jaccard

        # case 2: basenames differ -- combine generic similarity signals via max
        tokens_a, tokens_b = cls._tokenize_name(norm_a), cls._tokenize_name(norm_b)
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b) if (tokens_a | tokens_b) else 0.0
        seq = SequenceMatcher(None, norm_a, norm_b).ratio()
        # containment is a meaningful rename signal on its own (e.g. auth -> authentication),
        # so we lift it above the threshold floor when one name fully contains the other,
        # with the length-ratio gating how confident we are
        contained = 0.0
        if norm_a and norm_b and (norm_a in norm_b or norm_b in norm_a):
            length_ratio = min(len(norm_a), len(norm_b)) / max(len(norm_a), len(norm_b))
            contained = 0.5 + 0.5 * length_ratio

        # short-name floor: for very short names, only accept candidates with a strong token signal
        if min(len(norm_a), len(norm_b)) <= cls._SHORT_NAME_FLOOR and jaccard < 1.0:
            return 0.0
        return max(jaccard, seq, contained)

    @classmethod
    def _find_stale_reference_candidates(cls, missing_name: str, existing_names: list[str], threshold: float | None = None) -> list[str]:
        """
        :param missing_name: the unresolved reference target (without the ``mem:`` prefix).
        :param existing_names: the names of all currently existing memories.
        :param threshold: optional override for the minimum similarity required; defaults to
            :attr:`NAME_SIMILARITY_THRESHOLD`.
        :return: existing memory names whose similarity to ``missing_name`` meets or exceeds
            ``threshold``, sorted in descending order of similarity (ties broken alphabetically).
        """
        cutoff = cls.NAME_SIMILARITY_THRESHOLD if threshold is None else threshold
        scored: list[tuple[float, str]] = []
        for existing in existing_names:
            score = cls.compute_name_similarity(missing_name, existing)
            if score >= cutoff:
                scored.append((score, existing))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [name for _, name in scored]

    # character class delimiting a memory name; used to anchor regex matches so we never
    # consume a partial name (kept in sync with the boundary rule in rename_references_to_memory)
    _NAME_CHAR_CLASS: str = r"[A-Za-z0-9_\-/]"

    @classmethod
    def _iter_referenced_names_in_content(cls, content: str) -> Iterator[str]:
        """
        :param content: arbitrary memory content
        :return: an iterator over the memory names appearing as ``mem:NAME`` references in
            ``content``; duplicate occurrences are yielded once each.
        """
        # use the same boundary rule as rename_references_to_memory so the two stay consistent
        pattern = rf"(?<!{cls._NAME_CHAR_CLASS}){re.escape(cls._MEMORY_REF_PREFIX)}({cls._NAME_CHAR_CLASS}+?)(?!{cls._NAME_CHAR_CLASS})"
        for match in re.finditer(pattern, content):
            yield match.group(1)

    @classmethod
    def _find_bare_occurrences(cls, content: str, name: str) -> int:
        """
        :param content: arbitrary memory content
        :param name: a memory name to look for
        :return: the count of bare (i.e. not already ``mem:``-prefixed) word-boundary-anchored
            occurrences of ``name`` in ``content``. The match must not be preceded by ``mem:``
            and must not be embedded within a longer memory-name-like run of characters.
        """
        # negative lookbehind for the mem: prefix prevents double-counting valid references;
        # the additional name-char lookbehind/lookahead prevents matching inside longer names
        pattern = (
            rf"(?<!{re.escape(cls._MEMORY_REF_PREFIX)})"
            rf"(?<!{cls._NAME_CHAR_CLASS})"
            rf"{re.escape(name)}"
            rf"(?!{cls._NAME_CHAR_CLASS})"
        )
        return len(re.findall(pattern, content))

    @classmethod
    def _add_bare_occurrences_prefix(cls, content: str, name: str) -> tuple[str, int]:
        """
        :param content: arbitrary memory content
        :param name: the memory name whose bare occurrences should be rewritten
        :return: ``(new_content, n_replacements)`` after prefixing each bare occurrence of
            ``name`` with ``mem:`` (using the same boundary rule as
            :meth:`_find_bare_occurrences`).
        """
        pattern = (
            rf"(?<!{re.escape(cls._MEMORY_REF_PREFIX)})"
            rf"(?<!{cls._NAME_CHAR_CLASS})"
            rf"{re.escape(name)}"
            rf"(?!{cls._NAME_CHAR_CLASS})"
        )
        replacement = cls._MEMORY_REF_PREFIX + name
        return re.subn(pattern, lambda _m: replacement, content)

    @classmethod
    def _iter_long_bare_tokens(cls, content: str) -> Iterator[tuple[str, int]]:
        """
        :param content: arbitrary memory content
        :return: an iterator over ``(token, count)`` pairs for each distinct name-shaped
            token in ``content`` whose length meets :attr:`_HIGH_CONFIDENCE_NAME_LENGTH`
            and which is not preceded by ``mem:`` (those are already valid references).
            The boundaries follow :attr:`_NAME_CHAR_CLASS`, so embedded substrings of
            longer name-character runs are not matched.
        """
        # require minimum length so we only scan tokens that are unlikely to be coincidental prose
        pattern = (
            rf"(?<!{re.escape(cls._MEMORY_REF_PREFIX)})"
            rf"(?<!{cls._NAME_CHAR_CLASS})"
            rf"({cls._NAME_CHAR_CLASS}{{{cls._HIGH_CONFIDENCE_NAME_LENGTH},}})"
            rf"(?!{cls._NAME_CHAR_CLASS})"
        )
        counts: dict[str, int] = {}
        for match in re.finditer(pattern, content):
            token = match.group(1)
            counts[token] = counts.get(token, 0) + 1
        return iter(counts.items())

    def get_memory_file_path(self, name: str) -> Path:
        name = self._prepare_name(name)
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
        name = self._prepare_name(name)
        self._check_not_ignored(name)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            return f"Memory file {name} not found, consider creating it with the `write_memory` tool if you need it."
        with open(memory_file_path, encoding=self._encoding) as f:
            return f.read()

    def save_memory(self, name: str, content: str, is_tool_context: bool) -> str:
        name = self._prepare_name(name)
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

        def extend(self, other: "MemoriesManager.MemoriesList") -> None:
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

    @dataclass(frozen=True)
    class StaleReference:
        """
        A ``mem:NAME`` reference whose target memory does not exist.

        :ivar source_memory: the name of the memory whose content contains the broken reference.
        :ivar referenced_name: the name following ``mem:`` that did not resolve to an existing memory.
        :ivar candidates: existing memory names proposed as likely intended targets, ranked by
            decreasing similarity. May be empty if no candidate exceeded the similarity threshold.
        :ivar source_is_read_only: whether the source memory is read-only.
        """

        source_memory: str
        referenced_name: str
        candidates: list[str]
        source_is_read_only: bool

    @dataclass(frozen=True)
    class UnmarkedReferenceWarning:
        """
        A bare occurrence in a memory's content that looks like a forgotten reference to an
        existing memory.

        Two flavours of finding share this class:

        * **exact match** — the bare text equals an existing memory name verbatim
          (``actual_token`` either equals ``suspected_name`` or is left empty).
        * **fuzzy near-miss** — the bare text does not equal any existing memory name, but
          a long, distinctive token in the body similarity-matches a high-confidence existing
          memory name (``actual_token`` is the bare text actually found, distinct from
          ``suspected_name``). Such findings are reported but **not** rewritten by
          :meth:`auto_prefix_bare_references`, since they would require substring
          substitution rather than a prefix addition.

        :ivar source_memory: the name of the memory whose content contains the bare occurrence.
        :ivar suspected_name: the existing memory name proposed as the intended target.
        :ivar occurrences: the number of occurrences of ``actual_token`` in the source memory's content.
        :ivar is_high_confidence: True when ``suspected_name`` contains a ``/`` separator or
            exceeds the configured length threshold; such names are unlikely to coincide with
            ordinary prose. False otherwise (a low-confidence warning).
        :ivar source_is_read_only: whether the source memory is read-only.
        :ivar actual_token: the bare text actually found in the source memory's content.
            Defaults to ``""``, which is taken to mean ``suspected_name`` (the exact-match case).
            When non-empty and different from ``suspected_name``, this is a fuzzy near-miss.
        """

        source_memory: str
        suspected_name: str
        occurrences: int
        is_high_confidence: bool
        source_is_read_only: bool
        actual_token: str = ""

        @property
        def is_exact_match(self) -> bool:
            """:return: True iff the bare text in the body equals ``suspected_name`` (i.e. not a fuzzy near-miss)."""
            return self.actual_token == "" or self.actual_token == self.suspected_name

    @dataclass(frozen=True)
    class AutofixedReference:
        """
        A bare occurrence rewritten to include the ``mem:`` prefix.

        :ivar source_memory: the name of the memory whose content was modified.
        :ivar referenced_name: the memory name whose bare occurrences were prefixed.
        :ivar n_replacements: the number of bare occurrences replaced in the source memory.
        """

        source_memory: str
        referenced_name: str
        n_replacements: int

    @dataclass
    class ReferentialIntegrityReport:
        """
        Outcome of :meth:`MemoriesManager.validate_referential_integrity`.

        :ivar stale_references: ``mem:NAME`` references whose target memory does not exist.
        :ivar high_confidence_warnings: bare references whose suspected target name is unlikely
            to be coincidental prose (topic-path or sufficiently long).
        :ivar low_confidence_warnings: bare references whose suspected target name could plausibly
            appear in ordinary prose (short, flat names).
        """

        stale_references: list["MemoriesManager.StaleReference"] = field(default_factory=list)
        high_confidence_warnings: list["MemoriesManager.UnmarkedReferenceWarning"] = field(default_factory=list)
        low_confidence_warnings: list["MemoriesManager.UnmarkedReferenceWarning"] = field(default_factory=list)

        def is_clean(self) -> bool:
            """:return: True iff no stale references and no warnings of any confidence level were found."""
            return not (self.stale_references or self.high_confidence_warnings or self.low_confidence_warnings)

        def format(self) -> str:
            """:return: a human-readable rendering suitable for CLI display."""
            tb = TextBuilder()
            if self.is_clean():
                tb.with_line("✓ No referential integrity issues found.")
                return tb.build()

            # stale references — grouped by writable / read-only for clarity
            if self.stale_references:
                tb.with_line(f"Stale references ({len(self.stale_references)}):")
                for ref in self.stale_references:
                    ro_tag = " [read-only source]" if ref.source_is_read_only else ""
                    tb.with_line(f"  - `mem:{ref.referenced_name}` in `{ref.source_memory}`{ro_tag}")
                    if ref.candidates:
                        candidates_str = ", ".join(f"`mem:{c}`" for c in ref.candidates)
                        tb.with_line(f"    candidates: {candidates_str}")
                    else:
                        tb.with_line("    candidates: (none above similarity threshold)")
                tb.with_line("")

            # unmarked-reference warnings, split by confidence
            for label, warnings in (
                ("High-confidence unmarked references", self.high_confidence_warnings),
                ("Low-confidence unmarked references", self.low_confidence_warnings),
            ):
                if not warnings:
                    continue
                tb.with_line(f"{label} ({len(warnings)}):")
                for w in warnings:
                    ro_tag = " [read-only source]" if w.source_is_read_only else ""
                    occ = "occurrence" if w.occurrences == 1 else "occurrences"
                    if w.is_exact_match:
                        tb.with_line(
                            f"  - {w.occurrences} {occ} of `{w.suspected_name}` in `{w.source_memory}`{ro_tag}"
                            f" (suggested: `mem:{w.suspected_name}`)"
                        )
                    else:
                        # fuzzy near-miss: the bare text differs from the proposed target
                        tb.with_line(
                            f"  - {w.occurrences} {occ} of `{w.actual_token}` in `{w.source_memory}`{ro_tag}"
                            f" — near-miss (suggested: `mem:{w.suspected_name}`)"
                        )
                tb.with_line("")
            return tb.build()

    @dataclass
    class AutofixReport:
        """
        Outcome of :meth:`MemoriesManager.auto_prefix_bare_references`.

        :ivar autofixed: per-(source, target) records of bare references that were rewritten.
            When the call was a dry run, these records describe what *would* have been
            written; the files themselves are unchanged.
        :ivar dry_run: True if the run was a preview that did not write any files.
        :ivar skipped_read_only: warnings whose source memory was read-only and therefore not
            modified (only populated when ``include_read_only`` is False).
        :ivar skipped_flat: warnings skipped because their suspected target had no ``/``
            separator and was not long enough to be high-confidence (only populated when
            ``include_flat_names`` is False).
        :ivar skipped_global: warnings skipped because their source memory was global and
            ``include_global`` was False.
        :ivar skipped_fuzzy: warnings whose bare text in the source memory differs from the
            suspected target (fuzzy near-misses). These require substring substitution rather
            than a prefix addition and are never autofixed; surface them to the user for
            manual review instead.
        """

        autofixed: list["MemoriesManager.AutofixedReference"] = field(default_factory=list)
        dry_run: bool = False
        skipped_read_only: list["MemoriesManager.UnmarkedReferenceWarning"] = field(default_factory=list)
        skipped_flat: list["MemoriesManager.UnmarkedReferenceWarning"] = field(default_factory=list)
        skipped_global: list["MemoriesManager.UnmarkedReferenceWarning"] = field(default_factory=list)
        skipped_fuzzy: list["MemoriesManager.UnmarkedReferenceWarning"] = field(default_factory=list)

        @property
        def total_replacements(self) -> int:
            return sum(a.n_replacements for a in self.autofixed)

        def format(self) -> str:
            """:return: a human-readable rendering suitable for CLI display."""
            tb = TextBuilder()
            verb = "Would apply" if self.dry_run else "Applied"
            if self.autofixed:
                tb.with_line(
                    f"{verb} {self.total_replacements} replacement(s) across "
                    f"{len(self.autofixed)} memory/target pair(s)" + (" (dry run; no files were modified)" if self.dry_run else "") + ":"
                )
                for a in self.autofixed:
                    tb.with_line(f"  - {a.n_replacements} x `{a.referenced_name}` -> `mem:{a.referenced_name}` in `{a.source_memory}`")
                tb.with_line("")
            else:
                tb.with_line("No replacements" + (" would be" if self.dry_run else "") + " applied.")
                tb.with_line("")

            for label, items in (
                ("Skipped (read-only source; pass --include-read-only to override)", self.skipped_read_only),
                ("Skipped (flat name; pass --include-flat-names to include)", self.skipped_flat),
                ("Skipped (global memory; pass --include-global to include)", self.skipped_global),
                (
                    "Skipped (fuzzy near-miss; bare text differs from target name — not safe to auto-rewrite, review manually)",
                    self.skipped_fuzzy,
                ),
            ):
                if not items:
                    continue
                tb.with_line(f"{label}:")
                for w in items:
                    if w.is_exact_match:
                        tb.with_line(f"  - `{w.suspected_name}` in `{w.source_memory}`")
                    else:
                        tb.with_line(f"  - `{w.actual_token}` in `{w.source_memory}` (suggested: `mem:{w.suspected_name}`)")
                tb.with_line("")
            return tb.build()

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
        memories: MemoriesManager.MemoriesList

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
        name = self._prepare_name(name)
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
        old_name = self._prepare_name(old_name)
        new_name = self._prepare_name(new_name)
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

    def edit_memory(
        self,
        name: str,
        needle: str,
        repl: str,
        mode: Literal["literal", "regex"],
        allow_multiple_occurrences: bool,
        is_tool_context: bool,
        dotall: bool = True,
    ) -> str:
        """
        Edit a memory by replacing content matching a pattern.

        :param name: the memory name
        :param needle: the string or regex to search for
        :param repl: the replacement string
        :param mode: "literal" or "regex"
        :param allow_multiple_occurrences:
        :param is_tool_context: whether the call originates from a tool invocation (affects write-access checks)
        :param dotall: whether to compile the regex with the DOTALL flag (``.`` matches newlines). Only relevant in regex mode.
        """
        name = self._prepare_name(name)
        self._check_not_ignored(name)
        self._check_write_access(name, is_tool_context)
        memory_file_path = self.get_memory_file_path(name)
        if not memory_file_path.exists():
            raise FileNotFoundError(f"Memory {name} not found.")
        with open(memory_file_path, encoding=self._encoding) as f:
            original_content = f.read()
        replacer = ContentReplacer(mode=mode, allow_multiple_occurrences=allow_multiple_occurrences, dotall=dotall)
        updated_content = replacer.replace(original_content, needle, repl)
        with open(memory_file_path, "w", encoding=self._encoding) as f:
            f.write(updated_content)
        return f"Memory {name} edited successfully."

    def _is_self_reference(self, source_memory: str, suspected_name: str) -> bool:
        """
        :return: True iff ``suspected_name`` would refer to ``source_memory`` itself
            (including the case where ``suspected_name`` equals the basename of a topic-path
            source memory).
        """
        if suspected_name == source_memory:
            return True
        source_basename = source_memory.rsplit("/", 1)[-1]
        return suspected_name == source_basename

    def validate_referential_integrity(self) -> "MemoriesManager.ReferentialIntegrityReport":
        """
        Scans every (non-ignored) memory's content for referential integrity issues.

        The scan covers both project-local and global memories. Three kinds of finding are
        produced:

        * **stale references** — occurrences of ``mem:NAME`` where ``NAME`` does not resolve
          to an existing memory. For each, a list of similarly-named existing memories is
          proposed as candidate intended targets (see :meth:`compute_name_similarity`).
        * **exact unmarked-reference warnings** — bare occurrences of an existing memory
          name that appear without the ``mem:`` prefix. Split into high-confidence (the
          suspected name contains a ``/`` or exceeds :attr:`_HIGH_CONFIDENCE_NAME_LENGTH`)
          and low-confidence groups.
        * **fuzzy near-miss warnings** — long, distinctive bare tokens in a memory body
          that *do not* match an existing name exactly but similarity-match a
          high-confidence existing name AND share at least :attr:`_FUZZY_BARE_TOKEN_JACCARD_FLOOR`
          of their tokenized name parts (e.g. ``adding_new_language_support`` in prose when
          the memory is named ``adding_new_language_support_guide``). Always reported as
          high-confidence; the actual bare text is preserved on
          :attr:`UnmarkedReferenceWarning.actual_token`.

        Self-references (a memory's content mentioning its own name or basename) and empty
        memories are skipped silently.

        This method has no side effects.

        :return: a :class:`ReferentialIntegrityReport` summarizing all findings.
        """
        report = MemoriesManager.ReferentialIntegrityReport()

        # gather all existing memory names (project + global) with their read-only status
        memories_list = self.list_memories()
        all_names = sorted(set(memories_list.memories) | set(memories_list.read_only_memories))
        read_only_names = set(memories_list.read_only_memories)
        existing_set = set(all_names)
        # only existing names that are themselves "memory-name-like" qualify as fuzzy candidates,
        # otherwise short flat names would match arbitrary long prose words via containment
        high_confidence_names = [n for n in all_names if "/" in n or len(n) >= self._HIGH_CONFIDENCE_NAME_LENGTH]

        for source_name in all_names:
            content = self.load_memory(source_name)
            if not content:
                # skip empty memories silently — no references can exist in empty content
                continue
            source_is_read_only = source_name in read_only_names

            # stale references: every mem:NAME whose NAME is not an existing memory
            stale_seen: set[str] = set()
            for referenced in self._iter_referenced_names_in_content(content):
                if referenced in existing_set or referenced in stale_seen:
                    continue
                stale_seen.add(referenced)
                candidates = self._find_stale_reference_candidates(referenced, all_names)
                report.stale_references.append(
                    MemoriesManager.StaleReference(
                        source_memory=source_name,
                        referenced_name=referenced,
                        candidates=candidates,
                        source_is_read_only=source_is_read_only,
                    )
                )

            # exact unmarked references: bare occurrences of any existing memory name (except self)
            for candidate_name in all_names:
                if self._is_self_reference(source_name, candidate_name):
                    continue
                n = self._find_bare_occurrences(content, candidate_name)
                if n == 0:
                    continue
                is_high_conf = "/" in candidate_name or len(candidate_name) >= self._HIGH_CONFIDENCE_NAME_LENGTH
                warning = MemoriesManager.UnmarkedReferenceWarning(
                    source_memory=source_name,
                    suspected_name=candidate_name,
                    occurrences=n,
                    is_high_confidence=is_high_conf,
                    source_is_read_only=source_is_read_only,
                    actual_token=candidate_name,
                )
                if is_high_conf:
                    report.high_confidence_warnings.append(warning)
                else:
                    report.low_confidence_warnings.append(warning)

            # fuzzy near-misses: long bare tokens that similarity-match a high-confidence existing name
            for token, n in self._iter_long_bare_tokens(content):
                if token in existing_set:
                    # exact-match path already handled this token (or self-referenced and was skipped)
                    continue
                token_tokens = self._tokenize_name(token)
                best_name: str | None = None
                best_score = 0.0
                for existing in high_confidence_names:
                    if self._is_self_reference(source_name, existing):
                        continue
                    score = self.compute_name_similarity(token, existing)
                    if score < self.NAME_SIMILARITY_THRESHOLD:
                        continue
                    # safeguard against substring-only matches: require meaningful token overlap so
                    # generic prose words don't get flagged just because they happen to be substrings
                    # of an existing memory name
                    existing_tokens = self._tokenize_name(existing)
                    union = token_tokens | existing_tokens
                    if not union:
                        continue
                    jaccard = len(token_tokens & existing_tokens) / len(union)
                    if jaccard < self._FUZZY_BARE_TOKEN_JACCARD_FLOOR:
                        continue
                    if score > best_score:
                        best_score = score
                        best_name = existing
                if best_name is None:
                    continue
                report.high_confidence_warnings.append(
                    MemoriesManager.UnmarkedReferenceWarning(
                        source_memory=source_name,
                        suspected_name=best_name,
                        occurrences=n,
                        is_high_confidence=True,
                        source_is_read_only=source_is_read_only,
                        actual_token=token,
                    )
                )

        return report

    def auto_prefix_bare_references(
        self,
        include_flat_names: bool = False,
        include_read_only: bool = False,
        include_global: bool = False,
        dry_run: bool = False,
    ) -> "MemoriesManager.AutofixReport":
        """
        Rewrites *exact* bare occurrences of existing memory names by adding the ``mem:`` prefix.

        .. warning::
            **This is a heuristic, file-mutating operation** (unless ``dry_run`` is True). A
            bare word that happens to coincide with a memory name will be rewritten as a
            reference, even if it was intended as ordinary prose. Pass ``dry_run=True`` to
            preview the rewrites before applying them.

        Scope is intentionally narrower than what :meth:`validate_referential_integrity`
        reports:

        * Only **exact** bare occurrences are rewritten — i.e. the bare text in the source
          body must equal an existing memory name verbatim. Fuzzy near-miss findings
          (where the actual token differs from the suspected target) require substring
          substitution rather than a prefix addition and are routed into
          :attr:`AutofixReport.skipped_fuzzy` for manual review.
        * By default the rewrite is restricted to *high-confidence* findings only — those
          whose suspected target name contains a ``/`` separator or exceeds the
          configured length threshold — and skips global memories and read-only memories.
          The defaults intentionally err toward false negatives over false positives.

        :param include_flat_names: if True, also rewrite low-confidence findings (flat,
            short memory names). Increases recall but markedly raises false-positive risk.
        :param include_read_only: if True, also rewrite occurrences inside read-only
            memories. Use with care, as read-only memories are typically considered
            authoritative.
        :param include_global: if True, also rewrite occurrences inside global memories.
            Modifying a global memory affects every project that consumes it.
        :param dry_run: if True, the report describes the rewrites that *would* be applied
            but no files are modified.
        :return: an :class:`AutofixReport` describing every replacement (made or planned)
            and every warning that was deliberately skipped.
        """
        report = MemoriesManager.AutofixReport(dry_run=dry_run)

        # build the integrity report first so autofix decisions are made on the same data
        validation = self.validate_referential_integrity()

        # combine the warning groups according to the include_flat_names policy
        warnings: list[MemoriesManager.UnmarkedReferenceWarning] = list(validation.high_confidence_warnings)
        if include_flat_names:
            warnings.extend(validation.low_confidence_warnings)
        else:
            report.skipped_flat.extend(validation.low_confidence_warnings)

        # apply replacements per source memory, grouping warnings to avoid re-reading content
        warnings_by_source: dict[str, list[MemoriesManager.UnmarkedReferenceWarning]] = {}
        for w in warnings:
            # fuzzy near-misses are never auto-rewritten — the bare text differs from the target
            if not w.is_exact_match:
                report.skipped_fuzzy.append(w)
                continue
            # filter remaining warnings according to scope flags
            if w.source_is_read_only and not include_read_only:
                report.skipped_read_only.append(w)
                continue
            if self._is_global(w.source_memory) and not include_global:
                report.skipped_global.append(w)
                continue
            warnings_by_source.setdefault(w.source_memory, []).append(w)

        for source_memory, source_warnings in warnings_by_source.items():
            content = self.load_memory(source_memory)
            total_n = 0
            per_target_records: list[MemoriesManager.AutofixedReference] = []

            # apply replacements sequentially; each pass uses the (potentially updated) content
            for w in source_warnings:
                content, n = self._add_bare_occurrences_prefix(content, w.suspected_name)
                if n > 0:
                    per_target_records.append(
                        MemoriesManager.AutofixedReference(
                            source_memory=source_memory,
                            referenced_name=w.suspected_name,
                            n_replacements=n,
                        )
                    )
                    total_n += n

            if total_n > 0:
                if not dry_run:
                    # use is_tool_context=False so we don't trip read-only protection when --include-read-only is set
                    self.save_memory(source_memory, content, is_tool_context=False)
                report.autofixed.extend(per_target_records)

        return report


class Project(ToStringMixin):
    def __init__(
        self,
        *,
        project_root: str,
        project_config: ProjectConfig,
        serena_config: SerenaConfig,
        is_newly_created: bool = False,
    ):
        assert serena_config is not None
        self.project_root = project_root
        self.project_config = project_config
        self.serena_config = serena_config
        self._serena_data_folder = serena_config.get_project_serena_folder(self.project_root)
        log.info("Serena project data folder: %s", self._serena_data_folder)

        read_only_memory_patterns = serena_config.read_only_memory_patterns + project_config.read_only_memory_patterns
        ignored_memory_patterns = serena_config.ignored_memory_patterns + project_config.ignored_memory_patterns
        self.memories_manager = MemoriesManager(
            self._serena_data_folder,
            read_only_memory_patterns=read_only_memory_patterns,
            ignored_memory_patterns=ignored_memory_patterns,
        )

        # resolve line ending (project -> global)
        self.line_ending = project_config.line_ending or serena_config.line_ending

        self.language_server_manager: LanguageServerManager | None = None
        self._language_server_manager_init_error: Exception | None = None
        self.is_newly_created = is_newly_created
        self._agent: Optional["SerenaAgent"] = None

        # create .gitignore file in the project's Serena data folder if not yet present
        serena_data_gitignore_path = os.path.join(self._serena_data_folder, ".gitignore")
        if not os.path.exists(serena_data_gitignore_path):
            os.makedirs(os.path.dirname(serena_data_gitignore_path), exist_ok=True)
            log.info(f"Creating .gitignore file in {serena_data_gitignore_path}")
            with open(serena_data_gitignore_path, "w", encoding="utf-8") as f:
                f.write(f"/{SolidLanguageServer.CACHE_FOLDER_NAME}\n")
                f.write(f"/{ProjectConfig.SERENA_LOCAL_PROJECT_FILE}\n")

        # prepare ignore spec asynchronously, ensuring immediate project activation.
        self.__ignored_patterns: list[str] | None = None
        self.__ignore_spec: pathspec.PathSpec | None = None
        self._ignore_spec_available = threading.Event()
        threading.Thread(name=f"gather-ignorespec[{self.project_config.project_name}]", target=self._gather_ignorespec, daemon=True).start()

    def _gather_ignorespec(self) -> None:
        with LogTime(f"Gathering ignore spec for project {self.project_config.project_name}", logger=log):
            try:
                # gather ignored paths from the global configuration, project configuration, and gitignore files
                global_ignored_paths = self.serena_config.ignored_paths
                ignored_patterns = list(global_ignored_paths) + list(self.project_config.ignored_paths)
                if len(global_ignored_paths) > 0:
                    log.info(f"Using {len(global_ignored_paths)} ignored paths from the global configuration.")
                    log.debug(f"Global ignored paths: {list(global_ignored_paths)}")
                if len(self.project_config.ignored_paths) > 0:
                    log.info(f"Using {len(self.project_config.ignored_paths)} ignored paths from the project configuration.")
                    log.debug(f"Project ignored paths: {self.project_config.ignored_paths}")
                log.debug(f"Combined ignored patterns: {ignored_patterns}")
                if self.project_config.ignore_all_files_in_gitignore:
                    gitignore_parser = GitignoreParser(self.project_root)
                    for spec in gitignore_parser.get_ignore_specs():
                        log.debug(f"Adding {len(spec.patterns)} patterns from {spec.file_path} to the ignored paths.")
                        ignored_patterns.extend(spec.patterns)
                self.__ignored_patterns = ignored_patterns

                # Set up the pathspec matcher for the ignored paths
                # for all absolute paths in ignored_paths, convert them to relative paths
                processed_patterns = []
                for pattern in ignored_patterns:
                    # Normalize separators (pathspec expects forward slashes)
                    pattern = pattern.replace(os.path.sep, "/")
                    processed_patterns.append(pattern)
                log.debug(f"Processing {len(processed_patterns)} ignored paths")
                self.__ignore_spec = pathspec.PathSpec.from_lines(pathspec.patterns.GitWildMatchPattern, processed_patterns)
            except Exception as e:
                log.error(f"Error while gathering ignore spec for project {self.project_config.project_name}: {e}", exc_info=e)

        self._ignore_spec_available.set()

    def _tostring_includes(self) -> list[str]:
        return []

    def _tostring_additional_entries(self) -> dict[str, Any]:
        return {"root": self.project_root, "name": self.project_name}

    def set_agent(self, agent: "SerenaAgent") -> None:
        self._agent = agent

    @property
    def project_name(self) -> str:
        return self.project_config.project_name

    @classmethod
    def load(
        cls,
        project_root: str | Path,
        serena_config: "SerenaConfig",
        autogenerate: bool = True,
    ) -> "Project":
        assert serena_config is not None
        project_root = Path(project_root).resolve()
        if not project_root.exists():
            raise FileNotFoundError(f"Project root not found: {project_root}")
        project_config = ProjectConfig.load(project_root, serena_config=serena_config, autogenerate=autogenerate)
        return Project(project_root=str(project_root), project_config=project_config, serena_config=serena_config)

    def save_config(self) -> None:
        """
        Saves the current project configuration to disk.
        """
        self.project_config.save(self.path_to_project_yml())

    def path_to_serena_data_folder(self) -> str:
        return self._serena_data_folder

    def path_to_project_yml(self) -> str:
        return self.serena_config.get_project_yml_location(self.project_root)

    def read_file(self, relative_path: str) -> str:
        """
        Reads a file relative to the project root.

        :param relative_path: the path to the file relative to the project root
        :return: the content of the file
        """
        abs_path = Path(self.project_root) / relative_path
        return FileUtils.read_file(str(abs_path), self.project_config.encoding)

    @property
    def _ignore_spec(self) -> pathspec.PathSpec:
        """
        :return: the pathspec matcher for the paths that were configured to be ignored,
            either explicitly or implicitly through .gitignore files.
        """
        if not self._ignore_spec_available.is_set():
            log.info("Waiting for ignore spec to become available ...")
            self._ignore_spec_available.wait()
            if self.__ignore_spec is not None:
                log.info("Ignore spec is now available for project; proceeding")
        if self.__ignore_spec is None:
            raise ValueError(
                "The ignore spec could not be computed; please check the log for errors and report here: https://github.com/oraios/serena/issues"
            )
        return self.__ignore_spec

    @property
    def _ignored_patterns(self) -> list[str]:
        """
        :return: the list of ignored path patterns
        """
        if not self._ignore_spec_available.is_set():
            log.info("Waiting for ignored patterns to become available ...")
            self._ignore_spec_available.wait()
            if self.__ignored_patterns is not None:
                log.info("Ignored patterns are now available for project; proceeding")
        if self.__ignored_patterns is None:
            raise ValueError(
                "The ignored patterns could not be computed; please check the log for errors and report here: https://github.com/oraios/serena/issues"
            )
        return self.__ignored_patterns

    def _is_ignored_relative_path(self, relative_path: str | Path, ignore_non_source_files: bool = True) -> bool:
        """
        Determine whether an existing path should be ignored based on file type and ignore patterns.
        Raises `FileNotFoundError` if the path does not exist.

        :param relative_path: Relative path to check
        :param ignore_non_source_files: whether files that are not source files (according to the file masks
            determined by the project's programming language) shall be ignored

        :return: whether the path should be ignored
        """
        # special case, never ignore the project root itself
        # If the user ignores hidden files, "." might match against the corresponding PathSpec pattern.
        # The empty string also points to the project root and should never be ignored.
        if str(relative_path) in [".", ""]:
            return False

        abs_path = os.path.join(self.project_root, relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File {abs_path} not found, the ignore check cannot be performed")

        # Check file extension if it's a file
        is_file = os.path.isfile(abs_path)
        if is_file and ignore_non_source_files:
            is_file_in_supported_language = False
            for language in self.project_config.languages:
                fn_matcher = language.get_source_fn_matcher()
                if fn_matcher.is_relevant_filename(abs_path):
                    is_file_in_supported_language = True
                    break
            if not is_file_in_supported_language:
                return True

        # Create normalized path for consistent handling
        rel_path = Path(relative_path)

        # always ignore paths inside .git
        if len(rel_path.parts) > 0 and ".git" in rel_path.parts:
            return True

        return match_path(str(relative_path), self._ignore_spec, root_path=self.project_root)

    def is_ignored_path(self, path: str | Path, ignore_non_source_files: bool = False) -> bool:
        """
        Checks whether the given path is ignored

        :param path: the path to check, can be absolute or relative
        :param ignore_non_source_files: whether to ignore files that are not source files
            (according to the file masks determined by the project's programming language)
        """
        path = Path(path)
        if path.is_absolute():
            try:
                relative_path = path.relative_to(self.project_root)
            except ValueError:
                # If the path is not relative to the project root, we consider it as an absolute path outside the project
                # (which we ignore)
                log.warning(f"Path {path} is not relative to the project root {self.project_root} and was therefore ignored")
                return True
        else:
            relative_path = path

        return self._is_ignored_relative_path(str(relative_path), ignore_non_source_files=ignore_non_source_files)

    def is_path_in_project(self, path: str | Path) -> bool:
        """
        Checks if the given (absolute or relative) path is inside the project directory.

        Note: This is intended to catch cases where ".." segments would lead outside of the project directory,
        but we intentionally allow symlinks, as the assumption is that they point to relevant project files.
        """
        if not os.path.isabs(path):
            path = os.path.join(self.project_root, path)

        # collapse any ".." or "." segments (purely lexically)
        path = os.path.normpath(path)

        try:
            return os.path.commonpath([self.project_root, path]) == self.project_root
        except ValueError:
            # occurs, in particular, if paths are on different drives on Windows
            return False

    def relative_path_exists(self, relative_path: str) -> bool:
        """
        Checks if the given relative path exists in the project directory.

        :param relative_path: the path to check, relative to the project root
        :return: True if the path exists, False otherwise
        """
        abs_path = Path(self.project_root) / relative_path
        return abs_path.exists()

    def validate_relative_path(self, relative_path: str, require_not_ignored: bool = False) -> None:
        """
        Validates that the given relative path to an existing file/dir is safe to read or edit,
        meaning it's inside the project directory.

        Passing a path to a non-existing file will lead to a `FileNotFoundError`.

        :param relative_path: the path to validate, relative to the project root
        :param require_not_ignored: if True, the path must not be ignored according to the project's ignore settings
        """
        if not self.is_path_in_project(relative_path):
            raise ValueError(f"{relative_path=} points to path outside of the repository root; cannot access for safety reasons")

        if require_not_ignored:
            if self.is_ignored_path(relative_path):
                raise ValueError(f"Path {relative_path} is ignored; cannot access for safety reasons")

    def gather_source_files(self, relative_path: str = "") -> list[str]:
        """Retrieves relative paths of all source files, optionally limited to the given path

        :param relative_path: if provided, restrict search to this path
        """
        rel_file_paths = []
        start_path = os.path.join(self.project_root, relative_path)
        if not os.path.exists(start_path):
            raise FileNotFoundError(f"Relative path {start_path} not found.")
        if os.path.isfile(start_path):
            return [relative_path]
        else:
            for root, dirs, files in os.walk(start_path, followlinks=True):
                # prevent recursion into ignored directories
                dirs[:] = [d for d in dirs if not self.is_ignored_path(os.path.join(root, d))]

                # collect non-ignored files
                for file in files:
                    abs_file_path = os.path.join(root, file)
                    try:
                        if not self.is_ignored_path(abs_file_path, ignore_non_source_files=True):
                            try:
                                rel_file_path = os.path.relpath(abs_file_path, start=self.project_root)
                            except Exception:
                                log.warning(
                                    "Ignoring path '%s' because it appears to be outside of the project root (%s)",
                                    abs_file_path,
                                    self.project_root,
                                )
                                continue
                            rel_file_paths.append(rel_file_path)
                    except FileNotFoundError:
                        log.warning(
                            f"File {abs_file_path} not found (possibly due it being a symlink), skipping it in request_parsed_files",
                        )
            return rel_file_paths

    def search_source_files_for_pattern(
        self,
        pattern: str,
        relative_path: str = "",
        context_lines_before: int = 0,
        context_lines_after: int = 0,
        paths_include_glob: str | None = None,
        paths_exclude_glob: str | None = None,
        dotall: bool = True,
    ) -> list[MatchedConsecutiveLines]:
        """
        Search for a pattern across all (non-ignored) source files

        :param pattern: Regular expression pattern to search for, either as a compiled Pattern or string
        :param relative_path:
        :param context_lines_before: Number of lines of context to include before each match
        :param context_lines_after: Number of lines of context to include after each match
        :param paths_include_glob: Glob pattern to filter which files to include in the search
        :param paths_exclude_glob: Glob pattern to filter which files to exclude from the search. Takes precedence over paths_include_glob.
        :param dotall: Whether to compile the regex with the DOTALL flag (``.`` matches newlines).
        :return: List of matched consecutive lines with context
        """
        relative_file_paths = self.gather_source_files(relative_path=relative_path)
        return search_files(
            relative_file_paths,
            pattern,
            root_path=self.project_root,
            file_reader=self.read_file,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            paths_include_glob=paths_include_glob,
            paths_exclude_glob=paths_exclude_glob,
            dotall=dotall,
        )

    def retrieve_content_around_line(
        self, relative_file_path: str, line: int, context_lines_before: int = 0, context_lines_after: int = 0
    ) -> MatchedConsecutiveLines:
        """
        Retrieve the content of the given file around the given line.

        :param relative_file_path: The relative path of the file to retrieve the content from
        :param line: The line number to retrieve the content around
        :param context_lines_before: The number of lines to retrieve before the given line
        :param context_lines_after: The number of lines to retrieve after the given line

        :return MatchedConsecutiveLines: A container with the desired lines.
        """
        file_contents = self.read_file(relative_file_path)
        return MatchedConsecutiveLines.from_file_contents(
            file_contents,
            line=line,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            source_file_path=relative_file_path,
        )

    def create_language_server_manager(self) -> LanguageServerManager:
        """
        Creates the language server manager for the project, starting one language server per configured programming language.

        :return: the language server manager, which is also stored in the project instance
        """
        try:
            # determine timeout to use for LS calls
            tool_timeout = self.serena_config.tool_timeout
            if tool_timeout is None or tool_timeout < 0:
                ls_timeout = None
            else:
                if tool_timeout < 10:
                    raise ValueError(f"Tool timeout must be at least 10 seconds, but is {tool_timeout} seconds")
                ls_timeout = tool_timeout - 5  # the LS timeout is for a single call, it should be smaller than the tool timeout

            # if there is an existing instance, stop its language servers first
            if self.language_server_manager is not None:
                log.info("Stopping existing language server manager ...")
                self.language_server_manager.stop_all()
                self.language_server_manager = None

            log.info(f"Creating language server manager for {self.project_root}")
            self._language_server_manager_init_error = None
            ls_specific_settings = {**self.serena_config.ls_specific_settings, **self.project_config.ls_specific_settings}
            factory = LanguageServerFactory(
                project_root=self.project_root,
                project_data_path=self._serena_data_folder,
                encoding=self.project_config.encoding,
                ignored_patterns=self._ignored_patterns,
                ls_timeout=ls_timeout,
                ls_specific_settings=ls_specific_settings,
                additional_workspace_folders=self.project_config.additional_workspace_folders,
                trace_lsp_communication=self.serena_config.trace_lsp_communication,
            )
            self.language_server_manager = LanguageServerManager.from_languages(self.project_config.languages, factory)
            return self.language_server_manager
        except Exception as e:
            self._language_server_manager_init_error = e
            raise

    def get_language_server_manager_or_raise(self) -> LanguageServerManager:
        if self.language_server_manager is None:
            msg = TextBuilder("The language server manager is not initialized, indicating a problem during project initialisation.")
            if self._language_server_manager_init_error is not None:
                msg.with_text(str(self._language_server_manager_init_error))
            if self._agent is not None:
                msg.with_text("For details, please check the logs. " + self._agent.get_log_inspection_instructions())
            msg.with_text(
                "IMPORTANT: Stop, do not attempt workarounds. Inform the user and wait for further instructions before you continue!"
            )
            raise Exception(msg.build())
        return self.language_server_manager

    def add_language(self, language: Language) -> None:
        """
        Adds a new programming language to the project configuration, starting the corresponding
        language server instance if the LS manager is active.
        The project configuration is saved to disk after adding the language.

        :param language: the programming language to add
        """
        if language in self.project_config.languages:
            log.info(f"Language {language.value} is already present in the project configuration.")
            return

        # start the language server (if the LS manager is active)
        if self.language_server_manager is None:
            log.info("Language server manager is not active; skipping language server startup for the new language.")
        else:
            log.info("Adding and starting the language server for new language %s ...", language.value)
            self.language_server_manager.add_language_server(language)

        # update the project configuration
        self.project_config.languages.append(language)
        self.save_config()

    def remove_language(self, language: Language) -> None:
        """
        Removes a programming language from the project configuration, stopping the corresponding
        language server instance if the LS manager is active.
        The project configuration is saved to disk after removing the language.

        :param language: the programming language to remove
        """
        if language not in self.project_config.languages:
            log.info(f"Language {language.value} is not present in the project configuration.")
            return
        # update the project configuration
        self.project_config.languages.remove(language)
        self.save_config()

        # stop the language server (if the LS manager is active)
        if self.language_server_manager is None:
            log.info("Language server manager is not active; skipping language server shutdown for the removed language.")
        else:
            log.info("Removing and stopping the language server for language %s ...", language.value)
            self.language_server_manager.remove_language_server(language)

    def shutdown(self, timeout: float = 2.0) -> None:
        if self.language_server_manager is not None:
            self.language_server_manager.stop_all(save_cache=True, timeout=timeout)
            self.language_server_manager = None
