# SPDX-License-Identifier: MIT

"""Behavioral tests for subprocess execution."""

import subprocess
import sys
import textwrap
from pathlib import Path
from time import monotonic

import psutil
import pytest

from solidlsp.util.subprocess_util import convert_shell_cmd, subprocess_run


def test_timeout_stops_descendants_and_returns_promptly(tmp_path: Path) -> None:
    """A timed-out shell command must stop its descendants even when they hold output pipes open."""
    # start a command whose child inherits the captured output pipes
    pid_file = tmp_path / "pids.txt"
    script = tmp_path / "command.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, pathlib, subprocess, sys
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
            pathlib.Path({str(pid_file)!r}).write_text(f"{{os.getpid()}} {{child.pid}}")
            print("ready", flush=True)
            child.wait()
            """
        )
    )
    command = convert_shell_cmd([sys.executable, str(script)])

    # verify that timeout cleanup returns before the child would finish naturally
    started = monotonic()
    try:
        with pytest.raises(subprocess.TimeoutExpired) as error:
            subprocess_run(command, shell=True, timeout=2.0)
        assert monotonic() - started < 12.0
        assert pid_file.exists(), "The command must start before the timeout"
        for pid in map(int, pid_file.read_text().split()):
            try:
                process = psutil.Process(pid)
            except psutil.NoSuchProcess:
                continue
            assert process.status() == psutil.STATUS_ZOMBIE, f"Process {pid} survived the timeout"
        assert error.value.stdout is not None
        assert "ready" in str(error.value.stdout)
    finally:
        # clean up any survivors if the regression recurs
        if pid_file.exists():
            for pid in reversed(list(map(int, pid_file.read_text().split()))):
                try:
                    process = psutil.Process(pid)
                    if process.status() != psutil.STATUS_ZOMBIE:
                        process.kill()
                        process.wait(timeout=5.0)
                except psutil.NoSuchProcess:
                    pass
