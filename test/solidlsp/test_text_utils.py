from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from solidlsp.ls_utils import InvalidTextLocationError, TextStepper, TextUtils

# Characters that Python's str.splitlines() treats as line breaks but the LSP does not
# (vertical tab, form feed, file/group/record separators, NEL, line/paragraph separator).
# TextStepper must treat them as ordinary line content.
_NON_LSP_LINE_BREAKS = "\v\f\x1c\x1d\x1e\x85\u2028\u2029"

_LINE_CONTENT = st.text(
    st.sampled_from(list(_NON_LSP_LINE_BREAKS)) | st.characters(exclude_categories=("Cs",), exclude_characters="\r\n"),
    max_size=6,
)

# Deterministic so that any failure is reproducible, and without per-example timing assertions,
# which would be the primary source of flakiness on the slower CI runners.
_PROPERTY = settings(derandomize=True, deadline=None, database=None, max_examples=200)


@dataclass(frozen=True)
class _GeneratedText:
    """A generated text together with the line contents from which it was assembled."""

    text: str
    """the assembled text, using the newline sequences the LSP defines"""
    lines: list[str]
    """the newline-free content of each line; a text ending in a newline has an empty final line"""


def _assemble_text(contents: list[str], separators: list[str]) -> _GeneratedText:
    r"""
    Joins the given line contents with the given newline sequences, adjusting any separator that
    would combine with its predecessor: an "\r" separator, an empty line and an "\n" separator
    together form a single "\r\n" newline, which would render the line structure unknown.

    :param contents: the newline-free content of each line
    :param separators: the newline sequence following each line but the last
    :return: the assembled text together with the line contents it is composed of
    """
    adjusted: list[str] = []
    for index, separator in enumerate(separators):
        if adjusted and adjusted[-1] == "\r" and contents[index] == "" and separator == "\n":
            separator = "\r\n"
        adjusted.append(separator)
    return _GeneratedText("".join(c + s for c, s in zip(contents, adjusted + [""], strict=True)), contents)


# Texts using all three newline sequences the LSP defines, paired with their line contents.
# Random text alone essentially never produces "\r\n", so the newlines are drawn explicitly.
# Note that a text ending in a newline has an empty final line.
_TEXTS_WITH_LINES = st.lists(_LINE_CONTENT, min_size=1, max_size=6).flatmap(
    lambda contents: st.lists(st.sampled_from(["\n", "\r\n", "\r"]), min_size=len(contents) - 1, max_size=len(contents) - 1).map(
        lambda separators: _assemble_text(contents, separators)
    )
)


