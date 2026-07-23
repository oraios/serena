import platform
import subprocess
import time

import psutil
import pytest

from serena.util.shell import execute_shell_command


class TestExecuteShellCommandTimeout:
    def test_no_timeout_runs_to_completion(self):
        result = execute_shell_command("echo hello")
        assert result.stdout.strip() == "hello"
        assert result.return_code == 0

    def test_timeout_raises_and_kills_process(self):
        command = "sleep 60"
        start = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            execute_shell_command(command, timeout=1)
        elapsed = time.monotonic() - start
        # the call must not block for anywhere near the full duration of the hung command
        assert elapsed < 30

        # give the OS a moment to reflect the kill, then confirm no "sleep 60" process survives
        time.sleep(1)
        for proc in psutil.process_iter(["cmdline"]):
            cmdline = " ".join(proc.info.get("cmdline") or [])
            assert command not in cmdline, f"orphaned process still running: {proc.info}"

    @pytest.mark.skipif(platform.system() == "Windows", reason="shell pipeline spawns differ on Windows")
    def test_timeout_kills_child_of_shell_pipeline(self):
        # the actual long-running process is a grandchild of the shell serena spawns (shell=True),
        # so the fix must terminate the whole process tree, not just the top-level shell pid
        command = "sh -c 'sleep 60'"
        with pytest.raises(subprocess.TimeoutExpired):
            execute_shell_command(command, timeout=1)

        time.sleep(1)
        for proc in psutil.process_iter(["cmdline"]):
            cmdline = " ".join(proc.info.get("cmdline") or [])
            assert "sleep 60" not in cmdline, f"orphaned child process still running: {proc.info}"
