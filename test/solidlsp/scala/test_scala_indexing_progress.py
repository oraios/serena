"""
Unit tests for the tracking of the work-done progress Metals reports.
"""

import threading
import time

import pytest

from solidlsp.language_servers.scala_language_server import (
    DEFAULT_INDEXING_QUIET_PERIOD,
    DEFAULT_INDEXING_START_GRACE,
    DEFAULT_INDEXING_TIMEOUT,
    IndexingOutcome,
    MetalsProgressTracker,
    _get_scala_settings,
)
from solidlsp.ls_config import LanguageServerId
from solidlsp.settings import SolidLSPSettings

# `$/progress` as Metals sends it (scala/meta/internal/metals/WorkDoneProgress.scala), whose
# titles are the ones that matter to a cross-file query: the build import, the index, and the
# compilation that produces the SemanticDB references are read from.
IMPORTING = "Importing build"
INDEXING = "Indexing"
COMPILING = "Compiling core"


def begin(token: str, title: str) -> dict:
    return {"token": token, "value": {"kind": "begin", "title": title}}


def report(token: str, message: str = "1s") -> dict:
    return {"token": token, "value": {"kind": "report", "message": message}}


def end(token: str) -> dict:
    return {"token": token, "value": {"kind": "end"}}


@pytest.fixture
def tracker() -> MetalsProgressTracker:
    return MetalsProgressTracker()


def test_no_work_reported(tracker: MetalsProgressTracker) -> None:
    """A server that reports nothing must not hold a query for the whole timeout."""
    tracker.expect_work()
    started = time.monotonic()
    assert tracker.wait_until_idle(timeout=30, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.NO_WORK
    assert time.monotonic() - started < 5


def test_waits_for_work_that_starts_within_the_grace(tracker: MetalsProgressTracker) -> None:
    tracker.expect_work()

    def work() -> None:
        time.sleep(0.1)
        tracker.on_progress(begin("t1", INDEXING))
        time.sleep(0.2)
        tracker.on_progress(end("t1"))

    threading.Thread(target=work, daemon=True).start()
    assert tracker.wait_until_idle(timeout=10, start_grace=2, quiet_period=0.1) == IndexingOutcome.IDLE


def test_waits_for_every_outstanding_token(tracker: MetalsProgressTracker) -> None:
    """Indexing ending is not readiness: the compilations that follow it must be waited for too."""
    tracker.on_progress(begin("index", INDEXING))
    tracker.on_progress(begin("compile", COMPILING))
    tracker.on_progress(report("index"))
    tracker.on_progress(end("index"))

    assert tracker.wait_until_idle(timeout=0.2, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.TIMEOUT
    assert COMPILING in tracker.describe()

    tracker.on_progress(end("compile"))
    assert tracker.wait_until_idle(timeout=1, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.IDLE


def test_token_created_before_it_begins_is_awaited(tracker: MetalsProgressTracker) -> None:
    """`window/workDoneProgress/create` arrives first, and work announced that way still counts."""
    assert tracker.on_create({"token": "t1"}) == {}
    assert tracker.wait_until_idle(timeout=0.2, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.TIMEOUT

    tracker.on_progress(begin("t1", IMPORTING))
    tracker.on_progress(end("t1"))
    assert tracker.wait_until_idle(timeout=1, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.IDLE


def test_unknown_and_repeated_ends_do_not_unbalance_the_count(tracker: MetalsProgressTracker) -> None:
    tracker.on_progress(begin("t1", INDEXING))
    tracker.on_progress(end("unknown"))
    assert tracker.wait_until_idle(timeout=0.2, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.TIMEOUT

    tracker.on_progress(end("t1"))
    tracker.on_progress(end("t1"))
    assert tracker.wait_until_idle(timeout=1, start_grace=0.2, quiet_period=0.1) == IndexingOutcome.IDLE


def test_describe_reports_outstanding_titles(tracker: MetalsProgressTracker) -> None:
    assert "<none>" in tracker.describe()
    tracker.on_progress(begin("t1", COMPILING))
    described = tracker.describe()
    assert COMPILING in described
    assert "idle=False" in described


def test_indexing_settings_defaults() -> None:
    settings = _get_scala_settings(SolidLSPSettings())
    assert settings["indexing_timeout"] == DEFAULT_INDEXING_TIMEOUT
    assert settings["indexing_start_grace"] == DEFAULT_INDEXING_START_GRACE


@pytest.mark.parametrize("value", [45, 45.0])
def test_indexing_settings_are_read(value: object) -> None:
    settings = _get_scala_settings(SolidLSPSettings(ls_specific_settings={LanguageServerId.SCALA: {"indexing_timeout": value}}))
    assert settings["indexing_timeout"] == 45.0


@pytest.mark.parametrize("value", [0, -1, "soon", True, None])
def test_invalid_indexing_settings_fall_back_to_the_default(value: object) -> None:
    settings = _get_scala_settings(SolidLSPSettings(ls_specific_settings={LanguageServerId.SCALA: {"indexing_start_grace": value}}))
    assert settings["indexing_start_grace"] == DEFAULT_INDEXING_START_GRACE


def test_a_gap_between_phases_does_not_end_the_wait(tracker: MetalsProgressTracker) -> None:
    """Metals' token set empties between its phases; the wait must not return in that gap."""
    tracker.on_progress(begin("import", IMPORTING))

    def work() -> None:
        tracker.on_progress(end("import"))
        time.sleep(0.4)  # the handover, during which nothing is outstanding
        tracker.on_progress(begin("index", INDEXING))
        time.sleep(0.2)
        tracker.on_progress(end("index"))

    threading.Thread(target=work, daemon=True).start()
    started = time.monotonic()
    assert tracker.wait_until_idle(timeout=10, start_grace=1, quiet_period=0.6) == IndexingOutcome.IDLE
    assert time.monotonic() - started >= 0.6, "returned during the gap, before indexing began"


def test_quiet_period_default_is_read() -> None:
    assert _get_scala_settings(SolidLSPSettings())["indexing_quiet_period"] == DEFAULT_INDEXING_QUIET_PERIOD
