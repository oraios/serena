"""
Unit tests for :class:`serena.project.MemoriesManager` helpers that do not
require touching the filesystem (in particular, :meth:`rename_references_to_memory`
and :meth:`_prepare_name`).
"""

import os

import pytest

from serena.project import MemoriesManager


@pytest.fixture
def manager() -> MemoriesManager:
    # serena_data_folder=None: the tested helpers do not access the filesystem
    return MemoriesManager(serena_data_folder=None)


class TestPrepareName:
    @pytest.mark.parametrize(
        "name",
        [
            "memory",
            "emergency",
            "meeting_notes",
            "em-dash",
            "ml_notes",
            "embedding",
            "e",
            "m",
            "mem",
            ":colon_prefixed_unlikely",
        ],
    )
    def test_does_not_strip_partial_prefix_chars_from_real_names(self, manager: MemoriesManager, name: str) -> None:
        """A regression guard: previously used ``str.lstrip("mem:")`` which strips any leading m/e/:."""
        assert manager._prepare_name(name) == name

    @pytest.mark.parametrize(
        ("input_name", "expected"),
        [
            ("mem:foo", "foo"),
            ("mem:foo/bar", "foo/bar"),
            ("mem:memory", "memory"),  # prefix is removed only once, not greedily
            ("mem:", ""),
        ],
    )
    def test_strips_mem_prefix_only_when_actually_a_prefix(self, manager: MemoriesManager, input_name: str, expected: str) -> None:
        assert manager._prepare_name(input_name) == expected

    @pytest.mark.parametrize(
        ("input_name", "expected"),
        [
            ("foo.md", "foo"),
            ("topic/foo.md", "topic/foo"),
            ("a.md.notes", "a.md.notes"),  # ".md" must only be stripped as trailing extension
            ("foo.markdown", "foo.markdown"),
            (".md", ""),
        ],
    )
    def test_strips_md_only_as_suffix(self, manager: MemoriesManager, input_name: str, expected: str) -> None:
        assert manager._prepare_name(input_name) == expected

    def test_normalizes_os_separator(self, manager: MemoriesManager) -> None:
        assert manager._prepare_name(f"topic{os.sep}sub{os.sep}name") == "topic/sub/name"

    def test_combined_normalizations(self, manager: MemoriesManager) -> None:
        assert manager._prepare_name(f"mem:topic{os.sep}foo.md") == "topic/foo"


