"""
Characterization tests for open-document management in ``SolidLanguageServer``.

Phase 0 safety net: these tests PIN THE CURRENT behavior of open-document
management (see ``src/solidlsp/ls.py`` around lines 1428-1577) BEFORE the planned
refactor of the god class into a facade over smaller collaborators. They encode
the ACTUAL observed behavior of:

- ``open_file`` / ``_open_file_context`` refcounting: nested ``open_file`` calls
  for the same path share a single ``LSPFileBuffer`` and increment/decrement
  ``ref_count``; the buffer is only removed from ``open_file_buffers`` once
  ``ref_count`` returns to 0;
- ``insert_text_at_position``: returns the updated ``Position`` and mutates the
  in-memory buffer contents;
- ``delete_text_between_positions``: returns the deleted text and mutates the
  in-memory buffer contents.

These tests are intentionally backend-independent (the logic under test lives
entirely in ``ls.py``), so they run against the default ``Language.PYTHON``
backend only to stay fast and deterministic. All mutations are in-memory only
(the setter never writes to disk), and every ``open_file`` context is closed so
the module-scoped language server is left with no lingering open buffers.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls_config import Language

MODELS_FILE = os.path.join("test_repo", "models.py")


@pytest.mark.python
@pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
class TestOpenFileRefCounting:
    """Pin the reference-counting semantics of ``open_file``."""

    def test_single_open_registers_buffer_then_removes_on_exit(self, language_server: SolidLanguageServer) -> None:
        uri = language_server._resolve_file_uri(MODELS_FILE)
        assert uri not in language_server.open_file_buffers

        with language_server.open_file(MODELS_FILE) as fb:
            assert fb.uri == uri
            assert fb.ref_count == 1
            # The registered buffer is the very object yielded by the context.
            assert language_server.open_file_buffers[uri] is fb

        # ref_count returned to 0 -> buffer removed from the registry.
        assert uri not in language_server.open_file_buffers

    def test_nested_open_shares_single_buffer_and_refcounts(self, language_server: SolidLanguageServer) -> None:
        uri = language_server._resolve_file_uri(MODELS_FILE)

        with language_server.open_file(MODELS_FILE) as outer:
            assert outer.ref_count == 1
            with language_server.open_file(MODELS_FILE) as inner:
                # The same path yields the SAME buffer instance (shared state).
                assert inner is outer
                assert inner.ref_count == 2
                assert language_server.open_file_buffers[uri] is outer
            # Leaving the inner context decrements the shared buffer...
            assert outer.ref_count == 1
            # ...but the buffer stays registered while the outer ref is alive.
            assert language_server.open_file_buffers[uri] is outer

        # Only once ref_count returns to 0 is the buffer removed.
        assert uri not in language_server.open_file_buffers

    def test_triple_nested_open_refcounts_step_by_step(self, language_server: SolidLanguageServer) -> None:
        uri = language_server._resolve_file_uri(MODELS_FILE)

        with language_server.open_file(MODELS_FILE) as fb1:
            with language_server.open_file(MODELS_FILE) as fb2:
                with language_server.open_file(MODELS_FILE) as fb3:
                    assert fb1 is fb2 is fb3
                    assert fb1.ref_count == 3
                assert fb1.ref_count == 2
                assert language_server.open_file_buffers[uri] is fb1
            assert fb1.ref_count == 1
            assert language_server.open_file_buffers[uri] is fb1

        assert uri not in language_server.open_file_buffers

    def test_open_in_ls_false_still_registers_and_refcounts(self, language_server: SolidLanguageServer) -> None:
        """Refcounting is independent of whether the file is opened in the LS."""
        uri = language_server._resolve_file_uri(MODELS_FILE)

        with language_server.open_file(MODELS_FILE, open_in_ls=False) as fb:
            assert language_server.open_file_buffers[uri] is fb
            assert fb.ref_count == 1
            with language_server.open_file(MODELS_FILE, open_in_ls=False) as inner:
                assert inner is fb
                assert fb.ref_count == 2
            assert fb.ref_count == 1

        assert uri not in language_server.open_file_buffers


@pytest.mark.python
@pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
class TestInsertTextAtPosition:
    """Pin the return value and buffer mutation of ``insert_text_at_position``."""

    def test_single_line_insert_returns_position_and_updates_buffer(self, language_server: SolidLanguageServer) -> None:
        with language_server.open_file(MODELS_FILE) as fb:
            original = fb.contents
            pos = language_server.insert_text_at_position(MODELS_FILE, 0, 0, "XYZ")

            # No newline inserted: line unchanged, character advances by len(text).
            assert pos == {"line": 0, "character": 3}
            # In-memory contents updated with the inserted prefix.
            assert fb.contents == "XYZ" + original

    def test_multiline_insert_returns_position_after_last_newline(self, language_server: SolidLanguageServer) -> None:
        with language_server.open_file(MODELS_FILE) as fb:
            original = fb.contents
            inserted = "# a\n# b\n"
            pos = language_server.insert_text_at_position(MODELS_FILE, 0, 0, inserted)

            # Two newlines -> line advances by 2; character is the length of the
            # text following the final newline (here the empty string -> 0).
            assert pos == {"line": 2, "character": 0}
            assert fb.contents == inserted + original

    def test_insert_increments_buffer_version(self, language_server: SolidLanguageServer) -> None:
        with language_server.open_file(MODELS_FILE) as fb:
            version_before = fb.version
            language_server.insert_text_at_position(MODELS_FILE, 0, 0, "Q")
            assert fb.version == version_before + 1

    def test_insert_without_open_file_raises_assertion_error(self, language_server: SolidLanguageServer) -> None:
        """Mutation helpers assert the file is already open."""
        uri = language_server._resolve_file_uri(MODELS_FILE)
        assert uri not in language_server.open_file_buffers
        with pytest.raises(AssertionError):
            language_server.insert_text_at_position(MODELS_FILE, 0, 0, "X")


@pytest.mark.python
@pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
class TestDeleteTextBetweenPositions:
    """Pin the return value and buffer mutation of ``delete_text_between_positions``."""

    def test_delete_returns_deleted_text_and_updates_buffer(self, language_server: SolidLanguageServer) -> None:
        with language_server.open_file(MODELS_FILE) as fb:
            # Insert a known marker so the delete target is deterministic and
            # independent of the sample file's actual contents.
            language_server.insert_text_at_position(MODELS_FILE, 0, 0, "HELLO")
            contents_with_marker = fb.contents
            assert contents_with_marker.startswith("HELLO")

            deleted = language_server.delete_text_between_positions(
                MODELS_FILE,
                {"line": 0, "character": 0},
                {"line": 0, "character": 5},
            )

            assert deleted == "HELLO"
            assert fb.contents == contents_with_marker[5:]

    def test_delete_increments_buffer_version(self, language_server: SolidLanguageServer) -> None:
        with language_server.open_file(MODELS_FILE) as fb:
            language_server.insert_text_at_position(MODELS_FILE, 0, 0, "ABCDE")
            version_before = fb.version
            language_server.delete_text_between_positions(
                MODELS_FILE,
                {"line": 0, "character": 0},
                {"line": 0, "character": 5},
            )
            assert fb.version == version_before + 1

    def test_insert_then_delete_round_trips_buffer_contents(self, language_server: SolidLanguageServer) -> None:
        with language_server.open_file(MODELS_FILE) as fb:
            original = fb.contents
            language_server.insert_text_at_position(MODELS_FILE, 0, 0, "TEMP\n")
            assert fb.contents == "TEMP\n" + original

            deleted = language_server.delete_text_between_positions(
                MODELS_FILE,
                {"line": 0, "character": 0},
                {"line": 1, "character": 0},
            )

            assert deleted == "TEMP\n"
            assert fb.contents == original
