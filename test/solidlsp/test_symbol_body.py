"""Unit tests for SymbolBody / SymbolBodyFactory that need no running language server."""

import pytest

from solidlsp.ls import SymbolBodyFactory
from solidlsp.ls_exceptions import InvalidTextLocationError


class _StubBuffer:
    """Minimal stand-in for LSPFileBuffer: the factory only reads split_lines()."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def split_lines(self) -> list[str]:
        return self._lines


def _symbol(start_line: int, start_col: int, end_line: int, end_col: int) -> dict:
    return {
        "location": {
            "range": {
                "start": {"line": start_line, "character": start_col},
                "end": {"line": end_line, "character": end_col},
            }
        }
    }


# 3 lines, valid indices 0..2
LINES = ["class Foo:", "    var x = 1", "    var y = 2"]
FULL = "\n".join(LINES)


def _factory() -> SymbolBodyFactory:
    return SymbolBodyFactory(_StubBuffer(list(LINES)))


def test_get_text_in_bounds_range() -> None:
    """A range ending at the last real position returns the whole symbol (control)."""
    body = _factory().create_symbol_body(_symbol(0, 0, 2, len(LINES[2])))
    assert body.get_text() == FULL


def test_get_text_end_line_past_eof_does_not_raise() -> None:
    """A range whose end.line is past EOF used to raise IndexError in get_text.

    The LSP convention for a range covering whole lines ends it at the start of the
    following line, which for the last line is one line past EOF. That end position
    must be clamped to the end of the file, so the text runs through the last line.
    """
    body = _factory().create_symbol_body(_symbol(0, 0, len(LINES), 0))
    assert body.get_text() == FULL


def test_get_text_end_col_past_line_end() -> None:
    """An end.character past the end of a valid last line is clamped, no over-trim."""
    body = _factory().create_symbol_body(_symbol(0, 0, 2, 999))
    assert body.get_text() == FULL


def test_get_text_start_line_past_eof_returns_empty() -> None:
    """A start.line past EOF is degenerate; it must not raise and yields no text."""
    body = _factory().create_symbol_body(_symbol(len(LINES), 0, len(LINES), 0))
    assert body.get_text() == ""


def test_get_text_end_line_far_past_eof_still_raises() -> None:
    """end.line more than one line past EOF is a different, unconfirmed problem.

    Only the single-line-past-EOF case (the documented whole-line-range convention) is
    well-defined enough to correct. Anything further out is rejected explicitly, rather
    than guessing at a body that could be silently wrong.
    """
    body = _factory().create_symbol_body(_symbol(0, 0, len(LINES) + 1, 0))
    with pytest.raises(InvalidTextLocationError):
        body.get_text()


def test_get_text_end_line_past_eof_with_nonzero_col_raises() -> None:
    """end.line one past EOF with a nonzero end.character is not the documented convention.

    The well-defined case is specifically column 0 (the start of the nonexistent
    following line). A nonzero column there has no defined meaning for a line that does
    not exist, so it must raise rather than being clamped as if it were the same case.
    """
    body = _factory().create_symbol_body(_symbol(0, 0, len(LINES), 5))
    with pytest.raises(InvalidTextLocationError):
        body.get_text()
