import pytest

from solidlsp.ls_utils import InvalidTextLocationError, TextStepper, TextUtils


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

    def test_insert_position_accounts_for_newline_merge(self) -> None:
        r"""A leading "\n" inserted directly after an existing "\r" merges with it into a single
        "\r\n" newline sequence. The returned position must therefore be derived from the
        resulting text; computing it from the inserted text alone reports a line too far.
        """
        new_text, line, col = TextUtils.insert_text_at_position("\r", 1, 0, "\n")
        assert new_text == "\r\n"
        assert (line, col) == (1, 0)

    def test_insert_position_after_full_text_accounts_for_newline_merge(self) -> None:
        r"""Inserting one line past the last line prepends a "\n" to the inserted text; when the
        text ends in "\r" the two merge into a single "\r\n". The returned position must describe
        where the inserted text actually ended up.
        """
        new_text, line, col = TextUtils.insert_text_at_position("a\r", 2, 0, "X")
        assert new_text == "a\r\nX"
        assert (line, col) == (1, 1)

    def test_insert_position_after_full_text_without_merge(self) -> None:
        r"""The same one-line-past-EOF insertion into "\n"-terminated text is unaffected."""
        new_text, line, col = TextUtils.insert_text_at_position("a\n", 2, 0, "X")
        assert new_text == "a\n\nX"
        assert (line, col) == (2, 1)

    def test_insert_position_accounts_for_newline_merge_mid_document(self) -> None:
        r"""The merge is not specific to the end of the buffer: inserting "\n" at the start of a
        line that follows a bare "\r" merges with that "\r" in the middle of the document too.
        """
        new_text, line, col = TextUtils.insert_text_at_position("x\ry", 1, 0, "\n")
        assert new_text == "x\r\ny"
        assert (line, col) == (1, 0)

    def test_insert_position_inside_newline_sequence_splits_it(self) -> None:
        r"""Inserting between the "\r" and the "\n" of a "\r\n" splits it into two newline
        sequences, adding a line. The position must again come from the resulting text.
        """
        new_text, line, col = TextUtils.insert_text_at_position("\r\n", 0, 1, "Z")
        assert new_text == "\rZ\n"
        assert (line, col) == (1, 1)

    def test_insert_at_column_beyond_text_appends(self) -> None:
        """A column past the end of the text appends and reports the true end position.

        Callers may pass a column that exceeds the text length -- notably an LSP column, which
        counts UTF-16 code units, for a line containing non-BMP characters. The insertion clamps
        to the end of the text, so the reported position must too, rather than addressing an
        index that does not exist in the result.
        """
        new_text, line, col = TextUtils.insert_text_at_position("abc", 0, 10, "X")
        assert new_text == "abcX"
        assert (line, col) == (0, 4)

    def test_insert_at_column_beyond_text_containing_non_bmp_character(self) -> None:
        """A non-BMP character is one code point but two UTF-16 code units, which is one way a
        caller's column comes to exceed the text length. The column is clamped, and the returned
        position is expressed in code points like every other position in TextUtils.
        """
        new_text, line, col = TextUtils.insert_text_at_position("\U0001f600", 0, 2, "X")
        assert new_text == "\U0001f600X"
        assert (line, col) == (0, 2)
