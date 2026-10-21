# SPDX-License-Identifier: MIT

import logging
import threading
import time
from enum import Enum

log = logging.getLogger(__name__)


class IndexingOutcome(Enum):
    """How a wait for a language server's outstanding work ended."""

    NO_WORK = "no-work"
    """The server reported nothing at all within the start grace — it may not report progress."""

    IDLE = "idle"
    """Every task the server reported has finished."""

    TIMEOUT = "timeout"
    """Work was still outstanding when the timeout expired."""


class WorkDoneProgressTracker:
    """
    Tracks the work-done progress a language server reports (`window/workDoneProgress/create` and `$/progress`),
    so that a cross-file query can wait for the server's indexing (and similar work) rather than for a fixed period.

    Some servers keep reporting progress for the rest of the session, so the tracker answers "is anything
    outstanding right now", never "has the server finished for good".
    """

    def __init__(self, server_name: str) -> None:
        """
        :param server_name: the name of the server, used in log messages
        """
        self._server_name = server_name
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}
        self._seen_work = False
        self._idle = threading.Event()
        self._idle.set()

    def expect_work(self) -> None:
        """
        Mark the tracker busy ahead of an action that is expected to make the server do something,
        so that a wait started before the first token arrives blocks rather than returning at once.
        """
        self._idle.clear()

    def on_create(self, params: dict) -> dict:
        """
        Handle `window/workDoneProgress/create`, which precedes the token's first notification.

        Tracking from creation rather than from `begin` means work announced just before a query
        is waited for even if it has not started yet.

        :param params: the request's `WorkDoneProgressCreateParams`
        :return: the empty result the request expects
        """
        with self._lock:
            self._active.setdefault(str(params.get("token", "")), "")
            self._seen_work = True
            self._idle.clear()
        return {}

    def on_progress(self, params: dict) -> None:
        """
        Handle a `$/progress` notification, tracking the token's title for diagnostics.

        :param params: the notification's `ProgressParams`
        """
        token = str(params.get("token", ""))
        value = params.get("value") or {}
        kind = value.get("kind")
        if kind == "begin":
            title = str(value.get("title", ""))
            with self._lock:
                self._active[token] = title
                self._seen_work = True
                self._idle.clear()
            log.info(f"{self._server_name} progress [{token}] started: {title}")
        elif kind == "end":
            with self._lock:
                title = self._active.pop(token, "")
                if not self._active:
                    self._idle.set()
            log.info(f"{self._server_name} progress [{token}] ended: {title}")

    def wait_until_idle(self, timeout: float, start_grace: float, quiet_period: float) -> IndexingOutcome:
        """
        Wait for everything the server is doing to finish.

        Servers may hand off between phases rather than overlapping them, so their set of tokens can empty
        for a moment in between. Readiness is therefore "nothing outstanding for `quiet_period`",
        not "nothing outstanding", which would return in the first such gap.

        :param timeout: how long to wait, in seconds, once work is known to be outstanding
        :param start_grace: how long to wait, in seconds, for work to appear at all
        :param quiet_period: how long, in seconds, the server must report nothing to count as finished
        :return: how the wait ended
        """
        grace_deadline = time.monotonic() + start_grace
        while time.monotonic() < grace_deadline:
            with self._lock:
                if self._active or self._seen_work:
                    break
            time.sleep(0.05)

        with self._lock:
            if not self._active and not self._seen_work:
                self._idle.set()
                return IndexingOutcome.NO_WORK

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._idle.wait(timeout=remaining):
                return IndexingOutcome.TIMEOUT
            if self._stays_idle(quiet_period, deadline):
                return IndexingOutcome.IDLE

    def _stays_idle(self, quiet_period: float, deadline: float) -> bool:
        """
        :param quiet_period: how long, in seconds, nothing new must be reported
        :param deadline: the monotonic time at which to give up regardless
        :return: whether the tracker stayed idle for the whole quiet period
        """
        quiet_end = time.monotonic() + quiet_period
        while time.monotonic() < min(quiet_end, deadline):
            if not self._idle.is_set():
                return False
            time.sleep(0.05)
        return self._idle.is_set()

    def describe(self) -> str:
        """:return: compact diagnostic state of the server's outstanding work."""
        with self._lock:
            titles = sorted(title for title in self._active.values() if title)
            idle = self._idle.is_set()
        return f"idle={idle}, active={', '.join(titles) or '<none>'}"


def parse_positive_float(value: object, name: str, default: float) -> float:
    """
    Validate a positive-number setting, falling back to the default if it is unusable.
    """
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        log.warning(f"Invalid {name} value {value!r}, expected a positive number; using {default}")
        return default
    return float(value)
