"""Tests for CLI setup commands."""

import subprocess
import tomllib

from click.testing import CliRunner

from serena.cli import SetupCommands, top_level


def test_claude_code_setup_user_scope_invokes_documented_command(monkeypatch):
    """User-scope Claude Code setup should call the documented Claude CLI command."""
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run(command, *, check, **kwargs):
        captured["command"] = command
        captured["check"] = check
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("serena.cli.subprocess.run", fake_run)

    result = runner.invoke(top_level, ["setup", "claude-code"])

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "Configured Serena for Claude Code."
    assert captured["check"] is True
    assert captured["command"] == [
        "claude",
        "mcp",
        "add",
        "--scope",
        "user",
        "serena",
        "--",
        "uvx",
        "--python",
        "3.13",
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context=claude-code",
        "--project-from-cwd",
    ]


def test_claude_code_setup_project_scope_uses_given_project(monkeypatch, tmp_path):
    """Project-scope Claude Code setup should use the requested project path."""
    runner = CliRunner()
    captured: list[str] = []

    def fake_run(command, *, check, **kwargs):
        del check, kwargs
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("serena.cli.subprocess.run", fake_run)

    result = runner.invoke(SetupCommands.claude_code, ["--scope", "project", "--project", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert captured == [
        "claude",
        "mcp",
        "add",
        "serena",
        "--",
        "uvx",
        "--python",
        "3.13",
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "claude-code",
        "--project",
        str(tmp_path.resolve()),
    ]


def test_codex_setup_creates_config(monkeypatch, tmp_path):
    """Codex setup should create the expected Serena config section."""
    runner = CliRunner()
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(top_level, ["setup", "codex"])

    assert result.exit_code == 0, result.output
    config_path = tmp_path / ".codex" / "config.toml"
    assert config_path.exists()

    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["mcp_servers"]["serena"] == {
        "startup_timeout_sec": 25,
        "command": "uvx",
        "args": [
            "-p",
            "3.13",
            "--from",
            "git+https://github.com/oraios/serena",
            "serena",
            "start-mcp-server",
            "--project-from-cwd",
            "--context",
            "codex",
        ],
    }


def test_codex_setup_replaces_existing_serena_section(tmp_path):
    """Codex setup should update the Serena table without dropping other tables."""
    runner = CliRunner()
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[profiles.default]
model = "gpt-5"

[mcp_servers.serena]
startup_timeout_sec = 5
command = "old"
args = ["--old"]

[mcp_servers.other]
command = "keep"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(SetupCommands.codex, ["--config-path", str(config_path)])

    assert result.exit_code == 0, result.output
    content = config_path.read_text(encoding="utf-8")
    assert content.count("[mcp_servers.serena]") == 1

    parsed = tomllib.loads(content)
    assert parsed["profiles"]["default"]["model"] == "gpt-5"
    assert parsed["mcp_servers"]["other"]["command"] == "keep"
    assert parsed["mcp_servers"]["serena"]["command"] == "uvx"
