"""
Memory reference matching, similarity scoring, and integrity reporting.

This module contains the pure helpers and data types used by
:class:`serena.project.MemoriesManager` to (a) detect and rank references
between memories, and (b) report referential integrity issues. The
:class:`MemoryReferenceAnalyzer` class drives the validation and autofix
workflows against a live ``MemoriesManager`` instance.

Kept separate from the manager so the matching heuristics can be evolved
and tested in isolation from filesystem and lifecycle concerns.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sensai.util.string import TextBuilder

if TYPE_CHECKING:
    from .memory_manager import MemoryManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MEMORY_REF_PREFIX: str = "mem:"
"""Reference prefix used inside memory bodies to point at another memory."""

NAME_SIMILARITY_THRESHOLD: float = 0.55
"""Minimum :func:`compute_name_similarity` score for a candidate to be reported."""

HIGH_CONFIDENCE_NAME_LENGTH: int = 10
"""Length threshold above which a flat memory name is considered "name-shaped" (i.e.
unlikely to coincide with ordinary prose)."""

SHORT_NAME_FLOOR: int = 3
"""Below this basename length, only an exact token match keeps similarity above 0."""

FUZZY_BARE_TOKEN_JACCARD_FLOOR: float = 0.6
"""For fuzzy bare-text matching, the bare token and the candidate existing name must
share at least this fraction of their tokenized name parts. Containment / SequenceMatcher
signals alone over-match — e.g. a generic prose word like ``repository`` is a substring of
``serena_repository_structure`` but their token Jaccard is only 1/3, so we reject it at
this floor."""

BASENAME_JACCARD_FLOOR: float = 0.34
"""In :func:`compute_name_similarity` case 2 (basenames differ), when the two names also
carry *differing* topic prefixes, demand at least one strong basename signal: token
Jaccard >= this floor, basename containment, or typo-level seq ratio. Without this gate,
names like ``frontend/x-subtleties`` and ``backend/y-subtleties`` get matched purely on the
shared trailing token via the SequenceMatcher signal."""

BASENAME_TYPO_SEQ_FLOOR: float = 0.75
"""Companion to :data:`BASENAME_JACCARD_FLOOR`: a basename seq ratio above this is treated
as typo-level edit distance and bypasses the Jaccard/containment requirement."""

MAX_STALE_REFERENCE_CANDIDATES: int = 3
"""Hard cap on candidates proposed per stale reference. Beyond a small number the list
stops aiding disambiguation and becomes noise."""

WORDS_TO_IGNORE_AS_MEMORY_NAME_CANDIDATES: frozenset[str] = frozenset({"core"})
"""Names that coincide with common English words and are filtered out of the unmarked-
reference scan to avoid false positives."""

NAME_CHAR_CLASS: str = r"[A-Za-z0-9_\-/]"
"""Character class delimiting a memory name. Used to anchor regex matches so we never
consume a partial name (kept in sync with the boundary rule in
:meth:`MemoriesManager.rename_references_to_memory`)."""

_VERSION_SUFFIX_PATTERN: re.Pattern[str] = re.compile(r"_(?:v\d+|old|new|legacy|bak)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Pure helpers: normalization, tokenization, similarity
# ---------------------------------------------------------------------------


def normalize_for_similarity(name: str) -> str:
    """
    :param name: a memory name
    :return: a lowercased copy of ``name`` with version/legacy-style trailing suffixes stripped
        (e.g. ``"auth_v2"`` -> ``"auth"``); used as the canonical form for similarity scoring.
    """
    return _VERSION_SUFFIX_PATTERN.sub("", name.lower())


def tokenize_name(name: str) -> set[str]:
    """
    :param name: a memory name
    :return: the set of lowercase tokens extracted by splitting ``name`` on ``/``, ``_``, ``-``
        and at camelCase boundaries; empty tokens are dropped.
    """
    parts = re.split(r"[/_\-]|(?<=[a-z])(?=[A-Z])", name)
    return {p.lower() for p in parts if p}


def compute_name_similarity(a: str, b: str) -> float:
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
        frontend/x-subtleties ~ backend/y-subtleties -> 0.00 (different topics + only a
                                                             shared generic trailing token)

    :param a: first memory name
    :param b: second memory name
    :return: the similarity score
    """
    # normalize: lowercase + strip version/legacy suffixes
    norm_a, norm_b = normalize_for_similarity(a), normalize_for_similarity(b)
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
        prefix_tokens_a, prefix_tokens_b = tokenize_name(prefix_a), tokenize_name(prefix_b)
        prefix_jaccard = (
            len(prefix_tokens_a & prefix_tokens_b) / len(prefix_tokens_a | prefix_tokens_b) if (prefix_tokens_a | prefix_tokens_b) else 0.0
        )
        return 0.5 + 0.5 * prefix_jaccard

    # case 2: basenames differ -- score the *basenames* only, so that a shared topic prefix
    # plus a generic trailing token (e.g. "frontend/X-subtleties" vs "frontend/Y-subtleties")
    # does not inflate the SequenceMatcher signal into a false positive.
    basename_tokens_a, basename_tokens_b = tokenize_name(basename_a), tokenize_name(basename_b)
    union_basename = basename_tokens_a | basename_tokens_b
    basename_jaccard = (len(basename_tokens_a & basename_tokens_b) / len(union_basename)) if union_basename else 0.0
    basename_contained = bool(basename_a) and bool(basename_b) and (basename_a in basename_b or basename_b in basename_a)
    seq = SequenceMatcher(None, basename_a, basename_b).ratio()

    # when both names carry *differing* topic prefixes, demand at least one strong basename
    # signal — otherwise a single coincidental shared token at the end of long basenames
    # under different topic roots slips through purely on the seq-ratio
    if prefix_a and prefix_b and prefix_a != prefix_b:
        if basename_jaccard < BASENAME_JACCARD_FLOOR and not basename_contained and seq < BASENAME_TYPO_SEQ_FLOOR:
            return 0.0

    # containment is a meaningful rename signal on its own (e.g. auth -> authentication),
    # so we lift it above the threshold floor when one basename fully contains the other,
    # with the length-ratio gating how confident we are
    contained = 0.0
    if basename_contained:
        length_ratio = min(len(basename_a), len(basename_b)) / max(len(basename_a), len(basename_b))
        contained = 0.5 + 0.5 * length_ratio

    # short-name floor: for very short basenames, only accept candidates with a strong token signal
    if min(len(basename_a), len(basename_b)) <= SHORT_NAME_FLOOR and basename_jaccard < 1.0:
        return 0.0
    return max(basename_jaccard, seq, contained)


