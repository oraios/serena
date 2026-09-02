"""Unit tests for VueLanguageServer._ensure_vue_files_indexed_on_ts_server that need no running
language server, mirroring the reproduction harness from GH issue #1923.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

from solidlsp.language_servers.vue_language_server import VueLanguageServer


@dataclass
class _FakeFileBuffer:
    uri: str
    ref_count: int = 0


class _FakeTSServer:
    """Minimal stand-in for VueTypeScriptServer: only open_file()/expect_indexing() are exercised."""

    def __init__(self, failing_files: frozenset[str] = frozenset()) -> None:
        self._failing_files = failing_files
        self.indexing_expected_count = 0

    def expect_indexing(self) -> None:
        self.indexing_expected_count += 1

    @contextmanager
    def open_file(self, relative_path: str) -> Iterator[_FakeFileBuffer]:
        if relative_path in self._failing_files:
            raise RuntimeError(f"companion TS server unavailable for {relative_path}")
        yield _FakeFileBuffer(uri=f"file:///{relative_path}")


def _make_server(vue_files: list[str], failing_files: frozenset[str] = frozenset()) -> tuple[VueLanguageServer, list[int]]:
    """Build a bare VueLanguageServer with just enough state to exercise the indexing method.

    :return: the server and a single-element list tracking how many times
        _wait_for_ts_indexing_complete was called (a plain counter, since the method itself is
        stubbed to a no-op).
    """
    srv = object.__new__(VueLanguageServer)
    srv._vue_files_indexed = False
    srv._indexed_vue_file_uris = []
    srv._ts_server = cast(Any, _FakeTSServer(failing_files))
    srv._find_all_vue_files = lambda: list(vue_files)
    wait_calls = [0]
    srv._wait_for_ts_indexing_complete = lambda: wait_calls.__setitem__(0, wait_calls[0] + 1)
    return srv, wait_calls


def test_all_files_fail_leaves_indexed_flag_unset() -> None:
    """A companion server that is down/unresponsive fails every open; the completion flag must
    stay False so a later call retries, instead of silently and permanently losing cross-file
    indexing (GH #1923).
    """
    srv, wait_calls = _make_server(["a.vue", "b.vue"], failing_files=frozenset({"a.vue", "b.vue"}))
    srv._ensure_vue_files_indexed_on_ts_server()
    assert srv._vue_files_indexed is False
    assert srv._indexed_vue_file_uris == []
    assert wait_calls[0] == 0


def test_all_files_succeed_sets_indexed_flag() -> None:
    srv, wait_calls = _make_server(["a.vue", "b.vue"])
    srv._ensure_vue_files_indexed_on_ts_server()
    assert srv._vue_files_indexed is True
    assert srv._indexed_vue_file_uris == ["file:///a.vue", "file:///b.vue"]
    assert wait_calls[0] == 1


def test_partial_failure_still_sets_indexed_flag() -> None:
    """Some coverage is better than none; only a *total* failure defers completion."""
    srv, wait_calls = _make_server(["a.vue", "b.vue"], failing_files=frozenset({"a.vue"}))
    srv._ensure_vue_files_indexed_on_ts_server()
    assert srv._vue_files_indexed is True
    assert srv._indexed_vue_file_uris == ["file:///b.vue"]
    assert wait_calls[0] == 1


def test_no_vue_files_sets_indexed_flag() -> None:
    """Nothing to index is not the failure case; it is trivially complete."""
    srv, wait_calls = _make_server([])
    srv._ensure_vue_files_indexed_on_ts_server()
    assert srv._vue_files_indexed is True
    assert srv._indexed_vue_file_uris == []
    assert wait_calls[0] == 1


def test_retry_after_total_failure_can_succeed() -> None:
    """A transient companion-server outage must not be permanent: once it recovers, the next
    call finishes indexing instead of short-circuiting on a flag that was never set.
    """
    srv, wait_calls = _make_server(["a.vue"], failing_files=frozenset({"a.vue"}))
    srv._ensure_vue_files_indexed_on_ts_server()
    assert srv._vue_files_indexed is False

    # the companion server recovers; the next call should actually retry, not short-circuit
    srv._ts_server = cast(Any, _FakeTSServer())
    srv._ensure_vue_files_indexed_on_ts_server()
    assert srv._vue_files_indexed is True
    assert srv._indexed_vue_file_uris == ["file:///a.vue"]
    assert wait_calls[0] == 1
