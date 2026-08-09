from types import SimpleNamespace

from click.testing import CliRunner

from serena.cli import TopLevelCommands
from serena.util.shell import ShellCommandResult

GROK_ADD_COMMAND = "grok mcp add --scope user serena -- serena start-mcp-server --context=grok --project-from-cwd"


def _result(command: str, return_code: int = 0, stdout: str = "", stderr: str = "") -> ShellCommandResult:
    return ShellCommandResult(stdout=stdout, stderr=stderr, return_code=return_code, cwd=".")


def test_setup_grok_success(monkeypatch):
    commands: list[str] = []

    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        commands.append(command)
        if command == "grok --version":
            return _result(command, stdout="grok 0.2.82 (6d0b07d2de) [stable]\n")
        if command == "grok mcp add --help":
            return _result(command, stdout="Add or update an MCP server\n")
        if command == GROK_ADD_COMMAND:
            return _result(command)
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    result = CliRunner().invoke(TopLevelCommands.setup, ["grok"])

    assert result.exit_code == 0, result.output
    assert "successfully set up for grok" in result.output
    assert "recommend" in result.output.lower()
    assert "030_clients.html#grok" in result.output
    assert commands == ["grok --version", "grok mcp add --help", GROK_ADD_COMMAND]


def test_setup_grok_not_applicable_exits_1(monkeypatch):
    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        if command == "grok --version":
            return _result(command, return_code=1)
        return _result(command)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    result = CliRunner().invoke(TopLevelCommands.setup, ["grok"])

    assert result.exit_code == 1
    assert "Cannot apply setup for client 'grok'" in result.output


def test_setup_grok_apply_failure_exits_1(monkeypatch):
    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        if command == "grok --version":
            return _result(command, stdout="grok 0.2.82 (6d0b07d2de) [stable]\n")
        if command == "grok mcp add --help":
            return _result(command, stdout="Add or update an MCP server\n")
        if command == GROK_ADD_COMMAND:
            return _result(command, return_code=1, stderr="boom")
        return _result(command, return_code=1)

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)

    result = CliRunner().invoke(TopLevelCommands.setup, ["grok"])

    assert result.exit_code == 1
    assert "Failed to set up Serena for grok" in result.output
    assert "recommend" not in result.output.lower()
    assert "030_clients.html#grok" not in result.output


def test_init_suggests_grok_when_detected(monkeypatch):
    def fake_execute_shell_command(command: str, capture_stderr: bool = False) -> ShellCommandResult:
        if command == "grok --version":
            return _result(command, stdout="grok 0.2.82 (6d0b07d2de) [stable]\n")
        if command == "grok mcp add --help":
            return _result(command, stdout="Add or update an MCP server\n")
        return _result(command, return_code=1)

    def fake_init(**kwargs) -> SimpleNamespace:
        return SimpleNamespace(config_file_path="/tmp/serena_config.yml")

    monkeypatch.setattr("serena.config.client_setup.execute_shell_command", fake_execute_shell_command)
    monkeypatch.setattr("serena.cli.SerenaConfig.init", fake_init)

    result = CliRunner().invoke(TopLevelCommands.init, [])

    assert result.exit_code == 0, result.output
    assert "serena setup grok" in result.output
    assert "serena setup claude-code" not in result.output