def find_stale_reference_candidates(missing_name: str, existing_names: list[str], threshold: float | None = None) -> list[str]:
    """
    :param missing_name: the unresolved reference target (without the ``mem:`` prefix).
    :param existing_names: the names of all currently existing memories.
    :param threshold: optional override for the minimum similarity required; defaults to
        :data:`NAME_SIMILARITY_THRESHOLD`.
    :return: existing memory names whose similarity to ``missing_name`` meets or exceeds
        ``threshold``, sorted in descending order of similarity (ties broken alphabetically)
        and capped at :data:`MAX_STALE_REFERENCE_CANDIDATES` entries to keep the output
        focused on the most plausible matches.
    """
    cutoff = NAME_SIMILARITY_THRESHOLD if threshold is None else threshold
    scored: list[tuple[float, str]] = []
    for existing in existing_names:
        score = compute_name_similarity(missing_name, existing)
        if score >= cutoff:
            scored.append((score, existing))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [name for _, name in scored[:MAX_STALE_REFERENCE_CANDIDATES]]


def iter_referenced_names_in_content(content: str) -> Iterator[str]:
    """
    :param content: arbitrary memory content
    :return: an iterator over the memory names appearing as ``mem:NAME`` references in
        ``content``; duplicate occurrences are yielded once each.
    """
    # use the same boundary rule as MemoriesManager.rename_references_to_memory so the two stay consistent
    pattern = rf"(?<!{NAME_CHAR_CLASS}){re.escape(MEMORY_REF_PREFIX)}({NAME_CHAR_CLASS}+?)(?!{NAME_CHAR_CLASS})"
    for match in re.finditer(pattern, content):
        yield match.group(1)


