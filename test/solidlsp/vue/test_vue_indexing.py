"""Unit tests for VueLanguageServer._ensure_vue_files_indexed_on_ts_server that need no running
language server, mirroring the reproduction harness from GH issue #1923.
"""

import threading
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


def _make_operational_server(vue_files: list[str], failing_files: frozenset[str] = frozenset()) -> tuple[VueLanguageServer, list[int]]:
    """Build a bare VueLanguageServer with the `_ensure_ls_operational` state machine wired up,
    on top of the same indexing stand-ins as `_make_server`.

    :return: the server and a single-element list tracking how many times the (stubbed)
        cross-file-reference wait actually ran.
    """
    srv, _ = _make_server(vue_files, failing_files)
    srv.server_started = True
    srv._ls_operational_ready_event = threading.Event()
    srv._ls_operational_lock = threading.Lock()
    srv._has_waited_for_cross_file_references = False
    wait_calls = [0]
    srv._get_wait_time_for_cross_file_referencing = lambda: 0
    real_ensure_ls_operational = VueLanguageServer._ensure_ls_operational.__get__(srv)

    def _ensure_ls_operational_counting_sleeps() -> None:
        had_waited = srv._has_waited_for_cross_file_references
        real_ensure_ls_operational()
        if not had_waited and srv._has_waited_for_cross_file_references:
            wait_calls[0] += 1

    srv._ensure_ls_operational = _ensure_ls_operational_counting_sleeps  # type: ignore[method-assign]
    return srv, wait_calls


def test_ensure_ls_operational_retries_vue_indexing_on_a_later_call() -> None:
    """GH review on #1970: a total failure on the first `_ensure_ls_operational()` call must
    actually be retried by a *later* call, not just by calling
    `_ensure_vue_files_indexed_on_ts_server` directly in isolation (the gap that let the
    original fix through: `_ensure_ls_operational` unconditionally sets the ready event, which
    every real caller short-circuits on before ever reaching the retry).
    """
    srv, wait_calls = _make_operational_server(["a.vue"], failing_files=frozenset({"a.vue"}))

    srv._ensure_ls_operational()
    assert srv._vue_files_indexed is False
    assert srv._ls_operational_ready_event.is_set(), "other request types must not be blocked by a failed vue index"

    # companion server recovers; a later call (as any real request handler makes) must retry.
    # Simulates the backoff window having elapsed (see the dedicated backoff test below for the
    # window itself) rather than actually sleeping VUE_INDEX_RETRY_BACKOFF_SECONDS in a test.
    srv._ts_server = cast(Any, _FakeTSServer())
    srv._vue_index_retry_after = 0
    srv._ensure_ls_operational()
    assert srv._vue_files_indexed is True
    assert srv._indexed_vue_file_uris == ["file:///a.vue"]

    # the one-time cross-file-reference wait must not repeat just to retry vue indexing
    assert wait_calls[0] == 1


def test_ensure_ls_operational_does_not_rewait_or_block_readiness_on_permanent_vue_failure() -> None:
    """A companion server that never recovers must not turn every future request into a
    repeated cross-file-reference wait, and must not prevent operational readiness from ever
    being reached - every other request type (TS/JS definitions, renames, diagnostics) would
    otherwise re-run this whole method, including a full vue re-index attempt, on every single
    call for as long as the companion server stays down.
    """
    srv, wait_calls = _make_operational_server(["a.vue"], failing_files=frozenset({"a.vue"}))

    for _ in range(3):
        srv._ensure_ls_operational()
        assert srv._vue_files_indexed is False
        assert srv._ls_operational_ready_event.is_set()

    # still only one cross-file-reference wait across all 3 calls
    assert wait_calls[0] == 1
    # and only one indexing attempt: the backoff (tested directly below) suppresses the 2nd
    # and 3rd calls' retries, since they happen well within VUE_INDEX_RETRY_BACKOFF_SECONDS of
    # the first - without it, a permanently-broken companion server would make every single
    # future request (of any kind, not just vue-related) re-open every .vue file in the repo
    assert cast(Any, srv._ts_server).indexing_expected_count == 1


def test_ensure_ls_operational_backs_off_between_retries() -> None:
    """A failed attempt must not be retried again until VUE_INDEX_RETRY_BACKOFF_SECONDS have
    passed, even if the companion server has since recovered - otherwise every request in that
    window would still pay the cost of reopening every .vue file, just to fail.
    """
    srv, _ = _make_operational_server(["a.vue"], failing_files=frozenset({"a.vue"}))
    srv._ensure_ls_operational()
    assert srv._vue_files_indexed is False

    # companion server recovers immediately, but the backoff window has not elapsed yet
    srv._ts_server = cast(Any, _FakeTSServer())
    srv._ensure_ls_operational()
    assert srv._vue_files_indexed is False, "must not retry before the backoff window elapses"
    assert cast(Any, srv._ts_server).indexing_expected_count == 0

    # simulate the backoff window having elapsed
    srv._vue_index_retry_after = 0
    srv._ensure_ls_operational()
    assert srv._vue_files_indexed is True
    assert cast(Any, srv._ts_server).indexing_expected_count == 1