class TestRenameReferencesToMemory:
    @pytest.mark.parametrize(
        ("content", "old_name", "new_name", "expected_content", "expected_count"),
        [
            # simple cases
            pytest.param("see mem:foo for details", "foo", "bar", "see mem:bar for details", 1, id="simple"),
            pytest.param("nothing to see here", "foo", "bar", "nothing to see here", 0, id="no_match"),
            pytest.param(
                "mem:foo and mem:foo and `mem:foo`",
                "foo",
                "bar",
                "mem:bar and mem:bar and `mem:bar`",
                3,
                id="multiple_occurrences",
            ),
            # boundaries
            pytest.param("mem:foo rest", "foo", "bar", "mem:bar rest", 1, id="start_of_string"),
            pytest.param("prefix mem:foo", "foo", "bar", "prefix mem:bar", 1, id="end_of_string"),
            pytest.param("mem:foo", "foo", "bar", "mem:bar", 1, id="entire_string"),
            # must NOT match: embedded in longer name
            pytest.param("`mem:foobar`", "foo", "bar", "`mem:foobar`", 0, id="longer_suffix"),
            pytest.param("`mem:foo/sub`", "foo", "bar", "`mem:foo/sub`", 0, id="subtopic"),
            pytest.param("mem:foo-extra", "foo", "bar", "mem:foo-extra", 0, id="hyphen_suffix"),
            pytest.param("mem:foo_extra", "foo", "bar", "mem:foo_extra", 0, id="underscore_suffix"),
            pytest.param("xmem:foo", "foo", "bar", "xmem:foo", 0, id="preceded_by_name_char"),
            # boundaries on non-name characters
            pytest.param("see `mem:foo.md`", "foo", "bar", "see `mem:bar.md`", 1, id="md_extension_suffix"),
            # topic renames
            pytest.param("`mem:foo/bar`", "foo/bar", "baz", "`mem:baz`", 1, id="topic_to_flat"),
            pytest.param("`mem:foo`", "foo/bar", "baz", "`mem:foo`", 0, id="parent_does_not_match_topic"),
            pytest.param("`mem:foo`", "foo", "topic/bar", "`mem:topic/bar`", 1, id="flat_to_topic"),
            # regex-meta safety
            pytest.param("`mem:a.b`", "a.b", "c", "`mem:c`", 1, id="dot_in_old_name_literal"),
            pytest.param("`mem:axb`", "a.b", "c", "`mem:axb`", 0, id="dot_in_old_name_not_wildcard"),
            # mixed
            pytest.param(
                "valid `mem:foo`, embedded mem:foobar, subtopic mem:foo/x, and another `mem:foo`.",
                "foo",
                "bar",
                "valid `mem:bar`, embedded mem:foobar, subtopic mem:foo/x, and another `mem:bar`.",
                2,
                id="mixed_matching_and_nonmatching",
            ),
            # input names that previously broke due to lstrip("mem:") in _add_reference_prefix
            pytest.param("see `mem:memory`", "memory", "diary", "see `mem:diary`", 1, id="old_name_starts_with_m"),
            pytest.param("see `mem:emergency`", "emergency", "incident", "see `mem:incident`", 1, id="old_name_starts_with_e"),
            pytest.param("see `mem:foo`", "foo", "memory", "see `mem:memory`", 1, id="new_name_starts_with_m"),
        ],
    )
    def test_rename(
        self,
        manager: MemoriesManager,
        content: str,
        old_name: str,
        new_name: str,
        expected_content: str,
        expected_count: int,
    ) -> None:
        result, n = manager.rename_references_to_memory(content, old_name, new_name)
        assert result == expected_content
        assert n == expected_count

    @pytest.mark.parametrize(
        "delimiter_pair",
        [
            ("`", "`"),
            ('"', '"'),
            ("'", "'"),
            ("(", ")"),
            ("[", "]"),
            ("{", "}"),
            (" ", " "),
            ("\n", "\n"),
            ("\t", "\t"),
            (",", ","),
            (";", ";"),
            ("", ""),  # raw, no delimiters
        ],
    )
    def test_replacement_inside_various_delimiters(self, manager: MemoriesManager, delimiter_pair: tuple[str, str]) -> None:
        left, right = delimiter_pair
        content = f"{left}mem:foo{right}"
        result, n = manager.rename_references_to_memory(content, "foo", "bar")
        assert result == f"{left}mem:bar{right}"
        assert n == 1


