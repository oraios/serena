import json
import pickle
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from serena.hooks import (
    HookClient,
    PreToolUseRemindAboutSerenaHook,
    SessionEndCleanupHook,
    SessionStartActivateProjectHook,
    hook_commands,
)

ToolUseCounter = PreToolUseRemindAboutSerenaHook.ToolUseCounter


def _make_stdin(data: dict) -> StringIO:
    return StringIO(json.dumps(data))


def _base_input(tool_name: str = "grep_search", session_id: str = "test-session-123") -> dict:
    return {
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": {"query": "foo"},
    }


class TestHookClientDetection:
    """Tests for the --client option propagation."""

    def test_claude_code_client(self, tmp_path: Path):
        stdin_data = _base_input()
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            hook = PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE)
        assert hook._client == HookClient.CLAUDE_CODE

    def test_vscode_client(self, tmp_path: Path):
        stdin_data = _base_input()
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            hook = PreToolUseRemindAboutSerenaHook(HookClient.VSCODE)
        assert hook._client == HookClient.VSCODE


class TestPreToolUseRemindAboutSerenaHook:
    """Tests for the PreToolUse hook that nudges the agent toward symbolic tools."""

    def test_missing_tool_name_raises(self, tmp_path: Path):
        stdin_data = {"session_id": "s1"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            with pytest.raises(ValueError, match="Tool name is required"):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE)

    def test_missing_session_id_raises(self, tmp_path: Path):
        stdin_data = {"tool_name": "grep"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            with pytest.raises(ValueError, match="Session ID is required"):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE)

    def test_grep_tool_detection(self, tmp_path: Path):
        for name, expected in [("grep_search", True), ("mcp_grep", True), ("read_file", False), ("serena_find", False)]:
            with patch("sys.stdin", _make_stdin(_base_input(tool_name=name))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE)
            assert hook.is_grep_tool() == expected, f"is_grep_tool() wrong for {name}"

    def test_read_file_tool_detection(self, tmp_path: Path):
        for name, expected in [("read_file", True), ("readFile", True), ("grep_search", False), ("file_writer", False)]:
            with patch("sys.stdin", _make_stdin(_base_input(tool_name=name))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE)
            assert hook.is_read_file_tool() == expected, f"is_read_file_tool() wrong for {name}"

    def test_serena_tool_detection(self, tmp_path: Path):
        for name, expected in [("mcp_serena_find_symbol", True), ("serena_overview", True), ("grep_search", False)]:
            with patch("sys.stdin", _make_stdin(_base_input(tool_name=name))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE)
            assert hook.is_serena_tool() == expected, f"is_serena_tool() wrong for {name}"

    def test_no_output_below_threshold(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Below the threshold, the hook should produce no output (tool is allowed)."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD - 1):
            with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_deny_output_after_threshold_greps_claude_code(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the grep threshold, the hook should output a deny."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "grep" in hook_output["additionalContext"].lower()

    def test_deny_output_after_threshold_greps_vscode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the grep threshold, the hook should output a deny for VS Code."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSerenaHook(HookClient.VSCODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "grep" in hook_output["additionalContext"].lower()

    def test_deny_output_after_threshold_reads(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the read file threshold, the hook should output a deny."""
        for _ in range(ToolUseCounter._READ_FILE_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("read_file"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "read file" in hook_output["additionalContext"].lower()

    def test_serena_tool_resets_counters(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Using a Serena tool should reset counters, so the threshold is not reached."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD - 1):
            with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()

        with patch("sys.stdin", _make_stdin(_base_input("mcp_serena_find_symbol"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()

        with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()

        assert capsys.readouterr().out == ""

    def test_counter_resets_after_deny(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After a deny is emitted, the counter is reset so the next burst starts fresh."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()
        capsys.readouterr()

        with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSerenaHook(HookClient.CLAUDE_CODE).execute()

        assert capsys.readouterr().out == ""


class TestToolUseCounter:
    """Tests for the time-windowed tool-use counter logic."""

    def test_update_increments_grep_within_period(self):
        counter = ToolUseCounter()
        now = datetime.now()
        counter.last_grep_use_timestamp = now - timedelta(seconds=1)
        counter.n_recent_grep_uses = 1

        hook = self._make_hook_stub("grep_search", now)
        counter.update(hook)

        assert counter.n_recent_grep_uses == 2
        assert counter.last_grep_use_timestamp == now

    def test_update_resets_grep_outside_period(self):
        counter = ToolUseCounter()
        now = datetime.now()
        counter.last_grep_use_timestamp = now - timedelta(seconds=ToolUseCounter._PERIOD_TO_RESET_COUNTERS_SECONDS + 1)
        counter.n_recent_grep_uses = 2

        hook = self._make_hook_stub("grep_search", now)
        counter.update(hook)

        assert counter.n_recent_grep_uses == 1
        assert counter.last_grep_use_timestamp == now

    def test_update_increments_read_file_within_period(self):
        counter = ToolUseCounter()
        now = datetime.now()
        counter.last_read_file_use_timestamp = now - timedelta(seconds=1)
        counter.n_recent_read_file_uses = 1

        hook = self._make_hook_stub("read_file", now)
        counter.update(hook)

        assert counter.n_recent_read_file_uses == 2

    def test_update_resets_read_file_outside_period(self):
        counter = ToolUseCounter()
        now = datetime.now()
        counter.last_read_file_use_timestamp = now - timedelta(seconds=ToolUseCounter._PERIOD_TO_RESET_COUNTERS_SECONDS + 1)
        counter.n_recent_read_file_uses = 2

        hook = self._make_hook_stub("read_file", now)
        counter.update(hook)

        assert counter.n_recent_read_file_uses == 1

    def test_serena_tool_resets_all_counters(self):
        counter = ToolUseCounter(
            n_recent_grep_uses=2,
            n_recent_read_file_uses=2,
            last_grep_use_timestamp=datetime.now(),
            last_read_file_use_timestamp=datetime.now(),
        )
        hook = self._make_hook_stub("mcp_serena_overview", datetime.now())
        counter.update(hook)

        assert counter.n_recent_grep_uses == 0
        assert counter.n_recent_read_file_uses == 0
        assert counter.last_grep_use_timestamp is None
        assert counter.last_read_file_use_timestamp is None

    def test_non_matching_tool_leaves_counters_unchanged(self):
        counter = ToolUseCounter(n_recent_grep_uses=1, n_recent_read_file_uses=1)
        hook = self._make_hook_stub("write_file", datetime.now())
        counter.update(hook)

        assert counter.n_recent_grep_uses == 1
        assert counter.n_recent_read_file_uses == 1

    def test_persistence_round_trip(self, tmp_path: Path):
        counter = ToolUseCounter(n_recent_grep_uses=2, n_recent_read_file_uses=1)

        hook_stub = type("HookStub", (), {"session_persistence_dir": str(tmp_path)})()
        counter.save(hook_stub)  # type: ignore[arg-type]
        loaded = ToolUseCounter.load(hook_stub)  # type: ignore[arg-type]

        assert loaded.n_recent_grep_uses == 2
        assert loaded.n_recent_read_file_uses == 1

    def test_load_returns_fresh_counter_on_missing_file(self, tmp_path: Path):
        hook_stub = type("HookStub", (), {"session_persistence_dir": str(tmp_path / "nonexistent")})()
        loaded = ToolUseCounter.load(hook_stub)  # type: ignore[arg-type]
        assert loaded == ToolUseCounter()

    def test_load_returns_fresh_counter_on_corrupt_file(self, tmp_path: Path):
        hook_stub = type("HookStub", (), {"session_persistence_dir": str(tmp_path)})()
        path = tmp_path / ToolUseCounter._FILE_NAME
        path.write_bytes(b"not a pickle")
        loaded = ToolUseCounter.load(hook_stub)  # type: ignore[arg-type]
        assert loaded == ToolUseCounter()

    @staticmethod
    def _make_hook_stub(tool_name: str, timestamp: datetime) -> PreToolUseRemindAboutSerenaHook:
        """Create a minimal stub that satisfies ToolUseCounter.update without reading stdin."""
        stub = object.__new__(PreToolUseRemindAboutSerenaHook)
        stub._tool_name = tool_name.lower()
        stub.triggered_at_timestamp = timestamp
        return stub


class TestSessionStartActivateProjectHook:
    def test_outputs_activation_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        stdin_data = {"session_id": "s1"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            SessionStartActivateProjectHook(HookClient.VSCODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        context = result["hookSpecificOutput"]["additionalContext"]
        assert "Activate" in context
        assert "Serena Instructions Manual" in context


class TestSessionEndCleanupHook:
    def test_removes_session_dir(self, tmp_path: Path):
        session_dir = tmp_path / "hook_data" / "cleanup-session"
        session_dir.mkdir(parents=True)
        # place a file inside to verify recursive removal
        (session_dir / "tool_use_counter.pkl").write_bytes(pickle.dumps(ToolUseCounter()))

        stdin_data = {"session_id": "cleanup-session"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            SessionEndCleanupHook(HookClient.CLAUDE_CODE).execute()

        assert not session_dir.exists()

    def test_cleanup_is_idempotent(self, tmp_path: Path):
        """Cleaning up a non-existent session directory should not raise."""
        stdin_data = {"session_id": "nonexistent-session"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            SessionEndCleanupHook(HookClient.CLAUDE_CODE).execute()


class TestHookCli:
    """Tests for the Click CLI entry point (serena-hooks)."""

    def test_activate_command(self, tmp_path: Path):
        stdin_json = json.dumps({"session_id": "cli-test"})
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["activate", "--client", "vscode"], input=stdin_json)
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "Activate" in output["hookSpecificOutput"]["additionalContext"]

    def test_cleanup_command(self, tmp_path: Path):
        session_dir = tmp_path / "hook_data" / "cli-cleanup"
        session_dir.mkdir(parents=True)
        (session_dir / "somefile").write_text("data")

        stdin_json = json.dumps({"session_id": "cli-cleanup"})
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["cleanup", "--client", "claude-code"], input=stdin_json)
        assert result.exit_code == 0
        assert not session_dir.exists()

    def test_remind_command(self, tmp_path: Path):
        """Invoke the remind command enough times to trigger a deny."""
        runner = CliRunner()
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            stdin_json = json.dumps({"session_id": "cli-remind", "tool_name": "grep_search", "tool_input": {}})
            with patch("serena.hooks.serena_home_dir", str(tmp_path)):
                result = runner.invoke(hook_commands, ["remind", "--client", "claude-code"], input=stdin_json)
            assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_client_default_is_claude_code(self, tmp_path: Path):
        """When --client is omitted, it defaults to claude-code."""
        stdin_json = json.dumps({"session_id": "cli-default"})
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["activate"], input=stdin_json)
        assert result.exit_code == 0

    def test_invalid_client_rejected(self, tmp_path: Path):
        stdin_json = json.dumps({"session_id": "s1"})
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["activate", "--client", "invalid"], input=stdin_json)
        assert result.exit_code != 0

    def test_invalid_stdin_exits_nonzero(self, tmp_path: Path):
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["activate", "--client", "claude-code"], input="not json")
        assert result.exit_code != 0
