"""
Characterization tests for document-symbol caching in ``SolidLanguageServer``.

These tests PIN the CURRENT behavior of ``request_document_symbols``
(``src/solidlsp/ls.py``) and its two backing caches BEFORE the planned
refactoring of ``SolidLanguageServer`` into a facade over smaller collaborators.

Two caches are involved:
  * the high-level document symbols cache (``_document_symbols_cache``), which
    maps a relative file path to ``(content_hash, DocumentSymbols)``; and
  * the raw document symbols cache (``_raw_document_symbols_cache``), which maps
    a relative file path to ``(content_hash, raw_ls_response)``.

This is a safety net, not a specification: every assertion encodes the ACTUAL
observed behavior of the unmodified code. The tests reach into the (private)
cache dictionaries on purpose -- that internal state IS the behavior under
characterization here.
"""

import os

import pytest

from solidlsp import SolidLanguageServer
from solidlsp.ls import DocumentSymbols
from solidlsp.ls_config import Language

# File in the shared python sample repo with a stable set of top-level symbols.
MODELS_FILE = os.path.join("test_repo", "models.py")
# A separate existing file used for the "empty/None response" cases.
UTILS_FILE = os.path.join("test_repo", "utils.py")


def _root_names(document_symbols: DocumentSymbols) -> set[str]:
    """Names of the root (top-level) symbols in the document symbol tree."""
    return {s.get("name") for s in document_symbols.root_symbols}


def _all_names(document_symbols: DocumentSymbols) -> set[str]:
    """Names of every symbol (roots + descendants) in the document symbol tree."""
    return {s.get("name") for s in document_symbols.iter_symbols()}


def _clear_caches_for(ls: SolidLanguageServer, key: str) -> None:
    """Drop any cached entries for ``key`` so a call starts from a cold state.

    The LS may have loaded a persistent on-disk cache at construction time, so
    clearing the in-memory entry is what makes 'cold call' deterministic.
    """
    ls._document_symbols_cache.pop(key, None)
    ls._raw_document_symbols_cache.pop(key, None)


def _content_hash(ls: SolidLanguageServer, rel_path: str) -> str:
    """The content hash the caches key on, as computed from the current file."""
    with ls.open_file(rel_path, open_in_ls=False) as fb:
        return fb.content_hash