class TestNameSimilarity:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            # exact match (and case-insensitive) -> 1.0
            pytest.param("foo", "foo", 1.0, id="identical"),
            pytest.param("Foo", "foo", 1.0, id="case_insensitive"),
            # version-suffix renames are normalized away -> 1.0
            pytest.param("auth_v1", "auth_v2", 1.0, id="version_suffix_rename"),
            pytest.param("auth_old", "auth", 1.0, id="old_suffix_normalized"),
            pytest.param("auth_legacy", "auth", 1.0, id="legacy_suffix_normalized"),
            # flat <-> topic basename move: canonical rename, fully confident
            pytest.param("a/b/c/login", "login", 1.0, id="topic_move_to_flat"),
            pytest.param("login", "auth/login", 1.0, id="flat_to_topic_move"),
            # both sides share a prefix token AND basename: high confidence
            pytest.param("auth/login", "auth/v2/login", 0.75, id="basename_match_shared_prefix"),
        ],
    )
    def test_high_similarity_cases(self, manager: MemoriesManager, a: str, b: str, expected: float) -> None:
        assert manager.compute_name_similarity(a, b) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            # completely unrelated names should be below threshold
            pytest.param("authentication", "database", id="unrelated_long"),
            pytest.param("api/users", "logging/handlers", id="unrelated_topic_paths"),
            # short names without strong token signals must hit the short-name floor
            pytest.param("foo", "bar", id="short_names_unrelated"),
            pytest.param("foo", "for", id="short_names_typo_distance"),
            # IMPORTANT: same basename under unrelated topic prefixes is NOT a rename.
            # `auth/login` and `security/login` are two different login flows in different
            # subsystems; `topic1/topic2/core` and `topic3/topic5/core` are unrelated.
            pytest.param("auth/login", "security/login", id="same_basename_unrelated_prefixes"),
            pytest.param("topic1/topic2/core", "topic3/topic5/core", id="same_basename_disjoint_prefix_tokens"),
        ],
    )
    def test_below_threshold_cases(self, manager: MemoriesManager, a: str, b: str) -> None:
        assert manager.compute_name_similarity(a, b) < MemoriesManager.NAME_SIMILARITY_THRESHOLD

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            # prefix/suffix extensions: caught by sequence ratio / containment, even though Jaccard is 0
            pytest.param("auth", "authentication", id="prefix_extension"),
            pytest.param("login", "user_login", id="token_extension"),
            # typos on longer names: caught by sequence ratio
            pytest.param("authentication", "autentication", id="typo_in_long_name"),
            # token reorder / partial overlap
            pytest.param("user_login_flow", "login_flow", id="partial_token_overlap"),
        ],
    )
    def test_above_threshold_cases(self, manager: MemoriesManager, a: str, b: str) -> None:
        assert manager.compute_name_similarity(a, b) >= MemoriesManager.NAME_SIMILARITY_THRESHOLD

    def test_symmetry(self, manager: MemoriesManager) -> None:
        # similarity is order-independent
        assert manager.compute_name_similarity("auth/login", "security/login") == manager.compute_name_similarity(
            "security/login", "auth/login"
        )

    def test_find_candidates_ranks_by_descending_similarity(self, manager: MemoriesManager) -> None:
        existing = ["auth/login", "security/login", "database", "authentication"]
        candidates = manager._find_stale_reference_candidates("login", existing)
        # both auth/login and security/login share basename `login` -> tied at 1.0; expect them first, alphabetical tiebreak
        assert candidates[:2] == ["auth/login", "security/login"]
        # `database` is unrelated and must not appear
        assert "database" not in candidates

    def test_find_candidates_returns_empty_below_threshold(self, manager: MemoriesManager) -> None:
        existing = ["completely_unrelated", "another_thing"]
        assert manager._find_stale_reference_candidates("foo", existing) == []

    def test_find_candidates_custom_threshold(self, manager: MemoriesManager) -> None:
        # raising the threshold filters out borderline matches
        existing = ["authentication"]
        loose = manager._find_stale_reference_candidates("auth", existing, threshold=0.2)
        strict = manager._find_stale_reference_candidates("auth", existing, threshold=0.95)
        assert loose == ["authentication"]
        assert strict == []


@pytest.fixture
def fs_manager(tmp_path) -> MemoriesManager:
    """A MemoriesManager backed by tmp_path with no read-only patterns."""
    return MemoriesManager(serena_data_folder=tmp_path)


def _write(manager: MemoriesManager, name: str, content: str) -> None:
    manager.save_memory(name, content, is_tool_context=False)


