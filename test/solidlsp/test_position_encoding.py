"""Regression tests for the LSP `character` (UTF-16 code unit) vs Python code-point mismatch.

The `Position.character` field the LSP spec defines is a UTF-16 code unit offset (see the
docstring on `solidlsp.lsp_protocol_handler.lsp_types.Position`, which gives the classic
`a𐐀b` example: the offset of `b` is 3, not 2, because the astral character in between counts
as two units). `SolidLanguageServer.insert_text_at_position`/`delete_text_between_positions`
receive exactly such offsets (from a real language server's response, or, via
`LanguageServerSymbol.get_body_start_position`/`get_body_end_position`, echoed straight from
one), but index into the in-memory buffer with plain Python string indexing, which counts code
points. On a line with any character outside the Basic Multilingual Plane (most emoji, for
instance), every edit position after it was one code point too far, silently corrupting the
file while returning success.
"""

from unittest.mock import MagicMock

from solidlsp.ls import SolidLanguageServer
from solidlsp.ls_types import Position


class DummyLanguageServer(SolidLanguageServer):
    def _start_server(self) -> None:
        raise AssertionError("Not used in this test")

    def _create_base_initialize_params(self) -> dict:
        return {}


class _FakeFileBuffer:
    """Stands in for `LSPFileBuffer`: exposes only what insert/delete touch."""

    def __init__(self, contents: str, uri: str) -> None:
        self.contents = contents
        self.version = 0
        self.uri = uri


def _make_server(contents: str) -> tuple[SolidLanguageServer, _FakeFileBuffer, str]:
    language_server = object.__new__(DummyLanguageServer)
    language_server.repository_root_path = "/repo"
    language_server.server_started = True
    language_server.server = MagicMock()

    uri = language_server._resolve_file_uri("fake.py")
    file_buffer = _FakeFileBuffer(contents, uri)
    language_server.open_file_buffers = {uri: file_buffer}
    return language_server, file_buffer, uri


# "𐐀" (U+10400, the LSP spec's own example character) is 1 Python code point but 2 UTF-16
# code units (a surrogate pair). A conformant language server reports the position right after
# it on this line as UTF-16 character 2, not code-point column 2.
_ASTRAL_LINE = "𐐀AB\n"


def test_insert_text_at_position_uses_utf16_column_not_codepoint_index() -> None:
    language_server, file_buffer, _ = _make_server(_ASTRAL_LINE)

    # UTF-16 character 2 is the boundary between "𐐀" and "A" (it occupies units 0-1). Treated
    # as a raw code-point index (the pre-fix behaviour), 2 lands one character later, between
    # "A" and "B".
    result = language_server.insert_text_at_position("fake.py", 0, 2, "X")

    assert file_buffer.contents == "𐐀XAB\n"
    # the returned cursor position must itself be reported back in UTF-16 units: "𐐀X" is
    # 2 + 1 = 3 UTF-16 code units, not 2 code points.
    assert result == Position(line=0, character=3)


def test_delete_text_between_positions_uses_utf16_columns_not_codepoint_indices() -> None:
    language_server, file_buffer, _ = _make_server(_ASTRAL_LINE)

    # Delete "A": UTF-16 characters 2 to 3. Treated as raw code-point indices, 2..3 deletes "B"
    # instead (one character too far, the same off-by-one the insert test exercises).
    deleted = language_server.delete_text_between_positions(
        "fake.py",
        start=Position(line=0, character=2),
        end=Position(line=0, character=3),
    )

    assert deleted == "A"
    assert file_buffer.contents == "𐐀B\n"


def test_insert_text_at_position_before_any_astral_character_is_unaffected() -> None:
    """Control: positions before the first astral character on the line need no conversion."""
    language_server, file_buffer, _ = _make_server(_ASTRAL_LINE)

    result = language_server.insert_text_at_position("fake.py", 0, 0, "X")

    assert file_buffer.contents == "X𐐀AB\n"
    assert result == Position(line=0, character=1)