class TestTextUtils:
    LINE = "012"
    TEXT = LINE + "\n" + LINE + "\r\n" + LINE + "\r" + LINE

    def test_split_lines(self):
        lines = TextUtils.split_lines(self.TEXT, with_ends=False)
        assert len(lines) == 4
        for line in lines:
            assert line == self.LINE

    def test_split_lines_with_ends(self):
        lines = TextUtils.split_lines(self.TEXT, with_ends=True)
        assert len(lines) == 4
        for i, line in enumerate(lines):
            assert line[: len(self.LINE)] == self.LINE
        for i, ending in enumerate(["\n", "\r\n", "\r", ""]):
            assert lines[i][len(self.LINE) :] == ending

    def test_line_col_from_idx(self):
        assert TextUtils.get_line_col_from_index(self.LINE, 0) == (0, 0)
        assert TextUtils.get_line_col_from_index(self.LINE, 1) == (0, 1)
        assert TextUtils.get_line_col_from_index(self.TEXT, 0) == (0, 0)
        assert TextUtils.get_line_col_from_index(self.TEXT, 1) == (0, 1)
        assert TextUtils.get_line_col_from_index(self.TEXT, 3 + 1 + 1) == (1, 1)
        assert TextUtils.get_line_col_from_index(self.TEXT, 3 + 1 + 3 + 2 + 1) == (2, 1)

    def test_idx_from_line_col(self):
        assert TextUtils.get_index_from_line_col(self.TEXT, 0, 0) == 0
        assert TextUtils.get_index_from_line_col(self.TEXT, 0, 1) == 1
        assert TextUtils.get_index_from_line_col(self.TEXT, 1, 1) == 3 + 1 + 1
        assert TextUtils.get_index_from_line_col(self.TEXT, 2, 1) == 3 + 1 + 3 + 2 + 1

    def test_step_to(self):
        stepper = TextStepper(self.TEXT)
        stepper.step_to(2, 1)
        assert stepper.line == 2
        assert stepper.col == 1
        assert stepper.idx == 3 + 1 + 3 + 2 + 1

    def test_insert_text_at_index(self):
        insertion = "XXX"
        new_text, l, c = TextUtils.insert_text_at_position(self.TEXT, 0, 1, insertion)
        assert (l, c) == (0, 1 + len(insertion))
        assert new_text.startswith("0XXX12")

    def test_insert_text_in_next_line_beyond_content(self):
        """
        Test inserting text at a line index 1 beyond the actual number of lines.
        This case is specifically handled as an edge case in the implementation.
        """
        insertion = "XXX"
        new_text, l, c = TextUtils.insert_text_at_position(self.TEXT, 4, 0, insertion)
        assert (l, c) == (4, len(insertion))
        assert new_text == self.TEXT + "\n" + insertion

    def test_delete_text_deletes_last_line_without_trailing_newline(self) -> None:
        """Deleting the final line must work whether or not the file ends in a newline.

        delete_lines(k, N-1) addresses the position one line past the last line
        (line N, col 0). With no trailing newline there is no closing newline to
        count, so get_index_from_line_col cannot resolve it; the delete must still
        remove the last line instead of raising InvalidTextLocationError.
        """
        # File with 3 lines, no trailing newline: read_file (splitlines) shows 0='a',1='b',2='c'.
        text = "a\nb\nc"
        new_text, deleted = TextUtils.delete_text_between_positions(text, 2, 0, 3, 0)
        assert new_text == "a\nb\n"
        assert deleted == "c"

    def test_delete_text_last_line_matches_trailing_newline_variant(self) -> None:
        """Deleting the last line yields the same result with or without a trailing newline."""
        without_nl, _ = TextUtils.delete_text_between_positions("a\nb\nc", 2, 0, 3, 0)
        with_nl, _ = TextUtils.delete_text_between_positions("a\nb\nc\n", 2, 0, 3, 0)
        assert without_nl == with_nl == "a\nb\n"

    def test_delete_text_still_raises_for_out_of_range_end(self) -> None:
        """A genuinely out-of-range end position (beyond one-past-EOF) still raises."""
        with pytest.raises(InvalidTextLocationError):
            # end_line = 5 is well past the one-line-past-EOF position (3) for a 3-line file.
            TextUtils.delete_text_between_positions("a\nb\nc", 0, 0, 5, 0)


class TestTextUtilsProperties:
    """
    Property-based counterparts to the example-based tests above: these cover the space of
    newline combinations that a single fixture can only sample.
    """

    @_PROPERTY
    @given(generated=_TEXTS_WITH_LINES, data=st.data())
    def test_line_col_to_index_and_back_is_the_identity(self, generated: _GeneratedText, data: st.DataObject) -> None:
        """Converting a valid position to an index and back must yield the original position."""
        text, contents = generated.text, generated.lines
        line = data.draw(st.integers(0, len(contents) - 1))
        col = data.draw(st.integers(0, len(contents[line])))
        index = TextUtils.get_index_from_line_col(text, line, col)
        assert TextUtils.get_line_col_from_index(text, index) == (line, col)

    @_PROPERTY
    @given(generated=_TEXTS_WITH_LINES, data=st.data())
    def test_index_to_line_col_and_back_is_the_identity_outside_newline_sequences(
        self, generated: _GeneratedText, data: st.DataObject
    ) -> None:
        r"""Converting an index to a position and back must yield the original index, except for an
        index pointing into a multi-character newline sequence: "\r\n" maps to the beginning of the
        following line, as documented in get_line_col_from_index.
        """
        text = generated.text
        index = data.draw(st.integers(0, len(text)))
        line, col = TextUtils.get_line_col_from_index(text, index)
        points_into_crlf = 0 < index < len(text) and text[index - 1] == "\r" and text[index] == "\n"
        expected = index + 1 if points_into_crlf else index
        assert TextUtils.get_index_from_line_col(text, line, col) == expected

    @_PROPERTY
    @given(generated=_TEXTS_WITH_LINES)
    def test_split_lines_reconstructs_the_text(self, generated: _GeneratedText) -> None:
        """The lines with their endings must join back into the original text, and the lines
        without their endings must be the line contents.
        """
        text, contents = generated.text, generated.lines
        assert "".join(TextUtils.split_lines(text, with_ends=True)) == text
        assert TextUtils.split_lines(text, with_ends=False) == contents

    @_PROPERTY
    @given(generated=_TEXTS_WITH_LINES, excess=st.integers(1, 5))
    def test_index_beyond_the_text_is_rejected(self, generated: _GeneratedText, excess: int) -> None:
        text = generated.text
        with pytest.raises(InvalidTextLocationError):
            TextUtils.get_line_col_from_index(text, len(text) + excess)
