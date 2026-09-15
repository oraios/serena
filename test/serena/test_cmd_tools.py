"""Tests for serena.tools.cmd_tools."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from serena.tools.cmd_tools import TOOL_TIMEOUT_MARGIN, ExecuteShellCommandTool


class _StubConfig:
    def __init__(self, tool_timeout: float | None) -> None:
        self.tool_timeout = tool_timeout
        self.default_max_tool_answer_chars = 100_000


class _StubAgent:
    def __init__(self, tool_timeout: float | None) -> None:
        self.serena_config = _StubConfig(tool_timeout)


def _tool(tool_timeout: float | None) -> ExecuteShellCommandTool:
    tool = ExecuteShellCommandTool.__new__(ExecuteShellCommandTool)
    tool.agent = _StubAgent(tool_timeout)
    return tool


class TestCommandTimeout:
    @pytest.mark.parametrize("tool_timeout", [240.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 2.0, 0.5])
    def test_command_deadline_stays_below_the_tool_deadline(self, tool_timeout: float):
        """The command must be given up on before the tool call itself times out.

        Otherwise the tool reports a timeout while the command is still running, which is the
        leak this derivation exists to prevent.
        """
        command_timeout = _tool(tool_timeout)._get_command_timeout()
        assert command_timeout is not None
        assert command_timeout < tool_timeout

    def test_margin_is_applied_when_the_tool_timeout_is_large_enough(self):
        assert _tool(240.0)._get_command_timeout() == 240.0 - TOOL_TIMEOUT_MARGIN

    @pytest.mark.parametrize("tool_timeout", [None, -1.0])
    def test_no_tool_timeout_means_no_command_timeout(self, tool_timeout: float | None):
        assert _tool(tool_timeout)._get_command_timeout() is None


class TestApplyBoundsTheCommand:
    def test_apply_terminates_a_command_that_outlives_the_tool_deadline(self, tmp_path: Path):
        """The tool must pass its derived deadline down to the command.

        Without the pass-through the command is unbounded, so the tool call ends -- by its own
        timeout, one level up -- while the process carries on. The marker is written only after
        that point, so its absence is what proves the command was actually bounded.
        """
        marker = tmp_path / "marker.txt"
        command = f"{sys.executable} -c \"import time,pathlib; time.sleep(5.0); pathlib.Path(r'{marker}').write_text('ran')\""

        tool = _tool(2.0)  # -> command deadline of 1.0s
        tool.get_project_root = lambda: str(tmp_path)

        with pytest.raises(subprocess.TimeoutExpired):
            tool.apply(command=command)

        time.sleep(6.0)
        assert not marker.exists(), "Command kept running after the tool call ended"
