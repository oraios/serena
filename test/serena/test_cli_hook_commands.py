"""Tests for CLI hook commands (stamp, check, cleanup)."""

import json
import os
import shutil
import tempfile
import time

import pytest
from click.testing import CliRunner

from serena.cli import HookCommands

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture
def serena_home(monkeypatch):
    """Override SERENA_HOME so tests use a temporary directory."""
    tmpdir = tempfile.mkdtemp()
    monkeypatch.setenv("SERENA_HOME", tmpdir)
    try:
        yield tmpdir
    finally:
        if os.name == "nt":
            time.sleep(0.2)
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def cli_runner():
    """Create a CliRunner for testing Click commands."""
    return CliRunner()


class TestHookStamp:
    """Tests for 'hook stamp' command."""

    def test_stamp_creates_file(self, cli_runner, serena_home):
        """Stamp should create a timestamp file for the session."""
        result = cli_runner.invoke(HookCommands.stamp, ["--session-id", "test-abc"])
        assert result.exit_code == 0, f"Command failed: {result.output}"
        assert result.output == ""
        ts_path = os.path.join(serena_home, "hook_last_serena_call_test-abc")
        assert os.path.exists(ts_path)
        with open(ts_path) as f:
            stamp = float(f.read().strip())
        assert abs(stamp - time.time()) < 5

    def test_stamp_updates_existing(self, cli_runner, serena_home):
        """Stamping twice should update the timestamp."""
        cli_runner.invoke(HookCommands.stamp, ["--session-id", "test-upd"])
        ts_path = os.path.join(serena_home, "hook_last_serena_call_test-upd")
        with open(ts_path) as f:
            first = float(f.read().strip())
        time.sleep(0.05)
        cli_runner.invoke(HookCommands.stamp, ["--session-id", "test-upd"])
        with open(ts_path) as f:
            second = float(f.read().strip())
        assert second >= first

    def test_stamp_no_session_id(self, cli_runner, serena_home):
        """Stamp with no session_id should exit silently."""
        result = cli_runner.invoke(HookCommands.stamp, [])
        assert result.exit_code == 0
        assert result.output == ""
        files = os.listdir(serena_home)
        assert not any(f.startswith("hook_last_serena_call_") for f in files)


class TestHookCheck:
    """Tests for 'hook check' command."""

    def test_check_no_file_silent(self, cli_runner, serena_home):
        """Check with no timestamp file should produce no output."""
        result = cli_runner.invoke(HookCommands.check, ["--session-id", "test-none"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_check_recent_silent(self, cli_runner, serena_home):
        """Check immediately after stamp should produce no output (under threshold)."""
        cli_runner.invoke(HookCommands.stamp, ["--session-id", "test-recent"])
        result = cli_runner.invoke(HookCommands.check, ["--session-id", "test-recent"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_check_stale_emits_reminder(self, cli_runner, serena_home):
        """Check with a stale timestamp should emit a reminder."""
        ts_path = os.path.join(serena_home, "hook_last_serena_call_test-stale")
        with open(ts_path, "w") as f:
            f.write(str(time.time() - 120))
        result = cli_runner.invoke(HookCommands.check, ["--session-id", "test-stale"])
        assert result.exit_code == 0
        assert result.output.strip() != ""
        output = json.loads(result.output.strip())
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "Serena" in output["hookSpecificOutput"]["additionalContext"]

    def test_check_output_is_valid_json(self, cli_runner, serena_home):
        """The reminder output should be valid JSON with the correct structure."""
        ts_path = os.path.join(serena_home, "hook_last_serena_call_test-json")
        with open(ts_path, "w") as f:
            f.write(str(time.time() - 120))
        result = cli_runner.invoke(HookCommands.check, ["--session-id", "test-json"])
        output = json.loads(result.output.strip())
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert isinstance(output["hookSpecificOutput"]["additionalContext"], str)
        assert len(output["hookSpecificOutput"]["additionalContext"]) > 0


class TestHookCleanup:
    """Tests for 'hook cleanup' command."""

    def test_cleanup_removes_file(self, cli_runner, serena_home):
        """Cleanup should remove the timestamp file."""
        cli_runner.invoke(HookCommands.stamp, ["--session-id", "test-clean"])
        ts_path = os.path.join(serena_home, "hook_last_serena_call_test-clean")
        assert os.path.exists(ts_path)
        result = cli_runner.invoke(HookCommands.cleanup, ["--session-id", "test-clean"])
        assert result.exit_code == 0
        assert result.output == ""
        assert not os.path.exists(ts_path)

    def test_cleanup_no_file_silent(self, cli_runner, serena_home):
        """Cleanup with no file should exit silently."""
        result = cli_runner.invoke(HookCommands.cleanup, ["--session-id", "test-noop"])
        assert result.exit_code == 0
        assert result.output == ""