def find_bare_occurrences(content: str, name: str) -> int:
    """
    :param content: arbitrary memory content
    :param name: a memory name to look for
    :return: the count of bare (i.e. not already ``mem:``-prefixed) word-boundary-anchored
        occurrences of ``name`` in ``content``. The match must not be preceded by ``mem:``
        and must not be embedded within a longer memory-name-like run of characters.
    """
    pattern = (
        rf"(?<!{re.escape(MEMORY_REF_PREFIX)})"
        rf"(?<!{NAME_CHAR_CLASS})"
        rf"{re.escape(name)}"
        rf"(?!{NAME_CHAR_CLASS})"
    )
    return len(re.findall(pattern, content))


def add_bare_occurrences_prefix(content: str, name: str) -> tuple[str, int]:
    """
    :param content: arbitrary memory content
    :param name: the memory name whose bare occurrences should be rewritten
    :return: ``(new_content, n_replacements)`` after prefixing each bare occurrence of
        ``name`` with ``mem:`` (using the same boundary rule as :func:`find_bare_occurrences`).
    """
    pattern = (
        rf"(?<!{re.escape(MEMORY_REF_PREFIX)})"
        rf"(?<!{NAME_CHAR_CLASS})"
        rf"{re.escape(name)}"
        rf"(?!{NAME_CHAR_CLASS})"
    )
    replacement = MEMORY_REF_PREFIX + name
    return re.subn(pattern, lambda _m: replacement, content)


def iter_long_bare_tokens(content: str) -> Iterator[tuple[str, int]]:
    """
    :param content: arbitrary memory content
    :return: an iterator over ``(token, count)`` pairs for each distinct name-shaped
        token in ``content`` whose length meets :data:`HIGH_CONFIDENCE_NAME_LENGTH`
        and which is not preceded by ``mem:`` (those are already valid references).
        The boundaries follow :data:`NAME_CHAR_CLASS`, so embedded substrings of
        longer name-character runs are not matched.
    """
    pattern = (
        rf"(?<!{re.escape(MEMORY_REF_PREFIX)})"
        rf"(?<!{NAME_CHAR_CLASS})"
        rf"({NAME_CHAR_CLASS}{{{HIGH_CONFIDENCE_NAME_LENGTH},}})"
        rf"(?!{NAME_CHAR_CLASS})"
    )
    counts: dict[str, int] = {}
    for match in re.finditer(pattern, content):
        token = match.group(1)
        counts[token] = counts.get(token, 0) + 1
    return iter(counts.items())


def is_self_reference(source_memory: str, suspected_name: str) -> bool:
    """
    :return: True iff ``suspected_name`` would refer to ``source_memory`` itself
        (including the case where ``suspected_name`` equals the basename of a topic-path
        source memory).
    """
    if suspected_name == source_memory:
        return True
    source_basename = source_memory.rsplit("/", 1)[-1]
    return suspected_name == source_basename


