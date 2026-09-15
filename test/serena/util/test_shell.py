"""Tests for serena.util.shell.execute_shell_command."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from serena.util.shell import execute_shell_command


def _sleep_then_write(marker: Path, seconds: float) -> str:
    """A shell command that writes ``marker`` only after ``seconds`` have elapsed."""
    return f"{sys.executable} -c \"import time,pathlib; time.sleep({seconds}); pathlib.Path(r'{marker}').write_text('ran')\""


class TestExecuteShellCommandTimeout:
    def test_command_within_timeout_returns_normally(self):
        """A command that finishes in time is unaffected by the timeout."""
        result = execute_shell_command(f"{sys.executable} -c \"print('hello')\"", timeout=30.0)
        assert result.return_code == 0
        assert "hello" in result.stdout

    def test_timeout_raises_and_kills_the_process(self, tmp_path: Path):
        """A command exceeding the timeout is terminated, not merely abandoned.

        The side effect is scheduled for after the timeout, so its absence is what proves the
        process was actually killed rather than left running with its result discarded.
        """
        marker = tmp_path / "marker.txt"
        with pytest.raises(subprocess.TimeoutExpired):
            execute_shell_command(_sleep_then_write(marker, 5.0), timeout=0.5)
        time.sleep(6.0)
        assert not marker.exists(), "Command kept running after the timeout expired"

    def test_without_timeout_the_command_runs_to_completion(self, tmp_path: Path):
        """Negative case: omitting the timeout preserves the previous blocking behaviour."""
        marker = tmp_path / "marker.txt"
        result = execute_shell_command(_sleep_then_write(marker, 0.5))
        assert result.return_code == 0
        assert marker.exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="relies on POSIX shell command grouping")
    def test_timeout_kills_a_child_the_shell_did_not_exec(self, tmp_path: Path):
        """The whole process tree must die, not just the shell that leads it.

        A compound command makes the shell fork the program instead of exec'ing it, so the
        program is a grandchild of ours. Signalling only the leader would leave it running.
        """
        marker = tmp_path / "marker.txt"
        with pytest.raises(subprocess.TimeoutExpired):
            execute_shell_command(f"{_sleep_then_write(marker, 5.0)} ; true", timeout=0.5)
        time.sleep(6.0)
        assert not marker.exists(), "Grandchild process survived the timeout"
