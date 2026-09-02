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


def _symbol(
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
    selection_range: dict | None = None,
    name: str = "some_symbol",
) -> dict:
    symbol: dict = {
        "name": name,
        "location": {
            "relativePath": "some_file.py",
            "range": {
                "start": {"line": start_line, "character": start_col},
                "end": {"line": end_line, "character": end_col},
            },
        },
    }
    if selection_range is not None:
        symbol["selectionRange"] = selection_range
    return symbol


def _range(start_line: int, start_col: int, end_line: int, end_col: int) -> dict:
    return {"start": {"line": start_line, "character": start_col}, "end": {"line": end_line, "character": end_col}}


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


def test_selection_range_within_body_range_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """A selectionRange inside the body range is the normal case; it must not warn."""
    selection_range = _range(1, 4, 1, 9)  # "var x" inside line 1
    with caplog.at_level("WARNING"):
        body = _factory().create_symbol_body(_symbol(0, 0, 2, len(LINES[2]), selection_range=selection_range))
    assert body.get_text() == FULL
    assert caplog.records == []


def test_selection_range_outside_body_range_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A selectionRange outside the body range indicates a stale/mismatched language server
    response (see GH issue #1593); the body is still returned as before, but a warning is logged
    so the mismatch is visible instead of silently yielding a body for the wrong symbol.
    """
    selection_range = _range(5, 0, 5, 3)  # entirely outside the symbol's own range (rows 0-2)
    with caplog.at_level("WARNING"):
        body = _factory().create_symbol_body(_symbol(0, 0, 2, len(LINES[2]), selection_range=selection_range, name="make-nested"))
    assert body.get_text() == FULL  # behaviour (the extracted body) is unchanged
    assert len(caplog.records) == 1
    assert "make-nested" in caplog.records[0].message
    assert "some_file.py" in caplog.records[0].message


def test_selection_range_missing_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    """Symbols without a selectionRange (e.g. SymbolKind.File) skip the check entirely."""
    with caplog.at_level("WARNING"):
        body = _factory().create_symbol_body(_symbol(0, 0, 2, len(LINES[2])))
    assert body.get_text() == FULL
    assert caplog.records == []