# ---------------------------------------------------------------------------
# Report dataclasses
# ---------------------------------------------------------------------------


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
      :meth:`MemoryReferenceAnalyzer.auto_prefix_bare_references`, since they would
      require substring substitution rather than a prefix addition.

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
    Outcome of :meth:`MemoryReferenceAnalyzer.validate_referential_integrity`.

    :ivar stale_references: ``mem:NAME`` references whose target memory does not exist.
    :ivar high_confidence_unmarked_memories: bare references whose suspected target name is unlikely
        to be coincidental prose (topic-path or sufficiently long).
    :ivar low_confidence_unmarked_memories: bare references whose suspected target name could plausibly
        appear in ordinary prose (short, flat names).
    """

    stale_references: list[StaleReference] = field(default_factory=list)
    high_confidence_unmarked_memories: list[UnmarkedReferenceWarning] = field(default_factory=list)
    low_confidence_unmarked_memories: list[UnmarkedReferenceWarning] = field(default_factory=list)

    def is_clean(self) -> bool:
        """:return: True iff no stale references and no warnings of any confidence level were found."""
        return not (self.stale_references or self.high_confidence_unmarked_memories or self.low_confidence_unmarked_memories)

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

        # unmarked-reference warnings — split exact vs fuzzy near-miss, then by confidence
        exact_high = [w for w in self.high_confidence_unmarked_memories if w.is_exact_match]
        exact_low = [w for w in self.low_confidence_unmarked_memories if w.is_exact_match]
        fuzzy = [w for w in self.high_confidence_unmarked_memories if not w.is_exact_match] + [
            w for w in self.low_confidence_unmarked_memories if not w.is_exact_match
        ]

        # the "may be intentional" caveat is meaningful only for exact matches (where the bare
        # text equals a real memory name and may simply be ordinary prose); print it once,
        # before the first exact-match section
        if exact_high or exact_low:
            tb.with_line("Possibly unmarked references — exact matches:")
            tb.with_line("  (note: bare matches in prose may be intentional and not actual references)")
            for label, warnings in (("high confidence", exact_high), ("low confidence", exact_low)):
                if not warnings:
                    continue
                tb.with_line(f"  {label} ({len(warnings)}):")
                for w in warnings:
                    ro_tag = " [read-only source]" if w.source_is_read_only else ""
                    occ = "occurrence" if w.occurrences == 1 else "occurrences"
                    tb.with_line(
                        f"    - {w.occurrences} {occ} of `{w.suspected_name}` in `{w.source_memory}`{ro_tag}"
                        f" (suggested: `mem:{w.suspected_name}`)"
                    )
            tb.with_line("")

        if fuzzy:
            tb.with_line(f"Possibly unmarked references — fuzzy near-misses ({len(fuzzy)}):")
            for w in fuzzy:
                ro_tag = " [read-only source]" if w.source_is_read_only else ""
                occ = "occurrence" if w.occurrences == 1 else "occurrences"
                tb.with_line(
                    f"  - {w.occurrences} {occ} of `{w.actual_token}` in `{w.source_memory}`{ro_tag}"
                    f" — near-miss (suggested: `mem:{w.suspected_name}`)"
                )
            tb.with_line("")
        return tb.build()


@dataclass
class AutofixReport:
    """
    Outcome of :meth:`MemoryReferenceAnalyzer.auto_prefix_bare_references`.

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

    autofixed: list[AutofixedReference] = field(default_factory=list)
    dry_run: bool = False
    skipped_read_only: list[UnmarkedReferenceWarning] = field(default_factory=list)
    skipped_flat: list[UnmarkedReferenceWarning] = field(default_factory=list)
    skipped_global: list[UnmarkedReferenceWarning] = field(default_factory=list)
    skipped_fuzzy: list[UnmarkedReferenceWarning] = field(default_factory=list)

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


# ---------------------------------------------------------------------------
# Analyzer: ties the helpers above to a live MemoriesManager instance
# ---------------------------------------------------------------------------


