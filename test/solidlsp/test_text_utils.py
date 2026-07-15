from solidlsp.ls_utils import TextUtils


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
