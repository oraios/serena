# SPDX-License-Identifier: MIT

from solidlsp.language_servers.godot_language_server import GodotLanguageServer


def _lines(*rows: str) -> list[str]:
    return list(rows)


def test_clamp_trailing_blank_lines_before_next_function():
    lines = _lines(
        "func first():",
        '\tprint("old")',
        "",
        "func second():",
        '\tprint("keep")',
    )
    # Godot often reports the first function ending at the start of the next one
    rng = {"start": {"line": 0, "character": 0}, "end": {"line": 3, "character": 0}}
    GodotLanguageServer._clamp_trailing_blank_lines(rng, lines)
    assert rng["end"] == {"line": 1, "character": len(lines[1])}


def test_clamp_does_not_move_end_inside_content():
    lines = _lines("func first():", '\tprint("old")', "", "func second():")
    rng = {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 12}}
    GodotLanguageServer._clamp_trailing_blank_lines(rng, lines)
    assert rng["end"] == {"line": 1, "character": len(lines[1])}


def test_clamp_never_crosses_start():
    lines = _lines("", "", "func only():", "\tpass")
    rng = {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 0}}
    GodotLanguageServer._clamp_trailing_blank_lines(rng, lines)
    assert rng["end"]["line"] == 2


def test_fix_symbol_ranges_end_to_end_on_function():
    lines = _lines(
        "func first():",
        '\tprint("old")',
        "",
        "func second():",
        '\tprint("keep")',
    )
    symbol = {
        "name": "first",
        "location": {
            "range": {
                "start": {"line": 0, "character": 0},
                # Godot-style: end at start of next function
                "end": {"line": 3, "character": 0},
            }
        },
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 3, "character": 0},
        },
        "selectionRange": {
            "start": {"line": 0, "character": 5},
            "end": {"line": 0, "character": 10},
        },
        "children": [],
    }
    GodotLanguageServer._fix_symbol_ranges(symbol, lines)
    # body/location range ends on last content line, one past last char
    assert symbol["location"]["range"]["end"] == {"line": 1, "character": len(lines[1])}
    assert symbol["range"]["end"] == {"line": 1, "character": len(lines[1])}
    # selectionRange (the identifier) is untouched
    assert symbol["selectionRange"]["start"] == {"line": 0, "character": 5}


def test_fix_range_end_off_by_one_still_applied_before_clamp():
    lines = _lines("func f():", "\tpass")
    rng = {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": len(lines[1]) + 1}}
    GodotLanguageServer._fix_range_end(rng, lines)
    GodotLanguageServer._clamp_trailing_blank_lines(rng, lines)
    assert rng["end"] == {"line": 1, "character": len(lines[1])}
