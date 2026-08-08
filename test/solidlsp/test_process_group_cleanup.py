"""Regression tests for issue #1818: LSP process-group cleanup must not require enumerating
the system process table (``psutil.Process.children(recursive=True)``), which can be denied
even for processes we started and own (``Operation not permitted`` from
``sysctl(KERN_PROC_ALL)`` in a sandboxed macOS environment).

``StdioLanguageServer`` already starts every LSP process in its own session
(``start_independent_lsp_process`` defaults to True, see ``ls_config.py``), which makes the
process its own POSIX process group leader, with a PGID equal to its PID at launch;
``subprocess_util.terminate_process_tree_with_kill_fallback`` accepts that PGID as
``process_group_id`` and, when given, signals the whole group directly via ``os.killpg``
instead of walking the tree with ``psutil``. No language markers: these exercise
``subprocess_util`` directly with plain Python helper processes and run in catch-all.
"""

from __future__ import annotations

import os
import platform
import signal
import subprocess
import sys
import textwrap
import time

import psutil
import pytest

from solidlsp.util.subprocess_util import _signal_process_group, terminate_process_tree_with_kill_fallback

pytestmark = pytest.mark.skipif(platform.system() == "Windows", reason="process groups / os.killpg are POSIX-specific")


def _group_is_gone(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return False
    except ProcessLookupError:
        return True


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class _DenyingProcess:
    """Stand-in for ``psutil.Process`` that always raises ``AccessDenied``, used to simulate
    a sandboxed environment denying process-table enumeration without needing one. A real class
    (not a plain function) so it substitutes cleanly for ``psutil.Process`` in the
    ``subprocess.Popen | psutil.Process`` type union that subprocess_util.py evaluates eagerly.
    """

    def __new__(cls, pid: int) -> "_DenyingProcess":
        raise psutil.AccessDenied(pid)


def _spawn_ready(src: str) -> subprocess.Popen:
    """Starts ``src`` in its own session and waits for it to print READY, mirroring
    test_pdeathsig.py's driver pattern (deterministic sync instead of a blind sleep).
    """
    proc = subprocess.Popen([sys.executable, "-c", src], start_new_session=True, stdout=subprocess.PIPE, text=True)
    ready_line = proc.stdout.readline()
    assert ready_line.strip() == "READY", f"helper process failed to start: {ready_line!r}"
    return proc


class TestSignalProcessGroup:
    def test_nonexistent_group_is_treated_as_already_clean(self) -> None:
        bogus_pgid = 2**30  # not a real PGID; must be handled like an already-gone group
        _signal_process_group(bogus_pgid, terminate=True)  # must not raise

    def test_permission_error_is_caught_and_logged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_eperm(pgid: int, sig: int) -> None:
            raise PermissionError("simulated sandbox denial")

        monkeypatch.setattr(os, "killpg", raise_eperm)
        _signal_process_group(12345, terminate=True)  # must not raise


class TestTerminateProcessTreeWithKillFallback:
    def test_terminates_child_and_grandchild_via_group_id(self) -> None:
        """A focused POSIX cleanup test: start a child and grandchild in one new session,
        invoke the cleanup utility by PGID only, and verify both are gone, without ever
        calling psutil.
        """
        src = textwrap.dedent(
            """
            import subprocess, sys, time
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            print("READY", flush=True)
            time.sleep(300)
            """
        )
        proc = _spawn_ready(src)
        pgid = proc.pid
        try:
            assert not _group_is_gone(pgid), "process group should be alive before cleanup"
            terminate_process_tree_with_kill_fallback(proc, terminate_timeout=5.0, process_group_id=pgid)
            assert _wait_until(lambda: _group_is_gone(pgid)), f"process group {pgid} survived cleanup"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2.0)

    def test_falls_back_to_kill_when_group_ignores_sigterm(self) -> None:
        src = textwrap.dedent(
            """
            import signal, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            print("READY", flush=True)
            time.sleep(300)
            """
        )
        proc = _spawn_ready(src)
        pgid = proc.pid
        try:
            terminate_process_tree_with_kill_fallback(proc, terminate_timeout=1.0, process_group_id=pgid)
            assert _wait_until(lambda: _group_is_gone(pgid)), f"process group {pgid} survived SIGKILL fallback"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2.0)

    def test_already_exited_group_does_not_raise(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        pgid = proc.pid
        proc.wait(timeout=5.0)
        assert _wait_until(lambda: _group_is_gone(pgid)), "group should be released once the leader is reaped"
        terminate_process_tree_with_kill_fallback(proc, terminate_timeout=1.0, process_group_id=pgid)

    def test_process_group_id_none_never_calls_killpg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """start_independent_lsp_process=False means the process shares our own process
        group, so cleanup must never call killpg: doing so could signal Serena itself.
        """

        def fail_if_called(pgid: int, sig: int) -> None:
            raise AssertionError("os.killpg must not be called when process_group_id is None")

        monkeypatch.setattr(os, "killpg", fail_if_called)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        try:
            terminate_process_tree_with_kill_fallback(proc, terminate_timeout=5.0, process_group_id=None)
            proc.wait(timeout=5.0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2.0)


class TestPsutilDenialConsequences:
    """Demonstrates the actual production consequence when process-table enumeration is denied,
    without depending on macOS: ``psutil.AccessDenied`` is the same exception class regardless of
    which syscall the platform used to deny it. Without a known ``process_group_id``,
    ``_signal_process_tree`` falls back to signaling only the ``Popen`` object it was given (see
    its ``except (psutil.NoSuchProcess, psutil.AccessDenied, Exception): pass`` branch), so a
    child the leader spawned itself leaks. Passing the group id (this fix) avoids psutil
    entirely and reaps it regardless.
    """

    @staticmethod
    def _spawn_leader_with_child() -> tuple[subprocess.Popen, int]:
        src = textwrap.dedent(
            """
            import subprocess, sys, time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
            print(child.pid, flush=True)
            print("READY", flush=True)
            time.sleep(300)
            """
        )
        proc = subprocess.Popen([sys.executable, "-c", src], start_new_session=True, stdout=subprocess.PIPE, text=True)
        child_pid = int(proc.stdout.readline().strip())
        ready_line = proc.stdout.readline()
        assert ready_line.strip() == "READY", f"helper process failed to start: {ready_line!r}"
        return proc, child_pid

    def test_psutil_denial_without_group_id_leaks_the_leaders_child(self, monkeypatch: pytest.MonkeyPatch) -> None:
        proc, child_pid = self._spawn_leader_with_child()

        monkeypatch.setattr("solidlsp.util.subprocess_util.psutil.Process", _DenyingProcess)
        try:
            # The call shape every site used before this fix: no process_group_id.
            terminate_process_tree_with_kill_fallback(proc, terminate_timeout=2.0, process_name="leader")
            assert _wait_until(lambda: proc.poll() is not None), "leader itself should still die (direct signal, not enumerated)"
            time.sleep(0.3)
            assert _process_alive(child_pid), (
                "expected the leader's own child to leak when psutil is denied and no process_group_id is given "
                "(this is the #1818 defect: process-table denial silently drops descendants)"
            )
        finally:
            for pid in (child_pid, proc.pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc.poll() is None:
                proc.wait(timeout=2.0)

    def test_process_group_id_survives_psutil_denial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        proc, child_pid = self._spawn_leader_with_child()
        pgid = proc.pid

        monkeypatch.setattr("solidlsp.util.subprocess_util.psutil.Process", _DenyingProcess)
        try:
            terminate_process_tree_with_kill_fallback(proc, terminate_timeout=5.0, process_group_id=pgid)
            assert _wait_until(lambda: _group_is_gone(pgid)), f"process group {pgid} survived cleanup despite psutil denial"
            assert not _process_alive(child_pid), "leader's child leaked even though the group id path avoids psutil entirely"
        finally:
            for pid in (child_pid, proc.pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc.poll() is None:
                proc.wait(timeout=2.0)