@pytest.mark.python
@pytest.mark.parametrize("language_server", [Language.PYTHON], indirect=True)
class TestDocumentSymbolCaching:
    def test_cold_call_returns_expected_top_level_symbols(self, language_server: SolidLanguageServer) -> None:
        """(a) A cold call returns a DocumentSymbols tree with the expected top-level symbols."""
        ls = language_server
        _clear_caches_for(ls, MODELS_FILE)

        result = ls.request_document_symbols(MODELS_FILE)

        assert isinstance(result, DocumentSymbols)
        root_names = _root_names(result)
        # models.py defines these at module level (three classes + one function).
        expected_top_level = {"BaseModel", "User", "Item", "create_user_object"}
        assert expected_top_level.issubset(root_names), (
            f"expected {sorted(expected_top_level)} among top-level symbols, got {sorted(root_names)}"
        )

        # The cold call populated the high-level cache with the current content
        # hash, and the cached object IS the object that was returned.
        assert MODELS_FILE in ls._document_symbols_cache
        cached_hash, cached_symbols = ls._document_symbols_cache[MODELS_FILE]
        assert cached_symbols is result
        assert cached_hash == _content_hash(ls, MODELS_FILE)

    def test_second_call_with_unchanged_content_served_from_cache(self, language_server: SolidLanguageServer) -> None:
        """(b) A second call with unchanged content is served from cache: same object, same hash."""
        ls = language_server
        _clear_caches_for(ls, MODELS_FILE)

        first = ls.request_document_symbols(MODELS_FILE)
        hash_after_first, _ = ls._document_symbols_cache[MODELS_FILE]

        second = ls.request_document_symbols(MODELS_FILE)
        hash_after_second, _ = ls._document_symbols_cache[MODELS_FILE]

        # A cache HIT returns the very same cached DocumentSymbols object; the
        # tree is not rebuilt when the content hash is unchanged.
        assert second is first
        assert hash_after_second == hash_after_first
        assert hash_after_second == _content_hash(ls, MODELS_FILE)

    def test_changed_content_marks_cache_stale_and_rebuilds(self, language_server: SolidLanguageServer) -> None:
        """(c) After the file content changes, the cached entry is treated as stale and rebuilt."""
        ls = language_server
        rel_path = os.path.join("test_repo", "_char_cache_stale_sample.py")
        abs_path = os.path.join(ls.repository_root_path, rel_path)
        _clear_caches_for(ls, rel_path)
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("class AlphaClass:\n    def alpha_method(self):\n        return 1\n")

            first = ls.request_document_symbols(rel_path)
            assert "AlphaClass" in _all_names(first)
            hash_a, cached_first = ls._document_symbols_cache[rel_path]
            assert cached_first is first

            # Change the file content on disk (different top-level symbol).
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write("class BetaClass:\n    def beta_method(self):\n        return 2\n")

            # The new content hashes differently, but the cache still holds the
            # old entry -- i.e. it is now stale relative to the file.
            new_hash = _content_hash(ls, rel_path)
            assert new_hash != hash_a
            stale_hash, _ = ls._document_symbols_cache[rel_path]
            assert stale_hash == hash_a

            second = ls.request_document_symbols(rel_path)

            # The stale entry is rebuilt: a NEW object reflecting the new content,
            # with the cache updated to the new content hash.
            assert second is not first
            second_names = _all_names(second)
            assert "BetaClass" in second_names
            assert "AlphaClass" not in second_names
            rebuilt_hash, cached_second = ls._document_symbols_cache[rel_path]
            assert rebuilt_hash == new_hash
            assert cached_second is second
        finally:
            _clear_caches_for(ls, rel_path)
            if os.path.exists(abs_path):
                os.remove(abs_path)

    def test_none_ls_response_not_cached_in_raw_cache(self, language_server: SolidLanguageServer, monkeypatch: pytest.MonkeyPatch) -> None:
        """(d) A None language-server response is not stored in the raw cache."""
        ls = language_server
        _clear_caches_for(ls, UTILS_FILE)
        monkeypatch.setattr(ls.server.send, "document_symbol", lambda *args, **kwargs: None)

        raw = ls._request_document_symbols(UTILS_FILE, None)

        assert raw is None
        assert UTILS_FILE not in ls._raw_document_symbols_cache

    def test_empty_ls_response_not_cached_in_raw_cache(self, language_server: SolidLanguageServer, monkeypatch: pytest.MonkeyPatch) -> None:
        """(d) An empty language-server response is not stored in the raw cache."""
        ls = language_server
        _clear_caches_for(ls, UTILS_FILE)
        monkeypatch.setattr(ls.server.send, "document_symbol", lambda *args, **kwargs: [])

        raw = ls._request_document_symbols(UTILS_FILE, None)

        assert raw == []
        assert UTILS_FILE not in ls._raw_document_symbols_cache

    def test_none_response_does_not_poison_caches(self, language_server: SolidLanguageServer, monkeypatch: pytest.MonkeyPatch) -> None:
        """(d) A None response returns empty symbols without poisoning either cache; a later real call rebuilds."""
        ls = language_server
        _clear_caches_for(ls, UTILS_FILE)

        monkeypatch.setattr(ls.server.send, "document_symbol", lambda *args, **kwargs: None)
        result = ls.request_document_symbols(UTILS_FILE)

        # An empty DocumentSymbols is returned, and neither cache retains an entry.
        assert isinstance(result, DocumentSymbols)
        assert result.root_symbols == []
        assert UTILS_FILE not in ls._raw_document_symbols_cache
        assert UTILS_FILE not in ls._document_symbols_cache

        # With the real LS restored, the (unpoisoned) caches let a fresh call
        # query the language server again and return real symbols.
        monkeypatch.undo()
        real = ls.request_document_symbols(UTILS_FILE)
        assert len(real.root_symbols) > 0
