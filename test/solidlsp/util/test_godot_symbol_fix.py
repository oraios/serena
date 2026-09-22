"""Unit tests for GodotLanguageServer's document-symbol range correction.

See oraios/serena#1974: Godot's GDScript parser can report a symbol's end column one
column past the line-end convention every other language server follows, which silently
rolls over into the following line's content (or, at the last line of a body, into the
separating blank line) when the position is later turned into a text index.
"""

from __future__ import annotations

from solidlsp.language_servers.godot_language_server import GodotLanguageServer

_fix_range_end = GodotLanguageServer._fix_range_end
_fix_symbol_ranges = GodotLanguageServer._fix_symbol_ranges


def _range(end_line: int, end_char: int, start_line: int = 0, start_char: int = 0) -> dict:
    return {"start": {"line": start_line, "character": start_char}, "end": {"line": end_line, "character": end_char}}


# The exact fixture from the reported issue: a 13-char line whose reported end column is 14.
_ISSUE_1952_LINES = ["extends Node", "", "func first():", '\tprint("old")', "", "func second():", '\tprint("keep")']


def test_fix_range_end_corrects_the_measured_off_by_one() -> None:
    rng = _range(end_line=3, end_char=14)
    _fix_range_end(rng, _ISSUE_1952_LINES)
    assert rng["end"]["character"] == 13


def test_fix_range_end_leaves_a_correct_one_past_end_column_alone() -> None:
    rng = _range(end_line=3, end_char=13)
    _fix_range_end(rng, _ISSUE_1952_LINES)
    assert rng["end"]["character"] == 13


def test_fix_range_end_does_not_guess_at_a_larger_overshoot() -> None:
    # Two past the line's end is not the measured Godot mechanism; leave it as reported
    # rather than assume the same +1 correction applies.
    rng = _range(end_line=3, end_char=15)
    _fix_range_end(rng, _ISSUE_1952_LINES)
    assert rng["end"]["character"] == 15


def test_fix_range_end_ignores_an_out_of_range_line() -> None:
    rng = _range(end_line=99, end_char=5)
    _fix_range_end(rng, _ISSUE_1952_LINES)
    assert rng["end"]["character"] == 5


def test_fix_range_end_tolerates_a_missing_end() -> None:
    _fix_range_end({"start": {"line": 0, "character": 0}}, _ISSUE_1952_LINES)  # must not raise


def test_fix_symbol_ranges_corrects_range_selection_range_and_location_recursively() -> None:
    # line 2, "func first():", is 13 chars: end_char=14 is the off-by-one, end_char=5 is not.
    child = {
        "name": "inner",
        "range": _range(end_line=3, end_char=14),
        "selectionRange": _range(end_line=2, end_char=14, start_line=2),
    }
    root = {
        "name": "first",
        "range": _range(end_line=3, end_char=14),
        "selectionRange": _range(end_line=2, end_char=5, start_line=2),
        "children": [child],
    }
    _fix_symbol_ranges(root, _ISSUE_1952_LINES)

    assert root["range"]["end"]["character"] == 13
    assert root["selectionRange"]["end"]["character"] == 5  # unaffected, no overshoot
    assert child["range"]["end"]["character"] == 13
    assert child["selectionRange"]["end"]["character"] == 13  # line 2 is 13 chars, 14 was the overshoot


def test_fix_symbol_ranges_corrects_symbol_information_style_location() -> None:
    # SymbolInformation (the flat, non-hierarchical shape) nests its range under "location".
    symbol = {"name": "first", "location": {"uri": "file:///script.gd", "range": _range(end_line=3, end_char=14)}}
    _fix_symbol_ranges(symbol, _ISSUE_1952_LINES)
    assert symbol["location"]["range"]["end"]["character"] == 13
