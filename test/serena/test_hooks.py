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
    PreToolUseAutoApproveSerenaHook,
    PreToolUseRemindAboutSymbolicToolsHook,
    SessionEndCleanupHook,
    hook_commands,
)

ToolUseCounter = PreToolUseRemindAboutSymbolicToolsHook.ToolUseCounter


def _make_stdin(data: dict) -> StringIO:
    return StringIO(json.dumps(data))


def _base_input(
    tool_name: str = "grep_search",
    session_id: str = "test-session-123",
    tool_input: dict | None = None,
) -> dict:
    return {
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": tool_input if tool_input is not None else {"query": "foo"},
    }


def _read_input(tool_name: str = "read", session_id: str = "test-session-123", file_path: str = "src/foo.py") -> dict:
    """Build a hook payload for a read-style tool call against a file."""
    return {
        "session_id": session_id,
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
    }


class TestHookClientDetection:
    """Tests for the --client option propagation."""

    def test_claude_code_client(self, tmp_path: Path):
        stdin_data = _base_input()
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)
        assert hook._client == HookClient.CLAUDE_CODE

    def test_vscode_client(self, tmp_path: Path):
        stdin_data = _base_input()
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.VSCODE)
        assert hook._client == HookClient.VSCODE


class TestPreToolUseRemindAboutSerenaHook:
    """Tests for the PreToolUse hook that nudges the agent toward symbolic tools."""

    def test_missing_tool_name_raises(self, tmp_path: Path):
        stdin_data = {"session_id": "s1"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            with pytest.raises(ValueError, match="Tool name is required"):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)

    def test_missing_session_id_raises(self, tmp_path: Path):
        stdin_data = {"tool_name": "grep"}
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            with pytest.raises(ValueError, match="Session ID is required"):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)

    def test_grep_tool_detection_claude_code(self, tmp_path: Path):
        """Claude Code uses the exact tool name ``Grep`` (lowercased to ``grep``)."""
        for name, expected in [("grep", True), ("grep_search", False), ("mcp_grep", False), ("read", False)]:
            with patch("sys.stdin", _make_stdin(_base_input(tool_name=name))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)
            assert hook.is_grep_call() == expected, f"is_grep_tool() wrong for {name} (claude-code)"

    def test_grep_tool_detection_non_claude_code(self, tmp_path: Path):
        """Non-Claude-Code clients fall back to substring matching to cover verbose tool names."""
        for name, expected in [("grep_search", True), ("mcp_grep", True), ("read_file", False), ("serena_find", False)]:
            with patch("sys.stdin", _make_stdin(_base_input(tool_name=name))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.VSCODE)
            assert hook.is_grep_call() == expected, f"is_grep_tool() wrong for {name} (vscode)"

    def test_grep_tool_detection_codex_shell_commands(self, tmp_path: Path):
        """Codex shell-command tools are classified by the command embedded in their payload."""
        cases = [
            ("exec_command", {"cmd": "rg -n foo README.md"}, True),
            ("functions.shell_command", {"command": "rg -n foo README.md"}, True),
            ("functions.shell_command", {"command": "Get-Content README.md"}, False),
        ]
        for tool_name, tool_input, expected in cases:
            with (
                patch("sys.stdin", _make_stdin(_base_input(tool_name=tool_name, tool_input=tool_input))),
                patch("serena.hooks.serena_home_dir", str(tmp_path)),
            ):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CODEX)
            assert hook.is_grep_call() == expected, f"is_grep_tool() wrong for {tool_name} / {tool_input}"

    def test_read_file_tool_detection_claude_code(self, tmp_path: Path):
        """Claude Code uses the exact tool name ``Read`` (lowercased to ``read``)."""
        for name, expected in [("read", True), ("mcp__serena__read_file", True), ("grep", False), ("serena_search_for_pattern", False)]:
            with (
                patch("sys.stdin", _make_stdin(_read_input(tool_name=name))),
                patch("serena.hooks.serena_home_dir", str(tmp_path)),
            ):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)
            assert hook.is_read_file_call() == expected, f"is_read_file_tool() wrong for {name} (claude-code)"

    def test_read_file_tool_detection_non_claude_code(self, tmp_path: Path):
        """Non-Claude-Code clients accept any read-style verb (``read``/``view``/``open``/``show``)
        combined with ``file``.
        """
        cases = [
            # canonical names
            ("read_file", True),
            ("readFile", True),
            # alternative read verbs used by other agents/editors
            ("view_file", True),
            ("open_file", True),
            ("show_file", True),
            # negatives: no "file", or "file" without a read verb, or modifying verbs
            ("grep_search", False),
            ("file_writer", False),
            ("write_file", False),
            ("edit_file", False),
        ]
        for name, expected in cases:
            with (
                patch("sys.stdin", _make_stdin(_read_input(tool_name=name))),
                patch("serena.hooks.serena_home_dir", str(tmp_path)),
            ):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.VSCODE)
            assert hook.is_read_file_call() == expected, f"is_read_file_tool() wrong for {name} (vscode)"

    def test_read_non_code_file_counts_as_file_read(self, tmp_path: Path):
        """A ``Read`` call against a non-source file still counts as a file read."""
        payload = _read_input(tool_name="read", file_path="notes/todo.txt")
        with patch("sys.stdin", _make_stdin(payload)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)
        assert hook.is_read_call() is True
        assert hook.is_read_file_call() is True
        assert hook.is_read_code_file_call() is False

    def test_read_code_file_detection(self, tmp_path: Path):
        """Only source-like read targets count for the code-read reminder."""
        cases = [
            (HookClient.CLAUDE_CODE, _read_input(tool_name="read", file_path="README.md"), False),
            (HookClient.CLAUDE_CODE, _read_input(tool_name="read", file_path="src/foo.py"), True),
            (HookClient.CODEX, _base_input("functions.shell_command", tool_input={"command": "Get-Content README.md"}), False),
            (HookClient.CODEX, _base_input("functions.shell_command", tool_input={"command": "Get-Content src/foo.py"}), True),
        ]
        for client, payload, expected in cases:
            with patch("sys.stdin", _make_stdin(payload)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSymbolicToolsHook(client)
            assert hook.is_read_code_file_call() == expected, f"is_read_code_file_call() wrong for {client} / {payload}"

    def test_read_file_tool_detection_codex_shell_commands(self, tmp_path: Path):
        """Codex shell-command tools count PowerShell file reads, including non-code files."""
        cases = [
            ("exec_command", {"cmd": "cat README.md"}, True),
            ("functions.shell_command", {"command": "Get-Content README.md"}, True),
            ("functions.shell_command", {"command": "rg -n foo README.md"}, False),
        ]
        for tool_name, tool_input, expected in cases:
            with (
                patch("sys.stdin", _make_stdin(_base_input(tool_name=tool_name, tool_input=tool_input))),
                patch("serena.hooks.serena_home_dir", str(tmp_path)),
            ):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CODEX)
            assert hook.is_read_file_call() == expected, f"is_read_file_tool() wrong for {tool_name} / {tool_input}"

    def test_serena_tool_detection(self, tmp_path: Path):
        for name, expected in [("mcp_serena_find_symbol", True), ("serena_overview", True), ("grep_search", False)]:
            with patch("sys.stdin", _make_stdin(_base_input(tool_name=name))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                hook = PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE)
            assert hook.is_serena_symbolic_tool() == expected, f"is_serena_tool() wrong for {name}"

    def test_no_output_below_threshold(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Below the threshold, the hook should produce no output (tool is allowed)."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD - 1):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_deny_output_after_threshold_greps_claude_code(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the grep threshold, the hook should output a deny."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "grep" in hook_output["additionalContext"].lower()

    def test_deny_output_after_threshold_greps_vscode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the grep threshold, the hook should output a deny for VS Code."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep_search"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.VSCODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "grep" in hook_output["additionalContext"].lower()

    def test_deny_output_after_threshold_greps_codex_shell_command(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the grep threshold, Codex ``functions.shell_command`` emits a deny."""
        payload = _base_input("functions.shell_command", tool_input={"command": "rg -n foo README.md"})
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(payload)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CODEX).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "additionalContext" not in hook_output
        assert "grep" in hook_output["permissionDecisionReason"].lower()

    def test_deny_output_after_threshold_reads(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After reaching the read file threshold, the hook should output a deny.

        ``_read_input`` supplies the direct ``file_path`` field emitted by file-read tools.
        """
        for _ in range(ToolUseCounter._READ_FILE_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_read_input("read"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "read" in hook_output["additionalContext"].lower()
        assert "files" in hook_output["additionalContext"].lower()

    def test_no_deny_after_threshold_get_content_markdown_codex(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """PowerShell ``Get-Content`` calls on markdown files do not count for the code-read reminder."""
        payload = _base_input("functions.shell_command", tool_input={"command": "Get-Content README.md"})
        for _ in range(ToolUseCounter._READ_FILE_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(payload)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CODEX).execute()

        assert capsys.readouterr().out == ""

    def test_deny_output_after_threshold_get_content_code_file_codex(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """PowerShell ``Get-Content`` calls on source files count for the code-read reminder."""
        payload = _base_input("functions.shell_command", tool_input={"command": "Get-Content src/foo.py"})
        for _ in range(ToolUseCounter._READ_FILE_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(payload)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CODEX).execute()

        result = json.loads(capsys.readouterr().out.strip())
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "additionalContext" not in hook_output
        assert "read" in hook_output["permissionDecisionReason"].lower()

    def test_serena_tool_resets_counters(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Using a Serena tool should reset counters, so the threshold is not reached."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD - 1):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        with patch("sys.stdin", _make_stdin(_base_input("mcp_serena_find_symbol"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        assert capsys.readouterr().out == ""

    def test_counter_resets_after_deny(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """After a deny is emitted, the counter is reset so the next burst starts fresh."""
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()
        capsys.readouterr()

        with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        assert capsys.readouterr().out == ""

    def test_rate_limit_gates_entire_hook_within_interval(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """While within the rate-limit window, the entire hook must be a no-op:
        no deny is emitted, AND the persisted counters must remain untouched.
        """
        # first burst: should emit a deny
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()
        first_output = capsys.readouterr().out.strip()
        assert first_output, "first burst should have emitted a deny"

        # snapshot the persisted counter immediately after the deny was emitted
        stub_for_path = object.__new__(PreToolUseRemindAboutSymbolicToolsHook)
        stub_for_path.session_persistence_dir = str(tmp_path / "hook_data" / _base_input()["session_id"])
        counter_before = ToolUseCounter.load(stub_for_path)

        # second burst immediately after: within the rate-limit window, the entire
        # hook must short-circuit — no deny output and no counter mutation
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        assert capsys.readouterr().out == ""

        counter_after = ToolUseCounter.load(stub_for_path)
        assert counter_after == counter_before, "gated hook must not mutate the persisted counter"

    def test_rate_limit_allows_deny_after_interval(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Once the minimum deny interval has elapsed, a fresh burst emits a deny again."""
        # first burst: emits a deny
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()
        capsys.readouterr()

        # backdate the persisted last_deny_timestamp so the rate-limit window has expired
        stub_for_path = object.__new__(PreToolUseRemindAboutSymbolicToolsHook)
        stub_for_path.session_persistence_dir = str(tmp_path / "hook_data" / _base_input()["session_id"])
        counter = ToolUseCounter.load(stub_for_path)
        assert counter.last_deny_timestamp is not None
        counter.last_deny_timestamp -= timedelta(seconds=ToolUseCounter._MIN_DENY_INTERVAL_SECONDS + 1)
        counter.save(stub_for_path)

        # second burst should now emit a deny again
        for _ in range(ToolUseCounter._GREP_USES_THRESHOLD):
            with patch("sys.stdin", _make_stdin(_base_input("grep"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
                PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        second_output = capsys.readouterr().out.strip()
        assert second_output, "after the rate-limit window elapsed, a new burst should emit a deny"
        result = json.loads(second_output)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_non_symbolic_deny_emitted_when_combined_threshold_tripped(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Pre-populated state trips only the combined non-symbolic counter (not per-tool ones)
        so execute() must fall through to the _build_non_symbolic_deny branch.
        """
        # pre-populate the pickle so only the combined counter is over threshold
        session_dir = tmp_path / "hook_data" / _base_input()["session_id"]
        session_dir.mkdir(parents=True)
        counter = ToolUseCounter(
            n_recent_grep_uses=ToolUseCounter._GREP_USES_THRESHOLD - 1,
            n_recent_read_file_uses=ToolUseCounter._READ_FILE_USES_THRESHOLD - 1,
            n_recent_non_symbolic_uses=ToolUseCounter._NON_SYMBOLIC_USES_THRESHOLD,
            last_grep_use_timestamp=datetime.now(),
            last_read_file_use_timestamp=datetime.now(),
            last_non_symbolic_use_timestamp=datetime.now(),
        )
        stub_for_path = object.__new__(PreToolUseRemindAboutSymbolicToolsHook)
        stub_for_path.session_persistence_dir = str(session_dir)
        counter.save(stub_for_path)

        # invoke execute with a neutral (non-grep, non-read, non-serena) tool so that
        # update() leaves the counters untouched and the fall-through branch is taken
        with patch("sys.stdin", _make_stdin(_base_input("Edit"))), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseRemindAboutSymbolicToolsHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        assert output, "expected a non-symbolic deny to be emitted"
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["permissionDecision"] == "deny"
        assert "symbolic" in hook_output["additionalContext"].lower()


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
        counter.last_grep_use_timestamp = now - timedelta(seconds=ToolUseCounter._GREP_RESET_PERIOD_SECONDS + 1)
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

        hook = self._make_hook_stub("read_file", now, file_path="src/foo.py")
        counter.update(hook)

        assert counter.n_recent_read_file_uses == 2

    def test_update_resets_read_file_outside_period(self):
        counter = ToolUseCounter()
        now = datetime.now()
        counter.last_read_file_use_timestamp = now - timedelta(seconds=ToolUseCounter._READ_FILE_RESET_PERIOD_SECONDS + 1)
        counter.n_recent_read_file_uses = 2

        hook = self._make_hook_stub("read_file", now, file_path="src/foo.py")
        counter.update(hook)

        assert counter.n_recent_read_file_uses == 1

    def test_update_ignores_read_of_non_code_file(self):
        """A read call whose payload points at a non-source file does not increment the code-read counter."""
        counter = ToolUseCounter()
        now = datetime.now()

        hook = self._make_hook_stub("read_file", now, file_path="notes/todo.txt")
        counter.update(hook)

        assert counter.n_recent_read_file_uses == 0
        assert counter.last_read_file_use_timestamp is None

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

    def test_is_hook_active_respects_min_interval(self):
        """:meth:`is_hook_active` returns False within the minimum interval, True outside it."""
        counter = ToolUseCounter()
        base = datetime.now()

        # no prior deny → hook is always active
        assert counter.is_hook_active(base)

        # within the interval → hook gated
        counter.last_deny_timestamp = base
        interval = ToolUseCounter._MIN_DENY_INTERVAL_SECONDS
        assert not counter.is_hook_active(base + timedelta(seconds=interval - 1))
        assert not counter.is_hook_active(base)

        # at/after the interval → hook active again
        assert counter.is_hook_active(base + timedelta(seconds=interval))
        assert counter.is_hook_active(base + timedelta(seconds=interval + 1))

    def test_reset_preserves_last_deny_timestamp(self):
        """``reset`` clears burst counters but must keep ``last_deny_timestamp`` intact."""
        counter = ToolUseCounter()
        base = datetime.now()
        counter.last_deny_timestamp = base
        counter.n_recent_grep_uses = 5
        counter.n_recent_read_file_uses = 4
        counter.n_recent_non_symbolic_uses = 7

        counter.reset()

        assert counter.n_recent_grep_uses == 0
        assert counter.n_recent_read_file_uses == 0
        assert counter.n_recent_non_symbolic_uses == 0
        assert counter.last_deny_timestamp == base

    @staticmethod
    def _make_hook_stub(
        tool_name: str,
        timestamp: datetime,
        file_path: str | None = None,
        command_args_str: str | None = None,
    ) -> PreToolUseRemindAboutSymbolicToolsHook:
        """Create a minimal stub that satisfies ToolUseCounter.update without reading stdin.

        Uses ``HookClient.VSCODE`` so that ``is_grep_tool`` / ``is_read_file_tool`` apply the
        substring-matching branch — the counter tests below feed verbose tool names like
        ``grep_search`` / ``read_file`` which are only recognized under the non-Claude-Code
        branch (Claude Code uses exact names ``grep`` / ``read``).

        :param file_path: optional payload path; the hook classifies read-style tools as
            file reads regardless of the path extension.
        :param command_args_str: optional shell-argument tail; equivalent to ``file_path`` but
            populates the ``cmd``-derived field instead of ``file_path``.
        """
        stub = object.__new__(PreToolUseRemindAboutSymbolicToolsHook)
        stub._tool_name = tool_name.lower()
        stub._client = HookClient.VSCODE
        stub.triggered_at_timestamp = timestamp
        stub._command = None
        stub._command_name = None
        stub._command_args_str = command_args_str
        stub._file_path = file_path
        return stub


class TestPreToolUseAutoApproveSerenaHook:
    """Tests for the auto-approve hook that allows Serena tools while the client is in a permissive permission mode (``acceptEdits`` or ``auto``)."""

    @staticmethod
    def _approve_input(
        tool_name: str = "mcp__serena__find_symbol",
        permission_mode: str | None = "acceptEdits",
        session_id: str = "auto-approve-session",
        permission_mode_key: str = "permission_mode",
    ) -> dict:
        data: dict = {
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_input": {},
        }
        if permission_mode is not None:
            data[permission_mode_key] = permission_mode
        return data

    def test_approves_serena_tool_in_accept_edits_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """When the tool is a Serena tool and the mode is ``acceptEdits``, an allow decision is emitted."""
        stdin_data = self._approve_input()
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "PreToolUse"
        assert hook_output["permissionDecision"] == "allow"
        assert "acceptedits" in hook_output["permissionDecisionReason"].lower()

    def test_approves_serena_tool_in_auto_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """When the tool is a Serena tool and the mode is ``auto``, an allow decision is emitted.

        Claude Code's ``auto`` mode is the hands-off-execution mode users adopt for autonomous
        runs; Serena tool calls should be auto-approved there for the same reason as in
        ``acceptEdits`` (Serena's destructive tools would otherwise still prompt per call).
        """
        stdin_data = self._approve_input(permission_mode="auto")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        result = json.loads(output)
        hook_output = result["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "PreToolUse"
        assert hook_output["permissionDecision"] == "allow"
        # the reason must identify the actual mode that triggered the approval, not just say
        # "auto-approved" — the substring " auto " (with surrounding spaces) discriminates the
        # mode name from the unrelated "Auto-approved" prefix.
        assert " auto " in hook_output["permissionDecisionReason"]

    def test_accepts_camel_case_permission_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """The hook also reads the ``permissionMode`` (camelCase) variant of the field."""
        stdin_data = self._approve_input(permission_mode_key="permissionMode")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()

        output = capsys.readouterr().out.strip()
        assert json.loads(output)["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_stays_silent_for_non_serena_tool(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Non-Serena tools get no decision even in ``acceptEdits`` mode (the hook stays silent)."""
        stdin_data = self._approve_input(tool_name="Grep")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_stays_silent_in_default_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Serena tools in ``default`` mode get no decision (the hook stays silent)."""
        stdin_data = self._approve_input(permission_mode="default")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_stays_silent_in_plan_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """Other permission modes (e.g. ``plan``) must not trigger an auto-approve."""
        stdin_data = self._approve_input(permission_mode="plan")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_stays_silent_in_bypass_permissions_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """``bypassPermissions`` already approves everything upstream in Claude Code, so the
        hook deliberately does not emit an explicit allow there — it stays silent.

        This test pins that boundary: only ``acceptEdits`` and ``auto`` are active modes for the
        hook; expanding it further requires a deliberate change here.
        """
        stdin_data = self._approve_input(permission_mode="bypassPermissions")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_stays_silent_in_dont_ask_mode(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """``dontAsk`` is the user's deny-by-default posture (auto-deny unless allow-listed);
        the hook honors that choice and stays silent rather than overriding it.
        """
        stdin_data = self._approve_input(permission_mode="dontAsk")
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""

    def test_stays_silent_when_permission_mode_missing(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        """If ``permission_mode`` is missing from the input, the hook stays silent rather than erroring."""
        stdin_data = self._approve_input(permission_mode=None)
        with patch("sys.stdin", _make_stdin(stdin_data)), patch("serena.hooks.serena_home_dir", str(tmp_path)):
            PreToolUseAutoApproveSerenaHook(HookClient.CLAUDE_CODE).execute()
        assert capsys.readouterr().out == ""


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
            stdin_json = json.dumps({"session_id": "cli-remind", "tool_name": "grep", "tool_input": {}})
            with patch("serena.hooks.serena_home_dir", str(tmp_path)):
                result = runner.invoke(hook_commands, ["remind", "--client", "claude-code"], input=stdin_json)
            assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_auto_approve_command(self, tmp_path: Path):
        """The ``auto-approve`` CLI command emits an allow for a Serena tool in acceptEdits mode."""
        stdin_json = json.dumps(
            {
                "session_id": "cli-auto-approve",
                "tool_name": "mcp__serena__find_symbol",
                "tool_input": {},
                "permission_mode": "acceptEdits",
            }
        )
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["auto-approve", "--client", "claude-code"], input=stdin_json)
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_auto_approve_command_in_auto_mode(self, tmp_path: Path):
        """The ``auto-approve`` CLI command emits an allow for a Serena tool in ``auto`` mode."""
        stdin_json = json.dumps(
            {
                "session_id": "cli-auto-approve-auto-mode",
                "tool_name": "mcp__serena__find_symbol",
                "tool_input": {},
                "permission_mode": "auto",
            }
        )
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["auto-approve", "--client", "claude-code"], input=stdin_json)
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_auto_approve_command_stays_silent_in_default_mode(self, tmp_path: Path):
        """The ``auto-approve`` CLI command emits nothing when the mode is not ``acceptEdits``."""
        stdin_json = json.dumps(
            {
                "session_id": "cli-auto-approve-default",
                "tool_name": "mcp__serena__find_symbol",
                "tool_input": {},
                "permission_mode": "default",
            }
        )
        runner = CliRunner()
        with patch("serena.hooks.serena_home_dir", str(tmp_path)):
            result = runner.invoke(hook_commands, ["auto-approve", "--client", "claude-code"], input=stdin_json)
        assert result.exit_code == 0
        assert result.output == ""

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