class TestValidateReferentialIntegrity:
    def test_clean_report_when_all_references_resolve(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth", "# auth notes")
        _write(fs_manager, "login_flow", "see `mem:auth` for details")
        report = fs_manager.validate_referential_integrity()
        assert report.is_clean()
        assert "No referential integrity issues" in report.format()

    def test_stale_reference_with_topic_move_candidate(self, fs_manager: MemoriesManager) -> None:
        # original memory `login` was moved to `auth/login`; a reference still points to bare `login`
        _write(fs_manager, "auth/login", "# moved here")
        _write(fs_manager, "docs", "old reference: `mem:login`")
        report = fs_manager.validate_referential_integrity()
        assert len(report.stale_references) == 1
        stale = report.stale_references[0]
        assert stale.source_memory == "docs"
        assert stale.referenced_name == "login"
        assert "auth/login" in stale.candidates

    def test_stale_reference_with_no_candidate(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "completely_unrelated", "# content")
        _write(fs_manager, "docs", "broken: `mem:xyz_unknown_thing`")
        report = fs_manager.validate_referential_integrity()
        assert len(report.stale_references) == 1
        assert report.stale_references[0].candidates == []

    def test_high_confidence_unmarked_warning_for_topic_path(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "the auth/login process is documented elsewhere")
        report = fs_manager.validate_referential_integrity()
        assert len(report.high_confidence_unmarked_memories) == 1
        warning = report.high_confidence_unmarked_memories[0]
        assert warning.suspected_name == "auth/login"
        assert warning.is_high_confidence is True
        assert warning.occurrences == 1
        assert report.low_confidence_unmarked_memories == []

    def test_low_confidence_unmarked_warning_for_short_flat_name(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth", "# notes")
        _write(fs_manager, "docs", "you must use auth here")
        report = fs_manager.validate_referential_integrity()
        assert report.high_confidence_unmarked_memories == []
        assert len(report.low_confidence_unmarked_memories) == 1
        assert report.low_confidence_unmarked_memories[0].suspected_name == "auth"
        assert report.low_confidence_unmarked_memories[0].is_high_confidence is False

    def test_long_flat_name_is_high_confidence(self, fs_manager: MemoriesManager) -> None:
        # a flat name >= _HIGH_CONFIDENCE_NAME_LENGTH chars is unlikely to be coincidental prose
        long_name = "authentication_flow"
        assert len(long_name) >= MemoriesManager._HIGH_CONFIDENCE_NAME_LENGTH
        _write(fs_manager, long_name, "# notes")
        _write(fs_manager, "docs", f"the {long_name} is documented here")
        report = fs_manager.validate_referential_integrity()
        assert len(report.high_confidence_unmarked_memories) == 1

    def test_fuzzy_near_miss_rejects_substring_only_matches(self, fs_manager: MemoriesManager) -> None:
        """
        Regression: fuzzy bare-text matching must require meaningful token overlap, not just
        substring containment. Without the token-Jaccard floor, generic words like
        ``Repository`` would be flagged as near-misses for ``serena_repository_structure``
        purely because they appear as substrings — a noise flood. The cases below are taken
        from a real run on the Serena codebase that produced six false positives.
        """
        _write(fs_manager, "serena_repository_structure", "# repo structure notes")
        _write(fs_manager, "suggested_commands", "# command notes")
        _write(
            fs_manager,
            "docs",
            # generic words ("Repository", "repository") and unrelated code identifiers
            # ("_create_launch_command", "create_launch_command", "repository_root_path")
            # that happen to be substrings of, or share one token with, an existing memory name
            """\
            See _create_launch_command and also create_launch_command.
            The Repository pattern is documented elsewhere.
            Also repository_root_path is set via env var.
            The repository contains many tools.
            """,
        )
        report = fs_manager.validate_referential_integrity()
        assert report.is_clean(), (
            f"Expected no findings; got high={report.high_confidence_unmarked_memories}, "
            f"low={report.low_confidence_unmarked_memories}, stale={report.stale_references}"
        )

    def test_long_flat_name_near_miss_is_high_confidence(self, fs_manager: MemoriesManager) -> None:
        """
        Regression: bare text that is a *near-match* of an existing long memory name
        (e.g. the same name with a missing suffix) should be flagged as a high-confidence
        unmarked-reference warning. Long, distinctive multi-word tokens that appear bare in
        prose and similarity-match an existing memory are almost certainly intended references.

        Real-world case: ``serena_repository_structure.md`` mentions
        ``adding_new_language_support`` in prose; the actual memory is
        ``adding_new_language_support_guide``. Exact-substring matching alone misses this.
        """
        existing = "adding_new_language_support_guide"
        bare = "adding_new_language_support"  # prefix of `existing`; clearly the same concept
        assert len(bare) >= MemoriesManager._HIGH_CONFIDENCE_NAME_LENGTH
        _write(fs_manager, existing, "# guide content")
        _write(fs_manager, "docs", f"See {bare} for details")

        report = fs_manager.validate_referential_integrity()
        assert len(report.high_confidence_unmarked_memories) == 1, (
            f"expected one high-confidence warning for the near-miss reference, "
            f"got {len(report.high_confidence_unmarked_memories)} "
            f"(high={report.high_confidence_unmarked_memories}, low={report.low_confidence_unmarked_memories})"
        )
        warning = report.high_confidence_unmarked_memories[0]
        assert warning.suspected_name == existing
        assert warning.source_memory == "docs"

    def test_self_reference_is_ignored(self, fs_manager: MemoriesManager) -> None:
        # the basename `login` appears in `auth/login`'s own content -> must not be flagged
        _write(fs_manager, "auth/login", "this login flow ...")
        _write(fs_manager, "auth", "# auth notes")
        report = fs_manager.validate_referential_integrity()
        # `auth/login` mentioning its own basename `login` should not produce a warning;
        # `auth` mentioned in `auth/login` content also shouldn't (it's the prefix), and only
        # actual matches matter — assert no warning concerns the source itself
        for w in report.high_confidence_unmarked_memories + report.low_confidence_unmarked_memories:
            assert not (w.source_memory == "auth/login" and w.suspected_name in ("login", "auth/login"))

    def test_marked_reference_does_not_produce_unmarked_warning(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "see `mem:auth/login` for details")
        report = fs_manager.validate_referential_integrity()
        # the marked reference is valid; no warning should fire on that occurrence
        assert report.is_clean()

    def test_mixed_marked_and_bare_in_same_content(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "we have `mem:auth/login` plus a bare auth/login mention")
        report = fs_manager.validate_referential_integrity()
        # only the bare occurrence should be counted
        assert len(report.high_confidence_unmarked_memories) == 1
        assert report.high_confidence_unmarked_memories[0].occurrences == 1

    def test_empty_memory_skipped(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "")
        _write(fs_manager, "docs", "# nothing relevant")
        # must not raise even though one memory is empty
        report = fs_manager.validate_referential_integrity()
        assert report.is_clean()

    def test_read_only_status_propagated(self, tmp_path) -> None:
        manager = MemoriesManager(serena_data_folder=tmp_path, read_only_memory_patterns=[r"frozen/.*"])
        _write(manager, "frozen/notes", "see bare auth/login mention")
        _write(manager, "auth/login", "# notes")
        report = manager.validate_referential_integrity()
        warnings = report.high_confidence_unmarked_memories
        assert len(warnings) == 1
        assert warnings[0].source_memory == "frozen/notes"
        assert warnings[0].source_is_read_only is True


class TestAutoPrefixBareReferences:
    def test_prefixes_high_confidence_warning_in_writable_memory(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "the auth/login process is documented here")
        result = fs_manager.auto_prefix_bare_references()
        assert result.total_replacements == 1
        assert len(result.autofixed) == 1
        # verify the file content was actually mutated
        assert fs_manager.load_memory("docs") == "the mem:auth/login process is documented here"

    def test_skips_low_confidence_by_default(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth", "# notes")
        _write(fs_manager, "docs", "use auth here")
        result = fs_manager.auto_prefix_bare_references()
        assert result.total_replacements == 0
        assert len(result.skipped_flat) == 1
        # content unchanged
        assert fs_manager.load_memory("docs") == "use auth here"

    def test_include_flat_names_widens_scope(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth", "# notes")
        _write(fs_manager, "docs", "use auth here")
        result = fs_manager.auto_prefix_bare_references(include_flat_names=True)
        assert result.total_replacements == 1
        assert fs_manager.load_memory("docs") == "use mem:auth here"

    def test_skips_read_only_source_by_default(self, tmp_path) -> None:
        manager = MemoriesManager(serena_data_folder=tmp_path, read_only_memory_patterns=[r"frozen/.*"])
        _write(manager, "frozen/notes", "the auth/login process")
        _write(manager, "auth/login", "# notes")
        result = manager.auto_prefix_bare_references()
        assert result.total_replacements == 0
        assert len(result.skipped_read_only) == 1
        # content unchanged
        assert manager.load_memory("frozen/notes") == "the auth/login process"

    def test_include_read_only_modifies_read_only_source(self, tmp_path) -> None:
        manager = MemoriesManager(serena_data_folder=tmp_path, read_only_memory_patterns=[r"frozen/.*"])
        _write(manager, "frozen/notes", "the auth/login process")
        _write(manager, "auth/login", "# notes")
        result = manager.auto_prefix_bare_references(include_read_only=True)
        assert result.total_replacements == 1
        assert manager.load_memory("frozen/notes") == "the mem:auth/login process"

    def test_multiple_occurrences_in_same_memory(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "auth/login here and auth/login there")
        result = fs_manager.auto_prefix_bare_references()
        assert result.total_replacements == 2
        assert fs_manager.load_memory("docs") == "mem:auth/login here and mem:auth/login there"

    def test_marked_references_left_alone(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "see `mem:auth/login` and also auth/login bare")
        result = fs_manager.auto_prefix_bare_references()
        # only the bare occurrence is rewritten; the already-marked one stays as-is
        assert result.total_replacements == 1
        assert fs_manager.load_memory("docs") == "see `mem:auth/login` and also mem:auth/login bare"

    def test_dry_run_does_not_modify_files(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "the auth/login process is documented here")
        result = fs_manager.auto_prefix_bare_references(dry_run=True)
        # report describes what *would* have been done
        assert result.dry_run is True
        assert result.total_replacements == 1
        assert len(result.autofixed) == 1
        # but the file on disk is unchanged
        assert fs_manager.load_memory("docs") == "the auth/login process is documented here"
        # running again non-dry actually rewrites
        result = fs_manager.auto_prefix_bare_references()
        assert result.dry_run is False
        assert fs_manager.load_memory("docs") == "the mem:auth/login process is documented here"

    def test_fuzzy_warnings_are_routed_to_skipped_fuzzy(self, fs_manager: MemoriesManager) -> None:
        # set up a fuzzy near-miss case (token shares all parts with a longer existing name)
        existing = "adding_new_language_support_guide"
        bare = "adding_new_language_support"
        _write(fs_manager, existing, "# guide content")
        _write(fs_manager, "docs", f"See {bare} for details")
        result = fs_manager.auto_prefix_bare_references()
        # fuzzy match must NOT be auto-rewritten — it would require substring substitution
        assert result.total_replacements == 0
        assert len(result.skipped_fuzzy) == 1
        skipped = result.skipped_fuzzy[0]
        assert skipped.actual_token == bare
        assert skipped.suspected_name == existing
        # source unchanged
        assert fs_manager.load_memory("docs") == f"See {bare} for details"

    def test_no_double_prefix_on_repeated_runs(self, fs_manager: MemoriesManager) -> None:
        _write(fs_manager, "auth/login", "# notes")
        _write(fs_manager, "docs", "the auth/login process")
        fs_manager.auto_prefix_bare_references()
        second = fs_manager.auto_prefix_bare_references()
        # idempotent: the second run should not touch anything
        assert second.total_replacements == 0
        assert fs_manager.load_memory("docs") == "the mem:auth/login process"
