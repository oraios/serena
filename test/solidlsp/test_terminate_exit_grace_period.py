"""Tests for ``exit_grace_period`` of ``subprocess_util.terminate_process_tree_with_kill_fallback``.

A language server that was sent the LSP ``exit`` notification may need some time to finish (JDTLS saves its
Eclipse workspace then). Signaling it at once is a hard kill on Windows, so it never gets to finish. These tests use
plain Python helper processes and run in catch-all, on every platform.
"""

from __future__ import annotations

import subprocess
import sys
import time

from solidlsp.util.subprocess_util import ManagedSubprocess, terminate_process_tree_with_kill_fallback

_EXITS_BY_ITSELF_AFTER_ONE_SECOND = "import time; time.sleep(1); raise SystemExit(0)"
_NEVER_EXITS = "import time; time.sleep(60)"


def _spawn(code: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", code])


def test_process_that_exits_within_the_grace_period_is_not_signaled() -> None:
    process = _spawn(_EXITS_BY_ITSELF_AFTER_ONE_SECOND)

    terminate_process_tree_with_kill_fallback(process, terminate_timeout=5, exit_grace_period=10)

    # a signal would have given a different exit code than the one the process chose itself
    assert process.returncode == 0


def test_process_that_does_not_exit_is_signaled_after_the_grace_period() -> None:
    process = _spawn(_NEVER_EXITS)
    started = time.monotonic()

    terminate_process_tree_with_kill_fallback(process, terminate_timeout=5, exit_grace_period=1)

    elapsed = time.monotonic() - started
    assert process.returncode is not None and process.returncode != 0
    assert elapsed >= 1


def test_without_a_grace_period_the_process_is_signaled_at_once() -> None:
    process = _spawn(_EXITS_BY_ITSELF_AFTER_ONE_SECOND)

    terminate_process_tree_with_kill_fallback(process, terminate_timeout=5)

    assert process.returncode != 0


def test_managed_subprocess_passes_the_grace_period_on() -> None:
    managed = ManagedSubprocess(_spawn(_EXITS_BY_ITSELF_AFTER_ONE_SECOND), name="Test process", start_new_session=False)

    managed.terminate(timeout=5, exit_grace_period=10)

    assert managed.returncode == 0
