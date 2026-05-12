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
