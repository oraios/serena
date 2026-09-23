import pytest

from solidlsp.ls_utils import InvalidTextLocationError, TextCoordinateProvider, TextCoordinates


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
        coordinates = TextCoordinateProvider(content)
        for index in range(len(content) + 1):
            loc = coordinates.compute_coordinates(index)
            assert loc.line >= 0
            assert loc.col >= 0
            # a col greater than 0 implies that none of the col characters before the index is a line separator
            if loc.col > 0:
                preceding = content[index - loc.col : index]
                assert "\n" not in preceding and "\r" not in preceding

    def test_line_col_at_index_basic_lf(self):
        """Coordinates for LF-only content match the manually derived line layout."""
        coordinates = TextCoordinateProvider("alpha\nbeta\ngamma\n")
        assert coordinates.compute_coordinates(0) == TextCoordinates(line=0, col=0)
        assert coordinates.compute_coordinates(3) == TextCoordinates(line=0, col=3)
        assert coordinates.compute_coordinates(5) == TextCoordinates(line=0, col=5)
        assert coordinates.compute_coordinates(6) == TextCoordinates(line=1, col=0)
        assert coordinates.compute_coordinates(8) == TextCoordinates(line=1, col=2)
        assert coordinates.compute_coordinates(11) == TextCoordinates(line=2, col=0)
        assert coordinates.compute_coordinates(12) == TextCoordinates(line=2, col=1)
        assert coordinates.compute_coordinates(16) == TextCoordinates(line=2, col=5)
        # an index at the end of the text (after the trailing newline) denotes the start of a new line
        assert coordinates.compute_coordinates(17) == TextCoordinates(line=3, col=0)

    def test_line_col_at_index_crlf(self):
        r"""CRLF sequences count as a single line ending. An index pointing at the "\n" of a pair denotes
        the beginning of the following line (column 0), whereas the "\r" itself still belongs to the
        preceding line.
        """
        coordinates = TextCoordinateProvider("alpha\r\nbeta\r\n")
        assert coordinates.compute_coordinates(0) == TextCoordinates(line=0, col=0)
        assert coordinates.compute_coordinates(5) == TextCoordinates(line=0, col=5)
        assert coordinates.compute_coordinates(6) == TextCoordinates(line=1, col=0)
        assert coordinates.compute_coordinates(7) == TextCoordinates(line=1, col=0)
        assert coordinates.compute_coordinates(8) == TextCoordinates(line=1, col=1)
        assert coordinates.compute_coordinates(11) == TextCoordinates(line=1, col=4)
        assert coordinates.compute_coordinates(12) == TextCoordinates(line=2, col=0)
        assert coordinates.compute_coordinates(13) == TextCoordinates(line=2, col=0)

    def test_line_col_at_index_bare_cr(self):
        r"""Bare "\r" characters act as line separators."""
        coordinates = TextCoordinateProvider("alpha\rbeta\r")
        assert coordinates.compute_coordinates(5) == TextCoordinates(line=0, col=5)
        assert coordinates.compute_coordinates(6) == TextCoordinates(line=1, col=0)
        assert coordinates.compute_coordinates(10) == TextCoordinates(line=1, col=4)
        assert coordinates.compute_coordinates(11) == TextCoordinates(line=2, col=0)

    def test_line_col_at_index_mixed(self):
        """Mixed line endings resolve consistently in a single text."""
        coordinates = TextCoordinateProvider("a\r\nb\rc\nd\r\n")
        # "\r\n" ends line 0; "\r" ends line 1; "\n" ends line 2; "\r\n" ends line 3
        assert coordinates.compute_coordinates(0) == TextCoordinates(line=0, col=0)
        assert coordinates.compute_coordinates(1) == TextCoordinates(line=0, col=1)
        assert coordinates.compute_coordinates(2) == TextCoordinates(line=1, col=0)
        assert coordinates.compute_coordinates(3) == TextCoordinates(line=1, col=0)
        assert coordinates.compute_coordinates(4) == TextCoordinates(line=1, col=1)
        assert coordinates.compute_coordinates(5) == TextCoordinates(line=2, col=0)
        assert coordinates.compute_coordinates(6) == TextCoordinates(line=2, col=1)
        assert coordinates.compute_coordinates(7) == TextCoordinates(line=3, col=0)
        assert coordinates.compute_coordinates(8) == TextCoordinates(line=3, col=1)
        assert coordinates.compute_coordinates(9) == TextCoordinates(line=4, col=0)
        assert coordinates.compute_coordinates(10) == TextCoordinates(line=4, col=0)

    def test_line_col_at_index_empty_content(self):
        """The only valid index in empty content resolves to the origin."""
        coordinates = TextCoordinateProvider("")
        assert coordinates.compute_coordinates(0) == TextCoordinates(line=0, col=0)
        with pytest.raises(InvalidTextLocationError):
            coordinates.compute_coordinates(1)

    def test_line_col_at_index_out_of_range(self):
        """Indices beyond the text length are rejected."""
        coordinates = TextCoordinateProvider("abc")
        with pytest.raises(InvalidTextLocationError):
            coordinates.compute_coordinates(4)
        with pytest.raises(InvalidTextLocationError):
            coordinates.compute_coordinates(-1)
