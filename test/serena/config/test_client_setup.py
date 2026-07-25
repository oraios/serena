import json
from pathlib import Path

import pytest

from serena.config.client_setup import ClientSetupHandlerDevin, ClientSetupHandlerGrok, client_setup_handlers
from serena.config.context_mode import SerenaAgentContext
from serena.util.shell import ShellCommandResult


def _result(command: str, return_code: int = 0, stdout: str = "") -> ShellCommandResult:
    return ShellCommandResult(stdout=stdout, stderr="", return_code=return_code, cwd=".")


def test_grok_setup_handler_is_applicable_for_grok_build(monkeypatch):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "grok --version":
            return _result(command, stdout="grok 0.2.82 (6d0b07d2de) [stable]\n")
        if command == "grok mcp add --help":
            return _result(command, stdout="Add or update an MCP server\n")
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerGrok().is_applicable() is True
    assert commands == ["grok --version", "grok mcp add --help"]


def test_grok_setup_handler_rejects_binary_without_mcp_add(monkeypatch):
    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        if command == "grok --version":
            return _result(command, stdout="grok 0.2.82 (6d0b07d2de) [stable]\n")
        return _result(command, return_code=1, stdout="unknown command\n")

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerGrok().is_applicable() is False


@pytest.mark.parametrize(
    ("return_code", "stdout"),
    [
        (1, ""),
        (0, "0.0.34\n"),
        (0, "my-grok wrapper 1.0\n"),
        (0, "grok\n"),
        (0, "  grok 0.2.82"),
    ],
)
def test_grok_setup_handler_short_circuits_when_version_probe_does_not_match(monkeypatch, return_code: int, stdout: str):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "grok --version":
            return _result(command, return_code=return_code, stdout=stdout)
        return _result(command, stdout="Add or update an MCP server\n")

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerGrok().is_applicable() is False
    assert commands == ["grok --version"]


def test_grok_setup_handler_accepts_case_insensitive_grok_version(monkeypatch):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "grok --version":
            return _result(command, stdout="Grok 0.3.0 [stable]")
        if command == "grok mcp add --help":
            return _result(command, stdout="Add or update an MCP server\n")
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerGrok().is_applicable() is True
    assert commands == ["grok --version", "grok mcp add --help"]


@pytest.mark.parametrize("help_stdout", ["Usage: grok mcp add\n", "add or update an mcp server\n"])
def test_grok_setup_handler_rejects_mcp_add_help_without_expected_text(monkeypatch, help_stdout: str):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "grok --version":
            return _result(command, stdout="grok 0.2.82 (6d0b07d2de) [stable]\n")
        if command == "grok mcp add --help":
            return _result(command, stdout=help_stdout)
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerGrok().is_applicable() is False
    assert commands == ["grok --version", "grok mcp add --help"]


def test_grok_setup_handler_apply_uses_grok_mcp_add(monkeypatch):
    commands: list[str] = []

    def fake_run_shell_command(self: ClientSetupHandlerGrok, command: str) -> bool:
        commands.append(command)
        return True

    monkeypatch.setattr(ClientSetupHandlerGrok, "_run_shell_command", fake_run_shell_command)

    assert ClientSetupHandlerGrok().apply() is True
    assert commands == ["grok mcp add --scope user serena -- serena start-mcp-server --context=grok --project-from-cwd"]


def test_grok_setup_handler_apply_failure_skips_hook_recommendation(monkeypatch, capsys):
    def fake_run_shell_command(self: ClientSetupHandlerGrok, command: str) -> bool:
        return False

    monkeypatch.setattr(ClientSetupHandlerGrok, "_run_shell_command", fake_run_shell_command)

    assert ClientSetupHandlerGrok().apply() is False
    assert "recommend" not in capsys.readouterr().out.lower()


def test_client_setup_handlers_use_resolvable_contexts():
    handler_names = [handler.name for handler in client_setup_handlers]
    assert "grok" in handler_names

    for handler in client_setup_handlers:
        context_options = [option for option in handler.get_mcp_server_options() if option.startswith("--context=")]
        assert len(context_options) == 1
        context_name = context_options[0].removeprefix("--context=")
        assert SerenaAgentContext.from_name(context_name).name == context_name


def test_devin_setup_handler_is_applicable_for_devin_cli(monkeypatch):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "devin --version":
            return _result(command, stdout="devin 3000.2.17 (2c489dfc)\n")
        if command == "devin mcp add --help":
            return _result(command, stdout="Add a new MCP server.\n")
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerDevin().is_applicable() is True
    assert commands == ["devin --version", "devin mcp add --help"]


