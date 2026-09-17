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
