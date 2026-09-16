import pytest

from solidlsp.ls_utils import InvalidTextLocationError, LineCol, TextCoordinates


class TestTextCoordinates:
    """Tests for the public contract of TextCoordinates and LineCol."""

    @pytest.mark.parametrize(
        "content",
        [
            "hello\nworld\n",
            "hello\r\nworld\r\n",
            "hello\rworld\r",
            "a\rb\nc\r\nd\r\n",
            "",
            "no newline at end",
            "\n",
            "\r",
            "a\r\n\r\nb",
        ],
    )
    def test_line_col_at_index_end_to_end(self, content):
        """Every index within the text resolves to a position that is consistent with the line layout."""
        coordinates = TextCoordinates(content)
        for index in range(len(content) + 1):
            loc = coordinates.line_col_at_index(index)
            assert loc.line >= 0
            assert loc.col >= 0
            # a col greater than 0 implies that none of the col characters before the index is a line separator
            if loc.col > 0:
                preceding = content[index - loc.col : index]
                assert "\n" not in preceding and "\r" not in preceding

    def test_line_col_at_index_basic_lf(self):
        """Coordinates for LF-only content match the manually derived line layout."""
        coordinates = TextCoordinates("alpha\nbeta\ngamma\n")
        assert coordinates.line_col_at_index(0) == LineCol(line=0, col=0)
        assert coordinates.line_col_at_index(3) == LineCol(line=0, col=3)
        assert coordinates.line_col_at_index(5) == LineCol(line=0, col=5)
        assert coordinates.line_col_at_index(6) == LineCol(line=1, col=0)
        assert coordinates.line_col_at_index(8) == LineCol(line=1, col=2)
        assert coordinates.line_col_at_index(11) == LineCol(line=2, col=0)
        assert coordinates.line_col_at_index(12) == LineCol(line=2, col=1)
        assert coordinates.line_col_at_index(16) == LineCol(line=2, col=5)
        # an index at the end of the text (after the trailing newline) denotes the start of a new line
        assert coordinates.line_col_at_index(17) == LineCol(line=3, col=0)

    def test_line_col_at_index_crlf(self):
        r"""CRLF sequences count as a single line ending. An index pointing at the "\n" of a pair denotes
        the beginning of the following line (column 0), whereas the "\r" itself still belongs to the
        preceding line.
        """
        coordinates = TextCoordinates("alpha\r\nbeta\r\n")
        assert coordinates.line_col_at_index(0) == LineCol(line=0, col=0)
        assert coordinates.line_col_at_index(5) == LineCol(line=0, col=5)
        assert coordinates.line_col_at_index(6) == LineCol(line=1, col=0)
        assert coordinates.line_col_at_index(7) == LineCol(line=1, col=0)
        assert coordinates.line_col_at_index(8) == LineCol(line=1, col=1)
        assert coordinates.line_col_at_index(11) == LineCol(line=1, col=4)
        assert coordinates.line_col_at_index(12) == LineCol(line=2, col=0)
        assert coordinates.line_col_at_index(13) == LineCol(line=2, col=0)

    def test_line_col_at_index_bare_cr(self):
        r"""Bare "\r" characters act as line separators."""
        coordinates = TextCoordinates("alpha\rbeta\r")
        assert coordinates.line_col_at_index(5) == LineCol(line=0, col=5)
        assert coordinates.line_col_at_index(6) == LineCol(line=1, col=0)
        assert coordinates.line_col_at_index(10) == LineCol(line=1, col=4)
        assert coordinates.line_col_at_index(11) == LineCol(line=2, col=0)

    def test_line_col_at_index_mixed(self):
        """Mixed line endings resolve consistently in a single text."""
        coordinates = TextCoordinates("a\r\nb\rc\nd\r\n")
        # "\r\n" ends line 0; "\r" ends line 1; "\n" ends line 2; "\r\n" ends line 3
        assert coordinates.line_col_at_index(0) == LineCol(line=0, col=0)
        assert coordinates.line_col_at_index(1) == LineCol(line=0, col=1)
        assert coordinates.line_col_at_index(2) == LineCol(line=1, col=0)
        assert coordinates.line_col_at_index(3) == LineCol(line=1, col=0)
        assert coordinates.line_col_at_index(4) == LineCol(line=1, col=1)
        assert coordinates.line_col_at_index(5) == LineCol(line=2, col=0)
        assert coordinates.line_col_at_index(6) == LineCol(line=2, col=1)
        assert coordinates.line_col_at_index(7) == LineCol(line=3, col=0)
        assert coordinates.line_col_at_index(8) == LineCol(line=3, col=1)
        assert coordinates.line_col_at_index(9) == LineCol(line=4, col=0)
        assert coordinates.line_col_at_index(10) == LineCol(line=4, col=0)

    def test_line_col_at_index_empty_content(self):
        """The only valid index in empty content resolves to the origin."""
        coordinates = TextCoordinates("")
        assert coordinates.line_col_at_index(0) == LineCol(line=0, col=0)
        with pytest.raises(InvalidTextLocationError):
            coordinates.line_col_at_index(1)

    def test_line_col_at_index_out_of_range(self):
        """Indices beyond the text length are rejected."""
        coordinates = TextCoordinates("abc")
        with pytest.raises(InvalidTextLocationError):
            coordinates.line_col_at_index(4)
        with pytest.raises(InvalidTextLocationError):
            coordinates.line_col_at_index(-1)