def test_devin_setup_handler_rejects_binary_without_mcp_add(monkeypatch):
    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        if command == "devin --version":
            return _result(command, stdout="devin 3000.2.17 (2c489dfc)\n")
        return _result(command, return_code=1, stdout="unknown command\n")

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerDevin().is_applicable() is False


def test_devin_setup_handler_apply_uses_devin_mcp_add(monkeypatch):
    commands: list[str] = []

    def fake_run_shell_command(self: ClientSetupHandlerDevin, command: str) -> bool:
        commands.append(command)
        return True

    monkeypatch.setattr(ClientSetupHandlerDevin, "_run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(ClientSetupHandlerDevin, "_configure_devin_config", lambda self, scope: True)

    assert ClientSetupHandlerDevin().apply() is True
    assert commands == [
        "devin mcp add -s user serena -- serena start-mcp-server --context=devin --enable-web-dashboard false --open-web-dashboard false --add-mode query-projects --project-from-cwd"
    ]


@pytest.mark.parametrize(
    ("return_code", "stdout"),
    [
        (1, ""),
        (0, "0.0.34\n"),
        (0, "my-devin wrapper 1.0\n"),
        (0, "devin\n"),
        (0, "  devin 3000.2.17"),
    ],
)
def test_devin_setup_handler_short_circuits_when_version_probe_does_not_match(monkeypatch, return_code: int, stdout: str):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "devin --version":
            return _result(command, return_code=return_code, stdout=stdout)
        return _result(command, stdout="Add a new MCP server.\n")

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerDevin().is_applicable() is False
    assert commands == ["devin --version"]


@pytest.mark.parametrize("help_stdout", ["Usage: devin mcp add\n", "add a new mcp server\n"])
def test_devin_setup_handler_rejects_mcp_add_help_without_expected_text(monkeypatch, help_stdout: str):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "devin --version":
            return _result(command, stdout="devin 3000.2.17 (2c489dfc)\n")
        if command == "devin mcp add --help":
            return _result(command, stdout=help_stdout)
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    assert ClientSetupHandlerDevin().is_applicable() is False
    assert commands == ["devin --version", "devin mcp add --help"]


def test_devin_setup_handler_writes_full_config(monkeypatch, tmp_path: Path):
    handler = ClientSetupHandlerDevin()
    config_path = tmp_path / "config.json"
    initial = {
        "mcpServers": {
            "serena": {
                "command": "serena",
                "args": ["start-mcp-server", "--context=devin", "--project-from-cwd"],
            }
        }
    }
    config_path.write_text(json.dumps(initial))
    monkeypatch.setattr(handler, "_devin_config_path", lambda scope: config_path)

    assert handler._configure_devin_config("user") is True

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["mcpServers"]["serena"]["command"] == "serena"
    assert "mcp__serena__*" in config["permissions"]["allow"]
    assert any(entry.get("hooks", [])[0].get("command") == "serena-hooks remind --client=devin" for entry in config["hooks"]["PreToolUse"])
    assert any(
        entry.get("hooks", [])[0].get("command") == "serena-hooks post-remind --client=devin" for entry in config["hooks"]["PostToolUse"]
    )
    assert any("--include-instructions" in entry.get("hooks", [])[0].get("command", "") for entry in config["hooks"]["PostCompaction"])


def test_devin_setup_handler_removes_stale_node_hooks(monkeypatch, tmp_path: Path):
    handler = ClientSetupHandlerDevin()
    config_path = tmp_path / "config.json"
    initial = {
        "mcpServers": {"serena": {"command": "serena", "args": ["start-mcp-server"]}},
        "hooks": {
            "SessionStart": [
                {"hooks": [{"type": "command", "command": 'node "$HOME/.config/devin/hooks/serena/serena-devin.js" SessionStart'}]},
                {"hooks": [{"type": "command", "command": "serena-hooks activate --client=devin"}]},
            ]
        },
    }
    config_path.write_text(json.dumps(initial))
    monkeypatch.setattr(handler, "_devin_config_path", lambda scope: config_path)

    assert handler._configure_devin_config("user") is True
    config = json.loads(config_path.read_text(encoding="utf-8"))
    session_start = config["hooks"]["SessionStart"]
    assert all("serena-devin.js" not in entry["hooks"][0]["command"] for entry in session_start)
    assert any(entry["hooks"][0]["command"] == "serena-hooks activate --client=devin" for entry in session_start)