class MemoryReferenceAnalyzer:
    """
    Drives validation and autofix workflows against a :class:`MemoriesManager`.

    Composition rather than inheritance — the analyzer only needs the manager's
    memory enumeration, loading, saving, and is-global helpers, and is otherwise
    independent of project-management concerns.
    """

    def __init__(self, manager: MemoryManager):
        self._manager = manager

    def validate_referential_integrity(
        self, include_unmarked: bool = True, include_fuzzy_matching: bool = True
    ) -> ReferentialIntegrityReport:
        """
        Scans every (non-ignored) memory's content for referential integrity issues.

        The scan covers both project-local and global memories. Three kinds of finding are
        produced, each independently gated:

        * **stale references** — occurrences of ``mem:NAME`` where ``NAME`` does not resolve
          to an existing memory. For each, a list of similarly-named existing memories is
          proposed as candidate intended targets (see :func:`compute_name_similarity`),
          capped at :data:`MAX_STALE_REFERENCE_CANDIDATES`. Always reported.
        * **exact unmarked-reference warnings** — bare occurrences of an existing memory
          name that appear without the ``mem:`` prefix. Split into high-confidence (the
          suspected name contains a ``/`` or exceeds :data:`HIGH_CONFIDENCE_NAME_LENGTH`)
          and low-confidence groups. Candidate names whose basename is in
          :data:`WORDS_TO_IGNORE_AS_MEMORY_NAME_CANDIDATES` are skipped. Gated by
          ``include_unmarked``.
        * **fuzzy near-miss warnings** — long, distinctive bare tokens in a memory body
          that *do not* match an existing name exactly but similarity-match a
          high-confidence existing name AND share at least
          :data:`FUZZY_BARE_TOKEN_JACCARD_FLOOR` of their tokenized name parts. Always
          reported as high-confidence; the actual bare text is preserved on
          :attr:`UnmarkedReferenceWarning.actual_token`. Gated by ``include_unmarked
          and include_fuzzy_matching`` — fuzzy matches are noisy and only meaningful when
          unmarked-reference checking is enabled.

        Self-references (a memory's content mentioning its own name or basename) and empty
        memories are skipped silently. This method has no side effects.

        :param include_unmarked: if False, skip both the exact unmarked scan and the fuzzy
            near-miss scan; only stale references are reported.
        :param include_fuzzy_matching: if False, skip the fuzzy near-miss scan even when
            unmarked-reference checking is otherwise enabled. Has no effect when
            ``include_unmarked`` is False.
        :return: a :class:`ReferentialIntegrityReport` summarizing all findings.
        """
        report = ReferentialIntegrityReport()

        # gather all existing memory names (project + global) with their read-only status
        memories_list = self._manager.list_memories()
        all_names = sorted(set(memories_list.memories) | set(memories_list.read_only_memories))
        read_only_names = set(memories_list.read_only_memories)
        existing_set = set(all_names)
        # only existing names that are themselves "memory-name-like" qualify as fuzzy candidates,
        # otherwise short flat names would match arbitrary long prose words via containment
        high_confidence_names = [n for n in all_names if "/" in n or len(n) >= HIGH_CONFIDENCE_NAME_LENGTH]

        for source_name in all_names:
            # content of this memory should not be analyzed regarding stale references
            if source_name == self._manager.MEMORY_MAINTENANCE_NAME:
                continue

            content = self._manager.load_memory(source_name)
            if not content:
                # skip empty memories silently — no references can exist in empty content
                continue
            source_is_read_only = source_name in read_only_names

            # stale references: every mem:NAME whose NAME is not an existing memory
            stale_seen: set[str] = set()
            for referenced in iter_referenced_names_in_content(content):
                if referenced in existing_set or referenced in stale_seen:
                    continue
                stale_seen.add(referenced)
                candidates = find_stale_reference_candidates(referenced, all_names)
                report.stale_references.append(
                    StaleReference(
                        source_memory=source_name,
                        referenced_name=referenced,
                        candidates=candidates,
                        source_is_read_only=source_is_read_only,
                    )
                )

            if not include_unmarked:
                continue

            # exact unmarked references: bare occurrences of any existing memory name (except self)
            for candidate_name in all_names:
                if is_self_reference(source_name, candidate_name):
                    continue
                # skip candidate names whose basename is an ambiguous common word
                if candidate_name.rsplit("/", 1)[-1] in WORDS_TO_IGNORE_AS_MEMORY_NAME_CANDIDATES:
                    continue
                n = find_bare_occurrences(content, candidate_name)
                if n == 0:
                    continue
                is_high_conf = "/" in candidate_name or len(candidate_name) >= HIGH_CONFIDENCE_NAME_LENGTH
                warning = UnmarkedReferenceWarning(
                    source_memory=source_name,
                    suspected_name=candidate_name,
                    occurrences=n,
                    is_high_confidence=is_high_conf,
                    source_is_read_only=source_is_read_only,
                    actual_token=candidate_name,
                )
                if is_high_conf:
                    report.high_confidence_unmarked_memories.append(warning)
                else:
                    report.low_confidence_unmarked_memories.append(warning)

            if not include_fuzzy_matching:
                continue

            # fuzzy near-misses: long bare tokens that similarity-match a high-confidence existing name
            for token, n in iter_long_bare_tokens(content):
                if token in existing_set:
                    # exact-match path already handled this token (or self-referenced and was skipped)
                    continue
                # filter bare tokens that coincide with common English words; the same filter is
                # applied to candidate names in the exact-match loop, this is the symmetric side
                token_norm = normalize_for_similarity(token)
                if token_norm in WORDS_TO_IGNORE_AS_MEMORY_NAME_CANDIDATES:
                    continue
                token_tokens = tokenize_name(token)
                best_name: str | None = None
                best_score = 0.0
                for existing in high_confidence_names:
                    if existing.rsplit("/", 1)[-1] in WORDS_TO_IGNORE_AS_MEMORY_NAME_CANDIDATES:
                        continue
                    # require substring containment between bare token and existing name: fuzzy
                    # matches without a containment relationship are rarely useful as rewrite
                    # suggestions (auto_prefix_bare_references can't fix them anyway) and dominate
                    # the false-positive rate, e.g. "grid-layout" vs "layout-grid-subtleties".
                    existing_norm = normalize_for_similarity(existing)
                    if token_norm not in existing_norm and existing_norm not in token_norm:
                        continue
                    score = compute_name_similarity(token, existing)
                    if score < NAME_SIMILARITY_THRESHOLD:
                        continue
                    # safeguard against substring-only matches: require meaningful token overlap so
                    # generic prose words don't get flagged just because they happen to be substrings
                    # of an existing memory name
                    existing_tokens = tokenize_name(existing)
                    union = token_tokens | existing_tokens
                    if not union:
                        continue
                    jaccard = len(token_tokens & existing_tokens) / len(union)
                    if jaccard < FUZZY_BARE_TOKEN_JACCARD_FLOOR:
                        continue
                    if score > best_score:
                        best_score = score
                        best_name = existing
                if best_name is None:
                    continue
                # skip self-suggestions: a memory's body containing a near-miss of its own
                # name (e.g. capitalised "Conventions" in source `conventions`) would otherwise
                # produce a warning pointing the source at itself
                if normalize_for_similarity(best_name) == normalize_for_similarity(source_name):
                    continue
                report.high_confidence_unmarked_memories.append(
                    UnmarkedReferenceWarning(
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
    ) -> AutofixReport:
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
        report = AutofixReport(dry_run=dry_run)

        # build the integrity report first so autofix decisions are made on the same data
        validation = self.validate_referential_integrity()

        # combine the warning groups according to the include_flat_names policy
        warnings: list[UnmarkedReferenceWarning] = list(validation.high_confidence_unmarked_memories)
        if include_flat_names:
            warnings.extend(validation.low_confidence_unmarked_memories)
        else:
            report.skipped_flat.extend(validation.low_confidence_unmarked_memories)

        # apply replacements per source memory, grouping warnings to avoid re-reading content
        warnings_by_source: dict[str, list[UnmarkedReferenceWarning]] = {}
        for w in warnings:
            # fuzzy near-misses are never auto-rewritten — the bare text differs from the target
            if not w.is_exact_match:
                report.skipped_fuzzy.append(w)
                continue
            # filter remaining warnings according to scope flags
            if w.source_is_read_only and not include_read_only:
                report.skipped_read_only.append(w)
                continue
            if self._manager._is_global(w.source_memory) and not include_global:
                report.skipped_global.append(w)
                continue
            warnings_by_source.setdefault(w.source_memory, []).append(w)

        for source_memory, source_warnings in warnings_by_source.items():
            content = self._manager.load_memory(source_memory)
            total_n = 0
            per_target_records: list[AutofixedReference] = []

            # apply replacements sequentially; each pass uses the (potentially updated) content
            for w in source_warnings:
                content, n = add_bare_occurrences_prefix(content, w.suspected_name)
                if n > 0:
                    per_target_records.append(
                        AutofixedReference(
                            source_memory=source_memory,
                            referenced_name=w.suspected_name,
                            n_replacements=n,
                        )
                    )
                    total_n += n

            if total_n > 0:
                if not dry_run:
                    # use is_tool_context=False so we don't trip read-only protection when --include-read-only is set
                    self._manager.save_memory(source_memory, content, is_tool_context=False)
                report.autofixed.extend(per_target_records)

        return report
