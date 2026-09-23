"""Behavior tests for ``terminate_processes_with_kill_fallback``: it must actually make the
given processes gone, not merely signal them. Uses real short-lived Python sleeper processes
and runs on all platforms (unlike the POSIX-only process-group cleanup tests).
"""

from __future__ import annotations

import subprocess
import sys
import time

import psutil

from solidlsp.util.subprocess_util import terminate_processes_with_kill_fallback


def _spawn_sleeper() -> psutil.Process:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    return psutil.Process(proc.pid)


def _wait_until_gone(proc: psutil.Process, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        time.sleep(0.05)
    return False


def test_terminate_processes_graceful():
    procs = [_spawn_sleeper(), _spawn_sleeper()]

    terminate_processes_with_kill_fallback(procs, terminate_timeout=10.0, process_name="Test")

    for proc in procs:
        assert _wait_until_gone(proc), f"process {proc.pid} still running after termination"


def test_terminate_processes_kill_fallback():
    # terminate_timeout=0 forces the graceful wait to time out immediately, exercising the kill path.
    procs = [_spawn_sleeper(), _spawn_sleeper()]

    terminate_processes_with_kill_fallback(procs, terminate_timeout=0.0, process_name="Test", kill_timeout=10.0)

    for proc in procs:
        assert _wait_until_gone(proc), f"process {proc.pid} still running after kill fallback"


def test_terminate_processes_empty_is_noop():
    terminate_processes_with_kill_fallback([], terminate_timeout=1.0)
